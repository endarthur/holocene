# Automation Boundaries

**For complete details, see `holocene_design.md` lines 458-508.**

---

## Allowed Automation

### IFTTT-Style Rules
User-created or Holocene-suggested, always user-approved:

```python
Rule(
    trigger="coding_session > 2_hours",
    condition="no_break_taken",
    action="miband.vibrate('take a break')"
)

Rule(
    trigger="commit_to_repo('GGR')",
    action="log_activity(tags=['geostatistics', 'python'])"
)
```

### Script Generation
- Holocene can generate automation scripts
- User reviews before first execution
- Can mark as "trusted" for future auto-run
- Comprehensive audit logging

### Allowed Operations
```python
ALLOWED_OPERATIONS = [
    'home_assistant.call_service',
    'calendar.create_event',
    'miband.vibrate',
    'journel.log_entry',
]
```

---

## Forbidden Automation

**NOT Allowed:**
- Autonomous code execution without approval
- Self-modification of rules/behavior
- Spawning persistent agents
- Recursive agent creation
- File system access outside designated zones
- POST/PUT/DELETE requests to external APIs

---

## Sandbox Constraints

```python
class SafeExecutionEnvironment:
    ALLOWED_PATHS = [
        '/home/holocene/workspace',
        '/tmp/holocene'
    ]

    # No network by default
    # No subprocess/eval/exec
    # Resource limits: CPU, memory, time
```

---

**Last Updated:** 2025-11-17
**Philosophy:** Tool that assists, not agent that acts
