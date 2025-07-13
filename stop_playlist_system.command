#!/bin/bash

# Stop script for Playlist Processing System
# This script stops the custom requests watcher running in the background

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check if the PID file exists
if [ -f "$SCRIPT_DIR/Logs/watcher.pid" ]; then
    PID=$(cat "$SCRIPT_DIR/Logs/watcher.pid")
    
    # Check if the process is still running
    if ps -p $PID > /dev/null; then
        echo "Stopping Custom Requests Watcher (PID: $PID)..."
        kill $PID
        
        # Wait a moment to confirm it's stopped
        sleep 1
        
        if ps -p $PID > /dev/null; then
            echo "Warning: Process didn't stop immediately, forcing termination..."
            kill -9 $PID
        fi
        
        echo "Watcher stopped successfully!"
    else
        echo "Watcher process is not running (PID: $PID)"
    fi
    
    # Remove the PID file
    rm "$SCRIPT_DIR/Logs/watcher.pid"
else
    echo "No watcher PID file found. The watcher may not be running."
fi

echo ""
echo "==================== Playlist System Stopped ===================="
echo "To restart the system:"
echo "  Run ./start_playlist_system.command"
echo "=============================================================="

# Keep the terminal window open
read -p "Press Enter to close this window..."
