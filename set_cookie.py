#!/usr/bin/env python3
"""set_cookie.py — connect Beat Drop to your YouTube Music account.

Your session cookie is pasted into a HIDDEN prompt (nothing is shown on screen, nothing touches
the clipboard after you paste), checked, saved to ONE file only you can read, and tested.
This script never prints, logs, or sends the cookie anywhere.

How to copy the cookie (desktop Chrome, Edge, or Firefox):
  1. Open https://music.youtube.com and make sure you are signed in.
  2. Open DevTools (F12) and go to the Network tab.
  3. Click "Library" on the page, then click a request named "browse" in the Network list.
  4. Under Request Headers, find "cookie", right-click its value, and choose Copy value.
  5. Run:  python set_cookie.py   and paste when asked. Then clear your clipboard.

The session file lives at ~/.beat-drop/auth.json (or BEAT_DROP_AUTH, if you set it).
"""
import getpass
import json
import os
import sys
from pathlib import Path

AUTH = Path(os.environ.get("BEAT_DROP_AUTH", Path.home() / ".beat-drop" / "auth.json"))


def write_private(path: Path, text: str) -> None:
    """Write a file only the current user can read (0600 on macOS/Linux)."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    if os.name == "posix":
        os.chmod(path, 0o600)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    cookie = getpass.getpass("Paste the cookie value (hidden), then press Enter: ").strip()
    if cookie.lower().startswith("cookie:"):
        cookie = cookie.split(":", 1)[1].strip()
    if "SAPISID=" not in cookie or "\n" in cookie or len(cookie) < 100:
        print("That doesn't look like a YouTube Music cookie (no SAPISID in it). Nothing was saved.")
        print("Copy the VALUE next to 'cookie' in the 'browse' request's Request Headers and try again.")
        return 1
    if "__Secure-3PAPISID=" not in cookie:
        print("That cookie is missing __Secure-3PAPISID, so it's from a signed-out or partial request.")
        print("Make sure you're signed in, reload music.youtube.com, and copy from the 'browse' request. Nothing was saved.")
        return 1

    AUTH.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        os.chmod(AUTH.parent, 0o700)

    data = {}
    if AUTH.exists():
        try:
            data = json.loads(AUTH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        # Exactly ONE backup, private like the original. Old sessions are not hoarded.
        write_private(AUTH.with_suffix(".json.bak"), AUTH.read_text(encoding="utf-8"))
    data.update({
        "cookie": cookie,
        "origin": "https://music.youtube.com",
        "x-goog-authuser": data.get("x-goog-authuser", "0"),
    })
    data.pop("authorization", None)  # the server rebuilds this from the cookie on every call
    write_private(AUTH, json.dumps(data, indent=2))
    del cookie

    # The same check the status tool uses. A dead session raises nothing (YouTube just serves an
    # empty library), so "no error" is not a login. Only SIGNED IN counts.
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import beat_drop
        state = beat_drop.session_state()
    except Exception as e:  # noqa: BLE001
        state = f"SIGNED OUT - the check failed ({type(e).__name__})"
    if not state.startswith("SIGNED IN"):
        print("Saved, but YouTube Music did not accept the session:")
        print(f"  {state}")
        print("Copy the cookie again from a freshly loaded, signed-in page.")
        return 2
    print(f"Connected: {state}")
    print(f"Session saved privately at {AUTH}. You can clear your clipboard now.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
