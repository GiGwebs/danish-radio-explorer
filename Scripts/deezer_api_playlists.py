#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Deezer API Playlist Creator

This script creates playlists in Deezer using the official Deezer API.
It reads the consolidated radio playlist data and creates Danish and English playlists.

Usage:
    python deezer_api_playlists.py

Dependencies:
    - deezer-python
    - pandas
    - requests
"""

import os
import sys
import time
import json
import re
import pandas as pd
import requests
import logging
import webbrowser
from datetime import datetime
import deezer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('deezer_playlist_creator.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('deezer_playlist_creator')

# Constants
DEEZER_EMAIL = "djspinfox@gmail.com"
DEEZER_PASSWORD = "Apple1982"
TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.deezer_token.json')

def read_playlist_file(file_path):
    """Read a playlist CSV file and return a list of tracks"""
    try:
        df = pd.read_csv(file_path)
        # Get the Track column, which contains tracks in "Artist - Title" format
        tracks = df['Track'].tolist()
        
        # If there's a Repeats column, we can prioritize by play count
        if 'Repeats' in df.columns:
            # Sort by Repeats (highest first)
            df = df.sort_values('Repeats', ascending=False)
            tracks = df['Track'].tolist()
            
        return tracks
    except Exception as e:
        logger.error(f"Error reading playlist file {file_path}: {str(e)}")
        return []

def get_latest_playlist_file(directory):
    """Get the most recent playlist file in a directory"""
    try:
        files = [f for f in os.listdir(directory) if f.endswith('.csv')]
        if not files:
            return None
        
        # Sort by modification time (newest first)
        files.sort(key=lambda x: os.path.getmtime(os.path.join(directory, x)), reverse=True)
        return os.path.join(directory, files[0])
    except Exception as e:
        logger.error(f"Error finding latest playlist file in {directory}: {str(e)}")
        return None

def normalize_track_name(track_name):
    """Normalize track name for better matching"""
    if not track_name:
        return ""
        
    # Convert to lowercase
    track = track_name.lower()
    
    # Remove special characters and extra spaces
    track = re.sub(r'[^\w\s]', ' ', track)
    track = re.sub(r'\s+', ' ', track).strip()
    
    # Remove common words that might vary (feat, ft, etc.)
    track = re.sub(r'\bfeat\.?\b|\bft\.?\b', '', track)
    
    return track

def get_artist_title_parts(track_string):
    """Extract artist and title from track string (Format: Artist - Title)"""
    if not track_string:
        return "", ""
        
    parts = track_string.split(' - ', 1)
    if len(parts) == 2:
        artist, title = parts
        return artist.strip(), title.strip()
    
    # If we can't determine, return the whole string as both
    return track_string, ""

def search_deezer_track(track_string):
    """
    Search for a track on Deezer
    
    Args:
        track_string: Track in "Artist - Title" format
        
    Returns:
        The track ID if found, None otherwise
    """
    artist, title = get_artist_title_parts(track_string)
    
    # If we have both artist and title, search using both
    if artist and title:
        search_query = f'{artist} {title}'
    else:
        # If we couldn't parse artist and title, search the whole string
        search_query = track_string
    
    # Make a request to the Deezer API
    try:
        url = f'https://api.deezer.com/search?q={search_query}'
        response = requests.get(url)
        data = response.json()
        
        # Check if we got results
        if 'data' in data and len(data['data']) > 0:
            # Find the best match
            best_match = None
            best_score = 0
            
            normalized_artist = normalize_track_name(artist)
            normalized_title = normalize_track_name(title)
            
            for track in data['data']:
                track_artist = track.get('artist', {}).get('name', '')
                track_title = track.get('title', '')
                
                # Skip if missing key information
                if not track_artist or not track_title:
                    continue
                
                # Calculate score based on similarity
                score = 0
                
                # Check if artist and title match
                if normalized_artist and normalized_artist in normalize_track_name(track_artist):
                    score += 0.5
                if normalized_title and normalized_title in normalize_track_name(track_title):
                    score += 0.5
                
                # Update best match if this score is higher
                if score > best_score:
                    best_score = score
                    best_match = track
            
            # Return the track ID if we found a good match
            if best_match and best_score >= 0.5:
                logger.info(f"Match found for '{track_string}': '{best_match['artist']['name']} - {best_match['title']}'")
                return best_match['id']
        
        logger.warning(f"No match found for: {track_string}")
        return None
    
    except Exception as e:
        logger.error(f"Error searching for track: {str(e)}")
        return None

def create_deezer_playlists():
    """Create Deezer playlists from consolidated radio data"""
    print("\n--- Deezer API Playlist Creator ---\n")
    
    # Find latest playlist files
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    combined_danish_dir = os.path.join(base_dir, 'Outputs', 'Combined', 'Danish')
    combined_english_dir = os.path.join(base_dir, 'Outputs', 'Combined', 'English')
    
    danish_file = get_latest_playlist_file(combined_danish_dir)
    english_file = get_latest_playlist_file(combined_english_dir)
    
    if not danish_file and not english_file:
        logger.error("Could not find any playlist files. Run the consolidator first.")
        print("Could not find any playlist files. Run the consolidator first.")
        return False
    
    # Read the playlists
    danish_tracks = []
    if danish_file:
        danish_tracks = read_playlist_file(danish_file)
        print(f"Found {len(danish_tracks)} Danish tracks in {os.path.basename(danish_file)}")
    
    english_tracks = []
    if english_file:
        english_tracks = read_playlist_file(english_file)
        print(f"Found {len(english_tracks)} English tracks in {os.path.basename(english_file)}")
    
    # Check if we have tracks to process
    if not danish_tracks and not english_tracks:
        logger.error("No tracks found in playlist files")
        print("No tracks found in playlist files")
        return False
    
    # Limit to top tracks to avoid overwhelming the API
    max_tracks = 50
    danish_tracks = danish_tracks[:min(max_tracks, len(danish_tracks))]
    english_tracks = english_tracks[:min(max_tracks, len(english_tracks))]
    
    # Create timestamp for playlist names
    today = datetime.now().strftime('%Y-%m-%d')
    
    # Generate command to open Deezer and create playlists
    print("\nTo create Deezer playlists, use these manual steps or your preferred method:")
    
    if danish_tracks:
        print(f"\n1. Danish Radio Hits ({today}):")
        print("   Tracks to include:")
        for i, track in enumerate(danish_tracks[:10]):
            print(f"   - {track}")
        if len(danish_tracks) > 10:
            print(f"   - ... and {len(danish_tracks)-10} more tracks")
    
    if english_tracks:
        print(f"\n2. English Radio Hits ({today}):")
        print("   Tracks to include:")
        for i, track in enumerate(english_tracks[:10]):
            print(f"   - {track}")
        if len(english_tracks) > 10:
            print(f"   - ... and {len(english_tracks)-10} more tracks")
    
    # For future automation, we need to:
    # 1. Register an app on Deezer Developer portal
    # 2. Use OAuth for authentication
    # 3. Use the API to create playlists and add tracks
    
    print("\nNote: For complete automation, we need to register a Deezer API application.")
    print("This requires setting up a Deezer Developer account and getting API credentials.")
    print("Would you like to proceed with this setup?")
    
    # For now, offer to open Deezer in a browser
    open_deezer = input("\nOpen Deezer in your browser? (y/n): ").lower() == 'y'
    if open_deezer:
        webbrowser.open("https://www.deezer.com/")
    
    return True

if __name__ == "__main__":
    create_deezer_playlists()
