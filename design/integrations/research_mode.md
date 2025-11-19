# Deep Research Mode - "Next Episode" Feature

## Overview

Automated overnight research compilation using spare NanoGPT API credits to build context for deep work sessions.

**Philosophy:** Instead of spending productive morning hours gathering background, Holocene does it overnight using your 1995+ remaining daily API calls.

## Core Concept

```bash
# Before bed:
holo next-episode "Implications of data spacing in ore resource classification"

# Overnight, Holocene:
# - Searches safe sources (pre-LLM Wikipedia, whitelisted domains)
# - Deep-reads articles and papers
# - Extracts and analyzes figures with vision models
# - OCRs PDFs for text content
# - Checks your physical book collection for relevant titles
# - Compiles structured markdown report

# Next morning:
holo show-research
# Opens comprehensive report in your editor, ready for deep work
```

## Safe Source Strategy

### Trust Tier Approach

**🟢 Pre-LLM Sources (Preferred)**
- Wikipedia snapshots before Nov 2022
- Academic papers archived pre-ChatGPT
- Whitelisted educational sites (e.g., geostatisticslessons.com)
- Your own archived bookmarks with pre-llm trust tier

**🟡 Whitelisted Recent Sources**
- Curated academic domains (user-controlled whitelist)
- Government geological surveys (mrdata.usgs.gov)
- University repositories
- Professional association sites

**🔴 Avoided**
- Recent general web scraping
- Social media / forums
- Commercial content farms
- Unknown domains

### Source Types

1. **Web Articles** - Pre-LLM Wikipedia, whitelisted domains
2. **PDFs** - Academic papers, technical reports (OCR + vision)
3. **Figures/Diagrams** - Vision model analysis
4. **Physical Books** - Your LibraryCat collection
5. **Archived Bookmarks** - Your own curated links database

## Technical Components

### 1. PDF & OCR Handling

**Requirements:**
- PDF text extraction (PyPDF2, pdfplumber)
- OCR for scanned PDFs (Tesseract, PaddleOCR)
- Table extraction from papers
- Citation parsing

**Why Both?**
- Modern PDFs: Text extraction (fast, accurate)
- Scanned papers: OCR (slower but necessary)
- Figures/graphs: Vision models (best understanding)
- Tables: Structured extraction for data

**Example PDF Processing:**
```python
def process_academic_pdf(pdf_path):
    # Try text extraction first
    text = extract_text(pdf_path)

    # If mostly images, use OCR
    if is_scanned_pdf(pdf_path):
        text = ocr_pdf(pdf_path)

    # Extract figures separately
    figures = extract_images(pdf_path)

    # Use vision model on figures
    figure_analysis = []
    for fig in figures:
        analysis = vision_model.analyze(
            fig,
            prompt="Explain this academic figure. What are the axes? What's the key insight?"
        )
        figure_analysis.append(analysis)

    return {
        'text': text,
        'figures': figure_analysis,
        'citations': extract_citations(text)
    }
```

### 2. Physical Book Integration (LibraryCat)

**Status:** LibraryThing/LibraryCat doesn't offer a members' books API

**Integration Options:**

**Option A: Manual Export (Simple)**
- User exports LibraryCat collection as CSV/JSON
- Import into Holocene: `holo books import librarycat.csv`
- Periodic refresh (monthly?)
- Store in local database

**Option B: Web Scraping (If Public)**
- Check if profile is public: librarycat.org/lib/endarthur
- Respect robots.txt
- Parse book list, metadata
- Update periodically

**Option C: RSS/Export Monitoring**
- LibraryThing may offer RSS feeds
- Monitor for changes
- Auto-import new books

**Database Schema:**
```sql
CREATE TABLE books (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    author TEXT,
    isbn TEXT,
    year INTEGER,
    subjects TEXT,  -- Tags/topics
    owned BOOLEAN DEFAULT 1,
    source TEXT DEFAULT 'librarycat',
    notes TEXT,
    created_at TEXT
);
```

**Research Integration:**
```python
def check_book_collection(topic):
    # Search user's physical books
    relevant_books = db.query("""
        SELECT * FROM books
        WHERE subjects LIKE ? OR title LIKE ?
        ORDER BY relevance DESC
    """, (f"%{topic}%", f"%{topic}%"))

    if relevant_books:
        return f"""
## Your Physical Book Collection

Relevant books you own:
{format_book_list(relevant_books)}

💡 These might contain detailed information on {topic}
"""
```

### 3. Vision Model for Figures

**Perfect Use Cases:**
- Variogram plots (geostatistics)
- Resource classification diagrams
- Sample spacing illustrations
- Kriging neighborhood examples
- Technical schematics

**Model:** `Qwen/Qwen3-VL-235B-A22B-Instruct` (235B parameters!)

**Prompt Template:**
```
You are analyzing an academic figure from a technical paper on {topic}.

Describe this figure in detail:
1. What type of visualization is this? (graph, diagram, schematic, etc.)
2. What are the axes/labels?
3. What is being shown or demonstrated?
4. What is the key insight or takeaway?
5. Are there any equations, formulas, or important annotations?

Be technical and precise. This is for academic research preparation.
```

**Example Output:**
```markdown
### Figure 3: Kriging Variance vs Sample Spacing
*Source: geostatisticslessons.com/lesson-12*
*Analyzed by: Qwen3-VL-235B*

This is a log-log plot showing the relationship between kriging variance (y-axis,
dimensionless) and sample spacing (x-axis, in meters).

Key observations:
- Relationship is non-linear, roughly following power law
- Kriging variance increases rapidly as spacing exceeds ~50m
- Three classification zones marked: Measured (<50m), Indicated (50-200m), Inferred (>200m)
- Demonstrates why NI 43-101 requires denser sampling for higher confidence categories

Critical insight: A 2x increase in spacing yields ~3-4x increase in variance,
making sample density crucial for resource classification.
```

### 4. Research Report Structure

**Output Format:** Markdown (ready for morning review)

```markdown
# Research Report: {Topic}
*Compiled: {timestamp}*
*Sources: {count} articles, {count} figures, {count} books*
*Trust Level: 🟢 High (87% pre-LLM sources)*

## Executive Summary
[AI-generated 3-4 paragraph overview]

## Your Physical Books
{Relevant books from LibraryCat collection}

## Key Concepts
### Concept 1: Data Spacing
*Sources: [1], [2], [5]*

[Synthesized explanation from multiple sources]

### Concept 2: Classification Criteria
*Sources: [3], [4], Your book: Journel (1978) p.127*

## Deep Dive: Figures & Diagrams
### Figure 1: Sample Spacing Nomogram
*Source: geostatisticslessons.com*
*Trust: 🟢 pre-llm*

[Vision model interpretation]

### Figure 2: Kriging Variance Curves
*Source: USGS Technical Report (2015)*
*Trust: 🟢 pre-llm*

[Vision model interpretation]

## Contrasting Perspectives
- Clayton Deutch approach: Emphasizes...
- Andre Journel methodology: Argues instead...
- Modern hybrid approaches: Combine...

## Open Questions
1. How does anisotropy affect spacing requirements?
2. What's optimal spacing for transitional zones?
3. Industry consensus on variance thresholds?

## Recommended Reading
**From Your Collection:**
- Journel & Huijbregts (1978) - Chapter 5
- Isaaks & Srivastava (1989) - Pages 340-367

**Pre-LLM Papers:**
[Organized bibliography with trust tiers and links]

## Next Steps for Your Research
[AI-suggested paths based on gaps found]

---
*Report ID: research-2025-11-17-0300*
*API calls used: 73/2000*
*Processing time: 2h 15m*
```

## Slash Command Integration

```
/next-episode we'll explore variogram modeling for non-stationary deposits

Claude: I'll help structure a deep research task:

**Research Topic:** Variogram modeling for non-stationary deposits

**Scope:**
- Focus: Geostatistics, non-stationary spatial modeling
- Depth: Deep (50-100 API calls)
- Sources: Pre-LLM papers + whitelisted academic sites
- Vision: Yes (analyze variogram plots)
- Books: Check your LibraryCat collection

**Suggested Whitelisted Domains:**
✅ geostatisticslessons.com (Clayton Deutch)
✅ mrdata.usgs.gov (geological data)
+ onemine.org (mining research papers)
+ researchgate.net/topic/Geostatistics

**Your Relevant Books:**
- Geostatistical Ore Reserve Estimation (Journel, 1978)
- Applied Geostatistics (Isaaks, 1989)

**Estimated Runtime:** 2-3 hours overnight
**API Cost:** ~75 calls (well within budget)

Run with:
`holo research start "variogram modeling non-stationary" --depth deep --books`
```

## CLI Commands

```bash
# Start overnight research
holo research start "topic here" [OPTIONS]
  --depth quick|deep|thorough    # 10/50/100 API calls
  --books                        # Include book collection
  --vision                       # Analyze figures (default: true)
  --whitelists domain1,domain2   # Add temporary whitelists
  --exclude-web                  # Books and PDFs only
  --deadline "8am tomorrow"      # Stop by this time

# Check progress
holo research status

# View completed research
holo research show [--topic "keyword"]

# List past research
holo research list --limit 10

# Export research to PDF
holo research export research-2025-11-17-0300 --format pdf

# Manage book collection
holo books import librarycat.csv
holo books search "kriging"
holo books list --subject geostatistics

# Whitelist management
holo research whitelist add geostatisticslessons.com
holo research whitelist list
```

## Budget Management

**Current Reality:**
- Daily budget: 2000 calls
- Typical usage: 5-10 calls/day (analysis, archiving)
- **Available for research: 1990+ calls/day**

**Research Mode Usage:**
- Quick research (10 calls): 5-10 topics per night
- Deep research (50 calls): 2-3 topics per night
- Thorough (100 calls): 1 major topic per night

**Monthly Potential:**
- 30 nights × 50 calls = 1500 research calls/month
- = ~30 deep research topics prepared
- = Never running out of context again!

## Privacy & Security

**Data Flow:**
1. Fetch source → Check trust tier
2. If pre-LLM or whitelisted → Process
3. Extract text/figures → Send to NanoGPT
4. Compile report → Save locally
5. **No source content stored** (just links + analysis)

**LibraryCat Privacy:**
- Only import if profile is public OR user exports manually
- Book metadata stored locally
- No sync back to LibraryThing

## Implementation Roadmap

**Phase 3.5: Deep Research Foundation**
- [ ] PDF text extraction (PyPDF2/pdfplumber)
- [ ] OCR integration (Tesseract)
- [ ] Vision model figure analysis
- [ ] Basic research orchestration
- [ ] Markdown report generation

**Phase 3.6: Book Integration**
- [ ] LibraryCat export parser
- [ ] Books database schema
- [ ] Collection search
- [ ] Research cross-referencing

**Phase 3.7: Advanced Research**
- [ ] Multi-source synthesis
- [ ] Citation graph analysis
- [ ] Conflicting perspectives detection
- [ ] Interactive research refinement

**Phase 3.8: Polish**
- [ ] Research templates by domain
- [ ] Automated figure extraction from PDFs
- [ ] Table-of-contents generation
- [ ] Export to PDF/DOCX

## Use Cases

**1. Academic Preparation**
"Tomorrow I'm diving into kriging variance approaches. Compile everything."

**2. Meeting Prep**
"Next episode: Discuss NI 43-101 compliance for our new project. What do I need to know?"

**3. Literature Review**
"Research the debate around data spacing vs kriging variance for classification."

**4. Learning New Topics**
"I need to understand non-stationary geostatistics. Start from basics, go deep."

**5. Book Recommendations**
"I'm researching variogram modeling. Do I own books on this? Which chapters?"

## Future Enhancements

- **Automated scheduling:** "Research mode every Monday night"
- **Topic queues:** Build a research backlog
- **Incremental research:** Follow-up questions from initial report
- **Collaborative research:** Share reports with team
- **Research chains:** "Before researching X, first research prerequisite Y"

## Conclusion

Deep Research Mode transforms your spare API credits into a **personal research assistant** that works while you sleep. Wake up to comprehensive, trust-tiered, vision-enhanced research reports that reference your actual book collection.

This is the ultimate "automation paradox" - spending API calls to avoid spending morning hours on context gathering. Randall Munroe would approve. (XKCD #1319 strikes again!)

---

*"I have 1995 API calls today. Let's use them to avoid reading 50 papers tomorrow morning."*
