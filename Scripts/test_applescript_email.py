#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Test AppleScript Email Script for Radio Playlist System

This script tests the macOS AppleScript email integration by sending a test email.
It uses the same configuration as the updated auto_radio_update.py script.
"""

import os
import sys
import logging
import subprocess
from datetime import datetime
from dotenv import load_dotenv

# Configure basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('test_applescript_email')

# Get base directory path
DIR_PATH = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.abspath(os.path.join(DIR_PATH, '..'))
OUTPUT_DIR = os.path.join(PROJECT_DIR, 'Outputs')
ENV_FILE = os.path.join(PROJECT_DIR, '.env')

# Create output directory if it doesn't exist
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Load environment variables from .env file
if os.path.exists(ENV_FILE):
    load_dotenv(ENV_FILE)
    print(f".env file loaded from: {ENV_FILE}")
else:
    print(f"Warning: .env file not found at: {ENV_FILE}")


def send_test_email():
    """Send a test email using AppleScript via macOS Mail app"""
    try:
        # Get recipient email from environment or use default
        recipient_email = os.environ.get('EMAIL_RECIPIENT', 'gigwebs@gmail.com')
        
        # Create HTML content for the test email
        subject = f"Danish Radio Playlist System Test - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        html_content = f"""
        <html>
        <body>
            <h2>Danish Radio Playlist System - AppleScript Test</h2>
            <p>This is a test email sent via macOS AppleScript.</p>
            <p>If you're receiving this email, the AppleScript email integration is working correctly!</p>
            <p>Sent at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </body>
        </html>
        """
        
        # Save notification as HTML file (for attachment and fallback)
        filename = f"notification_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        filepath = os.path.join(OUTPUT_DIR, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"Created test HTML file: {filepath}")
        
        # Clean the subject to avoid AppleScript errors
        clean_subject = subject.replace("'", "\\'")
        
        # Create AppleScript to send email via Mail app
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
        
        print(f"Sending test email to: {recipient_email}")
        
        # Execute the AppleScript
        process = subprocess.Popen(['osascript', '-e', applescript],
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        
        if process.returncode == 0:
            print(f"Success! Email sent to {recipient_email} via macOS Mail")
            return True
        else:
            error = stderr.decode('utf-8')
            print(f"Error executing AppleScript: {error}")
            return False
            
    except Exception as e:
        print(f"Error sending test email: {str(e)}")
        return False


if __name__ == "__main__":
    print("Testing AppleScript email functionality for Danish Radio Playlist system...")
    send_test_email()
