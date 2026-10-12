"""Run the small RAGAS POC against the real LangGraph retrieval pipeline."""
import json
import math
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from chatapp.evaluation import (
    format_retrieved_contexts,
    load_evaluation_cases,
    serialise_retrieved_contexts,
)
from chatapp.orchestration import chat_graph
from chatapp.ragas_compat import prepare_ragas_imports

# Set to an integer to run that many cases from evaluation_cases.json.
# Set to None to run every case.
CASE_LIMIT: int | None = None

METRIC_NAMES = ("context_precision", "context_recall", "factual_correctness")
SCORE_DECIMALS = 4
# Gemini can temporarily return 503 under high demand. Keep these low enough
# for local runs while giving transient failures a chance to recover.
EVALUATOR_MAX_RETRIES = 3
EVALUATION_MAX_WORKERS = 1


class Command(BaseCommand):
    help = "Evaluate selected movie GraphRAG test cases with RAGAS."

    @staticmethod
    def _clean_score(value):
        """Return a rounded float, or None when the metric was not scored (None/NaN)."""
        if value is None:
            return None
        try:
            value = float(value)
        except (TypeError, ValueError):
            return None
        if math.isnan(value) or math.isinf(value):
            return None
        return round(value, SCORE_DECIMALS)

    @staticmethod
    def _as_context_list(contexts):
        """Always return the retrieved contexts as a list of strings."""
        if contexts is None:
            return []
        if isinstance(contexts, (list, tuple)):
            return [str(item) for item in contexts]
        return [str(contexts)]

    @classmethod
    def _build_json_report(cls, rows, report_frame, metric_names, generated_at,
                           evaluator_model):
        """Build the clean JSON structure: report metadata, summary averages, per-case results."""
        score_records = report_frame.to_dict("records")

        results = []
        for row, score_row in zip(rows, score_records):
            results.append({
                "case_id": row["case_id"],
                "question": row["question"],
                "retrieved_contexts": cls._as_context_list(row["contexts"]),
                "response": row["answer"],
                "reference": row["ground_truth"],
                "scores": {
                    name: cls._clean_score(score_row.get(name))
                    for name in metric_names
                },
            })

        # Average per metric, ignoring cases where the metric was not scored.
        summary = {}
        for name in metric_names:
            values = [
                result["scores"][name]
                for result in results
                if result["scores"][name] is not None
            ]
            summary[name] = (
                round(sum(values) / len(values), SCORE_DECIMALS) if values else None
            )

        return {
            "report": {
                "generated_at": generated_at.isoformat(timespec="seconds"),
                "evaluator_model": evaluator_model,
                "metrics": list(metric_names),
                "total_cases": len(results),
            },
            "summary": summary,
            "results": results,
        }

    @staticmethod
    def _write_markdown_report(output_file, report_frame, metric_names):
        """Write a readable companion report; the CSV remains spreadsheet-ready."""
        lines = ["# RAGAS evaluation report", "", f"Metrics: {', '.join(metric_names)}"]
        for row in report_frame.to_dict("records"):
            question = row.get("user_input", row.get("question", ""))
            contexts = row.get("retrieved_contexts", row.get("contexts", ""))
            response = row.get("response", row.get("answer", ""))
            reference = row.get("reference", row.get("ground_truth", ""))
            lines.extend([
                "",
                f"## {row['case_id']}",
                "",
                f"**Question:** {question}",
                "",
                f"**Retrieved context:** {contexts}",
                "",
                f"**Response:** {response}",
                "",
                f"**Reference:** {reference}",
                "",
                "| Metric | Score |",
                "| --- | ---: |",
            ])
            for metric_name in metric_names:
                score = row.get(metric_name)
                display_score = "not scored" if score is None or score != score else f"{score:.4f}"
                lines.append(f"| {metric_name} | {display_score} |")
        output_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir",
            default=settings.BASE_DIR / "evaluation_results",
            help="Directory in which to save the timestamped CSV, Markdown and JSON reports.",
        )

    def handle(self, *args, **options):
        prepare_ragas_imports()
        try:
            from datasets import Dataset
            from ragas import evaluate
            from ragas.llms import llm_factory
            from ragas.metrics import ContextPrecision, ContextRecall, FactualCorrectness
            from ragas.run_config import RunConfig
        except ImportError as exc:
            raise CommandError(
                "RAGAS dependencies are missing. Run: pip install -r requirements.txt"
            ) from exc

        if not settings.GEMINI_API_KEY:
            raise CommandError("GEMINI_API_KEY must be set to run RAGAS evaluation.")

        all_cases = load_evaluation_cases()
        if CASE_LIMIT is not None and CASE_LIMIT < 1:
            raise CommandError("CASE_LIMIT must be a positive integer or None.")
        cases = all_cases if CASE_LIMIT is None else all_cases[:CASE_LIMIT]
        self.stdout.write(
            f"Running {len(cases)} of {len(all_cases)} cases through LangGraph and Neo4j..."
        )

        rows = []
        for case in cases:
            result = chat_graph.invoke({
                "original_question": case["question"],
                "question": case["question"],
                "history": [],
                "retry_count": 0,
                "results": [],
            })
            answer = result.get("answer")
            contexts = serialise_retrieved_contexts(result.get("results", []))
            if not answer or not contexts:
                raise CommandError(
                    f"Pipeline did not retrieve an answer and context for case '{case['id']}'. "
                    "Check Neo4j, the Gemini configuration, and the generated Cypher."
                )
            rows.append({
                "case_id": case["id"],
                "question": case["question"],
                "answer": answer,
                "contexts": contexts,
                "ground_truth": case["reference_answer"],
            })

        from google import genai

        client = genai.Client(api_key=settings.GEMINI_API_KEY)

        # --- Evaluator LLM (Gemini) ---
        # If this raises "unexpected keyword argument" for max_retries,
        # delete that line; RunConfig below also handles retries.
        evaluator_llm = llm_factory(
            settings.RAGAS_EVALUATOR_MODEL,
            provider="google",
            client=client,
            max_retries=EVALUATOR_MAX_RETRIES,
        )

        # All three metrics use only the Gemini judge LLM (no embedding model).
        metrics = [
            ContextPrecision(llm=evaluator_llm),
            ContextRecall(llm=evaluator_llm),
            FactualCorrectness(llm=evaluator_llm),
        ]

        dataset = Dataset.from_dict({
            "question": [row["question"] for row in rows],
            "answer": [row["answer"] for row in rows],
            "contexts": [row["contexts"] for row in rows],
            "ground_truth": [row["ground_truth"] for row in rows],
        })

        self.stdout.write("Scoring with RAGAS (this makes evaluator-model API calls)...")

        try:
            report = evaluate(
                dataset,
                metrics=metrics,
                llm=evaluator_llm,
                run_config=RunConfig(
                    max_workers=EVALUATION_MAX_WORKERS,
                    max_retries=EVALUATOR_MAX_RETRIES,
                    max_wait=30,
                ),
                # Do not write a successful-looking report with null/NaN metrics.
                raise_exceptions=True,
            )
        except Exception as exc:
            raise CommandError(
                "RAGAS could not finish every metric. Gemini may be temporarily "
                "busy; wait a moment and run the command again. "
                f"Original error: {exc}"
            ) from exc

        report_frame = report.to_pandas()
        # RAGAS may name this column "factual_correctness(mode=f1)"; normalise it.
        report_frame = report_frame.rename(columns={
            col: "factual_correctness"
            for col in report_frame.columns
            if str(col).startswith("factual_correctness")
        })
        report_frame.insert(0, "case_id", [row["case_id"] for row in rows])
        context_column = (
            "retrieved_contexts"
            if "retrieved_contexts" in report_frame.columns
            else "contexts"
        )
        report_frame[context_column] = [
            format_retrieved_contexts(row["contexts"])
            for row in rows
        ]

        output_dir = Path(options["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        generated_at = datetime.now()
        timestamp = generated_at.strftime("%Y%m%d_%H%M%S")

        # CSV (spreadsheet-ready)
        output_file = output_dir / f"ragas_{timestamp}.csv"
        report_frame.to_csv(output_file, index=False)

        # Markdown (human-readable)
        markdown_file = output_dir / f"ragas_{timestamp}.md"
        self._write_markdown_report(markdown_file, report_frame, METRIC_NAMES)

        # JSON (clean, structured)
        json_file = output_dir / f"ragas_{timestamp}.json"
        json_report = self._build_json_report(
            rows=rows,
            report_frame=report_frame,
            metric_names=METRIC_NAMES,
            generated_at=generated_at,
            evaluator_model=settings.RAGAS_EVALUATOR_MODEL,
        )
        json_file.write_text(
            json.dumps(json_report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        self.stdout.write(self.style.SUCCESS(f"RAGAS report saved to {output_file}"))
        self.stdout.write(self.style.SUCCESS(f"Readable report saved to {markdown_file}"))
        self.stdout.write(self.style.SUCCESS(f"JSON report saved to {json_file}"))
        self.stdout.write(str(report))