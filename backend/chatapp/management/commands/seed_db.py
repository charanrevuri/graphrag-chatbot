"""
Seeds a small "dummy" movie graph into Neo4j so there's something for the
chatbot to query. Run with:

    python manage.py seed_db

Add --wipe to delete all existing nodes/relationships first.
"""
from django.core.management.base import BaseCommand

from chatapp.neo4j_service import get_driver

MOVIES = [
    {"title": "The Matrix", "released": 1999, "tagline": "Welcome to the Real World",
     "genres": ["Sci-Fi", "Action"],
     "director": "Lana Wachowski",
     "cast": [("Keanu Reeves", ["Neo"]), ("Carrie-Anne Moss", ["Trinity"]), ("Laurence Fishburne", ["Morpheus"])],
     "writer": "Lana Wachowski", "producer": "Joel Silver"},
    {"title": "The Matrix Reloaded", "released": 2003, "tagline": "Free your mind",
     "genres": ["Sci-Fi", "Action"],
     "director": "Lana Wachowski",
     "cast": [("Keanu Reeves", ["Neo"]), ("Carrie-Anne Moss", ["Trinity"]), ("Laurence Fishburne", ["Morpheus"])],
     "writer": "Lana Wachowski", "producer": "Joel Silver"},
    {"title": "Top Gun", "released": 1986, "tagline": "I feel the need, the need for speed.",
     "genres": ["Action", "Drama"],
     "director": "Tony Scott",
     "cast": [("Tom Cruise", ["Maverick"]), ("Kelly McGillis", ["Charlie"]), ("Val Kilmer", ["Iceman"])],
     "writer": "Jim Cash", "producer": "Jerry Bruckheimer"},
    {"title": "Jerry Maguire", "released": 2000, "tagline": "The rest of his life begins now.",
     "genres": ["Drama", "Romance"],
     "director": "Cameron Crowe",
     "cast": [("Tom Cruise", ["Jerry Maguire"]), ("Renee Zellweger", ["Dorothy Boyd"]), ("Cuba Gooding Jr.", ["Rod Tidwell"])],
     "writer": "Cameron Crowe", "producer": "James L. Brooks"},
    {"title": "A Few Good Men", "released": 1992, "tagline": "In the heart of the nation's capital...",
     "genres": ["Drama"],
     "director": "Rob Reiner",
     "cast": [("Tom Cruise", ["Lt. Daniel Kaffee"]), ("Jack Nicholson", ["Col. Nathan Jessup"]), ("Demi Moore", ["Lt. Cdr. JoAnne Galloway"])],
     "writer": "Aaron Sorkin", "producer": "Rob Reiner"},
    {"title": "Sleepless in Seattle", "released": 1993, "tagline": "What if someone you never met was the love of your life?",
     "genres": ["Comedy", "Romance"],
     "director": "Nora Ephron",
     "cast": [("Tom Hanks", ["Sam Baldwin"]), ("Meg Ryan", ["Annie Reed"]), ("Rita Wilson", ["Suzy"])],
     "writer": "Nora Ephron", "producer": "Gary Foster"},
    {"title": "You've Got Mail", "released": 1998, "tagline": "At odds in life... at ease online.",
     "genres": ["Comedy", "Romance"],
     "director": "Nora Ephron",
     "cast": [("Tom Hanks", ["Joe Fox"]), ("Meg Ryan", ["Kathleen Kelly"])],
     "writer": "Nora Ephron", "producer": "Nora Ephron"},
    {"title": "Cast Away", "released": 2000, "tagline": "At the edge of the world, his journey begins.",
     "genres": ["Drama", "Adventure"],
     "director": "Robert Zemeckis",
     "cast": [("Tom Hanks", ["Chuck Noland"]), ("Helen Hunt", ["Kelly Frears"])],
     "writer": "William Broyles Jr.", "producer": "Tom Hanks"},
    {"title": "Apollo 13", "released": 1995, "tagline": "Houston, we have a problem.",
     "genres": ["Drama", "Adventure"],
     "director": "Ron Howard",
     "cast": [("Tom Hanks", ["Jim Lovell"]), ("Kevin Bacon", ["Jack Swigert"]), ("Ed Harris", ["Gene Kranz"])],
     "writer": "William Broyles Jr.", "producer": "Brian Grazer"},
    {"title": "Forrest Gump", "released": 1994, "tagline": "Life is like a box of chocolates.",
     "genres": ["Drama", "Romance"],
     "director": "Robert Zemeckis",
     "cast": [("Tom Hanks", ["Forrest Gump"]), ("Robin Wright", ["Jenny Curran"]), ("Gary Sinise", ["Lt. Dan Taylor"])],
     "writer": "Eric Roth", "producer": "Wendy Finerman"},
]

PERSON_BIRTH_YEARS = {
    "Keanu Reeves": 1964, "Carrie-Anne Moss": 1967, "Laurence Fishburne": 1961,
    "Lana Wachowski": 1965, "Joel Silver": 1952,
    "Tom Cruise": 1962, "Kelly McGillis": 1957, "Val Kilmer": 1959, "Tony Scott": 1944,
    "Jim Cash": 1941, "Jerry Bruckheimer": 1945, "Renee Zellweger": 1969,
    "Cuba Gooding Jr.": 1968, "Cameron Crowe": 1957, "James L. Brooks": 1940,
    "Jack Nicholson": 1937, "Demi Moore": 1962, "Rob Reiner": 1947, "Aaron Sorkin": 1961,
    "Tom Hanks": 1956, "Meg Ryan": 1961, "Rita Wilson": 1956, "Nora Ephron": 1941,
    "Gary Foster": 1956, "Helen Hunt": 1963, "Robert Zemeckis": 1951,
    "William Broyles Jr.": 1944, "Kevin Bacon": 1958, "Ed Harris": 1950,
    "Ron Howard": 1954, "Brian Grazer": 1951, "Robin Wright": 1966, "Gary Sinise": 1955,
    "Eric Roth": 1945, "Wendy Finerman": 1961,
}


class Command(BaseCommand):
    help = "Seeds a dummy movie graph into Neo4j."

    def add_arguments(self, parser):
        parser.add_argument("--wipe", action="store_true", help="Delete all existing data first")

    def handle(self, *args, **options):
        driver = get_driver()
        with driver.session() as session:
            if options["wipe"]:
                self.stdout.write("Wiping existing graph...")
                session.run("MATCH (n) DETACH DELETE n")

            self.stdout.write("Creating constraints...")
            session.run("CREATE CONSTRAINT movie_title IF NOT EXISTS FOR (m:Movie) REQUIRE m.title IS UNIQUE")
            session.run("CREATE CONSTRAINT person_name IF NOT EXISTS FOR (p:Person) REQUIRE p.name IS UNIQUE")
            session.run("CREATE CONSTRAINT genre_name IF NOT EXISTS FOR (g:Genre) REQUIRE g.name IS UNIQUE")

            self.stdout.write(f"Seeding {len(MOVIES)} movies...")
            for movie in MOVIES:
                session.run(
                    """
                    MERGE (m:Movie {title: $title})
                    SET m.released = $released, m.tagline = $tagline
                    """,
                    title=movie["title"], released=movie["released"], tagline=movie["tagline"],
                )

                for genre in movie["genres"]:
                    session.run(
                        """
                        MERGE (g:Genre {name: $genre})
                        WITH g
                        MATCH (m:Movie {title: $title})
                        MERGE (m)-[:IN_GENRE]->(g)
                        """,
                        genre=genre, title=movie["title"],
                    )

                def merge_person_rel(name, rel_type, roles=None):
                    born = PERSON_BIRTH_YEARS.get(name)
                    if roles is not None:
                        session.run(
                            f"""
                            MERGE (p:Person {{name: $name}})
                            SET p.born = $born
                            WITH p
                            MATCH (m:Movie {{title: $title}})
                            MERGE (p)-[r:{rel_type}]->(m)
                            SET r.roles = $roles
                            """,
                            name=name, born=born, title=movie["title"], roles=roles,
                        )
                    else:
                        session.run(
                            f"""
                            MERGE (p:Person {{name: $name}})
                            SET p.born = $born
                            WITH p
                            MATCH (m:Movie {{title: $title}})
                            MERGE (p)-[:{rel_type}]->(m)
                            """,
                            name=name, born=born, title=movie["title"],
                        )

                merge_person_rel(movie["director"], "DIRECTED")
                merge_person_rel(movie["writer"], "WROTE")
                merge_person_rel(movie["producer"], "PRODUCED")
                for actor_name, roles in movie["cast"]:
                    merge_person_rel(actor_name, "ACTED_IN", roles=roles)

        self.stdout.write(self.style.SUCCESS("Dummy movie graph seeded successfully."))
