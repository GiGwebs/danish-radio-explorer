"""
Helper library for playlist integration:
- Local library index using mutagen
- Fuzzy matching using rapidfuzz
- VirtualDJ .vdjfolder export (local + TIDAL netsearch where available)
- M3U8 export (local-only)
- Discovery utilities to find latest compiled CSVs
"""
from __future__ import annotations

import csv
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from rapidfuzz import fuzz, process  # type: ignore
from mutagen import File as MutagenFile  # type: ignore


# -----------------------------
# Data models
# -----------------------------

@dataclass
class TrackRow:
    artist: str
    title: str
    duration: Optional[float] = None
    bpm: Optional[float] = None
    musical_key: Optional[str] = None

    def key(self) -> str:
        return normalize_key(self.artist, self.title)


@dataclass
class MatchResult:
    row: TrackRow
    local_path: Optional[Path]
    confidence: float
    tidal_id: Optional[str]


# -----------------------------
# Normalization
# -----------------------------

def normalize_text(s: str) -> str:
    s = s.strip().lower()
    # remove common featuring markers
    s = re.sub(r"\b(feat|ft|featuring)\.?\b", "", s)
    # remove common qualifiers in brackets like (radio edit), [remastered 2011], {extended mix}
    s = re.sub(r"\((?:[^)]*(?:remix|edit|version|remaster|live|extended|mix)[^)]*)\)", " ", s, flags=re.I)
    s = re.sub(r"\[(?:[^\]]*(?:remix|edit|version|remaster|live|extended|mix)[^\]]*)\]", " ", s, flags=re.I)
    s = re.sub(r"\{(?:[^}]*(?:remix|edit|version|remaster|live|extended|mix)[^}]*)\}", " ", s, flags=re.I)
    # remove trailing qualifiers like '- radio edit', '- remastered 2009'
    s = re.sub(r"\b(?:radio|club|extended|clean|dirty)\s+edit\b", "", s, flags=re.I)
    s = re.sub(r"\bremaster(?:ed)?\b(?:\s*\d{2,4})?", "", s, flags=re.I)
    # normalize connectors
    s = s.replace(" & ", " and ")
    s = s.replace("–", "-")
    # collapse extra spaces
    s = re.sub(r"\s+", " ", s)
    return s


def normalize_key(artist: str, title: str) -> str:
    a = normalize_text(artist)
    t = normalize_text(title)
    return f"{a} - {t}"


# -----------------------------
# Parsing helpers
# -----------------------------

def parse_duration(value: str) -> Optional[float]:
    """Parse duration strings like '3:45', '03:45', '1:02:03', or seconds as number.
    Returns seconds as float.
    """
    s = (value or "").strip()
    if not s:
        return None
    # try plain number
    try:
        return float(s)
    except Exception:
        pass
    # try h:m:s or m:s
    parts = s.split(":")
    try:
        if len(parts) == 2:
            m, sec = parts
            return int(m) * 60 + float(sec)
        if len(parts) == 3:
            h, m, sec = parts
            return int(h) * 3600 + int(m) * 60 + float(sec)
    except Exception:
        return None
    return None


# Normalize header names for robust CSV parsing
def _norm_header_name(s: str) -> str:
    s = str(s or "").strip().lower()
    s = s.replace("_", " ").replace("-", " ")
    s = re.sub(r"\s+", " ", s)
    return s


def _pick_col(fieldnames: List[str], candidates: List[str], contains: Optional[List[str]] = None) -> Optional[str]:
    """Pick a column from fieldnames by case-insensitive match with normalization.

    - candidates: list of exact normalized names to try first (e.g., ["bpm", "tempo"])
    - contains: optional list of substrings to fall back on (e.g., ["bpm", "tempo"]).
    Returns the original field name if found, else None.
    """
    raw = fieldnames or []
    norm_map = {_norm_header_name(c): c for c in raw}
    for c in candidates:
        nc = _norm_header_name(c)
        if nc in norm_map:
            return norm_map[nc]
    if contains:
        for k_norm, orig in norm_map.items():
            for sub in contains:
                if _norm_header_name(sub) in k_norm:
                    return orig
    return None


# -----------------------------
# Field extraction helpers
# -----------------------------

_RE_NUM = re.compile(r"(\d+(?:\.\d+)?)")
_RE_CAMELOT = re.compile(r"\b(?:1[0-2]|[1-9])[AB]\b", re.IGNORECASE)
_RE_KEYNAME = re.compile(r"\b([A-G](?:#|b)?(?:maj|min|m|M)?)\b")


def _extract_bpm(value: str) -> Optional[float]:
    s = str(value or "").strip()
    if not s:
        return None
    try:
        return float(s)
    except Exception:
        m = _RE_NUM.search(s)
        if m:
            try:
                return float(m.group(1))
            except Exception:
                return None
    return None


def _extract_key(value: str) -> Optional[str]:
    s = str(value or "").strip()
    if not s:
        return None
    m = _RE_CAMELOT.search(s)
    if m:
        # Normalize camelot to upper (e.g., '12A')
        return m.group(0).upper()
    m2 = _RE_KEYNAME.search(s)
    if m2:
        k = m2.group(1)
        # normalize minor/major variants
        k = k.replace("maj", "M").replace("min", "m")
        return k
    return s


# -----------------------------
# XML helpers
# -----------------------------

def _escape_xml_attr(s: str) -> str:
    """Escape characters for use inside XML attribute values."""
    return (
        s.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# -----------------------------
# Library index (mutagen)
# -----------------------------

AUDIO_EXTS = {
    ".mp3", ".m4a", ".flac", ".wav", ".aif", ".aiff", ".aac", ".ogg"
}


def _extract_tags(path: Path) -> Tuple[Optional[str], Optional[str], Optional[float], Optional[float], Optional[str]]:
    try:
        audio = MutagenFile(str(path))
        if not audio:
            return None, None, None, None, None
        artist, title = None, None
        tag_bpm: Optional[float] = None
        tag_key: Optional[str] = None
        tags = getattr(audio, "tags", {}) or {}

        def _first_str(v):
            if isinstance(v, list):
                v = v[0] if v else None
            if hasattr(v, "text"):
                try:
                    return v.text[0] if getattr(v, "text", []) else None
                except Exception:
                    pass
            return str(v) if v is not None else None

        # Try common tag names for artist/title
        for k in ("artist", "ARTIST", "Author", "TPE1"):
            if hasattr(tags, "__contains__") and k in tags:
                v = _first_str(tags.get(k))
                artist = str(v) if v else artist
                if artist:
                    break
        for k in ("title", "TITLE", "Title", "TIT2"):
            if hasattr(tags, "__contains__") and k in tags:
                v = _first_str(tags.get(k))
                title = str(v) if v else title
                if title:
                    break

        # Extract BPM and Initial Key if present in tags
        # Check explicit ID3 frames and EasyID3 keys where possible
        for k in ("TBPM", "bpm", "BPM", "tempo"):
            if hasattr(tags, "__contains__") and k in tags and tag_bpm is None:
                v = _first_str(tags.get(k))
                tag_bpm = _extract_bpm(v or "") if v else None
        for k in ("TKEY", "initialkey", "InitialKey", "INITIALKEY", "key", "KEY"):
            if hasattr(tags, "__contains__") and k in tags and tag_key is None:
                v = _first_str(tags.get(k))
                tag_key = _extract_key(v or "") if v else None

        # Fallback: scan arbitrary tag keys for substrings 'bpm' and 'key'
        if (tag_bpm is None or tag_key is None) and hasattr(tags, "items"):
            try:
                for k, v in list(tags.items()):
                    kstr = str(k).lower()
                    vs = _first_str(v) or ""
                    if (tag_bpm is None) and ("bpm" in kstr):
                        tag_bpm = _extract_bpm(vs)
                    if (tag_key is None) and ("key" in kstr):
                        tag_key = _extract_key(vs)
            except Exception:
                pass

        # Duration (seconds)
        dur = None
        try:
            dur = float(audio.info.length) if hasattr(audio, "info") and hasattr(audio.info, "length") else None
        except Exception:
            dur = None
        return artist, title, dur, tag_bpm, tag_key
    except Exception:
        return None, None, None, None, None


def scan_library(root: Path, existing_index: Optional[dict] = None) -> dict:
    """Scan music library and build/refresh an index.

    Index structure:
    {
      "tracks": {
        "/abs/path.mp3": {"artist": "...", "title": "...", "key": "normalized key", "duration": 223.4}
      },
      "by_key": {"artist - title": ["/abs/path1", "/abs/path2"]},
      "mtime": {"/abs/path.mp3": 1234567890.0}
    }
    """
    index = existing_index or {"tracks": {}, "by_key": {}, "mtime": {}}

    # prune removed files
    existing_paths = set(Path(p) for p in index.get("tracks", {}).keys())
    still_exists = {p for p in existing_paths if p.exists()}
    removed = existing_paths - still_exists
    for p in removed:
        # remove from tracks
        index["tracks"].pop(str(p), None)
        # remove from mtime
        index["mtime"].pop(str(p), None)
        # remove from by_key lists
    # rebuild by_key later

    # scan filesystem
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in AUDIO_EXTS:
                continue
            p = Path(dirpath) / fn
            sp = str(p)
            mtime = p.stat().st_mtime
            if sp in index.get("mtime", {}) and index["mtime"][sp] == mtime:
                # unchanged
                continue
            artist, title, duration, tag_bpm, tag_key = _extract_tags(p)
            if not artist or not title:
                # fallback: infer from filename "Artist - Title.xxx"
                base = p.stem
                parts = re.split(r"\s*-\s*", base, maxsplit=1)
                if len(parts) == 2:
                    artist = artist or parts[0]
                    title = title or parts[1]
            if not artist or not title:
                # skip if insufficient metadata
                index["mtime"][sp] = mtime
                continue
            key = normalize_key(artist, title)
            index.setdefault("tracks", {})[sp] = {
                "artist": artist,
                "title": title,
                "key": key,
                "duration": duration,
                "tag_bpm": tag_bpm,
                "tag_key": tag_key,
            }
            index.setdefault("mtime", {})[sp] = mtime

    # rebuild by_key
    by_key: Dict[str, List[str]] = {}
    for sp, meta in index.get("tracks", {}).items():
        by_key.setdefault(meta["key"], []).append(sp)
    index["by_key"] = by_key
    return index


def save_index(path: Path, index: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(index, f)


def load_index(path: Path) -> dict:
    if not path.exists():
        return {"tracks": {}, "by_key": {}, "mtime": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"tracks": {}, "by_key": {}, "mtime": {}}


# -----------------------------
# TIDAL id discovery from VirtualDJ database
# -----------------------------

def build_tidal_index_from_vdj_db(vdj_db_path: Path) -> Dict[str, str]:
    """Parse VirtualDJ database.xml and collect mapping of normalized 'artist - title' -> 'tdXXXX'.
    We parse <Song> blocks that contain either FilePath="netsearch://td..." or <Link NetSearch="td...">.
    """
    if not vdj_db_path.exists():
        return {}
    tidal_map: Dict[str, str] = {}
    try:
        buf: List[str] = []
        inside = False
        for line in vdj_db_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "<Song " in line:
                inside = True
                buf = [line]
                continue
            if inside:
                buf.append(line)
                if "</Song>" in line:
                    block = "\n".join(buf)
                    # extract tidal id
                    m_id = re.search(r'Link\s+NetSearch="(td\d+)"', block)
                    if not m_id:
                        m_id = re.search(r'FilePath="netsearch://(td\d+)"', block)
                    tidal_id = m_id.group(1) if m_id else None
                    if tidal_id:
                        m_artist = re.search(r'Tags\s+[^>]*Author="([^"]+)"', block)
                        m_title = re.search(r'Tags\s+[^>]*Title="([^"]+)"', block)
                        if m_artist and m_title:
                            key = normalize_key(m_artist.group(1), m_title.group(1))
                            tidal_map[key] = tidal_id
                    inside = False
        return tidal_map
    except Exception:
        return {}


# New: parse BPM/Key and TIDAL id per (artist-title) from VirtualDJ DB
def build_vdj_meta_index(vdj_db_path: Path) -> Dict[str, Dict[str, Optional[str]]]:
    """Return mapping of normalized 'artist - title' -> { 'tidal_id': str|None, 'bpm': float|None, 'key': str|None }.

    We reuse the simple block parser and extract additional attributes from <Tags> if present.
    """
    if not vdj_db_path.exists():
        return {}
    meta_map: Dict[str, Dict[str, Optional[str]]] = {}
    try:
        buf: List[str] = []
        inside = False
        for line in vdj_db_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "<Song " in line:
                inside = True
                buf = [line]
                continue
            if inside:
                buf.append(line)
                if "</Song>" in line:
                    block = "\n".join(buf)
                    # tidal id
                    m_id = re.search(r'Link\s+NetSearch="(td\d+)"', block)
                    if not m_id:
                        m_id = re.search(r'FilePath="netsearch://(td\d+)"', block)
                    tidal_id = m_id.group(1) if m_id else None
                    # tags: author/title
                    m_artist = re.search(r'Tags\s+[^>]*Author="([^"]+)"', block)
                    m_title = re.search(r'Tags\s+[^>]*Title="([^"]+)"', block)
                    if m_artist and m_title:
                        key_norm = normalize_key(m_artist.group(1), m_title.group(1))
                        # bpm/key from tags
                        m_bpm = re.search(r'Tags\s+[^>]*(?:BPM|Bpm)="([^"]+)"', block)
                        m_key = re.search(r'Tags\s+[^>]*(?:Key|KEY)="([^"]+)"', block)
                        bpm_val = None
                        key_val = None
                        if m_bpm:
                            bpm_val = _extract_bpm(m_bpm.group(1))
                        if m_key:
                            key_val = _extract_key(m_key.group(1))
                        meta_map[key_norm] = {
                            "tidal_id": tidal_id,
                            "bpm": bpm_val,
                            "key": key_val,
                        }
                    inside = False
        return meta_map
    except Exception:
        return {}

# -----------------------------
# Matching
# -----------------------------

def match_playlist_rows(
    rows: List[TrackRow],
    library_index: dict,
    threshold: int = 85,
) -> List[Tuple[TrackRow, Optional[Path], float]]:
    """Return best local match per row using fuzzy key matching, preferring close duration where available.

    Improvements:
    - Use token_set_ratio for better tolerance to word order and extra tokens.
    - Candidate filter window widened to (threshold - 12) to avoid missing good matches.
    - Duration-aware acceptance: if duration delta <= 4s, allow slightly lower fuzzy score (threshold - 8).
    """
    results: List[Tuple[TrackRow, Optional[Path], float]] = []
    keys = list(library_index.get("by_key", {}).keys())

    def best_path_for_key(k: str, target_dur: Optional[float]) -> Optional[Path]:
        paths = library_index.get("by_key", {}).get(k, [])
        if not paths:
            return None
        if target_dur is None:
            return Path(paths[0])
        best_path = Path(paths[0])
        best_delta = float("inf")
        for sp in paths:
            meta = library_index.get("tracks", {}).get(sp, {})
            dur = meta.get("duration")
            if isinstance(dur, (int, float)):
                delta = abs(float(dur) - float(target_dur))
                if delta < best_delta:
                    best_delta = delta
                    best_path = Path(sp)
        return best_path

    for row in rows:
        key = row.key()
        if key in library_index.get("by_key", {}):
            # exact normalized key hit
            path = best_path_for_key(key, row.duration)
            results.append((row, path, 100.0))
            continue
        if not keys:
            results.append((row, None, 0.0))
            continue
        # get top candidates with a tolerant scorer
        candidates = process.extract(key, keys, scorer=fuzz.token_set_ratio, limit=8)
        # filter by threshold window (slightly wider to avoid false negatives)
        candidates = [c for c in candidates if c[1] >= max(0, threshold - 12)]
        if not candidates:
            results.append((row, None, 0.0))
            continue
        # prefer by duration proximity then by score
        chosen_key = None
        chosen_path: Optional[Path] = None
        chosen_score = -1.0
        best_delta = float("inf") if row.duration is not None else None
        for cand_key, score, _ in candidates:
            path = best_path_for_key(cand_key, row.duration)
            if row.duration is not None and path is not None:
                meta = library_index.get("tracks", {}).get(str(path), {})
                dur = meta.get("duration")
                if isinstance(dur, (int, float)):
                    delta = abs(float(dur) - float(row.duration))
                    if delta < (best_delta or float("inf")) or (
                        abs(delta - (best_delta or float("inf"))) < 0.001 and score > chosen_score
                    ):
                        best_delta = delta
                        chosen_key = cand_key
                        chosen_path = path
                        chosen_score = float(score)
                    continue
            # fallback: no duration info
            if score > chosen_score:
                chosen_key = cand_key
                chosen_path = path
                chosen_score = float(score)
        if chosen_key is not None and chosen_score >= threshold:
            results.append((row, chosen_path, float(chosen_score)))
        else:
            # Duration-aware acceptance: if close in time, accept slightly below threshold
            if (best_delta is not None) and (best_delta <= 4.0) and (chosen_score >= (threshold - 8)):
                results.append((row, chosen_path, float(max(chosen_score, threshold - 2))))
            else:
                results.append((row, None, float(chosen_score if chosen_score >= 0 else 0.0)))
    return results


# -----------------------------
# Cumulative + Export Mode Helpers
# -----------------------------

def resolve_matches_for_rows(
    rows: List[TrackRow],
    library_index: dict,
    tidal_index: Dict[str, str],
    threshold: int = 85,
    vdj_meta_index: Optional[Dict[str, Dict[str, Optional[str]]]] = None,
) -> List[MatchResult]:
    """Resolve matches for a provided list of TrackRow objects.

    For any unresolved local match, attempt to attach a TIDAL id via tidal_index.
    """
    # Pre-enrich rows with BPM/Key from VDJ meta and library tags
    try:
        enrich_rows_with_meta(rows, library_index, vdj_meta_index or {})
    except Exception:
        pass
    matched = match_playlist_rows(rows, library_index, threshold=threshold)
    results: List[MatchResult] = []
    for row, lpath, score in matched:
        tid = None
        if not lpath:
            tid = tidal_index.get(row.key())
        results.append(MatchResult(row=row, local_path=lpath, confidence=score, tidal_id=tid))
    return results


# ---- VirtualDJ helpers ----

def build_song_paths_for_vdj(
    matches: List[MatchResult],
    use_generic_netsearch: bool = False,
) -> List[str]:
    """Return the list of path strings that would be written to <song path="..."/> in a .vdjfolder.

    This mirrors export_vdjfolder logic but as a pure builder.
    """
    paths: List[str] = []
    for m in matches:
        if m.local_path:
            paths.append(str(m.local_path))
        elif m.tidal_id:
            paths.append(f"netsearch://{m.tidal_id}")
        else:
            if use_generic_netsearch:
                paths.append(build_generic_netsearch_uri(m.row))
            else:
                # skip missing
                continue
    return paths


def parse_vdjfolder_paths(path: Path) -> List[str]:
    """Parse an existing .vdjfolder file and return the ordered list of song path values.

    If the file cannot be read or parsed, return an empty list.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    paths: List[str] = []
    for line in text.splitlines():
        m = re.search(r'<song\s+[^>]*path="([^"]+)"', line)
        if m:
            paths.append(m.group(1))
    return paths


def write_vdjfolder_paths(list_name: str, paths: List[str], vdj_mylist_dir: Path) -> Path:
    """Write a .vdjfolder given explicit song path values."""
    vdj_mylist_dir.mkdir(parents=True, exist_ok=True)
    out = vdj_mylist_dir / f"{list_name}.vdjfolder"
    lines = ["<VirtualFolder>"]
    for p in paths:
        lines.append(f'  <song path="{_escape_xml_attr(p)}" />')
    lines.append("</VirtualFolder>")
    content = "\n".join(lines) + "\n"
    out.write_text(content, encoding="utf-8")
    return out


def export_vdjfolder_mode(
    list_name: str,
    matches: List[MatchResult],
    vdj_mylist_dir: Path,
    mode: str = "replace",  # replace | add | save_as_new
    new_name: Optional[str] = None,
    use_generic_netsearch: bool = False,
) -> Path:
    """Export VDJ folder with selectable mode.

    - replace: overwrite list_name
    - add: append only new items to existing list_name
    - save_as_new: write to new_name
    """
    new_paths = build_song_paths_for_vdj(matches, use_generic_netsearch=use_generic_netsearch)
    mode = (mode or "replace").lower()
    if mode == "save_as_new":
        target = (new_name or list_name).strip() or list_name
        return write_vdjfolder_paths(target, new_paths, vdj_mylist_dir)
    if mode == "add":
        existing_file = vdj_mylist_dir / f"{list_name}.vdjfolder"
        existing_paths = parse_vdjfolder_paths(existing_file) if existing_file.exists() else []
        seen = set(existing_paths)
        merged = existing_paths + [p for p in new_paths if p not in seen]
        return write_vdjfolder_paths(list_name, merged, vdj_mylist_dir)
    # default: replace
    return write_vdjfolder_paths(list_name, new_paths, vdj_mylist_dir)


# ---- M3U8 helpers ----

def build_m3u_entries(matches: List[MatchResult]) -> List[Tuple[str, str]]:
    """Build (#EXTINF, path) entries for local-only tracks from matches."""
    entries: List[Tuple[str, str]] = []
    for m in matches:
        if not m.local_path:
            continue
        extinf = f"#EXTINF:-1,{m.row.artist} - {m.row.title}"
        entries.append((extinf, str(m.local_path)))
    return entries


def parse_m3u_paths(path: Path) -> List[str]:
    """Parse an existing .m3u8 and return the ordered list of path lines (ignoring comments)."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    paths: List[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        paths.append(s)
    return paths


def write_m3u_from_entries(list_name: str, entries: List[Tuple[str, str]], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{list_name}.m3u8"
    lines = ["#EXTM3U"]
    for extinf, p in entries:
        lines.append(extinf)
        lines.append(p)
    content = "\n".join(lines) + "\n"
    out.write_text(content, encoding="utf-8")
    return out


def export_m3u8_mode(
    list_name: str,
    matches: List[MatchResult],
    out_dir: Path,
    mode: str = "replace",  # replace | add | save_as_new
    new_name: Optional[str] = None,
) -> Path:
    """Export M3U8 with selectable mode.

    - replace: overwrite list_name
    - add: append only new items (local-only) to existing list_name, preserving existing content
    - save_as_new: write to new_name
    """
    entries = build_m3u_entries(matches)
    mode = (mode or "replace").lower()
    if mode == "save_as_new":
        target = (new_name or list_name).strip() or list_name
        return write_m3u_from_entries(target, entries, out_dir)
    if mode == "add":
        file = out_dir / f"{list_name}.m3u8"
        if file.exists():
            existing_text = file.read_text(encoding="utf-8", errors="ignore")
            existing_paths = set(parse_m3u_paths(file))
            to_append = [(e, p) for (e, p) in entries if p not in existing_paths]
            if not to_append:
                # nothing to do
                return file
            # Append maintaining original content
            if not existing_text.endswith("\n"):
                existing_text += "\n"
            app_lines: List[str] = []
            for extinf, p in to_append:
                app_lines.append(extinf)
                app_lines.append(p)
            new_text = existing_text + "\n".join(app_lines) + "\n"
            file.write_text(new_text, encoding="utf-8")
            return file
        else:
            # no existing file; same as replace
            return write_m3u_from_entries(list_name, entries, out_dir)
    # default: replace
    return write_m3u_from_entries(list_name, entries, out_dir)


# -----------------------------
# CSV parsing & discovery
# -----------------------------

def read_playlist_csv(path: Path) -> List[TrackRow]:
    rows: List[TrackRow] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        # Robust, case-insensitive, underscore/dash-insensitive header detection
        fns = list(reader.fieldnames or [])
        artist_col = _pick_col(fns, ["artist"], contains=["artist", "author"])
        title_col = _pick_col(fns, ["title"], contains=["title"])
        dur_col = _pick_col(fns, ["duration", "length", "time"], contains=["dur", "length", "time"])
        bpm_col = _pick_col(
            fns,
            ["bpm", "tempo", "tempo (bpm)", "avg bpm", "bpm avg"],
            contains=["bpm", "tempo"],
        ) 
        key_col = _pick_col(
            fns,
            ["key", "musical key", "camelot", "initial key", "initialkey", "key (camelot)"],
            contains=["key", "camelot"],
        )
        if artist_col is None or title_col is None:
            # fallback: assume two-column CSV with Artist,Title
            f.seek(0)
            simple = csv.reader(f)
            # skip header
            next(simple, None)
            for r in simple:
                if len(r) >= 2:
                    rows.append(TrackRow(artist=r[0], title=r[1], duration=None, bpm=None, musical_key=None))
            return rows
        for r in reader:
            a = r.get(artist_col) or ""
            t = r.get(title_col) or ""
            d: Optional[float] = None
            if dur_col is not None:
                tmp = parse_duration(str(r.get(dur_col) or ""))
                d = float(tmp) if tmp is not None else None
            b: Optional[float] = None
            if bpm_col is not None:
                b = _extract_bpm(str(r.get(bpm_col) or ""))
            k: Optional[str] = None
            if key_col is not None:
                k = _extract_key(str(r.get(key_col) or ""))
            if a.strip() and t.strip():
                rows.append(TrackRow(artist=a, title=t, duration=d, bpm=b, musical_key=k))
    return rows


def infer_playlist_name(csv_path: Path) -> str:
    name = csv_path.stem
    # Convert underscores to spaces early so we can reliably strip markers
    name = name.replace("_", " ")
    # Remove any 'annotated' marker regardless of separators/case (e.g., ' - Annotated', ' annotated', '_annotated')
    name = re.sub(r"(?i)(?:^|[\s\-])annotated(?:$|[\s\-])", " ", name)
    # Normalize multiple spaces
    name = re.sub(r"\s+", " ", name)
    return name.strip()


def find_compiled_playlists(outputs_dir: Path) -> List[Path]:
    candidates: List[Path] = []
    # Prefer latest Archive Transfer lists
    archive = outputs_dir / "Archive"
    if archive.exists():
        for p in archive.glob("**/Transfer/*.csv"):
            candidates.append(p)
    # Also include any current Transfer lists
    current = outputs_dir / "Transfer"
    for p in current.glob("**/*.csv"):
        candidates.append(p)

    # Filter: only annotated lists with minimal columns (artist, title, bpm, key)
    def _is_annotated(path: Path) -> bool:
        return "annotated" in path.stem.lower() or "annotated" in path.name.lower()

    def _has_min_columns(path: Path) -> bool:
        try:
            with open(path, newline="", encoding="utf-8") as f:
                reader = csv.reader(f)
                header = next(reader, [])
            hdr = [h.strip() for h in header]
            # build case-insensitive set
            lower = {h.lower() for h in hdr}

            def has_any(options: List[str]) -> bool:
                return any(opt.lower() in lower for opt in options)
            artist_ok = has_any(["artist", "ARTIST"])  # case-insensitive anyway
            title_ok = has_any(["title", "TITLE"])
            bpm_ok = has_any(["bpm", "tempo"])
            key_ok = has_any(["key", "musical key"])
            return artist_ok and title_ok and bpm_ok and key_ok
        except Exception:
            return False

    filtered_annotated: List[Path] = [p for p in candidates if _is_annotated(p) and _has_min_columns(p)]
    if filtered_annotated:
        # De-duplicate by path string and sort by mtime desc
        uniq = {str(p): p for p in filtered_annotated}
        return sorted(uniq.values(), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)

    # Fallback: accept non-annotated Transfer CSVs that at least have Artist and Title
    def _has_artist_title(path: Path) -> bool:
        try:
            with open(path, newline="", encoding="utf-8") as f:
                reader = csv.reader(f)
                header = next(reader, [])
            lower = {str(h).strip().lower() for h in header}
            return ("artist" in lower) and ("title" in lower)
        except Exception:
            return False

    filtered_relaxed: List[Path] = [p for p in candidates if _has_artist_title(p)]
    uniq2 = {str(p): p for p in filtered_relaxed}
    return sorted(uniq2.values(), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)


# -----------------------------
# Exporters
# -----------------------------

def build_generic_netsearch_uri(row: TrackRow) -> str:
    """Build a generic netsearch URI based on artist/title (experimental)."""
    # VirtualDJ expects the form: search://Artist/Title/
    # Keep spaces as-is; VDJ handles them. Include trailing slash per examples.
    artist = (row.artist or "").strip()
    title = (row.title or "").strip()
    return f"search://{artist}/{title}/"


def export_vdjfolder(
    list_name: str,
    matches: List[MatchResult],
    vdj_mylist_dir: Path,
    use_generic_netsearch: bool = False,
) -> Path:
    vdj_mylist_dir.mkdir(parents=True, exist_ok=True)
    # Keep file name simple, allow spaces
    out = vdj_mylist_dir / f"{list_name}.vdjfolder"
    lines = ["<VirtualFolder>"]
    for m in matches:
        if m.local_path:
            lines.append(f'  <song path="{_escape_xml_attr(str(m.local_path))}" />')
        elif m.tidal_id:
            lines.append(f'  <song path="{_escape_xml_attr(f"netsearch://{m.tidal_id}")}" />')
        else:
            if use_generic_netsearch:
                uri = build_generic_netsearch_uri(m.row)
                lines.append(f'  <song path="{_escape_xml_attr(uri)}" />')
            else:
                # skip missing
                continue
    lines.append("</VirtualFolder>")
    content = "\n".join(lines) + "\n"
    out.write_text(content, encoding="utf-8")
    return out


def export_m3u8(list_name: str, matches: List[MatchResult], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{list_name}.m3u8"
    lines = ["#EXTM3U"]
    for m in matches:
        if not m.local_path:
            continue
        lines.append(f"#EXTINF:-1,{m.row.artist} - {m.row.title}")
        lines.append(str(m.local_path))
    content = "\n".join(lines) + "\n"
    out.write_text(content, encoding="utf-8")
    return out


# -----------------------------
# Orchestration helpers
# -----------------------------

def resolve_matches_for_csv(
    csv_path: Path,
    library_index: dict,
    tidal_index: Dict[str, str],
    threshold: int = 85,
    vdj_meta_index: Optional[Dict[str, Dict[str, Optional[str]]]] = None,
) -> List[MatchResult]:
    rows = read_playlist_csv(csv_path)
    try:
        enrich_rows_with_meta(rows, library_index, vdj_meta_index or {})
    except Exception:
        pass
    matched = match_playlist_rows(rows, library_index, threshold=threshold)
    results: List[MatchResult] = []
    for row, lpath, score in matched:
        tid = None
        if not lpath:
            tid = tidal_index.get(row.key())
        results.append(MatchResult(row=row, local_path=lpath, confidence=score, tidal_id=tid))
    return results


def enrich_rows_with_meta(
    rows: List[TrackRow],
    library_index: dict,
    vdj_meta_index: Dict[str, Dict[str, Optional[str]]],
) -> None:
    """Fill missing row.bpm and row.musical_key using VDJ DB and library tag metadata.

    - Prefer VDJ DB values when available for the normalized (artist - title) key.
    - If still missing, and the library has one or more local files under the same normalized key,
      copy the first track's tag_bpm/tag_key.
    """
    by_key = library_index.get("by_key", {})
    tracks_meta = library_index.get("tracks", {})
    for r in rows:
        k = r.key()
        if (r.bpm is None) and (k in vdj_meta_index):
            vbpm = vdj_meta_index[k].get("bpm")
            try:
                r.bpm = float(vbpm) if vbpm is not None else None
            except Exception:
                pass
        if (not r.musical_key) and (k in vdj_meta_index):
            vkey = vdj_meta_index[k].get("key")
            if vkey:
                r.musical_key = str(vkey)
        if (r.bpm is None) or (not r.musical_key):
            lib_paths = by_key.get(k, [])
            if lib_paths:
                meta = tracks_meta.get(lib_paths[0], {})
                if r.bpm is None:
                    tb = meta.get("tag_bpm")
                    try:
                        r.bpm = float(tb) if tb is not None else None
                    except Exception:
                        pass
                if not r.musical_key:
                    tk = meta.get("tag_key")
                    if tk:
                        r.musical_key = str(tk)
