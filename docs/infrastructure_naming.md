# Infrastructure Naming Schema

**Author:** Arthur
**Date:** 2025-11-19
**Inspiration:** William Gibson (Sprawl Trilogy, Bridge Trilogy, Blue Ant Trilogy)

---

## Overview

Holocene's infrastructure follows a naming convention inspired by William Gibson's AIs and characters, chosen for their thematic resonance with each device's role in the system.

---

## Device Naming

### **wmut** - Framework 13 (Intel i7, 40GB RAM)
**Full Name:** Wintermute (from *Neuromancer*, 1984)
**Role:** Personal workstation, the planner, the calculating intelligence
**Function:** Primary development machine, interactive CLI usage, local SQLite database

**Why Wintermute:**
- The calculating AI working behind the scenes
- Plans and orchestrates
- Framework 13 as the main "thinking" device
- Been using this name for personal computers for 15+ years

**Gibson Quote:**
> "Wintermute was hive mind, decision maker, effecting change in the world outside."

---

### **eunice** - Samsung S24+ (Android phone)
**Full Name:** Eunice (from *Agency*, 2020)
**Role:** Mobile companion, the interactive assistant
**Function:** Mobile quick-capture, Telegram bot client, Tasker automations, SSH access

**Why Eunice:**
- The personable, interactive AI companion
- More character than Wintermute
- Perfect for a device that's always with you
- Modern AI assistant (post-LLM era character)

**Gibson Quote:**
> "I'm a cross-platform, aggregate prosthetic agent. I was purpose-built for a specific client."

**Prescience:** Eunice as a rehash of the Dixie Flatline construct (stored expertise you can query) was written just before the modern LLM boom. Gibson called it again.

---

### **rei** - Beelink U59 (Intel N5095, 16GB RAM, Proxmox VE)
**Full Name:** Rei Toei (from *Idoru*, 1996)
**Role:** Virtualization platform, the purely virtual being
**Function:** 24/7 server running Proxmox, hosts Home Assistant, Holocene daemon, background services

**Why Rei Toei:**
- The idoru (idol) - a completely virtual celebrity
- Perfect metaphor for a virtualization platform (Proxmox runs VMs and LXC containers)
- Emphasizes the virtual nature of the infrastructure
- Pairs thematically with wmut and eunice

**Gibson Quote:**
> "She is Rei Toei. She is a personality-construct, a congeries of software agents, the creation of information-designers."

**Modern Reality:** Rei Toei seemed far-fetched in 1996. Now we have Hatsune Miku, Neuro-sama, AI VTubers, virtual influencers. Gibson was spot-on decades early.

**Services Running on rei:**
- Proxmox VE (hypervisor)
- Home Assistant (LXC container)
- Holocene daemon (LXC container, 24/7)
- PostgreSQL (future, if migrating from SQLite)
- Telegram bot (background service)
- MQTT broker (Home Assistant integration)

---

### **finn** - Mac Mini M4 (65GB RAM, future purchase)
**Full Name:** Finn (from *Count Zero*, 1986)
**Role:** Local inference server, the info broker
**Function:** Run local LLMs (privacy-sensitive content), offline inference, model hosting

**Why Finn:**
- The fence and information broker in the Sprawl
- Hub of underground information flow
- Perfect for a server hosting local models
- Central point for knowledge access

**Gibson Quote:**
> "Finn was a fence, a broker of stolen information."

**Planned Use:**
- Ollama server (local LLMs)
- Privacy-sensitive content processing
- Offline inference when needed
- Complement to NanoGPT (cloud) with local option
- Future integration with Holocene's LLM routing

**Model Hosting:**
- DeepSeek V3 quantized (if possible)
- Qwen3-Coder (local)
- Smaller models for quick tasks
- Embedding models for vault linking

---

## Service/Persona Naming

### **Laney-chan** - DeepSeek V3 Persona (via NanoGPT)
**Full Name:** Colin Laney (from *Idoru* and *All Tomorrow's Parties*, gender-bent)
**Role:** Pattern recognition, data analysis, knowledge synthesis
**Function:** Primary LLM for enrichment, categorization, summarization, connection-finding

**Why Laney (gender-bent as Laney-chan):**
- Colin Laney's gift: seeing patterns in vast streams of data
- DeepSeek V3's strength: analyzing and finding connections
- "Laney-chan" adds playful anime suffix (fits the tone)
- Avoids conflict with GitHub's Mona mascot

**Gibson Quote:**
> "Laney's node-spotter function is some sort of metaphor for whatever it is that I actually do."

**Perfect Metaphor:** When Holocene asks DeepSeek to enrich metadata, categorize content, or find connections between papers/books/links, it's literally asking Laney-chan to spot the nodes in the data stream.

**Usage in Holocene:**
```python
# holocene/llm/nanogpt_client.py
from holocene.config import load_config

config = load_config()
laney = NanoGPTClient(
    api_key=config.llm.api_key,
    model=config.llm.primary  # deepseek-ai/DeepSeek-V3.1
)

# Ask Laney-chan to find patterns
enriched = laney.simple_prompt(
    "Analyze this book and extract key themes, connections to other works, and categorization",
    temperature=0.1
)
```

**Model Routing:**
- **Laney-chan (DeepSeek V3)**: Primary analysis, enrichment, pattern recognition
- **Qwen3-Coder**: Code generation, technical tasks
- **DeepSeek-R1**: Complex reasoning, multi-step analysis
- **Hermes-4-70B**: Verification, cross-checking Laney-chan's work

---

## Infrastructure Map

```
┌─────────────────────────────────────────────────────────────┐
│                     Holocene Infrastructure                  │
└─────────────────────────────────────────────────────────────┘

┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│   wmut       │      │   eunice     │      │   rei        │
│ Framework 13 │◄────►│  S24+ Phone  │◄────►│ Proxmox VE   │
│              │ WiFi │              │ WiFi │ (24/7)       │
│ • Dev work   │      │ • Mobile     │      │ • Daemon     │
│ • CLI usage  │      │ • Telegram   │      │ • Home Asst  │
│ • SQLite DB  │      │ • Quick save │      │ • PostgreSQL │
└──────────────┘      └──────────────┘      └──────┬───────┘
                                                    │
                                                    │ (future)
                                            ┌───────▼───────┐
                                            │    finn       │
                                            │  Mac Mini M4  │
                                            │               │
                                            │ • Local LLM   │
                                            │ • Ollama      │
                                            │ • Privacy     │
                                            └───────────────┘

                      ┌──────────────────┐
                      │   Laney-chan     │
                      │  (DeepSeek V3)   │
                      │                  │
                      │ • Enrichment     │
                      │ • Analysis       │
                      │ • Pattern-finding│
                      └──────────────────┘
                      (via NanoGPT API)
```

---

## Gibson's Prescience

### Dixie Flatline (1984) → Modern LLMs
**Original Concept:** Stored consciousness/expertise you can query
**Initial Thought:** "This makes no sense technically"
**Modern Reality:** Purpose-built LLMs with stored knowledge. We can absolutely do this now.

**Quote from *Neuromancer*:**
> "Dixie was a ROM construct, a personality recording."

**Modern Equivalent:** Fine-tuned LLMs, RAG systems, knowledge bases with semantic search.

---

### Rei Toei / Idoru (1996) → Virtual Influencers
**Original Concept:** Completely virtual celebrity with agency
**Seemed Far-fetched:** Virtual being with personality and fan following
**Modern Reality:**
- Hatsune Miku (2007) - Virtual idol with massive following
- Neuro-sama (2022) - AI VTuber with real agency (LLM-powered)
- AI influencers on Instagram/TikTok
- VTubers as multi-billion dollar industry

**Quote from *Idoru*:**
> "The idoru is a personality-construct, a congeries of software agents."

**Modern Reality:** Literally describes modern AI VTubers and virtual influencers.

---

### Eunice (2020) → LLM Assistants
**Original Concept:** Aggregate prosthetic agent, helpful AI companion
**Written:** Just before GPT-3/ChatGPT era
**Modern Reality:** Eunice is basically a GPT-4 level assistant with personality

**Quote from *Agency*:**
> "I'm a military-grade AI, repurposed for consultation."

**Modern Equivalent:** Claude, ChatGPT, specialized LLMs with domain expertise.

---

### Colin Laney (1996-1999) → Data Analytics
**Original Concept:** Human with enhanced pattern recognition in data streams
**Seemed Sci-fi:** Spotting "nodal points" in vast information flow
**Modern Reality:**
- Machine learning for pattern recognition
- Anomaly detection in big data
- LLMs finding connections across documents
- Knowledge graphs and semantic analysis

**Quote from *All Tomorrow's Parties*:**
> "He could see nodal points where things could change, where history could be altered."

**Modern Equivalent:** DeepSeek V3 analyzing knowledge bases, finding connections, predicting trends.

---

## Naming Conventions in Use

### Hostnames
```bash
# wmut (Framework 13)
hostname: wmut

# rei (Proxmox server)
hostname: rei

# eunice (S24+)
device name: eunice

# finn (Mac Mini M4, future)
hostname: finn
```

### Configuration References
```yaml
# ~/.config/holocene/config.yml
infrastructure:
  primary_workstation: wmut
  mobile_device: eunice
  server: rei
  local_inference: finn  # future

llm:
  primary_persona: laney-chan
  primary_model: deepseek-ai/DeepSeek-V3.1
```

### Code Comments
```python
# Example usage in code
class SyncManager:
    """
    Manages database sync between:
    - wmut (Framework 13): Local SQLite cache
    - rei (Proxmox): Authoritative PostgreSQL database
    - eunice (S24+): Read-only mobile access
    """
```

### Documentation Style
When referring to infrastructure in docs:
- **wmut** - Framework 13 development machine
- **eunice** - S24+ mobile device
- **rei** - Proxmox 24/7 server
- **finn** - Mac Mini M4 local inference (future)
- **Laney-chan** - DeepSeek V3 persona

---

## Future Expansion

As infrastructure grows, continue Gibson naming:

**Potential Names:**
- **Case** (Neuromancer protagonist) - Could be a user-facing interface/app
- **Molly** (Street samurai) - Security/authentication layer?
- **Armitage** (Neuromancer) - Task scheduler/orchestrator?
- **Tessier-Ashpool** - Archive system?

**Principle:** Choose names that thematically match the component's function within Gibson's works.

---

## Why This Matters

1. **Consistency:** 15+ year naming convention (wmut) with thematic expansion
2. **Meaningfulness:** Each name reflects the device/service's role
3. **Fun:** Gibson references make infrastructure memorable
4. **Prescience:** Reminds us that sci-fi often becomes reality
5. **Community:** Other Gibson fans will get the references immediately

---

## Related Documents

- `docs/integration_strategy_framework.md` - Infrastructure deployment targets
- `docs/self_hosted_read_later_evaluation.md` - Services running on rei
- `design/SUMMARY.md` - LLM routing (Laney-chan usage)

---

**Last Updated:** 2025-11-19
**Status:** Active naming convention

---

## Quotes to Live By

**On Wintermute:**
> "Wintermute was hive mind, decision maker, effecting change in the world outside."
> — *Neuromancer* (1984)

**On Eunice:**
> "I'm extremely good at what I do, and I'm purposed to help you."
> — *Agency* (2020)

**On Rei Toei:**
> "She had been designed to be the object of worship for millions."
> — *Idoru* (1996)

**On Finn:**
> "You could ask Finn. Finn knew everything."
> — *Count Zero* (1986)

**On Laney:**
> "He sees nodal points. Critical. Where things can change. Where history can be altered."
> — *All Tomorrow's Parties* (1999)

---

*The future is already here — it's just not evenly distributed.*
— William Gibson
