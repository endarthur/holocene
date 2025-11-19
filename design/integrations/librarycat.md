# LibraryCat Book Collection Integration

## User's Collection

**Profile:** https://www.librarycat.org/lib/endarthur

## API Status (as of 2025-11-17)

**LibraryThing/LibraryCat Official Statement:**
> "LibraryThing does not currently offer an API for members' books. This is due to data-licensing restrictions from external providers, especially Amazon."

**Holocene's Approach:**
- ✅ Respect LibraryThing's policy - **no API workarounds**
- ✅ Use official export feature: https://www.librarything.com/export.php
- ✅ Manual import into Holocene
- ✅ Periodic refresh (when you buy enough books to need a new bookshelf 📚)

**Why no scraping/workarounds:**
- LibraryThing has legitimate legal reasons (Amazon licensing)
- They're being transparent about it
- Manual export is easy and ethical
- Book collections don't change daily anyway

## Integration Approach

### Manual Export (Simple & Ethical)

**Steps:**
1. Visit LibraryThing export page: https://www.librarything.com/export.php
2. Download collection as CSV/JSON/Tab-delimited
3. Import to Holocene: `holo books import librarycat.csv`
4. Refresh when collection grows (probably after you get that new bookshelf!)

**Advantages:**
- ✅ Simple implementation
- ✅ Respects LibraryThing's policies
- ✅ No legal/licensing concerns
- ✅ User controls data completely
- ✅ Works offline
- ✅ Book collections are relatively static anyway

**Process:**
- One-time setup: ~2 minutes
- Periodic refresh: When you add significant new books (monthly? quarterly?)
- Optional: `holo books check-update` reminder if it's been >90 days

## Database Schema

```sql
CREATE TABLE books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    author TEXT,
    subtitle TEXT,
    isbn TEXT,
    isbn13 TEXT,
    publication_year INTEGER,
    publisher TEXT,
    subjects TEXT,  -- JSON array of topics/tags
    lc_classification TEXT,  -- Library of Congress
    dewey_decimal TEXT,
    owned BOOLEAN DEFAULT 1,
    source TEXT DEFAULT 'librarycat',
    date_added TEXT,
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_books_subjects ON books(subjects);
CREATE INDEX idx_books_title ON books(title);
CREATE INDEX idx_books_author ON books(author);
```

## CLI Commands

```bash
# Import book collection
holo books import librarycat.csv
holo books import --format json librarycat.json

# Search your books
holo books search "kriging"
holo books search --author "Journel"
holo books search --subject "geostatistics"

# List books
holo books list
holo books list --subject "statistics"
holo books list --recent 10

# Book details
holo books show <book-id>

# Update notes
holo books note <book-id> "Chapter 5 has great kriging examples"

# Export
holo books export --format csv
```

## Research Integration

When running `holo next-episode "topic"`, the research mode will:

1. **Parse topic keywords**
   - "kriging variance" → ["kriging", "variance", "geostatistics"]

2. **Search book collection**
   ```sql
   SELECT * FROM books
   WHERE subjects LIKE '%kriging%'
      OR title LIKE '%kriging%'
      OR notes LIKE '%kriging%'
   ORDER BY relevance DESC
   ```

3. **Include in research report**
   ```markdown
   ## Your Physical Book Collection

   Relevant books you own:

   📚 **Geostatistical Ore Reserve Estimation**
      *Journel & Huijbregts (1978)*
      - Subject: Geostatistics, Mining
      - Your note: "Chapter 5 has great kriging examples"
      - Recommended reading: Chapter 5, pages 127-156

   📚 **Applied Geostatistics**
      *Isaaks & Srivastava (1989)*
      - Subject: Geostatistics, Statistics
      - Recommended reading: Section on kriging variance
   ```

4. **LLM enhancement**
   - DeepSeek can suggest specific chapters/sections
   - Cross-reference with online sources
   - Identify gaps in your collection

## Expected Data Format

### LibraryCat CSV Export (Typical)

```csv
Title,Author,Subtitle,ISBN,ISBN13,Year,Publisher,Subjects,Notes
"Geostatistical Ore Reserve Estimation","Journel, A.G.; Huijbregts, C.J.","","","9780123910509",1978,"Academic Press","geostatistics, mining, statistics",""
"Applied Geostatistics","Isaaks, E.H.; Srivastava, R.M.","","0195050134","9780195050134",1989,"Oxford University Press","geostatistics, statistics",""
```

### Holocene Import Parser

```python
def import_librarycat_csv(csv_path: Path) -> int:
    """Import books from LibraryCat CSV export."""
    books_imported = 0

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for row in reader:
            # Parse subjects
            subjects = [s.strip() for s in row['Subjects'].split(',')]

            # Insert into database
            db.execute("""
                INSERT INTO books (
                    title, author, subtitle, isbn, isbn13,
                    publication_year, publisher, subjects,
                    notes, source, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                row['Title'],
                row['Author'],
                row.get('Subtitle', ''),
                row.get('ISBN', ''),
                row.get('ISBN13', ''),
                int(row['Year']) if row['Year'] else None,
                row.get('Publisher', ''),
                json.dumps(subjects),
                row.get('Notes', ''),
                'librarycat',
                datetime.now().isoformat()
            ))

            books_imported += 1

    return books_imported
```

## Future Enhancements

### Book Content Indexing (Advanced)

If user has digital versions:
- PDF import of owned books
- Full-text search within books
- "Check page 127 of Journel (1978)" → Extract that exact page
- Vector embeddings for semantic search

### Recommendation Engine

Based on research topics:
- "You're researching kriging. Consider buying: [book suggestions]"
- "Similar to books you own: ..."
- Link to library catalogs, used book stores

### Reading Tracker

- Mark chapters read
- Notes per chapter
- Cross-reference with research topics
- "You researched this topic but haven't read Chapter 5 yet"

## Privacy Considerations

- ✅ All book data stored locally
- ✅ No sync to external services
- ✅ User controls import/export
- ✅ Can delete entire collection anytime

## Implementation Priority

**MVP (Phase 3.5):**
- [ ] CSV import parser
- [ ] Basic book search
- [ ] Research report integration
- [ ] Simple CLI commands

**Phase 3.6:**
- [ ] JSON import support
- [ ] Notes management
- [ ] Subject browsing
- [ ] Export functionality

**Future:**
- [ ] Investigate RSS/API options
- [ ] PDF content indexing
- [ ] Recommendation engine
- [ ] Reading tracker

## Next Steps

1. **User action needed:** Export LibraryCat collection as CSV
2. **Test data structure:** Verify CSV format matches expectations
3. **Implement parser:** CSV → SQLite
4. **Test research integration:** Run overnight research with book cross-referencing

## Example Research Output

```markdown
# Research Report: Kriging Variance Approaches

## Your Physical Book Collection

You own **2 highly relevant books** on this topic:

📚 **Geostatistical Ore Reserve Estimation** (Journel & Huijbregts, 1978)
   Recommended sections:
   - Chapter 5: Kriging (pages 127-156)
   - Chapter 7: Variance estimation (pages 201-234)

   This book is foundational and was published pre-digital era,
   making it a trusted pre-LLM reference (trust tier: 🟢 pre-llm by definition!)

📚 **Applied Geostatistics** (Isaaks & Srivastava, 1989)
   Recommended sections:
   - Chapter 12: Kriging variance
   - Chapter 15: Practical applications

💡 **Suggestion:** Start with Isaaks (more accessible) before diving into
   Journel's theoretical treatment. Both predate ChatGPT, so consider them
   trusted sources for this research.
```

---

*Note: Integration will start simple (CSV import) and can evolve based on LibraryThing API developments.*
