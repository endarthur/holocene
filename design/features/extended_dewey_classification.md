# Extended Dewey Classification System for Holocene

**Date:** 2025-11-18
**Status:** Approved - Ready for implementation

---

## Overview

Holocene extends the Dewey Decimal Classification (DDC) to cover all content types: books, academic papers, web links, and research reports. This provides a **unified classification system** across the entire knowledge base.

---

## Standard Dewey (Books Only)

Traditional DDC call numbers for physical books:

```
550.182 I10a  - Geostatistics book by Isaaks
551.8 G66     - Structural geology by Goodman
005.133 K78   - Python programming by Kernighan
```

**Format:** `[Dewey] [Cutter][WorkLetter]`

---

## Holocene Extended Classification

### Content Type Prefixes

| Prefix | Type | Example | Description |
|--------|------|---------|-------------|
| *(none)* | Book | `550.182 I10a` | Physical or digital books (standard Dewey) |
| **P** | Paper | `P550.182 M63` | Academic papers, journal articles |
| **W** | Web | `W550.182` | Web links, blog posts, tutorials |
| **R** | Research | `R550.182` | Personal research reports and notes |
| **N** | Note | `N550.182` | Quick capture notes, fleeting notes |

### Classification Rules

**Books (no prefix):**
- Full Dewey + Cutter + Work letter
- Example: `550.182 I10a`
- Authority: Library of Congress Dewey tables

**Papers (P prefix):**
- Full Dewey + Cutter (from first author)
- Example: `P550.182 M63` (Matheron, 1963)
- No work letter (papers are unique by DOI)

**Web links (W prefix):**
- Dewey only (no author)
- Example: `W550.182`
- Content-based classification

**Research reports (R prefix):**
- Dewey only (topic-based)
- Example: `R551.8` (structural geology research)
- May add date: `R551.8_2025-11`

**Notes (N prefix):**
- Dewey + optional date
- Example: `N550.182_2025-11-18`
- For quick captures before filing

---

## Examples by Topic

### Geostatistics (550.182)

```
550.182 I10a          📚 Book: "Geostatistics" by Isaaks & Srivastava
P550.182 M63          📄 Paper: Matheron's variogram theory (1963)
P550.182 C75          📄 Paper: Chiles on kriging methods
W550.182              🌐 Link: Online geostatistics tutorial
R550.182              📋 Report: Your research on kriging applications
N550.182_2025-11-18   📝 Note: Ideas about spatial interpolation
```

### Machine Learning (006.31)

```
006.31 G66            📚 Book: "Deep Learning" by Goodfellow
P006.31 A12           📄 Paper: AlexNet (2012)
P006.31 V37           📄 Paper: Attention is All You Need
W006.31               🌐 Link: PyTorch tutorial
R006.31               📋 Report: ML for geological prediction
```

### Structural Geology (551.8)

```
551.8 R21             📚 Book: "Structural Geology" by Ramsay
P551.8 A52            📄 Paper: Anderson's fault theory
W551.8                🌐 Link: Field guide online
R551.8_2025-11        📋 Report: Cerro Rico structural analysis
```

---

## Implementation

### Database Schema

```sql
-- Universal classification table
CREATE TABLE classifications (
    id INTEGER PRIMARY KEY,
    content_type TEXT,      -- 'book', 'paper', 'web', 'research', 'note'
    content_id INTEGER,     -- FK to books/papers/links/research tables

    dewey_class TEXT,       -- e.g., "550.182"
    cutter TEXT,            -- e.g., "I10" (if applicable)
    work_letter TEXT,       -- e.g., "a" (if applicable)

    call_number TEXT,       -- Full: "P550.182 M63"

    classified_by TEXT,     -- 'manual', 'llm', 'automatic'
    confidence REAL,        -- 0.0-1.0
    classified_at TEXT
);

-- Index for browsing
CREATE INDEX idx_call_number ON classifications(call_number);
CREATE INDEX idx_dewey_class ON classifications(dewey_class);
```

### Call Number Generation

```python
# src/holocene/core/classification.py

class CallNumber:
    """Holocene extended call number"""

    PREFIXES = {
        'book': '',
        'paper': 'P',
        'web': 'W',
        'research': 'R',
        'note': 'N'
    }

    def __init__(self, content_type, dewey_class, cutter=None, work_letter=None):
        self.type = content_type
        self.dewey = dewey_class
        self.cutter = cutter
        self.work_letter = work_letter

    @property
    def call_number(self):
        """Generate full call number"""
        prefix = self.PREFIXES[self.type]
        parts = [prefix + self.dewey]

        if self.cutter:
            cutter_part = self.cutter
            if self.work_letter:
                cutter_part += self.work_letter
            parts.append(cutter_part)

        return ' '.join(parts)

    def __str__(self):
        return self.call_number

    def __repr__(self):
        return f"CallNumber({self.call_number})"


# Usage examples
book = CallNumber('book', '550.182', 'I10', 'a')
print(book)  # "550.182 I10a"

paper = CallNumber('paper', '550.182', 'M63')
print(paper)  # "P550.182 M63"

web = CallNumber('web', '550.182')
print(web)  # "W550.182"

research = CallNumber('research', '551.8')
print(research)  # "R551.8"
```

---

## CLI Commands

### Browse by Classification

```bash
# Show all content in a Dewey class
holo catalog show 550.182
# Output:
# 550.182 - Geostatistics
#
# 📚 Books (1):
#   550.182 I10a - Introduction to Geostatistics (Isaaks, 1989)
#
# 📄 Papers (3):
#   P550.182 M63 - Variogram Theory and Application (Matheron, 1963)
#   P550.182 C75 - Geostatistics for Natural Resources (Chiles, 1999)
#   P550.182 W84 - Kriging Methods (Webster, 2007)
#
# 🌐 Web Links (2):
#   W550.182 - Online Geostatistics Tutorial
#   W550.182 - Introduction to Spatial Statistics
#
# 📋 Research (1):
#   R550.182 - Kriging Applications in Mining (2025-11-18)
```

### List by Type

```bash
# Books only
holo books list --by-dewey

# Papers only
holo papers list --by-dewey

# Everything
holo catalog list --by-dewey
```

### Search Across All Types

```bash
holo catalog search "geostatistics"
# Finds books, papers, links, reports with that topic

holo catalog search 550.182
# All items in that class
```

---

## Obsidian Vault Organization

### Directory Structure

```
~/Documents/Obsidian/Holocene/

  000 Computer Science/
    005.133/
      005.133 K78a - Python Programming.md          [Book]
      P005.133 R67 - Python Semantics Paper.md     [Paper]
      W005.133 - Python Tutorial.md                [Link]

    006.31/
      006.31 G66 - Deep Learning.md                [Book]
      P006.31 V37 - Attention Transformer.md       [Paper]
      R006.31 - ML for Geology.md                  [Research]

  500 Natural Sciences/
    550.182/
      550.182 I10a - Geostatistics.md              [Book]
      P550.182 M63 - Variogram Theory.md           [Paper]
      P550.182 C75 - Kriging Methods.md            [Paper]
      W550.182 - Geostatistics Tutorial.md         [Link]
      R550.182 - My Kriging Research.md            [Research]

    551.8/
      551.8 R21 - Structural Geology.md            [Book]
      R551.8_2025-11 - Cerro Rico Analysis.md      [Research]
```

### Note Cross-Linking

```markdown
# R550.182 - Kriging Applications in Mining

## Background

This research applies geostatistics to ore grade estimation.

## Key References

- [[550.182 I10a]] - Foundational textbook on geostatistics
- [[P550.182 M63]] - Matheron's original variogram theory
- [[P550.182 C75]] - Modern kriging methods
- [[W550.182]] - Online tutorial for implementation details

## Related Work

- [[R551.8_2025-11]] - Structural analysis of same deposit
- [[006.31 G66]] - ML methods chapter 8 (kriging as Gaussian process)
```

---

## Benefits

### 1. Unified Browsing

Browse your entire knowledge base by topic, regardless of medium:

```bash
holo catalog show 550.182
# See books, papers, web resources, your research - all together
```

### 2. Cross-References

Notes can link across content types naturally:

```markdown
See [[P550.182 M63]] for theoretical background,
then [[550.182 I10a]] chapter 4 for practical examples,
and [[W550.182]] for modern implementation.
```

### 3. Research Integration

Research mode automatically finds all relevant sources:

```bash
holo research start "geostatistics"
# Finds: books (550.182), papers (P550.182), links (W550.182)
```

### 4. Knowledge Graph

Visualize connections across content types:

```
      550.182 I10a (Book)
            ↓ cites
      P550.182 M63 (Paper)
            ↓ explained by
      W550.182 (Tutorial)
            ↓ applied in
      R550.182 (Your research)
```

### 5. Library Science Principles

Maintains centuries of library classification expertise:
- Dewey hierarchy (500s = sciences, 550s = earth sciences)
- Cutter numbers for author sorting
- Consistent, recognizable call numbers

---

## Classification Workflow

### Books (Existing)

```bash
holo books add-ia <identifier>
# → Downloads book
# → LLM classifies: "550.182"
# → Generates Cutter: "I10"
# → Work letter: "a"
# → Final: "550.182 I10a"
```

### Papers (New)

```bash
holo papers add 10.1007/BF01027661
# → Fetches metadata from Crossref
# → Author: Matheron
# → LLM classifies: "550.182" (geostatistics)
# → Cutter from author: "M63"
# → Final: "P550.182 M63"
```

### Web Links (New)

```bash
holo links add https://example.com/geostatistics-tutorial
# → Fetches content
# → LLM classifies: "550.182"
# → No author → no Cutter
# → Final: "W550.182"
```

### Research Reports (Automatic)

```bash
holo research start "structural geology"
# → LLM determines topic: 551.8
# → Generates: "R551.8"
# → Full filename: "R551.8_2025-11-18_structural_geology.md"
```

---

## Migration Plan

**Phase 1: Core implementation**
- Implement `CallNumber` class
- Add `classifications` table
- CLI commands: `holo catalog show/list/search`

**Phase 2: Content type integration**
- Books: Add call_number generation (already have Dewey)
- Papers: Integrate with Crossref import
- Links: Add classification during import
- Research: Auto-classify on creation

**Phase 3: Vault generation**
- Create Dewey-based directory structure
- Generate markdown files with call numbers in filenames
- Cross-reference wikilinks

**Phase 4: Advanced features**
- Knowledge graph by call number
- Visual browsing (browse 500s → 550s → 550.182)
- Related items across types

---

## Design Considerations

### Why Prefixes Instead of Separate Ranges?

**Alternative considered:** Use Dewey 000s for web, 900s for research, etc.

**Problems:**
- Breaks topic coherence (geostatistics split across multiple ranges)
- Confuses users familiar with Dewey
- Harder to browse by topic

**Prefix solution:**
- All geostatistics together (550.182, P550.182, W550.182, R550.182)
- Clear content type distinction
- Maintains Dewey semantics

### Why No Cutter for Web/Research?

**Web links:** Often no clear author, or multiple contributors
**Research reports:** Personal work, no need for author sorting

Cutter numbers are for shelf organization when multiple items exist at same classification. For web/research, chronological or quality-based sorting makes more sense.

---

## Future Extensions

### Subdomain Specificity

For large collections, add subdomain specificity:

```
P550.182.01 - Variogram theory
P550.182.02 - Kriging methods
P550.182.03 - Cokriging
```

### Date Suffixes

For temporal organization:

```
R551.8_2025-11-18  - Specific day
R551.8_2025-11     - Month
R551.8_2025        - Year
```

### Custom Tags

Combine with tags for additional facets:

```
P550.182 M63  #foundational #classic #must-read
W550.182      #tutorial #beginner #python
```

---

**Last Updated:** 2025-11-18
**Status:** Approved for implementation in Phase 4.3
