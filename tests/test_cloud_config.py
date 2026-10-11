"""The sync settings: what is stored, how it is checked, what the user is told."""
import base64
import json
import sys
import urllib.error
import urllib.request

import pytest

from core import cloud_config
from core.cloud_config import SyncSettings
from core.cloud_sync import SyncError
from core.secret_store import seal, unseal

KEY = "k" * 64
TOKEN = "123456789:" + "A" * 35
WINDOWS = pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows only")


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTEPAD_DATA_DIR", str(tmp_path / "appdata"))
    return tmp_path / "appdata"


def fake_api(monkeypatch, error=None, notes=()):
    class Api:
        def __init__(self, url, key, proxy=""):
            pass

        def call(self, path, method="GET", body=None):
            if error is not None:
                raise error
            return {"notes": list(notes)}

    monkeypatch.setattr(cloud_config, "CloudApi", Api)


class Reply:
    def __init__(self, body: bytes):
        self._body = body

    def read(self, *_):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


# Storage

@WINDOWS
def test_the_key_and_the_token_are_not_readable_in_the_file(data_dir):
    cloud_config.save(SyncSettings(enabled=True, url="https://a.workers.dev", key=KEY, bot_token=TOKEN))
    raw = cloud_config.path().read_bytes()
    assert KEY.encode() not in raw and TOKEN.encode() not in raw


def test_saved_settings_come_back_as_they_were(data_dir):
    saved = SyncSettings(enabled=True, url="https://a.workers.dev", key=KEY, bot_token=TOKEN)
    cloud_config.save(saved)
    assert cloud_config.load() == saved


def test_an_older_plain_file_loads_and_is_sealed_on_the_next_save(data_dir):
    cloud_config.path().parent.mkdir(parents=True, exist_ok=True)
    cloud_config.path().write_text(json.dumps({
        "enabled": True, "url": "https://a.workers.dev", "key": KEY, "proxy": "http://127.0.0.1:1",
    }), encoding="utf-8")
    loaded = cloud_config.load()
    assert loaded.key == KEY and loaded.proxy == "http://127.0.0.1:1"
    cloud_config.save(loaded)
    text = cloud_config.path().read_text(encoding="utf-8")
    if sys.platform == "win32":
        assert KEY not in text
    assert cloud_config.load().key == KEY


def test_a_file_saved_with_a_byte_order_mark_is_read(data_dir):
    cloud_config.path().parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps({"enabled": True, "url": "https://a.workers.dev", "key": ""}).encode()
    cloud_config.path().write_bytes(b"\xef\xbb\xbf" + body)
    assert cloud_config.load().enabled is True


def test_a_missing_or_broken_file_means_sync_is_off(data_dir):
    assert cloud_config.load() == SyncSettings()
    cloud_config.path().parent.mkdir(parents=True, exist_ok=True)
    cloud_config.path().write_text("{ broken", encoding="utf-8")
    assert cloud_config.load() == SyncSettings()


@WINDOWS
def test_a_value_sealed_for_another_account_is_left_empty(data_dir):
    cloud_config.path().parent.mkdir(parents=True, exist_ok=True)
    foreign = "dpapi:" + base64.b64encode(b"\x00\x01\x02not-a-dpapi-blob").decode("ascii")
    cloud_config.path().write_text(json.dumps({"enabled": True, "url": "https://a.workers.dev",
                                               "key": foreign}), encoding="utf-8")
    assert cloud_config.load().key == ""


# The seal itself

def test_empty_and_bare_values_pass_through_the_seal():
    assert seal("") == "" and unseal("") == ""
    assert unseal("plain-old-value") == "plain-old-value"


@WINDOWS
def test_windows_seals_a_value_and_opens_it_again():
    sealed = seal("hello-سلام")
    assert sealed.startswith("dpapi:") and "hello" not in sealed
    assert unseal(sealed) == "hello-سلام"


# Checks the user can read

@pytest.mark.parametrize("url, problem", [
    ("", "آدرس سرور را وارد کن."),
    ("http://a.workers.dev", "آدرس باید با https:// شروع شود."),
    ("https://a.workers.dev/api", "فقط آدرس اصلی سرور را بگذار؛ بدون /api یا مسیر اضافه."),
    ("https://a.workers.dev?x=1", "فقط آدرس اصلی سرور را بگذار؛ بدون /api یا مسیر اضافه."),
])
def test_only_the_main_https_address_is_accepted(url, problem):
    assert cloud_config.address_problem(url) == problem


def test_a_plain_server_address_passes():
    assert cloud_config.address_problem("https://notepad.workers.dev/") is None


def test_the_key_must_look_generated():
    assert cloud_config.key_problem("") is not None
    assert cloud_config.key_problem("short") is not None
    assert cloud_config.key_problem("a" * 40 + " b") is not None
    assert cloud_config.key_problem(cloud_config.new_secret()) is None


def test_generated_keys_are_long_and_never_repeat():
    first, second = cloud_config.new_secret(), cloud_config.new_secret()
    assert len(first) == 64 and first != second


def test_the_bot_token_must_look_like_botfathers_and_is_optional():
    assert cloud_config.token_problem("") is None
    assert cloud_config.token_problem("not a token") is not None
    assert cloud_config.token_problem(TOKEN) is None


def test_a_bad_address_is_refused_before_anything_is_sent(monkeypatch):
    class Refuse:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("no request should be made")

    monkeypatch.setattr(cloud_config, "CloudApi", Refuse)
    ok, message = cloud_config.check_server("http://a.workers.dev", KEY)
    assert not ok and "https://" in message


def test_a_wrong_key_is_named_as_the_key(monkeypatch):
    error = SyncError("Cloud request failed (401)")
    error.status = 401
    fake_api(monkeypatch, error=error)
    ok, message = cloud_config.check_server("https://a.workers.dev", KEY)
    assert not ok and "کلید" in message


def test_a_wrong_address_is_named_as_the_address(monkeypatch):
    error = SyncError("Cloud request failed (404)")
    error.status = 404
    fake_api(monkeypatch, error=error)
    ok, message = cloud_config.check_server("https://a.workers.dev", KEY)
    assert not ok and "سرور پیدا نشد" in message


def test_no_answer_is_named_as_the_network(monkeypatch):
    fake_api(monkeypatch, error=SyncError("Cloud is unavailable (ConnectionRefusedError)"))
    ok, message = cloud_config.check_server("https://a.workers.dev", KEY)
    assert not ok and "به سرور نرسیدم" in message


def test_success_says_how_many_notes_there_are(monkeypatch):
    fake_api(monkeypatch, notes=[{}, {}, {}])
    ok, message = cloud_config.check_server("https://a.workers.dev", KEY)
    assert ok and "۳ یادداشت" in message


def test_the_bot_answers_with_its_name(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda url, timeout=0: Reply(b'{"ok": true, "result": {"username": "my_bot"}}'))
    ok, message = cloud_config.check_bot(TOKEN)
    assert ok and "@my_bot" in message


def test_a_rejected_token_is_named_as_the_token(monkeypatch):
    def refuse(url, timeout=0):
        raise urllib.error.HTTPError(url, 401, "Unauthorized", None, None)

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    ok, message = cloud_config.check_bot(TOKEN)
    assert not ok and "توکن" in message


def test_the_token_is_never_repeated_in_a_message(monkeypatch):
    def unreachable(url, timeout=0):
        raise urllib.error.URLError("no route")

    monkeypatch.setattr(urllib.request, "urlopen", unreachable)
    ok, message = cloud_config.check_bot(TOKEN)
    assert not ok and TOKEN not in message and "فیلترشکن" in message


def test_the_combined_check_fails_when_only_the_bot_does(monkeypatch):
    monkeypatch.setattr(cloud_config, "check_server", lambda *_a: (True, "سرور خوب است"))
    monkeypatch.setattr(cloud_config, "check_bot", lambda _t: (False, "توکن اشتباه است"))
    settings = SyncSettings(url="https://a.workers.dev", key=KEY, bot_token=TOKEN)
    ok, message = cloud_config.check_all(settings)
    assert not ok and "سرور خوب است" in message and "توکن اشتباه است" in message


def test_without_a_bot_token_only_the_server_is_checked(monkeypatch):
    monkeypatch.setattr(cloud_config, "check_server", lambda *_a: (True, "سرور خوب است"))
    assert cloud_config.check_all(SyncSettings(url="https://a.workers.dev", key=KEY)) == (True, "سرور خوب است")


def test_the_guide_has_a_heading_and_code_for_each_server_step():
    kinds = [kind for kind, _ in cloud_config.GUIDE]
    assert kinds.count("code") >= 5 and kinds[0] == "h"
    commands = " ".join(text for kind, text in cloud_config.GUIDE if kind == "code")
    assert "wrangler deploy" in commands and "DESKTOP_SYNC_KEY" in commands
