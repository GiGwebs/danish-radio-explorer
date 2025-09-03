#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function
import requests
import json
import csv
import sys
import codecs
import re
import time
from datetime import datetime, timedelta
from langdetect import detect
from bs4 import BeautifulSoup
import pandas as pd
import os

def get_nova_playlist(date_str):
    """Fetch playlist data for a specific date from OnlineRadioBox."""
    print("Fetching data for {}".format(date_str))
    
    # Format date for URL if needed
    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
    formatted_date = date_obj.strftime('%Y-%m-%d')
    
    # OnlineRadioBox stores recent playlist data (up to 7 days)
    url = "https://onlineradiobox.com/dk/nova/playlist/{}?lang=en".format(formatted_date)
    print("URL: {}".format(url))
    
    # Add retry mechanism with exponential backoff for 429 errors
    max_retries = 5
    retry_delay = 2
    
    # Try to fetch real data from OnlineRadioBox
    for attempt in range(max_retries):
        try:
            response = requests.get(url)
            print("Response status code: {}".format(response.status_code))
            if response.status_code == 200:
                # Parse the HTML to extract playlist data
                soup = BeautifulSoup(response.text, 'html.parser')
                playlist_data = []
                
                # Each track is a link in the playlist section
                playlist_entries = soup.find_all('a', href=lambda href: href and '/track/' in href)
                
                # Look for timestamps - they're near each track
                timestamps = []
                for time_text in soup.get_text().split():
                    if re.match(r'\d{2}:\d{2}', time_text):
                        timestamps.append(time_text)
                
                # Also look for tracks without links (some songs might not have links)
                non_linked_tracks = []
                text_content = soup.get_text()
                lines = text_content.split('\n')
                for line in lines:
                    if re.match(r'\d{2}:\d{2}\s+[^\d]+', line):
                        # This line likely contains a track without a link
                        non_linked_tracks.append(line.strip())
                
                # Process the linked tracks
                for i, track_link in enumerate(playlist_entries):
                    if i < len(timestamps):
                        # Get the track text - usually "Title - Artist"
                        track_text = track_link.get_text().strip()
                        if ' - ' in track_text:
                            artist = track_text.split(' - ')[1].strip()
                            title = track_text.split(' - ')[0].strip()
                            
                            playlist_data.append({
                                'eventTime': timestamps[i],
                                'nowPlayingTrack': title,
                                'nowPlayingArtist': artist
                            })
                
                # Process any non-linked tracks
                for track_line in non_linked_tracks:
                    match = re.match(r'(\d{2}:\d{2})\s+(.+)', track_line)
                    if match:
                        time_str = match.group(1)
                        track_info = match.group(2).strip()
                        
                        if ' - ' in track_info:
                            artist = track_info.split(' - ')[1].strip()
                            title = track_info.split(' - ')[0].strip()
                            
                            # Check if this time/track is already in the playlist
                            if not any(item['eventTime'] == time_str for item in playlist_data):
                                playlist_data.append({
                                    'eventTime': time_str,
                                    'nowPlayingTrack': title,
                                    'nowPlayingArtist': artist
                                })
                
                print("Successfully extracted {} tracks from OnlineRadioBox".format(len(playlist_data)))
                return playlist_data
                
            elif response.status_code == 429:
                # Too many requests, back off and retry
                retry_delay *= 2  # Exponential backoff
                print("Rate limited (429). Backing off for {} seconds...".format(retry_delay))
                time.sleep(retry_delay)
            else:
                print("Error fetching data for {}: HTTP {}".format(date_str, response.status_code))
                return None
        except Exception as e:
            print("Exception when fetching data for {}: {}".format(date_str, e))
            return None
    
    print("Max retries exceeded for {}".format(date_str))
    return None

def is_english(text):
    """Detect if text is in English language."""
    # Ensure text is a str
    if isinstance(text, bytes):
        text = text.decode('utf-8', errors='ignore')
        
    # Check for Danish-specific characters
    danish_chars = [u'æ', u'ø', u'å', u'Æ', u'Ø', u'Å']
    has_danish_chars = any(char in text for char in danish_chars)
    
    # If it has Danish characters, it's probably not English
    if has_danish_chars:
        return False
    
    # Attempt language detection
    try:
        detected_lang = detect(text)
        return detected_lang == 'en'
    except Exception:
        # Default to not English if detection fails
        return False

def process_nova_data_for_2024():
    """Process NOVA Radio data for 2024 (Jan 1 through Dec 31), extracting English titles."""
    # Date range for 2024 (Jan 1 through Dec 31)
    start_date = datetime(2024, 1, 1)
    end_date = datetime(2024, 12, 31)
    current_date = start_date
    
    # Store qualifying tracks
    english_tracks = []
    days_processed = 0
    total_days = (end_date - start_date).days + 1
    
    print("\nProcessing {} days from {} to {}".format(
        total_days, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')))
    
    # Process each day in 2024
    while current_date <= end_date:
        date_str = current_date.strftime('%Y-%m-%d')
        days_processed += 1
        print("\nProcessing date: {} ({}/{} - {}%)".format(
            date_str, days_processed, total_days, int(days_processed * 100 / total_days)))
        
        # Get playlist data
        playlist_data = get_nova_playlist(date_str)
        
        if playlist_data:
            # Extract tracks with English titles
            for item in playlist_data:
                if 'nowPlayingTrack' in item and 'nowPlayingArtist' in item and 'eventTime' in item:
                    title = item['nowPlayingTrack']
                    artist = item['nowPlayingArtist']
                    event_time = item['eventTime']
                    
                    # Check if title is in English
                    if title and is_english(title):
                        english_tracks.append({
                            'Date': date_str,
                            'Time': event_time,  # Keep time temporarily for sorting
                            'Title': title,
                            'Artist': artist
                        })
        
        # Move to next day
        current_date += timedelta(days=1)
        time.sleep(1)  # Be nice to the API
    
    return english_tracks

def save_to_csv(tracks, filename):
    """Save processed tracks to CSV file."""
    if not tracks:
        print("No English tracks found")
        return False
    
    # Convert to DataFrame for easier processing
    df = pd.DataFrame(tracks)
    
    # Sort by Date and Time
    df = df.sort_values(['Date', 'Time'])
    
    # Remove the Time column (only used for sorting)
    df = df.drop('Time', axis=1)
    
    # Remove duplicates
    df = df.drop_duplicates()
    
    # Save to CSV
    df.to_csv(filename, index=False, encoding='utf-8')
    
    return True

def summarize_tracks(input_csv, output_csv):
    """Summarize tracks by counting occurrences."""
    # Read the CSV file
    df = pd.read_csv(input_csv)
    
    # Create a list of "Artist - Title" strings
    artist_title_list = []
    for _, row in df.iterrows():
        artist_title = "{} - {}".format(row['Artist'], row['Title'])
        artist_title_list.append(artist_title)
    
    # Count occurrences and create a new DataFrame
    track_counts = {}
    for track in artist_title_list:
        if track in track_counts:
            track_counts[track] += 1
        else:
            track_counts[track] = 1
    
    # Convert to DataFrame and sort
    summary_df = pd.DataFrame({
        'Track': list(track_counts.keys()),
        'Repeats': list(track_counts.values())
    })
    summary_df = summary_df.sort_values('Repeats', ascending=False)
    
    # Save to CSV
    summary_df.to_csv(output_csv, index=False, encoding='utf-8')
    
    return len(summary_df)

def main():
    print("Starting NOVA Radio English titles extraction for 2024...")
    print("This will process data from January 1 to December 31, 2024")
    
    # Set up file paths with better organization
    # Use relative paths to work from any directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.abspath(os.path.join(script_dir, '../..'))
    
    # Extract the year from the date range for folder organization
    start_year = "2024"
    
    # Ensure year directories exist
    year_dirs = [
        os.path.join(project_dir, "Outputs/English/{}".format(start_year)),
        os.path.join(project_dir, "Outputs/Archive/{}".format(start_year))
    ]
    for year_dir in year_dirs:
        if not os.path.exists(year_dir):
            os.makedirs(year_dir)
    
    # Set up output file paths
    date_range = "{}_to_{}".format("2024-01-01", "2024-12-31")
    raw_output = os.path.join(project_dir, "Outputs/Archive/{}/NOVA_English_Raw_{}.csv".format(start_year, date_range))
    summary_output = os.path.join(project_dir, "Outputs/English/{}/NOVA_English_Titles_{}.csv".format(start_year, date_range))
    
    # Extract English tracks
    english_tracks = process_nova_data_for_2024()
    success = save_to_csv(english_tracks, raw_output)
    
    if success:
        print("SUCCESS! Raw English tracks saved to: {}".format(raw_output))
        
        # Summarize the tracks
        unique_count = summarize_tracks(raw_output, summary_output)
        print("Summarized {} unique English tracks to: {}".format(unique_count, summary_output))
        
        # Print a sample of the summarized tracks
        try:
            summary_df = pd.read_csv(summary_output)
            print("\nSample of English tracks (most repeated first):")
            print(summary_df.head(10).to_string(index=False))
            print("\nTotal unique English tracks: {}".format(len(summary_df)))
        except Exception as e:
            print("Error displaying summary: {}".format(e))

if __name__ == "__main__":
    main()
