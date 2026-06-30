-- PR Chatbot Database Schema (SQLite)
-- Tables are created IF NOT EXISTS (safe to re-run).

-- Users: one row per person
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    github_username TEXT UNIQUE NOT NULL,
    github_token TEXT,
    profile TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Sessions: one row per conversation
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    mode TEXT DEFAULT 'idle',
    status TEXT DEFAULT 'active',
    resources TEXT DEFAULT '[]',
    summary TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Messages: conversation history (bulk-inserted at events, not every turn)
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Indexes for fast retrieval
CREATE INDEX IF NOT EXISTS idx_sessions_user_recent ON sessions(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_session_recent ON messages(session_id, created_at DESC);
