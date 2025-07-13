# Danish Radio Playlist Extraction System

[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](https://github.com/your-username/danish-radio-explorer)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

This project extracts and processes song data from multiple Danish radio stations, organizing tracks by language (Danish and English) and providing cross-station analysis to identify the most popular tracks across Denmark.

> **Note:** This project is being expanded to include a modern desktop application with UI. See the [Desktop Application](#desktop-application) section below for details.

## Project Structure

```
Radio Filter/
├── Scripts/                       # All extraction and processing scripts
│   ├── extract_radio_playlists.py # Main script for extracting playlists from all stations
│   ├── radio_playlist_consolidator.py # Script for combining and analyzing all station data
│   └── extract_p3_current_playlist.py # Legacy script for P3 station
├── Outputs/                       # All data output files
│   ├── Stations/                  # Individual station data
│   │   ├── NOVA/                  # NOVA Radio data
│   │   │   ├── Danish/            # Danish tracks from NOVA
│   │   │   ├── English/           # English tracks from NOVA
│   │   │   └── Raw/               # Raw NOVA playlist data
│   │   ├── P3/                    # P3 Radio data
│   │   │   ├── Danish/            # Danish tracks from P3
│   │   │   ├── English/           # English tracks from P3
│   │   │   └── Raw/               # Raw P3 playlist data
│   │   ├── TheVoice/              # TheVoice Radio data
│   │   └── ... (other stations)   # Similar structure for all stations
│   ├── Combined/                  # Combined analysis across all stations
│   │   ├── Danish/                # Combined Danish tracks analysis
│   │   ├── English/               # Combined English tracks analysis
│   │   └── All/                   # Complete dataset with all tracks
│   └── Previous_Attempts/         # Archive of previous approaches
└── README.md                      # This documentation file
```

## Scripts Usage

### Extracting Playlists from Radio Stations

1. Extract playlists from all supported stations:
   ```
   python Scripts/extract_radio_playlists.py
   ```

2. Extract playlists from specific stations:
   ```
   python Scripts/extract_radio_playlists.py NOVA P3 TheVoice
   ```
   Supported stations: NOVA, P3, TheVoice, Radio100, PartyFM, PopFM, RadioGlobus, SkalaFM, P4, RBClassics

### Consolidating and Analyzing Playlists

After extracting playlists from the desired stations, run the consolidator to generate combined analysis:
```
python Scripts/radio_playlist_consolidator.py
```

This will:
1. Combine all station data
2. Identify tracks played across multiple stations
3. Generate rankings by play count
4. Output combined files in the Outputs/Combined/ directory

## Data Format

### Individual Station Files
Station-specific output files contain the following columns:
- Track: In format "Artist - Title"
- Repeats: Number of times the track was played in the time period
- Timestamp: When the track was played (if available)

### Combined Analysis Files
The consolidated output files contain enhanced information:
- Track: In format "Artist - Title"
- Repeats: Total number of plays across all stations
- Stations: List of stations where the track was played
- Station_Count: Number of different stations playing the track

## Supported Radio Stations

The system currently extracts and analyzes playlists from these Danish radio stations:
- NOVA
- P3
- TheVoice
- Radio100
- PartyFM
- PopFM
- RadioGlobus
- SkalaFM
- P4
- RBClassics (R&B Classics)

## Language Detection

The system uses sophisticated language detection to classify tracks as Danish or English:
1. Danish-specific character detection (æ, ø, å)
2. Word-based language detection
3. Context from artist names
4. Special case handling for mixed-language titles

Tracks that cannot be confidently classified are listed separately.

## Dependencies

Install all required dependencies:
```
pip install -r requirements.txt
```

Main dependencies:
- requests: For fetching web content
- beautifulsoup4: For HTML parsing
- html5lib: For robust HTML handling
- pandas: For data manipulation and analysis
- langdetect: For language classification assistance
- deezer-python: For Deezer API integration
- flask: For OAuth authentication handling

## Deezer Playlist Transfer

The system prepares playlist data for transfer to Deezer using third-party services like Soundiiz or TuneMyMusic:

### Features

- **CSV Export**: Creates properly formatted CSV files for transfer services
- **Real Data Only**: Uses only actual radio playlist data (never fake or simulated data)
- **Language-Separated**: Creates separate files for Danish and English tracks
- **Prioritized by Popularity**: Tracks are ordered by play count and station coverage
- **Date-Tagged Files**: Includes the current date in filenames for tracking

### Usage

1. **Automatic**: After running the consolidator, it will ask if you want to prepare CSV files for transfer
2. **Manual**: Run directly anytime after consolidation:
   ```
   python Scripts/prepare_transfer_csv.py
   ```

The script will:
- Create CSV files in the `/Outputs/Transfer/` directory
- Format files for both Soundiiz and TuneMyMusic services
- Provide instructions for completing the transfer to Deezer

### Transfer Process

#### Option 1: Using Soundiiz
1. Go to [Soundiiz](https://soundiiz.com/)
2. Create a free account and log in
3. Go to 'Upload Playlist'
4. Select 'Import from a file'
5. Upload the `*_Soundiiz.csv` files
6. Convert to Deezer

#### Option 2: Using TuneMyMusic
1. Go to [TuneMyMusic](https://www.tunemymusic.com/)
2. Select 'Source: File'
3. Upload the `*_TuneMyMusic.csv` files
4. Select 'Destination: Deezer'
5. Login to your Deezer account
6. Start the transfer

## Email Notifications

The system can automatically send email notifications when new updates are available:

- **AppleScript Integration**: Uses macOS Mail app to send notifications
- **Customizable Notifications**: HTML-formatted emails with detailed results
- **Automated**: Notifications are sent automatically during scheduled updates

## Desktop Application

> **Coming Soon:** A modern desktop application with intuitive UI is in development.

### Key Features

- **Modern UI**: Beautiful, user-friendly interface built with Tauri and React/Vue
- **Dashboard**: Real-time status monitoring and update history
- **Playlist Explorer**: Browse, search, and filter playlists by language and station
- **Manual Controls**: Trigger updates on-demand with visual feedback
- **M3U Generation**: Create playlists compatible with DJ software from radio tracks
- **Library Matching**: Match radio tracks with your existing music collection
- **Settings Management**: Configure paths, email notifications, and scheduling

### Technology Stack

- **Frontend**: Modern web technologies (React/Vue + Tailwind/DaisyUI)
- **Backend**: Python API exposing existing radio script functionality
- **Framework**: Tauri for native desktop integration and packaging
- **Database**: Local storage for settings and cached data

### Development Roadmap

See the [Project Plan](docs/project_plan.md) for the detailed development roadmap and progress tracking.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
