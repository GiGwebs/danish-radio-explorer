#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Index downloaded audio tracks under specified root folders and cache the results
for fast lookup during playlist CSV annotation.

- Scans the following default roots (override with --roots):
  1) /Users/gigwebs/Library/CloudStorage/Dropbox/MUSIC BANK/Rekordbox Scouts/Rekordbox Filter
  2) /Users/gigwebs/Music/DJ Collection

- Outputs JSON cache at:
  <Radio Filter Base>/Outputs/Cache/downloaded_index.json

Cache schema (version 1):
{
  "version": 1,
  "generated_at": "YYYY-MM-DDTHH:MM:SS",
  "items": [
    {
      "key": "norm(artist) - norm(title)",
      "artist": "...",
      "title": "...",
      "path": "/abs/path/to/file.mp3",
      "ext": ".mp3",
      "size": 1234567,
      "mtime": 1690000000.0
    },
    ...
  ]
}

Notes:
- Attempts to read tags using mutagen if available; falls back to filename parsing.
- Audio extensions: .mp3, .m4a (can be extended).
"""

import os
import sys
import json
import time
import argparse
import logging
import re
from datetime import datetime

# Try optional tag reader
try:
    from mutagen.easyid3 import EasyID3  # type: ignore
    from mutagen.mp4 import MP4  # type: ignore
    HAVE_MUTAGEN = True
except Exception:
    HAVE_MUTAGEN = False

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("index_downloaded_tracks")

AUDIO_EXTS = {".mp3", ".m4a"}

# Resolve Base (Radio Filter root = one level up from this script)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
CACHE_DIR = os.path.join(BASE_DIR, 'Outputs', 'Cache')
CACHE_FILE = os.path.join(CACHE_DIR, 'downloaded_index.json')

DEFAULT_ROOTS = [
    "/Users/gigwebs/Library/CloudStorage/Dropbox/MUSIC BANK/Rekordbox Scouts/Rekordbox Filter",
    "/Users/gigwebs/Music/DJ Collection",
]

TOKEN_DROP = {
    'feat', 'ft', 'featuring', 'remix', 'edit', 'version', 'radio', 'mix'
}

WS_RE = re.compile(r"\s+")
PUNC_RE = re.compile(r"[\(\)\[\]\{\}/\\:,;._\-]+")


def norm_text(t: str) -> str:
    t = (t or '').lower()
    t = t.replace("’", "'")
    t = PUNC_RE.sub(" ", t)
    parts = [p for p in t.split() if p not in TOKEN_DROP]
    t = " ".join(parts)
    t = WS_RE.sub(" ", t).strip()
    return t


def make_key(artist: str, title: str) -> str:
    return f"{norm_text(artist)} - {norm_text(title)}".strip()


def parse_filename_guess(path: str) -> tuple[str, str]:
    """Fallback: try to parse 'Artist - Title.ext' from filename."""
    name = os.path.splitext(os.path.basename(path))[0]
    parts = name.split(" - ", 1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return "", name.strip()


def extract_tags(path: str) -> tuple[str, str]:
    if not HAVE_MUTAGEN:
        return parse_filename_guess(path)
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".mp3":
            audio = EasyID3(path)
            artist = (audio.get('artist') or audio.get('albumartist') or [""])[0]
            title = (audio.get('title') or [""])[0]
            if artist or title:
                return artist, title
        elif ext == ".m4a":
            mp4 = MP4(path)
            artist = (mp4.tags.get('\u00a9ART') or mp4.tags.get('aART') or [""])[0]
            title = (mp4.tags.get('\u00a9nam') or [""])[0]
            if artist or title:
                return str(artist), str(title)
    except Exception:
        pass
    return parse_filename_guess(path)


def scan_roots(roots: list[str]) -> list[dict]:
    items: list[dict] = []
    for root in roots:
        if not os.path.exists(root):
            logger.warning(f"Root does not exist, skipping: {root}")
            continue
        for dirpath, _, filenames in os.walk(root):
            for fn in filenames:
                ext = os.path.splitext(fn)[1].lower()
                if ext not in AUDIO_EXTS:
                    continue
                p = os.path.join(dirpath, fn)
                try:
                    stat = os.stat(p)
                    artist, title = extract_tags(p)
                    key = make_key(artist, title)
                    items.append({
                        "key": key,
                        "artist": artist,
                        "title": title,
                        "path": p,
                        "ext": ext,
                        "size": stat.st_size,
                        "mtime": stat.st_mtime,
                    })
                except Exception as e:
                    logger.debug(f"Skip {p}: {e}")
    return items


def save_cache(items: list[dict]) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    data = {
        "version": 1,
        "generated_at": datetime.now().isoformat(timespec='seconds'),
        "items": items,
    }
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"Indexed {len(items)} audio files -> {CACHE_FILE}")


def main():
    parser = argparse.ArgumentParser(description="Index downloaded audio files")
    parser.add_argument('--roots', nargs='*', help='Override scan roots')
    args = parser.parse_args()

    roots = args.roots if args.roots else DEFAULT_ROOTS
    items = scan_roots(roots)
    save_cache(items)

if __name__ == '__main__':
    main()
