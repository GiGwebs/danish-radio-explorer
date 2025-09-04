from __future__ import annotations

import json
import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import streamlit as st

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

status = load_status()

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
            st.experimental_rerun()
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
        filt = st.multiselect("Filter by status", options=sorted(df["status"].unique()), default=[])
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
    st.code(safe_read(path), language="log")
    if st.button("Refresh log view"):
        st.experimental_rerun()

st.divider()

st.caption("Tip: Use the Run now button sparingly. The LaunchAgent will run on Tuesday and Friday at 09:30.")
