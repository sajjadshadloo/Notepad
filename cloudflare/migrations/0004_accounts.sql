-- Apply once, with the old single-owner Worker still running and registration
-- disabled. IDs, versions, message links, deletion marks and digest claims stay.
PRAGMA defer_foreign_keys = ON;

CREATE TABLE accounts (
    id TEXT PRIMARY KEY,
    telegram_id TEXT UNIQUE,
    created_at INTEGER NOT NULL,
    disabled INTEGER NOT NULL DEFAULT 0 CHECK (disabled IN (0, 1))
);
INSERT INTO accounts (id, created_at) VALUES ('legacy-owner', 0);

CREATE TABLE devices (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES accounts(id),
    key_hash TEXT UNIQUE,
    name TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0 CHECK (revoked IN (0, 1))
);
CREATE INDEX devices_user ON devices(user_id);
INSERT INTO devices (id, user_id, name, created_at)
    VALUES ('legacy-desktop', 'legacy-owner', 'رایانهٔ قبلی', 0);

CREATE TABLE notes_new (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'legacy-owner' REFERENCES accounts(id),
    path TEXT NOT NULL,
    text TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 1),
    deleted INTEGER NOT NULL DEFAULT 0 CHECK (deleted IN (0, 1)),
    updated_at INTEGER,
    UNIQUE (user_id, path),
    UNIQUE (user_id, id)
);
INSERT INTO notes_new (id, path, text, version, deleted, updated_at)
    SELECT id, path, text, version, deleted, updated_at FROM notes;
CREATE TABLE telegram_messages_new (
    user_id TEXT NOT NULL DEFAULT 'legacy-owner',
    chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    note_id TEXT NOT NULL,
    base_version INTEGER NOT NULL,
    last_text TEXT NOT NULL,
    PRIMARY KEY (chat_id, message_id),
    FOREIGN KEY (user_id, note_id) REFERENCES notes_new(user_id, id)
);
INSERT INTO telegram_messages_new (chat_id, message_id, note_id, base_version, last_text)
    SELECT chat_id, message_id, note_id, base_version, last_text FROM telegram_messages;
CREATE TABLE conflicts_new (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'legacy-owner',
    note_id TEXT NOT NULL,
    chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    expected_version INTEGER NOT NULL,
    current_version INTEGER NOT NULL,
    current_text TEXT NOT NULL,
    proposed_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    created_at INTEGER,
    UNIQUE (user_id, chat_id, message_id, expected_version, proposed_text),
    FOREIGN KEY (user_id, note_id) REFERENCES notes_new(user_id, id)
);
INSERT INTO conflicts_new (id, note_id, chat_id, message_id, expected_version,
    current_version, current_text, proposed_text, status, created_at)
    SELECT id, note_id, chat_id, message_id, expected_version, current_version,
           current_text, proposed_text, status, created_at FROM conflicts;
DROP TABLE telegram_messages;
DROP TABLE conflicts;
DROP TABLE notes;
ALTER TABLE notes_new RENAME TO notes;
ALTER TABLE telegram_messages_new RENAME TO telegram_messages;
ALTER TABLE conflicts_new RENAME TO conflicts;
CREATE INDEX conflicts_user ON conflicts(user_id, status);

ALTER TABLE desktop_sync_status RENAME TO legacy_sync_status;
CREATE TABLE desktop_sync_status (
    user_id TEXT NOT NULL REFERENCES accounts(id),
    device_id TEXT NOT NULL REFERENCES devices(id),
    checked_at INTEGER NOT NULL,
    completed_at INTEGER,
    state TEXT NOT NULL CHECK (state IN ('ok', 'attention', 'error')),
    downloaded INTEGER NOT NULL DEFAULT 0,
    uploaded INTEGER NOT NULL DEFAULT 0,
    deleted INTEGER NOT NULL DEFAULT 0,
    conflicts INTEGER NOT NULL DEFAULT 0,
    skipped INTEGER NOT NULL DEFAULT 0,
    error TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (user_id, device_id)
);
INSERT INTO desktop_sync_status
    SELECT 'legacy-owner', 'legacy-desktop', checked_at, completed_at, state,
           downloaded, uploaded, deleted, conflicts, skipped, error FROM legacy_sync_status;
DROP TABLE legacy_sync_status;

ALTER TABLE daily_digest RENAME TO legacy_daily_digest;
CREATE TABLE daily_digest (
    user_id TEXT NOT NULL DEFAULT 'legacy-owner' REFERENCES accounts(id),
    day TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('pending', 'sent', 'failed')),
    claimed_at INTEGER NOT NULL,
    sent_at INTEGER,
    message_id INTEGER,
    error TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (user_id, day)
);
INSERT INTO daily_digest (day, state, claimed_at, sent_at, message_id, error)
    SELECT day, state, claimed_at, sent_at, message_id, error FROM legacy_daily_digest;
DROP TABLE legacy_daily_digest;

CREATE TABLE pairings (
    id TEXT PRIMARY KEY,
    link_hash TEXT NOT NULL UNIQUE,
    poll_hash TEXT NOT NULL,
    key_hash TEXT NOT NULL UNIQUE,
    device_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    confirm_code TEXT NOT NULL,
    presented_to TEXT,
    user_id TEXT REFERENCES accounts(id),
    expires_at INTEGER NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE INDEX pairings_expiry ON pairings(expires_at);

CREATE TABLE request_limits (
    bucket TEXT PRIMARY KEY,
    count INTEGER NOT NULL,
    expires_at INTEGER NOT NULL
);

-- Conservative beta quotas; the existing owner's dataset is left intact.
CREATE TRIGGER notes_insert_quota BEFORE INSERT ON notes
WHEN NEW.user_id <> 'legacy-owner' AND (
    length(CAST(NEW.text AS BLOB)) > 300000 OR
    (SELECT COUNT(*) FROM notes WHERE user_id = NEW.user_id) >= 2000 OR
    (NEW.deleted = 0 AND (SELECT COUNT(*) FROM notes WHERE user_id = NEW.user_id AND deleted = 0) >= 200) OR
    (SELECT COALESCE(SUM(length(CAST(text AS BLOB))), 0) FROM notes WHERE user_id = NEW.user_id)
        + length(CAST(NEW.text AS BLOB)) > 2097152
)
BEGIN SELECT RAISE(ABORT, 'account_quota'); END;
CREATE TRIGGER notes_update_quota BEFORE UPDATE OF text, deleted ON notes
WHEN NEW.user_id <> 'legacy-owner' AND (
    length(CAST(NEW.text AS BLOB)) > 300000 OR
    (OLD.deleted = 1 AND NEW.deleted = 0 AND (SELECT COUNT(*) FROM notes WHERE user_id = NEW.user_id AND deleted = 0) >= 200) OR
    (SELECT COALESCE(SUM(length(CAST(text AS BLOB))), 0) FROM notes WHERE user_id = NEW.user_id AND id <> OLD.id)
        + length(CAST(NEW.text AS BLOB)) > 2097152
)
BEGIN SELECT RAISE(ABORT, 'account_quota'); END;
