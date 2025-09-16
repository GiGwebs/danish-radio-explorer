#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Automated Radio Playlist Update System

This script automatically runs the radio playlist extraction and consolidation,
generates transfer files, and sends notifications.

Features:
- Weekly automated extraction from radio stations
- Track difference analysis (shows only new tracks compared to previous week)
- Email notifications with playlist stats
"""

import os
import sys
import subprocess
import glob
import time
import shutil
import logging
import argparse
import pandas as pd
import json
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Base directory is the Radio Filter root (one level up from this script)
# Use absolute path for robustness when invoked with a relative script path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

# Define constants (paths and script locations)
SCRIPT_DIR = os.path.join(BASE_DIR, 'Scripts')
PLAYLIST_FETCHER_SCRIPT = os.path.join(SCRIPT_DIR, 'extract_radio_playlists.py')
CONSOLIDATOR_SCRIPT = os.path.join(SCRIPT_DIR, 'radio_playlist_consolidator.py')
TRANSFER_SCRIPT = os.path.join(SCRIPT_DIR, 'prepare_playlist_transfer.py')
INDEXER_SCRIPT = os.path.join(SCRIPT_DIR, 'index_downloaded_tracks.py')

# Output directories
OUTPUT_DIR = os.path.join(BASE_DIR, 'Outputs')
LOGS_DIR = os.path.join(BASE_DIR, 'Logs')
OUTPUTS_DIR = os.path.join(BASE_DIR, 'Outputs')
ARCHIVE_DIR = os.path.join(OUTPUTS_DIR, 'Archive')
CONSOLIDATED_DANISH_DIR = os.path.join(OUTPUTS_DIR, 'Combined', 'Danish')
CONSOLIDATED_ENGLISH_DIR = os.path.join(OUTPUTS_DIR, 'Combined', 'English')
TRANSFER_DIR = os.path.join(OUTPUTS_DIR, 'Transfer', 'Radio')
STATUS_DIR = os.path.join(OUTPUTS_DIR, 'Status')

# Ensure log directory exists
os.makedirs(LOGS_DIR, exist_ok=True)

# Configure logging
log_file = os.path.join(
    LOGS_DIR,
    f"auto_update_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('auto_radio_update')

# Ensure directories exist
os.makedirs(ARCHIVE_DIR, exist_ok=True)
os.makedirs(TRANSFER_DIR, exist_ok=True)
os.makedirs(CONSOLIDATED_DANISH_DIR, exist_ok=True)
os.makedirs(CONSOLIDATED_ENGLISH_DIR, exist_ok=True)
os.makedirs(STATUS_DIR, exist_ok=True)

# Debug log key paths and Python executable
logger.info(f"Python executable: {sys.executable}")
logger.info(f"BASE_DIR: {BASE_DIR}")
logger.info(f"SCRIPT_DIR: {SCRIPT_DIR}")
logger.info(f"CONSOLIDATOR_SCRIPT (initial): {CONSOLIDATOR_SCRIPT}")
logger.info(f"PLAYLIST_FETCHER_SCRIPT (initial): {PLAYLIST_FETCHER_SCRIPT}")

# Fallback if consolidator path is wrong (e.g., when invoked from unexpected CWD)
if not os.path.exists(CONSOLIDATOR_SCRIPT):
    consolidator_fallback = os.path.abspath(os.path.join(os.getcwd(), 'Scripts', 'radio_playlist_consolidator.py'))
    if os.path.exists(consolidator_fallback):
        logger.warning(f"Consolidator not found at configured path. Using fallback: {consolidator_fallback}")
        CONSOLIDATOR_SCRIPT = consolidator_fallback
    else:
        logger.error("Consolidator script not found at either configured path or fallback.")

# Fallback if extractor path is wrong (e.g., when invoked from unexpected CWD)
if not os.path.exists(PLAYLIST_FETCHER_SCRIPT):
    extractor_fallback = os.path.abspath(os.path.join(os.getcwd(), 'Scripts', 'extract_radio_playlists.py'))
    if os.path.exists(extractor_fallback):
        logger.warning(f"Extractor not found at configured path. Using fallback: {extractor_fallback}")
        PLAYLIST_FETCHER_SCRIPT = extractor_fallback
    else:
        logger.error("Extractor script not found at either configured path or fallback.")

# Default email address for notifications
DEFAULT_EMAIL = "gigwebs@gmail.com"

def send_desktop_notification(title, message, output_path=None):
    """Send a simple desktop notification via macOS Notification Center."""
    try:
        applescript = f'display notification "{message}" with title "{title}"'
        proc = subprocess.run(
            ['osascript', '-e', applescript],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        if proc.returncode == 0:
            logger.info(f"Sent desktop notification: {title}")
            return True
        else:
            err = proc.stderr.decode('utf-8', errors='ignore')
            logger.error(f"osascript notification error: {err}")
            return False
    except Exception as e:
        logger.error(f"Error sending desktop notification: {str(e)}")
        return False

def send_email_notification(to_email, subject, message_html, attachments=None):
    """Send an email notification via macOS Mail (AppleScript).
    Falls back to saving HTML. Optionally attaches files in `attachments`.
    """
    try:
        # Clean subject for AppleScript quoting
        clean_subject = subject.replace("'", "\\'")

        # Save the HTML content so it can be attached
        filename = f"notification_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        filepath = os.path.join(OUTPUT_DIR, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"<html><body><h3>{subject}</h3>{message_html}</body></html>")

        # Build AppleScript commands for optional attachments
        attachments = attachments or []
        attachment_lines = ""
        for path in attachments:
            try:
                if os.path.exists(path):
                    safe_path = path.replace('"', '\\"')
                    attachment_lines += f'''
                set attFile to POSIX file "{safe_path}"
                make new attachment with properties {{file name:attFile}} at after the last paragraph
                '''
            except Exception:
                continue

        # AppleScript to send via Mail
        applescript = f'''
        tell application "Mail"
            set newMessage to make new outgoing message with properties {{subject:"{clean_subject}", content:"Please see the attached HTML file for the update details.", visible:false}}
            tell newMessage
                set htmlFile to POSIX file "{filepath}"
                make new attachment with properties {{file name:htmlFile}} at after the last paragraph
{attachment_lines}
                make new to recipient with properties {{address:"{to_email}"}}
                send
            end tell
        end tell
        '''

        process = subprocess.Popen(
            ['osascript', '-e', applescript],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = process.communicate()

        if process.returncode == 0:
            logger.info(f"Email notification sent to {to_email} via macOS Mail")
            return True
        else:
            error_message = stderr.decode('utf-8')
            logger.error(f"Error sending email via AppleScript: {error_message}")
            raise Exception(f"AppleScript error: {error_message}")

    except Exception as e:
        logger.error(f"Error sending email notification: {str(e)}")
        # Fallback: save notification as HTML for reference
        try:
            notification_file = os.path.join(
                BASE_DIR,
                'Logs',
                f'email_notification_error_{datetime.now().strftime("%Y%m%d_%H%M%S")}.html'
            )
            with open(notification_file, 'w', encoding='utf-8') as f:
                f.write(f"<html><body><h3>{subject}</h3>{message_html}</body></html>")
            logger.info(f"Email sending failed, saved notification to {notification_file}")
        except Exception as inner_e:
            logger.error(f"Error saving notification file: {str(inner_e)}")
        return False

def archive_old_files():
    """Archive old consolidated files"""
    today = datetime.now().strftime('%Y-%m-%d')
    archive_date_dir = os.path.join(ARCHIVE_DIR, today)
    os.makedirs(archive_date_dir, exist_ok=True)
    
    # Create subdirectories in the archive
    for subdir in ['Danish', 'English', 'Transfer']:
        os.makedirs(os.path.join(archive_date_dir, subdir), exist_ok=True)
    
    # Archive Danish consolidated files
    danish_files = [f for f in os.listdir(CONSOLIDATED_DANISH_DIR) if f.endswith('.csv')]
    for file in danish_files:
        src = os.path.join(CONSOLIDATED_DANISH_DIR, file)
        dst = os.path.join(archive_date_dir, 'Danish', file)
        try:
            # Copy file to archive
            shutil.copy2(src, dst)
            logger.info(f"Archived Danish file: {file}")
        except Exception as e:
            logger.error(f"Error archiving file {file}: {str(e)}")
    
    # Archive English consolidated files
    english_files = [f for f in os.listdir(CONSOLIDATED_ENGLISH_DIR) if f.endswith('.csv')]
    for file in english_files:
        src = os.path.join(CONSOLIDATED_ENGLISH_DIR, file)
        dst = os.path.join(archive_date_dir, 'English', file)
        try:
            # Copy file to archive
            shutil.copy2(src, dst)
            logger.info(f"Archived English file: {file}")
        except Exception as e:
            logger.error(f"Error archiving file {file}: {str(e)}")
    
    # Archive Transfer files
    transfer_files = [f for f in os.listdir(TRANSFER_DIR) if f.endswith('.csv')]
    for file in transfer_files:
        src = os.path.join(TRANSFER_DIR, file)
        dst = os.path.join(archive_date_dir, 'Transfer', file)
        try:
            # Copy file to archive
            shutil.copy2(src, dst)
            logger.info(f"Archived Transfer file: {file}")
        except Exception as e:
            logger.error(f"Error archiving file {file}: {str(e)}")
    
    return archive_date_dir

def get_latest_file(directory):
    """Get the most recent CSV file from a directory"""
    try:
        files = [f for f in os.listdir(directory) if f.endswith('.csv')]
        if not files:
            return None
            
        files.sort(key=lambda x: os.path.getmtime(os.path.join(directory, x)), reverse=True)
        return os.path.join(directory, files[0])
    except Exception as e:
        logger.error(f"Error finding latest file in {directory}: {str(e)}")
        return None

def get_latest_matching_file(directory, pattern):
    """Get the most recent file in a directory matching a glob pattern."""
    try:
        paths = glob.glob(os.path.join(directory, pattern))
        if not paths:
            return None
        paths.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return paths[0]
    except Exception as e:
        logger.error(f"Error finding latest file for pattern {pattern} in {directory}: {str(e)}")
        return None

def get_station_config():
    """Retrieve station list and NO_LANGUAGE_SEPARATION from extractor module.

    Falls back to a static list if import fails.
    """
    try:
        if SCRIPT_DIR not in sys.path:
            sys.path.insert(0, SCRIPT_DIR)
        import extract_radio_playlists as ext
        stations = list(ext.STATION_MAP.keys())
        no_sep = set(ext.NO_LANGUAGE_SEPARATION)
        return stations, no_sep
    except Exception as e:
        logger.warning(f"Unable to import station config from extractor: {e}. Falling back to defaults.")
        stations = ['NOVA', 'P3', 'TheVoice', 'Radio100', 'PartyFM', 'RadioGlobus', 'SkalaFM', 'P4', 'PopFM', 'RBClassics']
        no_sep = {'RBClassics'}
        return stations, no_sep

def scan_extraction_status(date_str):
    """Scan Outputs/Stations for station files for the given date.

    Returns (stations, completed, partial, missing, no_playlist).
    - completed: stations with expected files present
    - partial: stations with only one of Danish/English present (when applicable)
    - missing: stations with no expected files and no marker
    - no_playlist: stations explicitly marked as having no playlist for this date
    """
    stations, no_sep = get_station_config()
    completed, partial, missing, no_playlist = [], [], [], []
    filename_date = f"past_7_days_{date_str}"
    for s in stations:
        station_dir = os.path.join(OUTPUTS_DIR, 'Stations', s)
        marker = os.path.join(station_dir, 'Raw', f"{s}_NoPlaylist_{filename_date}.json")
        if s in no_sep:
            all_ok = os.path.exists(os.path.join(station_dir, 'All', f"{s}_All_Tracks_{filename_date}.csv"))
            if all_ok:
                completed.append(s)
            else:
                if os.path.exists(marker):
                    no_playlist.append(s)
                else:
                    missing.append(s)
        else:
            danish_ok = os.path.exists(os.path.join(station_dir, 'Danish', f"{s}_Danish_Titles_{filename_date}.csv"))
            english_ok = os.path.exists(os.path.join(station_dir, 'English', f"{s}_English_Titles_{filename_date}.csv"))
            if danish_ok and english_ok:
                completed.append(s)
            elif danish_ok or english_ok:
                partial.append(s)
            else:
                if os.path.exists(marker):
                    no_playlist.append(s)
                else:
                    missing.append(s)
    return stations, completed, partial, missing, no_playlist

def write_status_json(filepath, payload):
    """Persist status payload to JSON."""
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.warning(f"Failed to write status JSON: {e}")
        return False

def compare_playlists(old_file, new_file):
    """Compare two playlists to find new tracks"""
    try:
        if not old_file or not os.path.exists(old_file) or not new_file or not os.path.exists(new_file):
            return [], 0
            
        old_df = pd.read_csv(old_file)
        new_df = pd.read_csv(new_file)
        
        # Check if the CSV has a 'Track' column
        if 'Track' in old_df.columns and 'Track' in new_df.columns:
            old_tracks = set(old_df['Track'].str.lower())
            new_tracks = set(new_df['Track'].str.lower())
            
            # Find tracks in new_df that weren't in old_df
            new_tracks_only = new_tracks - old_tracks
            
            # Get full rows for new tracks
            new_tracks_df = new_df[new_df['Track'].str.lower().isin(new_tracks_only)]
            
            return new_tracks_df.to_dict('records'), len(new_tracks_df)
        else:
            logger.warning("CSV files don't have 'Track' column, can't compare")
            return [], 0
    except Exception as e:
        logger.error(f"Error comparing playlists: {str(e)}")
        return [], 0

def save_new_tracks_csv(tracks, output_file):
    """Save new tracks to a CSV file"""
    try:
        if not tracks:
            return False
            
        df = pd.DataFrame(tracks)
        df.to_csv(output_file, index=False)
        logger.info(f"Saved {len(tracks)} new tracks to {output_file}")
        return True
    except Exception as e:
        logger.error(f"Error saving new tracks CSV: {str(e)}")
        return False

def run_automated_update(
    notify_email=None,
    extract_http_timeout=20,
    extract_retries=3,
    extract_backoff=0.5,
    extract_log_level="INFO",
    extract_subprocess_timeout=1200,
):
    """Run the automated radio playlist update"""
    try:
        start_time = time.time()
        today = datetime.now().strftime('%Y-%m-%d')
        logger.info(f"Starting automated radio playlist update on {today}")
        
        # Send desktop notification that process is starting
        send_desktop_notification(
            "Radio Playlist Update Started", 
            f"Starting automated update process on {today}"
        )
        
        # 1. Archive old files
        archive_dir = archive_old_files()
        logger.info(f"Archived old files to {archive_dir}")
        
        # 2. Run the station playlist extractor to fetch latest station-level data
        logger.info("Running station playlist extractor...")
        extractor_cmd = [
            sys.executable,
            PLAYLIST_FETCHER_SCRIPT,
            "--timeout", str(extract_http_timeout),
            "--retries", str(extract_retries),
            "--backoff", str(extract_backoff),
            "--log-level", str(extract_log_level),
            "all",
        ]
        logger.info(f"Extractor command: {' '.join(extractor_cmd)}")
        try:
            extractor_result = subprocess.run(
                extractor_cmd,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"},
                timeout=extract_subprocess_timeout,
            )
        except subprocess.TimeoutExpired as e:
            out = (e.stdout or "")[:2000]
            err = (e.stderr or "")[:2000]
            logger.error(f"Extractor timed out after {extract_subprocess_timeout}s")
            if out:
                logger.info(f"Extractor stdout before timeout (truncated):\n{out}")
            if err:
                logger.warning(f"Extractor stderr before timeout (truncated):\n{err}")
            send_desktop_notification("Radio Update Error", "Extractor timed out")
            if notify_email:
                send_email_notification(
                    notify_email,
                    "Radio Playlist Update Failed",
                    f"<p>The extractor timed out after {extract_subprocess_timeout}s.</p><pre>{err}</pre>"
                )
            return False
        if extractor_result.stdout:
            logger.info(f"Extractor stdout (truncated):\n{extractor_result.stdout[:2000]}")
        if extractor_result.stderr:
            logger.warning(f"Extractor stderr (truncated):\n{extractor_result.stderr[:2000]}")
        if extractor_result.returncode != 0:
            error_msg = f"Error running extractor: {extractor_result.stderr}"
            logger.error(error_msg)
            send_desktop_notification("Radio Update Error", "Error running extractor script")
            if notify_email:
                send_email_notification(
                    notify_email,
                    "Radio Playlist Update Failed",
                    f"<p>The radio playlist extraction step failed:</p><pre>{error_msg}</pre>"
                )
            return False

        # 2a. Validate extractor outputs for today and retry missing/partial stations once
        stations, completed, partial, missing, no_playlist = scan_extraction_status(today)
        if partial or missing:
            logger.warning(
                "Extractor outputs incomplete. Completed %s/%s. Missing: %s. Partial: %s.",
                len(completed), len(stations), 
                ", ".join(missing) if missing else "None",
                ", ".join(partial) if partial else "None",
            )
            # Exclude stations explicitly marked as no playlist
            retry_targets = sorted(set(missing + partial) - set(no_playlist))
            # Log which stations were excluded from retry due to no-playlist classification
            excluded_due_to_no_playlist = sorted(set(missing + partial) & set(no_playlist))
            if excluded_due_to_no_playlist:
                logger.info(
                    "Excluded from retry (no-playlist): %s",
                    ", ".join(excluded_due_to_no_playlist)
                )
            if retry_targets:
                logger.info(f"Retrying extractor for incomplete stations: {', '.join(retry_targets)}")
                retry_cmd = [
                    sys.executable,
                    PLAYLIST_FETCHER_SCRIPT,
                    "--timeout", str(extract_http_timeout),
                    "--retries", str(extract_retries),
                    "--backoff", str(extract_backoff),
                    "--log-level", str(extract_log_level),
                ] + retry_targets
                total_stations = len(stations) if stations else 1
                retry_timeout = max(300, int(extract_subprocess_timeout * len(retry_targets) / total_stations))
                logger.info(f"Extractor retry command: {' '.join(retry_cmd)} (timeout={retry_timeout}s)")
                retry_result = None
                try:
                    retry_result = subprocess.run(
                        retry_cmd,
                        capture_output=True,
                        text=True,
                        env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"},
                        timeout=retry_timeout,
                    )
                except subprocess.TimeoutExpired as e:
                    out = (e.stdout or "")[:2000]
                    err = (e.stderr or "")[:2000]
                    logger.error(f"Extractor retry timed out after {retry_timeout}s")
                    if out:
                        logger.info(f"Extractor retry stdout before timeout (truncated):\n{out}")
                    if err:
                        logger.warning(f"Extractor retry stderr before timeout (truncated):\n{err}")
                    # Proceed to re-scan and continue
                    stations, completed, partial, missing, no_playlist = scan_extraction_status(today)
                    
                if retry_result and retry_result.stdout:
                    logger.info(f"Extractor retry stdout (truncated):\n{retry_result.stdout[:2000]}")
                if retry_result and retry_result.stderr:
                    logger.warning(f"Extractor retry stderr (truncated):\n{retry_result.stderr[:2000]}")
                # Re-scan after retry
                stations, completed, partial, missing, no_playlist = scan_extraction_status(today)
                if partial or missing:
                    logger.warning(
                        "After retry, still incomplete. Completed %s/%s. Missing: %s. Partial: %s.",
                        len(completed), len(stations), 
                        ", ".join(missing) if missing else "None",
                        ", ".join(partial) if partial else "None",
                    )

        # Write extraction status JSON for monitoring
        status_payload = {
            "date": today,
            "stations_total": len(stations),
            "stations_completed": completed,
            "stations_partial": partial,
            "stations_missing": missing,
            "stations_no_playlist": no_playlist,
            "log_file": log_file,
            "generated_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        write_status_json(os.path.join(STATUS_DIR, 'last_update.json'), status_payload)

        # 3. Get previous consolidated files (for comparison later)
        previous_danish_file = get_latest_file(CONSOLIDATED_DANISH_DIR)
        previous_english_file = get_latest_file(CONSOLIDATED_ENGLISH_DIR)
        
        # 4. Run the consolidator script
        logger.info("Running radio playlist consolidator...")
        result = subprocess.run(
            [sys.executable, CONSOLIDATOR_SCRIPT, "--automated"],
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
        )
        
        # Log child outputs for debugging (truncate to avoid huge logs)
        if result.stdout:
            logger.info(f"Consolidator stdout (truncated):\n{result.stdout[:2000]}")
        if result.stderr:
            logger.warning(f"Consolidator stderr (truncated):\n{result.stderr[:2000]}")
        
        if result.returncode != 0:
            error_msg = f"Error running consolidator: {result.stderr}"
            logger.error(error_msg)
            send_desktop_notification("Radio Update Error", "Error running consolidator script")
            if notify_email:
                send_email_notification(
                    notify_email,
                    "Radio Playlist Update Failed",
                    f"<p>The radio playlist update process failed:</p><pre>{error_msg}</pre>"
                )
            return False
        
        logger.info("Radio playlist consolidator completed successfully")
        
        # 4b. Generate full transfer files (radio + cumulative) unconditionally
        try:
            logger.info("Generating full transfer files (radio + cumulative)...")
            transfer_full_args = [
                sys.executable,
                TRANSFER_SCRIPT,
                '--source', 'radio',
            ]
            transfer_full = subprocess.run(
                transfer_full_args,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
            )
            if transfer_full.stdout:
                logger.info(f"Transfer (radio) stdout (truncated):\n{transfer_full.stdout[:2000]}")
            if transfer_full.stderr:
                logger.warning(f"Transfer (radio) stderr (truncated):\n{transfer_full.stderr[:2000]}")
            if transfer_full.returncode != 0:
                logger.warning("Transfer (radio) returned non-zero exit code; continuing with workflow.")
            else:
                logger.info("Full radio + cumulative transfer generation completed successfully")
        except Exception as e:
            logger.warning(f"Failed to generate full transfer files: {e}")

        # 5. Get the new consolidated files
        new_danish_file = get_latest_file(CONSOLIDATED_DANISH_DIR)
        new_english_file = get_latest_file(CONSOLIDATED_ENGLISH_DIR)
        
        # 6. Compare to find new tracks
        new_danish_tracks, danish_count = compare_playlists(previous_danish_file, new_danish_file)
        new_english_tracks, english_count = compare_playlists(previous_english_file, new_english_file)
        
        # 7. Save new tracks to dedicated files
        new_tracks_dir = os.path.join(OUTPUTS_DIR, 'New_Tracks')
        os.makedirs(new_tracks_dir, exist_ok=True)
        
        new_danish_output = os.path.join(new_tracks_dir, f"New_Danish_Tracks_{today}.csv")
        new_english_output = os.path.join(new_tracks_dir, f"New_English_Tracks_{today}.csv")
        
        save_new_tracks_csv(new_danish_tracks, new_danish_output)
        save_new_tracks_csv(new_english_tracks, new_english_output)
        
        # 8. Only run transfer script if new tracks were found
        total_new_tracks = danish_count + english_count
        if total_new_tracks > 0:
            logger.info(f"Found {total_new_tracks} new tracks. Refreshing downloaded index cache and generating delta-only transfer files...")

            # 7a. Refresh downloaded index cache (non-fatal on failure)
            try:
                indexer_result = subprocess.run(
                    [sys.executable, INDEXER_SCRIPT],
                    capture_output=True,
                    text=True,
                    env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
                )
                if indexer_result.stdout:
                    logger.info(f"Indexer stdout (truncated):\n{indexer_result.stdout[:2000]}")
                if indexer_result.stderr:
                    logger.warning(f"Indexer stderr (truncated):\n{indexer_result.stderr[:2000]}")
                if indexer_result.returncode != 0:
                    logger.warning("Downloaded indexer returned non-zero; proceeding without annotation.")
            except Exception as e:
                logger.warning(f"Failed to run downloaded indexer: {e}")

            # 7b. Generate transfer files for only new tracks, with annotation if cache exists
            transfer_args = [
                sys.executable,
                TRANSFER_SCRIPT,
                '--source', 'new_tracks',
                '--annotate-downloaded',
                '--export-xlsx-review',
            ]
            transfer_result = subprocess.run(
                transfer_args,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
            )
            
            # Log transfer script outputs (truncate)
            if transfer_result.stdout:
                logger.info(f"Transfer stdout (truncated):\n{transfer_result.stdout[:2000]}")
            if transfer_result.stderr:
                logger.warning(f"Transfer stderr (truncated):\n{transfer_result.stderr[:2000]}")
            
            if transfer_result.returncode != 0:
                error_msg = f"Error running transfer script: {transfer_result.stderr}"
                logger.error(error_msg)
            else:
                logger.info("Delta-only playlist transfer generation completed successfully")
        else:
            logger.info("No new tracks found. Skipping transfer file generation.")
        
        # 9. Create notification message
        duration = time.time() - start_time
        message_html = f"""
        <h2>Radio Playlist Update Summary ({today})</h2>
        <p>The automated radio playlist update has completed successfully.</p>
        
        <h3>Statistics:</h3>
        <ul>
            <li><strong>Process duration:</strong> {duration:.1f} seconds</li>
            <li><strong>New Danish tracks:</strong> {danish_count}</li>
            <li><strong>New English tracks:</strong> {english_count}</li>
            <li><strong>Total new tracks:</strong> {danish_count + english_count}</li>
        </ul>
        
        <h3>Extraction Summary:</h3>
        <ul>
            <li><strong>Stations completed:</strong> {len(completed)}/{len(stations)}</li>
            <li><strong>No playlist:</strong> {', '.join(no_playlist) if no_playlist else 'None'}</li>
            <li><strong>Missing/Partial (retry candidates):</strong> {', '.join(sorted(set(missing + partial) - set(no_playlist))) if (missing or partial) else 'None'}</li>
        </ul>
        
        <h3>Files Generated:</h3>
        <ul>
            <li><strong>Danish Consolidated:</strong> {os.path.basename(new_danish_file) if new_danish_file else 'None'}</li>
            <li><strong>English Consolidated:</strong> {os.path.basename(new_english_file) if new_english_file else 'None'}</li>
            <li><strong>New Danish Tracks:</strong> {os.path.basename(new_danish_output)}</li>
            <li><strong>New English Tracks:</strong> {os.path.basename(new_english_output)}</li>
        </ul>
        
        <p>All files are ready for transfer to music streaming services.</p>
        """

        # Add note when there are zero new tracks (but attachments may include latest prior files)
        if total_new_tracks == 0:
            message_html += """
            <p><em>No new tracks were detected today. For convenience, the latest review XLSX and annotated CSV from the most recent run are attached.</em></p>
            """
        
        # 9. Send desktop notification with links to output folders
        send_desktop_notification(
            "Radio Playlist Update Complete", 
            f"Found {danish_count + english_count} new tracks across all stations. Click to open folder.",
            TRANSFER_DIR
        )
        
        # Also send notification about new tracks with link
        if danish_count + english_count > 0:
            send_desktop_notification(
                "New Radio Tracks Detected", 
                f"Found {danish_count} new Danish tracks and {english_count} new English tracks. Click to view.",
                new_tracks_dir
            )
        
        # Prepare attachments (review XLSX + annotated CSV)
        attachment_files = []
        if total_new_tracks > 0:
            for lang in ('Danish', 'English'):
                base = os.path.join(TRANSFER_DIR, f"{lang}_Radio_New_{today}")
                review = f"{base}_review.xlsx"
                annotated = f"{base}_annotated.csv"
                if os.path.exists(review):
                    attachment_files.append(review)
                if os.path.exists(annotated):
                    attachment_files.append(annotated)
        else:
            # Attach latest available review/annotated files from prior runs for convenience
            for lang in ('Danish', 'English'):
                latest_review = get_latest_matching_file(TRANSFER_DIR, f"{lang}_Radio_New_*_review.xlsx")
                latest_annot = get_latest_matching_file(TRANSFER_DIR, f"{lang}_Radio_New_*_annotated.csv")
                if latest_review and os.path.exists(latest_review):
                    attachment_files.append(latest_review)
                if latest_annot and os.path.exists(latest_annot):
                    attachment_files.append(latest_annot)

        # 10. Send email notification if requested
        if notify_email:
            send_email_notification(
                notify_email,
                f"Radio Playlist Update: {danish_count + english_count} New Tracks",
                message_html,
                attachments=attachment_files
            )
        
        logger.info(f"Automated update completed successfully. Found {danish_count + english_count} new tracks.")
        return True
        
    except Exception as e:
        error_msg = f"Error in automated update: {str(e)}"
        logger.error(error_msg)
        send_desktop_notification("Radio Update Error", "An unexpected error occurred")
        if notify_email:
            send_email_notification(
                notify_email,
                "Radio Playlist Update Failed",
                f"<p>The radio playlist update process failed with an unexpected error:</p><pre>{error_msg}</pre>"
            )
        return False

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='Automated Radio Playlist Update')
    parser.add_argument('--notify-email', help='Email to send notifications to', default=DEFAULT_EMAIL)
    parser.add_argument('--force', help='Force update even if not scheduled day', action='store_true')
    # Extractor runtime config
    parser.add_argument('--extract-timeout', type=int, default=1200, help='Global timeout (seconds) for extractor subprocess')
    parser.add_argument('--extract-http-timeout', type=int, default=20, help='HTTP timeout per request for extractor (--timeout)')
    parser.add_argument('--extract-retries', type=int, default=3, help='HTTP retry attempts for extractor (--retries)')
    parser.add_argument('--extract-backoff', type=float, default=0.5, help='HTTP retry backoff factor for extractor (--backoff)')
    parser.add_argument('--extract-log-level', default='INFO', help='Log level for extractor (--log-level)')
    
    args = parser.parse_args()
    
    # Check if it's the scheduled day (defaults: Tuesday and Friday)
    # This allows the script to run on a daily scheduler but only process on Tuesdays and Fridays
    today = datetime.now()
    weekday = today.weekday()  # Mon=0..Sun=6
    is_scheduled = weekday in (1, 4)  # 1=Tuesday, 4=Friday
    
    if args.force or is_scheduled:
        run_automated_update(
            args.notify_email,
            extract_http_timeout=args.extract_http_timeout,
            extract_retries=args.extract_retries,
            extract_backoff=args.extract_backoff,
            extract_log_level=args.extract_log_level,
            extract_subprocess_timeout=args.extract_timeout,
        )
    else:
        logger.info(f"Today ({today.strftime('%A')}) is not a scheduled update day. Use --force to run anyway.")

if __name__ == "__main__":
    main()
