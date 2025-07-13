#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Prepare Playlists for Transfer Services

This script prepares CSV files for transfer services like Soundiiz or TuneMyMusic
to easily import playlists to streaming services like Deezer, Spotify, etc.

Usage:
    python prepare_playlist_transfer.py [--source SOURCE] [--name NAME]

Arguments:
    --source SOURCE: 'radio' for radio playlists or path to a custom CSV file
    --name NAME: Custom name for the output playlist (default: based on source)

Dependencies:
    - pandas
"""

import os
import sys
import argparse
import pandas as pd
import logging
import shutil
from datetime import datetime

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

# Known artist corrections (format: 'track name': 'correct artist')
ARTIST_CORRECTIONS = {
    # Danish tracks
    'Down Under': 'Men At Work',
    'Mandags-Stævnemøde': 'Ray Dee Ohh',
    'Sømand Af Verden': 'Dodo and The Dodos',
    'Vi ku\' gå hele vejen': 'Blæst',
    'Vi Ku\' Gå Hele Vejen': 'Blæst',
    'Elsker Dig Så Meget': 'Blæst',
    'Du Ligner Din Mor': 'Benjamin Hav ft. Lukas Graham',
    'Du ligner din mor': 'Benjamin Hav ft. Lukas Graham',
    'Hele Vejen': 'Omar ft. Mumle',
    'Up': 'Jonah Blacksmith',
    'Er det mig du elsker?': 'Malte Ebert',
    'Fortæl Mig Hvis Du Vil Noget Andet': 'Malte Ebert',
    'Det sker alt for tit': 'Marcus.wav',
    'Det ønsker jeg for dig': 'Svea S',
    'California Dreamin\'': 'Lord Siva',
    'Smelter under månen': 'APHACA',
    'Luk Mig Ind': 'Annika',
    'Hen til det': 'Karla Korsbak',
    'Love Isn\'t Easy': 'Kind Mod Kind, Medina',
    'Det Modsatte': 'Mumle',
    'En drøm om et menneske': 'APHACA',
    'Blodigt': 'Anton Westerlin, Annika',
    'Gav det et skud': 'August Høyen',
    'Sorry I\'m Here For Someone Else': 'Benson Boone',
    'Entré': 'Anton Westerlin ft. Lamin and ozzy',
    'Lose Yourself': 'Mø',
    'Regntid': 'Tobias Rahim, Kabusa Oriental Choir',
    'Mit ord': 'ozzy',
    'Et sted hvor vi de første': 'APHACA',
    'All For Love': 'Bryan Adams, Rod Stewart and Sting',
    'Alt Det': 'Thor Farlov ft. Noah Carter',
    
    # English tracks
    'Azizam': 'Ed Sheeran',
    'The Summer Is Magic': 'Luvstruck, Carlprit',
    'Ordinary': 'Alex Warren',
    'Beautiful People': 'David Guetta and Sia',
    'One Thing': 'Lola Young',
    'Birds Of A Feather': 'Billie Eilish',
    'Austin': 'Dasha',
    'Belong Together': 'Mark Ambor',
    'Nice To Meet You': 'Myles Smith',
    'Busy Woman': 'Sabrina Carpenter',
    'Anxiety': 'Doechii',
    'Anti-Hero': 'Taylor Swift',
    'End Of The World': 'Miley Cyrus',
    'Abracadabra': 'Lady Gaga',
    'Stargazing': 'Myles Smith',
    'Blessings': 'Calvin Harris, Clementine Douglas',
    'Die With a Smile': 'Bruno Mars, Lady Gaga',
    'Revolving Door': 'Tate McRae',
    'Taste': 'Sabrina Carpenter',
    
    # Moto History playlist specific corrections
    'Happy Boys & Girls': 'Aqua',
    'Boyfriend': 'Alphabeat',
    'Back To The 80\'s': 'Aqua',
    'Barbie Girl': 'Aqua',
    'Kongens Have': 'Bamses Venner',
    'Vimmersvej': 'Bamses Venner',
    'Ring Til Politiet': 'Bring Det På',
    'Tro På Os To': 'DR Big Band & Kommunemanden & Motor Mille',
    'Min Store Kærlighed': 'Hva\' Snakker Du Om? & Anders Matthesen & Bossy Bo',
    'Ramt I Natten': 'Lizzie',
    'Boing!': 'Nik & Jay',
    'Nik Og Jay': 'Nik & Jay',
    'Ondt I Håret': 'Kandis 18',
    'Øde Ø': 'Rasmus Seebach',
    'Jeg Vil La\' Lyset Brænde': 'Ray Dee Ohh',
    'All my love': 'Rocazino',
    'Ridder Lykke': 'Rocazino',
    'All The People In The World': 'Safri Duo & Clark Anderson',
    'Played-A-Live': 'Safri Duo',
    'Taxa': 'Sanne Salomonsen',
    'Gonzo': 'Suspekt',
    'Den Jeg Elsker, Elsker Jeg': 'Søs Fenger, Thomas Helmig, Sanne Salomonsen & Anne Linnet',
    'Ben': 'Tessa',
    'Live Is Life': 'OPUS',
    'Tovepigen': 'Odense Assholes',
    'Bailando': 'Paradisio',
    'Pump Up The Mwaki': '2024 DJ Doolie Mashup',
    'Crazy Little Thing Called Love': 'Queen',
    'APT.': 'ROSÉ & Bruno Mars',
    'Killing In The Name': 'Rage Against The Machine',
    'Lidt I Fem': 'Rasmus Seebach',
    'Livstegn': 'Rasmus Seebach',
    'Children': 'Robert Miles',
    'Superstar': 'Rollergirl',
    'Espresso': 'Sabrina Carpenter',
    'Ecuador': 'Sash!',
    'Sminkedukke Sangen': 'Sminkedukken',
    'Roller Coaster': 'Sugar Station',
    'Pump Up The Jam': 'Technotronic',
    'Lyst Til At Hop\'': 'Tempo & MGP',
    'FuckBoi': 'Ude Af Kontrol',
    'Adam': 'Viro',
    'Boom Boom Boom Boom !!': 'Willy William x Vengaboys',
    'Zididada Day': 'Zididada',
    'Take On Me [Remastered in 4K]': 'a-ha',
}

# Common Danish/English artists for detection
KNOWN_ARTISTS = [
    # Danish artists
    'Blæst', 'Jonah Blacksmith', 'Lord Siva', 'Svea S', 'Malte Ebert', 
    'Burhan G', 'Medina', 'Tobias Rahim', 'Benjamin Hav', 'Lukas Graham',
    'Anton Westerlin', 'Dodo and The Dodos', 'APHACA', 'Annika', 'Mø',
    'Ray Dee Ohh', 'TV-2', 'Jung', 'Tessa', 'Christopher', 'Rasmus Seebach',
    'Guldimund', 'Drew Sycamore', 'Gilli', 'TopGunn', 'Node', 'Barselona',
    'Kesi', 'Suspekt', 'Pil', 'Bisse', 'Jada', 'Katinka', 'Folkeklubben',
    'Danser Med Drenge', 'Kim Larsen', 'C.V. Jørgensen', 'Gasolin', 'Søs Fenger',
    'Thomas Helmig', 'Nephew', 'Dizzy Mizz Lizzy', 'Sort Sol', 'Mew', 'DAD',
    'Anne Linnet', 'Sanne Salomonsen', 'Lis Sørensen', 'Rocazino', 'Dodo & The Dodos',
    
    # International artists
    'Ed Sheeran', 'Billie Eilish', 'Taylor Swift', 'David Guetta', 'Kygo',
    'Miley Cyrus', 'Beyoncé', 'Lady Gaga', 'Bruno Mars', 'The Weeknd',
    'Noah Kahan', 'Post Malone', 'Alex Warren', 'Dasha', 'Mark Ambor',
    'Myles Smith', 'Lola Young', 'Tate McRae', 'Sabrina Carpenter',
    'Doechii', 'Calvin Harris', 'Coldplay', 'Dua Lipa', 'Harry Styles',
    'Justin Bieber', 'Ariana Grande', 'Olivia Rodrigo', 'SZA', 'Drake',
    'Rihanna', 'Eminem', 'Adele', 'Kendrick Lamar', 'Imagine Dragons',
    'Maroon 5', 'Shawn Mendes', 'Lewis Capaldi', 'Elton John', 'Queen',
    'ABBA', 'The Beatles', 'Rolling Stones', 'Fleetwood Mac', 'Eagles',
    'Led Zeppelin', 'Pink Floyd', 'U2', 'Metallica', 'Nirvana', 'Pearl Jam',
    'Red Hot Chili Peppers', 'Foo Fighters', 'Green Day', 'Oasis', 'Radiohead',
    'Arctic Monkeys', 'The Killers', 'Arcade Fire', 'Kings of Leon',
    'Mumford & Sons', 'Florence + The Machine', 'Lana Del Rey', 'Lorde',
    'Men At Work', 'Bryan Adams', 'Rod Stewart', 'Sting', 'Michael Jackson',
    'Madonna', 'Prince', 'Whitney Houston', 'Céline Dion', 'Backstreet Boys',
    'NSYNC', 'Britney Spears', 'Christina Aguilera', 'Jennifer Lopez',
    'Katy Perry', 'P!nk', 'Alicia Keys', 'Usher', 'John Legend', 'Mariah Carey',
]

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
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return pd.DataFrame()
            
        df = pd.read_csv(file_path)
        
        # Check if it's a standard format with 'Track' column (radio playlist)
        if 'Track' in df.columns:
            # If there's a Repeats column, sort by it (highest first)
            if 'Repeats' in df.columns:
                df = df.sort_values('Repeats', ascending=False)
        
        return df
    except Exception as e:
        logger.error(f"Error reading playlist file {file_path}: {str(e)}")
        return pd.DataFrame()

def determine_artist_title(track):
    """Determine the correct artist and title from a track string"""
    # Check if this is a known track with a hardcoded correction
    for track_name, artist in ARTIST_CORRECTIONS.items():
        if track_name in track:
            # Extract the title based on the track name
            parts = track.split(' - ', 1)
            if len(parts) == 2:
                part1, part2 = parts
                if track_name in part1:
                    return artist, track_name
                elif track_name in part2:
                    return artist, track_name
            return artist, track_name
    
    # Standard parsing for tracks in "A - B" format
    parts = track.split(' - ', 1)
    if len(parts) == 2:
        part1, part2 = parts
        part1 = part1.strip()
        part2 = part2.strip()
        
        # Artist recognition heuristics
        part1_is_artist = False
        part2_is_artist = False
        
        # Check against known artists
        for artist in KNOWN_ARTISTS:
            if artist.lower() in part1.lower():
                part1_is_artist = True
                break
            if artist.lower() in part2.lower():
                part2_is_artist = True
                break
        
        # Check for common artist indicators (ft., feat, etc.)
        if any(x in part1.lower() for x in ['ft.', 'feat', 'featuring', 'and', '&', '/', 'vs', 'versus']):
            part1_is_artist = True
        if any(x in part2.lower() for x in ['ft.', 'feat', 'featuring', 'and', '&', '/', 'vs', 'versus']):
            part2_is_artist = True
            
        # Check for numeric patterns in part1 (like "2023 Remix")
        if any(c.isdigit() for c in part1) and len(part1) <= 20:
            part2_is_artist = True
        
        # Make the decision
        if part1_is_artist and not part2_is_artist:
            return part1, part2
        elif part2_is_artist and not part1_is_artist:
            return part2, part1
        else:
            # If we can't determine, assume first part is artist (most common case)
            return part1, part2
    else:
        # If we can't split, return the whole string as title
        return "", track.strip()

def deduplicate_tracks(data):
    """Remove duplicates from the track data in a smart way"""
    if not data:
        return []
        
    # Create a new list for deduplicated tracks
    deduplicated = []
    seen = set()  # Keep track of artist-title combinations we've seen
    seen_titles = {}  # Keep track of titles we've seen for fuzzy matching
    
    # First pass: collect normalized versions for fuzzy matching
    for item in data:
        artist = item.get('Artist', '').strip()
        title = item.get('Title', '').strip()
        
        # Skip entirely empty entries
        if not artist and not title:
            continue
            
        # Normalize title for better duplicate detection
        norm_title = title.lower()
        # Remove special characters, extra spaces and common words that might differ
        for char in ['(', ')', '[', ']', '-', '/', ':', '.', ',']:
            norm_title = norm_title.replace(char, ' ')
        norm_title = ' '.join(word for word in norm_title.split() 
                             if word not in ['feat', 'ft', 'featuring', 'remix', 'edit', 'version', 'radio'])
        norm_title = ' '.join(norm_title.split())  # Remove extra spaces
        
        # Store normalized version
        if norm_title:
            if norm_title in seen_titles:
                seen_titles[norm_title].append((artist, title, item))
            else:
                seen_titles[norm_title] = [(artist, title, item)]
    
    # Second pass: keep only unique tracks
    for norm_title, entries in seen_titles.items():
        # If we have multiple entries with the same normalized title
        if len(entries) > 1:
            # Prioritize entries with both artist and title
            complete_entries = [e for e in entries if e[0] and e[1]]
            if complete_entries:
                # Among complete entries, prefer the first one
                artist, title, item = complete_entries[0]
            else:
                # If no complete entries, take the first one
                artist, title, item = entries[0]
        else:
            # Only one entry with this title
            artist, title, item = entries[0]
        
        # Create the unique key for this artist-title combination
        key = (artist.lower(), norm_title)
        
        # Only add if we haven't seen this exact artist-title combination
        if key not in seen:
            seen.add(key)
            deduplicated.append(item)
    
    # Sort by artist name for nicer presentation
    deduplicated.sort(key=lambda x: x.get('Artist', '').lower())
    return deduplicated

def create_transfer_csv(tracks, output_file):
    """Create a CSV in transfer service format for importing"""
    try:
        # Extract artist and title from the "Track" column
        data = []
        duplicate_count = 0
        
        # Check if this is a radio playlist CSV (with Track column)
        if 'Track' in tracks.columns:
            # Check if this is a custom format with Track,Group columns
            if 'Group' in tracks.columns:
                # This is a custom playlist with Track,Group format
                for track in tracks['Track']:
                    artist, title = determine_artist_title(track)
                    data.append({'Artist': artist, 'Title': title})
            else:
                # Standard radio playlist format
                for track in tracks['Track']:
                    artist, title = determine_artist_title(track)
                    data.append({'Artist': artist, 'Title': title})
        # Check if it's a custom format with Artist and Title columns already
        elif 'Artist' in tracks.columns and 'Title' in tracks.columns:
            # Already in the right format, extract the data
            for _, row in tracks.iterrows():
                data.append({'Artist': row['Artist'], 'Title': row['Title']})
        # Try to handle other formats by assuming columns might be Song and Artist
        elif 'Song' in tracks.columns and 'Artist' in tracks.columns:
            # Extract data with column mapping
            for _, row in tracks.iterrows():
                data.append({'Artist': row['Artist'], 'Title': row['Song']})
        else:
            # Can't determine format, return an error
            logger.error("Unknown CSV format, needs Artist and Title columns or a Track column")
            return False
        
        # Log the original count
        original_count = len(data)
        
        # Deduplicate the data
        deduplicated_data = deduplicate_tracks(data)
        duplicate_count = original_count - len(deduplicated_data)
        
        # Check if an older version of this file exists and remove it
        output_dir = os.path.dirname(output_file)
        base_name = os.path.basename(output_file)
        name_parts = os.path.splitext(base_name)[0].split('_')
        
        # If there's a date at the end, keep only the playlist name part
        playlist_base_name = '_'.join(name_parts[:-1]) if len(name_parts) > 1 and name_parts[-1].startswith('20') else name_parts[0]
        
        # Look for existing files with the same base name
        for existing_file in os.listdir(output_dir):
            if existing_file.startswith(playlist_base_name + '_') and existing_file != base_name and existing_file.endswith('.csv'):
                try:
                    # If it's an older version, remove it
                    if 'Ranked' not in existing_file or ('Ranked' in existing_file and 'Ranked' in base_name):
                        os.remove(os.path.join(output_dir, existing_file))
                        logger.info("Removed older version: {}".format(existing_file))
                except Exception as e:
                    logger.warning("Could not remove older file {}: {}".format(existing_file, str(e)))
        
        # Create DataFrame and save to CSV
        transfer_df = pd.DataFrame(deduplicated_data)
        transfer_df.to_csv(output_file, index=False)
        
        # Log results
        if duplicate_count > 0:
            logger.info("Removed {} duplicate tracks from the playlist".format(duplicate_count))
        logger.info("Created transfer CSV with {} unique tracks: {}".format(len(deduplicated_data), output_file))
        return True
    except Exception as e:
        logger.error("Error creating transfer CSV: {}".format(str(e)))
        return False

def clean_old_files():
    """Clean up old files from previous attempts"""
    try:
        # Remove old files from the root Transfer directory
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        transfer_dir = os.path.join(base_dir, 'Outputs', 'Transfer')
        
        for file in os.listdir(transfer_dir):
            if file.endswith('.csv') and os.path.isfile(os.path.join(transfer_dir, file)):
                try:
                    os.remove(os.path.join(transfer_dir, file))
                except:
                    pass
                    
        # Remove old Deezer integration scripts
        for script in ['create_deezer_playlists.py', 'create_deezer_playlists_browser.py', 'auto_deezer_playlists.py']:
            script_path = os.path.join(base_dir, 'Scripts', script)
            if os.path.exists(script_path):
                try:
                    os.remove(script_path)
                except:
                    pass
                    
        logger.info("Cleaned up old files")
    except Exception as e:
        logger.error(f"Error cleaning old files: {str(e)}")

def prepare_radio_playlists():
    """Prepare CSV files from radio playlists"""
    print("\n--- Prepare Radio Playlists for Transfer ---\n")
    
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
    
    # Create Radio transfer directory
    transfer_dir = os.path.join(base_dir, 'Outputs', 'Transfer', 'Radio')
    os.makedirs(transfer_dir, exist_ok=True)
    
    # Get current date for filenames
    today = datetime.now().strftime('%Y-%m-%d')
    
    # Process Danish tracks
    danish_tracks = None
    if danish_file:
        danish_tracks = read_playlist_file(danish_file)
        if not danish_tracks.empty:
            print(f"Found {len(danish_tracks)} Danish tracks in {os.path.basename(danish_file)}")
            
            # Create transfer format
            danish_transfer_file = os.path.join(transfer_dir, f"Danish_Radio_Hits_{today}.csv")
            create_transfer_csv(danish_tracks, danish_transfer_file)
    
    # Process English tracks
    english_tracks = None
    if english_file:
        english_tracks = read_playlist_file(english_file)
        if not english_tracks.empty:
            print(f"Found {len(english_tracks)} English tracks in {os.path.basename(english_file)}")
            
            # Create transfer format
            english_transfer_file = os.path.join(transfer_dir, f"English_Radio_Hits_{today}.csv")
            create_transfer_csv(english_tracks, english_transfer_file)
    
    print("\nPlaylists prepared for transfer services!")
    print(f"\nFiles created in: {transfer_dir}")
    
    return True

def prepare_custom_playlist(file_path, name=None):
    """Prepare a custom CSV playlist for transfer"""
    print(f"\n--- Prepare Custom Playlist for Transfer ---\n")
    
    # Validate file exists
    if not os.path.exists(file_path):
        print(f"Error: File not found: {file_path}")
        return False
        
    # Get base name if no custom name provided
    if name is None:
        name = os.path.splitext(os.path.basename(file_path))[0]
    
    # Create Custom transfer directory
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    transfer_dir = os.path.join(base_dir, 'Outputs', 'Transfer', 'Custom')
    os.makedirs(transfer_dir, exist_ok=True)
    
    # Read custom playlist
    tracks = read_playlist_file(file_path)
    if tracks.empty:
        print("Error: Could not read playlist or file is empty")
        return False
        
    print(f"Found {len(tracks)} tracks in {os.path.basename(file_path)}")
    
    # Create transfer format
    today = datetime.now().strftime('%Y-%m-%d')
    transfer_file = os.path.join(transfer_dir, f"{name}_{today}.csv")
    
    if create_transfer_csv(tracks, transfer_file):
        print(f"\nPlaylist prepared for transfer services!")
        print(f"File created: {transfer_file}")
        return True
    else:
        print("Error: Failed to create transfer CSV")
        return False

def main():
    """Main function"""
    # Clean up old files and scripts
    clean_old_files()
    
    parser = argparse.ArgumentParser(description='Prepare playlists for transfer services')
    parser.add_argument('--source', help='radio or path to a custom CSV file', default='radio')
    parser.add_argument('--name', help='Custom name for the output playlist')
    
    args = parser.parse_args()
    
    if args.source == 'radio':
        prepare_radio_playlists()
    else:
        prepare_custom_playlist(args.source, args.name)
    
    # Provide transfer instructions
    print("\n--- Transfer Instructions ---\n")
    print("Option 1: Soundiiz (https://soundiiz.com)")
    print("1. Create a free account and log in")
    print("2. Go to 'Upload Playlist'")
    print("3. Select 'Import from a file'")
    print("4. Upload the CSV file")
    print("5. Select the destination (Deezer, Spotify, etc.)")
    
    print("\nOption 2: TuneMyMusic (https://www.tunemymusic.com)")
    print("1. Select 'Source: File'")
    print("2. Upload the CSV file")
    print("3. Select your destination service")
    print("4. Login to your account")
    print("5. Start the transfer")
    
    print("\nTransfer service websites:")
    print("- Soundiiz: https://soundiiz.com/")
    print("- TuneMyMusic: https://www.tunemymusic.com/")

if __name__ == "__main__":
    main()
