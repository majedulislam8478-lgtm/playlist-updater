import json
import logging
import os
import sys
import tempfile
from datetime import datetime, timezone, timedelta

CONFIG_FILE = "channels.json"
OUTPUT_FILE = "playlist.m3u8"
BD_TZ = timezone(timedelta(hours=6))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("playlist")


def countdown_label(start_time):
    if not start_time:
        return ""
    try:
        start = datetime.fromisoformat(start_time)
        if start.tzinfo is None:
            start = start.replace(tzinfo=BD_TZ)
    except ValueError:
        log.warning("Invalid start_time: %s", start_time)
        return ""
    diff = start - datetime.now(timezone.utc)
    if diff.total_seconds() <= 0:
        return "[LIVE] "
    total = int(diff.total_seconds())
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"[Starts in: {h:02d}:{m:02d}:{s:02d}] "


def load_channels():
    if not os.path.exists(CONFIG_FILE):
        log.error("%s not found", CONFIG_FILE)
        sys.exit(1)
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        log.error("Invalid JSON: %s", e)
        sys.exit(1)
    if not isinstance(data, list):
        log.error("%s must contain a list", CONFIG_FILE)
        sys.exit(1)
    return data


def build_entry(ch):
    name = str(ch.get("name", "")).strip()
    url = str(ch.get("url", "")).strip()
    if not name or not url.startswith(("http://", "https://")):
        log.warning("Skipping invalid entry: %s", ch)
        return None
    group = ch.get("group", "Live")
    headers = {k.lower(): v for k, v in (ch.get("headers") or {}).items()}
    label = countdown_label(ch.get("start_time"))
    lines = [f'#EXTINF:-1 group-title="{group}",{label}{name}']
    if "referer" in headers:
        lines.append(f'#EXTVLCOPT:http-referrer={headers["referer"]}')
    if "user-agent" in headers:
        lines.append(f'#EXTVLCOPT:http-user-agent={headers["user-agent"]}')
    lines.append(url)
    return "\n".join(lines)


def write_atomic(path, content):
    fd, tmp = tempfile.mkstemp(dir=".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def main():
    entries = [e for e in (build_entry(c) for c in load_channels()) if e]
    if not entries:
        log.error("No valid entries.")
        sys.exit(1)
    content = "#EXTM3U\n\n" + "\n\n".join(entries) + "\n"
    write_atomic(OUTPUT_FILE, content)
    log.info("Playlist generated with %d entries", len(entries))


if __name__ == "__main__":
    main()
