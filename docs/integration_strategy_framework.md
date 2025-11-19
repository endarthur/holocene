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

6. **You Have Infrastructure**
   - Already running a server
   - Have backup/monitoring setup
   - Comfortable with Docker/ops
   - Example: If you already have a home server

**⚠️ Self-Host Warning Signs:**
- Requires constant security patches
- Complex multi-service setup
- No official Docker image
- Poorly documented
- Inactive development (no updates in 1+ years)

**Real Examples from Holocene:**
- 🤔 **Wallabag** - Good self-host candidate (Docker, mature, active)
- ❌ **LLM Inference** - Bad candidate (expensive GPU, maintenance)
- 🤔 **Calibre Content Server** - Already integrated, running on demand

---

## Decision Tree

```
┌─────────────────────────────────┐
│ New Feature / Integration Need  │
└──────────────┬──────────────────┘
               │
               ▼
       ┌───────────────┐
       │ Is data        │──Yes──▶ Prefer: Build or Self-Host
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
       │ hosted exists? │──Yes──▶ Self-Host (if have infra)
       └───────┬────────┘
               │ No
               ▼
       ┌───────────────┐
       │ Build yourself │
       │ or skip feature│
       └────────────────┘
```

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

### Case Study 1: Read-It-Later (Current Decision)

**Options:**
1. Pay for hosted Wallabag (€9/year)
2. Self-host Wallabag (Docker)
3. Build Telegram bot integration
4. Use existing `holo links` + browser bookmarklet

**Analysis:**
- Data: Not super sensitive (public articles)
- Complexity: Moderate (text extraction, mobile apps)
- Existing: Have 1,145 links in `holo links` already
- Usage: Unknown - do we need offline reading?

**Recommendation:**
- **Phase 1:** Build Telegram bot (2-3 hours) - Test usage patterns
- **Phase 2:** Evaluate after 1 month - Self-host Wallabag if needed
- Rationale: Start simple, add complexity only if justified

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

## Action Items for Architecture Review

1. **Review Current Integrations**
   - Which paid services are we using? Cost? ROI?
   - Which self-built features could use paid alternatives?
   - Which could be self-hosted for better control?

2. **Establish Budget**
   - Max monthly spend for paid services
   - VPS budget for self-hosting
   - Time budget for building features

3. **Create Integration Checklist**
   - Template for evaluating new integrations
   - Force decision tree evaluation
   - Document rationale for future reference

4. **Plan for Changes**
   - When to migrate paid → self-hosted?
   - When to migrate self-built → paid?
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
