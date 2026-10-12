"""Small, conservative safety check for LLM-generated Cypher.

This is deliberately an allow-list for the application's read-only movie
questions. It is defence in depth; Neo4j should also use a read-only account in
production.
"""
import re


class CypherValidationError(ValueError):
    """Raised when generated Cypher is outside the application's safe subset."""


_FORBIDDEN = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|LOAD\s+CSV|FOREACH|CALL)\b",
    re.IGNORECASE,
)


def validate_read_only_cypher(cypher: str) -> None:
    """Validate the limited read-only Cypher subset accepted by this app."""
    query = cypher.strip()
    if not query:
        raise CypherValidationError("The generated query was empty.")
    if ";" in query:
        raise CypherValidationError("Only one Cypher statement is allowed.")
    if not re.match(r"^(OPTIONAL\s+MATCH|MATCH)\b", query, re.IGNORECASE):
        raise CypherValidationError("Queries must start with MATCH or OPTIONAL MATCH.")
    if not re.search(r"\bRETURN\b", query, re.IGNORECASE):
        raise CypherValidationError("Queries must include RETURN.")
    if not re.search(r"\bLIMIT\s+\d+\b", query, re.IGNORECASE):
        raise CypherValidationError("Queries must include a numeric LIMIT.")
    if _FORBIDDEN.search(query):
        raise CypherValidationError("Write operations and procedures are not allowed.")
