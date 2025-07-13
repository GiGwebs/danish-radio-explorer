# Danish Radio Explorer - Project Plan

This document outlines the development roadmap for transforming the existing Danish Radio Playlist Extraction System into a modern desktop application while preserving all current functionality.

## Project Overview

The Danish Radio Explorer project aims to create a user-friendly desktop application with a modern UI that integrates the existing Danish Radio Playlist Extraction System. The application will provide manual update controls, playlist exploration, m3u generation for DJ software, and library integration, while maintaining the current automated system's functionality.

## Technology Stack

- **Frontend**: React.js with Tailwind CSS/DaisyUI
- **Backend**: Python (existing scripts with API wrapper)
- **Desktop Framework**: Tauri (Rust-based)
- **Communication**: HTTP API between frontend and Python backend
- **Packaging**: PyInstaller for Python + Tauri bundling

## Development Phases

### Phase 1: Setup & Foundation

- [x] Review and audit existing radio filter project
- [x] Fix critical issues in current system (EOFError, terminal popups)
- [x] Implement email notifications with AppleScript integration
- [ ] Safeguard and commit current working project (baseline)
- [ ] Create GitHub repository with branching structure
- [ ] Install development dependencies (Rust, Node.js, Python, Tauri CLI)
- [ ] Set up initial Tauri project with React frontend
- [ ] Create Python API server skeleton (Sanic/Flask)
- [ ] Establish basic communication between frontend and Python via Rust bridge
- [ ] Verify baseline functionality and commit initial structure

### Phase 2: Core Integration

- [ ] Integrate existing radio scripts with minimal modifications
- [ ] Create API endpoints for playlist extraction
- [ ] Add endpoints for manual update triggering
- [ ] Implement async task handling for long operations
- [ ] Write unit tests for backend
- [ ] Verify automated scripts still function correctly
- [ ] Create application shell and navigation
- [ ] Design and implement base component library (DaisyUI/Tailwind)
- [ ] Build dashboard layout and state management
- [ ] Create basic playlist viewing components
- [ ] Implement settings panel structure

### Phase 3: Feature Development

- [ ] Develop system status indicators
- [ ] Create update history visualization
- [ ] Implement manual update controls
- [ ] Add notification history and management
- [ ] Create data refresh mechanisms
- [ ] Build playlist browsing interface with filters
- [ ] Add language toggle (Danish/English)
- [ ] Implement search functionality
- [ ] Create track detail view with metadata
- [ ] Add sorting and filtering options
- [ ] Build path configuration UI
- [ ] Create email notification settings
- [ ] Add update scheduling controls
- [ ] Implement theme switching (light/dark)
- [ ] Create backup/restore options for settings
- [ ] Develop DJ library scanning functionality
- [ ] Create track matching algorithm
- [ ] Build m3u generation interface
- [ ] Add visualization for match success rate
- [ ] Implement export options and preferences

### Phase 4: Packaging & Finalization

- [ ] Configure PyInstaller for backend packaging
- [ ] Handle dependencies and resource paths
- [ ] Test bundled Python backend execution
- [ ] Configure Tauri to launch/terminate Python backend
- [ ] Add resources/assets to bundle config
- [ ] Handle window management and app lifecycle
- [ ] Implement system tray integration (optional)
- [ ] Perform comprehensive functionality testing
- [ ] Verify compatibility with existing automation
- [ ] Check resource usage and performance
- [ ] Test on target macOS environment
- [ ] Create user documentation and guides
- [ ] Write developer documentation
- [ ] Package final application for distribution
- [ ] Create installation instructions

## Key Features

1. **Modern UI Dashboard**
   - Status overview with last update time
   - Update history and statistics
   - Quick action buttons for common tasks
   - System notifications and alerts

2. **Playlist Explorer**
   - Browse playlists by station and language
   - Search and filter functionality
   - Sort by play count, date, and other metrics
   - Cross-station analysis visualization

3. **Manual Controls**
   - On-demand update triggering
   - Station selection for targeted updates
   - Progress indicators and real-time feedback
   - Cancellation and pause functionality

4. **DJ Integration**
   - M3U playlist generation for DJ software
   - Library scanning and matching
   - Match confidence indicators
   - Customizable export options

5. **Settings Management**
   - Path configuration
   - Email notification preferences
   - Update scheduling
   - UI preferences (theme, language)

## Development Workflow

- **Branch Strategy**:
  - `main`: Production-ready code
  - `develop`: Integration branch
  - `feature/*`: Feature development
  - `bugfix/*`: Bug fixes

- **Testing**:
  - Unit tests for Python API endpoints
  - Integration tests for frontend-backend communication
  - E2E tests for critical workflows
  - Regression tests to ensure existing functionality

- **Release Process**:
  - Version tagging
  - Release notes generation
  - macOS package creation
  - Documentation updates

## Maintenance Guidelines

- Regularly back up the original scripts
- Document any changes made to core functionality
- Maintain compatibility with existing file structures
- Ensure the automated system continues to function independently

## Timeline

| Phase | Estimated Duration | Target Completion |
|-------|-------------------|-------------------|
| Phase 1: Setup & Foundation | 2 weeks | TBD |
| Phase 2: Core Integration | 3 weeks | TBD |
| Phase 3: Feature Development | 4 weeks | TBD |
| Phase 4: Packaging & Finalization | 2 weeks | TBD |

## Success Criteria

1. The desktop application successfully integrates all existing radio filter functionality
2. Users can trigger updates manually and view results in real-time
3. The playlist explorer provides intuitive browsing and search capabilities
4. M3U generation and DJ library matching works accurately
5. The application is packaged as a standalone macOS app
6. The existing automated system continues to function without interruption
