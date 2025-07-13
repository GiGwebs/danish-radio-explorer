#!/bin/bash

# Auto-start script for Playlist Processing System
# This script starts the custom requests watcher in the background

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

# Kill any existing watcher processes
pid_file="$SCRIPT_DIR/Logs/watcher.pid"
if [ -f "$pid_file" ]; then
    old_pid=$(cat "$pid_file")
    if ps -p "$old_pid" > /dev/null; then
        echo "Stopping existing watcher process (PID: $old_pid)..."
        kill "$old_pid" 2>/dev/null
        sleep 1
    fi
fi

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Make the logs directory if it doesn't exist
mkdir -p "$SCRIPT_DIR/Logs"

# Clean up duplicate files in output folder
python -c "
import os
import glob

# Define paths
output_dir = '$SCRIPT_DIR/Outputs/Transfer/Custom'
os.makedirs(output_dir, exist_ok=True)
os.chdir(output_dir)

# Get all CSV files
all_files = glob.glob('*.csv')

# Group files by base name (without date)
file_groups = {}
for filename in all_files:
    base_name = filename.split('_20')[0] if '_20' in filename else filename.split('.')[0]
    if base_name not in file_groups:
        file_groups[base_name] = []
    file_groups[base_name].append(filename)

# For each group, keep only the most recent file
for base_name, files in file_groups.items():
    if len(files) > 1:
        # Sort by modification time, newest first
        files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        # Keep the newest file
        keep_file = files[0]
        print(f'Keeping newest file: {keep_file}')
        # Remove older files
        for file in files[1:]:
            os.remove(file)
            print(f'Removed older duplicate: {file}')
"

# Start the watcher in the background and redirect output to a log file
echo "Starting Custom Requests Watcher..."
python "$SCRIPT_DIR/Scripts/watch_custom_requests.py" > "$SCRIPT_DIR/Logs/watcher_$(date +%Y%m%d).log" 2>&1 &

# Save the process ID for potential shutdown later
echo $! > "$SCRIPT_DIR/Logs/watcher.pid"

# Open the Custom Requests folder to make it easy to drop files
open "$SCRIPT_DIR/Custom Requests"

# Provide user feedback
echo ""
echo "==================== Playlist System Started ===================="
echo "Custom Requests Watcher is now running in the background"
echo "Process ID: $(cat "$SCRIPT_DIR/Logs/watcher.pid")"
echo ""
echo "To add a new playlist for processing:"
echo "  Simply drop a CSV file into the Custom Requests folder that just opened"
echo "  Files will be automatically processed and placed in Outputs/Transfer/Custom"
echo ""
echo "The watcher will keep running even if you close this window"
echo "To stop it later, run the stop_playlist_system.command file"
echo "=============================================================="

# Keep the terminal window open for a few seconds to show the message
sleep 5
