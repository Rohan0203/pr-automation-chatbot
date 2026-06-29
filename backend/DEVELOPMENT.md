# PR Chatbot — Development Documentation

> **Last updated:** April 7, 2026
> **Status:** MVP complete — core flow working end-to-end
> **Repo:** `abinashlingank/pr-automation-chatbot` (branch: `main`)

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture](#2-architecture)
3. [Tech Stack](#3-tech-stack)
4. [Project Structure](#4-project-structure)
5. [Backend — Detailed Breakdown](#5-backend--detailed-breakdown)
6. [Frontend — Detailed Breakdown](#6-frontend--detailed-breakdown)
7. [Resource Guide System (MD Files)](#7-resource-guide-system-md-files)
8. [LLM Integration](#8-llm-integration)
9. [State Machine & Agent Flow](#9-state-machine--agent-flow)
10. [GitHub OAuth & PR Creation](#10-github-oauth--pr-creation)
11. [API Reference](#11-api-reference)
12. [Database Schema](#12-database-schema)
13. [Prompt Engineering](#13-prompt-engineering)
14. [Configuration](#14-configuration)
15. [How to Run](#15-how-to-run)
16. [Known Issues & Limitations](#16-known-issues--limitations)
17. [Bugs Fixed During Development](#17-bugs-fixed-during-development)
18. [What's NOT Built Yet (Next Steps)](#18-whats-not-built-yet-next-steps)

---

## 1. Project Overview

**PR Chatbot** is a conversational AI agent that helps users generate **AWS infrastructure YAML configurations** through a chat interface. Once the user fills in all required fields via conversation, the agent generates a valid YAML file and automatically creates a **GitHub Pull Request** in a target repository.

### What It Does

1. User opens the chat UI → describes what resource they want (e.g., "I want to create an S3 bucket")
2. Agent detects the resource type (S3, Glue DB, or IAM)
3. Agent asks for required fields **one at a time**, validating each against strict rules defined in Markdown guide files
4. Once all fields are collected → agent generates a YAML configuration preview
5. User confirms, edits, or cancels
6. On confirmation → agent creates a GitHub PR with the YAML file in the target repo (`Rohan0203/infra-configs`)

### Supported Resource Types

| Resource | Description | Guide File |
|----------|-------------|------------|
| **S3** | S3 bucket configuration | `data/resources/s3.md` (185 lines) |
| **Glue DB** | AWS Glue database configuration | `data/resources/glue_db.md` (266 lines) |
| **IAM** | IAM role configuration | `data/resources/iam.md` (312 lines) |

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      React + Vite Frontend                   │
│  (ChatPanel, Sidebar, Header, MessageBubble, Toast)          │
│  Served as SPA from FastAPI at /                             │
└──────────────────────────┬──────────────────────────────────┘
                           │  HTTP (fetch)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI Backend                          │
│  /api/*  → Chat, Sessions, Schemas, Health, PR creation      │
│  /auth/* → GitHub OAuth login, callback, status              │
└──────────────┬──────────────────────┬───────────────────────┘
               │                      │
               ▼                      ▼
┌──────────────────────┐  ┌──────────────────────────────────┐
│  Generator Agent      │  │  SQLite Database                  │
│  (State Machine)      │  │  (chat_sessions, chat_messages,   │
│                       │  │   resource_states)                 │
│  Prompts + Resource   │  └──────────────────────────────────┘
│  MD files as context  │
└──────────┬────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────┐
│  Azure OpenAI via EPAM DIAL Proxy                             │
│  Model: gpt-4o-mini / gpt-4.1-mini                           │
│  Endpoint: https://ai-proxy.lab.epam.com                      │
└──────────────────────────────────────────────────────────────┘
           │
           ▼ (on confirm)
┌──────────────────────────────────────────────────────────────┐
│  GitHub API (PyGithub)                                        │
│  Repo: Rohan0203/infra-configs                                │
│  Creates branch → commits YAML → opens PR                     │
└──────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

- **MD files are the single source of truth** — all field definitions, validation rules, normalization rules, YAML templates, error messages, and conversation flow are defined in Markdown files under `data/resources/`. The Python code has **zero hardcoded validation logic**.
- **LLM does all extraction, validation, and YAML generation** — Python is just a thin state machine that routes messages and manages persistence.
- **History provider is abstracted** — currently sends full conversation history to LLM. Can be swapped to a summarization provider when token limits become an issue.
- **Frontend is a static SPA** — built with Vite, served from `frontend/dist/` by FastAPI. No separate frontend server in production.

---

## 3. Tech Stack

### Backend
| Technology | Version | Purpose |
|-----------|---------|---------|
| Python | 3.11 | Runtime |
| FastAPI | 0.115.6 | Web framework |
| Uvicorn | 0.34.0 | ASGI server |
| SQLAlchemy | 2.0.36 | ORM (async) |
| aiosqlite | 0.20.0 | Async SQLite driver |
| OpenAI SDK | 1.58.1 | LLM client (works with Azure/Groq/OpenAI) |
| PyGithub | 2.1.1 | GitHub API for PR creation |
| httpx | 0.28.1 | Async HTTP client (OAuth) |
| Pydantic | 2.10.3 | Data validation / settings |
| pydantic-settings | 2.7.0 | .env file loading |
| python-dotenv | 1.0.1 | Environment variables |
| PyYAML | 6.0.2 | YAML utilities |

### Frontend
| Technology | Version | Purpose |
|-----------|---------|---------|
| React | 19.2.4 | UI framework |
| Vite | (latest) | Build tool / dev server |
| CSS (vanilla) | — | Styling (no Tailwind/MUI) |

### Infrastructure
| Component | Details |
|-----------|---------|
| LLM Provider | Azure OpenAI via EPAM DIAL Proxy |
| LLM Model | `gpt-4.1-mini-2025-04-14` (deployment) |
| API Endpoint | `https://ai-proxy.lab.epam.com` |
| Database | SQLite (file: `pr_chatbot.db`) |
| GitHub Repo | `Rohan0203/infra-configs` |

---

## 4. Project Structure

```
pr chatbot/
├── main.py                          # FastAPI app entry point, SPA serving
├── requirements.txt                 # Python dependencies
├── .env                             # Environment variables (not committed)
├── .gitignore                       # Git ignore rules
├── DEVELOPMENT.md                   # This file
│
├── app/
│   ├── __init__.py
│   ├── config.py                    # Settings loaded from .env (Pydantic)
│   │
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── generator_agent.py       # State machine + LLM orchestration (~670 lines)
│   │   └── prompts.py               # All LLM prompt templates (~270 lines)
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py                # All REST API endpoints (~462 lines)
│   │
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── github_oauth.py          # OAuth flow: URL generation, token exchange (~82 lines)
│   │   └── routes.py                # /auth/* endpoints (~108 lines)
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── api_models.py            # Pydantic request/response models (~55 lines)
│   │   ├── database.py              # SQLAlchemy engine, session factory (~75 lines)
│   │   └── schemas.py               # SQLAlchemy ORM models (~100 lines)
│   │
│   └── services/
│       ├── __init__.py
│       ├── github_service.py        # GitHub PR creation via PyGithub (~88 lines)
│       ├── llm_client.py            # Switchable LLM client (Groq/OpenAI/Azure) (~143 lines)
│       └── schema_registry.py       # Loads resource MD files at startup (~103 lines)
│
├── data/
│   └── resources/
│       ├── s3.md                    # S3 resource guide (185 lines)
│       ├── glue_db.md               # Glue DB resource guide (266 lines)
│       └── iam.md                   # IAM resource guide (312 lines)
│
├── frontend/                        # React + Vite SPA
│   ├── package.json
│   ├── vite.config.js               # Proxy config + build output
│   ├── index.html
│   ├── dist/                        # Built output (served by FastAPI)
│   └── src/
│       ├── main.jsx                 # React entry point
│       ├── App.jsx                  # Main app component (state management)
│       ├── App.css
│       ├── index.css                # Global CSS variables + reset
│       ├── api.js                   # All API calls (fetch-based)
│       └── components/
│           ├── Header.jsx / .css    # Top bar with branding + GitHub connect
│           ├── Sidebar.jsx / .css   # Session list + new chat button
│           ├── ChatPanel.jsx / .css # Chat messages area + input bar
│           ├── MessageBubble.jsx / .css  # Message rendering (code blocks, markdown)
│           └── Toast.jsx / .css     # Notification toasts
│
└── venv/                            # Python virtual environment (not committed)
```

---

## 5. Backend — Detailed Breakdown

### `main.py` — Application Entry Point
- Creates the FastAPI app with CORS middleware (allows all origins for dev)
- On startup: initializes database tables, loads schema registry (resource MD files)
- Mounts API routes at `/api` and auth routes at `/auth`
- Serves the React SPA from `frontend/dist/` with a catch-all route (`/{full_path:path}`)
- Static assets (JS/CSS) served from `/assets`

### `app/config.py` — Configuration
- Uses `pydantic-settings` to load from `.env` file
- Supports 3 LLM providers: Groq, OpenAI, Azure OpenAI
- Configurable: database URL, server host/port, GitHub OAuth credentials, log level

### `app/agents/generator_agent.py` — Core Agent (~670 lines)
This is the heart of the application. It implements:

**State Machine:**
```
IDLE → DETECTING → COLLECTING → AWAITING_CONFIRMATION → DONE
                                       ↓ (edit)
                                   COLLECTING (re-enters)
                                       ↓ (cancel)
                                     IDLE
```

**Key Components:**
- `AgentState` — tracks current resource: type, collected fields, current field, phase, retries, generated YAML
- `SessionState` — tracks a full session: current agent, completed resources, conversation history, GitHub token
- `FullHistoryProvider` — sends last 30 messages as context to LLM (swappable via protocol)
- `GeneratorAgent` — the main class with handlers for each state:
  - `_handle_idle()` — routes between general chat, session end, or resource detection
  - `_handle_detection()` — uses DETECTION_PROMPT to identify resource type + extract initial fields
  - `_handle_collecting()` — uses RESOURCE_ACTION_PROMPT with MD file context to extract/validate fields one by one
  - `_generate_yaml()` — uses YAML_GENERATION_PROMPT to produce final YAML
  - `_handle_confirmation()` — handles confirm/edit/cancel with fast-path for simple words + LLM for complex edits
  - `_finalize_resource()` — marks complete, triggers GitHub PR creation if token available
  - `_handle_general()` — greetings, off-topic, capability questions

**PR Creation Flow:**
- On finalization, checks for GitHub token (in-memory first, then DB fallback)
- Runs PyGithub synchronously in a thread pool executor (since PyGithub is sync)
- Creates branch → commits YAML file → opens PR → returns URL

### `app/api/routes.py` — REST API (~462 lines)
All endpoints under `/api`:
- `POST /chat` — main endpoint; creates/reuses session, processes message through agent, persists messages + resource state
- `GET /sessions` — lists sessions filtered by `X-GitHub-User` header
- `GET /sessions/{id}` — session details with resource info
- `GET /sessions/{id}/history` — chat message history
- `DELETE /sessions/{id}` — deletes session + messages + resource states
- `POST /sessions/{id}/create-pr` — explicit PR creation for a confirmed resource
- `GET /schemas` — lists supported resource types
- `GET /health` — health check

**Cross-session token sync:** When a user chats, the endpoint checks if any other session by the same `created_by` user has a GitHub token, and copies it to the current session. This ensures new sessions automatically get the token after OAuth.

### `app/auth/` — GitHub OAuth
- `github_oauth.py` — generates auth URL with `session_id` encoded in the `state` parameter (format: `<csrf_token>:<session_id>`), exchanges code for token, fetches username
- `routes.py` — `/auth/github` redirects to GitHub, `/auth/github/callback` handles the return (saves token to session + backfills all user sessions), `/auth/me` checks auth status

### `app/services/llm_client.py` — LLM Client (~143 lines)
- Supports 3 providers: Groq (Llama 3.3 70B), OpenAI (GPT-4o-mini), Azure OpenAI (via EPAM DIAL proxy)
- Two methods: `chat()` for free-text responses, `extract_json()` for structured JSON extraction (uses `response_format: json_object`)
- Includes fallback JSON extraction from markdown code blocks if direct parsing fails
- Currently configured for **Azure** provider pointing to EPAM DIAL proxy

### `app/services/schema_registry.py` — Resource Guide Loader (~103 lines)
- Loads MD files from `data/resources/` at startup
- Provides resource context (full MD content) to prompts
- Has keyword-based trigger detection for routing messages to resource types
- Singleton pattern — loaded once, accessed everywhere

### `app/services/github_service.py` — GitHub PR Service (~88 lines)
- Uses PyGithub (synchronous) to interact with GitHub API
- Creates a new branch: `config/<intake_id>-<resource_type>-<timestamp>`
- Commits YAML to: `configs/<resource_type>/<intake_id>-<resource_name>.yaml`
- Opens PR with title: `[CONFIG] <TYPE> - <intake_id> - <resource_name>`
- PR body includes the YAML in a code block + metadata

---

## 6. Frontend — Detailed Breakdown

### Design
- **ChatGPT-like clean interface** — no cards, no quick-start buttons
- Left sidebar with session list + "New Chat" button
- Main chat panel with welcome screen, message bubbles, typing indicator
- Top header with branding + GitHub connect button

### Components

**`App.jsx`** — Main app orchestrator
- Manages state: `sessions`, `messages`, `activeSession`, `sending`, `githubUser`, `toast`
- Handles OAuth callback (reads `github_user` and `session_id` from URL params)
- Auto-loads sessions on mount, loads history when switching sessions
- Sends messages via `api.js`, appends user + assistant messages to state

**`Header.jsx`** — Top navigation bar
- Shows "PR Chatbot" branding
- GitHub connect button (links to `/auth/github?session_id=...`)
- Shows connected username when authenticated

**`Sidebar.jsx`** — Session management
- "New Chat" button to start fresh session
- Lists all sessions with message count badges
- Delete button per session
- Active session highlighted

**`ChatPanel.jsx`** — Chat area
- Welcome screen when no messages ("What would you like to build?")
- Auto-scrolls to bottom on new messages
- Typing indicator (animated dots) while waiting for response
- Input bar with Enter-to-send, disabled while sending

**`MessageBubble.jsx`** — Message rendering
- Differentiates user (right-aligned, blue) vs assistant (left-aligned, gray) bubbles
- Parses and renders:
  - Code blocks (```yaml, ```json, etc.) with copy-to-clipboard button
  - Inline code (backticks)
  - Bold text (**text**)
  - URLs as clickable links
- Timestamp display

**`Toast.jsx`** — Notification system
- Shows success/error/info toasts
- Auto-dismisses after timeout

### API Layer (`api.js`)
- All API calls centralized
- Automatically attaches `X-GitHub-User` header from localStorage
- Functions: `sendChat()`, `getSessions()`, `getSessionHistory()`, `deleteSession()`, `getGithubAuthUrl()`

### Build & Serving
- Development: `npm run dev` (Vite dev server with proxy to localhost:8000)
- Production: `npm run build` → outputs to `frontend/dist/` → served by FastAPI
- FastAPI mounts `/assets` from `dist/assets/` and serves `index.html` for all other routes (SPA)

---

## 7. Resource Guide System (MD Files)

The **most important design decision**: resource MD files are the **single source of truth** for everything about a resource type. The LLM receives the full MD content as context and uses it to:

- Know which fields to collect and in what order
- Validate field values (regex, enums, length constraints)
- Normalize input (e.g., lowercase, strip whitespace)
- Generate error messages
- Handle dependencies (e.g., `encryption_key_arn` required only if `encryption_type ≠ SSE-S3`)
- Build YAML output using templates and quoting rules

### MD File Structure (example: Glue DB)
```
---
resource: glue_db
schema_version: "1.0"
agent_role: Senior Data Platform Architect
---

<persona_definition> ... </persona_definition>
<boundary_protocols> ... </boundary_protocols>

## Field Schema Table
| Field | Type | Required | Constraints | ...

## Normalization Rules
| Input Pattern | Normalized |

## Validation Errors Table
| Field | Error Message |

## YAML Template
```yaml
...template...
```

## Conversation Flow
1. Ask intake_id
2. Ask database_name
...
```

### Adding a New Resource Type
To add a new resource (e.g., Lambda, DynamoDB):
1. Create `data/resources/<type>.md` following the same structure
2. Add the type to `RESOURCE_FILES` dict in `schema_registry.py`
3. Add trigger keywords to `RESOURCE_TRIGGERS`
4. No other code changes needed — the LLM will use the MD file automatically

---

## 8. LLM Integration

### Provider Configuration
```
LLM_PROVIDER=azure
AZURE_OPENAI_ENDPOINT=https://ai-proxy.lab.epam.com
AZURE_OPENAI_DEPLOYMENT=gpt-4o-mini-2024-07-18
AZURE_OPENAI_API_VERSION=2024-02-01
AZURE_OPENAI_API_KEY=<key>
```

### How the LLM Is Used
Every user message triggers 1-2 LLM calls:
1. **Detection** (if idle) — identify resource type + extract initial fields
2. **Collection** — extract field values, validate, determine next field
3. **YAML Generation** — produce final YAML from collected fields
4. **Confirmation** — interpret user's confirm/edit/cancel response

All LLM calls use `response_format: json_object` for structured output.

### Token Management
- `temperature: 0.0` for extraction/validation (deterministic)
- `temperature: 0.1` for general conversation (slight variation)
- `max_tokens: 2048` for all calls
- History truncated to last 30 messages to stay within context window

---

## 9. State Machine & Agent Flow

```
User: "I want to create a Glue database"
                    │
                    ▼
              [IDLE → DETECTING]
              LLM detects: glue_db, confidence: 0.95
                    │
                    ▼
              [COLLECTING]
              LLM reads glue_db.md, asks for intake_id
                    │
            User: "I-123456"
                    │
                    ▼
              LLM validates ✅, stores intake_id, asks for database_name
                    │
            User: "prd-lh1-agtr-src"
                    │
                    ▼
              LLM validates ✅, stores, asks next field...
              ... (repeats for all mandatory fields) ...
                    │
                    ▼
              All fields collected → LLM says "confirm"
                    │
                    ▼
              [AWAITING_CONFIRMATION]
              Generates YAML preview, shows to user
                    │
            User: "confirm"
                    │
                    ▼
              [DONE]
              Creates GitHub PR → returns PR URL
              User can create another resource or end session
```

### Error Handling
- Invalid field → LLM explains error from guide's validation_errors table, increments retry counter
- 3 failed retries on mandatory field → session aborted
- 3 failed retries on optional field → skipped
- LLM call failure → generic error message, user can retry

---

## 10. GitHub OAuth & PR Creation

### OAuth Flow
```
1. User clicks "Connect GitHub" in header
2. Frontend navigates to /auth/github?session_id=<current>
3. Backend generates GitHub OAuth URL with state=<csrf>:<session_id>
4. User authorizes on GitHub
5. GitHub redirects to /auth/github/callback?code=xxx&state=xxx
6. Backend exchanges code for token, fetches username
7. Saves token to session + backfills all sessions by same user
8. Redirects to frontend with ?github_user=<username>&session_id=<id>
9. Frontend stores username in localStorage
```

### PR Creation
```
Triggered on: resource confirmation (automatic) or POST /sessions/{id}/create-pr (manual)

1. Build branch: config/<intake_id>-<resource_type>-<timestamp>
2. Get SHA of target branch (main)
3. Create git ref (new branch)
4. Create file: configs/<type>/<intake_id>-<name>.yaml
5. Open PR with title, body (includes YAML), base=main
6. Return PR URL to user
```

### Target Repository
- Owner: `Rohan0203`
- Repo: `infra-configs`
- Target branch: `main`
- File pattern: `configs/<resource_type>/<intake_id>-<resource_name>.yaml`

---

## 11. API Reference

### Chat
```
POST /api/chat
Headers: X-GitHub-User: <username>
Body: { "session_id": "<optional>", "message": "<text>" }
Response: {
  "session_id": "...",
  "message": "...",
  "resource_type": "s3|glue_db|iam|null",
  "resource_status": "collecting|awaiting_confirmation|confirmed|null",
  "generated_yaml": "...|null",
  "needs_confirmation": true|false
}
```

### Sessions
```
GET  /api/sessions                    → SessionInfo[]
GET  /api/sessions/{id}               → SessionInfo
GET  /api/sessions/{id}/history       → MessageInfo[]
DELETE /api/sessions/{id}             → { detail: "deleted" }
POST /api/sessions/{id}/create-pr     → { success, pr_url, ... }
```

### Auth
```
GET /auth/github?session_id=xxx       → Redirect to GitHub
GET /auth/github/callback             → Redirect to frontend
GET /auth/me?session_id=xxx           → { authenticated, username }
```

### Utility
```
GET /api/schemas                      → { supported_types, primary_types }
GET /api/health                       → { status: "healthy", version: "0.1.0" }
```

---

## 12. Database Schema

### `chat_sessions`
| Column | Type | Notes |
|--------|------|-------|
| id | VARCHAR (PK) | UUID |
| created_at | DATETIME | |
| updated_at | DATETIME | |
| status | ENUM | active, completed, cancelled |
| github_token | TEXT | OAuth access token |
| github_username | TEXT | GitHub login |
| created_by | TEXT | X-GitHub-User header value |

### `chat_messages`
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER (PK) | Auto-increment |
| session_id | VARCHAR (FK) | → chat_sessions.id |
| role | ENUM | user, assistant, system |
| content | TEXT | Message text |
| created_at | DATETIME | |
| metadata_json | JSON | resource_type, status, needs_confirmation |

### `resource_states`
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER (PK) | Auto-increment |
| session_id | VARCHAR (FK) | → chat_sessions.id |
| resource_type | VARCHAR | s3, glue_db, iam |
| status | ENUM | collecting, awaiting_confirmation, confirmed, cancelled |
| collected_fields | JSON | All collected field values |
| generated_yaml | TEXT | Final YAML output |
| validation_errors | JSON | Current validation errors |
| current_field | VARCHAR | Field currently being asked |
| created_at | DATETIME | |
| updated_at | DATETIME | |
| pr_url | VARCHAR | GitHub PR URL after creation |

---

## 13. Prompt Engineering

The system uses 6 prompt templates in `app/agents/prompts.py`:

### SYSTEM_PROMPT
The agent's identity and 15 core rules:
1. Follow resource guide exactly
2. Never fabricate values
3. Collect one field at a time
4. Extract multiple fields from single message
5. Normalize input
6. **Anti-hallucination**: only validate against guide rules, never add subjective rules
7. Show confirmation before YAML
8. Follow templates exactly
9. Answer mid-conversation questions
10. Keep responses concise
11. Never re-ask collected fields
12. **Anti-hallucination (reinforced)**: prohibited from applying any rule not in the guide
13. **Enum enforcement**: strict enum validation, reject even "plausible-looking" values
14. **Field listing**: respond to "what fields do you need?" with full list
15. **Correction confirmations**: accept "yes" as confirmation of suggested correction, not as field value

### RESOURCE_ACTION_PROMPT
The main collection prompt. Receives:
- Resource type, full MD context, collected fields, phase, field retries, user message
- Contains sections for: correction confirmations, natural language empty responses, enum validation reminder
- Returns structured JSON: extracted_fields, invalid_fields, next_action, next_field, message

### YAML_GENERATION_PROMPT
Generates final YAML using collected fields + resource guide templates.

### CONFIRMATION_PROMPT
Handles confirm/edit/cancel with rules for:
- Confirm: must generate complete YAML immediately
- Edit: validate new values, regenerate YAML from scratch, return to confirmation screen
- Cancel: discard
- Question: answer from guide

### DETECTION_PROMPT
Identifies resource type from user message with confidence score + initial field extraction.

### GENERAL_CONVERSATION_PROMPT
Handles greetings, capability questions, off-topic, thanks.

---

## 14. Configuration

### Required Environment Variables (`.env`)
```bash
# LLM Provider (groq | openai | azure)
LLM_PROVIDER=azure

# Azure OpenAI / EPAM DIAL
AZURE_OPENAI_API_KEY=<your-key>
AZURE_OPENAI_ENDPOINT=https://ai-proxy.lab.epam.com
AZURE_OPENAI_DEPLOYMENT=gpt-4o-mini-2024-07-18
AZURE_OPENAI_API_VERSION=2024-02-01

# GitHub OAuth
GITHUB_CLIENT_ID=<your-client-id>
GITHUB_CLIENT_SECRET=<your-client-secret>
GITHUB_REPO_OWNER=Rohan0203
GITHUB_REPO_NAME=infra-configs
GITHUB_TARGET_BRANCH=main

# Frontend URL (for OAuth redirects)
FRONTEND_URL=http://localhost:8000
```

### Optional
```bash
# Alternative LLM providers
GROQ_API_KEY=...
GROQ_MODEL=llama-3.3-70b-versatile
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4o-mini

# Server
HOST=0.0.0.0
PORT=8000
DEBUG=true
LOG_LEVEL=INFO

# Database
DATABASE_URL=sqlite:///./pr_chatbot.db
```

---

## 15. How to Run

### Prerequisites
- Python 3.11+
- Node.js 18+ (for frontend build)
- Git

### Backend Setup
```bash
cd "pr chatbot"
python -m venv venv
.\venv\Scripts\activate        # Windows
# source venv/bin/activate     # macOS/Linux

pip install -r requirements.txt

# Create .env file with required variables (see section 14)
```

### Frontend Build
```bash
cd frontend
npm install
npm run build                  # Outputs to frontend/dist/
cd ..
```

### Run Server
```bash
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Access at: **http://localhost:8000**

### Development Mode (Frontend)
For hot-reload during frontend development:
```bash
# Terminal 1: Backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2: Frontend (Vite dev server with proxy)
cd frontend
npm run dev
# Access at http://localhost:5173 (proxies /api and /auth to :8000)
```

---

## 16. Known Issues & Limitations

### Current Limitations
1. **No authentication beyond GitHub OAuth** — anyone with the URL can access the chatbot. Session isolation relies on `X-GitHub-User` header sent by the frontend.
2. **SQLite is the database** — fine for single-user/demo, not suitable for production with concurrent users.
3. **In-memory agent state** — `_sessions` dict in `generator_agent.py` is lost on server restart. DB persists messages/resources but not the active conversation state (collecting phase, retries, etc.).
4. **No streaming** — LLM responses are returned all-at-once, not streamed. For long responses, the user sees a typing indicator until the full response arrives.
5. **Token limits** — full conversation history (last 30 messages) is sent every turn. Long conversations may exceed token limits.
6. **Sync GitHub API** — PyGithub is synchronous, wrapped in `ThreadPoolExecutor`. Works but not ideal for high concurrency.
7. **CORS allows all origins** — appropriate for development only.
8. **OAuth state stored in memory** — `OAUTH_STATES` dict in `github_oauth.py` is lost on restart.

### Known Bugs
1. **Detection typo extraction** — if user types "i wwant a s3 cbucket", the LLM may extract "cbucket" as the `bucket_name` from the typo instead of treating it as a general request. Not yet fixed.

---

## 17. Bugs Fixed During Development

| Bug | Root Cause | Fix |
|-----|-----------|-----|
| **LLM added subjective validation** (e.g., "description too short") | LLM hallucinated validation rules not in the guide | Added Rule 6 + Rule 12 (anti-hallucination) to SYSTEM_PROMPT |
| **Enum fields not enforced** (e.g., `aws_account_id` accepted any number) | LLM accepted "plausible-looking" values without checking enum list | Added Rule 13 (ENUM ENFORCEMENT) + VALIDATION REMINDER in RESOURCE_ACTION_PROMPT |
| **"list all fields" request ignored** — agent re-asked current field | LLM didn't recognize meta-questions about field listing | Added Rule 14 (FIELD LISTING) + handling in YOUR TASK item 2 |
| **Correction confirmation loop** — "Did you mean X?" → "yes" → re-asked same field | LLM treated "yes" as a field value instead of confirming the suggested correction | Added Rule 15 (CORRECTION CONFIRMATIONS) + CORRECTION CONFIRMATION section in RESOURCE_ACTION_PROMPT |
| **Edit flow re-asked fields** — after editing one field, agent asked for already-collected fields | CONFIRMATION_PROMPT didn't explicitly tell LLM to return to confirmation after a valid edit | Added CRITICAL instruction in CONFIRMATION_PROMPT edit rules |
| **Natural language empties** — "none", "skip" treated as invalid instead of empty | LLM didn't know to map these to empty string for optional fields | Added NATURAL LANGUAGE EMPTY RESPONSES section in RESOURCE_ACTION_PROMPT |
| **OAuth session not linked** — token saved but not associated with frontend session | Session ID not passed through OAuth flow | Encoded `session_id` in OAuth state parameter, parse it on callback |
| **New sessions missing GitHub token** — user logged in but new sessions had no token | Token only saved to the original OAuth session | Added cross-session token sync in `/api/chat` endpoint + backfill in OAuth callback |
| **Confirmation showed no YAML** — user confirmed but `yaml_output` was null | CONFIRMATION_PROMPT didn't mandate YAML generation on confirm | Added explicit rule: "yaml_output must NEVER be null when action is confirm" |

---

## 18. What's NOT Built Yet (Next Steps)

### High Priority
- [ ] **Streaming responses** — use SSE or WebSocket to stream LLM output token-by-token
- [ ] **Session resume on restart** — restore in-memory agent state from DB on server restart
- [ ] **Proper authentication** — add user auth (JWT, EPAM SSO, etc.) instead of relying on GitHub OAuth alone
- [ ] **History summarization** — implement `SummaryHistoryProvider` to avoid token overflow in long conversations
- [ ] **Error recovery** — handle LLM timeout/failure gracefully with retry logic

### Medium Priority
- [ ] **More resource types** — Lambda, DynamoDB, SNS, SQS, etc. (just add MD files)
- [ ] **Bulk resource creation** — allow creating multiple resources in sequence without re-authenticating
- [ ] **YAML diff on edit** — show what changed when user edits a field
- [ ] **PR status tracking** — show PR status (open, merged, closed) in the UI
- [ ] **Export YAML** — download button for generated YAML (without PR)
- [ ] **PostgreSQL support** — swap SQLite for PostgreSQL for multi-user production

### Low Priority / Nice-to-Have
- [ ] **Dark/light theme toggle** — currently dark theme only
- [ ] **Mobile responsive** — sidebar collapses on small screens
- [ ] **Keyboard shortcuts** — Ctrl+Enter to send, etc.
- [ ] **Message search** — search within chat history
- [ ] **Rate limiting** — prevent abuse of LLM calls
- [ ] **Logging dashboard** — structured logging + monitoring
- [ ] **Unit tests** — test agent state machine, prompt templates, API endpoints
- [ ] **CI/CD pipeline** — automated build + deploy
- [ ] **Docker** — containerize for easy deployment
- [ ] **Typo correction in detection** — fix the "cbucket" extraction bug

---

## Summary

The PR Chatbot is a **working MVP** with:
- ✅ Conversational field collection for 3 AWS resource types
- ✅ LLM-driven validation using MD files as single source of truth
- ✅ YAML generation with proper formatting
- ✅ GitHub OAuth + automatic PR creation
- ✅ React SPA frontend with session management
- ✅ Multi-session, multi-resource support
- ✅ Extensive prompt engineering to prevent LLM hallucination

The architecture is **extensible** — adding a new resource type only requires creating an MD file. No Python code changes needed.
