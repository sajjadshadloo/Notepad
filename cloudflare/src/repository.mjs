export class D1Notes {
  constructor(db) {
    this.db = db;
  }

  async list() {
    const result = await this.db.prepare('SELECT id, path, text, version, deleted FROM notes ORDER BY path').all();
    return result.results;
  }

  async create(path, text) {
    const existing = await this.db.prepare('SELECT id, version, deleted FROM notes WHERE path = ?')
      .bind(path).first();
    if (existing) {
      if (!existing.deleted) throw new Error('UNIQUE path');
      const restored = await this.db.prepare(
        'UPDATE notes SET text = ?, deleted = 0, version = version + 1 WHERE id = ? AND version = ? AND deleted = 1'
      ).bind(text, existing.id, existing.version).run();
      if (restored.meta.changes !== 1) throw new Error('UNIQUE path');
      return this.db.prepare('SELECT id, path, text, version, deleted FROM notes WHERE id = ?')
        .bind(existing.id).first();
    }
    const id = crypto.randomUUID();
    await this.db.prepare('INSERT INTO notes (id, path, text, version) VALUES (?, ?, ?, 1)')
      .bind(id, path, text).run();
    return { id, path, text, version: 1, deleted: 0 };
  }

  async change(id, version, text, deleted = false) {
    const updated = await this.db.prepare(
      'UPDATE notes SET text = COALESCE(?, text), deleted = ?, version = version + 1 WHERE id = ? AND version = ? AND deleted = 0'
    ).bind(text, deleted ? 1 : 0, id, version).run();
    const note = await this.db.prepare('SELECT id, path, text, version, deleted FROM notes WHERE id = ?')
      .bind(id).first();
    if (!note) return { kind: 'missing' };
    return { kind: updated.meta.changes === 1 ? 'changed' : 'conflict', note };
  }

  async createFromMessage(chatId, messageId, text) {
    const existing = await this.db.prepare(
      'SELECT note_id FROM telegram_messages WHERE chat_id = ? AND message_id = ?'
    ).bind(chatId, messageId).first();
    if (existing) return { kind: 'duplicate', noteId: existing.note_id };

    const noteId = crypto.randomUUID();
    try {
      await this.db.batch([
        this.db.prepare('INSERT INTO notes (id, path, text, version) VALUES (?, ?, ?, 1)')
          .bind(noteId, `Telegram/${noteId}.md`, text),
        this.db.prepare(
          'INSERT INTO telegram_messages (chat_id, message_id, note_id, base_version, last_text) VALUES (?, ?, ?, 1, ?)'
        ).bind(chatId, messageId, noteId, text),
      ]);
    } catch (error) {
      // Telegram may retry a webhook while the first copy is still finishing.
      const raced = await this.db.prepare(
        'SELECT note_id FROM telegram_messages WHERE chat_id = ? AND message_id = ?'
      ).bind(chatId, messageId).first();
      if (raced) return { kind: 'duplicate', noteId: raced.note_id };
      throw error;
    }
    return { kind: 'created', noteId, version: 1 };
  }

  async editFromMessage(chatId, messageId, text) {
    const link = await this.db.prepare(
      'SELECT note_id, base_version, last_text FROM telegram_messages WHERE chat_id = ? AND message_id = ?'
    ).bind(chatId, messageId).first();
    if (!link) return { kind: 'unknown' };
    if (link.last_text === text) return { kind: 'duplicate', noteId: link.note_id };

    const updated = await this.db.prepare(
      'UPDATE notes SET text = ?, version = version + 1 WHERE id = ? AND version = ? AND deleted = 0'
    ).bind(text, link.note_id, link.base_version).run();
    if (updated.meta.changes === 1) {
      const version = link.base_version + 1;
      await this.db.prepare(
        'UPDATE telegram_messages SET base_version = ?, last_text = ? WHERE chat_id = ? AND message_id = ?'
      ).bind(version, text, chatId, messageId).run();
      return { kind: 'edited', noteId: link.note_id, version };
    }

    const current = await this.db.prepare(
      'SELECT version, text FROM notes WHERE id = ?'
    ).bind(link.note_id).first();
    await this.db.prepare(
      'INSERT OR IGNORE INTO conflicts (id, note_id, chat_id, message_id, expected_version, current_version, current_text, proposed_text) VALUES (?, ?, ?, ?, ?, ?, ?, ?)'
    ).bind(crypto.randomUUID(), link.note_id, chatId, messageId,
      link.base_version, current.version, current.text, text).run();
    await this.db.prepare(
      'UPDATE telegram_messages SET last_text = ? WHERE chat_id = ? AND message_id = ?'
    ).bind(text, chatId, messageId).run();
    return { kind: 'conflict', noteId: link.note_id };
  }
}
