-- When a note last changed, for the Mini App's "edited …" line and its
-- newest-first order; and when a conflict was recorded. Rows written before
-- this migration keep NULL and simply show no time.
ALTER TABLE notes ADD COLUMN updated_at INTEGER;
ALTER TABLE conflicts ADD COLUMN created_at INTEGER;
