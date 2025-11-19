"""Tests for EmbeddingStore."""

import pytest
from pathlib import Path

from holocene.core import embeddings

# Check if ChromaDB is available
pytestmark = pytest.mark.skipif(
    not embeddings.CHROMADB_AVAILABLE,
    reason="ChromaDB not installed (pip install chromadb sentence-transformers)",
)


@pytest.fixture
def temp_store(tmp_path):
    """Create temporary embedding store."""
    store_dir = tmp_path / "embeddings"
    return embeddings.EmbeddingStore(store_dir, model_name="all-MiniLM-L6-v2")  # Smaller model for faster tests


def test_embedding_store_initialization(tmp_path):
    """Test embedding store initialization."""
    store_dir = tmp_path / "embeddings"
    store = embeddings.EmbeddingStore(store_dir, model_name="all-MiniLM-L6-v2")

    assert store.persist_directory == store_dir
    assert store_dir.exists()
    assert store.model_name == "all-MiniLM-L6-v2"


def test_get_or_create_collection(temp_store):
    """Test creating and getting collections."""
    collection = temp_store.get_or_create_collection("test_books")
    assert collection is not None
    assert collection.name == "test_books"
    assert collection.count() == 0

    # Get same collection again
    collection2 = temp_store.get_or_create_collection("test_books")
    assert collection2.name == collection.name


def test_add_item(temp_store):
    """Test adding single item."""
    temp_store.add_item(
        collection_name="books",
        item_id="book_1",
        text="Introduction to Geostatistics by Isaaks",
        metadata={"title": "Introduction to Geostatistics", "author": "Isaaks"},
    )

    stats = temp_store.get_collection_stats("books")
    assert stats["count"] == 1


def test_add_items_batch(temp_store):
    """Test adding multiple items in batch."""
    temp_store.add_items_batch(
        collection_name="papers",
        item_ids=["paper_1", "paper_2", "paper_3"],
        texts=[
            "Machine learning for geological prediction",
            "Deep learning in mineral exploration",
            "Neural networks for spatial analysis",
        ],
        metadatas=[
            {"title": "ML Geology", "year": 2020},
            {"title": "DL Mining", "year": 2021},
            {"title": "NN Spatial", "year": 2022},
        ],
    )

    stats = temp_store.get_collection_stats("papers")
    assert stats["count"] == 3


def test_search_by_text(temp_store):
    """Test semantic search by text query."""
    # Add some test data
    temp_store.add_items_batch(
        collection_name="books",
        item_ids=["book_1", "book_2", "book_3"],
        texts=[
            "Geostatistics and kriging methods for spatial interpolation",
            "Python programming for data science and analysis",
            "Variogram modeling in geological statistics",
        ],
    )

    # Search for geostatistics-related content
    results = temp_store.search("books", "spatial statistics", n_results=2)

    assert len(results) <= 2
    assert all("id" in r for r in results)
    assert all("distance" in r for r in results)

    # First result should be geostatistics-related
    # (either book_1 or book_3, not book_2 about Python)
    top_result_id = results[0]["id"]
    assert top_result_id in ["book_1", "book_3"]


def test_find_similar(temp_store):
    """Test finding similar items."""
    # Add test data
    temp_store.add_items_batch(
        collection_name="papers",
        item_ids=["paper_1", "paper_2", "paper_3", "paper_4"],
        texts=[
            "Machine learning for geological prediction",
            "Deep learning in mineral exploration",
            "Recipe for chocolate chip cookies",
            "Convolutional neural networks for rock classification",
        ],
    )

    # Find papers similar to paper_1 (ML geology)
    similar = temp_store.find_similar("papers", "paper_1", n_results=2)

    assert len(similar) <= 2
    # Should not include paper_1 itself
    assert not any(r["id"] == "paper_1" for r in similar)

    # Should find paper_2 or paper_4 (related topics), not paper_3 (cookies)
    similar_ids = [r["id"] for r in similar]
    assert "paper_3" not in similar_ids


def test_update_item(temp_store):
    """Test updating item text and metadata."""
    # Add item
    temp_store.add_item(
        "books",
        "book_1",
        "Original text",
        metadata={"version": 1},
    )

    # Update text
    temp_store.update_item("books", "book_1", text="Updated text")

    # Search should now find it with updated text
    results = temp_store.search("books", "updated", n_results=1)
    assert len(results) > 0

    # Update metadata
    temp_store.update_item("books", "book_1", metadata={"version": 2})


def test_delete_item(temp_store):
    """Test deleting items."""
    temp_store.add_item("books", "book_1", "Test book")

    stats = temp_store.get_collection_stats("books")
    assert stats["count"] == 1

    temp_store.delete_item("books", "book_1")

    stats = temp_store.get_collection_stats("books")
    assert stats["count"] == 0


def test_search_with_metadata_filter(temp_store):
    """Test searching with metadata filters."""
    temp_store.add_items_batch(
        collection_name="papers",
        item_ids=["paper_1", "paper_2", "paper_3"],
        texts=[
            "Machine learning paper from 2020",
            "Deep learning paper from 2021",
            "Neural networks paper from 2022",
        ],
        metadatas=[
            {"year": 2020},
            {"year": 2021},
            {"year": 2022},
        ],
    )

    # Search only papers from 2021 or later
    results = temp_store.search(
        "papers",
        "machine learning",
        n_results=10,
        where={"year": {"$gte": 2021}},
    )

    # Should only get papers from 2021 and 2022
    years = [r["metadata"]["year"] for r in results if r["metadata"]]
    assert all(year >= 2021 for year in years)


def test_get_collection_stats(temp_store):
    """Test getting collection statistics."""
    temp_store.add_items_batch(
        "books",
        ["book_1", "book_2"],
        ["Text 1", "Text 2"],
    )

    stats = temp_store.get_collection_stats("books")

    assert stats["name"] == "books"
    assert stats["count"] == 2
    assert "metadata" in stats


def test_list_collections(temp_store):
    """Test listing all collections."""
    # Create multiple collections
    temp_store.add_item("books", "book_1", "Text")
    temp_store.add_item("papers", "paper_1", "Text")
    temp_store.add_item("links", "link_1", "Text")

    collections = temp_store.list_collections()

    assert "books" in collections
    assert "papers" in collections
    assert "links" in collections


def test_reset_collection(temp_store):
    """Test resetting a collection."""
    # Add items
    temp_store.add_items_batch(
        "books",
        ["book_1", "book_2", "book_3"],
        ["Text 1", "Text 2", "Text 3"],
    )

    stats = temp_store.get_collection_stats("books")
    assert stats["count"] == 3

    # Reset
    temp_store.reset_collection("books")

    stats = temp_store.get_collection_stats("books")
    assert stats["count"] == 0


def test_multiple_collections_isolated(temp_store):
    """Test that different collections are isolated."""
    temp_store.add_item("books", "item_1", "Book text")
    temp_store.add_item("papers", "item_1", "Paper text")

    books_stats = temp_store.get_collection_stats("books")
    papers_stats = temp_store.get_collection_stats("papers")

    assert books_stats["count"] == 1
    assert papers_stats["count"] == 1

    # Delete from books shouldn't affect papers
    temp_store.delete_item("books", "item_1")

    books_stats = temp_store.get_collection_stats("books")
    papers_stats = temp_store.get_collection_stats("papers")

    assert books_stats["count"] == 0
    assert papers_stats["count"] == 1


def test_empty_search(temp_store):
    """Test searching empty collection."""
    results = temp_store.search("empty_collection", "test query", n_results=10)
    assert len(results) == 0


def test_find_similar_nonexistent_item(temp_store):
    """Test finding similar items for non-existent item."""
    temp_store.add_item("books", "book_1", "Test")

    # Try to find similar to non-existent item
    results = temp_store.find_similar("books", "nonexistent_id", n_results=5)
    assert len(results) == 0


def test_persistence_across_instances(tmp_path):
    """Test that data persists across store instances."""
    store_dir = tmp_path / "embeddings"

    # Create store and add data
    store1 = embeddings.EmbeddingStore(store_dir, model_name="all-MiniLM-L6-v2")
    store1.add_item("books", "book_1", "Test book")

    stats1 = store1.get_collection_stats("books")
    assert stats1["count"] == 1

    # Create new instance with same directory
    store2 = embeddings.EmbeddingStore(store_dir, model_name="all-MiniLM-L6-v2")
    stats2 = store2.get_collection_stats("books")

    # Data should persist
    assert stats2["count"] == 1


def test_semantic_search_quality(temp_store):
    """Test that semantic search finds conceptually similar items."""
    temp_store.add_items_batch(
        collection_name="books",
        item_ids=["book_1", "book_2", "book_3", "book_4"],
        texts=[
            "Geostatistics and spatial interpolation with kriging",
            "Variogram analysis and modeling for mining",
            "Introduction to Python web development with Django",
            "Spatial statistics and geographic information systems",
        ],
    )

    # Query for geostatistics content using related terms
    results = temp_store.search("books", "kriging variogram mining geology", n_results=2)

    # Top results should be geostatistics-related (book_1, book_2, or book_4)
    # NOT the Python web development book (book_3)
    top_ids = [r["id"] for r in results]
    assert "book_3" not in top_ids


def test_result_distance_ordering(temp_store):
    """Test that results are ordered by distance (most similar first)."""
    temp_store.add_items_batch(
        "papers",
        ["paper_1", "paper_2", "paper_3"],
        [
            "Machine learning and artificial intelligence",
            "Machine learning applications",
            "Cooking recipes and meal planning",
        ],
    )

    results = temp_store.search("papers", "machine learning", n_results=3)

    # Distances should be in ascending order (closer = more similar)
    distances = [r["distance"] for r in results]
    assert distances == sorted(distances)


def test_get_embedding_store_convenience_function(tmp_path, monkeypatch):
    """Test convenience function for getting embedding store."""
    # Mock Path.home() to return tmp_path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    store = embeddings.get_embedding_store()

    assert store.persist_directory == tmp_path / ".holocene" / "embeddings"
    assert store.persist_directory.exists()


def test_chromadb_not_available():
    """Test handling when ChromaDB is not available."""
    # This test runs even if ChromaDB IS installed
    # We're just testing the error message
    import holocene.core.embeddings as emb

    if not emb.CHROMADB_AVAILABLE:
        with pytest.raises(ImportError, match="ChromaDB is required"):
            emb.EmbeddingStore("/tmp/test")
