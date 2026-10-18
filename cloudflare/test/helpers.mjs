import { readFileSync } from 'node:fs';
import { DatabaseSync } from 'node:sqlite';

export const schema = readFileSync(new URL('../schema.sql', import.meta.url), 'utf8');
export function database(sql = schema) {
  const sqlite = new DatabaseSync(':memory:');
  sqlite.exec('PRAGMA foreign_keys = ON; BEGIN;\n' + sql + '\nCOMMIT;');
  const statement = (sql, values = []) => ({
    bind(...args) { return statement(sql, args); },
    async first() { return sqlite.prepare(sql).get(...values) ?? null; },
    async all() { return { results: sqlite.prepare(sql).all(...values) }; },
    async run() { return { meta: { changes: sqlite.prepare(sql).run(...values).changes } }; },
  });
  const db = {
    prepare: sql => statement(sql),
    async batch(statements) {
      sqlite.exec('BEGIN');
      try {
        const result = [];
        for (const item of statements) result.push(await item.run());
        sqlite.exec('COMMIT');
        return result;
      } catch (error) { sqlite.exec('ROLLBACK'); throw error; }
    },
  };
  return { db, sqlite };
}

export async function initData(id, token = 'test-token') {
  const params = new URLSearchParams({ auth_date: String(Math.floor(Date.now() / 1000)),
    user: JSON.stringify({ id, first_name: 'Test' }) });
  const sign = async (key, input) => {
    const imported = await crypto.subtle.importKey('raw', key, { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
    return crypto.subtle.sign('HMAC', imported, new TextEncoder().encode(input));
  };
  const secret = await sign(new TextEncoder().encode('WebAppData'), token);
  const data = [...params.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([a, b]) => `${a}=${b}`).join('\n');
  params.set('hash', Buffer.from(await sign(secret, data)).toString('hex'));
  return params.toString();
}
