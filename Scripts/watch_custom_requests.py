#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Custom Playlist Request Watcher

This script watches the 'Custom Requests' folder for new CSV files
and automatically processes them for transfer to streaming services.

Usage:
    python watch_custom_requests.py

Features:
    - Monitors the Custom Requests folder for new files
    - Automatically processes new CSV files for playlist transfer
    - Creates properly formatted output files in Outputs/Transfer/Custom
    - Logs all activity for auditing
"""

import os
import sys
import time
import logging
import subprocess
import shutil
import urllib.parse
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('custom_requests_watcher.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('custom_watcher')

# Base paths
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
CUSTOM_REQUESTS_DIR = os.path.join(BASE_DIR, 'Custom Requests')
ARCHIVE_DIR = os.path.join(BASE_DIR, 'Custom Requests', 'Archive')
TRANSFER_SCRIPT = os.path.join(BASE_DIR, 'Scripts', 'prepare_playlist_transfer.py')
RANKER_SCRIPT = os.path.join(BASE_DIR, 'Scripts', 'playlist_popularity_ranker.py')
OUTPUTS_DIR = os.path.join(BASE_DIR, 'Outputs', 'Transfer', 'Custom')

# Ensure directories exist
os.makedirs(CUSTOM_REQUESTS_DIR, exist_ok=True)
os.makedirs(ARCHIVE_DIR, exist_ok=True)

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

class NewFileHandler(FileSystemEventHandler):
    """Handler for file system events"""
    
    def __init__(self):
        self.processing = False
        self.last_processed_files = set()
    
    def on_created(self, event):
        """Handle file creation events"""
        if self.processing:
            return
            
        if event.is_directory:
            return
            
        # Process only CSV files
        if not event.src_path.lower().endswith('.csv'):
            return
        
        # Avoid processing the same file multiple times (watchdog sometimes fires multiple events)
        if event.src_path in self.last_processed_files:
            return
            
        self.last_processed_files.add(event.src_path)
        if len(self.last_processed_files) > 10:  # Keep the set from growing too large
            self.last_processed_files = set(list(self.last_processed_files)[-10:])
        
        # Small delay to ensure file is fully written
        time.sleep(1)
        
        # Send notification that processing is starting
        file_name = os.path.basename(event.src_path)
        send_desktop_notification(
            "Processing Custom Playlist", 
            "Starting to process: {}".format(file_name)
        )
        
        self.process_new_file(event.src_path)
    
    def process_new_file(self, file_path):
        """Process a new playlist file"""
        try:
            self.processing = True
            
            file_name = os.path.basename(file_path)
            logger.info("New file detected: {}".format(file_name))
            
            # Check if file exists and is not empty
            if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
                logger.warning("File {} doesn't exist or is empty. Skipping.".format(file_name))
                self.processing = False
                return
            
            # Generate playlist name from filename (without extension and date)
            playlist_name = os.path.splitext(file_name)[0]
            # Remove date suffix if present (e.g., _2025-04-19)
            if '_20' in playlist_name:
                playlist_name = playlist_name.split('_20')[0]
            
            # Check for special processing flags in filename
            rank_by_popularity = False
            if '_rank' in playlist_name.lower() or '_popular' in playlist_name.lower():
                rank_by_popularity = True
                # Remove the flag from the name
                playlist_name = playlist_name.lower().replace('_rank', '').replace('_popular', '')
                
            # Process the file
            logger.info("Processing {} as '{}'".format(file_name, playlist_name))
            
            # Run the playlist transfer script
            command = [
                sys.executable, 
                TRANSFER_SCRIPT, 
                '--source', file_path, 
                '--name', playlist_name
            ]
            
            result = subprocess.run(
                command,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                logger.info("Successfully processed {}".format(file_name))
                
                # Find the generated transfer file
                today = datetime.now().strftime('%Y-%m-%d')
                transfer_file = os.path.join(OUTPUTS_DIR, "{}_{}.csv".format(playlist_name, today))
                output_file_path = transfer_file
                
                # If ranking is requested, run the popularity ranker
                if rank_by_popularity:
                    logger.info("Ranking playlist by popularity: {}".format(playlist_name))
                    
                    if os.path.exists(transfer_file):
                        # Run the popularity ranker
                        rank_command = [
                            sys.executable,
                            RANKER_SCRIPT,
                            '--source', transfer_file,
                            '--output', "{}_Ranked".format(playlist_name)
                        ]
                        
                        rank_result = subprocess.run(
                            rank_command,
                            capture_output=True,
                            text=True
                        )
                        
                        if rank_result.returncode == 0:
                            logger.info("Successfully ranked playlist by popularity: {}".format(playlist_name))
                            # Update the output file path to the ranked version
                            output_file_path = os.path.join(OUTPUTS_DIR, "{}_Ranked_{}.csv".format(playlist_name, today))
                        else:
                            logger.error("Error ranking playlist: {}".format(rank_result.stderr))
                    else:
                        logger.error("Could not find transfer file for ranking: {}".format(transfer_file))
                
                # Send desktop notification with link to the output folder
                track_count = 0
                try:
                    import pandas as pd
                    if os.path.exists(output_file_path):
                        df = pd.read_csv(output_file_path)
                        track_count = len(df)
                except:
                    pass
                
                # Send notification with the output directory path
                send_desktop_notification(
                    "Playlist Processing Complete",
                    "Processed {} with {} tracks. Click to open folder.".format(file_name, track_count),
                    OUTPUTS_DIR
                )
                
                # Move the file to the processed folder with timestamp
                now = datetime.now().strftime('%Y%m%d_%H%M%S')
                processed_file = os.path.join(ARCHIVE_DIR, "{}_{}.csv".format(os.path.splitext(file_name)[0], now))
                shutil.move(file_path, processed_file)
                logger.info("Moved {} to {}".format(file_name, processed_file))
            else:
                logger.error("Error processing {}: {}".format(file_name, result.stderr))
                
                # Send error notification
                send_desktop_notification(
                    "Playlist Processing Error",
                    "Error processing {}. Check the logs for details.".format(file_name)
                )
        
        except Exception as e:
            logger.error("Error processing file {}: {}".format(file_path, str(e)))
        
        finally:
            self.processing = False

def start_watching():
    """Start watching the custom requests folder"""
    logger.info("Starting to watch folder: {}".format(CUSTOM_REQUESTS_DIR))
    logger.info("Processed files will be moved to: {}".format(ARCHIVE_DIR))
    
    # Process any existing files in the folder first
    existing_files = [
        os.path.join(CUSTOM_REQUESTS_DIR, f) for f in os.listdir(CUSTOM_REQUESTS_DIR)
        if os.path.isfile(os.path.join(CUSTOM_REQUESTS_DIR, f)) and f.lower().endswith('.csv')
    ]
    
    handler = NewFileHandler()
    
    # Process existing files
    if existing_files:
        logger.info("Found {} existing CSV files to process".format(len(existing_files)))
        for file_path in existing_files:
            handler.process_new_file(file_path)
    
    # Set up the file watcher
    observer = Observer()
    observer.schedule(handler, CUSTOM_REQUESTS_DIR, recursive=False)
    observer.start()
    
    try:
        logger.info("Watcher started successfully. Press Ctrl+C to stop.")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        logger.info("Watcher stopped by user")
    
    observer.join()

if __name__ == "__main__":
    print("Starting Custom Requests watcher for folder: {}".format(CUSTOM_REQUESTS_DIR))
    print("Drop CSV files in this folder to automatically process them")
    print("Press Ctrl+C to stop the watcher")
    print("-" * 60)
    
    # Install watchdog if not already installed
    try:
        import watchdog
    except ImportError:
        print("Installing required dependency: watchdog")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "watchdog"])
        print("Dependency installed successfully")
    
    start_watching()
