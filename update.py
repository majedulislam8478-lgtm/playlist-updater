from datetime import datetime, timezone, timedelta
import json
import logging
import os
import re
import sys
import tempfile
import requests
from bs4 import BeautifulSoup

OUTPUT_FILE = "playlist.m3u8"
BD_TZ = timezone(timedelta(hours=6))

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
)
log = logging.getLogger("playlist")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://pogo.pk/",
}


def fetch_pogo_matches():
  """pogo.pk ওয়েবসাইট থেকে লাইভ ও আপকামিং ম্যাচের তথ্য ফেচ করে"""
  url = "https://pogo.pk/"
  try:
    response = requests.get(url, headers=HEADERS, timeout=15)
    response.raise_for_status()
  except requests.RequestException as e:
    log.error("Failed to fetch pogo.pk: %s", e)
    return []

  soup = BeautifulSoup(response.text, "html.parser")
  channels = []

  # পোগো ডট পিকে সাইটের গঠন অনুযায়ী ম্যাচ বা স্ট্রিম এলিমেন্টগুলো সংগ্রহ করা
  # সাধারণত প্রতিটি ম্যাচের একটি টাইটেল এবং স্ট্রিম লিংক বা ডিটেইল পেজ থাকে
  # এখানে সাইটের স্ট্রাকচার অনুযায়ী ম্যাচ আইটেমগুলো পার্স করা হচ্ছে:
  for item in soup.select("a[href*='stream'], .match-item, .card, li"):
    href = item.get("href", "")
    text = item.get_text(" ", strip=True)

    if not href or ("pogo.pk" not in href and not href.startswith("/")):
      continue

    full_url = href if href.startswith("http") else f"https://pogo.pk{href}"

    # ম্যাচ নেম বা ডিটেইল আলাদা করা
    if " vs " in text or " - " in text:
      channels.append({
          "name": text[:60], 
          "url": full_url,
          "group": "Pogo Live",
          "headers": {"referer": "https://pogo.pk/", "user-agent": HEADERS["User-Agent"]},
      })

  # যদি সরাসরি লিংক না পাওয়া যায়, তবে ব্যাকআপ হিসেবে কিছু ডিফল্ট স্ট্রিম সোর্স বা পেজ থেকে ডেটা নেওয়া যেতে পারে
  if not channels:
    log.warning(
        "No dynamic matches parsed directly, checking alternative selectors..."
    )
    # সাইটের নিজস্ব প্রধান ক্যাটাগরি বা ম্যাচ লিঙ্ক ট্র্যাক করার জন্য
    for a in soup.find_all("a", href=True):
      link = a["href"]
      if "match" in link or "live" in link:
        full_link = link if link.startswith("http") else f"https://pogo.pk{link}"
        title = a.get_text(strip=True)
        if title and len(title) > 3:
          channels.append({
              "name": title,
              "url": full_link,
              "group": "Pogo Sports",
              "headers": {
                  "referer": "https://pogo.pk/",
                  "user-agent": HEADERS["User-Agent"],
              },
          })

  # ডুপ্লিকেট রিমুভ করা
  unique_channels = []
  seen_urls = set()
  for ch in channels:
    if ch["url"] not in seen_urls:
      seen_urls.add(ch["url"])
      unique_channels.append(ch)

  return unique_channels


def build_entry(ch):
  name = str(ch.get("name", "")).strip()
  url = str(ch.get("url", "")).strip()
  if not name or not url.startswith(("http://", "https://")):
    return None

  group = ch.get("group", "Pogo Live")
  headers = {k.lower(): v for k, v in (ch.get("headers") or {}).items()}

  lines = [f'#EXTINF:-1 group-title="{group}",{name}']
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
  raw_channels = fetch_pogo_matches()
  if not raw_channels:
    log.error("No channels fetched from pogo.pk.")
    # ফলব্যাক বা ডিফল্ট এন্ট্রি রাখতে পারেন যদি সাইট থেকে লাইভ ম্যাচ না পাওয়া যায়
    raw_channels = [{
        "name": "Pogo.pk Home Stream",
        "url": "https://pogo.pk/",
        "group": "Pogo Live",
        "headers": {
            "referer": "https://pogo.pk/",
            "user-agent": HEADERS["User-Agent"],
        },
    }]

  entries = [e for e in (build_entry(c) for c in raw_channels) if e]
  content = "#EXTM3U\n\n" + "\n\n".join(entries) + "\n"
  write_atomic(OUTPUT_FILE, content)
  log.info("Playlist generated with %d entries from Pogo.pk", len(entries))


if __name__ == "__main__":
  main()
