"""
Thin wrapper around the Neo4j Python driver.

Uses a module-level singleton driver so we don't reopen a connection
pool on every request.
"""
import logging

from neo4j import GraphDatabase
from django.conf import settings

logger = logging.getLogger(__name__)

_driver = None


def get_driver():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )
    return _driver


def run_cypher(cypher: str, params: dict | None = None, limit_rows: int = 50):
    """
    Executes a read Cypher query and returns a list of plain dicts.
    Raises whatever exception the driver raises (e.g. on bad syntax) —
    the caller is expected to handle/report it.
    """
    driver = get_driver()
    params = params or {}
    with driver.session() as session:
        result = session.run(cypher, params)
        records = [record.data() for record in result]
    return records[:limit_rows]


def close_driver():
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None
