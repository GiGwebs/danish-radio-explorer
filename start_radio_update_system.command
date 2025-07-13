#!/bin/bash

# Auto-start script for Radio Playlist Update System
# This script sets up weekly automatic updates of radio playlists

# Make sure script runs properly regardless of how it's executed
set -e  # Exit immediately if a command fails

# Explicitly set PATH to include common locations
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

# Get the directory where this script is located - this works regardless of execution method
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    # Script is being executed directly
    SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
else
    # Script is being sourced
    SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
fi

# Change to the script directory and verify the change worked
echo "Changing to directory: $SCRIPT_DIR"
cd "$SCRIPT_DIR" || {
    echo "Error: Could not change to directory $SCRIPT_DIR"
    echo "Please run this script from the correct location or check permissions"
    exit 1
}

# Make the logs directory if it doesn't exist
mkdir -p "$SCRIPT_DIR/Logs"

# Ensure we have all required directories
mkdir -p "$SCRIPT_DIR/Outputs/Archive"
mkdir -p "$SCRIPT_DIR/Outputs/New_Tracks"

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Set up the weekly launchd job for Sunday at 3:00 AM (or when computer wakes up)
echo "Setting up weekly automated radio update (Sundays at 3:00 AM)"

# Create LaunchAgent directory if it doesn't exist
LAUNCH_AGENT_DIR="$HOME/Library/LaunchAgents"
mkdir -p "$LAUNCH_AGENT_DIR"

# Create a unique identifier for our LaunchAgent
LAUNCH_AGENT_ID="com.radioplaylists.autoupdate"
LAUNCH_AGENT_FILE="$LAUNCH_AGENT_DIR/$LAUNCH_AGENT_ID.plist"

# Create the launchd plist file
cat > "$LAUNCH_AGENT_FILE" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LAUNCH_AGENT_ID</string>
    <key>ProgramArguments</key>
    <array>
        <string>$SCRIPT_DIR/venv/bin/python</string>
        <string>$SCRIPT_DIR/Scripts/auto_radio_update.py</string>
        <string>--notify-email</string>
        <string>djspinfox@gmail.com</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>9</integer>
        <key>Minute</key>
        <integer>0</integer>
        <key>Weekday</key>
        <integer>0</integer>
    </dict>
    <key>WorkingDirectory</key>
    <string>$SCRIPT_DIR</string>
    <key>StandardOutPath</key>
    <string>$SCRIPT_DIR/Logs/auto_radio_update_launchd.log</string>
    <key>StandardErrorPath</key>
    <string>$SCRIPT_DIR/Logs/auto_radio_update_launchd_error.log</string>
    <key>RunAtLoad</key>
    <false/>
    <key>StartOnMount</key>
    <false/>
</dict>
</plist>
EOF

# Unload any existing instance
launchctl unload "$LAUNCH_AGENT_FILE" 2>/dev/null

# Load the LaunchAgent
launchctl load "$LAUNCH_AGENT_FILE"

echo "Weekly radio update job added as LaunchAgent"
echo "This will run every Sunday at 9:00 AM or when the computer wakes up after a missed run"

# Write a backup check script to run at login
LOGIN_CHECK_SCRIPT="$SCRIPT_DIR/Scripts/check_missed_updates.py"

cat > "$LOGIN_CHECK_SCRIPT" << EOF
#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Check for missed radio updates and run if needed.
This script checks when the last update ran and runs it if more than 7 days have passed.
"""

import os
import sys
import time
import datetime
import subprocess
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('missed_updates.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('missed_updates')

# Base paths
BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
LAST_RUN_FILE = os.path.join(BASE_DIR, 'Logs', 'last_radio_update.txt')
UPDATE_SCRIPT = os.path.join(BASE_DIR, 'Scripts', 'auto_radio_update.py')

def check_and_run():
    """Check if we missed an update and run if needed"""
    try:
        now = datetime.datetime.now()
        
        # Get the last run time
        last_run_time = None
        if os.path.exists(LAST_RUN_FILE):
            try:
                with open(LAST_RUN_FILE, 'r') as f:
                    last_run_str = f.read().strip()
                    last_run_time = datetime.datetime.strptime(last_run_str, '%Y-%m-%d %H:%M:%S')
            except Exception as e:
                logger.error(f"Error reading last run time: {str(e)}")
        
        # If never run or more than 7 days passed, run now
        if last_run_time is None or (now - last_run_time).days >= 7:
            logger.info(f"Last run was more than 7 days ago or never. Running update now.")
            
            # Run the update script
            subprocess.Popen(
                [sys.executable, UPDATE_SCRIPT, '--force'],
                start_new_session=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Update last run time
            with open(LAST_RUN_FILE, 'w') as f:
                f.write(now.strftime('%Y-%m-%d %H:%M:%S'))
                
            return True
        else:
            logger.info(f"Last run was on {last_run_time}, no need to run now.")
            return False
    except Exception as e:
        logger.error(f"Error checking missed updates: {str(e)}")
        return False

if __name__ == "__main__":
    check_and_run()
EOF

# Make the check script executable
chmod +x "$LOGIN_CHECK_SCRIPT"

# Add the check script to login items to run at startup
LOGIN_ITEMS_PLIST="$LAUNCH_AGENT_DIR/com.radioplaylists.checkupdates.plist"

cat > "$LOGIN_ITEMS_PLIST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.radioplaylists.checkupdates</string>
    <key>ProgramArguments</key>
    <array>
        <string>$SCRIPT_DIR/venv/bin/python</string>
        <string>$LOGIN_CHECK_SCRIPT</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>WorkingDirectory</key>
    <string>$SCRIPT_DIR</string>
    <key>StandardOutPath</key>
    <string>$SCRIPT_DIR/Logs/check_updates.log</string>
    <key>StandardErrorPath</key>
    <string>$SCRIPT_DIR/Logs/check_updates_error.log</string>
    <key>ProcessType</key>
    <string>Background</string>
    <key>AbandonProcessGroup</key>
    <true/>
    <key>LaunchOnlyOnce</key>
    <true/>
</dict>
</plist>
EOF

# Unload any existing instance
launchctl unload "$LOGIN_ITEMS_PLIST" 2>/dev/null

# Load the LaunchAgent
launchctl load "$LOGIN_ITEMS_PLIST"

echo "Added login check for missed updates"

# Run the update once immediately if user wants
echo ""
echo "==================== Radio Update System Setup ===================="
echo "Weekly radio playlist update has been scheduled"
echo "System will automatically run every Sunday at 9:00 AM"
echo "If your computer is asleep at that time, it will run when it wakes up"
echo "Updates will be sent to: djspinfox@gmail.com"
echo ""
echo "No need to run an update now if you don't want to. The system is already set up."
echo "Setup is complete and the system will run automatically."
echo ""
echo "If you do want to run a manual update now, type 'y' and press Enter. Otherwise press Enter to finish setup."
read -r RUN_NOW

if [[ "$RUN_NOW" =~ ^[Yy]$ ]]; then
    echo "Running radio update now..."
    python "$SCRIPT_DIR/Scripts/auto_radio_update.py" --force
else
    echo "Setup complete. The system will run automatically on schedule."
fi

echo ""
echo "You can check the status of scheduled jobs with: launchctl list | grep radioplaylists"
echo "You can run a manual update anytime with: python Scripts/auto_radio_update.py --force"
echo "=============================================================="

# Keep the terminal window open
read -p "Press Enter to close this window..."
