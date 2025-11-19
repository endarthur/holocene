# Quarantine System

**For complete details, see `holocene_design.md` lines 412-435.**

---

## Purpose

Isolate external content until user approval prevents compromised content from entering agentic context.

---

## Workflow

```
External Content → Multi-Model Verification → Quarantine → User Review → Approved/Rejected
```

**Verification Pipeline:**
1. DS V3 summarizes (read-only mode, no tool access)
2. Llama 3B canary checks for injection patterns
3. Hermes 4 cross-checks summary accuracy
4. Heuristic regex scans for suspicious patterns
5. Verification score calculated
6. Stored in quarantine with metadata

**Database Schema:**
```python
{
  "id": "summary_uuid",
  "source_url": "...",
  "summary_text": "...",
  "verification_score": 0.95,
  "status": "quarantine|approved|rejected",
  "created_at": "..."
}
```

---

## User Commands

```bash
holo review-quarantine          # List all quarantined summaries
holo approve-summary <id>       # Approve for use in context
holo reject-summary <id>        # Permanently reject
```

---

**Last Updated:** 2025-11-17
**Status:** Designed, not yet implemented
