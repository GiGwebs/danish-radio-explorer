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
import platform
import re
import time
import shutil
import logging
import random
import string
import glob
import argparse
import traceback
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Base directory is 2 levels up from this script
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

# Define constants (paths and script locations)
SCRIPT_DIR = os.path.join(BASE_DIR, 'Scripts')
PLAYLIST_FETCHER_SCRIPT = os.path.join(SCRIPT_DIR, 'fetch_all_radio_playlists.py')
CONSOLIDATOR_SCRIPT = os.path.join(SCRIPT_DIR, 'radio_playlist_consolidator.py')
TRANSFER_SCRIPT = os.path.join(SCRIPT_DIR, 'prepare_radio_playlists.py')

# Output directories
OUTPUT_DIR = os.path.join(BASE_DIR, 'Outputs')
LOGS_DIR = os.path.join(BASE_DIR, 'Logs')
OUTPUTS_DIR = os.path.join(BASE_DIR, 'Outputs')
ARCHIVE_DIR = os.path.join(OUTPUTS_DIR, 'Archive')
CONSOLIDATED_DANISH_DIR = os.path.join(OUTPUTS_DIR, 'Combined', 'Danish')
CONSOLIDATED_ENGLISH_DIR = os.path.join(OUTPUTS_DIR, 'Combined', 'English')
TRANSFER_DIR = os.path.join(OUTPUTS_DIR, 'Transfer', 'Radio')

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

# Default email address for notifications
DEFAULT_EMAIL = "gigwebs@gmail.com"

def send_desktop_notification(title, message, output_path=None):
    """Send a desktop notification with an optional link to a file/folder"""
    try:
        # If output_path is provided, create an AppleScript that can open the file/folder
        if output_path:
            # Convert to file URL
            file_url = f"file://{urllib.parse.quote(os.path.abspath(output_path))}"
            
            # Create an AppleScript that shows notification and can open file when clicked
            applescript = f'''
            display notification "{message}" with title "{title}" subtitle "Click to open folder"
            '''
            
            # Add handler for clicking notification (opens the folder)
            applescript += f'''
            tell application "System Events"
                set lastNotification to last notification
                tell lastNotification
                    set theActions to actions
                    repeat with anAction in theActions
                        if title of anAction is "Show" then
                            tell application "Finder"
                                open location "{file_url}"
                            end tell
                            exit repeat
                        end if
                    end repeat
                end tell
            end tell
            '''
        else:
            # Simple notification without link
            applescript = f'''
            display notification "{message}" with title "{title}"
            '''
            
        # Run the AppleScript
        subprocess.run(['osascript', '-e', applescript])
        logger.info(f"Sent desktop notification: {title}")
        return True
    except Exception as e:
        logger.error(f"Error sending desktop notification: {str(e)}")
        return False

def send_email_notification(to_email, subject, message_html):
    """Send an email notification using Gmail SMTP"""
    try:
        # Get email configuration from environment variables
        sender_email = os.environ.get('EMAIL_SENDER')
        sender_password = os.environ.get('EMAIL_PASSWORD')
        
        # Validate email configuration
        
        # Format the subject and clean the notification message for AppleScript
        # Replace any single quotes with escaped single quotes to avoid AppleScript errors
        clean_subject = subject.replace("'", "\\'")  
        
        # Save notification as HTML file (as a fallback and for reference)
        filename = f"notification_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        filepath = os.path.join(OUTPUT_DIR, filename)
        with open(filepath, 'w') as f:
            f.write(notification_message)
        
        # Use AppleScript to send email via the macOS Mail app
        applescript = f'''
        tell application "Mail"
            set newMessage to make new outgoing message with properties {{subject:"{clean_subject}", content:"Please see the attached HTML file for the update details.", visible:false}}
            tell newMessage
                set htmlFile to POSIX file "{filepath}"
                make new attachment with properties {{file name:htmlFile}} at after the last paragraph
                make new to recipient with properties {{address:"{recipient_email}"}}
                send
            end tell
        end tell
        '''
        
        # Execute the AppleScript to send the email
        process = subprocess.Popen(['osascript', '-e', applescript], 
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        
        if process.returncode == 0:
            logger.info(f"Email notification sent to {recipient_email} via macOS Mail")
            return True
        else:
            error_message = stderr.decode('utf-8')
            logger.error(f"Error sending email via AppleScript: {error_message}")
            raise Exception(f"AppleScript error: {error_message}")
            
    except Exception as e:
        logger.error(f"Error sending email notification: {str(e)}")
        # Fallback to saving notification as HTML file only
        logger.info(f"Notification saved as HTML file: {filepath}")
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
            logger.warning(f"CSV files don't have 'Track' column, can't compare")
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

def run_automated_update(notify_email=None):
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
        
        # 2. Get previous consolidated files (for comparison later)
        previous_danish_file = get_latest_file(CONSOLIDATED_DANISH_DIR)
        previous_english_file = get_latest_file(CONSOLIDATED_ENGLISH_DIR)
        
        # 3. Run the consolidator script
        logger.info("Running radio playlist consolidator...")
        result = subprocess.run(
            [sys.executable, CONSOLIDATOR_SCRIPT, "--automated"],
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
        )
        
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
        
        # 4. Get the new consolidated files
        new_danish_file = get_latest_file(CONSOLIDATED_DANISH_DIR)
        new_english_file = get_latest_file(CONSOLIDATED_ENGLISH_DIR)
        
        # 5. Compare to find new tracks
        new_danish_tracks, danish_count = compare_playlists(previous_danish_file, new_danish_file)
        new_english_tracks, english_count = compare_playlists(previous_english_file, new_english_file)
        
        # 6. Save new tracks to dedicated files
        new_tracks_dir = os.path.join(OUTPUTS_DIR, 'New_Tracks')
        os.makedirs(new_tracks_dir, exist_ok=True)
        
        new_danish_output = os.path.join(new_tracks_dir, f"New_Danish_Tracks_{today}.csv")
        new_english_output = os.path.join(new_tracks_dir, f"New_English_Tracks_{today}.csv")
        
        save_new_tracks_csv(new_danish_tracks, new_danish_output)
        save_new_tracks_csv(new_english_tracks, new_english_output)
        
        # 7. Only run transfer script if new tracks were found
        total_new_tracks = danish_count + english_count
        if total_new_tracks > 0:
            logger.info(f"Found {total_new_tracks} new tracks. Running playlist transfer script...")
            transfer_result = subprocess.run(
                [sys.executable, TRANSFER_SCRIPT],
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
            )
            
            if transfer_result.returncode != 0:
                error_msg = f"Error running transfer script: {transfer_result.stderr}"
                logger.error(error_msg)
            else:
                logger.info("Playlist transfer script completed successfully")
        else:
            logger.info("No new tracks found. Skipping transfer file generation.")
        
        # 8. Create notification message
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
        
        <h3>Files Generated:</h3>
        <ul>
            <li><strong>Danish Consolidated:</strong> {os.path.basename(new_danish_file) if new_danish_file else 'None'}</li>
            <li><strong>English Consolidated:</strong> {os.path.basename(new_english_file) if new_english_file else 'None'}</li>
            <li><strong>New Danish Tracks:</strong> {os.path.basename(new_danish_output)}</li>
            <li><strong>New English Tracks:</strong> {os.path.basename(new_english_output)}</li>
        </ul>
        
        <p>All files are ready for transfer to music streaming services.</p>
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
        
        # 10. Send email notification if requested
        if notify_email:
            send_email_notification(
                notify_email,
                f"Radio Playlist Update: {danish_count + english_count} New Tracks",
                message_html
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
    
    args = parser.parse_args()
    
    # Check if it's the scheduled day (default: Sunday)
    # This allows the script to run on a daily cron job but only process on Sundays
    today = datetime.now()
    is_sunday = today.weekday() == 6  # 6 = Sunday
    
    if args.force or is_sunday:
        run_automated_update(args.notify_email)
    else:
        logger.info(f"Today ({today.strftime('%A')}) is not a scheduled update day. Use --force to run anyway.")

if __name__ == "__main__":
    main()
