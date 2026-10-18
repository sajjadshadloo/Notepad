# Notepad Plus shared Telegram bridge

Worker: `https://notepad-plus-bot.sajadshadlloo23.workers.dev`.
The 4.4.0 beta supports separate accounts on one Worker/D1.
See [rollout and verification](../docs/MULTI-USER-IMPLEMENTATION.md).

## Identity and data

The API derives an account from verified Telegram initData or a hashed,
revocable device credential. Caller-supplied account IDs are never authority.
Notes, conflicts, message links, heartbeat and digest claims are account-scoped.
Paths are unique per account. Legacy credentials map only to legacy-owner and
legacy-desktop; they remain valid unless that device is revoked.

TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET, TELEGRAM_OWNER_ID and
DESKTOP_SYNC_KEY remain Cloudflare Secrets. Never ship them in an installer.
PUBLIC_REGISTRATION, MAX_USERS and MAINTENANCE are non-secret variables.
The deployed beta caps accounts at 20. Raising capacity needs review.
Optional TELEGRAM_BOT_USERNAME avoids the first getMe identity lookup.

Webhook registration must accept `message`, `edited_message`, and
`callback_query`. The legacy message-only filter blocks pairing confirmation
even when /start and health checks work. After deployment the administrator
should inspect `GET /telegram/webhook-settings` using the existing owner key.
Its guarded POST repairs the filter without dropping queued updates; it refuses
to overwrite a webhook pointing to another URL. Public device keys cannot use
these administrator endpoints. See the 2026-10-18 incident.

## Pairing

The desktop generates independent 256-bit device/poll keys. POST /api/pairings
receives a device-key hash and poll proof, returning an expiring Telegram link
and comparison code. Opening the link presents a confirmation button bound to
that Telegram user. Confirmation atomically creates one device and claims the
request. POST /api/pairings/:id requires the poll key and returns approval
metadata, never device credentials. The desktop already holds its device key
and stores it using Windows DPAPI. A request expires after ten minutes.

GET /api/account identifies the authenticated account/device. GET /api/devices
lists metadata without hashes; DELETE /api/devices/:id revokes only the caller's
device. The /devices bot command also supports revocation. File sync requires
explicit confirmation of the local folder and supports relative exclusions.
Exclusions do not remove copies already uploaded to the server.

## Database deployment

Fresh database: execute schema.sql once. It includes the original schema and
migration 0004; do not also execute 0004 on that database.
Existing production database: migration 0004_accounts.sql has already been
applied. It retains note IDs/versions, deletion marks, message links and digest
history. Do not re-run it.

For future migrations: enable maintenance, deploy, confirm API/webhook 503,
export and verify a private D1 backup, apply the tested migration, compare data
and integrity, then disable maintenance and deploy. Maintenance also stops the
scheduled digest. Never roll back a single-owner Worker over multi-user data:
it does not enforce account boundaries. Prefer a forward fix.

The digest checks every 15 minutes but sends only in Tehran's 09:00 hour.
Claims are per account/day. Unknown delivery outcomes stay claimed to prevent
duplicates. At most six messages are attempted each invocation, with unattempted
accounts before explicit failures. The 20-account beta fits four invocations;
increasing capacity requires revisiting this batching.

## Development

Run `npm test` and `npx wrangler deploy --dry-run` here.
From the root, run `python -m pytest -q` and optionally
`python tools/check_miniapp_scroll.py`.

The browser check needs Python Playwright, installed Edge, and WebKit from
`python -m playwright install webkit`. These are development dependencies only.
The check uses the production shell/CSP with fabricated notes and mocked APIs.
Pass `--url <public /app URL>` to verify deployed assets with fabricated data.

The existing tools/run_cloud_sync.py scheduled helper now honors account
identity, confirmed folder and exclusions. Public users use in-app pairing.
Do not run tools/setup_cloud_sync.py for public users: that legacy administrator
helper rotates the shared owner key.
