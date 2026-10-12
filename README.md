# GraphRAG Movie Chatbot

Pipeline: **User → LangGraph orchestration → Gemini (text→Cypher) → Neo4j → Gemini (results→answer) → Answer**, streamed to a React frontend over WebSockets, served by a Django Channels backend.

```
graphrag-chatbot/
├── backend/          Django + Channels (WebSocket) + Neo4j driver + Gemini
│   ├── .env.example   <- Template for backend environment variables
│   ├── requirements.txt <- Python dependencies
│   ├── chatapp/        WebSocket consumer, LangGraph pipeline, Gemini & Neo4j services, seed & eval commands
│   └── chatbot_project/ Django settings / ASGI / urls
└── frontend/          React app (plain WebSocket client, no extra libs needed)
    └── .env.example   <- Template for frontend WebSocket URL
```

## 1. Get Neo4j running (the "dummy database")

Easiest option — Docker:

```bash
docker run -d --name neo4j-dummy \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/password123 \
  neo4j:5
```

Or install [Neo4j Desktop](https://neo4j.com/download/) and create a local DB with your own user/password. Either way, make sure `backend/.env` has matching `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD` values.

## 2. Configure your environment variables

Copy the example environment file and add your Gemini API key:

```bash
cp backend/.env.example backend/.env
```

Open `backend/.env` and paste your key:

```env
GEMINI_API_KEY=your_real_key_here
```

(Get one at https://aistudio.google.com/apikey if you don't have one yet.)

## 3. Backend — create virtual environment, install dependencies & seed data

```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Seed the dummy movie graph into Neo4j (run once, or with --wipe to reset)
python manage.py seed_db

# Start the WebSocket/ASGI server
python manage.py runserver
```

This serves both the health check (`http://localhost:8000/health/`) and the WebSocket endpoint (`ws://localhost:8000/ws/chat/`).

> Note: `manage.py runserver` works fine for local dev with Channels installed. For production, run via Daphne explicitly: `daphne -b 0.0.0.0 -p 8000 chatbot_project.asgi:application`.

## 4. Frontend

```bash
cd frontend
cp .env.example .env            # Optional: defaults to ws://localhost:8000/ws/chat/
npm install
npm start
```

Opens at `http://localhost:3000`. It connects to `ws://localhost:8000/ws/chat/` (configurable via `frontend/.env`).

## Try asking

- "Which movies did Tom Hanks act in?"
- "Who directed The Matrix?"
- "List all movies in the Sci-Fi genre"
- "Who acted in Top Gun?"

## How the pipeline works

`backend/chatapp/orchestration.py` defines the LangGraph workflow:

```text
rewrite follow-up → generate Cypher → validate read-only Cypher → query Neo4j → generate answer
                                              │                      │
                                              └── repair once ◀──────┘
```

1. Frontend sends `{"message": "..."}` over the WebSocket.
2. On an existing WebSocket connection, Gemini first rewrites a context-dependent follow-up into a standalone question. For example, after an answer naming Robert Zemeckis, `Who was he?` becomes `Who was Robert Zemeckis?`.
3. Gemini receives the standalone question and graph schema (`chatapp/schema.py`) and generates Cypher.
4. The read-only guard rejects writes, procedures, multiple statements, and queries without `RETURN` and `LIMIT`.
5. Neo4j runs a validated query. A guard or Neo4j failure triggers one Gemini repair attempt.
6. Gemini receives the resulting records and creates the natural-language answer.
7. The WebSocket continues to stream status updates, including follow-up understanding, validation, and query repair, followed by the final `answer` message.

Conversation context is held in memory for the lifetime of an open WebSocket. Reloading the page or reconnecting starts a fresh conversation; use a persistent LangGraph checkpointer or a database when cross-session memory is needed.

## Small RAGAS evaluation POC

Five hand-authored cases grounded in `seed_db.py` live in `backend/chatapp/evaluation_cases.json`. They cover movie directors, actors, genres, and roles. The evaluation command runs every question through the real LangGraph → Neo4j → Gemini pipeline, then scores the returned Neo4j records and final answer with RAGAS:

```bash
cd backend
source venv/bin/activate
pip install -r requirements.txt
python manage.py evaluate_rag
```

Override the evaluator model in `backend/.env` when needed:

```env
RAGAS_EVALUATOR_MODEL=gemini-3.7-flash
```

The command includes a temporary compatibility bridge (`chatapp/ragas_compat.py`) for RAGAS 0.4.x and the newer LangChain release required by LangGraph. It is internal to the command; no extra setup is needed.

The command prints aggregate scores and writes timestamped CSV, Markdown (`.md`), and JSON (`.json`) reports to `backend/evaluation_results/`. It measures `context_precision`, `context_recall`, and `factual_correctness` against the predefined reference answer.

The guard is defence in depth. Use a Neo4j account with read-only permissions in any deployed environment.

## Extending the dummy data / schema

Edit `backend/chatapp/management/commands/seed_db.py` to add more nodes/relationships, and update `backend/chatapp/schema.py` to match — that schema text is what Gemini uses to know what it's allowed to query.
