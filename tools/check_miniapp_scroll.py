"""Browser regression check for long notes; no real notes or credentials.

Development only: pip install playwright; python -m playwright install webkit
Run: python tools/check_miniapp_scroll.py
Uses installed Edge and Playwright WebKit, with the production shell and CSP.
"""
import argparse
import json
import subprocess
import threading
from datetime import datetime, timedelta, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
LONG_TEXT = "\n".join(f"سطر {i} ـ متن آزمایشی اسکرول گوشی" for i in range(1, 201))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", help="Public Mini App /app URL; all note APIs remain mocked")
    args = parser.parse_args()
    shell = json.loads(subprocess.check_output([
        "node", "--input-type=module", "-e",
        "import worker from './cloudflare/src/worker.mjs';"
        "const r=await worker.fetch(new Request('https://example.test/app'),{});"
        "console.log(JSON.stringify({html:await r.text(),"
        "csp:r.headers.get('Content-Security-Policy')}));",
    ], cwd=ROOT, encoding="utf-8"))

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            if urlsplit(self.path).path != "/app":
                return super().do_GET()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Security-Policy", shell["csp"])
            self.end_headers()
            self.wfile.write(shell["html"].encode("utf-8"))

    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(
        Handler, directory=str(ROOT / "cloudflare/public")))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as playwright:
            for engine in ("chromium", "webkit"):
                browser_type = getattr(playwright, engine)
                options = {"channel": "msedge"} if engine == "chromium" else {}
                with browser_type.launch(headless=True, **options) as browser:
                    for width, height in ((390, 700), (320, 568), (700, 390)):
                        check(browser, engine, width, height,
                              args.url or f"http://127.0.0.1:{server.server_port}/app")
    finally:
        server.shutdown()
        server.server_close()


def check(browser, engine, width, height, url):
    today = datetime.now(timezone(timedelta(hours=3, minutes=30))).strftime("%Y/%m/%d")
    notes = [{"id": "long", "path": "Inbox/scroll-check.md", "text": LONG_TEXT,
              "version": 1, "deleted": 0},
             {"id": "tasks", "path": "tasks.md", "version": 1, "deleted": 0,
              "text": "\n".join(f"- [ ] کار آزمایشی {i} @{today}" for i in range(60))}]
    notes += [{"id": str(i), "path": f"Inbox/note-{i}.md", "text": "آزمایشی",
               "version": 1, "deleted": 0} for i in range(45)]
    saved = []
    with browser.new_context(viewport={"width": width, "height": height},
                             is_mobile=True, has_touch=True) as context:
        context.add_init_script("""window.__tgEvents = {};
          window.Telegram = {WebApp: {
            viewportHeight: innerHeight, initData: 'test-only', colorScheme: 'light',
            isVersionAtLeast: () => true, ready() {}, expand() {},
            disableVerticalSwipes() {}, setHeaderColor() {}, setBackgroundColor() {},
            setBottomBarColor() {}, enableClosingConfirmation() {}, disableClosingConfirmation() {},
            BackButton: {show() {}, hide() {}, onClick() {}},
            onEvent(name, callback) { window.__tgEvents[name] = callback; }
          }};""")
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("https://telegram.org/**", lambda route: route.fulfill(body=""))

        def api(route):
            path = urlsplit(route.request.url).path
            if route.request.method == "PUT":
                body = route.request.post_data_json
                saved.append(body["text"])
                notes[0].update(text=body["text"], version=notes[0]["version"] + 1)
                data = {"note": notes[0]}
            elif path == "/api/notes":
                data = {"notes": notes}
            elif path == "/api/conflicts":
                data = {"conflicts": []}
            else:
                data = {"status": None}
            route.fulfill(json=data)

        page.route("**/api/**", api)
        page.goto(url)
        page.locator(".page").wait_for()
        for tab in ("today", "notes", "tasks", "cal"):
            page.locator(f"[data-tab={tab}]").click()
            page.wait_for_function("() => document.querySelector('#scroll').scrollHeight > document.querySelector('#scroll').clientHeight")
            page.evaluate("document.querySelector('#scroll').scrollTop = 100000")
            assert page.locator("#scroll").evaluate("el => el.scrollTop") > 0, tab

        page.locator("[data-tab=notes]").click()
        page.locator(".note-main").filter(has_text="scroll-check").click()
        area = page.locator("#edText")
        area.wait_for()
        assert area.input_value() == LONG_TEXT
        assert area.evaluate("el => el.scrollHeight > el.clientHeight"), "Long note is clipped"
        assert area.evaluate("el => getComputedStyle(el).overflowY") == "auto"
        box = area.bounding_box()
        if engine == "chromium":
            # A real touch gesture must scroll the text, not just its parent.
            cdp = context.new_cdp_session(page)
            x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] * .8
            cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x, "y": y}]})
            for step in range(1, 7):
                cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x, "y": y - step * box["height"] / 12}]})
                page.wait_for_timeout(20)
            cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
            page.wait_for_function("() => document.querySelector('#edText').scrollTop > 0")
        else:
            # Mobile WebKit's automation API has no wheel/touch drag support.
            # Native caret navigation still verifies scrolling the textarea.
            area.press("Control+End")
            page.wait_for_function("() => document.querySelector('#edText').scrollTop > 0")

        area.evaluate("el => el.scrollTop = el.scrollHeight")
        assert area.evaluate("el => Math.abs(el.scrollHeight - el.clientHeight - el.scrollTop) < 2")
        # Telegram viewport event without a window resize (keyboard/WebView).
        page.evaluate("""() => { Telegram.WebApp.viewportHeight = 300;
          __tgEvents.viewportChanged({isStateStable: true}); }""")
        page.wait_for_function("() => document.querySelector('#app').clientHeight === 300")
        assert_inside(page, area, 300)
        # A browser/visual viewport shrink must also work with a stale SDK height.
        page.evaluate("Telegram.WebApp.viewportHeight = 1000")
        page.set_viewport_size({"width": width, "height": 340})
        page.wait_for_function("() => document.querySelector('#app').clientHeight === 340")
        assert_inside(page, area, 340)
        area.press("Control+End")
        area.press("End")
        area.type(" END-OF-NOTE")
        assert area.input_value().endswith(" END-OF-NOTE")
        page.locator("#edSave").click()
        page.wait_for_function("() => document.querySelector('#edState').textContent === 'ذخیره شد'")
        assert saved == [LONG_TEXT + " END-OF-NOTE"], "Save changed or lost text"
        page.locator(".ed-back").click()
        page.locator("#nav").wait_for(state="visible")
        assert not errors, errors
        gesture = "touch" if engine == "chromium" else "caret scroll"
        print(f"PASS {engine} {width}x{height}: lists, long note, {gesture}, last line, viewport, save, back")


def assert_inside(page, area, height):
    text = area.bounding_box()
    toolbar = page.locator("#edbar").bounding_box()
    assert text["height"] > 50
    assert text["y"] + text["height"] <= toolbar["y"] + 1
    assert toolbar["y"] + toolbar["height"] <= height + 1


if __name__ == "__main__":
    main()
