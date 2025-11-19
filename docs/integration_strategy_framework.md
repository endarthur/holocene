# Integration Strategy Framework: Paid vs Self-Built vs Self-Hosted

**Purpose:** Decision framework for choosing integration approaches
**Status:** Draft - for Architecture Review Session
**Last Updated:** 2025-11-19

---

## Holocene's Core Principles

Before making integration decisions, align with project philosophy:

1. **Privacy-First** - Personal data stays local when possible
2. **Local-First** - Offline capability and data sovereignty
3. **Pragmatic** - Use paid services when ROI is clear
4. **Maintainable** - Avoid complexity traps and maintenance burden
5. **Human-in-the-Loop** - User control, not full automation
6. **Cost-Conscious** - Good value, not necessarily cheapest

---

## Available Infrastructure

**Home Server:**
- **Hardware:** Beelink U59 (Intel N5095 11th gen, 16GB RAM)
- **OS:** Proxmox VE (virtualization platform)
- **Current Services:** Home Assistant
- **Capabilities:** Can run Docker containers, LXC containers, or full VMs
- **Uptime:** 24/7 (home server)
- **Network:** Local network access

**Development Machine:**
- **Hardware:** Framework 13 (i7, 40GB RAM)
- **Use:** Primary development workstation
- **Capabilities:** Can run local services when docked
- **Uptime:** Work hours only

**Mobile Devices:**
- **Phone:** Samsung S24+ (high-end Android)
- **Tablets:** 2x Android tablets (specs TBD)
- **Capabilities:** Could run Termux, dedicated apps, or be repurposed

**Key Insight:** Having Proxmox server means self-hosting is **much more viable** than typical setup. Infrastructure already exists, paid, and maintained.

---

## Decision Matrix

### When to Use PAID Services

**✅ Choose Paid When:**

1. **Time-to-Value is Critical**
   - Building would take weeks/months
   - Feature is needed now, not "someday"
   - Example: NanoGPT LLM access ($8/mo) vs self-hosting models

2. **Maintenance Burden is High**
   - Service requires constant updates/monitoring
   - Security-critical infrastructure (auth, payments)
   - Example: Email delivery, SMS notifications

3. **Specialized Expertise Required**
   - Service solves hard technical problems
   - Would need to learn new domains
   - Example: Bright Data anti-bot proxies vs DIY proxy rotation

4. **Cost is Reasonable**
   - Monthly cost < 2 hours of your time
   - ROI is clear and measurable
   - Example: €9/year Wallabag hosting vs self-hosting

5. **Data is Not Sensitive**
   - Public or non-personal data
   - Can be lost/shared without concern
   - Example: Public API caching, web scraping

6. **Reliability Matters**
   - Uptime requirements are high
   - No time to debug at 3am
   - Example: Critical monitoring, backups

**Real Examples from Holocene:**
- ✅ **NanoGPT** ($8/mo) - Would cost thousands to self-host equivalent GPU
- ✅ **Bright Data** (~$0.60/400 items) - Anti-bot expertise we don't have
- ✅ **GitHub** (Free) - Could self-host Gitea, but why?

---

### When to BUILD Yourself

**✅ Choose Self-Built When:**

1. **Integration is Simple**
   - Can implement in a few hours
   - Minimal dependencies
   - Example: Telegram bot, browser bookmarklet

2. **Specific to Your Workflow**
   - No existing tool fits your needs
   - Custom logic required
   - Example: Holocene's Dewey classification with Cutter numbers

3. **Privacy is Critical**
   - Data is personal/sensitive
   - Cannot trust third parties
   - Example: Personal journal entries, financial data

4. **Learning Opportunity**
   - Skill development is a goal
   - Project is interesting technically
   - Example: Spinitex thermal printer renderer

5. **Vendor Lock-in Risk**
   - Service could disappear (RIP Pocket)
   - Pricing could change dramatically
   - Example: Core features like database, link storage

6. **High Volume / Expensive at Scale**
   - API costs grow linearly with usage
   - One-time build is cheaper long-term
   - Example: PDF text extraction vs paid OCR API at scale

**Real Examples from Holocene:**
- ✅ **Spinitex** - TeX-inspired markdown renderer (custom need)
- ✅ **Classification System** - Unique Dewey + Cutter implementation
- ✅ **HTTPFetcher** - Simple abstraction, 200 lines of code
- ✅ **Link Collection** - Core feature, must own the data

---

### When to SELF-HOST

**✅ Choose Self-Hosted When:**

1. **Data Sovereignty Required**
   - Must control where data lives
   - Compliance/privacy requirements
   - Example: Personal research database

2. **Mature Open Source Available**
   - Well-maintained project
   - Good documentation
   - Active community
   - Example: Wallabag, Calibre

3. **Simple Deployment (Docker)**
   - One-command setup
   - Minimal configuration
   - Clear upgrade path
   - Example: Most modern self-hosted apps

4. **Long-term Cost Savings**
   - Paid service costs > VPS costs
   - High usage volume
   - Example: Hosting 10 services on $5/mo VPS vs $5/mo each

5. **Customization Needed**
   - Can modify source code
   - Can add integrations
   - Example: Calibre library management

6. **You Have Infrastructure** ✅ **WE HAVE THIS!**
   - Already running Proxmox server
   - Home Assistant shows Docker/ops comfort
   - Backups presumably configured
   - 16GB RAM can handle multiple services
   - Example: Wallabag, Linkding, monitoring tools

**⚠️ Self-Host Warning Signs:**
- Requires constant security patches
- Complex multi-service setup
- No official Docker image
- Poorly documented
- Inactive development (no updates in 1+ years)

**💡 Our Proxmox Advantage:**
- **Zero additional infrastructure cost** - Server already running 24/7
- **Easy deployment** - LXC containers or Docker via Portainer
- **Resource headroom** - 16GB RAM, quad-core CPU plenty for services
- **Home Assistant integration** - Can trigger Holocene from HA automations
- **Local network access** - Fast, no internet latency
- **Full control** - Can snapshot VMs, rollback if needed

**Real Examples from Holocene:**
- ✅ **Wallabag** - STRONG self-host candidate (Docker, mature, have infrastructure)
- ❌ **LLM Inference** - Still bad (N5095 has no GPU, would be slow)
- ✅ **Calibre Content Server** - Already integrated, could run 24/7 on Proxmox
- ✅ **Monitoring/logging** - Could add Grafana, Prometheus on Proxmox
- ✅ **Backup services** - Could run automated backup jobs

---

## Decision Tree (Updated for Proxmox Setup)

```
┌─────────────────────────────────┐
│ New Feature / Integration Need  │
└──────────────┬──────────────────┘
               │
               ▼
       ┌───────────────┐
       │ Is data        │──Yes──▶ Prefer: Build or Self-Host on Proxmox
       │ sensitive?     │
       └───────┬────────┘
               │ No
               ▼
       ┌───────────────┐
       │ Simple to      │──Yes──▶ Build it (< 1 day work)
       │ build?         │
       └───────┬────────┘
               │ No
               ▼
       ┌───────────────┐
       │ Good paid      │──Yes──▶ Check cost
       │ service exists?│         │
       └───────┬────────┘         ▼
               │ No        ┌──────────────┐
               │           │ < 2hrs/mo    │──Yes──▶ Use Paid
               │           │ of your time?│
               │           └──────┬───────┘
               │                  │ No
               ▼                  │
       ┌───────────────┐         │
       │ Good self-     │◀────────┘
       │ hosted exists? │──Yes──▶ Self-Host on Proxmox ✅
       └───────┬────────┘         (We have infrastructure!)
               │ No
               ▼
       ┌───────────────┐
       │ Build yourself │
       │ or skip feature│
       └────────────────┘
```

---

## Deployment Targets: Where to Run What

### 🏠 Proxmox Server (Beelink U59 - Primary Self-Hosting)

**Best For:**
- 24/7 services (Wallabag, monitoring, backups)
- Database servers (PostgreSQL, Redis)
- Web services accessible from phone/tablet
- Home Assistant automations
- Background jobs (scheduled tasks, scrapers)

**Resource Allocation:**
- **Light Services** (< 512MB RAM): LXC containers (faster, lighter)
- **Medium Services** (512MB-2GB): Docker containers
- **Heavy Services** (2GB+): Full VMs (if needed)

**Examples for Holocene:**
- ✅ Wallabag (read-it-later) - ~256MB RAM Docker container
- ✅ Calibre Content Server - ~128MB RAM, on-demand
- ✅ PostgreSQL (if we migrate from SQLite) - ~256-512MB
- ✅ Backup automation - Cron jobs in LXC container
- ✅ Web API endpoint for mobile quick-saves
- ⚠️ LLM inference - NO (no GPU, would be slow)

**Deployment Pattern:**
```bash
# Proxmox → LXC container → Docker Compose
docker-compose up -d wallabag
docker-compose up -d calibre-web
```

---

### 💻 Framework 13 (i7, 40GB RAM - Development Machine)

**Best For:**
- Main Holocene CLI (`holo` commands)
- Active development work
- LLM-heavy operations (DeepSeek via NanoGPT)
- Large data processing (batch enrichment)
- Testing before deploying to Proxmox

**Resource Allocation:**
- Can spare 10-20GB RAM for local services
- SSD for fast database operations
- Full development environment

**Examples for Holocene:**
- ✅ Primary `holo` CLI usage
- ✅ `holo books enrich --batch` (LLM calls)
- ✅ `holo mercadolivre enrich-proxy` (Bright Data)
- ✅ Local SQLite database (fast SSD access)
- ✅ Development testing of new features
- ⚠️ 24/7 services - NO (laptop sleeps/travels)

---

### 📱 Samsung S24+ (Mobile Quick Access)

**Best For:**
- Quick capture (Telegram bot, shortcuts)
- Mobile-first interfaces
- On-the-go access to Holocene data
- Field work data collection

**Capabilities:**
- Termux for CLI access
- Tasker for automation
- Telegram for quick saves
- SSH to Proxmox server

**Examples for Holocene:**
- ✅ Telegram bot → save links/notes
- ✅ SSH to Proxmox, run `holo` commands
- ✅ Tasker automation (share → Holocene)
- ✅ Access Calibre web interface (if on Proxmox)
- ⚠️ Running `holo` locally - Possible via Termux, but slow

---

### 📋 Android Tablets (Repurpose Options)

**Option 1: Dedicated Dashboard**
- Home Assistant dashboard
- Holocene stats/visualizations (if we build web UI)
- Research dashboard (current papers, todos)
- Wall-mounted information display

**Option 2: Field Device**
- Rugged case, bring to field sites
- Offline data collection
- Geology field notes
- Photo documentation with metadata

**Option 3: Development Test Device**
- Test Holocene mobile interfaces
- Browser extension testing
- Termux development environment

**Decision:** Get tablet specs first, then decide best use

---

## Updated Cost Guidelines (With Proxmox)

### Self-Hosting Costs (Already Paid!)
- **Proxmox Server Electricity:** ~$5-10/mo (already running for HA)
- **Backup Storage:** Minimal (local drives or cloud backup)
- **Domain/SSL (if exposing):** $10-20/year (optional)

**Conclusion:** Marginal cost of adding services to Proxmox is **nearly zero**. This tips the scales heavily toward self-hosting vs paid services.

### Revised Monthly Budget
- **Paid Services:** < $50/mo total
- **Self-Hosting (Proxmox):** $0/mo additional (electricity already paid)
- **Development Time:** Willing to invest if reusable

### Updated ROI Calculation

**Before (No Server):**
- Self-host = Need to rent VPS ($5-10/mo) + setup time
- Paid service at $9/mo might be cheaper

**After (With Proxmox):**
- Self-host = Zero additional cost + setup time
- Paid service at $9/mo = $108/year for something we could host free
- **Break-even:** If setup takes < ~10 hours, self-hosting wins

---

## Cost Guidelines

### Monthly Budget Targets
- **Total Paid Services:** < $50/mo (for personal project)
- **Per-Service Max:** $10-15/mo (exceptions for high-value)
- **Self-Hosting Costs:** $5-10/mo VPS acceptable

### Value Assessment
**Good ROI Examples:**
- $8/mo saves 20+ hours of GPU management → ✅ Worth it
- $1.50/400 items avoids IP bans → ✅ Worth it
- €9/year for zero maintenance → ✅ Worth it

**Bad ROI Examples:**
- $20/mo for feature used once a month → ❌ Build it
- $50/mo when self-hosted costs $5/mo → ❌ Self-host
- $100/mo for simple API calls → ❌ Build it

---

## Maintenance Overhead Comparison

### Paid Service
- ✅ Zero maintenance
- ✅ Automatic updates
- ✅ Support available
- ❌ Monthly costs
- ❌ Vendor dependency
- ❌ Data out of your control

### Self-Hosted
- ⚠️ Docker updates (monthly)
- ⚠️ Security patches (as needed)
- ⚠️ Backups (automated but needs monitoring)
- ⚠️ Monitoring/uptime
- ✅ One-time setup effort
- ✅ Full control
- ✅ No recurring costs

### Self-Built
- ✅ Perfect fit for needs
- ✅ Full control
- ✅ No external dependencies
- ❌ Initial development time
- ⚠️ Maintenance is on you
- ⚠️ Feature additions take your time

---

## Real-World Examples

### ✅ Good Paid Service Decisions

**NanoGPT LLM Access**
- Cost: $8/mo for 2,000 prompts/day
- Alternative: Self-host GPU server ($100+/mo)
- Decision: ✅ Paid - Massive cost savings
- Rationale: Specialized infrastructure, would need expensive GPU

**Bright Data Web Unlocker**
- Cost: ~$1.50/CPM for anti-bot proxy
- Alternative: DIY proxy rotation + captcha solving
- Decision: ✅ Paid - Specialized expertise
- Rationale: Anti-bot is hard, avoid IP bans, time-to-value

**GitHub**
- Cost: Free (could pay for private repos)
- Alternative: Self-host Gitea/GitLab
- Decision: ✅ Paid/Free - Zero maintenance
- Rationale: Free tier is generous, hosting git is a pain

---

### ✅ Good Self-Built Decisions

**HTTPFetcher Abstraction**
- Effort: ~2 hours
- Alternative: Use requests library everywhere
- Decision: ✅ Build - Simple, custom logic
- Rationale: Reusable, proxy logic, caching, fits our needs

**Spinitex Thermal Renderer**
- Effort: ~8 hours
- Alternative: Generic markdown → bitmap libraries
- Decision: ✅ Build - Unique requirements
- Rationale: Thermal-specific (margins, PPI, dithering), learning opportunity

**Dewey + Cutter Classification**
- Effort: ~4 hours
- Alternative: ??? (doesn't exist for personal use)
- Decision: ✅ Build - No alternative
- Rationale: Unique need, library science application

---

### ✅ Good Self-Host Decisions

**Calibre Content Server**
- Effort: Already integrated, on-demand
- Alternative: Use Calibre cloud services ($$)
- Decision: ✅ Self-Host - Already using Calibre
- Rationale: Local ebook library, runs when needed

---

### 🤔 Questionable Decisions (Learn From)

**Apify Actors**
- Tried to use for Mercado Livre scraping
- Got complex fast (actor config, pageFunction, etc.)
- Decision: ❌ Abandoned - Pivoted to Bright Data proxy
- Lesson: Simple proxy > complex actor framework

---

## Case Studies for Architecture Review

### Case Study 1: Read-It-Later (UPDATED with Proxmox)

**Options:**
1. Pay for hosted Wallabag (€9/year)
2. Self-host Wallabag on Proxmox (Docker)
3. Build Telegram bot integration
4. Use existing `holo links` + browser bookmarklet

**Analysis:**
- Data: Not super sensitive (public articles)
- Complexity: Moderate (text extraction, mobile apps)
- Existing: Have 1,145 links in `holo links` already
- Usage: Unknown - do we need offline reading?
- **Infrastructure: Have Proxmox with 16GB RAM** ✅

**Updated Recommendation:**
- **Phase 1:** Build Telegram bot (2-3 hours) - Test usage patterns
- **Phase 2:** Self-host Wallabag on Proxmox (Docker, 1-2 hours setup)
  - Zero ongoing cost vs €9/year hosted
  - Full control over data
  - Can integrate with Home Assistant
  - Mobile apps work with local server (via Tailscale/WireGuard)
- **Phase 3:** Sync Wallabag → `holo links` periodically for research integration
- Rationale: With Proxmox, self-hosting is cheaper AND better (control, privacy)

---

### Case Study 2: LLM Access (Already Decided)

**Options:**
1. Self-host with local GPU
2. Pay for NanoGPT ($8/mo)
3. Pay for OpenAI/Anthropic (higher cost)

**Decision:** ✅ NanoGPT
- Cost: $8/mo for 2,000/day prompts
- Alternative: M4 Mac Mini local inference (future consideration)
- Rationale: Cost-effective, no GPU management, 2K/day is plenty

---

### Case Study 3: Book Metadata (Mixed Approach)

**Current:**
- ✅ Internet Archive API (free, public domain)
- ✅ Crossref API (free, academic papers)
- ✅ Google Books API (free tier, OAuth)

**Considered:**
- ❌ Paid metadata services ($$$)
- ✅ Open Library API (free, no auth)

**Decision:** Free APIs + self-built enrichment
- Rationale: Metadata is public, free APIs are good enough
- Enhancement: Use LLM to improve metadata (already paying for NanoGPT)

---

## Guidelines Summary

### Default to PAID when:
- [ ] Saves > 2 hours/month of your time
- [ ] Cost < $10-15/mo
- [ ] Data is not sensitive
- [ ] Alternative is complex to build/maintain

### Default to SELF-BUILT when:
- [ ] Can build in < 1 day
- [ ] Unique to your workflow
- [ ] Privacy/data sovereignty required
- [ ] No good paid/self-hosted option

### Default to SELF-HOSTED when:
- [ ] Mature open source exists
- [ ] Easy Docker deployment
- [ ] Data sovereignty required
- [ ] Long-term cost savings clear
- [ ] Have infrastructure already

### RED FLAGS (Avoid):
- 🚩 Requires constant manual intervention
- 🚩 No clear upgrade/backup strategy
- 🚩 Complex multi-service dependencies
- 🚩 Inactive project (no updates in 1+ years)
- 🚩 Poor documentation
- 🚩 Vendor lock-in with high switching costs

---

## How Proxmox Changes Our Strategy

### Before (No Home Server)
```
Self-Hosting = Need VPS ($5-10/mo) + maintenance
    ↓
Paid services often cheaper for simple needs
    ↓
Build only when truly custom or privacy-critical
```

### After (With Proxmox Server)
```
Self-Hosting = Zero marginal cost + one-time setup
    ↓
Self-hosting now preferred for most services
    ↓
Paid services only when significantly better or time-critical
```

### Strategic Shift

**Services to Reconsider Self-Hosting:**
1. ✅ **Wallabag** - Was maybe €9/year, now FREE on Proxmox
2. ✅ **Calibre Web** - Can run 24/7 for family access
3. ✅ **PostgreSQL** - If we migrate from SQLite, run on Proxmox
4. ✅ **Monitoring** - Grafana/Prometheus for Holocene metrics
5. ✅ **Backup automation** - Scheduled DB backups to cloud
6. ✅ **Web API** - REST API for mobile quick-saves

**Services Still Better Paid:**
1. ✅ **NanoGPT** - GPU inference not feasible on N5095
2. ✅ **Bright Data** - Anti-bot expertise we don't have
3. ✅ **GitHub** - Git hosting is a pain, free tier is generous
4. ⚠️ **Email/SMS** - If needed, complexity too high

### Home Assistant Synergy

**Automation Opportunities:**
- HA automation → triggers `holo` commands on Proxmox
- Daily backups scheduled via HA
- Telegram bot hosted on Proxmox, controlled via HA
- Presence detection → pause background jobs when away
- Morning routine → print thermal summary of today's tasks

**Example:**
```yaml
# Home Assistant automation
- alias: "Morning Holocene Summary"
  trigger:
    - platform: time
      at: "07:00:00"
  action:
    - service: shell_command.holo_print_summary
      # SSH to Proxmox, run: holo print summary
```

---

## Action Items for Architecture Review

1. **Review Current Integrations**
   - Which paid services are we using? Cost? ROI?
   - Which self-built features could be Proxmox-hosted?
   - Which should stay on Framework 13 vs move to Proxmox?

2. **Establish Budget**
   - Max monthly spend for paid services: < $50/mo
   - Self-hosting budget: $0/mo (Proxmox already running)
   - Time budget for building features: ~5-10 hrs/mo

3. **Create Integration Checklist**
   - Template for evaluating new integrations
   - Force decision tree evaluation
   - Document rationale for future reference
   - Add "Can this run on Proxmox?" question

4. **Plan Proxmox Deployments**
   - Which services to deploy first? (Wallabag, Calibre Web)
   - LXC vs Docker for each service?
   - Backup strategy for Proxmox containers
   - Network access strategy (local only vs VPN vs public)

5. **Plan for Changes**
   - When to migrate paid → Proxmox-hosted?
   - When to migrate Framework 13 → Proxmox (24/7 services)?
   - When to keep paid despite Proxmox (NanoGPT, Bright Data)?
   - Exit strategies for vendor lock-in

---

## Related Documents

- `docs/public_apis_evaluation.md` - Available APIs for integration
- `docs/self_hosted_read_later_evaluation.md` - Read-it-later case study
- `docs/ROADMAP.md` - Architecture review planning
- `design/architecture/integration_guidelines.md` - (TBD) Technical patterns

---

**Last Updated:** 2025-11-19
**Status:** Draft - Pending Architecture Review
**Next Review:** During Architecture Review Session
