# Human-readable description of the dummy graph, given to Gemini as
# context so it can write correct Cypher. Keep this in sync with
# chatapp/management/commands/seed_db.py.

GRAPH_SCHEMA = """
Node labels and their properties:
  (:Person {name: string, born: int})
  (:Movie  {title: string, released: int, tagline: string})
  (:Genre  {name: string})

Relationship types:
  (:Person)-[:ACTED_IN {roles: [string]}]->(:Movie)
  (:Person)-[:DIRECTED]->(:Movie)
  (:Person)-[:WROTE]->(:Movie)
  (:Person)-[:PRODUCED]->(:Movie)
  (:Movie)-[:IN_GENRE]->(:Genre)

Notes:
- This is a movie-domain graph (actors, directors, writers, producers, movies, genres).
- Property names and relationship types are case-sensitive and must be used exactly as shown.
"""
