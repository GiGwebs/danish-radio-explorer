#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function
import pandas as pd
import csv
from collections import Counter

def summarize_tracks():
    # Read the original CSV file
    print("Reading CSV file...")
    df = pd.read_csv('nova_danish_titles_2025.csv')
    
    # Create a list of "Artist - Title" strings
    artist_title_list = []
    for _, row in df.iterrows():
        artist_title = "{} - {}".format(row['Artist'], row['Title'])
        artist_title_list.append(artist_title)
    
    # Count the occurrences of each artist-title combination
    track_counts = Counter(artist_title_list)
    
    # Sort by count (most frequent first)
    sorted_tracks = sorted(track_counts.items(), key=lambda x: x[1], reverse=True)
    
    # Save the summarized data
    with open('nova_danish_titles_summary.csv', 'w') as f:
        writer = csv.writer(f)
        writer.writerow(['Track', 'Repeats'])
        for track, count in sorted_tracks:
            writer.writerow([track, count])
    
    print("Summary created: nova_danish_titles_summary.csv")
    
    # Print a sample of the results
    print("\nSample of summarized tracks (most repeated first):")
    for track, count in sorted_tracks[:10]:
        print("{}, {}".format(track, count))
    
    return len(sorted_tracks)

if __name__ == "__main__":
    unique_tracks = summarize_tracks()
    print("\nTotal unique Danish tracks: {}".format(unique_tracks))
