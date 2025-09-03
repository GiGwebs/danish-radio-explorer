# Radio Filter Scripts

This directory contains the end-to-end automation for extracting radio playlists, consolidating them, and generating transfer files.

## Quick start (manual run)

Use the venv-aware wrapper (auto-bootstraps dependencies on first run):

```bash
/Users/gigwebs/Library/CloudStorage/Dropbox/MUSIC\ BANK/Rekordbox\ Scouts/Rekordbox\ Filter/Radio\ Filter/Scripts/run_radio_update.sh --force --extract-log-level INFO --notify-email ""
```

Notes:
- `--force` runs immediately regardless of the usual Tue+Fri safeguard.
- Omit `--force` to respect the default schedule (processes only on Tuesdays and Fridays).
- Set `--notify-email you@example.com` to enable email notifications.

## Outputs and monitoring
- Status JSON (includes `stations_no_playlist`):
  - `Radio Filter/Outputs/Status/last_update.json`
- Logs:
  - `Radio Filter/Logs/auto_update_*.log`
- No-playlist markers (per station/day):
  - `Radio Filter/Outputs/Stations/<Station>/Raw/<Station>_NoPlaylist_past_7_days_<date>.json`

## Scheduling on macOS

You can schedule the update via launchd (recommended) or cron.

### Option A: launchd (recommended)
Create a LaunchAgent so it runs daily at 09:30. The orchestrator will only process on Tuesdays and Fridays unless `--force` is set.

1) Create a file at `~/Library/LaunchAgents/com.local.radio.update.plist` with the following content:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.local.radio.update</string>

  <key>ProgramArguments</key>
  <array>
    <string>/Users/gigwebs/Library/CloudStorage/Dropbox/MUSIC BANK/Rekordbox Scouts/Rekordbox Filter/Radio Filter/Scripts/run_radio_update.sh</string>
    <string>--extract-log-level</string>
    <string>INFO</string>
    <string>--notify-email</string><string>you@example.com</string>
  </array>

  <key>WorkingDirectory</key>
  <string>/Users/gigwebs/Library/CloudStorage/Dropbox/MUSIC BANK/Rekordbox Scouts/Rekordbox Filter/Radio Filter</string>

  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>9</integer>
    <key>Minute</key><integer>30</integer>
  </dict>
  <!-- Tip: To restrict to specific weekdays, you may instead use an array of dictionaries,
       e.g., run only Tue and Fri:
       <key>StartCalendarInterval</key>
       <array>
         <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>30</integer></dict>
         <dict><key>Weekday</key><integer>6</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>30</integer></dict>
       </array>
       (launchd uses 1=Sun .. 7=Sat)
  -->

  <key>StandardOutPath</key>
  <string>/Users/gigwebs/Library/CloudStorage/Dropbox/MUSIC BANK/Rekordbox Scouts/Rekordbox Filter/Radio Filter/Logs/launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/gigwebs/Library/CloudStorage/Dropbox/MUSIC BANK/Rekordbox Scouts/Rekordbox Filter/Radio Filter/Logs/launchd.err.log</string>

  <key>RunAtLoad</key><true/>
</dict>
</plist>
```

2) Load it:

```bash
launchctl load -w ~/Library/LaunchAgents/com.local.radio.update.plist
```

3) Later, to unload:

```bash
launchctl unload -w ~/Library/LaunchAgents/com.local.radio.update.plist
```

### Option B: cron
Add a daily cron at 09:30. The orchestrator will process only on Tuesdays and Fridays unless `--force` is added.

```bash
crontab -e
# Add:
30 9 * * * /Users/gigwebs/Library/CloudStorage/Dropbox/MUSIC\ BANK/Rekordbox\ Scouts/Rekordbox\ Filter/Radio\ Filter/Scripts/run_radio_update.sh --extract-log-level INFO >> \
  /Users/gigwebs/Library/CloudStorage/Dropbox/MUSIC\ BANK/Rekordbox\ Scouts/Rekordbox\ Filter/Radio\ Filter/Logs/cron.out.log 2>&1
```

## Frontend dashboard (Streamlit)

Run a local dashboard to visualize status, drill into stations, trigger a run, and view logs.

### Quick start (recommended)

From the project root:

```bash
./Scripts/run_dashboard.sh
```

This script bootstraps the virtual environment (if missing), installs requirements, and starts the app.

### Manual setup (alternative)

1) Install dependencies (inside project root):

```bash
source .venv/bin/activate  # or create: python3 -m venv .venv && source .venv/bin/activate
python -m pip install -r Scripts/requirements.txt
```

2) Start the app:

```bash
streamlit run Scripts/webapp/app.py
```

Notes:
- The app reads `Outputs/Status/last_update.json` and `Outputs/Stations/` to render KPIs and per-station files.
- The "Run now" button calls `Scripts/run_radio_update.sh` and uses a lock file in `Logs/.update.lock` to prevent overlaps.
- Logs are read from `Logs/auto_update_*.log` and the file referenced in `log_file` within the status JSON.

## Notes
- Desktop notifications may not display if the process runs in a non-interactive session. Email remains available via `--notify-email`.
- The wrapper bootstraps a virtual environment on first run and uses it thereafter.
- Logs include an explicit line listing stations excluded from retries due to `no_playlist` classification.
