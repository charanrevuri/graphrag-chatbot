"""LangGraph orchestration for the GraphRAG chat request lifecycle."""
import logging
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from . import gemini_service, neo4j_service
from .cypher_guard import CypherValidationError, validate_read_only_cypher


MAX_REPAIR_ATTEMPTS = 1
logger = logging.getLogger(__name__)

# schema for the shared state
    
class ChatState(TypedDict, total=False):
    original_question: str
    question: str
    rewritten_question: str
    history: list[dict[str, str]]
    cypher: str | None
    results: list[dict]
    answer: str | None
    query_error: str | None
    retry_count: int


def rewrite_question(state: ChatState) -> ChatState:
    """Resolve a follow-up question using the current WebSocket's prior turns."""
    original_question = state["question"]
    try:
        rewritten_question = gemini_service.rewrite_question(
            original_question, state.get("history", [])
        )
    except Exception:
        logger.exception("Question rewrite failed; using the original question")
        rewritten_question = original_question
    return {"question": rewritten_question, "rewritten_question": rewritten_question}


def generate_cypher(state: ChatState) -> ChatState:
    cypher = gemini_service.generate_cypher(state["question"])
    if cypher.strip().upper() == "NO_QUERY":
        return {"cypher": None}
    return {"cypher": cypher, "query_error": None}


def validate_cypher(state: ChatState) -> ChatState:
    try:
        validate_read_only_cypher(state["cypher"] or "")
    except CypherValidationError as exc:
        return {"query_error": str(exc)}
    return {"query_error": None}


def run_query(state: ChatState) -> ChatState:
    try:
        results = neo4j_service.run_cypher(state["cypher"] or "")
    except Exception as exc:
        return {"query_error": str(exc)}
    return {"results": results, "query_error": None}


def repair_cypher(state: ChatState) -> ChatState:
    cypher = gemini_service.repair_cypher(
        state["question"], state["cypher"] or "", state["query_error"] or "Unknown error"
    )
    if cypher.strip().upper() == "NO_QUERY":
        return {"cypher": None, "retry_count": state.get("retry_count", 0) + 1}
    return {
        "cypher": cypher,
        "query_error": None,
        "retry_count": state.get("retry_count", 0) + 1,
    }


def generate_answer(state: ChatState) -> ChatState:
    answer = gemini_service.generate_answer(
        state.get("original_question", state["question"]),
        state["cypher"] or "",
        state.get("results", []),
    )
    return {"answer": answer}


def unsupported_answer(_: ChatState) -> ChatState:
    return {"answer": "I can't answer that from the movie graph I have access to.", "results": []}


def failed_answer(state: ChatState) -> ChatState:
    return {
        "answer": "I couldn't create a safe query for that question. Please try rephrasing it.",
        "results": [],
    }


def after_generation(state: ChatState) -> str:
    return "unsupported" if state.get("cypher") is None else "validate"


def after_validation(state: ChatState) -> str:
    if not state.get("query_error"):
        return "query"
    return "repair" if state.get("retry_count", 0) < MAX_REPAIR_ATTEMPTS else "failed"


def after_query(state: ChatState) -> str:
    if not state.get("query_error"):
        return "answer"
    return "repair" if state.get("retry_count", 0) < MAX_REPAIR_ATTEMPTS else "failed"


def after_repair(state: ChatState) -> str:
    return "unsupported" if state.get("cypher") is None else "validate"


def build_chat_graph():
    graph = StateGraph(ChatState)

    # Registering  the processing nodes wherere each node represents a step in the chat request lifecycle
    graph.add_node("rewrite_question", rewrite_question)
    graph.add_node("generate_cypher", generate_cypher)
    graph.add_node("validate_cypher", validate_cypher)
    graph.add_node("run_query", run_query)
    graph.add_node("repair_cypher", repair_cypher)
    graph.add_node("generate_answer", generate_answer)
    graph.add_node("unsupported_answer", unsupported_answer)
    graph.add_node("failed_answer", failed_answer)

    graph.add_edge(START, "rewrite_question")
    graph.add_edge("rewrite_question", "generate_cypher")

    # conditional edge to check whether a Cypher query was generated

    graph.add_conditional_edges("generate_cypher", after_generation, {
        "validate": "validate_cypher", "unsupported": "unsupported_answer"
    })
    graph.add_conditional_edges("validate_cypher", after_validation, {
        "query": "run_query", "repair": "repair_cypher", "failed": "failed_answer"
    })
    graph.add_conditional_edges("run_query", after_query, {
        "answer": "generate_answer", "repair": "repair_cypher", "failed": "failed_answer"
    })
    graph.add_conditional_edges("repair_cypher", after_repair, {
        "validate": "validate_cypher", "unsupported": "unsupported_answer"
    })
    graph.add_edge("generate_answer", END)
    graph.add_edge("unsupported_answer", END)
    graph.add_edge("failed_answer", END)
    return graph.compile()


chat_graph = build_chat_graph()


def next_graph_event(iterator):
    """Return the next synchronous LangGraph event, or None at completion."""
    try:
        return next(iterator)
    except StopIteration:
        return None
