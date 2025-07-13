#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Test Email Script for Radio Playlist System

This script tests the Gmail SMTP email configuration by sending a test email.
It uses the same configuration as the main auto_radio_update.py script.
"""

import os
import sys
import smtplib
import logging
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

# Configure basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('test_email')

# Load environment variables from .env file
DIR_PATH = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.abspath(os.path.join(DIR_PATH, '..'))
ENV_FILE = os.path.join(PROJECT_DIR, '.env')

print(f"Looking for .env file at: {ENV_FILE}")
if os.path.exists(ENV_FILE):
    print(f".env file found at: {ENV_FILE}")
    load_dotenv(ENV_FILE)
else:
    print(f"ERROR: .env file not found at: {ENV_FILE}")

def send_test_email():
    """Send a test email using the configured SMTP settings"""
    try:
        # Get email configuration from environment variables
        sender_email = os.environ.get('EMAIL_SENDER')
        sender_password = os.environ.get('EMAIL_PASSWORD')
        recipient_email = os.environ.get('EMAIL_RECIPIENT')
        
        if not sender_email or not sender_password or not recipient_email:
            logger.error("Missing email configuration in .env file")
            logger.info("Please ensure EMAIL_SENDER, EMAIL_PASSWORD, and EMAIL_RECIPIENT are set")
            return False
            
        logger.info(f"Sending test email from {sender_email} to {recipient_email}")
        
        # Create email message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"Radio Playlist System Test Email - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        msg['From'] = sender_email
        msg['To'] = recipient_email
        
        # Create email content
        html_content = f"""
        <html>
        <body>
            <h2>Danish Radio Playlist System - Test Email</h2>
            <p>This is a test email sent from the Danish Radio Playlist extraction system.</p>
            <p>If you're receiving this email, the SMTP configuration is working correctly!</p>
            <p>Sent at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(html_content, 'html'))
        
        # Connect to Gmail SMTP server and send email
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            logger.info("Connecting to Gmail SMTP server...")
            server.login(sender_email, sender_password)
            logger.info("Successfully authenticated with Gmail")
            server.send_message(msg)
            logger.info("Email sent successfully!")
            
        return True
        
    except Exception as e:
        logger.error(f"Error sending test email: {str(e)}")
        return False

if __name__ == "__main__":
    print("Testing email functionality for Danish Radio Playlist system...")
    print("Using configuration from .env file")
    send_test_email()
