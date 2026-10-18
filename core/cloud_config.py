"""The sync settings typed into the app: server address, sync key, bot token.

Nothing leaves this computer except to the address the user typed, and to
Telegram's own API for the bot test. The key and the token are stored sealed
(see secret_store); the rest is plain.
"""
import json
import re
import secrets
import urllib.request
from dataclasses import dataclass
from urllib.error import HTTPError
from urllib.parse import urlsplit

from core import settings_manager
from core.cloud_sync import CloudApi, SyncError
from core.file_service import write_text_file_atomic
from core.jalali import to_persian_digits
from core.secret_store import seal, unseal

FILE_NAME = "cloud_sync.json"
KEY_MIN_LENGTH = 32
# What BotFather hands out: a numeric id, a colon, then a long secret.
TOKEN_SHAPE = re.compile(r"^\d{5,}:[A-Za-z0-9_-]{30,}$")


@dataclass
class SyncSettings:
    enabled: bool = False
    url: str = ""
    key: str = ""
    bot_token: str = ""
    # Written by older installs; the settings screen does not show it.
    proxy: str = ""
    user_id: str = ""
    device_id: str = ""
    confirmed_root: str = ""
    excluded_paths: tuple[str, ...] = ()


def path():
    return settings_manager.app_data_dir() / FILE_NAME


def load() -> SyncSettings:
    try:
        raw = json.loads(path().read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return SyncSettings()
    if not isinstance(raw, dict):
        return SyncSettings()
    return SyncSettings(
        enabled=bool(raw.get("enabled")),
        url=str(raw.get("url", "")).strip(),
        key=_read(raw.get("key")),
        bot_token=_read(raw.get("bot_token")),
        proxy=str(raw.get("proxy", "")),
        user_id=str(raw.get("user_id", "")),
        device_id=str(raw.get("device_id", "")),
        confirmed_root=str(raw.get("confirmed_root", "")),
        excluded_paths=tuple(v for v in raw.get("excluded_paths", []) if isinstance(v, str))
            if isinstance(raw.get("excluded_paths", []), list) else (),
    )


def _read(stored) -> str:
    try:
        return unseal(str(stored or ""))
    except (OSError, ValueError):
        # Sealed by another Windows account: it cannot be read here, so the
        # field stays empty and the value is entered again.
        return ""


def save(settings: SyncSettings):
    data = {
        "enabled": settings.enabled,
        "url": settings.url.strip(),
        "key": seal(settings.key.strip()),
        "bot_token": seal(settings.bot_token.strip()),
        "user_id": settings.user_id,
        "device_id": settings.device_id,
        "confirmed_root": settings.confirmed_root,
        "excluded_paths": list(settings.excluded_paths),
    }
    if settings.proxy:
        data["proxy"] = settings.proxy
    write_text_file_atomic(path(), json.dumps(data, ensure_ascii=False, indent=2))


def address_problem(url: str) -> str | None:
    url = url.strip()
    if not url:
        return "آدرس سرور را وارد کن."
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.netloc:
        return "آدرس باید با https:// شروع شود."
    if parts.path.strip("/") or parts.query or parts.fragment:
        return "فقط آدرس اصلی سرور را بگذار؛ بدون /api یا مسیر اضافه."
    return None


def key_problem(key: str) -> str | None:
    key = key.strip()
    if not key:
        return "کلید همگام‌سازی را وارد کن. دکمه‌ی «ساخت کلید» یک کلید تازه می‌سازد."
    if len(key) < KEY_MIN_LENGTH or any(ch.isspace() for ch in key):
        return "کلید درست نیست. از دکمه‌ی «ساخت کلید» استفاده کن."
    return None


def token_problem(token: str) -> str | None:
    token = token.strip()
    if token and not TOKEN_SHAPE.match(token):
        return "توکن بات شکل درستی ندارد؛ مثل 123456:ABC… که از @BotFather می‌گیری."
    return None


def new_secret() -> str:
    return secrets.token_hex(32)


def check_server(url: str, key: str, proxy: str = "") -> tuple[bool, str]:
    problem = address_problem(url) or key_problem(key)
    if problem:
        return False, problem
    try:
        notes = CloudApi(url.strip(), key.strip(), proxy).call("/notes")["notes"]
    except SyncError as exc:
        if exc.status == 401:
            return False, "کلید همگام‌سازی اشتباه است. همان کلیدی را بگذار که روی سرور ثبت کردی."
        if exc.status == 404:
            return False, "سرور پیدا نشد. آدرس را از خروجی «npx wrangler deploy» کپی کن."
        if exc.status:
            code = to_persian_digits(str(exc.status))
            return False, f"سرور خطا داد (کد {code}). چند دقیقه بعد دوباره امتحان کن."
        return False, "به سرور نرسیدم. اینترنت، فیلترشکن یا آدرس را چک کن."
    return True, f"به سرور وصل شد. {to_persian_digits(str(len(notes)))} یادداشت روی سرور است."


def check_bot(token: str) -> tuple[bool, str]:
    token = token.strip()
    if not token:
        return True, ""
    problem = token_problem(token)
    if problem:
        return False, problem
    try:
        with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getMe", timeout=15) as response:
            data = json.load(response)
    except HTTPError as exc:
        if exc.code in (401, 404):
            return False, "توکن بات اشتباه است یا بات حذف شده."
        return False, "تلگرام جواب نداد. چند دقیقه بعد دوباره امتحان کن."
    except (OSError, ValueError):
        return False, "به تلگرام نرسیدم. فیلترشکن را چک کن."
    name = (data.get("result") or {}).get("username", "") if isinstance(data, dict) else ""
    if data.get("ok") and name:
        return True, f"بات @{name} آماده است."
    return False, "تلگرام جواب نامفهومی داد."


def check_all(settings: SyncSettings) -> tuple[bool, str]:
    ok, message = check_server(settings.url, settings.key, settings.proxy)
    bot_ok, bot_message = check_bot(settings.bot_token)
    if not bot_message:
        return ok, message
    return ok and bot_ok, message + "\n" + bot_message


# The steps shown in the settings screen. ("h", heading), ("p", paragraph),
# ("code", a block to copy into a terminal).
GUIDE = (
    ("h", "۱. ساخت سرور شخصی (یک بار)"),
    ("p", "همگام‌سازی به سروری نیاز دارد که خودت روی حساب رایگان Cloudflare می‌سازی. "
          "Node.js را از nodejs.org (نسخه‌ی LTS) نصب کن. بعد در پوشه‌ی cloudflare ترمینال را باز کن و بزن:"),
    ("code", "npm install\nnpx wrangler login"),
    ("p", "پایگاه داده بساز. خروجی یک database_id می‌دهد؛ آن را در فایل wrangler.jsonc "
          "به جای مقدار قبلی بگذار:"),
    ("code", "npx wrangler d1 create notepad-plus-data"),
    ("p", "جدول‌ها را بساز:"),
    ("code", "npx wrangler d1 execute notepad-plus-data --remote --file schema.sql"),
    ("h", "۲. کلید همگام‌سازی"),
    ("p", "دکمه‌ی «ساخت کلید» را همین‌جا بزن. کلید کپی و در فیلد پر می‌شود. همان را روی سرور بگذار:"),
    ("code", "npx wrangler secret put DESKTOP_SYNC_KEY"),
    ("p", "وقتی پرسید، کلید را paste کن و Enter بزن."),
    ("h", "۳. انتشار سرور و تست"),
    ("code", "npx wrangler deploy"),
    ("p", "آدرسی که نشان می‌دهد (https://…workers.dev) را در «آدرس سرور» بگذار و «ذخیره و تست» را بزن. "
          "اگر «به سرور وصل شد» را دیدی، تمام است."),
    ("h", "۴. گوشی و تلگرام (اختیاری)"),
    ("p", "توکن بات را از @BotFather بگیر (اگر توکنی را جایی فرستاده‌ای، همان‌جا عوضش کن). "
          "شناسه‌ی عددی خودت را از @userinfobot بگیر. هر دو را روی سرور بگذار؛ "
          "برای TELEGRAM_WEBHOOK_SECRET یک بار دیگر «ساخت کلید» را بزن:"),
    ("code", "npx wrangler secret put TELEGRAM_BOT_TOKEN\n"
             "npx wrangler secret put TELEGRAM_OWNER_ID\n"
             "npx wrangler secret put TELEGRAM_WEBHOOK_SECRET\n"
             "npx wrangler deploy"),
    ("p", "توکن را همین‌جا هم بگذار و «ذخیره و تست» را بزن. آخر کار این آدرس را در مرورگر باز کن. "
          "TOKEN را توکن بات، SERVER_URL را آدرس سرور و WEBHOOK_SECRET را همان رشته‌ی تصادفی بگذار:"),
    ("code", "https://api.telegram.org/botTOKEN/setWebhook?url=SERVER_URL/telegram/webhook"
             "&secret_token=WEBHOOK_SECRET"),
    ("p", "این آدرس توکن را دارد؛ جای دیگری نفرستش."),
)
