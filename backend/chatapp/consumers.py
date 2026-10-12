import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async

from .orchestration import chat_graph, next_graph_event

logger = logging.getLogger(__name__)


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Holds context only while this WebSocket remains connected.
        self.conversation_history = []
        await self.accept()
        await self.send(json.dumps({
            "type": "system",
            "message": "Connected. Ask a question about the movie graph!",
        }))

    async def disconnect(self, close_code):
        pass

    async def receive(self, text_data):
        try:
            payload = json.loads(text_data)
        except json.JSONDecodeError:
            await self._send_error("Message must be valid JSON: {\"message\": \"...\"}")
            return

        question = (payload.get("message") or "").strip()
        if not question:
            await self._send_error("Empty question.")
            return

        initial_state = {
            "original_question": question,
            "question": question,
            "history": self.conversation_history,
            "retry_count": 0,
            "results": [],
        }
        final_state = dict(initial_state)
        status_by_node = {
            "rewrite_question": "Understanding follow-up question...",
            "generate_cypher": "Generating Cypher query...",
            "validate_cypher": "Validating read-only Cypher...",
            "run_query": "Querying Neo4j...",
            "repair_cypher": "Repairing Cypher query...",
            "generate_answer": "Generating answer...",
        }

        try:
            iterator = chat_graph.stream(initial_state, stream_mode="updates")
            while True:
                event = await sync_to_async(next_graph_event)(iterator)
                if event is None:
                    break
                node_name, update = next(iter(event.items()))
                final_state.update(update)
                if node_name in status_by_node:
                    await self.send(json.dumps({
                        "type": "status",
                        "message": status_by_node[node_name],
                        "cypher": final_state.get("cypher"),
                    }))
                if node_name == "rewrite_question":
                    rewritten_question = final_state.get("rewritten_question", question)
                    if rewritten_question.casefold().strip() != question.casefold().strip():
                        await self.send(json.dumps({
                            "type": "rewrite",
                            "original_question": question,
                            "rewritten_question": rewritten_question,
                        }))
        except Exception as exc:
            logger.exception("LangGraph chat orchestration failed")
            await self._send_error(f"Unable to process question: {exc}", final_state.get("cypher"))
            return

        await self.send(json.dumps({
            "type": "answer",
            "question": question,
            "cypher": final_state.get("cypher"),
            "results": final_state.get("results", []),
            "answer": final_state.get("answer"),
            "rewritten_question": final_state.get("rewritten_question", question),
        }))

        self.conversation_history.extend([
            {"role": "user", "content": question},
            {"role": "assistant", "content": final_state.get("answer") or ""},
        ])
        # Bound memory for a long-lived socket, while retaining recent turns.
        self.conversation_history = self.conversation_history[-12:]

    async def _send_error(self, message, cypher=None):
        await self.send(json.dumps({"type": "error", "message": message, "cypher": cypher}))
