# Laney-chan Field Assistant
**Vision Document - Future Phase**

## Overview

Transform Laney-chan from a passive archive assistant into an active field support system for geological fieldwork. Think MGS V's Mother Base support, but for science.

## The Vision

**Core Concept:** Laney-chan as HQ monitoring - providing contextual awareness, data logging, and decision support during remote fieldwork.

**Key Principle:** Offline-first. Everything must work without internet connectivity.

## Technology Stack (Realistic)

### Display Layer
**AR Glasses** (not sci-fi holograms)
- **Current options:**
  - Ray-Ban Meta Smart Glasses (camera, audio, no display)
  - Xreal Air 2 (display, no camera)
  - Apple Vision Pro (overkill, but could work)
  - Future: Meta Orion-style AR glasses (2026+)

**Fallback:** Phone screen + earbuds (works today)

**UI Aesthetic:**
- Purple holographic theme (consistent with Holocene branding)
- Inspired by MGS V iDroid interface
- Clean typography, satisfying interactions
- Tactical/scientific aesthetic

### Backend Infrastructure

**Hardware:**
- **holocene-rei** (LXC container server) - HQ server
- **M4 Mac Mini** - Local LLM inference (DeepSeek V3, 128K context)
- **Android phone** - Field device (GPS, camera, sensors)

**Software Stack:**
- **FastAPI** - REST API for field device
- **ATAK** - Android Team Awareness Kit (tactical mapping)
- **OpenStreetMap** - Local tile server (offline maps)
- **Whisper** - Local speech-to-text
- **Piper/Bark** - Local text-to-speech
- **PostgreSQL/PostGIS** - Spatial database

## Features by Phase

### Phase 1: Mapping Foundation
**Goal:** Get spatial awareness and logging working

**Features:**
- Local OSM tile server on holocene-rei
- GPS logging to Holocene database
- Web map viewer showing:
  - Field sample locations
  - Photo geotagging
  - Field notes with location
- Basic field log CLI: `holo field log "Found interesting outcrop"`

**Tech:**
- OSM data: Download region via [Geofabrik](https://download.geofabrik.de/)
- Tile server: [Martin](https://github.com/maplibre/martin) or Tegola
- Frontend: MapLibre GL JS

### Phase 2: ATAK Integration
**Goal:** Professional field mapping with Laney integration

**Features:**
- ATAK plugin communicating with Holocene API
- Real-time position sharing
- Sample sites as ATAK markers
- Field notes synced to ATAK
- Export field data as KML/GeoJSON

**Why ATAK:**
- Free, open source, actively developed
- Used by actual military/emergency services
- Offline-first architecture
- Extensible plugin system
- Works on cheap Android phones

**ATAK Plugin Capabilities:**
- Query Holocene database from map
- "What samples are near me?"
- Auto-create markers when taking field photos
- Voice command interface

### Phase 3: Laney Voice Assistant
**Goal:** Natural language interaction during fieldwork

**Interaction Model:**
```
User: "Laney, what's the formation here?"
Laney: "Based on your location (23.5°S, 45.2°E), you're on the
        Archean Rio das Velhas Greenstone Belt. You photographed
        a similar komatiite outcrop 3km northeast in 2022."

User: "Log sample: fresh komatiite, spinifex texture"
Laney: "Sample logged. This is your 4th komatiite sample this trip.
        Reminder: you wanted to check chromite content."
```

**Tech:**
- **STT:** OpenAI Whisper (local, offline)
- **LLM:** DeepSeek V3 via ollama (128K context)
- **TTS:** Piper (fast, local) or Bark (more natural)
- **Wake word:** "Hey Laney" via Porcupine

**Context for LLM:**
- Your current GPS location
- Recent field notes (last 24h)
- Relevant archived links (from your 1,210 telegram links!)
- Historical samples nearby
- Weather forecast
- Your stated goals for the trip

### Phase 4: Predictive/Proactive Features
**Goal:** Laney anticipates needs and provides suggestions

**Features:**
- **Safety monitoring:**
  - "Weather alert: thunderstorm approaching in 2 hours"
  - "You haven't checked in for 4 hours, should I alert emergency contact?"
  - "Battery at 15%, recommend heading back"

- **Contextual suggestions:**
  - "You're near a site you photographed in 2022, want to revisit?"
  - "Based on your trajectory, you're approaching the known ultramafic zone"
  - "That outcrop texture matches the spinifex pattern from your paper on komatiites"

- **Research connections:**
  - "You bookmarked a paper about Barberton komatiites yesterday - this formation is similar"
  - "Your notes mention looking for chromite - common in these settings"

- **Pattern recognition:**
  - "You've spent 90 minutes in this area - found something interesting?"
  - "This is your 5th komatiite sample - building a collection?"

## Geology-Specific Use Cases

### Komatiite Field Survey Example
```
[Morning briefing]
Laney: "Good morning. Today's forecast: 28°C, clear skies.
        You're targeting the komatiite belt 12km north. I've marked
        three outcrops from previous surveys on your map."

[In the field]
User: "Laney, sample photo" [takes picture]
Laney: "Logged. Excellent spinifex texture visible. This makes
        sample #3 today, all from the same flow unit."

[Analysis]
User: "Compare to yesterday's samples"
Laney: "Yesterday's samples were 2km south, slightly different
        olivine grain size. Could indicate flow direction variability.
        Checking your 2021 thesis notes... yes, you hypothesized this."

[Evening]
Laney: "Field session complete. 8.2km traveled, 7 samples logged,
        43 photos geotagged. Notable finding: the spinifex flow
        extends further east than mapped. Should I update the base map?"
```

## UI Aesthetic

**Inspiration:** MGS V iDroid (tactical cool + scientific precision)

**Color Palette:**
- Primary: Purple gradient (#667eea → #764ba2)
- Accent: Cyan/teal for active elements
- Dark theme (better for outdoor visibility)
- High contrast for sunlight readability

**Typography:**
- Monospace font for coordinates/data
- Sans-serif for prose
- Clear hierarchy

**Interactions:**
- Voice-first (hands-free in field)
- Gesture shortcuts on AR glasses
- Fallback to touch on phone

**HUD Elements:**
- Minimal by default
- Current location (coordinates)
- Compass heading
- Battery/connectivity status
- Quick access to recent samples
- Alert notifications

## Data Privacy

**Critical:** Field data may contain sensitive location information (mineral deposits, research sites)

**Privacy Model:**
- **Tier 1 (Local-only):** GPS tracks, sample locations, field notes
- **Tier 2 (Encrypted sync):** Cloud backup, but encrypted
- **Tier 3 (Public):** Published papers, public outcrops

**LLM Processing:**
- All inference runs locally (M4 Mac Mini)
- No data sent to cloud LLMs
- Field data never leaves your network

## Hardware Requirements

### Minimum (Phase 1-2)
- Android phone with GPS
- holocene-rei server
- Internet for initial setup (then offline)

### Optimal (Phase 3-4)
- AR glasses (XReal Air 2 or similar)
- M4 Mac Mini for local LLM
- Rugged Android phone (CAT S62 or similar)
- Satellite communicator (Garmin inReach or SPOT Gen4) for emergencies
- Portable battery pack

### Future Dream Setup
- Meta Orion-style AR glasses (2026+)
- Bone conduction audio (AfterShokz)
- Satellite messaging integration (see below)

## Connectivity Tiers

Laney's capabilities adapt based on available connectivity:

### Tier 1: Full Network (HQ Connected)
**Scenario:** WiFi/cellular to holocene-rei
**Capabilities:**
- Full DeepSeek V3 inference (128K context)
- Access to complete archive (1,200+ links, all papers)
- Real-time sync with main database
- High-quality TTS (Bark)
- Full map data

### Tier 2: PicoLaney (Phone-only, Offline)
**Scenario:** No network, phone has local LLM
**Capabilities:**
- Lightweight LLM on phone (Phi-3, Gemma 2B, or Llama 3.2 3B)
- Pre-cached map tiles (50-100MB for region)
- Recent field notes (last 30 days)
- Basic voice commands
- Photo geotagging and logging
- Fast TTS (Piper)

**Tech Stack:**
- **LLM:** Phi-3-mini (3.8B) or Llama 3.2 3B via Ollama Android
- **Storage:** SQLite database (syncs when connected)
- **Maps:** MBTiles format (vector tiles, 50-100MB per region)
- **Voice:** Whisper.cpp (optimized for mobile)

**Use Case:** Deep in the field, no signal, but still want voice logging and basic AI assistance.

### Tier 3: Emergency (Satellite Only)
**Scenario:** No cellular, only satellite messenger
**Capabilities:**
- Emergency beacon (SOS)
- Check-in messages ("All good", "Need pickup", "Medical")
- GPS position sharing
- Receive weather alerts
- Minimal text messages (140 chars, like SMS)

**Hardware Options (all non-Musk):**
- **Garmin inReach Mini 2** ($400, Iridium network)
  - Two-way messaging
  - Weather forecasts
  - SOS to GEOS rescue
  - ~50 hours battery

- **SPOT Gen4** ($150, Globalstar network)
  - Pre-set messages only
  - SOS to rescue
  - GPS tracking
  - Cheaper but less flexible

- **Zoleo** ($200, Iridium network)
  - Two-way messaging via phone app
  - SOS rescue
  - Weather forecasts
  - Good middle ground

**Integration Idea:**
- Send check-in to holocene-rei via satellite
- Laney logs your position automatically
- If check-in doesn't arrive on schedule, alert emergency contact
- Can request simple data: "WEATHER" → Laney replies with forecast via satellite

**Satellite Message Protocol:**
```
From field: "CHECKIN komatiite zone, 3 samples"
Laney reply: "Logged. Weather clear 4h. Sunset 1823."

From field: "QUERY nearest water"
Laney reply: "Stream 2.3km SE (23.54°S 45.32°E)"

Emergency: "SOS medical"
Laney action: Alert emergency contact, send last known position,
              notify rescue services, keep position tracking active
```

## Implementation Roadmap

### Phase 1: Q1 2025 (3-4 weeks)
- Set up local OSM tile server
- Create `holo field` CLI commands
- GPS logging to database
- Simple web map viewer

### Phase 2: Q2 2025 (6-8 weeks)
- Install ATAK on field phone
- Build Holocene ATAK plugin
- Test integration with real field trip
- Iterate on UX

### Phase 3: Q3 2025 (8-10 weeks)
- Set up local Whisper + DeepSeek V3
- Voice command prototype
- Test in controlled field setting
- Refine voice interaction

### Phase 4: Q4 2025+ (ongoing)
- Add predictive features
- AR glasses integration (when available)
- Machine learning on field patterns
- Community features (share field data with collaborators)

## References & Inspiration

**UI/UX:**
- Metal Gear Solid V: iDroid interface
- ATAK (Android Team Awareness Kit)
- Star Trek: LCARS (but less 90s)
- Modern tactical/aviation displays

**Technology:**
- ATAK: https://tak.gov/
- OpenStreetMap: https://www.openstreetmap.org/
- Whisper: https://github.com/openai/whisper
- DeepSeek V3: https://github.com/deepseek-ai/DeepSeek-V3

**Real-world examples:**
- Military C2 systems (minus the weapons)
- Emergency services dispatch
- Commercial pilot glass cockpits
- Scientific expedition support systems

## Why This Will Actually Work

Unlike most "AI assistant" vaporware, this is grounded in:

1. **Real need:** Geologists actually need better field data management
2. **Proven tech:** ATAK is battle-tested (literally)
3. **Offline-first:** Works in remote areas without connectivity
4. **Local LLMs:** No cloud dependency, respects privacy
5. **Incremental:** Each phase delivers value independently
6. **You're the user:** Designing for your own workflow ensures it's practical

## Next Steps

1. Document current field workflow (what's manual/painful?)
2. Set up local OSM server (can do this weekend)
3. Create basic GPS logging (already have DB schema)
4. Test ATAK on your Android phone
5. Build simple prototype for next field trip

---

**Status:** Vision document (not yet implemented)
**Last Updated:** 2025-11-24
**Next Review:** After Phase 1 prototype
