from unittest import TestCase
from unittest.mock import patch

from chatapp.cypher_guard import CypherValidationError, validate_read_only_cypher
from chatapp.evaluation import load_evaluation_cases, serialise_retrieved_contexts
from chatapp.ragas_compat import prepare_ragas_imports
from chatapp.orchestration import chat_graph


class CypherGuardTests(TestCase):
    def test_allows_limited_read_query(self):
        validate_read_only_cypher(
            'MATCH (m:Movie {title: "The Matrix"}) RETURN m.title LIMIT 25'
        )

    def test_rejects_write_query(self):
        with self.assertRaises(CypherValidationError):
            validate_read_only_cypher("MATCH (m:Movie) DELETE m RETURN m LIMIT 25")


class EvaluationCaseTests(TestCase):
    def test_poc_cases_are_well_formed_and_small(self):
        cases = load_evaluation_cases()
        self.assertEqual(len(cases), 5)
        self.assertTrue(all(case["question"] and case["reference_answer"] for case in cases))

    def test_neo4j_records_become_ragas_contexts(self):
        contexts = serialise_retrieved_contexts([{"director": "Lana Wachowski"}])
        self.assertEqual(contexts, ['{"director": "Lana Wachowski"}'])

    def test_ragas_compatibility_bridge_can_be_prepared(self):
        prepare_ragas_imports()
        from langchain_community.chat_models.vertexai import ChatVertexAI
        from langchain_community.llms import VertexAI

        self.assertIsInstance(ChatVertexAI, type)
        self.assertIsInstance(VertexAI, type)


class ChatGraphTests(TestCase):
    def test_rewrites_a_follow_up_before_generating_cypher(self):
        rewritten = "Who was Robert Zemeckis?"
        cypher = 'MATCH (p:Person {name: "Robert Zemeckis"}) RETURN p.name, p.born LIMIT 25'
        with (
            patch(
                "chatapp.orchestration.gemini_service.rewrite_question", return_value=rewritten
            ),
            patch("chatapp.orchestration.gemini_service.generate_cypher", return_value=cypher) as generate,
            patch(
                "chatapp.orchestration.neo4j_service.run_cypher",
                return_value=[{"name": "Robert Zemeckis", "born": 1952}],
            ),
            patch(
                "chatapp.orchestration.gemini_service.generate_answer",
                return_value="Robert Zemeckis is an American film director born in 1952.",
            ),
        ):
            result = chat_graph.invoke({
                "original_question": "Who was he?",
                "question": "Who was he?",
                "history": [
                    {"role": "user", "content": "Who directed Forrest Gump?"},
                    {"role": "assistant", "content": "Robert Zemeckis directed Forrest Gump."},
                ],
                "retry_count": 0,
                "results": [],
            })

        generate.assert_called_once_with(rewritten)
        self.assertEqual(result["rewritten_question"], rewritten)
        self.assertEqual(result["answer"], "Robert Zemeckis is an American film director born in 1952.")

    def test_repairs_an_unsafe_generated_query_once(self):
        repaired = "MATCH (m:Movie) RETURN m.title LIMIT 25"
        with (
            patch("chatapp.orchestration.gemini_service.rewrite_question", return_value="List movies"),
            patch(
                "chatapp.orchestration.gemini_service.generate_cypher",
                return_value="MATCH (m:Movie) DELETE m RETURN m LIMIT 25",
            ),
            patch(
                "chatapp.orchestration.gemini_service.repair_cypher", return_value=repaired
            ) as repair,
            patch("chatapp.orchestration.neo4j_service.run_cypher", return_value=[]),
            patch(
                "chatapp.orchestration.gemini_service.generate_answer",
                return_value="No matching data was found.",
            ),
        ):
            result = chat_graph.invoke(
                {"question": "List movies", "retry_count": 0, "results": []}
            )

        self.assertEqual(repair.call_count, 1)
        self.assertEqual(result["cypher"], repaired)
        self.assertEqual(result["retry_count"], 1)
        self.assertEqual(result["answer"], "No matching data was found.")
