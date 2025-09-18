from __future__ import annotations

from pathlib import Path
from typing import List, Optional
import subprocess
import sys
from itertools import groupby
import re
import importlib
import json
import threading
from datetime import datetime

import pandas as pd
import streamlit as st

# Use full-width layout so the 3-pane UI has room
try:
    st.set_page_config(layout="wide")
except Exception:
    # In multi-page apps, set_page_config may have been called already in main app.py
    pass

# Initialize persistent UI/session defaults
if "dj_status_filter" not in st.session_state:
    st.session_state["dj_status_filter"] = "All"
if "dj_page_title" not in st.session_state:
    st.session_state["dj_page_title"] = "Radio Playlist Orchestrator"
if "dj_minimal_ui" not in st.session_state:
    st.session_state["dj_minimal_ui"] = True
if "dj_compact_metrics" not in st.session_state:
    st.session_state["dj_compact_metrics"] = True

# Hide Streamlit chrome (Deploy/menu/toolbars) if minimal UI enabled
if st.session_state.get("dj_minimal_ui"):
    st.markdown(
        """
        <style>
        .stDeployButton {display: none !important;}
        div[data-testid="stToolbar"] {display: none !important;}
        #MainMenu {visibility: hidden !important;}
        footer {visibility: hidden !important;}
        </style>
        """,
        unsafe_allow_html=True,
    )

# Make parent webapp directory importable when running this page directly
PAGES_DIR = Path(__file__).resolve().parent
WEBAPP_DIR = PAGES_DIR.parent
if str(WEBAPP_DIR) not in sys.path:
    sys.path.insert(0, str(WEBAPP_DIR))

import playlist_lib as pl  # noqa: E402
# Ensure changes in playlist_lib are picked up during hot-reload development
pl = importlib.reload(pl)  # type: ignore

# Optional rich table
try:
    from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, JsCode  # type: ignore
    AGGRID_AVAILABLE = True
except Exception:
    AGGRID_AVAILABLE = False

# --------------------------------------------------------------------------------------
# Paths and constants (kept local to avoid coupling to app.py UI)
# --------------------------------------------------------------------------------------
# This page lives at: <PROJECT_ROOT>/Scripts/webapp/pages/DJ_Studio.py
BASE_DIR = Path(__file__).resolve().parents[3]
OUTPUTS_DIR = BASE_DIR / "Outputs"
LIB_INDEX_JSON = OUTPUTS_DIR / "Cache" / "library_index.json"
LOGS_DIR = BASE_DIR / "Logs"
WRAPPER_PATH = BASE_DIR / "Scripts" / "run_radio_update.sh"
LOCK_PATH = LOGS_DIR / ".update.lock"

# Persisted preferences file
SETTINGS_PATH = OUTPUTS_DIR / "Cache" / "dj_prefs.json"

VDJ_DB_PATH_DEFAULT = Path("/Users/gigwebs/Library/Application Support/VirtualDJ/database.xml")
VDJ_MYLIST_DIR_DEFAULT = Path("/Users/gigwebs/Library/Application Support/VirtualDJ/MyLists")
M3U_OUT_DIR_DEFAULT = OUTPUTS_DIR / "Playlists"
LIBRARY_ROOT_DEFAULT = Path("/Users/gigwebs/Music/DJ Collection")


# --------------------------------------------------------------------------------------
# Helpers & Preferences persistence
# --------------------------------------------------------------------------------------

PREF_KEYS = [
    "dj_page_title",
    "dj_minimal_ui",
    "dj_compact_metrics",
    "dj_visible_cols",
    "dj_thresh",
    "dj_cumulative",
    "dj_lib_root",
    "dj_lib_root2",
    "dj_vdj_db_path",
    "dj_vdj_mylist_dir",
    "dj_m3u_out_dir",
    "dj_status_filter",
]


def load_prefs() -> None:
    """Load persisted preferences only once per Streamlit session.

    We intentionally override any initial defaults on first load so that
    persisted values win. On subsequent reruns, we DO NOT overwrite values,
    so widget interactions (which update st.session_state prior to script
    execution) are preserved.
    """
    try:
        if st.session_state.get("dj_prefs_loaded"):
            return
        if SETTINGS_PATH.exists():
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for k in PREF_KEYS:
                    if k in data:
                        st.session_state[k] = data[k]
        st.session_state["dj_prefs_loaded"] = True
    except Exception:
        pass


def save_prefs() -> None:
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = {k: st.session_state.get(k) for k in PREF_KEYS}
        SETTINGS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

# Load persisted preferences and enforce always-on minimal UI + compact metrics
load_prefs()
st.session_state["dj_minimal_ui"] = True
st.session_state["dj_compact_metrics"] = True
save_prefs()

# --------------------------------------------------------------------------------------
# Orchestrator trigger (lightweight copy of app.py logic)
# --------------------------------------------------------------------------------------


def run_orchestrator_dj(
    force: bool,
    extract_log_level: str,
    notify_email: str,
) -> Optional[subprocess.Popen]:
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        if LOCK_PATH.exists():
            st.warning("A run appears to be in progress (lock file present).")
            return None
        LOCK_PATH.write_text(f"started: {datetime.now().isoformat()}\n")

        args = [str(WRAPPER_PATH), "--extract-log-level", extract_log_level]
        if force:
            args.append("--force")
        if notify_email:
            args.extend(["--notify-email", notify_email])

        proc = subprocess.Popen(args, cwd=str(BASE_DIR))

        def _cleanup_on_exit(p: subprocess.Popen) -> None:
            try:
                p.wait()
            finally:
                if LOCK_PATH.exists():
                    try:
                        LOCK_PATH.unlink()
                    except Exception:
                        pass

        threading.Thread(target=_cleanup_on_exit, args=(proc,), daemon=True).start()
        return proc
    except Exception as e:
        if LOCK_PATH.exists():
            try:
                LOCK_PATH.unlink()
            except Exception:
                pass
        st.error(f"Failed to start orchestrator: {e}")
        return None

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


def _get_station_urls() -> dict:
    """Return mapping of station name -> playlist URL.

    Prefer importing from radio_playlist_consolidator.STATION_URLS to avoid drift.
    Fallback to a static map when import is unavailable.
    """
    try:
        # Try importing from Scripts dir
        scripts_dir = BASE_DIR / "Scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        import radio_playlist_consolidator as rpc  # type: ignore
        urls = getattr(rpc, "STATION_URLS", None)
        if isinstance(urls, dict) and urls:
            return urls
    except Exception:
        pass
    # Fallback map
    return {
        'NOVA': 'https://onlineradiobox.com/dk/nova/playlist/',
        'P3': 'https://onlineradiobox.com/dk/drp3/playlist/',
        'TheVoice': 'https://onlineradiobox.com/dk/thevoice/playlist/',
        'Radio100': 'https://onlineradiobox.com/dk/radio100/playlist/',
        'PartyFM': 'https://onlineradiobox.com/dk/partyfm/playlist/',
        'RadioGlobus': 'https://onlineradiobox.com/dk/radioglobus/playlist/',
        'SkalaFM': 'https://onlineradiobox.com/dk/skalafm/playlist/',
        'P4': 'https://onlineradiobox.com/dk/drp4kobenhavn/playlist/',
        'PopFM': 'https://onlineradiobox.com/dk/poppremium/playlist/',
        'RBClassics': 'https://onlineradiobox.com/dk/rbclassics/playlist/',
    }


# --------------------------------------------------------------------------------------
# UI: DJ Studio (3-pane)
# --------------------------------------------------------------------------------------

st.title(f"📻 {st.session_state.get('dj_page_title', 'Radio Playlist Orchestrator')}")

with st.expander("Settings", expanded=False):
    c1, c2 = st.columns(2)
    with c1:
        st.text_input(
            "Page title",
            key="dj_page_title",
            help="Rename this page's title to better describe the app",
        )
        lib_root_str = st.text_input(
            "Local library root",
            value=str(LIBRARY_ROOT_DEFAULT),
            key="dj_lib_root",
            help="Root folder that contains your local music files",
        )
        vdj_db_str = st.text_input(
            "VirtualDJ database.xml",
            value=str(VDJ_DB_PATH_DEFAULT),
            key="dj_vdj_db_path",
        )
    with c2:
        lib_root2_str = st.text_input(
            "Secondary library root",
            value=str(Path("/Users/gigwebs/Music/Djay Bank/Song REQUESTS")),
            key="dj_lib_root2",
            help="Additional root to index (recursively)",
        )
        vdj_mylist_str = st.text_input(
            "VirtualDJ MyLists folder",
            value=str(VDJ_MYLIST_DIR_DEFAULT),
            key="dj_vdj_mylist_dir",
        )
        m3u_out_str = st.text_input(
            "M3U output folder",
            value=str(M3U_OUT_DIR_DEFAULT),
            key="dj_m3u_out_dir",
        )
    b1, b2, b3 = st.columns([1, 1, 2])
    with b1:
        if st.button("Rescan library", key="dj_btn_rescan_lib"):
            with st.spinner("Scanning local library (mutagen)..."):
                LIB_INDEX_JSON.parent.mkdir(parents=True, exist_ok=True)
                existing = pl.load_index(Path(LIB_INDEX_JSON))
                new_index = pl.scan_library(Path(lib_root_str), existing_index=existing)
                # Scan secondary root if provided
                try:
                    if lib_root2_str and str(lib_root2_str).strip():
                        p2 = Path(lib_root2_str)
                        if p2.exists():
                            new_index = pl.scan_library(p2, existing_index=new_index)
                except Exception:
                    pass
                pl.save_index(Path(LIB_INDEX_JSON), new_index)
            st.success("Library index updated.")
            st.rerun()
    with b2:
        if st.button("Open MyLists in Finder", key="dj_btn_open_mylists"):
            try:
                subprocess.Popen(["open", vdj_mylist_str])
            except Exception:
                pass
    with b3:
        if st.button("Open M3U folder", key="dj_btn_open_m3u"):
            try:
                subprocess.Popen(["open", m3u_out_str])
            except Exception:
                pass

# Persist preferences after adjusting Settings
save_prefs()

# Columns: Left (browser), Center (tracks), Right (actions/metrics)
left_col, center_col, right_col = st.columns([1.2, 2.8, 1.1])

# Left: Playlist browser
with left_col:
    st.subheader("Playlists")
    search = st.text_input("Search playlists", value=st.session_state.get("dj_search", ""), key="dj_search")

    compiled_csvs = pl.find_compiled_playlists(OUTPUTS_DIR)
    # items: (group, display_name, path, mtime, series_name)
    items: List[tuple] = []
    series_by_path: dict[str, str] = {}
    if compiled_csvs:
        date_pattern = re.compile(
            r"(?:^|[ _-])"
            r"(20\d{2}[._-](?:0[1-9]|1[0-2])[._-](?:0[1-9]|[12]\d|3[01]))"
            r"(?:$|[ _-])"
        )
        for p in compiled_csvs:
            try:
                rel = p.relative_to(OUTPUTS_DIR)
                parts = rel.parts
            except Exception:
                parts = p.parts
            if len(parts) >= 3 and parts[0] == "Archive" and parts[2] == "Transfer":
                group = f"Archive/{parts[1]}/Transfer"
            elif len(parts) >= 1 and parts[0] == "Transfer":
                group = "Transfer"
            else:
                group = str(Path(*parts[:-1])) if len(parts) > 1 else "Other"
            base_name = pl.infer_playlist_name(p)
            # Extra UI guard: aggressively strip any 'annotated' token from labels
            base_display = re.sub(r"(?i)annotated", " ", base_name)
            base_display = re.sub(r"\s+", " ", base_display).strip()
            # Series strips dates from the cleaned base name
            series_name = date_pattern.sub(" ", base_display).replace("_", " ").strip()
            mtime = p.stat().st_mtime if p.exists() else 0
            items.append((group, base_display, p, mtime, series_name))
            series_by_path[str(p)] = series_name or base_display

        # Apply search across series/base/group/filename
        if search:
            s = search.lower()
            items = [it for it in items if (
                s in it[4].lower() or s in it[1].lower() or s in it[2].name.lower() or s in it[0].lower()
            )]

        # Option to show only the latest CSV per series (default True)
        show_latest_only = st.checkbox("Show latest per series", value=True, key="dj_latest_only")
        st.caption(
            "When enabled, only the newest CSV for each series is shown. "
            "Turn off to browse all archive days for each series."
        )
        if show_latest_only:
            # Deduplicate globally by series name, keep the newest across all groups.
            # If mtime ties, prefer the 'annotated' CSV variant.
            latest_by_series_global = {}
            for it in items:
                key_series = it[4]  # series name only
                existing = latest_by_series_global.get(key_series)
                if not existing:
                    latest_by_series_global[key_series] = it
                    continue
                cur_mtime = it[3]
                ex_mtime = existing[3]
                if cur_mtime > ex_mtime:
                    latest_by_series_global[key_series] = it
                elif cur_mtime == ex_mtime:
                    cur_is_ann = ("annotated" in it[2].stem.lower())
                    ex_is_ann = ("annotated" in existing[2].stem.lower())
                    if cur_is_ann and not ex_is_ann:
                        latest_by_series_global[key_series] = it
            items = list(latest_by_series_global.values())

        # Sort by desired group order (Transfer first, then Archive, then others), then recency, then series name
        def _group_priority(g: str) -> int:
            if g == "Transfer":
                return 0
            if g.startswith("Archive/"):
                return 1
            return 2
        items.sort(key=lambda t: (_group_priority(t[0]), t[0], -t[3], t[4].lower()))

    sel_csv = st.session_state.get("dj_sel_csv")
    if not items:
        st.info("No compiled playlists found under Outputs/.")
        sel_csv = None
    else:
        # Build grouped expanders with clickable items to drive selection
        for grp, group_items_iter in groupby(items, key=lambda t: t[0]):
            group_items = list(group_items_iter)
            with st.expander(f"{grp} ({len(group_items)})", expanded=False):
                for _, base_nm, pp, _, series_nm in group_items:
                    is_selected = (str(st.session_state.get("dj_sel_csv")) == str(pp))
                    btn_key = f"dj_sel_btn_{abs(hash(str(pp))) % (10**8)}"
                    if st.button(series_nm or base_nm, key=btn_key, type=("primary" if is_selected else "secondary")):
                        st.session_state["dj_sel_csv"] = pp
                        st.session_state["dj_series_name"] = series_nm or base_nm
                        # Persist current filter selection explicitly
                        st.session_state["dj_status_filter"] = st.session_state.get("dj_status_filter", "All")
                        # Force immediate UI refresh so the selected button highlights right away
                        st.rerun()
        # Fallback: default to the most recent item if nothing selected yet
        if not st.session_state.get("dj_sel_csv") and items:
            most_recent = max(items, key=lambda t: t[3])  # t[3] = mtime
            st.session_state["dj_sel_csv"] = most_recent[2]
            st.session_state["dj_series_name"] = most_recent[4] or most_recent[1]
            sel_csv = most_recent[2]
        else:
            sel_csv = st.session_state.get("dj_sel_csv")
        if sel_csv is not None:
            st.caption(str(sel_csv))

        # View options under Archive/Playlists to save vertical space
        with st.expander("View options", expanded=False):
            # Threshold slider stored in session state
            st.slider(
                "Match threshold",
                min_value=70,
                max_value=100,
                value=int(st.session_state.get("dj_thresh", 88)),
                step=1,
                key="dj_thresh",
                on_change=save_prefs,
            )
            st.checkbox(
                "Cumulative union across series (union of archives)",
                value=bool(st.session_state.get("dj_cumulative", False)),
                key="dj_cumulative",
                on_change=save_prefs,
            )
            # Column chooser
            all_cols = [
                "Artist", "Title", "BPM", "Key", "CSV Dur", "Local Dur",
                "Local", "Confidence", "TIDAL", "Status",
            ]
            if "dj_visible_cols" not in st.session_state:
                st.session_state["dj_visible_cols"] = [
                    "Artist", "Title", "TIDAL", "Status", "Confidence",
                ]
            st.multiselect(
                "Columns",
                all_cols,
                default=st.session_state["dj_visible_cols"],
                key="dj_visible_cols",
                help="Choose which columns to display in the table",
                on_change=save_prefs,
            )

        # Persist user preferences after updating view options
        save_prefs()

# Center: tracks table
with center_col:
    st.subheader("Tracks")

    # Load library & tidal index
    lib_index = pl.load_index(Path(LIB_INDEX_JSON))
    if not lib_index.get("tracks"):
        st.warning("Library index is empty. Use Settings → Rescan library.")
    tidal_index = pl.build_tidal_index_from_vdj_db(Path(vdj_db_str))
    vdj_meta_index = pl.build_vdj_meta_index(Path(vdj_db_str))

    # Read header controls from left pane (session state)
    threshold = int(st.session_state.get("dj_thresh", 88))
    use_cumulative = bool(st.session_state.get("dj_cumulative", False))

    matches: List[pl.MatchResult] = []  # type: ignore
    if sel_csv is not None:
        try:
            if use_cumulative and st.session_state.get("dj_series_name"):
                series_name_cur = st.session_state.get("dj_series_name")
                all_csvs = pl.find_compiled_playlists(OUTPUTS_DIR)
                date_pattern = re.compile(
                    r"(?:^|[ _-])"
                    r"(20\d{2}[._-](?:0[1-9]|1[0-2])[._-](?:0[1-9]|[12]\d|3[01]))"
                    r"(?:$|[ _-])"
                )
                union_map: dict[str, tuple[pl.TrackRow, float]] = {}
                for p in all_csvs:
                    bnm = pl.infer_playlist_name(p)
                    snm = date_pattern.sub(" ", bnm).replace("_", " ").strip()
                    if snm != series_name_cur:
                        continue
                    mtime = p.stat().st_mtime if p.exists() else 0.0
                    for r in pl.read_playlist_csv(p):
                        k = r.key()
                        cur = union_map.get(k)
                        if (cur is None) or (mtime > cur[1]):
                            union_map[k] = (r, mtime)
                union_rows: List[pl.TrackRow] = [t[0] for t in union_map.values()]
                matches = pl.resolve_matches_for_rows(
                    union_rows, lib_index, tidal_index, threshold=threshold, vdj_meta_index=vdj_meta_index
                )
            else:
                matches = pl.resolve_matches_for_csv(
                    sel_csv, lib_index, tidal_index, threshold=threshold, vdj_meta_index=vdj_meta_index
                )
        except Exception as e:
            st.error(f"Failed to resolve matches: {e}")
            matches = []

    if matches:
        rows = []
        for m in matches[:1000]:  # show more here than the main app
            local_dur = None
            meta = {}
            if m.local_path:
                meta = lib_index.get("tracks", {}).get(str(m.local_path), {})
                local_dur = meta.get("duration")
            bpm_raw = getattr(m.row, "bpm", None)
            key_raw = getattr(m.row, "musical_key", None)
            # Fallback to library tag metadata when CSV lacks BPM/Key
            if (bpm_raw is None or bpm_raw == "") and meta:
                bpm_raw = meta.get("tag_bpm")
            if (not key_raw) and meta:
                key_raw = meta.get("tag_key")
            status = (
                "Local" if m.local_path else ("TIDAL" if getattr(m, 'tidal_id', None) else "Missing")
            )
            rows.append({
                "Artist": m.row.artist,
                "Title": m.row.title,
                "BPM": (round(bpm_raw, 1) if isinstance(bpm_raw, (int, float)) else (bpm_raw or "")),
                "Key": (key_raw or ""),
                "CSV Dur": _mmss(m.row.duration),
                "Local Dur": _mmss(local_dur),
                "Local": str(m.local_path) if m.local_path else "",
                "Confidence": round(m.confidence, 1),
                "TIDAL": f"netsearch://{getattr(m, 'tidal_id', '')}" if getattr(m, 'tidal_id', None) else "",
                "Status": status,
            })
        df_full = pd.DataFrame(rows)

        # Apply Status filter from right column (session state)
        status_filter = st.session_state.get("dj_status_filter", "All")
        if status_filter in {"Local", "TIDAL", "Missing"}:
            df_full = df_full[df_full["Status"] == status_filter].reset_index(drop=True)

        selection_local_path: Optional[str] = None
        # Determine visible columns but keep full data for selection and hidden fields
        session_cols = st.session_state.get("dj_visible_cols", [])
        visible_cols = [c for c in session_cols if c in df_full.columns]
        df_view = (df_full[visible_cols] if visible_cols else df_full)

        if AGGRID_AVAILABLE and not df_full.empty:
            try:
                gob = GridOptionsBuilder.from_dataframe(df_full)
                gob.configure_selection("single")
                gob.configure_default_column(resizable=True, filter=True, sortable=True)
                # Column widths and pinning
                widths = {
                    "Artist": 160, "Title": 260, "BPM": 80, "Key": 80,
                    "CSV Dur": 90, "Local Dur": 90, "Local": 420,
                    "Confidence": 110, "TIDAL": 180, "Status": 90,
                }
                for col in df_full.columns:
                    hidden = (visible_cols != []) and (col not in visible_cols)
                    if col in ("Artist", "Title"):
                        gob.configure_column(col, width=widths.get(col, 120), pinned="left", hide=hidden)
                    else:
                        gob.configure_column(col, width=widths.get(col, 120), hide=hidden)

                # Row highlighting based on Status, theme-aware for dark mode
                is_dark = str(st.get_option("theme.base") or "light").lower() == "dark"
                row_style = JsCode(
                    (
                        "function(params) {\n"
                        "  if (!params.data || !params.data.Status) { return {}; }\n"
                        "  const s = params.data.Status;\n"
                        f"  const isDark = {'true' if is_dark else 'false'};\n"
                        "  let bg = null;\n"
                        "  if (s === 'Local') {\n"
                        "    bg = isDark ? 'rgba(76,175,80,0.48)' : '#e8f5e9';\n"
                        "  } else if (s === 'TIDAL') {\n"
                        "    bg = isDark ? 'rgba(33,150,243,0.48)' : '#e3f2fd';\n"
                        "  } else if (s === 'Missing') {\n"
                        "    bg = isDark ? 'rgba(255,152,0,0.40)' : '#fff3e0';\n"
                        "  }\n"
                        "  const color = isDark ? 'rgba(255,255,255,0.94)' : '#111';\n"
                        "  return bg ? { 'backgroundColor': bg, 'color': color } : { 'color': color };\n"
                        "}"
                    )
                )
                gob.configure_grid_options(getRowStyle=row_style)
                grid_options = gob.build()
                # Fix truncated last row by letting grid auto-size vertically
                grid_options["domLayout"] = "autoHeight"
                grid_options["rowHeight"] = 30
                grid = AgGrid(
                    df_full,
                    gridOptions=grid_options,
                    update_mode=GridUpdateMode.SELECTION_CHANGED,
                    theme="streamlit",
                    allow_unsafe_jscode=True,
                    fit_columns_on_grid_load=False,
                    enable_enterprise_modules=False,
                )
                sel = grid.get("selected_rows", [])
                if sel:
                    selection_local_path = sel[0].get("Local") or None
            except Exception:
                st.dataframe(df_view, use_container_width=True, hide_index=True)
        else:
            st.dataframe(df_view, use_container_width=True, hide_index=True)

        if selection_local_path:
            st.caption("Preview selected (local)")
            try:
                with open(selection_local_path, "rb") as f:
                    st.audio(f.read())
            except Exception:
                pass
    else:
        st.write("—")

# Right: metrics and exports
with right_col:
    st.subheader("Actions & Metrics")

    total = len(matches) if 'matches' in locals() else 0
    local_count = (
        sum(1 for m in matches if getattr(m, 'local_path', None))
        if matches else 0
    )
    tidal_count = (
        sum(
            1 for m in matches
            if (not getattr(m, 'local_path', None)) and getattr(m, 'tidal_id', None)
        )
        if matches else 0
    )
    missing_count = (total - local_count - tidal_count) if matches else 0

    # Theme-aware badge colors (high-contrast, non-transparent)
    is_dark_theme = str(st.get_option("theme.base") or "light").lower() == "dark"
    local_bg = "#2e7d32"   # solid green
    tidal_bg = "#1565c0"   # solid blue
    missing_bg = "#ef6c00" # solid orange
    neutral_bg = "#424242" if is_dark_theme else "#e0e0e0"
    text_on_colored = "#ffffff"
    text_on_neutral = "#ffffff" if is_dark_theme else "#111111"
    badge_css = "padding:2px 8px;border-radius:6px;"

    if st.session_state.get("dj_compact_metrics", True):
        # Compact badges row with high-contrast styles
        compact_html = (
            "<div style='display:flex;gap:8px;flex-wrap:wrap;margin-bottom:6px;'>"
            f"<span style='background:{neutral_bg};color:{text_on_neutral};{badge_css}'>Tracks: {total}</span>"
            f"<span style='background:{local_bg};color:{text_on_colored};{badge_css}'>Local: {local_count}</span>"
            f"<span style='background:{tidal_bg};color:{text_on_colored};{badge_css}'>TIDAL: {tidal_count}</span>"
            f"<span style='background:{missing_bg};color:{text_on_colored};{badge_css}'>Missing: {missing_count}</span>"
            "</div>"
        )
        st.markdown(compact_html, unsafe_allow_html=True)
    else:
        m1, m2 = st.columns(2)
        with m1:
            st.metric("Tracks", total)
            st.metric("Local matched", local_count)
        with m2:
            st.metric("TIDAL linked", tidal_count)
            st.metric("Missing", missing_count)

    st.divider()
    # Quick links to source playlists per station
    with st.expander("Station sources", expanded=False):
        try:
            url_map = _get_station_urls()
            if url_map:
                lines = [f"- [{name}]({url})" for name, url in sorted(url_map.items())]
                st.markdown("\n".join(lines))
        except Exception:
            st.caption("No station sources available.")

    # Filter view: show All / Local / TIDAL / Missing
    status_options = ["All", "Local", "TIDAL", "Missing"]
    try:
        sel_status = st.radio("Show", status_options, key="dj_status_filter", horizontal=True)
    except TypeError:
        sel_status = st.radio("Show", status_options, key="dj_status_filter")

    # Persist status filter preference
    save_prefs()

    # Color legend for row highlighting in the tracks grid (match badges)
    legend_html = (
        "<div style='margin: 0.25rem 0 0.75rem 0;'>"
        "<span style='display:inline-block;padding:2px 8px;border-radius:6px;"
        f"background:{local_bg};color:{text_on_colored};margin-right:6px;'>Local</span>"
        "<span style='display:inline-block;padding:2px 8px;border-radius:6px;"
        f"background:{tidal_bg};color:{text_on_colored};margin-right:6px;'>TIDAL</span>"
        "<span style='display:inline-block;padding:2px 8px;border-radius:6px;"
        f"background:{missing_bg};color:{text_on_colored};margin-right:6px;'>Missing</span>"
        "</div>"
    )
    st.markdown(legend_html, unsafe_allow_html=True)

    # Use stable series name (without dates) for deterministic export naming
    list_name = (
        st.session_state.get("dj_series_name")
        or (pl.infer_playlist_name(sel_csv) if sel_csv else "")
    )

    # Prepare filtered matches to respect current status filter in exports
    def _filter_matches(ms: List[pl.MatchResult], status: str) -> List[pl.MatchResult]:
        if status == "Local":
            return [m for m in ms if getattr(m, 'local_path', None)]
        if status == "TIDAL":
            return [m for m in ms if (not getattr(m, 'local_path', None)) and getattr(m, 'tidal_id', None)]
        if status == "Missing":
            return [m for m in ms if (not getattr(m, 'local_path', None)) and (not getattr(m, 'tidal_id', None))]
        return ms

    with st.expander("Export & options", expanded=False):
        use_generic_net = st.checkbox(
            "Use generic netsearch fallback for missing (experimental)",
            value=True,
            key="dj_use_generic_net",
        )

        # Export mode controls shared by both exporters
        mode_label = "Export mode"
        mode_options = [
            "Replace",
            "Add (append new only)",
            "Save as new",
        ]
        export_mode_ui = st.selectbox(mode_label, mode_options, index=0, key="dj_export_mode")
        mode_map = {
            "Replace": "replace",
            "Add (append new only)": "add",
            "Save as new": "save_as_new",
        }
        export_mode = mode_map.get(export_mode_ui, "replace")
        new_list_name: Optional[str] = None
        if export_mode == "save_as_new":
            new_list_name = st.text_input(
                "New list name (for 'Save as new')",
                value=str(list_name),
                key="dj_export_new_name",
            )

        # Target playlist/name selector (Option A)
        # Discover existing targets from VDJ MyLists and M3U output folders
        try:
            vdj_targets = []
            p_vdj = Path(vdj_mylist_str)
            if p_vdj.exists():
                vdj_targets = [p.stem for p in p_vdj.glob("*.vdjfolder")]
        except Exception:
            vdj_targets = []
        try:
            m3u_targets = []
            p_m3u = Path(m3u_out_str)
            if p_m3u.exists():
                m3u_targets = [p.stem for p in p_m3u.glob("*.m3u8")]
        except Exception:
            m3u_targets = []

        # Build unified target options (series name first), de-duplicated
        target_set = {str(list_name)}
        for nm in vdj_targets + m3u_targets:
            if nm and nm.strip():
                target_set.add(nm.strip())
        target_options = [str(list_name)] + sorted(x for x in target_set if x != str(list_name)) + ["Custom…"]
        target_choice = st.selectbox(
            "Target playlist/name (for Replace/Add)", target_options, index=0, key="dj_export_target_choice"
        )
        if target_choice == "Custom…":
            target_name = st.text_input(
                "Custom target name (for Replace/Add)", value=str(list_name), key="dj_export_target_custom"
            ).strip() or str(list_name)
        else:
            target_name = target_choice

        # Hint (Option D)
        st.caption(
            "Tip: Replace/Add export to the selected Target name above. 'Save as new' writes to 'New list name'; "
            "to append later, pick that name as Target."
        )

        cbtn1, cbtn2 = st.columns(2)
        with cbtn1:
            if st.button(
                "Export VirtualDJ (.vdjfolder)", disabled=(not matches), key="dj_btn_export_vdj"
            ):
                try:
                    export_set = _filter_matches(
                        matches, st.session_state.get("dj_status_filter", "All")
                    )
                    outp = pl.export_vdjfolder_mode(
                        target_name if export_mode != "save_as_new" else list_name,
                        export_set,
                        Path(vdj_mylist_str),
                        mode=export_mode,
                        new_name=new_list_name,
                        use_generic_netsearch=use_generic_net,
                    )
                    st.success(f"VDJ list written: {outp}")
                    st.session_state["dj_last_vdj_path"] = str(outp)
                except Exception as e:
                    st.warning(f"Failed to write VDJ list: {e}")
        with cbtn2:
            if st.button(
                "Export M3U8 (local only)", disabled=(not matches), key="dj_btn_export_m3u"
            ):
                try:
                    export_set = _filter_matches(
                        matches, st.session_state.get("dj_status_filter", "All")
                    )
                    # M3U8 export with mode (replace/add/save-as-new)
                    outp = pl.export_m3u8_mode(
                        target_name if export_mode != "save_as_new" else list_name,
                        export_set,
                        Path(m3u_out_str),
                        mode=export_mode,
                        new_name=new_list_name,
                    )
                    st.success(f"M3U8 exported: {outp}")
                    st.session_state["dj_last_m3u_path"] = str(outp)
                except Exception as e:
                    st.warning(f"Failed to export M3U8: {e}")

    # Series coverage verification: ensure latest-per-series isn't missing any archived tracks
    try:
        series_name_cur = st.session_state.get("dj_series_name")
        coverage_info = ""
        if series_name_cur:
            all_csvs = pl.find_compiled_playlists(OUTPUTS_DIR)
            same_series_paths = []
            date_pattern = re.compile(
                r"(?:^|[ _-])"
                r"(20\d{2}[._-](?:0[1-9]|1[0-2])[._-](?:0[1-9]|[12]\d|3[01]))"
                r"(?:$|[ _-])"
            )
            for p in all_csvs:
                bnm = pl.infer_playlist_name(p)
                snm = date_pattern.sub(" ", bnm).replace("_", " ").strip()
                if snm == series_name_cur:
                    same_series_paths.append(p)
            # Build union of keys across series CSVs
            union_keys = set()
            sel_keys = set()
            for p in same_series_paths:
                for r in pl.read_playlist_csv(p):
                    union_keys.add(r.key())
            if sel_csv is not None:
                for r in pl.read_playlist_csv(sel_csv):
                    sel_keys.add(r.key())
            missing_from_latest = union_keys - sel_keys
            if union_keys:
                msg = (
                    "Series coverage: "
                    f"{len(sel_keys)}/{len(union_keys)} tracks in latest; "
                    f"missing {len(missing_from_latest)} from archives"
                )
                st.caption(msg)
    except Exception:
        pass

    # Persistently show 'Open location' actions if last export paths exist
    last_vdj = st.session_state.get("dj_last_vdj_path")
    if last_vdj:
        if st.button("📂 Open VDJ export in Finder", key="dj_btn_open_vdj_loc", type="primary"):
            try:
                subprocess.Popen(["open", "-R", str(last_vdj)])
            except Exception:
                pass
        with st.expander("Preview last VDJ export (first 80 lines)", expanded=False):
            try:
                p = Path(str(last_vdj))
                txt = "\n".join(p.read_text(encoding="utf-8").splitlines()[:80])
                st.code(txt, language="xml")
            except Exception:
                st.write("—")
    last_m3u = st.session_state.get("dj_last_m3u_path")
    if last_m3u:
        if st.button("📂 Open M3U export in Finder", key="dj_btn_open_m3u_loc", type="primary"):
            try:
                subprocess.Popen(["open", "-R", str(last_m3u)])
            except Exception:
                pass

    # Run orchestrator (inline)
    st.divider()
    with st.expander("Run orchestrator", expanded=False):
        rc1, rc2, rc3 = st.columns([1, 1, 2])
        with rc1:
            force = st.checkbox("Force run", value=False, key="dj_force_run")
        with rc2:
            level = st.selectbox("Log level", ["DEBUG", "INFO", "WARNING", "ERROR"], index=1, key="dj_log_level")
        with rc3:
            notify = st.text_input("Notify email (optional)", value="", key="dj_notify_email")
        disabled = (not WRAPPER_PATH.exists()) or LOCK_PATH.exists()
        if st.button("Start orchestrator", type="primary", disabled=disabled, key="dj_btn_start_orchestrator"):
            proc = run_orchestrator_dj(force=force, extract_log_level=level, notify_email=notify)
            if proc is not None:
                st.success("Orchestrator started. A lock prevents overlaps; it will clear when done.")
