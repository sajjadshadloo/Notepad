"""Connect this device without a bot token or a shared desktop credential."""
import hashlib
import platform
import secrets
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from core.cloud_config import SyncSettings
from core.cloud_sync import CloudApi, SyncError

SERVICE_URL = "https://notepad-plus-bot.sajadshadlloo23.workers.dev"


@dataclass
class PairingAttempt:
    id: str
    key: str
    poll_key: str
    telegram_url: str
    confirm_code: str
    expires_at: int


def begin(proxy: str = "") -> PairingAttempt:
    key, poll_key = secrets.token_hex(32), secrets.token_hex(32)
    response = CloudApi(SERVICE_URL, poll_key, proxy).call("/pairings", "POST", {
        "name": (platform.node() or "رایانهٔ من")[:80], "poll_key": poll_key,
        "key_hash": hashlib.sha256(key.encode()).hexdigest(),
    })
    link = urlsplit(response["telegram_url"])
    if link.scheme != "https" or link.netloc != "t.me" or not link.path.strip("/"):
        raise SyncError("لینک اتصال معتبر نیست؛ دوباره امتحان کن.", code="invalid_pairing_link")
    return PairingAttempt(response["id"], key, poll_key, response["telegram_url"],
                          response["confirm_code"], response["expires_at"])


def poll(attempt: PairingAttempt, proxy: str = "") -> dict:
    return CloudApi(SERVICE_URL, attempt.poll_key, proxy).call(
        "/pairings/" + attempt.id, "POST", {"poll_key": attempt.poll_key})


def connected_settings(attempt: PairingAttempt, approved: dict, previous: SyncSettings,
                       root: str, excluded: tuple[str, ...]) -> SyncSettings:
    if approved.get("status") != "approved" or not approved.get("user_id") or not approved.get("device_id"):
        raise SyncError("اتصال هنوز تأیید نشده است.", code="not_approved")
    # Never mix a previously synced local folder with another cloud account.
    old_user = previous.user_id or ("legacy-owner" if previous.key else "")
    if old_user and (old_user != approved["user_id"] or previous.url.rstrip("/") != SERVICE_URL):
        raise SyncError("این پوشه به حساب دیگری وصل بوده است. برای تغییر حساب، ابتدا پوشه و وضعیت همگام‌سازی جدا لازم است.", code="account_mismatch")
    return SyncSettings(enabled=True, url=SERVICE_URL, key=attempt.key, proxy=previous.proxy,
                        user_id=approved["user_id"], device_id=approved["device_id"],
                        confirmed_root=str(Path(root).resolve()), excluded_paths=excluded)
