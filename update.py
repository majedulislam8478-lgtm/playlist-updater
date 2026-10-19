import json
import logging
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

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
    """Homepage theke protiti event-er link ebong name khunje ber kore."""
    try:
        res = session.get(BASE_URL, timeout=15)
        res.raise_for_status()
    except Exception as exc:
        log.error("Failed to fetch homepage: %s", exc)
        return []

    soup = BeautifulSoup(res.text, "html.parser")
    events = []

    # Match/Event links selector
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
    """Event page theke player page-e giye direct m3u8 ebong referer extract kore."""
    try:
        res = session.get(event_url, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")

        # Player ba stream iframe/link khunja
        player_links = []
        for tag in soup.select("a[href*='player'], a[href*='stream'], iframe[src]"):
            link = tag.get("href") or tag.get("src")
            if link:
                player_links.append(urljoin(event_url, link))

        for player_url in player_links:
            # Player page fetch kora
            player_res = session.get(player_url, headers={"Referer": event_url}, timeout=15)
            player_html = player_res.text

            # Regex diye m3u8 URL khunja
            m3u8_match = re.search(r'(https?://[^\s\'"]+\.m3u8[^\s\'"]*)', player_html)

            if m3u8_match:
                m3u8_url = m3u8_match.group(1).replace("\\", "")
                referer = player_url
                return m3u8_url, referer

    except Exception as exc:
        log.warning("Error parsing stream from %s: %s", event_url, exc)

    return None, None


def main():
    events = fetch_event_pages()
    json_data = []

    for event in events:
        log.info("Processing event: %s", event["name"])
        m3u8_url, referer = extract_stream_info(event["url"])

        # M3U8 paowa gele JSON-e add hobe, na paowa gele fallback hisebe event URL thakbe
        stream_url = m3u8_url if m3u8_url else event["url"]
        headers_dict = {}

        if referer:
            headers_dict["Referer"] = referer
        else:
            headers_dict["Referer"] = event["url"]

        headers_dict["User-Agent"] = HEADERS["User-Agent"]

        item = {
            "name": event["name"],
            "group": "Pogo Live Sports",
            "url": stream_url,
            "start_time": "",  # Proyojon onujayi website theke time format Parse kore boshano jabe
            "headers": headers_dict
        }

        json_data.append(item)

    # JSON File-e save kora
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)

    log.info("Successfully generated %s with %d entries.", OUTPUT_JSON, len(json_data))


if __name__ == "__main__":
    main()
