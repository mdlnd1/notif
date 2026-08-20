#!/usr/bin/env python3

import os
import re
import json
from pathlib import Path

import requests

# ---- Config ----------------------------------------------------------------
URL = "https://studentvillage.ch/en/"          # homepage carries the status banner
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")
STATE_FILE = Path(os.environ.get("SV_STATE_FILE", "sv_state.json"))
TIMEOUT = 30

# The site's own "rooms full" flag: the div that wraps the occupied banner.
FLAG_CLASS_RE = re.compile(r'class="[^"]*label_all_room_rented[^"]*"', re.I)

# Text fallbacks, in case they tweak the class but keep the wording.
OCCUPIED_TEXTS = [
    "all rooms are currently occupied",
    "all rooms are rented",
    "currently all rooms are rented",
]
# ---------------------------------------------------------------------------


def fetch(url: str) -> str:
    resp = requests.get(
        url, timeout=TIMEOUT,
        headers={"User-Agent": "personal-room-watcher/2.0 (individual use)"},
    )
    resp.raise_for_status()
    return resp.text


def visible_text(html: str) -> str:
    h = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    h = re.sub(r"<style.*?</style>", " ", h, flags=re.S | re.I)
    h = re.sub(r"<[^>]+>", " ", h)
    return re.sub(r"\s+", " ", h).strip().lower()


def is_occupied(html: str) -> bool:
    """True while the site still shows the 'rooms occupied' banner."""
    if FLAG_CLASS_RE.search(html):
        return True
    text = visible_text(html)
    return any(t in text for t in OCCUPIED_TEXTS)


def banner_text(html: str) -> str:
    """Grab the occupied banner's words, for a low-key 'wording changed' heads-up."""
    m = re.search(r"label_all_room_rented(.*?)</div>\s*</div>", html, re.S | re.I)
    if not m:
        return ""
    t = re.sub(r"<[^>]+>", " ", m.group(1))
    return re.sub(r"\s+", " ", t).strip().lower()


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state))


def notify(title: str, message: str, priority: str = "high") -> None:
    print(f"[NOTIFY] {title} :: {message}")
    if not NTFY_TOPIC:
        print("  (NTFY_TOPIC not set - printed only.)")
        return
    try:
        requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=message.encode("utf-8"),
            headers={"Title": title, "Priority": priority, "Tags": "house"},
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        print(f"  (ntfy send failed: {exc})")


def main() -> None:
    try:
        html = fetch(URL)
    except requests.RequestException as exc:
        print(f"[WARN] could not fetch page: {exc}")
        return

    full = is_occupied(html)
    label = banner_text(html)

    state = load_state()
    prev_full = state.get("full")
    prev_label = state.get("label", "")

    if prev_full is None:
        print("[OK] First run - baseline saved.")
    elif prev_full and not full:
        notify(
            "\U0001F3E0 Student Village - possible opening!",
            f"The 'all rooms occupied' banner is GONE. Check now and email "
            f"service@livit.ch fast: {URL}",
            priority="high",
        )
    elif not prev_full and full:
        notify(
            "Student Village - shows occupied again",
            f"The occupied banner is back. (You may have just missed a window.) {URL}",
            priority="default",
        )
    elif full and prev_label and label != prev_label:
        notify(
            "Student Village - status wording changed",
            f"Still occupied, but the banner text changed. Worth a quick check: {URL}",
            priority="low",
        )
    else:
        print(f"[OK] No change. occupied={full}")

    save_state({"full": full, "label": label})


if __name__ == "__main__":
    main()
