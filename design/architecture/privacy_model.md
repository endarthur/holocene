# Privacy Architecture

**For complete details, see `holocene_design.md` lines 144-187.**

---

## Three-Tier Privacy Model

### Tier 1: Safe for External APIs (NanoGPT)
- Generic activity descriptions ("worked on geostatistics code")
- Personal project details (full info on open-source work)
- Time patterns, categories
- Home Assistant data, Google Calendar, Mi Band
- General task management

### Tier 2: Local Only (Future M4 Mac Mini)
- Specific work context
- Internal documents (if sanitized)
- Gmail content
- Screenshot analysis (vision models)
- Detailed work context

### Tier 3: Never Logged
- Financial data, production numbers
- Unreleased exploration results
- Personnel/HR information
- Anything marked confidential
- Raw work data to external APIs

---

## Sanitization Layer

**Implementation:** `src/holocene/core/sanitizer.py`

```python
class PrivacySanitizer:
    BANNED_PATHS = ['/work/proprietary', '/Documents/Vale']
    BANNED_KEYWORDS = ['tonnage', 'carajas', 'n4e', 'sossego']
    WORK_DOMAINS = ['*.vale.com', 'mail.google.com']

    def sanitize_activity(self, activity):
        # Replace specific terms with generic ones
        # "analyzed N4E drill data" → "analyzed directional data"
        # "Carajás tonnage estimate" → "resource estimation work"

    def should_block(self, source):
        # Check against blacklists
        # Return True to block, False to allow
```

**Filtering BEFORE storage:**
- Blocked domains → activity rejected
- Blacklisted keywords → redacted to `[REDACTED]`
- Sensitive paths → activity rejected
- URLs → stripped to `[URL]`

---

**Last Updated:** 2025-11-17
**Location:** `src/holocene/core/sanitizer.py`
