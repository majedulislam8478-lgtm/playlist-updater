import json
import logging
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# Logger Setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("playlist_json")

BASE_URL = "https://pogo.pk/"
OUTPUT_JSON = "channels.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": BASE_URL,
}

session = requests.Session()
session.headers.update(HEADERS)


def fetch_event_pages():
    """হোমপেজ থেকে লাইভ ইভেন্টের লিংক এবং নাম সংগ্রহ করে"""
    try:
        res = session.get(BASE_URL, timeout=15)
        res.raise_for_status()
    except Exception as exc:
        log.error("Failed to fetch homepage: %s", exc)
        return []

    soup = BeautifulSoup(res.text, "html.parser")
    events = []

    for a in soup.select("a[href*='/events/'], .match-item a[href], .card a[href]"):
        href = a.get("href")
        name = a.get_text(" ", strip=True)

        if not href or not name:
            continue

        full_url = urljoin(BASE_URL, href)
        if not any(e["url"] == full_url for e in events):
            events.append({
                "name": name[:100],
                "url": full_url
            })

    log.info("Found %d events on homepage", len(events))
    return events


def extract_stream_info(event_url):
    """ইভেন্ট পেজ থেকে m3u8 লিংক বা প্লেয়ার লিংক খুঁজে বের করে"""
    try:
        res = session.get(event_url, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")

        player_links = []
        for tag in soup.select("a[href*='player'], a[href*='stream'], iframe[src], a.watch-btn, [data-stream]"):
            link = tag.get("href") or tag.get("src") or tag.get("data-stream")
            if link:
                player_links.append(urljoin(event_url, link))

        if not player_links:
            player_links.append(event_url)

        for player_url in player_links:
            try:
                player_res = session.get(player_url, headers={"Referer": event_url}, timeout=15)
                player_html = player_res.text

                # Regex দিয়ে .m3u8 URL খোঁজা
                m3u8_match = re.search(r'(https?://[^\s\'"]+\.m3u8[^\s\'"]*)', player_html)

                if m3u8_match:
                    m3u8_url = m3u8_match.group(1).replace("\\", "")
                    return m3u8_url, player_url
            except Exception:
                continue

    except Exception as exc:
        log.warning("Error parsing stream from %s: %s", event_url, exc)

    # যদি সরাসরি .m3u8 না পাওয়া যায়, তবে ইভেন্ট লিংকটিকেই রিটার্ন করবে যাতে লিস্ট খালি না থাকে
    return event_url, event_url


def main():
    events = fetch_event_pages()
    json_data = []

    for event in events:
        log.info("Processing event: %s", event["name"])
        stream_url, referer = extract_stream_info(event["url"])

        headers_dict = {
            "Referer": referer if referer else event["url"],
            "User-Agent": HEADERS["User-Agent"]
        }

        item = {
            "name": event["name"],
            "group": "Pogo Live Sports",
            "url": stream_url,
            "start_time": "",
            "headers": headers_dict
        }

        json_data.append(item)

    # channels.json ফাইলে সেভ করা
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)

    log.info("Successfully generated %s with %d entries.", OUTPUT_JSON, len(json_data))


if __name__ == "__main__":
    main()
