CREATE TABLE IF NOT EXISTS daily_digest (
    day TEXT PRIMARY KEY,
    state TEXT NOT NULL CHECK (state IN ('pending', 'sent', 'failed')),
    claimed_at INTEGER NOT NULL,
    sent_at INTEGER,
    message_id INTEGER,
    error TEXT NOT NULL DEFAULT ''
);
