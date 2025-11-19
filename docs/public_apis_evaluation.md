# Public APIs Evaluation for Holocene

**Source:** https://github.com/public-apis/public-apis
**Evaluated:** 2025-11-19
**Focus:** APIs useful for personal knowledge management, research, and productivity tracking

---

## Current Integration Status

### ✅ Already Implemented
- **Crossref** - Academic paper search, DOI lookup, pre-LLM filtering (`holo papers search`)
- **Internet Archive** - Public domain books, archiving (`holo books discover-ia`)
- **GitHub** - Repository scanning via git_scanner integration
- **Mercado Livre** - Product favorites tracking (via OAuth + web scraping)

---

## 🔥 High Priority - Recommended for Integration

### Books & Academic Research

| API | Auth | HTTPS | Why Useful | Notes |
|-----|------|-------|------------|-------|
| **Open Library** | None | ✅ | Books metadata, covers | Great IA supplement, more metadata fields |
| **Gutendex** | None | ✅ | Project Gutenberg API | Clean API for 70K+ public domain books |
| **CORE** | apiKey | ✅ | 200M+ research papers | Complement to Crossref, different coverage |
| **Google Books** | OAuth | ✅ | Comprehensive book metadata | Requires OAuth but very complete data |

### Productivity & Content

| API | Auth | HTTPS | Why Useful | Notes |
|-----|------|-------|------------|-------|
| **WakaTime** | None | ✅ | Automatic coding time tracking | Perfect for productivity tracking goals |
| **RSS feed to JSON** | None | ✅ | Convert RSS feeds to JSON | Add RSS monitoring to link collection |
| **Mercury** | apiKey | ✅ | Web parser/article extraction | Better link metadata extraction |
| **Notion** | OAuth | ✅ | Export/sync Holocene data | Popular note-taking tool integration |
| **Todoist** | OAuth | ✅ | Todo list integration | Task management sync |

### Web Scraping & Utilities

| API | Auth | HTTPS | Why Useful | Notes |
|-----|------|-------|------------|-------|
| **import.io** | apiKey | ✅ | Structured web scraping | Alternative to manual scraping |
| **iLovePDF** | apiKey | ✅ | PDF manipulation | 250 docs/month free tier |

---

## 🎯 Medium Priority - Future Enhancements

### Science & Research

| API | Auth | HTTPS | Why Useful | Notes |
|-----|------|-------|------------|-------|
| **GBIF** | apiKey | ✅ | Global biodiversity data | Earth science adjacent |
| **iNaturalist** | apiKey | ✅ | Species observations | Field research integration |
| **NOAA** | apiKey | ✅ | Weather/oceanographic data | Context for field work |
| **Wolfram Alpha** | apiKey | ✅ | Computational knowledge | Enhanced LLM reasoning |
| **ITIS** | None | ✅ | Taxonomic database | Species classifications |

### News & Information

| API | Auth | HTTPS | Why Useful | Notes |
|-----|------|-------|------------|-------|
| **NewsAPI** | apiKey | ✅ | News aggregation | Track pre-LLM vs recent news |
| **GNews** | apiKey | ✅ | Global news sources | Multiple languages |
| **Currents** | apiKey | ✅ | Real-time news | Global coverage |
| **New York Times** | apiKey | ✅ | Quality journalism | Established source |

### Development & Collaboration

| API | Auth | HTTPS | Why Useful | Notes |
|-----|------|-------|------------|-------|
| **GitLab** | OAuth | ✅ | Alternative git hosting | Supplement GitHub scanner |
| **StackExchange** | OAuth | ✅ | Programming Q&A | Track research questions |
| **IFTTT** | None | ✅ | Automation platform | Connect to other services |

---

## 💡 Nice-to-Have - Experimental

### Content Tools

| API | Auth | HTTPS | Why Useful | Notes |
|-----|------|-------|------------|-------|
| **Google Docs** | OAuth | ✅ | Export to Google Workspace | Report generation |
| **Google Sheets** | OAuth | ✅ | Data exports | Statistics and charts |
| **CloudConvert** | apiKey | ✅ | File format conversion | Multi-format support |
| **Airtable** | apiKey | ✅ | Database/spreadsheet hybrid | Alternative storage |

### Data Discovery

| API | Auth | HTTPS | Why Useful | Notes |
|-----|------|-------|------------|-------|
| **Common Crawl** | None | ✅ | Historical web content | Massive web archive |
| **World Bank** | None | ✅ | Development indicators | Research data source |
| **OpenDataSoft** | apiKey | ✅ | Various open datasets | Multiple data sources |
| **Archive.org Advanced Search** | None | ✅ | Extended IA searching | Beyond current IA integration |

### Analysis & Utilities

| API | Auth | HTTPS | Why Useful | Notes |
|-----|------|-------|------------|-------|
| **Hunter** | apiKey | ✅ | Email/contact finder | Contact management |
| **Agify.io** | None | ✅ | Estimate age from name | Author metadata |
| **Genderize.io** | None | ✅ | Estimate gender from name | Author metadata |
| **Nationalize.io** | None | ✅ | Estimate nationality | Author metadata |

---

## ❌ Not Relevant (Excluded)

- **Religious Texts** - Bible, Quran, Bhagavad Gita APIs (not research focus)
- **Entertainment** - Harry Potter API (Wizard World), poetry DBs
- **Weather Services** - Multiple weather APIs (could be useful for field work but not core)
- **IP/Network Tools** - Development utilities, not knowledge management
- **~~Pocket~~** - **SHUT DOWN** by Mozilla, no longer available

---

## 🎖️ Top 5 Recommendations for Next Integration

Based on current Holocene features and roadmap priorities:

### 1. **Open Library API** (No auth)
**Why:** Complements Internet Archive with richer book metadata
```bash
# Proposed commands
holo books search-openlibrary "geostatistics"
holo books enrich-from-openlibrary <book_id>
```

### 2. **WakaTime API** (No auth)
**Why:** Automatic coding time tracking fits productivity goals
```bash
# Proposed commands
holo usage sync-wakatime
holo usage coding-stats --this-week
```

### 3. **RSS feed to JSON** (No auth)
**Why:** Add RSS monitoring to link collection
```bash
# Proposed commands
holo links add-rss <feed_url>
holo links sync-rss
```

### 4. **Gutendex API** (No auth)
**Why:** Clean API for Project Gutenberg's 70K+ books
```bash
# Proposed commands
holo books discover-gutenberg "geology"
holo books add-gutenberg <gutenberg_id>
```

### 5. **CORE API** (apiKey required)
**Why:** 200M+ papers, different coverage than Crossref
```bash
# Proposed commands
holo papers search-core "mining engineering"
holo papers add-core <core_id>
```

---

## Implementation Notes

### Authentication Considerations
- **No Auth Required:** Open Library, Gutendex, RSS feed, WakaTime (basic)
- **API Key:** CORE, iLovePDF, CloudConvert, Hunter
- **OAuth:** Google Books, Notion, Todoist, GitHub/GitLab

### Rate Limiting
- Most free APIs have generous limits (200+ requests/sec for some)
- Crossref: Very generous, no hard limits with polite usage
- Google Books: 1000 requests/day free tier
- Open Library: No published limits, be polite

### Cost Optimization
- Prioritize free/no-auth APIs first (Open Library, Gutendex, RSS)
- Use LLM enhancement only when needed (we pay per-prompt with NanoGPT)
- Cache aggressively (HTML, API responses, metadata)

### Integration Pattern
Follow HTTPFetcher pattern established for Mercado Livre:
```python
# Example for new integration
from holocene.integrations.http_fetcher import HTTPFetcher

fetcher = HTTPFetcher.from_config(
    config=config,
    use_proxy=False,  # Most APIs don't need proxy
    integration_name='open_library'
)

# Fetch and cache
data, cached_path = fetcher.fetch(url, cache_key=book_id)
```

---

## Questions for Architecture Review

1. **API Client Abstraction:** Should we create `BaseAPIClient` class?
2. **Rate Limiting:** Global rate limiter or per-integration?
3. **Caching Strategy:** Separate cache dirs per integration?
4. **Error Handling:** Unified retry logic across integrations?
5. **OAuth Management:** How to handle token refresh for multiple services?
6. **Cost Tracking:** Track API calls per service (especially paid ones)?

---

## Related Documents

- `docs/ROADMAP.md` - Phase 4 integration plans
- `design/integrations/mercadolivre_favorites.md` - OAuth integration example
- `src/holocene/integrations/http_fetcher.py` - HTTP abstraction pattern
- `src/holocene/research/crossref_client.py` - Academic API example

---

**Last Updated:** 2025-11-19
**Next Review:** After Architecture Review Session
