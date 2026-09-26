CREATE TABLE IF NOT EXISTS notes (
    id TEXT PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    text TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 1),
    deleted INTEGER NOT NULL DEFAULT 0 CHECK (deleted IN (0, 1)),
    updated_at INTEGER
);

CREATE TABLE IF NOT EXISTS telegram_messages (
    chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    note_id TEXT NOT NULL REFERENCES notes(id),
    base_version INTEGER NOT NULL,
    last_text TEXT NOT NULL,
    PRIMARY KEY (chat_id, message_id)
);

CREATE TABLE IF NOT EXISTS conflicts (
    id TEXT PRIMARY KEY,
    note_id TEXT NOT NULL REFERENCES notes(id),
    chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    expected_version INTEGER NOT NULL,
    current_version INTEGER NOT NULL,
    current_text TEXT NOT NULL,
    proposed_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    created_at INTEGER,
    UNIQUE (chat_id, message_id, expected_version, proposed_text)
);

CREATE TABLE IF NOT EXISTS desktop_sync_status (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    checked_at INTEGER NOT NULL,
    completed_at INTEGER,
    state TEXT NOT NULL CHECK (state IN ('ok', 'attention', 'error')),
    downloaded INTEGER NOT NULL DEFAULT 0,
    uploaded INTEGER NOT NULL DEFAULT 0,
    deleted INTEGER NOT NULL DEFAULT 0,
    conflicts INTEGER NOT NULL DEFAULT 0,
    skipped INTEGER NOT NULL DEFAULT 0,
    error TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS daily_digest (
    day TEXT PRIMARY KEY,
    state TEXT NOT NULL CHECK (state IN ('pending', 'sent', 'failed')),
    claimed_at INTEGER NOT NULL,
    sent_at INTEGER,
    message_id INTEGER,
    error TEXT NOT NULL DEFAULT ''
);
