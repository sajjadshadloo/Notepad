import { authorized, desktopAuthorized } from './auth.mjs';

const json = (body, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' },
});

function validPath(path) {
  return typeof path === 'string' && path.length <= 240 && !path.includes('\\') &&
    !path.startsWith('/') && !path.includes(':') && !path.includes('\0') &&
    path.split('/').every(part => part && part !== '.' && part !== '..' && !part.startsWith('.')) &&
    /\.(md|txt|markdown)$/i.test(path);
}

async function bodyOf(request) {
  const text = await request.text();
  if (text.length > 250000) throw new Error('too_large');
  return JSON.parse(text);
}

export async function handleApi(request, env, notes) {
  if (!env.DB || !(await authorized(request, env))) return json({ error: 'unauthorized' }, 401);
  const url = new URL(request.url);
  const match = /^\/api\/notes\/([0-9a-f-]{36})$/.exec(url.pathname);
  if (url.pathname === '/api/sync-status' && request.method === 'GET') {
    const status = await env.DB.prepare('SELECT checked_at, completed_at, state, downloaded, uploaded, deleted, conflicts, skipped, error FROM desktop_sync_status WHERE id = 1').first();
    return json({ status });
  }
  if (url.pathname === '/api/sync-status' && request.method === 'POST') {
    if (!desktopAuthorized(request, env)) return json({ error: 'unauthorized' }, 401);
    let body;
    try { body = await bodyOf(request); } catch { return json({ error: 'bad_json' }, 400); }
    const counts = ['downloaded', 'uploaded', 'deleted', 'conflicts', 'skipped'];
    if (!body || typeof body !== 'object' || Array.isArray(body) ||
        !['ok', 'attention', 'error'].includes(body.state) ||
        counts.some(key => !Number.isSafeInteger(body[key]) || body[key] < 0 || body[key] > 100000) ||
        typeof body.error !== 'string' || body.error.length > 160) {
      return json({ error: 'invalid_status' }, 400);
    }
    const now = Date.now();
    await env.DB.prepare(`INSERT INTO desktop_sync_status
      (id, checked_at, completed_at, state, downloaded, uploaded, deleted, conflicts, skipped, error)
      VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(id) DO UPDATE SET checked_at = excluded.checked_at,
      completed_at = COALESCE(excluded.completed_at, desktop_sync_status.completed_at),
      state = excluded.state, downloaded = excluded.downloaded, uploaded = excluded.uploaded,
      deleted = excluded.deleted, conflicts = excluded.conflicts, skipped = excluded.skipped,
      error = excluded.error`)
      .bind(now, body.state === 'error' ? null : now, body.state,
        ...counts.map(key => body[key]), body.error).run();
    return json({ ok: true });
  }
  if (url.pathname === '/api/notes' && request.method === 'GET') {
    return json({ notes: await notes.list() });
  }
  if (url.pathname === '/api/notes' && request.method === 'POST') {
    let body;
    try { body = await bodyOf(request); } catch { return json({ error: 'bad_json' }, 400); }
    if (!validPath(body.path) || typeof body.text !== 'string') return json({ error: 'invalid_note' }, 400);
    try { return json({ note: await notes.create(body.path, body.text) }, 201); }
    catch (error) {
      if (String(error).includes('UNIQUE')) return json({ error: 'path_exists' }, 409);
      throw error;
    }
  }
  if (match && ['PUT', 'DELETE'].includes(request.method)) {
    let body;
    try { body = await bodyOf(request); } catch { return json({ error: 'bad_json' }, 400); }
    if (!Number.isSafeInteger(body.version) || body.version < 1 ||
        (request.method === 'PUT' && typeof body.text !== 'string')) {
      return json({ error: 'invalid_note' }, 400);
    }
    const result = await notes.change(match[1], body.version,
      request.method === 'PUT' ? body.text : null, request.method === 'DELETE');
    if (result.kind === 'missing') return json({ error: 'not_found' }, 404);
    if (result.kind === 'conflict') return json({ error: 'conflict', note: result.note }, 409);
    return json({ note: result.note });
  }
  return json({ error: 'not_found' }, 404);
}
