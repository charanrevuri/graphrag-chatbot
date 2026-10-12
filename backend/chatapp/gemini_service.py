"""
Two Gemini calls, matching the pipeline:

  user question --[Gemini #1]--> Cypher
  Cypher results --[Gemini #2]--> natural language answer
"""
import json
import re

import google.generativeai as genai
from django.conf import settings

from .schema import GRAPH_SCHEMA

_configured = False


def _ensure_configured():
    global _configured
    if not _configured:
        if not settings.GEMINI_API_KEY:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Add it to backend/.env before "
                "starting the server."
            )
        genai.configure(api_key=settings.GEMINI_API_KEY)
        _configured = True


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:cypher|sql|json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


CYPHER_PROMPT_TEMPLATE = """You are an expert at translating natural language questions into Cypher queries for a Neo4j graph database.

Graph schema:
{schema}

Rules:
- Return ONLY the Cypher query. No explanation, no markdown code fences, no commentary.
- Only use the labels, relationship types and properties given in the schema above.
- Always add a LIMIT clause (25 unless the question implies a different number) to avoid huge result sets.
- If the question cannot be answered with this schema, return exactly: NO_QUERY

Question: {question}

Cypher query:"""


ANSWER_PROMPT_TEMPLATE = """You are a helpful assistant answering questions using data retrieved from a graph database.

Original question: {question}

Cypher query that was run:
{cypher}

Query results (JSON):
{results}

Write a concise, natural-language answer to the original question using only the data above.
If the results are empty, say clearly that no matching data was found.
Do not mention Cypher, JSON, or the database itself in your answer — just answer the question naturally."""


QUERY_REWRITE_PROMPT_TEMPLATE = """Rewrite the latest user question as a complete, standalone question for a movie graph chatbot.

Conversation so far (oldest first):
{history}

Latest user question:
{question}

Rules:
- Return ONLY the rewritten question. Do not answer it and do not add commentary.
- Resolve references such as he, she, they, it, that movie, and the actor only when the conversation makes the reference unambiguous.
- Preserve the user's intent. Do not introduce facts or entities that are not in the conversation.
- If the latest question is already standalone, return it unchanged.
- If a reference is ambiguous, return the latest question unchanged.
"""


def generate_cypher(question: str) -> str:
    _ensure_configured()
    model = genai.GenerativeModel(settings.GEMINI_MODEL)
    prompt = CYPHER_PROMPT_TEMPLATE.format(schema=GRAPH_SCHEMA, question=question)
    response = model.generate_content(prompt)
    cypher = _strip_code_fences(response.text)
    return cypher


def rewrite_question(question: str, history: list[dict[str, str]]) -> str:
    """Use prior turns to make a follow-up question understandable in isolation."""
    if not history:
        return question

    _ensure_configured()
    model = genai.GenerativeModel(settings.GEMINI_MODEL)
    prompt = QUERY_REWRITE_PROMPT_TEMPLATE.format(
        history=json.dumps(history[-6:], ensure_ascii=False, default=str, indent=2)[:6000],
        question=question,
    )
    response = model.generate_content(prompt)
    rewritten = _strip_code_fences(response.text)
    return rewritten or question


def generate_answer(question: str, cypher: str, results: list) -> str:
    _ensure_configured()
    model = genai.GenerativeModel(settings.GEMINI_MODEL)
    prompt = ANSWER_PROMPT_TEMPLATE.format(
        question=question,
        cypher=cypher,
        results=json.dumps(results, default=str, indent=2)[:6000],  # keep prompt bounded
    )
    response = model.generate_content(prompt)
    return response.text.strip()


def repair_cypher(question: str, failed_cypher: str, error: str) -> str:
    """Return a corrected, read-only Cypher query after a failed attempt."""
    _ensure_configured()
    model = genai.GenerativeModel(settings.GEMINI_MODEL)
    prompt = f"""You repair Cypher queries for a Neo4j movie graph.

Graph schema:
{GRAPH_SCHEMA}

Original question: {question}

Failed Cypher:
{failed_cypher}

Failure reason:
{error}

Return ONLY one corrected, read-only Cypher query. It must use only the schema
above, start with MATCH or OPTIONAL MATCH, include RETURN and LIMIT, and must
not contain writes, procedures, or more than one statement. If the question
cannot be answered from this graph, return exactly NO_QUERY.
"""
    response = model.generate_content(prompt)
    return _strip_code_fences(response.text)
