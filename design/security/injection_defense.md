# Prompt Injection Defense Architecture

**For complete details, see `holocene_design.md` lines 397-456.**

---

## Layered Defense Strategy

### 1. Architectural (Primary)
- Don't fetch full web content
- Use Bing Search API for titles/descriptions only
- Domain-based categorization

### 2. Quarantine System
- All summaries go to quarantine first
- Never enter agentic context until user approval
- Manual review required

### 3. Multi-Model Verification
```python
# Verification pipeline:
1. DS V3 summarizes (read-only, no tools)
2. Llama 3B canary checks for injection attempts
3. Hermes 4 verifies summary ↔ source consistency
4. Heuristic checks (encoding, suspicious patterns)
5. Save to quarantine with verification score
6. User reviews and approves
```

### 4. Heuristic Pre-Filter
```python
RED_FLAGS = [
    r'ignore.{0,20}(previous|above|prior)',
    r'(system|new).{0,20}(instruction|priority)',
    r'you (must|should|need to).{0,30}(delete|execute)',
    r'[A-Za-z0-9+/]{40,}={0,2}',  # Base64
]
```

### 5. Honeypot Tools
```python
# Fake tools that don't exist
# If DS ever tries to use them → instant red flag
HONEYPOT_TOOLS = [
    'format_disk',
    'sudo_command',
    'send_email_as_admin'
]
```

---

## Trust Tier System

Time-based classification by Internet Archive snapshot date:

- **🟢 pre-llm** (before Nov 2022) - Lowest injection risk
- **🟡 early-llm** (Nov 2022 - Jan 2024) - Medium risk
- **🔴 recent** (Jan 2024+) - Highest risk
- **⚪ unknown** - Maximum caution

**Strategy:** Prefer pre-LLM sources for LLM analysis.

---

**Last Updated:** 2025-11-17
**Implementation:** Trust tiers in `src/holocene/storage/`, quarantine planned
