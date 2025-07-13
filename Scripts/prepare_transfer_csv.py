#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Prepare Transfer CSV Files

This script prepares CSV files formatted for services like Soundiiz or TuneMyMusic 
to easily transfer radio playlists to Deezer.

Usage:
    python prepare_transfer_csv.py

Dependencies:
    - pandas
"""

import os
import sys
import pandas as pd
import logging
from datetime import datetime
import webbrowser

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('playlist_transfer.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('playlist_transfer')

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

def read_playlist_file(file_path):
    """Read a playlist CSV file and return a DataFrame"""
    try:
        df = pd.read_csv(file_path)
        
        # If there's a Repeats column, sort by it (highest first)
        if 'Repeats' in df.columns:
            df = df.sort_values('Repeats', ascending=False)
            
        return df
    except Exception as e:
        logger.error(f"Error reading playlist file {file_path}: {str(e)}")
        return pd.DataFrame()

def create_soundiiz_format(tracks, output_file, max_tracks=None):
    """Create a CSV in Soundiiz format for importing"""
    try:
        # Extract artist and title from the "Track" column
        data = []
        
        # Limit the number of tracks if specified
        if max_tracks:
            tracks_to_process = tracks.head(max_tracks)
        else:
            tracks_to_process = tracks
        
        for track in tracks_to_process['Track']:
            parts = track.split(' - ', 1)
            if len(parts) == 2:
                part1, part2 = parts
                
                # Common Danish/English artist patterns to help with detection
                known_artists = [
                    'Ed Sheeran', 'Billie Eilish', 'Taylor Swift', 'David Guetta', 'Kygo',
                    'Miley Cyrus', 'Beyoncé', 'Lady Gaga', 'Bruno Mars', 'The Weeknd',
                    'Blæst', 'Jonah Blacksmith', 'Lord Siva', 'Svea S', 'Malte Ebert', 
                    'Burhan G', 'Medina', 'Tobias Rahim', 'Benjamin Hav', 'Lukas Graham',
                    'Anton Westerlin', 'Dodo and The Dodos', 'APHACA', 'Annika', 'Mø',
                    'Noah Kahan', 'Post Malone', 'Alex Warren', 'Ray Dee Ohh', 'TV-2'
                ]
                
                # Artist recognition heuristics
                part1_is_artist = False
                part2_is_artist = False
                
                # Check against known artists
                for artist in known_artists:
                    if artist.lower() in part1.lower():
                        part1_is_artist = True
                    if artist.lower() in part2.lower():
                        part2_is_artist = True
                
                # Check for common artist indicators (ft., feat, etc.)
                if any(x in part1.lower() for x in ['ft.', 'feat', 'featuring', 'and', '&', '/']):
                    part1_is_artist = True
                if any(x in part2.lower() for x in ['ft.', 'feat', 'featuring', 'and', '&', '/']):
                    part2_is_artist = True
                
                # Make the decision
                if part1_is_artist and not part2_is_artist:
                    artist, title = part1, part2
                elif part2_is_artist and not part1_is_artist:
                    artist, title = part2, part1
                else:
                    # If we can't determine, assume first part is artist (most common case)
                    artist, title = part1, part2
                
                data.append({'Artist': artist.strip(), 'Title': title.strip()})
            else:
                # If we can't split, use the whole string as title
                data.append({'Artist': '', 'Title': track.strip()})
        
        # Create DataFrame and save to CSV
        soundiiz_df = pd.DataFrame(data)
        soundiiz_df.to_csv(output_file, index=False)
        logger.info(f"Created Soundiiz-format CSV: {output_file}")
        return True
    except Exception as e:
        logger.error(f"Error creating Soundiiz format: {str(e)}")
        return False

def create_tunemymusic_format(tracks, output_file, max_tracks=None):
    """Create a CSV in TuneMyMusic format for importing"""
    try:
        # Extract artist and title from the "Track" column
        data = []
        
        # Limit the number of tracks if specified
        if max_tracks:
            tracks_to_process = tracks.head(max_tracks)
        else:
            tracks_to_process = tracks
        
        for track in tracks_to_process['Track']:
            parts = track.split(' - ', 1)
            if len(parts) == 2:
                part1, part2 = parts
                
                # Common Danish/English artist patterns to help with detection
                known_artists = [
                    'Ed Sheeran', 'Billie Eilish', 'Taylor Swift', 'David Guetta', 'Kygo',
                    'Miley Cyrus', 'Beyoncé', 'Lady Gaga', 'Bruno Mars', 'The Weeknd',
                    'Blæst', 'Jonah Blacksmith', 'Lord Siva', 'Svea S', 'Malte Ebert', 
                    'Burhan G', 'Medina', 'Tobias Rahim', 'Benjamin Hav', 'Lukas Graham',
                    'Anton Westerlin', 'Dodo and The Dodos', 'APHACA', 'Annika', 'Mø',
                    'Noah Kahan', 'Post Malone', 'Alex Warren', 'Ray Dee Ohh', 'TV-2'
                ]
                
                # Artist recognition heuristics
                part1_is_artist = False
                part2_is_artist = False
                
                # Check against known artists
                for artist in known_artists:
                    if artist.lower() in part1.lower():
                        part1_is_artist = True
                    if artist.lower() in part2.lower():
                        part2_is_artist = True
                
                # Check for common artist indicators (ft., feat, etc.)
                if any(x in part1.lower() for x in ['ft.', 'feat', 'featuring', 'and', '&', '/']):
                    part1_is_artist = True
                if any(x in part2.lower() for x in ['ft.', 'feat', 'featuring', 'and', '&', '/']):
                    part2_is_artist = True
                
                # Make the decision
                if part1_is_artist and not part2_is_artist:
                    artist, title = part1, part2
                elif part2_is_artist and not part1_is_artist:
                    artist, title = part2, part1
                else:
                    # If we can't determine, assume first part is artist (most common case)
                    artist, title = part1, part2
                
                data.append({'Song': title.strip(), 'Artist': artist.strip()})
            else:
                # If we can't split, use the whole string as title
                data.append({'Song': track.strip(), 'Artist': ''})
        
        # Create DataFrame and save to CSV
        tunemymusic_df = pd.DataFrame(data)
        tunemymusic_df.to_csv(output_file, index=False)
        logger.info(f"Created TuneMyMusic-format CSV: {output_file}")
        return True
    except Exception as e:
        logger.error(f"Error creating TuneMyMusic format: {str(e)}")
        return False

def prepare_transfer_files():
    """Main function to prepare transfer CSV files"""
    print("\n--- Prepare CSV Files for Deezer Transfer ---\n")
    
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
    
    # Create transfer directory
    transfer_dir = os.path.join(base_dir, 'Outputs', 'Transfer')
    os.makedirs(transfer_dir, exist_ok=True)
    
    # Get current date for filenames
    today = datetime.now().strftime('%Y-%m-%d')
    
    # Process Danish tracks
    danish_tracks = None
    if danish_file:
        danish_tracks = read_playlist_file(danish_file)
        if not danish_tracks.empty:
            print(f"Found {len(danish_tracks)} Danish tracks in {os.path.basename(danish_file)}")
            
            # Create Soundiiz format
            soundiiz_danish_file = os.path.join(transfer_dir, f"Danish_Radio_Hits_{today}_Soundiiz.csv")
            create_soundiiz_format(danish_tracks, soundiiz_danish_file)
            
            # Create TuneMyMusic format
            tunemymusic_danish_file = os.path.join(transfer_dir, f"Danish_Radio_Hits_{today}_TuneMyMusic.csv")
            create_tunemymusic_format(danish_tracks, tunemymusic_danish_file)
    
    # Process English tracks
    english_tracks = None
    if english_file:
        english_tracks = read_playlist_file(english_file)
        if not english_tracks.empty:
            print(f"Found {len(english_tracks)} English tracks in {os.path.basename(english_file)}")
            
            # Create Soundiiz format
            soundiiz_english_file = os.path.join(transfer_dir, f"English_Radio_Hits_{today}_Soundiiz.csv")
            create_soundiiz_format(english_tracks, soundiiz_english_file)
            
            # Create TuneMyMusic format
            tunemymusic_english_file = os.path.join(transfer_dir, f"English_Radio_Hits_{today}_TuneMyMusic.csv")
            create_tunemymusic_format(english_tracks, tunemymusic_english_file)
    
    # Provide instructions
    print("\nCSV files prepared for transfer services!")
    print(f"\nFiles created in: {transfer_dir}")
    
    print("\n--- Transfer Instructions ---")
    print("\nOption 1: Soundiiz (https://soundiiz.com)")
    print("1. Create a free account and log in")
    print("2. Go to 'Upload Playlist'")
    print("3. Select 'Import from a file'")
    print("4. Upload the *_Soundiiz.csv files")
    print("5. Convert to Deezer")
    
    print("\nOption 2: TuneMyMusic (https://www.tunemymusic.com)")
    print("1. Select 'Source: File'")
    print("2. Upload the *_TuneMyMusic.csv files")
    print("3. Select 'Destination: Deezer'")
    print("4. Login to your Deezer account")
    print("5. Start the transfer")
    
    # Provide links to transfer services
    print("\nTransfer service websites:")
    print("- Soundiiz: https://soundiiz.com/")
    print("- TuneMyMusic: https://www.tunemymusic.com/")
    print("\nVisit either site to transfer your playlists to Deezer")
    
    return True

if __name__ == "__main__":
    prepare_transfer_files()
