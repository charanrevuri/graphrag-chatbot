"""Helpers shared by the small, graph-grounded RAGAS evaluation POC."""
import json
from pathlib import Path


CASE_FILE = Path(__file__).with_name("evaluation_cases.json")
REQUIRED_CASE_FIELDS = {"id", "question", "reference_answer"}


def load_evaluation_cases(path: Path = CASE_FILE) -> list[dict[str, str]]:
    """Load and minimally validate the hand-authored evaluation cases."""
    cases = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(cases, list) or not cases:
        raise ValueError("Evaluation cases must be a non-empty JSON array.")

    for index, case in enumerate(cases, start=1):
        if not isinstance(case, dict) or not REQUIRED_CASE_FIELDS.issubset(case):
            raise ValueError(
                f"Case {index} must include: {', '.join(sorted(REQUIRED_CASE_FIELDS))}."
            )
    return cases


def serialise_retrieved_contexts(results: list[dict]) -> list[str]:
    """Make Neo4j records consumable by RAGAS context metrics."""
    return [json.dumps(record, default=str, sort_keys=True) for record in results]


def format_retrieved_contexts(contexts: list[str]) -> str:
    """Turn the JSON strings used by RAGAS into readable report text."""
    formatted_records = []
    for context in contexts:
        try:
            record = json.loads(context)
        except (TypeError, json.JSONDecodeError):
            formatted_records.append(str(context))
            continue

        if isinstance(record, dict):
            fields = []
            for key, value in record.items():
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, ensure_ascii=False)
                fields.append(f"{key}: {value}")
            formatted_records.append("; ".join(fields))
        else:
            formatted_records.append(str(record))
    return " | ".join(formatted_records)
