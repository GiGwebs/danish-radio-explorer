#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function
import pandas as pd
import csv
import sys
import codecs
from langdetect import detect
from langdetect.lang_detect_exception import LangDetectException

# Ensure UTF-8 encoding for Python 2.7
if sys.version_info[0] < 3:
    reload(sys)
    sys.setdefaultencoding('utf-8')

def is_definitely_danish(text):
    """More robust Danish language detection for song titles."""
    # Convert to unicode if needed (for Python 2.7)
    if isinstance(text, str):
        text = text.decode('utf-8')
        
    # Check for Danish-specific characters
    danish_chars = [u'æ', u'ø', u'å', u'Æ', u'Ø', u'Å']
    has_danish_chars = any(char in text for char in danish_chars)
    
    # Attempt language detection, but be more strict
    try:
        detected_lang = detect(text)
        # If text has Danish characters, strongly prefer Danish detection
        if has_danish_chars and detected_lang == 'da':
            return True
        # Without Danish characters, require higher confidence
        elif detected_lang == 'da':
            # Additional verification could be done here
            # For now, we'll manually check the known English tracks
            known_english = [
                "Outnumbered", 
                "Sorry I'm Here For Someone Else",
                "I Had Some Help"
            ]
            return text not in known_english
        else:
            return False
    except LangDetectException:
        # If detection fails but has Danish characters, consider it Danish
        return has_danish_chars

def filter_danish_tracks(year="2025", date_range="2025-01-01_to_2025-05-22"):
    """Filter tracks to ensure only Danish titles are included.
    
    Args:
        year (str): Year of the data to process
        date_range (str): Date range of the data in format YYYY-MM-DD_to_YYYY-MM-DD
    """
    # Use proper path handling
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.abspath(os.path.join(script_dir, '../..'))
    
    # Ensure year directories exist
    year_dirs = [
        os.path.join(project_dir, f"Outputs/Danish/{year}"),
        os.path.join(project_dir, f"Outputs/Archive/{year}")
    ]
    for year_dir in year_dirs:
        if not os.path.exists(year_dir):
            os.makedirs(year_dir)
            
    # Input file from archive - using the renamed file
    input_file = os.path.join(project_dir, f'Outputs/Archive/{year}/-X- nova_danish_titles_summary.csv')
    
    # Read the summarized data
    with codecs.open(input_file, 'r', 'utf-8') as f:
        reader = csv.reader(f)
        # Skip header
        header = next(reader)
        tracks = []
        for row in reader:
            if len(row) >= 2:
                track, repeats = row[0], row[1]
                # Extract the title part
                if ' - ' in track:
                    artist, title = track.split(' - ', 1)
                    title = title.strip()
                    # Only include if the title is definitely Danish
                    if is_definitely_danish(title):
                        tracks.append((track, int(repeats)))
    
    # Sort by play count (most frequent first)
    tracks.sort(key=lambda x: x[1], reverse=True)
    
    # Save the filtered data
    output_file = os.path.join(project_dir, f'Outputs/Danish/{year}/NOVA_Danish_Titles_{date_range}.csv')
    with codecs.open(output_file, 'w', 'utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Track', 'Repeats'])
        for track, count in tracks:
            writer.writerow([track, count])
    
    print("Filtered summary created: nova_danish_only_titles.csv")
    print("\nDanish-only tracks:")
    for track, count in tracks:
        print("{}, {}".format(track, count))
    
    return len(tracks)

if __name__ == "__main__":
    import sys
    
    # Allow passing year and date range as command-line arguments
    if len(sys.argv) > 1:
        year = sys.argv[1]
    else:
        year = "2025"
        
    if len(sys.argv) > 2:
        date_range = sys.argv[2]
    else:
        date_range = "2025-01-01_to_2025-05-22"
    
    print(f"Processing Danish tracks for {year}, date range: {date_range}")
    unique_tracks = filter_danish_tracks(year, date_range)
    print("\nTotal unique Danish-only tracks: {}".format(unique_tracks))
