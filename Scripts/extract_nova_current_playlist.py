#!/usr/bin/env python
# -*- coding: utf-8 -*-
import requests
import re
import os
from datetime import datetime, timedelta
from langdetect import detect
from bs4 import BeautifulSoup
import pandas as pd


def get_nova_current_playlist():
    """Fetch the current playlist data from OnlineRadioBox (past 7 days)."""
    print("Fetching current NOVA FM playlist data (past 7 days)")
    
    # OnlineRadioBox stores recent playlist data (up to 7 days)
    url = "https://onlineradiobox.com/dk/nova/playlist/?lang=en"
    print("URL: {}".format(url))
    
    try:
        response = requests.get(url)
        print("Response status code: {}".format(response.status_code))
        if response.status_code == 200:
            # Parse the HTML to extract playlist data
            soup = BeautifulSoup(response.text, 'html.parser')
            playlist_data = []
            
            # Try to get the actual date range from the page
            date_range_text = None
            date_element = soup.find('div', class_='playlist__title')
            if date_element:
                date_range_text = date_element.get_text().strip()
                print("Date range from website: {}".format(date_range_text))
            else:
                print("Couldn't find date range element on the page")
            
            # Each track is a link in the playlist section
            playlist_entries = soup.find_all('a', href=lambda href: href and '/track/' in href)
            
            # Look for timestamps - they're near each track
            timestamps = []
            date_markers = []
            
            # Find the date markers and timestamps
            for item in soup.find_all(['span', 'div']):
                if 'class' in item.attrs and 'playlist__date' in item.attrs['class']:
                    date_markers.append(item.get_text().strip())
                elif re.match(r'\d{2}:\d{2}', item.get_text().strip()):
                    timestamps.append(item.get_text().strip())
            
            # Process the tracks
            current_date = datetime.now().strftime('%Y-%m-%d')  # Default to current date
            timestamp_index = 0
            
            # Debug output
            print("Found {} track links in the page".format(len(playlist_entries)))
            print("Found {} timestamps in the page".format(len(timestamps)))
            
            # If we have no playlist entries or timestamps, try a different approach
            if len(playlist_entries) == 0:
                print("No playlist entries found with standard method, trying alternative approach...")
                # Look for track elements with different structure
                track_elements = soup.find_all('div', class_='track')
                print("Found {} track elements with alternative method".format(len(track_elements)))
                
                for track_element in track_elements:
                    # Try to find artist and title
                    artist_elem = track_element.find('div', class_='track__artist')
                    title_elem = track_element.find('div', class_='track__title')
                    time_elem = track_element.find('div', class_='track__time')
                    
                    if artist_elem and title_elem:
                        artist = artist_elem.get_text().strip()
                        title = title_elem.get_text().strip()
                        time_str = time_elem.get_text().strip() if time_elem else "00:00"
                        
                        playlist_data.append({
                            'Date': current_date,
                            'Time': time_str,
                            'Title': title,
                            'Artist': artist
                        })
            else:
                # Use the original approach
                for i, track_link in enumerate(playlist_entries):
                    # Get the track text - usually "Title - Artist"
                    track_text = track_link.get_text().strip()
                    if ' - ' in track_text:
                        title = track_text.split(' - ')[0].strip()
                        artist = track_text.split(' - ')[1].strip()
                        
                        # Get timestamp
                        time_str = "00:00"  # Default
                        if timestamp_index < len(timestamps):
                            time_str = timestamps[timestamp_index]
                            timestamp_index += 1
                        
                        playlist_data.append({
                            'Date': current_date,
                            'Time': time_str,
                            'Title': title,
                            'Artist': artist
                        })
            
            # If we still have no data, try one more approach - direct HTML inspection
            if len(playlist_data) == 0:
                print("Still no data found, attempting direct HTML parsing...")
                # Look for any content that might be track information
                content = soup.get_text()
                lines = [line.strip() for line in content.split('\n') if line.strip()]
                
                for line in lines:
                    # Look for patterns like "Artist - Title" or "Title - Artist"
                    if ' - ' in line and not line.startswith('http') and len(line) > 10:
                        parts = line.split(' - ')
                        if len(parts) == 2:
                            # Assume it's Artist - Title format
                            artist = parts[0].strip()
                            title = parts[1].strip()
                            
                            playlist_data.append({
                                'Date': current_date,
                                'Time': "00:00",
                                'Title': title,
                                'Artist': artist
                            })
            
            print("Successfully extracted {} tracks from OnlineRadioBox".format(len(playlist_data)))
            return playlist_data, date_range_text
        else:
            print("Error fetching data: HTTP {}".format(response.status_code))
            return None, None
    except Exception as e:
        print("Exception when fetching data: {}".format(e))
        return None, None

def is_definitely_danish(text, artist=""):
    """More robust Danish language detection for song titles.
    
    Args:
        text (str): The song title to check
        artist (str): The artist name, used for additional context
    """
    # Ensure text/artist are str in Python 3; decode only if bytes
    if isinstance(text, bytes):
        text = text.decode('utf-8', errors='ignore')
    if isinstance(artist, bytes):
        artist = artist.decode('utf-8', errors='ignore')
        
    # Check for Danish-specific characters in both title and artist
    danish_chars = [u'æ', u'ø', u'å', u'Æ', u'Ø', u'Å']
    has_danish_chars_title = any(char in text for char in danish_chars)
    has_danish_chars_artist = any(char in artist for char in danish_chars)
    
    # Known Danish artists - this list can be expanded
    known_danish_artists = [
        "Suspekt", "URO", "Uro", "Blæst", "Malte Ebert", "Mumle", "Lord Siva", 
        "Tobias Rahim", "Andreas Odbjerg", "Hjalmer", "Skinz", "Jonah Blacksmith"
    ]
    
    # Known Danish words that strongly indicate Danish language
    danish_words = [
        "og", "jeg", "du", "det", "den", "til", "er", "som", "på", "de", "med", "han", "af", "for", 
        "ikke", "der", "var", "mig", "sig", "men", "et", "har", "om", "vi", "min", "havde", "fra", 
        "skulle", "kunne", "eller", "hvad", "skal", "ville", "hvordan", "sin", "ind", "når", "være",
        "fortæl", "mig", "hvis", "vil", "noget", "andet", "elsker", "dig", "så", "meget", "det", "modsatte",
        "fra", "jylland", "københavn", "stjernerne", "tænker", "andre", "bror", "hvor", "var", "endt",
        "åboulevarden", "stor", "mand"
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
        "Min Bror",  # Explicitly add this one that was previously misclassified
        "Hvor Var Jeg Endt",
        "Åboulevarden",
        "Stor Mand"
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
    # Ensure text/artist are str in Python 3; decode only if bytes
    if isinstance(text, bytes):
        text = text.decode('utf-8', errors='ignore')
    if isinstance(artist, bytes):
        artist = artist.decode('utf-8', errors='ignore')
    
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
        "only", "girl", "give", "everything"
    ]
    
    # Known English artists - this is just a starting point
    known_english_artists = [
        "Benson Boone", "Dasha", "Myles Smith", "Alex Warren", "Mark Ambor", "Rihanna",
        "Pitbull", "Ne-yo", "Afrojack", "Nayer", "Selena Gomez", "Taylor Swift", "Ed Sheeran",
        "Adele", "Justin Bieber", "Ariana Grande", "Bruno Mars", "Katy Perry", "The Weeknd",
        "Shawn Mendes", "Billie Eilish", "Post Malone", "Khalid", "Drake", "Maroon 5",
        "Lady Gaga", "Coldplay", "Imagine Dragons", "OneRepublic", "Calvin Harris",
        "Dua Lipa", "Charlie Puth", "Sam Smith", "Halsey", "Camila Cabello", "Lil Nas X",
        "Lewis Capaldi", "Eminem", "Rihanna", "John Legend", "Ellie Goulding", "Avicii"
    ]
    
    # Check if the title or artist contains known English words
    words_title = [w.lower() for w in text.split()]
    words_artist = [w.lower() for w in artist.split()]
    has_english_word_title = any(word.lower() in words_title for word in english_words)
    has_english_word_artist = any(word.lower() in words_artist for word in english_words)
    
    # Check if the artist is a known English-language artist
    is_known_english_artist = any(english_artist.lower() in artist.lower() for english_artist in known_english_artists)
    
    # Specific track names that we know are English
    known_english_tracks = [
        "Beautiful Things",
        "Austin",
        "Nice To Meet You",
        "Ordinary",
        "Belong Together",
        "Lose A You",
        "Only Girl",
        "Give Me Everything"
    ]
    
    # Check if the title matches a known English track
    is_known_english_track = any(english_track.lower() in text.lower() for english_track in known_english_tracks)
    
    # If we already have strong indicators of English, return True without langdetect
    if is_known_english_artist or is_known_english_track or has_english_word_title or has_english_word_artist:
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

def main():
    print("Starting NOVA Radio current playlist extraction...")
    
    # Get current date for naming files
    today = datetime.now()
    date_str = today.strftime('%Y-%m-%d')
    
    # Set up file paths with better organization
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.abspath(os.path.join(script_dir, '..'))
    
    # Ensure output directories exist
    output_dirs = [
        os.path.join(project_dir, "Outputs/Current/Danish"),
        os.path.join(project_dir, "Outputs/Current/English"),
        os.path.join(project_dir, "Outputs/Current/Raw")
    ]
    for dir_path in output_dirs:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
    
    # Fetch the current playlist data
    playlist_data, date_range_text = get_nova_current_playlist()
    
    if not playlist_data:
        print("Failed to retrieve playlist data.")
        return
    
    # Clean up the date range text for filenames
    if date_range_text:
        # Extract just the date part and format for filenames
        date_parts = re.findall(r'\d+\.\d+\.\d+', date_range_text)
        if len(date_parts) >= 2:
            filename_date_range = "{}".format(date_parts)
        else:
            filename_date_range = "past_7_days_{}".format(date_str)
    else:
        filename_date_range = "past_7_days_{}".format(date_str)
    
    # Save raw data to archive
    raw_output = os.path.join(project_dir, "Outputs/Current/Raw/NOVA_Raw_Playlist_{}.csv".format(filename_date_range))
    save_to_csv(playlist_data, raw_output)
    print("Raw playlist data saved to: {}".format(raw_output))
    
    # Filter Danish and English tracks
    danish_tracks = []
    english_tracks = []
    
    for track in playlist_data:
        title = track['Title']
        artist = track['Artist']
        if is_definitely_danish(title, artist):
            danish_tracks.append(track)
        elif is_english(title, artist):
            english_tracks.append(track)
    
    # Summarize and save Danish tracks
    danish_output = os.path.join(project_dir, "Outputs/Current/Danish/NOVA_Danish_Titles_{}.csv".format(filename_date_range))
    danish_count = summarize_tracks(danish_tracks, danish_output)
    print("Summarized {} unique Danish tracks to: {}".format(danish_count, danish_output))
    
    # Summarize and save English tracks
    english_output = os.path.join(project_dir, "Outputs/Current/English/NOVA_English_Titles_{}.csv".format(filename_date_range))
    english_count = summarize_tracks(english_tracks, english_output)
    print("Summarized {} unique English tracks to: {}".format(english_count, english_output))
    
    # Print summary
    print("\nSummary:")
    print("  Total tracks in playlist: {}".format(len(playlist_data)))
    print("  Danish tracks: {}".format(danish_count))
    print("  English tracks: {}".format(english_count))
    print("  Other language tracks: {}".format(len(playlist_data) - len(danish_tracks) - len(english_tracks)))

if __name__ == "__main__":
    main()
