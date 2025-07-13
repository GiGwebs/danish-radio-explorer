#!/bin/bash

# Simple wrapper script for the playlist system
# This is designed to be easier to run from the terminal

# Full path to the actual script
SCRIPT_PATH="/Users/gigwebs/Library/CloudStorage/Dropbox/MUSIC BANK/Rekordbox Scouts/Rekordbox Filter/Radio Filter/start_playlist_system.command"

# Ensure the script is executable
chmod +x "$SCRIPT_PATH"

# Run the script
echo "Starting playlist system..."
"$SCRIPT_PATH"
