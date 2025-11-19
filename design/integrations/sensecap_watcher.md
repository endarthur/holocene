# SenseCap Watcher Integration for Holocene

## Overview

SenseCap Watcher ($79 vision AI device) integration for privacy-conscious activity tracking.

**Key Principle:** Manual-only capture, never automatic. User initiates all vision analysis.

## Hardware Specs

- **Camera:** Visual capture
- **Microphone:** Optional voice commands
- **Processing:** Local AI + API calls
- **Connectivity:** Wi-Fi
- **Power:** USB-C

## Integration Architecture

### Option 1: Direct API Integration (Recommended)

**Flow:**
1. User triggers Watcher (button press or voice: "What am I working on?")
2. Watcher captures screen image
3. Watcher calls Holocene API endpoint
4. Holocene sends image to NanoGPT vision model
5. DeepSeek analyzes: "Coding in VSCode - Python debugging"
6. Holocene logs activity with AI-generated description
7. Watcher provides audio/visual confirmation

**Privacy:**
- Image never stored, only sent to NanoGPT API
- All processing via your $8/month NanoGPT subscription
- Respects trust tier system (though new captures are always "recent")
- User controls exactly when capture happens

### Option 2: Custom Firmware (Advanced)

Replace Seeed's cloud with local Holocene server:
- Flash custom firmware using their SDK
- Run local model for quick analysis
- Use NanoGPT for deeper context
- Full privacy control

## API Endpoints to Implement

```python
# New endpoints for Watcher integration

@app.post("/api/v1/watcher/analyze")
async def analyze_screen(
    image: UploadFile,
    watcher_id: str,  # Unique device ID
    timestamp: Optional[datetime] = None
):
    """
    Analyze screen capture and log activity.

    Flow:
    1. Receive image from Watcher
    2. Send to NanoGPT Qwen/Qwen3-VL-235B-A22B-Instruct
    3. Parse response for:
       - Activity type (coding, research, etc.)
       - Detected application
       - Work context
       - Suggested tags
    4. Create activity with source="watcher"
    5. Return confirmation + activity ID
    """
    pass

@app.get("/api/v1/watcher/status")
async def watcher_status(watcher_id: str):
    """Return recent activities from this Watcher device."""
    pass
```

## Vision Model Prompts

```python
WATCHER_ANALYSIS_PROMPT = """
You are analyzing a screen capture to help with activity tracking.

Analyze this image and determine:
1. **Activity Type**: coding, research, documentation, communication, meeting, learning, planning, break, or other
2. **Application**: What software/website is visible?
3. **Context**: work, personal, open_source, or unknown
4. **Description**: Brief description of the activity (1 sentence)
5. **Suggested Tags**: 2-4 relevant tags

Format response as JSON:
{
  "activity_type": "coding",
  "application": "VSCode",
  "context": "open_source",
  "description": "Debugging Python code in VSCode - working on link management system",
  "tags": ["python", "debugging", "holocene"],
  "confidence": 0.95
}

Be specific but concise. Focus on observable facts from the screen.
"""
```

## Privacy Considerations

**Manual Trigger Only:**
- ✅ User presses button or says "analyze"
- ❌ Never automatic/periodic capture
- ❌ No continuous monitoring

**Data Flow:**
- Image → Holocene → NanoGPT → Deleted
- Only text description stored locally
- No image retention anywhere
- Respects existing privacy sanitizer

**Trust Tier:**
- Watcher captures are always "recent" tier
- But controlled environment (your screen, your trigger)
- Different risk profile than web scraping

## Configuration

```yaml
# ~/.config/holocene/config.yml

integrations:
  watcher_enabled: true
  watcher_devices:
    - id: "watcher-001"
      name: "Desk Watcher"
      api_key: "secure-random-key"
      auto_tag: ["watcher-desk"]

  watcher_vision_model: "Qwen/Qwen3-VL-235B-A22B-Instruct"
  watcher_confidence_threshold: 0.7  # Only log if AI is confident
```

## CLI Commands

```bash
# Register a Watcher device
holo watcher register --name "Desk Watcher"

# Show Watcher activity
holo watcher status

# Test Watcher connection
holo watcher test --id watcher-001

# Disable/enable Watcher
holo watcher disable --id watcher-001
```

## Watcher Firmware Configuration

If using custom firmware, configure Watcher to call:
```
POST https://your-holocene-instance/api/v1/watcher/analyze
Authorization: Bearer <watcher-api-key>
Content-Type: multipart/form-data

image: <captured-image.jpg>
watcher_id: watcher-001
```

## Use Cases

**1. Context Switching Detection**
- Working on Project A
- Get interrupted, switch to Project B
- Press Watcher button when resuming
- "Oh right, I was debugging the link archiver"

**2. Time Tracking Verification**
- Manual log says "coding for 2 hours"
- Watcher captures confirm: actually alternated between coding and Slack
- Data source alignment reveals reality

**3. Flow State Documentation**
- Deep focus session
- Periodically capture screens (manual button press)
- Build visual timeline of deep work session
- Review later to understand productivity patterns

**4. Meeting Context**
- In video call
- Capture screen: "Video meeting - discussing Holocene roadmap"
- Auto-tags with participants if visible
- Provides meeting context for daily review

## Future Enhancements

- **Voice commands:** "Holocene, what was I doing?"
- **Multi-modal analysis:** Audio + vision for meeting transcription
- **Screen OCR:** Extract code snippets, URLs, document titles
- **Activity continuity:** "You were working on this 2 hours ago"
- **Pomodoro integration:** Auto-capture at end of work sessions

## Security

**API Key Management:**
- Generate unique key per Watcher device
- Revoke compromised keys easily
- Rate limiting: 100 captures/hour max

**Network Security:**
- HTTPS only
- Optional: self-hosted Holocene server
- VPN recommended for remote access

## Cost Analysis

**NanoGPT Budget:**
- Current: 2000 calls/day, $8/month
- Vision calls same price as text
- ~50 Watcher captures/day = well within budget
- Still room for daily analysis runs

## Implementation Roadmap

**Phase 3.1: Basic Integration**
- [ ] Create Watcher API endpoints
- [ ] Vision model integration
- [ ] Basic CLI commands
- [ ] Documentation

**Phase 3.2: Enhanced Features**
- [ ] Multiple device support
- [ ] Voice command handling
- [ ] Screen OCR extraction
- [ ] Activity suggestions

**Phase 3.3: Advanced**
- [ ] Custom firmware option
- [ ] Local model fallback
- [ ] Multi-modal analysis
- [ ] Timeline reconstruction

## Alternative: Local LLaVA Model

If privacy is paramount, run vision model locally:
- LLaVA 1.5 (7B or 13B)
- Runs on consumer hardware
- No external API calls
- Slower but 100% private
- Watcher → Local server → Local model → SQLite

## Conclusion

SenseCap Watcher + Holocene = **Perfect ADHD-friendly activity tracker**

- Visual context capture
- AI-powered activity classification
- Privacy-respecting (manual only)
- Affordable ($79 device + $8/month API)
- Fits existing Holocene architecture
- Enables Phase 3 vision features

This could genuinely solve the "what was I doing?" problem that plagues ADHD brains!
