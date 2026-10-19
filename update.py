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
    """হোমপেজ থেকে লাইভ ইভেন্ট এবং যেগুলোর স্ট্যাটাস লাইভ বা কাছাকাছি, সেগুলোর তথ্য সংগ্রহ করে"""
    try:
        res = session.get(BASE_URL, timeout=15)
        res.raise_for_status()
    except Exception as exc:
        log.error("Failed to fetch homepage: %s", exc)
        return []

    soup = BeautifulSoup(res.text, "html.parser")
    events = []

    # প্রতিটি ম্যাচ কার্ড বা আইটেম চেক করা
    for item in soup.select(".match-item, .card, div"):
        a = item.select_one("a[href*='/events/']")
        if not a:
            continue

        href = a.get("href")
        name = a.get_text(" ", strip=True)
        
        # কার্ডের ভেতরের টেক্সট চেক করা (যেমন: Live Now বা Starts in সময়)
        card_text = item.get_text(" ", strip=True).lower()

        # ফিলتر: শুধুমাত্র যেগুলো Live Now অথবা কাছাকাছি সময়ে শুরু হবে (যেমন Starts in কম সময়)
        # অথবা আমরা সরাসরি সব ইভেন্ট চেক করে দেখবো যে m3u8 পাওয়া যায় কিনা।
        if href and name:
            full_url = urljoin(BASE_URL, href)
            if not any(e["url"] == full_url for e in events):
                events.append({
                    "name": name[:100],
                    "url": full_url,
                    "card_text": card_text
                })

    log.info("Found %d total events on homepage", len(events))
    return events


def extract_stream_info(event_url):
    """ইভেন্ট পেজ থেকে শুধু আসল m3u8 লিংক খুঁজে বের করে"""
    try:
        res = session.get(event_url, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")

        player_links = []
        for tag in soup.select("table a, .table a, a[href*='http'], td a, a.watch-btn"):
            link = tag.get("href")
            text = tag.get_text(strip=True).lower()
            if link and ("watch" in text or "player" in link or "stream" in link or "alpha" in link or "bhalocast" in link):
                player_links.append(urljoin(event_url, link))

        if not player_links:
            for tag in soup.select("a[href]"):
                link = tag.get("href")
                if link and not link.startswith("#") and "pogo.pk" not in link:
                    player_links.append(urljoin(event_url, link))

        for player_url in player_links:
            try:
                player_res = session.get(player_url, headers={"Referer": event_url}, timeout=15)
                player_html = player_res.text

                # Regex দিয়ে শুধুমাত্র .m3u8 URL খোঁজা
                m3u8_match = re.search(r'(https?://[^\s\'"]+\.m3u8[^\s\'"]*)', player_html)

                if m3u8_match:
                    m3u8_url = m3u8_match.group(1).replace("\\", "")
                    return m3u8_url, player_url
            except Exception:
                continue

    except Exception as exc:
        log.warning("Error parsing stream from %s: %s", event_url, exc)

    return None, None


def main():
    events = fetch_event_pages()
    json_data = []

    for event in events:
        log.info("Checking stream for: %s", event["name"])
        stream_url, referer = extract_stream_info(event["url"])

        # শর্ত: শুধুমাত্র যেগুলোতে আসল .m3u8 লিংক পাওয়া যাবে, কেবল সেগুলোই JSON-এ যুক্ত হবে
        if stream_url:
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
            log.info("Added live stream for: %s", event["name"])
        else:
            log.info("Skipped (Not live yet): %s", event["name"])

    # channels.json ফাইলে শুধু লাইভ ম্যাচগুলো সেভ করা
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)

    log.info("Successfully generated %s with %d active live entries.", OUTPUT_JSON, len(json_data))


if __name__ == "__main__":
    main()
