#!/usr/bin/env python3

import os
import re
import json
import hashlib
from pathlib import Path

import requests

# ---- Config ----------------------------------------------------------------
URL = "https://studentvillage.ch/en/apply/"
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")
STATE_FILE = Path(os.environ.get("SV_STATE_FILE", "sv_state.json"))
TIMEOUT = 30

FULL_MARKERS = [
    "all rooms are rented",
    "we do not have a waiting list",
]
# ---------------------------------------------------------------------------


def fetch_visible_text(url: str) -> str:
    resp = requests.get(
        url, timeout=TIMEOUT,
        headers={"User-Agent": "personal-room-watcher/1.0 (individual use)"},
    )
    resp.raise_for_status()
    html = resp.text
    html = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<style.*?</style>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


def looks_full(text: str) -> bool:
    return any(marker in text for marker in FULL_MARKERS)


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state))


def notify(title: str, message: str) -> None:
    print(f"[NOTIFY] {title} :: {message}")
    if not NTFY_TOPIC:
        print("  (NTFY_TOPIC not set - printed only.)")
        return
    try:
        requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=message.encode("utf-8"),
            headers={"Title": title, "Priority": "high", "Tags": "house"},
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        print(f"  (ntfy send failed: {exc})")


def main() -> None:
    try:
        text = fetch_visible_text(URL)
    except requests.RequestException as exc:
        print(f"[WARN] could not fetch page: {exc}")
        return

    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    full_now = looks_full(text)

    state = load_state()
    prev_digest = state.get("digest")
    prev_full = state.get("full")

    opened = prev_full is True and full_now is False
    changed = prev_digest is not None and digest != prev_digest

    if opened:
        notify(
            "🏠 Student Village Zurich - possible opening!",
            f"The 'all rooms rented' notice is GONE. Check now and email "
            f"service@livit.ch fast: {URL}",
        )
    elif changed:
        notify(
            "Student Village Zurich - page changed",
            f"The Apply page changed (not clearly an opening). Worth a look: {URL}",
        )
    else:
        print("[OK] No change." if prev_digest else "[OK] First run - baseline saved.")

    save_state({"digest": digest, "full": full_now})


if __name__ == "__main__":
    main()
