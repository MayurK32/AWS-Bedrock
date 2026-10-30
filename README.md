# AWS Bedrock - Learning Projects

Hands-on examples exploring **Amazon Bedrock**, the **Strands Agents** framework, and the **Model Context Protocol (MCP)** for building AI-powered support workflows.

## Projects

### Order Support Agent

**`order_support_agent.py`** — A multi-turn customer support agent built with [Strands Agents](https://github.com/strands-agents/sdk-python) and AWS Bedrock (Z.AI GLM 4.7).

- FastAPI backend with a streaming `/stream` endpoint
- Checks order status from an in-memory product dictionary
- Connects to a remote MCP ticket server for ticket operations (raise, escalate, close)
- In-memory session-based conversation history for multi-turn support
- Custom hook support (e.g., `TicketClosureHook` via `support_hooks.py`)
- Filters out unrelated MCP tools (weather, currency, inventory, shipping)

### Ticket MCP Server

**`ticket_mcp_server.py`** — A standalone [FastMCP](https://github.com/jlowin/fastmcp) server exposing 12+ ticket management tools over stdio or HTTP.

- Persistent SQLite storage (`data/tickets.db`)
- Full ticket lifecycle: create, assign, escalate, comment, close, reopen, delete
- Tool profiles: `all`, `support`, `read-only`
- Includes 4 extra demo tools (weather, currency, inventory, shipping quotes)

```bash
# Run over HTTP
python ticket_mcp_server.py --transport http --port 8756

# Run over stdio (default)
python ticket_mcp_server.py
```

### Bedrock GLM 4.7 CLI

**`bedrock_glm47.py`** — Send prompts to Z.AI GLM 4.7 through Amazon Bedrock's Converse API.

```bash
python bedrock_glm47.py "Explain tool calling with a short example."
python bedrock_glm47.py --region us-east-1 --profile my-profile
```

Reads credentials from environment variables or a `.env` file. Supports `--region`, `--profile`, and `--max-tokens` flags.

### Chatbot Frontend

**`chatbot.py`** — A Streamlit chat UI that connects to the FastAPI backend.

- Streams agent responses in real time
- Maintains per-session conversation history via a UUID session ID
- Error handling for backend connectivity issues

```bash
streamlit run chatbot.py
```

### Simple Agent

**`simple_agent.py`** — Minimal Strands agent example (4 lines).

### Seed Tickets

**`seed_tickets.py`** — Populates the MCP ticket server with 5 fictional support tickets for testing.

```bash
python seed_tickets.py --url http://127.0.0.1:8756/mcp
```

## Setup

```bash
# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
.venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt
```

### AWS Credentials

Configure credentials via any standard method:

- AWS CLI profile (`aws configure`)
- Environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`)
- A `.env` file beside the scripts (gitignored)

Your IAM user/role needs `bedrock:InvokeModel` permission.

## Requirements

- Python 3.10+
- `boto3`, `awscli` — AWS SDK and CLI
- `strands-agents`, `strands-agents-tools` — Agent framework
- `fastmcp` — MCP server toolkit
- `fastapi`, `uvicorn` — Web framework and ASGI server
- `streamlit` — Chat frontend

## Architecture

```
chatbot.py (Streamlit)  ──→  order_support_agent.py (FastAPI)  ──→  ticket_mcp_server.py
        │                            │                                      │
        └── session_id + prompt      ├── checkOrderStatus (local tool)      ├── SQLite (data/tickets.db)
                                     ├── AWS Bedrock (GLM 4.7)              └── 12+ ticket tools
                                     └── sessions dict (conversation history)
```

## Running

```bash
# Terminal 1: MCP ticket server
python ticket_mcp_server.py --transport http --port 8756

# Terminal 2: FastAPI backend
uvicorn order_support_agent:app --port 8000

# Terminal 3: Streamlit frontend
streamlit run chatbot.py
```

## License

This repository is for personal learning and experimentation.
