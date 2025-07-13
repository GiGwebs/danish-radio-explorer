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
