#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function
import os
import sys
import csv
import codecs
import pandas as pd
from collections import Counter
from datetime import datetime
import glob

# Ensure UTF-8 encoding for Python 2.7
if sys.version_info[0] < 3:
    reload(sys)
    sys.setdefaultencoding('utf-8')

# Dictionary mapping station name to OnlineRadioBox identifier
STATION_MAP = {
    'NOVA': 'nova',              # NOVA FM
    'P3': 'drp3',               # DR P3
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

# These are stations for which we'll create individual extractions with language separation
PRIMARY_STATIONS = ['NOVA', 'P3']

# Stations that don't need language separation
NO_LANGUAGE_SEPARATION = ['RBClassics']

# All stations will be included in the combined analysis

def get_station_files(language, station=None):
    """Get all station files for a given language, optionally filtered by station.
    
    Args:
        language (str): 'Danish' or 'English'
        station (str, optional): Station name to filter by
        
    Returns:
        list: List of file paths
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    station_path = os.path.join(base_dir, "Outputs", "Stations")
    
    if station:
        # Get files for a specific station
        station_lang_path = os.path.join(station_path, station, language)
        files = glob.glob(os.path.join(station_lang_path, "*.csv"))
    else:
        # Get files for all stations
        files = []
        for station_name in STATION_MAP.keys():
            station_lang_path = os.path.join(station_path, station_name, language)
            if os.path.exists(station_lang_path):
                files.extend(glob.glob(os.path.join(station_lang_path, "*.csv")))
    
    return files

def consolidate_playlists(language, output_file=None, stations=None):
    """Consolidate playlist data from multiple stations for a given language.
    
    Args:
        language (str): 'Danish' or 'English'
        output_file (str, optional): Output file path
        stations (list, optional): List of stations to include
        
    Returns:
        pandas.DataFrame: Consolidated playlist data
    """
    # Get all the files for the specified language and stations
    if stations:
        files = []
        for station in stations:
            files.extend(get_station_files(language, station))
    else:
        files = get_station_files(language)
    
    print("Found {} files for {} tracks:".format(len(files), language))
    for file in files:
        print("  - {}".format(os.path.basename(file)))
    
    # Read and combine the data
    all_tracks = {}
    station_plays = {}  # Track which stations played each track
    station_data = {}  # Store data by station for analytics
    
    for file in files:
        station = None
        for station_name in STATION_MAP.keys():
            if station_name in file:
                station = station_name
                break
        
        if not station:
            print("Warning: Could not determine station for file: {}".format(file))
            continue
        
        try:
            df = pd.read_csv(file)
            # Initialize station data if not already done
            if station not in station_data:
                station_data[station] = {'track_count': 0, 'total_plays': 0}
                
            # Update station statistics
            station_data[station]['track_count'] += len(df)
            station_data[station]['total_plays'] += df['Repeats'].sum()
            
            for _, row in df.iterrows():
                track = row['Track']
                repeats = int(row['Repeats'])
                
                if track in all_tracks:
                    all_tracks[track] += repeats
                    if station not in station_plays[track]:
                        station_plays[track].append(station)
                else:
                    all_tracks[track] = repeats
                    station_plays[track] = [station]
        except Exception as e:
            print("Error processing file {}: {}".format(file, e))
    
    # Print station statistics
    if station_data:
        print("\nStation statistics for {} tracks:".format(language))
        for station, data in station_data.items():
            print("  {}: {} unique tracks, {} total plays".format(
                station, data['track_count'], data['total_plays']))
    
    # Create a DataFrame from the combined data
    tracks_list = []
    for track, repeats in all_tracks.items():
        stations_str = ", ".join(sorted(station_plays[track]))
        tracks_list.append({
            'Track': track,
            'Repeats': repeats,
            'Stations': stations_str,
            'Station_Count': len(station_plays[track])
        })
    
    # Convert to DataFrame and sort
    if tracks_list:
        result_df = pd.DataFrame(tracks_list)
        # Sort by repeats first, then by number of stations, then by track name
        result_df = result_df.sort_values(
            ['Repeats', 'Station_Count', 'Track'], 
            ascending=[False, False, True]
        )
        
        # Save to file if output_file is specified
        if output_file:
            result_df.to_csv(output_file, index=False, encoding='utf-8')
            print("Consolidated {} tracks saved to: {}".format(language, output_file))
        
        return result_df
    else:
        print("No {} tracks found in the specified stations".format(language))
        return pd.DataFrame()

def consolidate_all_playlists(stations=None):
    """Consolidate all playlist data (Danish, English, combined).
    
    Args:
        stations (list, optional): List of stations to include
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    combined_dir = os.path.join(base_dir, "Outputs", "Combined")
    
    # Make sure the Combined directory exists
    for subdir in ['Danish', 'English', 'All']:
        dir_path = os.path.join(combined_dir, subdir)
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
    
    # Generate date string for filenames
    date_str = datetime.now().strftime('%Y-%m-%d')
    
    # If no stations specified, use all stations for combined analysis
    if not stations:
        stations = list(STATION_MAP.keys())
        
    # Stations string for filenames
    if len(stations) == len(STATION_MAP):
        stations_str = "All_Stations"
    else:
        stations_str = "_".join(stations)
    
    # Process Danish tracks
    danish_output = os.path.join(
        combined_dir, "Danish", 
        "Combined_Danish_{}_{}.csv".format(stations_str, date_str)
    )
    danish_df = consolidate_playlists('Danish', danish_output, stations)
    print("\nTop 5 Danish tracks:")
    if not danish_df.empty:
        print(danish_df.head(5).to_string(index=False))
    
    # Process English tracks
    english_output = os.path.join(
        combined_dir, "English", 
        "Combined_English_{}_{}.csv".format(stations_str, date_str)
    )
    english_df = consolidate_playlists('English', english_output, stations)
    print("\nTop 5 English tracks:")
    if not english_df.empty:
        print(english_df.head(5).to_string(index=False))
    
    # Combine Danish and English for a complete dataset
    if not danish_df.empty and not english_df.empty:
        all_df = pd.concat([danish_df, english_df])
        all_df = all_df.sort_values(['Repeats', 'Station_Count'], ascending=[False, False])
        all_output = os.path.join(
            combined_dir, "All", 
            "Combined_All_{}_{}.csv".format(stations_str, date_str)
        )
        all_df.to_csv(all_output, index=False, encoding='utf-8')
        print("\nCombined {} tracks saved to: {}".format(len(all_df), all_output))
        print("\nTop 10 overall tracks:")
        print(all_df.head(10).to_string(index=False))
        
        # Additional analytics
        if len(all_df) > 0:
            print("\nPlaylist Analytics:")
            print("  Total unique tracks: {}".format(len(all_df)))
            print("  Danish tracks: {} ({}%)".format(
                len(danish_df), 
                round(len(danish_df) / len(all_df) * 100, 1) if len(all_df) > 0 else 0
            ))
            print("  English tracks: {} ({}%)".format(
                len(english_df), 
                round(len(english_df) / len(all_df) * 100, 1) if len(all_df) > 0 else 0
            ))
            
            # Track distribution by station count
            station_counts = all_df['Station_Count'].value_counts().sort_index()
            print("\nTrack distribution by station count:")
            for count, num_tracks in station_counts.items():
                percentage = round(num_tracks / len(all_df) * 100, 1)
                print("  Tracks played on {} station{}: {} ({}%)".format(
                    count, "s" if count > 1 else "", num_tracks, percentage
                ))

def main():
    """Main function to handle command-line arguments."""
    print("Radio Playlist Consolidator")
    print("===========================")
    
    # Parse command-line arguments
    automated_mode = False
    station_args = []
    i = 1
    
    while i < len(sys.argv):
        arg = sys.argv[i].lower()
        if arg in ['--help', '-h']:
            print("Usage: python radio_playlist_consolidator.py [OPTIONS] [STATIONS...]")
            print("\nOptions:")
            print("  --primary     Only consolidate primary stations (NOVA, P3)")
            print("  --all         Consolidate all stations (default)")
            print("  --list        List all available stations")
            print("  --no-prompt   Skip interactive prompts (for automated runs)")
            print("  --automated   Same as --no-prompt")
            print("\nStations: Specify station names to limit consolidation")
            print("  Available stations: {}".format(", ".join(STATION_MAP.keys())))
            return
        elif arg in ['--no-prompt', '--automated']:
            automated_mode = True
        elif arg != '--all':
            station_args.append(sys.argv[i])
        i += 1
    
    # Check if specific stations are requested
    if station_args:
            
        # Check for --list
        if '--list' in station_args:
            print("Available stations:")
            for station, station_id in STATION_MAP.items():
                if station in PRIMARY_STATIONS:
                    print("  {} ({}) - Primary station".format(station, station_id))
                else:
                    print("  {} ({})".format(station, station_id))
            return
            
        # Check for --primary
        if '--primary' in station_args:
            print("Consolidating playlists for primary stations: {}".format(", ".join(PRIMARY_STATIONS)))
            consolidate_all_playlists(PRIMARY_STATIONS)
            return_val = 0
        else:
            # Filter out special flags
            stations = [arg for arg in station_args if not arg.startswith('--')]
            if stations:
                print("Consolidating playlists for stations: {}".format(", ".join(stations)))
                consolidate_all_playlists(stations)
            else:
                # Default to all stations
                print("Consolidating playlists for all stations")
                consolidate_all_playlists()
    else:
        print("Consolidating playlists for all stations")
        print("This will include: {}".format(", ".join(STATION_MAP.keys())))
        consolidate_all_playlists()
        
    # Return the automated mode flag for use after main()
    return automated_mode

if __name__ == "__main__":
    automated_mode = main()
    
    # Only prompt in interactive mode
    prepare_transfer = False
    
    if not automated_mode:
        try:
            prepare_transfer = input("\nPrepare CSV files for music service playlist transfer? (y/n): ").lower() == 'y'
        except EOFError:
            print("\nRunning in non-interactive mode, skipping transfer prompt.")
    
    if prepare_transfer:
        try:
            import prepare_playlist_transfer
            prepare_playlist_transfer.prepare_radio_playlists()
        except ImportError as e:
            print(f"\nError: {str(e)}")
            print("Please ensure prepare_playlist_transfer.py is in the Scripts directory and all dependencies are installed.")
        except Exception as e:
            print(f"\nError preparing transfer files: {str(e)}")
            print("Check the log file for more details.")

