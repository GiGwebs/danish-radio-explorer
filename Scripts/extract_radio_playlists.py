#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function
import requests
import json
import csv
import sys
import codecs
import re
import os
from datetime import datetime, timedelta
from langdetect import detect
from bs4 import BeautifulSoup
import pandas as pd

# Ensure UTF-8 encoding for Python 2.7
if sys.version_info[0] < 3:
    reload(sys)
    sys.setdefaultencoding('utf-8')

# Dictionary mapping station name to OnlineRadioBox identifier
STATION_MAP = {
    'NOVA': 'nova',              # NOVA FM
    'P3': 'drp3',                # DR P3
    'TheVoice': 'thevoice',      # The Voice - popular commercial station
    'Radio100': 'radio100',      # Radio 100 - major adult contemporary station
    'PartyFM': 'partyfm',        # Party FM - niche station with dedicated following
    'RadioGlobus': 'radioglobus',# Radio Globus
    'SkalaFM': 'skalafm',        # Skala FM
    'P4': 'drp4kobenhavn',       # DR P4 Copenhagen
    'PopFM': 'poppremium',       # Pop FM
    'RBClassics': 'rbclassics'   # R&B Classics
}

# URLs for each station's playlist on OnlineRadioBox
STATION_URLS = {
    'NOVA': 'https://onlineradiobox.com/dk/nova/playlist/',
    'P3': 'https://onlineradiobox.com/dk/drp3/playlist/',
    'TheVoice': 'https://onlineradiobox.com/dk/thevoice/playlist/',
    'Radio100': 'https://onlineradiobox.com/dk/radio100/playlist/',
    'PartyFM': 'https://onlineradiobox.com/dk/partyfm/playlist/',
    'RadioGlobus': 'https://onlineradiobox.com/dk/radioglobus/playlist/',
    'SkalaFM': 'https://onlineradiobox.com/dk/skalafm/playlist/',
    'P4': 'https://onlineradiobox.com/dk/drp4kobenhavn/playlist/',
    'PopFM': 'https://onlineradiobox.com/dk/poppremium/playlist/',
    'RBClassics': 'https://onlineradiobox.com/dk/rbclassics/playlist/'
}

# Stations that don't need language separation (e.g., primarily English content)
NO_LANGUAGE_SEPARATION = ['RBClassics']

def extract_onlineradiobox_playlist(url, station_name):
    """Extract playlist data from OnlineRadioBox.
    
    Args:
        url (str): URL to the OnlineRadioBox playlist page
        station_name (str): Name of the radio station
        
    Returns:
        list: Playlist data with artist, title, and timestamp
    """
    print(f"Fetching playlist data for {station_name} from OnlineRadioBox")
    print(f"URL: {url}")
    
    playlist_data = []
    current_date = datetime.now().strftime('%Y-%m-%d')
    
    try:
        # Add lang=en to ensure we get English interface
        if '?' in url:
            fetch_url = url + '&lang=en'
        else:
            fetch_url = url + '?lang=en'
            
        response = requests.get(fetch_url)
        print("Response status code: {}".format(response.status_code))
        
        if response.status_code == 200:
            # Parse the HTML to extract playlist data
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find all tracks which are links
            track_links = soup.find_all('a', href=lambda href: href and '/track/' in href)
            
            # Look for timestamps
            timestamps = []
            for element in soup.find_all(['span', 'div']):
                text = element.get_text().strip()
                if re.match(r'^\d{2}:\d{2}$', text):
                    timestamps.append(text)
            
            # Match timestamps with tracks
            timestamp_index = 0
            
            for track_link in track_links:
                track_text = track_link.get_text().strip()
                
                # Check for valid track format
                if ' - ' in track_text and len(track_text.split(' - ')) == 2:
                    # Extract artist and title
                    artist, title = track_text.split(' - ', 1)
                    artist = artist.strip()
                    title = title.strip()
                    
                    # Skip station identifications, ads, etc.
                    if station_name in artist or "Radio" in artist or "radio" in artist:
                        continue
                    
                    # Get timestamp if available
                    time_str = "00:00"  # Default
                    if timestamp_index < len(timestamps):
                        time_str = timestamps[timestamp_index]
                        timestamp_index += 1
                    
                    # Add to playlist data
                    playlist_data.append({
                        'Date': current_date,
                        'Time': time_str,
                        'Artist': artist,
                        'Title': title
                    })
            
            # If we couldn't find any tracks with the above method, try an alternative approach
            if len(playlist_data) == 0:
                print("No tracks found with primary method, trying alternative...")
                
                # Look for track links with slightly different format
                track_links = soup.find_all('a', href=lambda href: href and 'track' in href)
                
                for track_link in track_links:
                    track_text = track_link.get_text().strip()
                    
                    # Check for "Artist / Title" format (P3 format)
                    if ' / ' in track_text and len(track_text.split(' / ')) == 2:
                        # For P3 format
                        title, artist = track_text.split(' / ', 1)
                        title = title.strip()
                        artist = artist.strip()
                        
                        # Try to find timestamp by looking at previous siblings or parent's text
                        time_str = "00:00"  # Default
                        prev_text = ''
                        
                        # Look at previous element for timestamp
                        prev_elem = track_link.previous_sibling
                        while prev_elem and not prev_text:
                            if hasattr(prev_elem, 'string') and prev_elem.string:
                                prev_text = prev_elem.string.strip()
                            prev_elem = prev_elem.previous_sibling
                        
                        # Try to extract timestamp from previous text
                        if prev_text and re.match(r'^\d{2}:\d{2}$', prev_text):
                            time_str = prev_text
                        
                        # Skip station identifications, ads, etc.
                        if station_name in artist or "Radio" in artist or "radio" in artist:
                            continue
                        
                        playlist_data.append({
                            'Date': current_date,
                            'Time': time_str,
                            'Artist': artist,
                            'Title': title
                        })
                
                # If still no tracks found, try the direct text search method
                if len(playlist_data) == 0:
                    print("Still trying another alternative method...")
                    content = soup.get_text()
                    lines = [line.strip() for line in content.split('\n') if line.strip()]
                    
                    for i, line in enumerate(lines):
                        # Look for timestamps
                        if re.match(r'^\d{2}:\d{2}$', line) and i+1 < len(lines):
                            time_str = line
                            next_line = lines[i+1]
                            
                            # Check if next line has track info in "Artist / Title" format
                            if ' / ' in next_line and not next_line.startswith(station_name):
                                parts = next_line.split(' / ', 1)
                                if len(parts) == 2:
                                    title, artist = parts
                                    title = title.strip()
                                    artist = artist.strip()
                                    
                                    # Skip station identifications, ads, etc.
                                    if station_name in artist or "Radio" in artist or "radio" in artist:
                                        continue
                                    
                                    playlist_data.append({
                                        'Date': current_date,
                                        'Time': time_str,
                                        'Artist': artist,
                                        'Title': title
                                    })
                            # Check if next line has track info in "Artist - Title" format
                            elif ' - ' in next_line and not next_line.startswith(station_name):
                                parts = next_line.split(' - ', 1)
                                if len(parts) == 2:
                                    artist, title = parts
                                    artist = artist.strip()
                                    title = title.strip()
                                    
                                    # Skip station identifications, ads, etc.
                                    if station_name in artist or "Radio" in artist or "radio" in artist:
                                        continue
                                    
                                    playlist_data.append({
                                        'Date': current_date,
                                        'Time': time_str,
                                        'Artist': artist,
                                        'Title': title
                                    })
                    
                    # Try one more pattern for P3 specifically
                    if station_name == 'P3' and len(playlist_data) == 0:
                        print("Trying P3-specific extraction pattern...")
                        pattern = re.compile(r'(\d{2}:\d{2})\s+([^\n/]+)\s+/\s+([^\n]+)')
                        matches = pattern.findall(content)
                        
                        for match in matches:
                            time_str, title, artist = match
                            title = title.strip()
                            artist = artist.strip()
                            
                            # Skip station identifications, ads, etc.
                            if 'DR P3' in artist or 'dr.dk' in artist:
                                continue
                            
                            playlist_data.append({
                                'Date': current_date,
                                'Time': time_str,
                                'Artist': artist,
                                'Title': title
                            })
                        
                        # Try a second pattern for P3
                        if len(playlist_data) == 0:
                            pattern = re.compile(r'(\d{2}:\d{2})\s+([^\n]+?)\s+/\s+([^\n]+)')
                            matches = pattern.findall(content)
                            
                            for match in matches:
                                time_str, artist, title = match
                                artist = artist.strip()
                                title = title.strip()
                                
                                # Skip station identifications, ads, etc.
                                if 'DR P3' in artist or 'dr.dk' in artist:
                                    continue
                                
                                playlist_data.append({
                                    'Date': current_date,
                                    'Time': time_str,
                                    'Artist': artist,
                                    'Title': title
                                })
                        
                        # Try one final pattern
                        if len(playlist_data) == 0:
                            # Direct parsing of the format we observed in the P3 playlist
                            raw_content = soup.prettify()
                            pattern = re.compile(r'(\d{2}:\d{2})\s+(.*?)\s+-\s+(.*?)(?=\s+\d{2}:\d{2}|$)', re.DOTALL)
                            matches = pattern.findall(raw_content)
                            
                            for match in matches:
                                time_str, artist, title = match
                                artist = artist.strip()
                                title = title.strip()
                                
                                # Skip station identifications
                                if 'DR P3' in artist or 'dr.dk' in artist:
                                    continue
                                
                                playlist_data.append({
                                    'Date': current_date,
                                    'Time': time_str,
                                    'Artist': artist,
                                    'Title': title
                                })
                                
                # One last attempt - parse the simple list format we saw in the P3 page
                if station_name == 'P3' and len(playlist_data) == 0:
                    print("Trying final list pattern extraction...")
                    pattern = re.compile(r'(\d{2}:\d{2})\s+(.*?)\s+/\s+(.*?)\s')
                    content = soup.get_text()
                    matches = pattern.findall(content)
                    
                    for match in matches:
                        time_str, title, artist = match
                        
                        # Skip station identifications
                        if 'DR P3' in artist or 'dr.dk/p3' in artist:
                            continue
                            
                        playlist_data.append({
                            'Date': current_date,
                            'Time': time_str,
                            'Artist': artist,
                            'Title': title
                        })
                        
                    # If still nothing, try with a very simple pattern
                    if len(playlist_data) == 0:
                        simple_pattern = re.compile(r'(\d{2}:\d{2})\s+(.*?)\s+-\s+(.*?)(?=\s+\d{2}:\d{2}|$)')
                        matches = simple_pattern.findall(content)
                        
                        for match in matches:
                            time_str, artist, title = match
                            artist = artist.strip()
                            title = title.strip()
                            
                            # Skip station identifications
                            if 'DR P3' in artist or 'dr.dk' in artist:
                                continue
                                
                            playlist_data.append({
                                'Date': current_date,
                                'Time': time_str,
                                'Artist': artist,
                                'Title': title
                            })
            
            print(f"Successfully extracted {len(playlist_data)} tracks from {station_name}")
            return playlist_data
        else:
            print(f"Error fetching data: HTTP {response.status_code}")
            return None
    except Exception as e:
        print(f"Exception when fetching data for {station_name}: {e}")
        return None

def is_definitely_danish(text, artist=""):
    """More robust Danish language detection for song titles.
    
    Args:
        text (str): The song title to check
        artist (str): The artist name, used for additional context
    """
    # In Python 3, strings are already Unicode
    # Only decode in Python 2.7
    if sys.version_info[0] < 3:
        if isinstance(text, str):
            text = text.decode('utf-8')
        if isinstance(artist, str):
            artist = artist.decode('utf-8')
        
    # Check for Danish-specific characters in both title and artist
    danish_chars = [u'æ', u'ø', u'å', u'Æ', u'Ø', u'Å']
    has_danish_chars_title = any(char in text for char in danish_chars)
    has_danish_chars_artist = any(char in artist for char in danish_chars)
    
    # Known Danish artists - this list can be expanded
    known_danish_artists = [
        "Suspekt", "URO", "Uro", "Blæst", "Malte Ebert", "Mumle", "Lord Siva", 
        "Tobias Rahim", "Andreas Odbjerg", "Hjalmer", "Skinz", "Jonah Blacksmith",
        "Jung", "Gilli", "Pil", "Medina", "Rasmus Seebach", "Lukas Graham", 
        "Burhan G", "Christopher", "Tessa", "Benjamin Hav", "Scarlet Pleasure",
        "Mads Langer", "Infernal", "The Minds of 99", "TV-2", "Kim Larsen",
        "Alex Vargas", "Ukendt Kunstner", "USO", "Nik & Jay", "Thomas Helmig",
        "Szhirley", "Jada", "Karl William", "Kesi", "Nephew", "Node", "Oh Land",
        "Jyden", "Jyderne", "Anton Westerlin", "Annika", "Citybois", "SVEA S",
        "Djämes Braun", "Gobs", "Mads Christian", "Carmon", "ozzy", "APHACA"
    ]
    
    # Known Danish words that strongly indicate Danish language
    danish_words = [
        "og", "jeg", "du", "det", "den", "til", "er", "som", "på", "de", "med", "han", "af", "for", 
        "ikke", "der", "var", "mig", "sig", "men", "et", "har", "om", "vi", "min", "havde", "fra", 
        "skulle", "kunne", "eller", "hvad", "skal", "ville", "hvordan", "sin", "ind", "når", "være",
        "fortæl", "mig", "hvis", "vil", "noget", "andet", "elsker", "dig", "så", "meget", "det", "modsatte",
        "fra", "jylland", "københavn", "stjernerne", "tænker", "andre", "bror", "hvor", "var", "endt",
        "åboulevarden", "stor", "mand", "hjerte", "morgen", "drømmer", "venter", "længe", "himlen",
        "verden", "smuk", "kærlighed", "tid", "kære", "nat", "igen", "hjem", "uden", "ingen", "alt",
        "smukkeste", "kanoner", "kvinder", "sne", "blodigt", "hørt", "før", "ønsker", "slemme", "tæt",
        "igen", "øjne", "entré", "sidste", "gang", "seks", "hjerter"
    ]
    
    # Check if the title or artist contains known Danish words
    words_title = [w.lower() for w in text.split()]
    words_artist = [w.lower() for w in artist.split()]
    has_danish_word_title = any(word.lower() in words_title for word in danish_words)
    has_danish_word_artist = any(word.lower() in words_artist for word in danish_words)
    
    # Check if the artist is a known Danish artist
    is_known_danish_artist = any(danish_artist.lower() in artist.lower() for danish_artist in known_danish_artists)
    
    # Specific track names that we know are Danish
    known_danish_tracks = [
        "Fortæl Mig Hvis Du Vil Noget Andet",
        "Er Det Mig Du Elsker",
        "Stjernerne",
        "Det Modsatte",
        "Fra Jylland til København",
        "Elsker Dig Så Meget",
        "Tænker Ik På Andre",
        "Min Bror",
        "Hvor Var Jeg Endt",
        "Åboulevarden",
        "Stor Mand",
        "Kun For Mig",
        "Hele Vejen",
        "Luk Mig Ind",
        "Dårligt Match",
        "Kom Sommer",
        "Hjem Fra Fabrikken",
        "Lidt For Lidt",
        "Under Din Sne",
        "Du Ligner Din Mor",
        "California Dreamin'",
        "Det Smukkeste",
        "Æ Hjem og Sove",
        "Kvinder Og Kanoner",
        "Tro På Kærlighed",
        "Det Ønsker Jeg For Dig",
        "Blodigt",
        "Hørt Det Før",
        "En Drøm Om Et Menneske",
        "igen & igen"
    ]
    
    # Check if the title matches a known Danish track
    is_known_danish_track = any(danish_track.lower() in text.lower() for danish_track in known_danish_tracks)
    
    # Attempt language detection only if not already determined
    if is_known_danish_artist or is_known_danish_track or has_danish_chars_title or has_danish_chars_artist or has_danish_word_title or has_danish_word_artist:
        return True
    
    try:
        detected_lang = detect(text)
        return detected_lang == 'da'
    except Exception:
        # Last resort: if detection fails, check once more for Danish indicators
        return has_danish_chars_title or has_danish_chars_artist or has_danish_word_title or has_danish_word_artist

def is_english(text, artist=""):
    """Improved English language detection for song titles.
    
    Args:
        text (str): The song title to check
        artist (str): The artist name, used for additional context
    """
    # In Python 3, strings are already Unicode
    # Only decode in Python 2.7
    if sys.version_info[0] < 3:
        if isinstance(text, str):
            text = text.decode('utf-8')
        if isinstance(artist, str):
            artist = artist.decode('utf-8')
    
    # First check if it's Danish - if so, it's definitely not English
    if is_definitely_danish(text, artist):
        return False
        
    # Check for Danish-specific characters in both title and artist
    danish_chars = [u'æ', u'ø', u'å', u'Æ', u'Ø', u'Å']
    has_danish_chars_title = any(char in text for char in danish_chars)
    has_danish_chars_artist = any(char in artist for char in danish_chars)
    
    # If it has Danish characters, it's probably not English
    if has_danish_chars_title or has_danish_chars_artist:
        return False
    
    # Known English words that strongly indicate English language
    english_words = [
        "the", "and", "you", "that", "was", "for", "are", "with", "his", "they", "have", 
        "this", "from", "had", "not", "but", "what", "all", "were", "when", "your", "can", 
        "said", "there", "use", "each", "which", "she", "how", "their", "will", "other", "about", 
        "out", "many", "then", "them", "these", "some", "her", "would", "make", "like", "him", 
        "into", "time", "look", "two", "more", "write", "see", "number", "way", "could", "people",
        "beautiful", "things", "austin", "nice", "meet", "ordinary", "belong", "together", "lose",
        "only", "girl", "give", "everything", "love", "heart", "feel", "away", "life", "world",
        "never", "down", "day", "night", "eyes", "want", "need", "mind", "soul", "dream", "fly",
        "birds", "feather", "revolving", "door", "sports", "car", "anxiety", "voice", "instruction",
        "shake", "after", "hours", "guess", "still", "loading", "taste", "on", "me", "azizam"
    ]
    
    # Known English-language artists
    known_english_artists = [
        "Benson Boone", "Dasha", "Myles Smith", "Alex Warren", "Mark Ambor", "Rihanna",
        "Pitbull", "Ne-yo", "Afrojack", "Nayer", "Selena Gomez", "Taylor Swift", "Ed Sheeran",
        "Adele", "Justin Bieber", "Ariana Grande", "Bruno Mars", "Katy Perry", "The Weeknd",
        "Shawn Mendes", "Billie Eilish", "Post Malone", "Khalid", "Drake", "Maroon 5",
        "Lady Gaga", "Coldplay", "Imagine Dragons", "OneRepublic", "Calvin Harris",
        "Dua Lipa", "Charlie Puth", "Sam Smith", "Halsey", "Camila Cabello", "Lil Nas X",
        "Lewis Capaldi", "Eminem", "Rihanna", "John Legend", "Ellie Goulding", "Avicii",
        "David Guetta", "SZA", "Zach Bryan", "Noah Kahan", "Sabrina Carpenter", "Olivia Rodrigo",
        "Harry Styles", "Miley Cyrus", "Dua Lipa", "Beyoncé", "BTS", "Lizzo", "Lana Del Rey",
        "BLACKPINK", "The Weeknd", "Travis Scott", "Kendrick Lamar", "Cardi B", "Megan Thee Stallion",
        "Teddy Swims", "Charli XCX", "Tate McRae", "Central Cee", "Artemas", "CYRIL", "Sonny Fodera",
        "Jazzy", "Doechii", "Mike Posner", "Hozier", "RAYE", "Jax Jones", "Lola Young", "Eve",
        "MOLIY", "Silent Addy", "Skillibeng", "Shenseea", "Kehlani", "Daft Punk", "Gracie Abrams",
        "Marc Anthony", "SASO", "D1ma", "MØ", "Amy Winehouse", "Mark Ronson", "Francesco Yate",
        "Robin Schulz", "Usher", "Lil Jon", "Ludacris"
    ]
    
    # Check if the title or artist contains known English words
    words_title = [w.lower() for w in text.split()]
    words_artist = [w.lower() for w in artist.split()]
    has_english_word_title = any(word.lower() in words_title for word in english_words)
    has_english_word_artist = any(word.lower() in words_artist for word in english_words)
    
    # Check if the artist is a known English-language artist
    is_known_english_artist = any(english_artist.lower() in artist.lower() for english_artist in known_english_artists)
    
    # If we already have strong indicators of English, return True without langdetect
    if is_known_english_artist or has_english_word_title or has_english_word_artist:
        return True
    
    # Attempt language detection as a last resort
    try:
        detected_lang = detect(text)
        return detected_lang == 'en'
    except Exception:
        # Default to not English if detection fails
        return False

def save_to_csv(tracks, filename):
    """Save processed tracks to CSV file."""
    if not tracks:
        print("No tracks found")
        return False
    
    # Convert to DataFrame for easier processing
    df = pd.DataFrame(tracks)
    
    # Sort by Date and Time if available
    if 'Date' in df.columns and 'Time' in df.columns:
        df = df.sort_values(['Date', 'Time'])
    
    # Remove duplicates
    df = df.drop_duplicates()
    
    # Save to CSV
    df.to_csv(filename, index=False, encoding='utf-8')
    
    return True

def summarize_tracks(tracks, output_csv):
    """Summarize tracks by counting occurrences."""
    if not tracks:
        return 0
        
    # Create a list of "Artist - Title" strings
    artist_title_list = []
    for track in tracks:
        artist_title = "{} - {}".format(track['Artist'], track['Title'])
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

def extract_station_playlist(station_name, separate_languages=True):
    """Extract playlist data for a specific radio station.
    
    Args:
        station_name (str): Name of the radio station (key in STATION_MAP)
        separate_languages (bool): Whether to separate tracks by language
        
    Returns:
        tuple: Danish tracks, English tracks, other tracks, total tracks
    """
    print(f"\n{'='*50}")
    print(f"Extracting playlist data for {station_name}")
    print(f"{'='*50}")
    
    # Get the URL for this station
    if station_name not in STATION_URLS:
        print(f"No URL defined for station: {station_name}")
        return None, None, None, 0
    
    url = STATION_URLS[station_name]
    
    # Create output directories
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.abspath(os.path.join(script_dir, '..'))
    
    # Base directory for this station
    station_dir = os.path.join(project_dir, "Outputs", "Stations", station_name)
    
    # Create output directories based on whether we separate languages
    if separate_languages:
        output_dirs = [
            os.path.join(station_dir, "Danish"),
            os.path.join(station_dir, "English"),
            os.path.join(station_dir, "Raw")
        ]
    else:
        output_dirs = [
            os.path.join(station_dir, "All"),
            os.path.join(station_dir, "Raw")
        ]
    
    # Create directories if they don't exist
    for dir_path in output_dirs:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
    
    # Get current date for filenames
    today = datetime.now()
    date_str = today.strftime('%Y-%m-%d')
    filename_date = f"past_7_days_{date_str}"
    
    # Extract playlist data
    playlist_data = extract_onlineradiobox_playlist(url, station_name)
    
    if not playlist_data:
        print(f"Failed to retrieve playlist data for {station_name}.")
        return None, None, None, 0
    
    # Save raw data
    raw_output = os.path.join(station_dir, "Raw", f"{station_name}_Raw_Playlist_{filename_date}.csv")
    save_to_csv(playlist_data, raw_output)
    print(f"Raw playlist data saved to: {raw_output}")
    
    # If no language separation is needed, save all tracks to the All directory
    if not separate_languages:
        all_output = os.path.join(station_dir, "All", f"{station_name}_All_Tracks_{filename_date}.csv")
        track_count = summarize_tracks(playlist_data, all_output)
        print(f"Summarized {track_count} unique tracks to: {all_output}")
        return None, None, None, len(playlist_data)
    
    # Filter Danish and English tracks
    danish_tracks = []
    english_tracks = []
    other_tracks = []
    
    for track in playlist_data:
        title = track['Title']
        artist = track['Artist']
        
        # Skip promotional content
        if any(promo in title.lower() for promo in ['install', 'free', 'app', 'smartphone', 'download']):
            continue
        if any(promo in artist.lower() for promo in ['install', 'free', 'app', 'smartphone', 'download']):
            continue
        
        # Classify by language
        if is_definitely_danish(title, artist):
            danish_tracks.append(track)
        elif is_english(title, artist):
            english_tracks.append(track)
        else:
            other_tracks.append(track)
    
    # Print unclassified tracks for debugging
    if other_tracks:
        print(f"\nTracks that couldn't be classified for {station_name} (sample of up to 5):")
        for track in other_tracks[:5]:
            print(f"  {track['Artist']} - {track['Title']}")
    
    # Summarize and save Danish tracks
    danish_output = os.path.join(station_dir, "Danish", f"{station_name}_Danish_Titles_{filename_date}.csv")
    danish_count = summarize_tracks(danish_tracks, danish_output)
    print(f"Summarized {danish_count} unique Danish tracks to: {danish_output}")
    
    # Summarize and save English tracks
    english_output = os.path.join(station_dir, "English", f"{station_name}_English_Titles_{filename_date}.csv")
    english_count = summarize_tracks(english_tracks, english_output)
    print(f"Summarized {english_count} unique English tracks to: {english_output}")
    
    # Print summary
    print(f"\nSummary for {station_name}:")
    print(f"  Total tracks in playlist: {len(playlist_data)}")
    print(f"  Danish tracks: {danish_count}")
    print(f"  English tracks: {english_count}")
    print(f"  Other language tracks: {len(playlist_data) - len(danish_tracks) - len(english_tracks)}")
    
    return danish_tracks, english_tracks, other_tracks, len(playlist_data)

def main():
    """Main function to handle command-line arguments."""
    print("Radio Playlist Extractor")
    print("=======================")
    
    # Defined primary stations for language separation
    PRIMARY_STATIONS = ['NOVA', 'P3']
    
    # Get command line arguments
    args = sys.argv[1:]
    
    if len(args) > 0:
        # Check for help flag
        if args[0].lower() in ['-h', '--help', 'help']:
            print("Usage: python extract_radio_playlists.py [STATION...]")
            print("\nOptions:")
            print("  all         Extract playlists for all stations")
            print("  primary     Extract playlists for primary stations only (NOVA, P3)")
            print("  --list      List all available stations")
            print("\nExample:")
            print("  python extract_radio_playlists.py NOVA P3")
            print("  python extract_radio_playlists.py all")
            return
        
        # Check for list flag
        if args[0].lower() in ['--list', '-l']:
            print("Available stations:")
            for station in sorted(STATION_MAP.keys()):
                if station in NO_LANGUAGE_SEPARATION:
                    print("  {} (no language separation)".format(station))
                elif station in PRIMARY_STATIONS:
                    print("  {} (primary station)".format(station))
                else:
                    print("  {}".format(station))
        
        # Handle 'all' keyword
        if args[0].lower() == 'all':
            stations = sorted(STATION_MAP.keys())
        # Handle 'primary' keyword
        elif args[0].lower() == 'primary':
            stations = sorted(PRIMARY_STATIONS)
        # Otherwise, use the station names provided
        else:
            stations = []
            for arg in args:
                if arg in STATION_MAP:
                    stations.append(arg)
                else:
                    print(f"Warning: Unknown station '{arg}'. Skipping.")
        
        if not stations:
            print("No valid stations specified. Use --list to see available stations.")
            return
    else:
        # Default to all stations
        stations = sorted(STATION_MAP.keys())
    
    print(f"Extracting playlists for: {', '.join(stations)}")
    
    # Process each station
    total_danish = 0
    total_english = 0
    total_tracks = 0
    
    for station in stations:
        # Determine if we need language separation for this station
        separate_languages = station not in NO_LANGUAGE_SEPARATION
        
        danish, english, other, count = extract_station_playlist(station, separate_languages)
        
        if separate_languages and danish is not None and english is not None:
            total_danish += len(danish)
            total_english += len(english)
        
        total_tracks += count
    
    print("\nExtraction complete!")
    print(f"Total tracks processed: {total_tracks}")
    if total_danish > 0 or total_english > 0:
        print(f"Total Danish tracks: {total_danish}")
        print(f"Total English tracks: {total_english}")
    print("\nTo consolidate all playlists, run:")
    print("  python Scripts/radio_playlist_consolidator.py")

if __name__ == "__main__":
    main()
