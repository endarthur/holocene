# Self-Hosted Read-It-Later Evaluation

**Context:** Pocket shut down by Mozilla (July 2025)
**Evaluated:** 2025-11-19
**Source:** https://selfh.st/alternatives/read-later/

---

## Current Holocene Link Collection Status

**Existing Features:**
- Link collection with trust tiers (pre-LLM / early-LLM / recent)
- Internet Archive integration for archiving
- Browser bookmark import
- 1,145+ links currently tracked

**Missing Features:**
- Mobile quick-save interface
- Article text extraction/cleaning
- Offline reading
- Cross-device sync
- Browser extension for easy saving

---

## Self-Hosted Options Comparison

### 🥇 Wallabag (Most Popular)

**Pros:**
- Mature, well-established project
- Full API with good documentation
- Article text extraction (ad-free, cleaned)
- Browser extensions + mobile apps
- SQLite/MySQL/PostgreSQL support
- Easy Docker deployment
- Large ecosystem of integrations

**Cons:**
- Another service to maintain
- Overhead vs direct Holocene integration

**API:** ✅ Excellent - RESTful, well-documented
**Setup Difficulty:** Easy (Docker one-liner)
**Active Development:** ✅ Yes, very active
**Cost if Hosted:** €9/year

---

### 🥈 Linkding (Minimalist)

**Pros:**
- Intentionally minimal and fast
- Good API support
- Multi-user + SSO
- Web archiving built-in
- SQLite or PostgreSQL
- Very lightweight

**Cons:**
- Less feature-rich than Wallabag
- Minimal article text extraction

**API:** ✅ Good - RESTful
**Setup Difficulty:** Very easy (Docker)
**Active Development:** ✅ Yes
**Cost:** Free only (no hosted option)

---

### 🥉 Linkwarden (Modern)

**Pros:**
- Screenshots + Wayback Machine archiving
- Collections/tags/multi-user
- Fast development pace
- Modern UI
- Browser extensions + desktop apps

**Cons:**
- PostgreSQL required (no SQLite)
- More complex setup
- Relatively new project

**API:** ✅ Good
**Setup Difficulty:** Medium (requires PostgreSQL)
**Active Development:** ✅ Very active
**Cost:** Free only

---

### 🆕 Hoarder (AI-Powered)

**Pros:**
- **AI-based auto-tagging** (interesting!)
- OCR text extraction
- Video archiving support
- Mobile apps (iOS/Android)
- Modern stack

**Cons:**
- Brand new (first release 2024)
- Less proven/stable
- More overhead (AI processing)
- Unknown long-term maintenance

**API:** ✅ Assumed (has mobile apps)
**Setup Difficulty:** Medium-High
**Active Development:** ✅ Very active (new project)
**Cost:** Free only

---

### Others

| Service | Key Feature | API | Setup | Status |
|---------|-------------|-----|-------|--------|
| **Shiori** | Pocket-like interface | ✅ | Easy | Active |
| **Readeck** | Privacy-focused, e-book exports | ✅ | Easy | Active |
| **Grimoire** | Integration API, multi-user | ✅ | Easy | Active |
| **LinkAce** | Link monitoring, S3 backup | ✅ | Easy | Active |

---

## Integration Options for Holocene

### Option 1: Telegram Bot → Holocene (Recommended)

**Architecture:**
```
Telegram Bot → holo links add-url <url> --source=telegram
              ↓
          Holocene DB
              ↓
      Optional: IA archiving
```

**Pros:**
- No extra service to maintain
- Leverages existing `holo links` infrastructure
- Mobile-friendly (Telegram everywhere)
- Can add notes/tags via Telegram commands
- Simple to implement

**Cons:**
- No article text extraction (unless we add it)
- No offline reading without work
- Telegram dependency (but we likely use it anyway)

**Effort:** Low
**Maintenance:** Minimal

---

### Option 2: Wallabag API Sync

**Architecture:**
```
Wallabag (self-hosted) ← Save articles
         ↓
    Periodic sync via API
         ↓
    Holocene DB (holo links)
```

**Pros:**
- Full read-it-later experience
- Article text extraction handled
- Mobile apps + browser extensions
- Offline reading
- Can still use Holocene for research integration

**Cons:**
- Another service to maintain
- Docker container to run
- Potential data duplication
- Need sync logic

**Effort:** Medium
**Maintenance:** Medium (Docker updates, backups)

---

### Option 3: Browser Bookmarklet/HTTP Endpoint

**Architecture:**
```
Bookmarklet/Extension → POST to local endpoint
                              ↓
                      holo links add-url
                              ↓
                         Holocene DB
```

**Pros:**
- Extremely lightweight
- No external services
- Works cross-browser
- Simple implementation

**Cons:**
- Less convenient than mobile app
- No offline reading
- Manual text extraction
- Local-only (no remote saves)

**Effort:** Very Low
**Maintenance:** Minimal

---

### Option 4: Wallabag Hosted + API Sync

**Architecture:**
```
Wallabag (€9/year hosted) ← Save articles
              ↓
      API sync to Holocene
              ↓
          Research integration
```

**Pros:**
- Zero maintenance
- Full features
- Mobile apps work immediately
- Professional service
- Cheap (€9/year)

**Cons:**
- External dependency
- Annual cost
- Less control over data

**Effort:** Low
**Maintenance:** Zero

---

## Recommendation

### For Holocene Philosophy (Privacy-First, Local-First):

**Phase 1 (Quick Win):** Telegram Bot Integration
- Build simple bot that saves to `holo links`
- Add optional IA archiving trigger
- Leverage existing infrastructure
- **Effort:** 2-3 hours implementation

**Phase 2 (If Needed):** Add article text extraction
- Either via Wallabag API (without self-hosting)
- Or add Mercury/Readability.js to Holocene directly
- Store cleaned text in database
- **Effort:** 4-6 hours

**Phase 3 (Long-term):** Consider self-hosting Wallabag if...
- We need offline reading
- We want mobile apps
- Article extraction becomes critical
- We're comfortable maintaining another service

---

## Decision Framework

### Use Telegram Bot When:
- ✅ Quick mobile saves are primary need
- ✅ Want minimal maintenance overhead
- ✅ Already using Telegram regularly
- ✅ Don't need offline reading immediately

### Self-Host Wallabag When:
- ✅ Need full read-it-later experience
- ✅ Want mobile apps + browser extensions
- ✅ Comfortable maintaining Docker services
- ✅ Need article text extraction
- ✅ Want offline reading

### Use Hosted Wallabag When:
- ✅ Want zero maintenance
- ✅ €9/year is acceptable
- ✅ Don't need full data sovereignty
- ✅ Want professional service reliability

---

## Next Steps

1. **Immediate:** Add to architecture review agenda
2. **Short-term:** Prototype Telegram bot integration
3. **Evaluate:** Test bot for 2-4 weeks
4. **Decide:** Keep bot-only or add Wallabag sync based on usage

---

## Related Documents

- `docs/public_apis_evaluation.md` - API integration guidelines
- `docs/ROADMAP.md` - Architecture review planning
- `design/architecture/integration_guidelines.md` - (TBD) Integration patterns

---

**Last Updated:** 2025-11-19
**Decision Status:** Draft - pending architecture review
