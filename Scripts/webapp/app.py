from __future__ import annotations

import json
import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import streamlit as st
import io
import zipfile
import playlist_lib as pl
try:
    from streamlit_autorefresh import st_autorefresh  # type: ignore
except Exception:
    st_autorefresh = None  # type: ignore

# --------------------------------------------------------------------------------------
# Paths and constants
# --------------------------------------------------------------------------------------
# This file lives at: <PROJECT_ROOT>/Scripts/webapp/app.py
# We want base_dir = <PROJECT_ROOT> (the "Radio Filter" directory)
BASE_DIR = Path(__file__).resolve().parents[2]
OUTPUTS_DIR = BASE_DIR / "Outputs"
STATIONS_DIR = OUTPUTS_DIR / "Stations"
STATUS_PATH = OUTPUTS_DIR / "Status" / "last_update.json"
LOGS_DIR = BASE_DIR / "Logs"
WRAPPER_PATH = BASE_DIR / "Scripts" / "run_radio_update.sh"
LOCK_PATH = LOGS_DIR / ".update.lock"

# Defaults for DJ integration (configurable in UI)
LIBRARY_ROOT_DEFAULT = Path("/Users/gigwebs/Music/DJ Collection")
LIB_INDEX_JSON = OUTPUTS_DIR / "Cache" / "library_index.json"
VDJ_DB_PATH_DEFAULT = Path("/Users/gigwebs/Library/Application Support/VirtualDJ/database.xml")
VDJ_MYLIST_DIR_DEFAULT = Path("/Users/gigwebs/Library/Application Support/VirtualDJ/MyLists")
M3U_OUT_DIR_DEFAULT = OUTPUTS_DIR / "Playlists"

NO_PLAYLIST_MARKER = "NoPlaylist"


# --------------------------------------------------------------------------------------
# Utilities
# --------------------------------------------------------------------------------------


def load_status() -> Optional[dict]:
    try:
        with open(STATUS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except Exception as e:
        st.error(f"Failed to read status: {e}")
        return None


def list_latest_logs(limit: int = 10) -> List[Path]:
    if not LOGS_DIR.exists():
        return []
    logs = sorted(LOGS_DIR.glob("auto_update_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    return logs[:limit]


def safe_read(path: Path, max_bytes: int = 200_000) -> str:
    try:
        with open(path, "rb") as f:
            data = f.read(max_bytes)
        # If file is larger than max_bytes, indicate truncation
        suffix = b"\n\n-- (truncated) --\n" if path.stat().st_size > max_bytes else b""
        return (data + suffix).decode("utf-8", errors="replace")
    except Exception as e:
        return f"<error reading {path}: {e}>"


def list_transfer_files(date_str: Optional[str]) -> List[Path]:
    """Return transfer files for the given date, or a recent fallback.

    Prefers files matching "*Radio_New*_{date_str}*" under
    Outputs/Transfer/Radio. Falls back to the most recent Radio_New files.
    """
    base = OUTPUTS_DIR / "Transfer" / "Radio"
    results: List[Path] = []
    try:
        if not base.exists():
            return results
        if date_str:
            matches = list(base.glob(f"*Radio_New*_{date_str}*"))
            if matches:
                return sorted(matches, key=lambda p: p.name)
        # Fallback: most recent Radio_New files (up to 6)
        matches = sorted(
            base.glob("*Radio_New*"), key=lambda p: p.stat().st_mtime, reverse=True
        )
        return matches[:6]
    except Exception:
        return results


def build_zip_bytes(paths: List[Path]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in paths:
            try:
                zf.write(p, arcname=p.name)
            except Exception:
                # Skip unreadable files
                pass
    return buf.getvalue()


def next_scheduled_run(now: datetime) -> datetime:
    """Return next Tue/Fri at 09:30 local time from 'now'."""
    target_weekdays = {1, 4}  # Tue=1, Fri=4 (Python: Monday=0)
    target_hour = 9
    target_minute = 30
    candidates = []
    for d in target_weekdays:
        delta = (d - now.weekday()) % 7
        cand = (now + timedelta(days=delta)).replace(
            hour=target_hour, minute=target_minute, second=0, microsecond=0
        )
        if cand <= now:
            cand = cand + timedelta(days=7)
        candidates.append(cand)
    return min(candidates)


def stations_from_status(status: dict) -> pd.DataFrame:
    completed = status.get("stations_completed", [])
    partial = status.get("stations_partial", [])
    missing = status.get("stations_missing", [])
    no_playlist = status.get("stations_no_playlist", [])

    rows = []
    for s in completed:
        rows.append({"station": s, "status": "completed"})
    for s in partial:
        rows.append({"station": s, "status": "partial"})
    for s in missing:
        rows.append({"station": s, "status": "missing"})
    for s in no_playlist:
        rows.append({"station": s, "status": "no_playlist"})

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["status", "station"]).reset_index(drop=True)
    return df


def status_counts_df(status: dict) -> pd.DataFrame:
    counts = {
        "completed": len(status.get("stations_completed", [])),
        "partial": len(status.get("stations_partial", [])),
        "missing": len(status.get("stations_missing", [])),
        "no_playlist": len(status.get("stations_no_playlist", [])),
    }
    return pd.DataFrame({"status": list(counts.keys()), "count": list(counts.values())})


def preview_csv_file(path: Path, nrows: int = 20) -> Optional[pd.DataFrame]:
    try:
        return pd.read_csv(path).head(nrows)
    except Exception:
        try:
            return pd.read_csv(path, engine="python").head(nrows)
        except Exception:
            return None


def file_info(path: Path) -> str:
    try:
        stime = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        size = path.stat().st_size
        return f"{path.name} — {size} bytes — {stime}"
    except Exception:
        return path.name


def latest_station_files(station: str) -> Dict[str, List[Path]]:
    """Return recent files for a station grouped by category.

    Looks for:
    - Raw playlist CSVs: *_Raw_Playlist_past_7_days_*.csv
    - Titles CSVs: *_Danish_Titles_past_7_days_*.csv and *_English_Titles_past_7_days_*.csv
    - NoPlaylist markers: *_NoPlaylist_past_7_days_*.json
    """
    base = STATIONS_DIR / station
    results: Dict[str, List[Path]] = {
        "raw": [],
        "danish_titles": [],
        "english_titles": [],
        "no_playlist_markers": [],
    }
    if not base.exists():
        return results

    # Raw
    raw_dir = base / "Raw"
    if raw_dir.exists():
        results["raw"] = sorted(
            raw_dir.glob(f"{station}_Raw_Playlist_past_7_days_*.csv"),
            key=lambda p: p.name,
            reverse=True,
        )
        results["no_playlist_markers"] = sorted(
            raw_dir.glob(f"{station}_{NO_PLAYLIST_MARKER}_past_7_days_*.json"),
            key=lambda p: p.name,
            reverse=True,
        )

    # Danish
    danish_dir = base / "Danish"
    if danish_dir.exists():
        results["danish_titles"] = sorted(
            danish_dir.glob(f"{station}_Danish_Titles_past_7_days_*.csv"),
            key=lambda p: p.name,
            reverse=True,
        )

    # English
    english_dir = base / "English"
    if english_dir.exists():
        results["english_titles"] = sorted(
            english_dir.glob(f"{station}_English_Titles_past_7_days_*.csv"),
            key=lambda p: p.name,
            reverse=True,
        )

    return results


@dataclass
class RunConfig:
    force: bool = False
    extract_log_level: str = "INFO"
    notify_email: str = ""


def run_orchestrator(cfg: RunConfig) -> subprocess.Popen | None:
    """Kick off the orchestrator via the venv-aware wrapper.
    Uses a lock file to avoid concurrent runs. Returns the Popen object if started.
    """
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        if LOCK_PATH.exists():
            st.warning("A run appears to be in progress (lock file present).")
            return None
        # Create lock file
        LOCK_PATH.write_text(f"started: {datetime.now().isoformat()}\n")

        args = [str(WRAPPER_PATH), "--extract-log-level", cfg.extract_log_level]
        if cfg.force:
            args.append("--force")
        if cfg.notify_email:
            args.extend(["--notify-email", cfg.notify_email])

        # Start process detached so it survives app reloads
        proc = subprocess.Popen(args, cwd=str(BASE_DIR))

        def _cleanup_on_exit(p: subprocess.Popen):
            p.wait()
            # Remove lock when done
            if LOCK_PATH.exists():
                try:
                    LOCK_PATH.unlink()
                except Exception:
                    pass

        threading.Thread(target=_cleanup_on_exit, args=(proc,), daemon=True).start()
        return proc
    except Exception as e:
        # Ensure lock removed on failure
        if LOCK_PATH.exists():
            try:
                LOCK_PATH.unlink()
            except Exception:
                pass
        st.error(f"Failed to start orchestrator: {e}")
        return None


# --------------------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------------------

st.set_page_config(page_title="Radio Explorer", page_icon="📻", layout="wide")

st.title("📻 Danish Radio Explorer")
with st.sidebar:
    st.markdown("**Project root**")
    st.code(str(BASE_DIR))
    st.markdown("**Outputs**")
    st.code(str(OUTPUTS_DIR))
    st.markdown("**Logs**")
    st.code(str(LOGS_DIR))
    st.markdown("**Auto-refresh**")
    auto_status = st.checkbox("Status", value=False, key="auto_status")
    auto_logs = st.checkbox("Logs", value=False, key="auto_logs")
    interval = st.slider(
        "Interval (sec)", min_value=5, max_value=120, value=30, step=5, key="auto_interval"
    )
    if st_autorefresh is None and (auto_status or auto_logs):
        st.info("Auto-refresh helper will be installed automatically.")

status = load_status()

# Global auto-refresh (refreshes entire page)
if st_autorefresh and (auto_status or auto_logs):
    st_autorefresh(interval=interval * 1000, key="auto_refresh_tick")

# Top KPIs
col1, col2, col3, col4, col5 = st.columns(5)
if status:
    total = status.get("stations_total", 0)
    c = len(status.get("stations_completed", []))
    p = len(status.get("stations_partial", []))
    m = len(status.get("stations_missing", []))
    n = len(status.get("stations_no_playlist", []))

    with col1:
        st.metric("Stations (total)", total)
    with col2:
        st.metric("Completed", c)
    with col3:
        st.metric("Partial", p)
    with col4:
        st.metric("Missing", m)
    with col5:
        st.metric("No playlist", n)

    # Staleness check and caption
    gen_text = status.get("generated_at", "-")
    gen_dt = None
    try:
        if gen_text and gen_text != "-":
            gen_dt = datetime.strptime(gen_text, "%Y-%m-%d %H:%M:%S")
    except Exception:
        gen_dt = None

    if gen_dt is not None:
        age = datetime.now() - gen_dt
        if age.days >= 3:
            st.error(f"Status is stale: generated {age.days} days ago")
        elif age.days >= 1:
            st.warning(f"Status is {age.days} day(s) old")

    st.caption(
        f"Date: {status.get('date', '-')}, "
        f"Generated: {gen_text}, "
        f"Log: {status.get('log_file', '-')}"
    )

    ctrl1, ctrl2 = st.columns([1, 2])
    with ctrl1:
        if st.button("Reload status"):
            st.rerun()
    with ctrl2:
        try:
            st.download_button(
                label="Download status.json",
                data=STATUS_PATH.read_bytes(),
                file_name="last_update.json",
                mime="application/json",
                key="dl_status_json",
            )
        except Exception:
            pass

    nxt = next_scheduled_run(datetime.now())
    st.caption(f"Next scheduled run: {nxt.strftime('%Y-%m-%d %H:%M')} (local)")

    # Status breakdown chart
    st.subheader("Status breakdown")
    try:
        chart_df = status_counts_df(status)
        st.bar_chart(chart_df.set_index("status"))
    except Exception:
        pass
else:
    st.warning("Status file not found. Run the orchestrator to generate outputs.")

st.divider()

# Station overview table
st.subheader("Station status")
if status:
    df = stations_from_status(status)
    if df.empty:
        st.info("No stations reported in status.")
    else:
        filt_col, reset_col = st.columns([4, 1])
        with filt_col:
            selected = st.multiselect(
                "Filter by status",
                options=sorted(df["status"].unique()),
                default=[],
                key="status_filter",
            )
        with reset_col:
            if st.button("Reset", key="reset_status_filter"):
                st.session_state["status_filter"] = []
                st.rerun()

        filt = selected
        view = df if not filt else df[df["status"].isin(filt)].reset_index(drop=True)
        st.dataframe(view, use_container_width=True, hide_index=True)

        # Select a single station to inspect
        st.subheader("Station drilldown")
        station = st.selectbox("Choose a station", options=df["station"].tolist())
        files = latest_station_files(station)
        cols = st.columns(3)
        with cols[0]:
            st.markdown("**Raw playlist CSVs**")
            if files["raw"]:
                for p in files["raw"][:3]:
                    st.download_button(
                        label=p.name,
                        data=p.read_bytes(),
                        file_name=p.name,
                        mime="text/csv",
                        key=f"dl_raw_{p.name}",
                    )
            else:
                st.write("—")
        with cols[1]:
            st.markdown("**Danish titles CSVs**")
            if files["danish_titles"]:
                for p in files["danish_titles"][:3]:
                    st.download_button(
                        label=p.name,
                        data=p.read_bytes(),
                        file_name=p.name,
                        mime="text/csv",
                        key=f"dl_da_{p.name}",
                    )
            else:
                st.write("—")
        with cols[2]:
            st.markdown("**English titles CSVs**")
            if files["english_titles"]:
                for p in files["english_titles"][:3]:
                    st.download_button(
                        label=p.name,
                        data=p.read_bytes(),
                        file_name=p.name,
                        mime="text/csv",
                        key=f"dl_en_{p.name}",
                    )
            else:
                st.write("—")

        if files["no_playlist_markers"]:
            with st.expander("No‑playlist markers"):
                for p in files["no_playlist_markers"][:3]:
                    st.code(safe_read(p, max_bytes=50_000), language="json")

        # Previews
        with st.expander("Preview latest files"):
            p_raw = files["raw"][0] if files["raw"] else None
            p_da = files["danish_titles"][0] if files["danish_titles"] else None
            p_en = files["english_titles"][0] if files["english_titles"] else None

            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown("**Raw (latest)**")
                if p_raw:
                    st.caption(file_info(p_raw))
                    df_raw = preview_csv_file(p_raw)
                    if df_raw is not None and not df_raw.empty:
                        st.dataframe(df_raw, use_container_width=True, hide_index=True)
                    else:
                        st.write("(preview unavailable)")
                else:
                    st.write("—")
            with c2:
                st.markdown("**Danish (latest)**")
                if p_da:
                    st.caption(file_info(p_da))
                    df_da = preview_csv_file(p_da)
                    if df_da is not None and not df_da.empty:
                        st.dataframe(df_da, use_container_width=True, hide_index=True)
                    else:
                        st.write("(preview unavailable)")
                else:
                    st.write("—")
            with c3:
                st.markdown("**English (latest)**")
                if p_en:
                    st.caption(file_info(p_en))
                    df_en = preview_csv_file(p_en)
                    if df_en is not None and not df_en.empty:
                        st.dataframe(df_en, use_container_width=True, hide_index=True)
                    else:
                        st.write("(preview unavailable)")
                else:
                    st.write("—")

    # Transfer bundle download
    st.subheader("Transfer bundle")
    if status:
        date_str = status.get("date")
        bundle_files = list_transfer_files(date_str)
        if bundle_files:
            try:
                zip_bytes = build_zip_bytes(bundle_files)
                st.download_button(
                    label=f"Download transfer bundle ({len(bundle_files)} files)",
                    data=zip_bytes,
                    file_name=f"radio_transfer_{date_str or 'latest'}.zip",
                    mime="application/zip",
                    key="dl_transfer_zip",
                )
                with st.expander("Files in bundle"):
                    for p in bundle_files:
                        st.write(p.name)
            except Exception as e:
                st.warning(f"Unable to create transfer bundle: {e}")
        else:
            st.info("No transfer files found for the latest date.")
    else:
        st.info("Status not loaded; cannot determine latest transfer files.")

st.divider()

# Run Now section
st.subheader("Run now")
run_col1, run_col2, run_col3 = st.columns([1, 1, 2])
with run_col1:
    force = st.checkbox("Force run (ignore Tue/Fri gating)", value=False)
with run_col2:
    notify = st.text_input("Notify email (optional)", value="")
with run_col3:
    level = st.selectbox("Log level", options=["DEBUG", "INFO", "WARNING", "ERROR"], index=1)

btn = st.button("Start orchestrator", type="primary", disabled=LOCK_PATH.exists() or not WRAPPER_PATH.exists())
if btn:
    proc = run_orchestrator(RunConfig(force=force, extract_log_level=level, notify_email=notify))
    if proc is not None:
        st.success("Orchestrator started. A lock file prevents overlaps; it will clear when done.")

# Log viewer
st.subheader("Logs")
log_file_from_status = Path(status["log_file"]) if status and status.get("log_file") else None
available_logs = list_latest_logs(limit=20)

pref_list = [log_file_from_status] if log_file_from_status else []
log_candidates = pref_list + available_logs
log_options = [str(p) for p in log_candidates]

log_choice = st.selectbox("Choose a log file", options=log_options)

if log_choice:
    path = Path(log_choice)
    st.caption(f"Showing: {path}")

    lc1, lc2, lc3 = st.columns([1, 2, 1])
    with lc1:
        tail_n = st.slider("Last N lines", min_value=100, max_value=5000, value=800, step=100, key="tail_n")
    with lc2:
        filt_text = st.text_input("Filter (substring)", value="", key="log_filter")
    with lc3:
        ci = st.checkbox("Ignore case", value=True, key="log_ci")

    text = safe_read(path)
    lines = text.splitlines()
    if filt_text:
        if ci:
            q = filt_text.lower()
            lines = [ln for ln in lines if q in ln.lower()]
        else:
            lines = [ln for ln in lines if filt_text in ln]
    if tail_n and tail_n > 0:
        lines = lines[-tail_n:]
    display_text = "\n".join(lines) if lines else "(no matching lines)"
    st.code(display_text, language="log")

    r1, r2 = st.columns([1, 1])
    with r1:
        if st.button("Refresh log view"):
            st.rerun()
    with r2:
        if st.button("Reset log filter"):
            st.session_state["log_filter"] = ""
            st.rerun()

    st.divider()
    # ----------------------------------------------------------------------------------
    # Playlists (beta): Local matching, VDJ auto-export, on-demand M3U export
    # ----------------------------------------------------------------------------------
    st.subheader("Playlists (beta)")
    with st.expander("DJ integration settings"):
        c1, c2 = st.columns(2)
        with c1:
            lib_root_str = st.text_input(
                "Local library root",
                value=str(LIBRARY_ROOT_DEFAULT),
                key="lib_root",
                help="Root folder that contains your local music files",
            )
            vdj_db_str = st.text_input(
                "VirtualDJ database.xml",
                value=str(VDJ_DB_PATH_DEFAULT),
                key="vdj_db_path",
            )
        with c2:
            vdj_mylist_str = st.text_input(
                "VirtualDJ MyLists folder",
                value=str(VDJ_MYLIST_DIR_DEFAULT),
                key="vdj_mylist_dir",
            )
            m3u_out_str = st.text_input(
                "M3U output folder",
                value=str(M3U_OUT_DIR_DEFAULT),
                key="m3u_out_dir",
            )
        b1, b2, b3 = st.columns([1, 1, 2])
        with b1:
            if st.button("Rescan library", key="btn_rescan_lib"):
                with st.spinner("Scanning local library (mutagen)..."):
                    LIB_INDEX_JSON.parent.mkdir(parents=True, exist_ok=True)
                    existing = pl.load_index(Path(LIB_INDEX_JSON))
                    new_index = pl.scan_library(Path(lib_root_str), existing_index=existing)
                    pl.save_index(Path(LIB_INDEX_JSON), new_index)
                st.success("Library index updated.")
                st.rerun()
        with b2:
            if st.button("Open MyLists in Finder", key="btn_open_mylists"):
                try:
                    subprocess.Popen(["open", vdj_mylist_str])
                except Exception:
                    pass
        with b3:
            if st.button("Open M3U folder", key="btn_open_m3u"):
                try:
                    subprocess.Popen(["open", m3u_out_str])
                except Exception:
                    pass

    # Discover compiled playlists
    compiled_csvs = pl.find_compiled_playlists(OUTPUTS_DIR)
    if not compiled_csvs:
        st.info("No compiled playlists found under Outputs/. Run the orchestrator first.")
    else:
        # Selection and controls
        names = [pl.infer_playlist_name(p) for p in compiled_csvs]
        sel_name = st.selectbox("Choose a compiled playlist", options=names, index=0, key="pl_select")
        sel_idx = names.index(sel_name)
        sel_csv = compiled_csvs[sel_idx]
        st.caption(f"Using CSV: {sel_csv}")

        # Load library index and TIDAL index from VDJ db
        lib_index = pl.load_index(Path(LIB_INDEX_JSON))
        if not lib_index.get("tracks"):
            st.warning("Library index is empty. Click 'Rescan library' above to build it.")
        tidal_index = pl.build_tidal_index_from_vdj_db(Path(vdj_db_str))

        # Matching
        threshold = st.slider(
            "Fuzzy match threshold",
            min_value=70,
            max_value=100,
            value=88,
            step=1,
            key="match_thresh",
        )
        matches = pl.resolve_matches_for_csv(sel_csv, lib_index, tidal_index, threshold=threshold)
        total = len(matches)
        local_count = sum(1 for m in matches if m.local_path)
        tidal_count = sum(1 for m in matches if (not m.local_path) and m.tidal_id)
        missing_count = total - local_count - tidal_count
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Tracks", total)
        with c2:
            st.metric("Local matched", local_count)
        with c3:
            st.metric("TIDAL linked", tidal_count)
        with c4:
            st.metric("Missing", missing_count)

        # Show preview table
        if total:
            def _mmss(v: Optional[float]) -> str:
                try:
                    if v is None:
                        return ""
                    v = float(v)
                    m = int(v // 60)
                    s = int(round(v % 60))
                    return f"{m}:{s:02d}"
                except Exception:
                    return ""

            view_rows = []
            for m in matches[:300]:  # cap preview
                local_dur = None
                if m.local_path:
                    meta = lib_index.get("tracks", {}).get(str(m.local_path), {})
                    local_dur = meta.get("duration")
                bpm_raw = getattr(m.row, "bpm", None)
                key_raw = getattr(m.row, "musical_key", None)
                view_rows.append({
                    "Artist": m.row.artist,
                    "Title": m.row.title,
                    "BPM": (round(bpm_raw, 1) if isinstance(bpm_raw, (int, float)) else (bpm_raw or "")),
                    "Key": (key_raw or ""),
                    "CSV Dur": _mmss(m.row.duration),
                    "Local Dur": _mmss(local_dur),
                    "Local": str(m.local_path) if m.local_path else "",
                    "Confidence": round(m.confidence, 1),
                    "TIDAL": f"netsearch://{m.tidal_id}" if m.tidal_id else "",
                })
            st.dataframe(pd.DataFrame(view_rows), use_container_width=True, hide_index=True)

        # Auto-export VDJ folder on compute
        auto_vdj = st.checkbox("Auto-export VirtualDJ list to MyLists", value=True, key="auto_vdj")
        use_generic_net = st.checkbox(
            "Use generic netsearch fallback for missing (experimental)", value=True, key="use_generic_net"
        )
        list_name = sel_name
        if auto_vdj and total:
            try:
                vdj_out = pl.export_vdjfolder(
                    list_name, matches, Path(vdj_mylist_str), use_generic_netsearch=use_generic_net
                )
                st.success(f"VDJ list written: {vdj_out}")
            except Exception as e:
                st.warning(f"Failed to write VDJ list: {e}")

        # On-demand M3U export
        m3u_col1, m3u_col2 = st.columns([1, 3])
        with m3u_col1:
            if st.button("Export M3U8 now", key="btn_export_m3u"):
                try:
                    m3u_out = pl.export_m3u8(list_name, matches, Path(m3u_out_str))
                    st.success(f"M3U8 exported: {m3u_out}")
                except Exception as e:
                    st.warning(f"Failed to export M3U8: {e}")

    st.caption("Tip: Use the Run now button sparingly. The LaunchAgent will run on Tuesday and Friday at 09:30.")
