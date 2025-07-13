# Custom Playlist Processing System

This system automatically processes custom playlist files and prepares them for transfer to streaming services like Deezer, Spotify, and Apple Music.

## How to Use

### Starting the System

1. Double-click the `start_playlist_system.command` file in the main folder
2. This will start the watcher in the background and open the Custom Requests folder

### Adding a Playlist

1. Simply drop a CSV file into this folder (the Custom Requests folder)
2. The file will be automatically processed and moved to the "Processed" subfolder
3. The processed playlist will be available in `Outputs/Transfer/Custom`

### Special Naming Options

You can add special flags to your filename to enable additional processing:

- Add `_rank` or `_popular` to have your playlist automatically ranked by popularity
  - Example: `My_Favorites_rank.csv` or `Summer_Hits_popular.csv`
  - This will create an additional file sorted by popularity across streaming platforms

### File Format

Your CSV file should have one of these formats:

1. **Track,Group format**:
   ```
   Track,Group
   Artist - Title,Category
   ```

2. **Artist,Title format**:
   ```
   Artist,Title
   Taylor Swift,Blank Space
   ```

Any other format may not be processed correctly.

### Output Files

Processed files will be placed in:
- `Outputs/Transfer/Custom/`

For ranked playlists, you'll get:
- Regular version: `PlaylistName_YYYY-MM-DD.csv`
- Ranked version: `PlaylistName_Ranked_YYYY-MM-DD.csv`
- Detailed ranked version: `PlaylistName_Ranked_Detailed_YYYY-MM-DD.csv`

### Stopping the System

When you're done, you can stop the watcher by:
1. Double-clicking the `stop_playlist_system.command` file in the main folder

## Features

- **Automatic Deduplication**: Removes duplicate tracks intelligently
- **Smart Artist/Title Detection**: Properly identifies artist and title even when format varies
- **Popularity Ranking**: Can rank tracks by their popularity across streaming platforms
- **Format Conversion**: Converts various input formats to the standard Artist,Title format
- **Cached Results**: Popularity data is cached to improve performance for future runs
