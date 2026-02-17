CREATE TABLE IF NOT EXISTS conversations (
    id            TEXT PRIMARY KEY,
    slack_thread  TEXT,
    channel_id    TEXT,
    user_id       TEXT,
    skill_name    TEXT,
    state         TEXT,  -- JSON blob: phase, answers collected, etc.
    llm_provider  TEXT,  -- 'local' or 'cloud'
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT REFERENCES conversations(id),
    role            TEXT,  -- 'user', 'assistant', 'system'
    content         TEXT,
    timestamp       DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_conversations_thread ON conversations(slack_thread);
CREATE INDEX IF NOT EXISTS idx_conversations_channel ON conversations(channel_id);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);
