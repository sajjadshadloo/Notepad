import { authenticate } from './auth.mjs';
import { D1Notes } from './repository.mjs';
import { rateLimit } from './pairing.mjs';

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

export async function handleApi(request, env) {
  const identity = await authenticate(request, env);
  if (!identity) return json({ error: 'unauthorized' }, 401);
  const notes = new D1Notes(env.DB, identity.userId);
  if (!(await rateLimit(env, 'api:' + identity.userId, 600))) return json({ error: 'rate_limited' }, 429);
  const url = new URL(request.url);
  const match = /^\/api\/notes\/([0-9a-f-]{36})$/.exec(url.pathname);
  if (url.pathname === '/api/sync-status' && request.method === 'GET') {
    const status = await env.DB.prepare(`SELECT checked_at, completed_at, state, downloaded, uploaded, deleted, conflicts, skipped, error
      FROM desktop_sync_status WHERE user_id = ? ORDER BY checked_at DESC LIMIT 1`).bind(identity.userId).first();
    return json({ status });
  }
  if (url.pathname === '/api/sync-status' && request.method === 'POST') {
    if (identity.kind !== 'desktop') return json({ error: 'unauthorized' }, 401);
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
      (user_id, device_id, checked_at, completed_at, state, downloaded, uploaded, deleted, conflicts, skipped, error)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(user_id, device_id) DO UPDATE SET checked_at = excluded.checked_at,
      completed_at = COALESCE(excluded.completed_at, desktop_sync_status.completed_at),
      state = excluded.state, downloaded = excluded.downloaded, uploaded = excluded.uploaded,
      deleted = excluded.deleted, conflicts = excluded.conflicts, skipped = excluded.skipped,
      error = excluded.error`)
      .bind(identity.userId, identity.deviceId, now, body.state === 'error' ? null : now, body.state,
        ...counts.map(key => body[key]), body.error).run();
    return json({ ok: true });
  }
  if (url.pathname === '/api/account' && request.method === 'GET') {
    return json({ user_id: identity.userId, device_id: identity.deviceId || null });
  }
  if (url.pathname === '/api/devices' && request.method === 'GET') {
    const devices = (await env.DB.prepare('SELECT id, name, created_at, revoked FROM devices WHERE user_id = ? ORDER BY created_at')
      .bind(identity.userId).all()).results;
    return json({ devices, current_device: identity.deviceId || null });
  }
  const device = /^\/api\/devices\/([0-9a-f-]{36}|legacy-desktop)$/.exec(url.pathname);
  if (device && request.method === 'DELETE') {
    const result = await env.DB.prepare('UPDATE devices SET revoked = 1 WHERE id = ? AND user_id = ?')
      .bind(device[1], identity.userId).run();
    return result.meta.changes ? json({ ok: true }) : json({ error: 'not_found' }, 404);
  }
  if (url.pathname === '/api/conflicts' && request.method === 'GET') {
    return json({ conflicts: await notes.openConflicts() });
  }
  const conflict = /^\/api\/conflicts\/([0-9a-f-]{36})$/.exec(url.pathname);
  if (conflict && request.method === 'POST') {
    let body;
    try { body = await bodyOf(request); } catch { return json({ error: 'bad_json' }, 400); }
    if (!['current', 'proposed', 'both'].includes(body?.keep)) return json({ error: 'invalid_choice' }, 400);
    const result = await notes.resolveConflict(conflict[1], body.keep);
    if (result.kind === 'missing') return json({ error: 'not_found' }, 404);
    if (result.kind === 'conflict') return json({ error: 'conflict' }, 409);
    return json({ ok: true, note: result.note });
  }
  if (url.pathname === '/api/notes' && request.method === 'GET') {
    return json({ notes: await notes.list() });
  }
  if (url.pathname === '/api/notes' && request.method === 'POST') {
    let body;
    try { body = await bodyOf(request); } catch { return json({ error: 'bad_json' }, 400); }
    if (!body || !validPath(body.path) || typeof body.text !== 'string') return json({ error: 'invalid_note' }, 400);
    try { return json({ note: await notes.create(body.path, body.text) }, 201); }
    catch (error) {
      if (String(error).includes('UNIQUE')) return json({ error: 'path_exists' }, 409);
      if (String(error).includes('account_quota')) return json({ error: 'account_quota' }, 413);
      throw error;
    }
  }
  if (match && ['PUT', 'DELETE'].includes(request.method)) {
    let body;
    try { body = await bodyOf(request); } catch { return json({ error: 'bad_json' }, 400); }
    if (!body || !Number.isSafeInteger(body.version) || body.version < 1 ||
        (request.method === 'PUT' && typeof body.text !== 'string')) {
      return json({ error: 'invalid_note' }, 400);
    }
    let result;
    try {
      result = await notes.change(match[1], body.version,
        request.method === 'PUT' ? body.text : null, request.method === 'DELETE');
    } catch (error) {
      if (String(error).includes('account_quota')) return json({ error: 'account_quota' }, 413);
      throw error;
    }
    if (result.kind === 'missing') return json({ error: 'not_found' }, 404);
    if (result.kind === 'conflict') return json({ error: 'conflict', note: result.note }, 409);
    return json({ note: result.note });
  }
  return json({ error: 'not_found' }, 404);
}
