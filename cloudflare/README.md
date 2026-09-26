# Notepad Plus online bridge

The deployed Worker at `https://notepad-plus-bot.sajadshadlloo23.workers.dev`
stores private notes in D1. A Telegram message creates a note, editing that
message edits the same note, and `/app` serves the owner-only Mini App for
notes, Markdown checkbox tasks and a Persian calendar. The desktop API uses
version checks and soft deletion. The bot token, webhook secret, owner ID and
desktop sync key are Cloudflare Secrets, never repository values.

The Worker sends one daily Telegram digest at 09:00 Asia/Tehran even when the
computer is off. Its Cron Trigger checks every 15 minutes, but only the 09:00
hour can send. The digest includes unchecked tasks due today or overdue from
the shared Markdown notes; completed and undated tasks are omitted. No
qualifying tasks means no message. The `daily_digest` D1 table claims each day
before sending to prevent repeat messages. An explicit Telegram rejection can
retry at the next quarter-hour; an uncertain network result keeps the claim
to avoid duplicates. The code is in `src/daily-digest.mjs`, the schedule in
`wrangler.jsonc`, and the migration in `migrations/0002_daily_digest.sql`.

The desktop mirror is in `core/cloud_sync.py`. `ui/main_window.py` schedules it
when the source app runs. On this machine the installed editor is newer than
the checkout, so the existing `NotepadPlusCloudSync` Windows task runs
`tools/run_cloud_sync.py` every minute. Configuration and state are in the
user's Notepad Plus AppData folder. The initial 16 local files were backed up
before upload to `AppData/Roaming/Sajjad/Notepad Plus/backups/notes-before-cloud-sync-20260924-112535.zip`.

Development checks: `npm test` here, `python -m pytest -q tests/test_cloud_sync.py`
from the repository root. Deploy with `npx wrangler deploy`. To pair a new
Windows installation, run `python -m tools.setup_cloud_sync` from the root,
verify the Worker, then enable the generated `cloud_sync.json`. Pairing a
second computer needs a separate credential design; running setup there would
rotate the single desktop key used by this installation.

The Mini App UI lives in `src/miniapp.mjs` (the frame), `public/app.js` and
`public/app.css`. Wrangler serves the local Vazirmatn font files from
`public/fonts`. Before deployment, `npx wrangler dev --port 8787` allows a
mobile-width browser preview. The interface includes note previews, task
search and filters, daily calendar agenda, light/dark themes, and an unsaved
changes prompt in both editors.

`/api/sync-status` reads the latest desktop mirror report for the owner; only
the desktop key can POST a report. `schema.sql` includes the additive
`desktop_sync_status` table. The Windows scheduled helper writes a local status
file and sends a heartbeat after each pass. The Mini App shows the last check,
last completed pass, conflicts and skipped files; an old heartbeat is shown as
disconnected. An open document in the installed 4.2.3 editor displays a Reload
prompt after an external edit, or a missing-file prompt after deletion.

Telegram Mini App identity follows the official `initData` HMAC validation
scheme. A local mobile-browser smoke run covers the three views and CRUD, but
the owner's actual Telegram WebView still needs an on-device check.
