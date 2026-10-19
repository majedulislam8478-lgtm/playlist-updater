
from datetime import timezone, timedelta
import logging
import os
import tempfile
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

OUTPUT_FILE = "playlist.m3u8"
BASE_URL = "https://pogo.pk/"
BD_TZ = timezone(timedelta(hours=6))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("playlist")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": BASE_URL,
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def fetch_pogo_matches():
    """Fetch publicly accessible match links from Pogo.pk."""
    try:
        response = SESSION.get(BASE_URL, timeout=20)
        response.raise_for_status()
    except requests.RequestException as exc:
        log.error("Failed to fetch Pogo.pk: %s", exc)
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    channels = []
    seen_urls = set()

    selectors = [
        "a[href*='stream']",
        "a[href*='match']",
        "a[href*='live']",
        ".match-item a[href]",
        ".card a[href]",
    ]

    links = []
    for selector in selectors:
        links.extend(soup.select(selector))

    for item in links:
        href = (item.get("href") or "").strip()
        name = item.get_text(" ", strip=True)

        if not href or not name:
            continue

        full_url = urljoin(BASE_URL, href)
        parsed = urlparse(full_url)

        if parsed.scheme not in ("http", "https"):
            continue

        # Only accept links hosted on the expected website.
        if parsed.hostname not in ("pogo.pk", "www.pogo.pk"):
            continue

        if full_url in seen_urls:
            continue

        seen_urls.add(full_url)

        channels.append({
            "name": name[:100],
            "url": full_url,
            "group": "Pogo Live",
            "headers": {
                "referer": BASE_URL,
                "user-agent": HEADERS["User-Agent"],
            },
        })

    log.info("Found %d candidate links on Pogo.pk", len(channels))
    return channels


def build_entry(channel):
    name = str(channel.get("name", "")).strip()
    url = str(channel.get("url", "")).strip()
    group = str(channel.get("group", "Pogo Live")).strip()

    if not name or not url:
        return None

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        log.warning("Skipping invalid URL: %s", url)
        return None

    # Prevent malformed M3U metadata.
    name = name.replace("\r", " ").replace("\n", " ").replace(",", " ")
    group = group.replace('"', "").replace("\r", " ").replace("\n", " ")

    headers = {
        str(key).lower(): str(value)
        for key, value in (channel.get("headers") or {}).items()
    }

    lines = [f'#EXTINF:-1 group-title="{group}",{name}']

    if headers.get("referer"):
        referer = headers["referer"].replace("\r", "").replace("\n", "")
        lines.append(f"#EXTVLCOPT:http-referrer={referer}")

    if headers.get("user-agent"):
        user_agent = headers["user-agent"].replace("\r", "").replace("\n", "")
        lines.append(f"#EXTVLCOPT:http-user-agent={user_agent}")

    lines.append(url)
    return "\n".join(lines)


def write_atomic(path, content):
    """Write the playlist atomically to avoid partial files."""
    directory = os.path.dirname(os.path.abspath(path))

    fd, temp_path = tempfile.mkstemp(
        dir=directory,
        prefix=".playlist_",
        suffix=".tmp",
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as file:
            file.write(content)

        os.replace(temp_path, path)

    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise


def main():
    channels = fetch_pogo_matches()

    if not channels:
        log.error(
            "No match links found. Existing playlist will not be overwritten."
        )
        return

    entries = []
    for channel in channels:
        entry = build_entry(channel)
        if entry:
            entries.append(entry)

    if not entries:
        log.error("No valid playlist entries generated.")
        return

    content = "#EXTM3U\n" + "\n".join(entries) + "\n"

    try:
        write_atomic(OUTPUT_FILE, content)
    except OSError as exc:
        log.error("Failed to write playlist: %s", exc)
        raise

    log.info(
        "Playlist generated successfully with %d entries: %s",
        len(entries),
        OUTPUT_FILE,
    )


if __name__ == "__main__":
    main()
