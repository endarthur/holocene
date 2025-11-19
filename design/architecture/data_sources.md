# Data Sources Architecture

Holocene integrates with multiple data sources for comprehensive activity tracking.

**For complete details, see `holocene_design.md` lines 51-142.**

---

## Implemented Sources ✅

### journel Integration
- Manual activity logs, project tracking
- Read-only integration (8 active projects)
- Location: `src/holocene/integrations/journel.py`

### Git Activity
- Commit frequency, repo switching, branch activity
- Personal repos only (GGR, wabisabi, Pollywog, etc.)
- Location: `src/holocene/integrations/git_scanner.py`

---

## Planned Sources (Autonomous Mode)

### Browser Activity
- Chrome/Edge extension (unpublished, developer mode)
- Tracks: Active tab, domain, category, time spent
- Privacy: Blacklist for sensitive domains, domain-level only
- Communication: WebSocket/HTTP POST every 30s to localhost:8765

### Window Focus
- OS-level window title monitoring
- Tracks: Active application, context switches
- Privacy: Similar blacklist to browser

### System Metrics
- CPU/RAM usage patterns via psutil
- Running processes (whitelisted only)
- Indicates intensive work periods

### Home Assistant
- Temperature, humidity, light levels
- Presence detection (office occupancy)
- Office door state, any enabled sensors
- **Output:** Mi Band vibrations, environment control

### Google Calendar
- Events (personal calendar only, not work)
- Time blocks, meeting patterns
- Focus block detection

### Mi Band (via Home Assistant)
- Heart rate patterns (stress vs. calm)
- Sleep quality/duration, steps/activity
- **Output:** Vibration notifications for breaks, focus blocks

---

## Data Flow

```
Data Source → Privacy Sanitizer → SQLite Database → LLM Analysis (NanoGPT)
```

**Privacy Tier Filtering:**
- Tier 1 (NanoGPT): Generic descriptions, personal projects
- Tier 2 (Local): Work context, screenshots
- Tier 3 (Never): Financial, confidential data

**See:** `design/architecture/privacy_model.md` for sanitization details

---

**Last Updated:** 2025-11-17
**Status:** 2 sources implemented ✅, 6 planned for autonomous mode
