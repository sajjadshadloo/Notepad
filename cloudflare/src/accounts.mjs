export async function accountForTelegram(env, telegramId, register = false) {
  if (!/^[1-9][0-9]{0,15}$/.test(String(telegramId))) return null;
  const owner = String(telegramId) === String(env.TELEGRAM_OWNER_ID);
  if (owner) {
    await env.DB.prepare("UPDATE accounts SET telegram_id = ? WHERE id = 'legacy-owner' AND telegram_id IS NULL")
      .bind(String(telegramId)).run();
  }
  let account = await env.DB.prepare('SELECT id, telegram_id, disabled FROM accounts WHERE telegram_id = ?')
    .bind(String(telegramId)).first();
  if (!account && register && env.PUBLIC_REGISTRATION === 'true') {
    const cap = Math.max(1, Math.min(10000, Number(env.MAX_USERS) || 20));
    await env.DB.prepare(`INSERT OR IGNORE INTO accounts (id, telegram_id, created_at)
      SELECT ?, ?, ? WHERE (SELECT COUNT(*) FROM accounts) < ?`)
      .bind(crypto.randomUUID(), String(telegramId), Date.now(), cap).run();
    account = await env.DB.prepare('SELECT id, telegram_id, disabled FROM accounts WHERE telegram_id = ?')
      .bind(String(telegramId)).first();
  }
  return account && !account.disabled ? account : null;
}
