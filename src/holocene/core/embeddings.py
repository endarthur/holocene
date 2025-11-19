"""
Vector embeddings and semantic search using ChromaDB.

Provides semantic similarity search for books, papers, and links.
Much better than keyword-based search for finding related content.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger("holocene.embeddings")

# ChromaDB is optional - only import if available
try:
    import chromadb
    from chromadb.config import Settings
    from chromadb.utils import embedding_functions

    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    logger.warning(
        "ChromaDB not available. Install with: pip install chromadb sentence-transformers"
    )


class EmbeddingStore:
    """
    Vector embedding store using ChromaDB.

    Provides semantic similarity search across books, papers, and links.
    Uses sentence-transformers model (all-mpnet-base-v2) for high-quality embeddings.
    """

    def __init__(
        self,
        persist_directory: Union[str, Path],
        model_name: str = "all-mpnet-base-v2",
    ):
        """
        Initialize embedding store.

        Args:
            persist_directory: Directory to store ChromaDB data
            model_name: Sentence transformer model to use
                       Default: all-mpnet-base-v2 (384 dims, good quality)
        """
        if not CHROMADB_AVAILABLE:
            raise ImportError(
                "ChromaDB is required for embeddings. "
                "Install with: pip install chromadb sentence-transformers"
            )

        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        self.model_name = model_name

        # Initialize ChromaDB client
        self.client = chromadb.PersistentClient(
            path=str(self.persist_directory),
            settings=Settings(anonymized_telemetry=False),
        )

        # Initialize embedding function
        self.embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=model_name
        )

        logger.info(
            f"Initialized embedding store: {persist_directory} (model: {model_name})"
        )

    def get_or_create_collection(self, name: str) -> "chromadb.Collection":
        """
        Get or create a collection.

        Args:
            name: Collection name (e.g., 'books', 'papers', 'links')

        Returns:
            ChromaDB collection
        """
        collection = self.client.get_or_create_collection(
            name=name,
            embedding_function=self.embedding_function,
            metadata={"hnsw:space": "cosine"},  # Use cosine similarity
        )

        logger.debug(f"Collection '{name}': {collection.count()} items")
        return collection

    def add_item(
        self,
        collection_name: str,
        item_id: str,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Add item to collection with embedding.

        Args:
            collection_name: Name of collection
            item_id: Unique identifier (e.g., 'book_42', 'doi_10.1234/5678')
            text: Text to embed (title, abstract, combined fields)
            metadata: Optional metadata to store with item
        """
        collection = self.get_or_create_collection(collection_name)

        # ChromaDB will automatically generate embedding from text
        collection.add(
            ids=[item_id],
            documents=[text],
            metadatas=[metadata] if metadata else None,
        )

        logger.debug(f"Added {item_id} to {collection_name}")

    def add_items_batch(
        self,
        collection_name: str,
        item_ids: List[str],
        texts: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """
        Add multiple items in batch (more efficient).

        Args:
            collection_name: Name of collection
            item_ids: List of unique identifiers
            texts: List of texts to embed
            metadatas: Optional list of metadata dicts
        """
        collection = self.get_or_create_collection(collection_name)

        collection.add(
            ids=item_ids,
            documents=texts,
            metadatas=metadatas,
        )

        logger.info(f"Added {len(item_ids)} items to {collection_name}")

    def search(
        self,
        collection_name: str,
        query_text: str,
        n_results: int = 10,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for similar items by text query.

        Args:
            collection_name: Name of collection to search
            query_text: Query text (will be embedded automatically)
            n_results: Number of results to return
            where: Optional metadata filter (e.g., {"year": {"$gte": 2020}})

        Returns:
            List of dicts with 'id', 'distance', 'metadata', 'document'
        """
        collection = self.get_or_create_collection(collection_name)

        results = collection.query(
            query_texts=[query_text],
            n_results=n_results,
            where=where,
        )

        # Reformat results for easier use
        items = []
        if results["ids"] and len(results["ids"]) > 0:
            for i in range(len(results["ids"][0])):
                items.append(
                    {
                        "id": results["ids"][0][i],
                        "distance": results["distances"][0][i],
                        "metadata": results["metadatas"][0][i] if results["metadatas"] else None,
                        "document": results["documents"][0][i] if results["documents"] else None,
                    }
                )

        logger.debug(f"Found {len(items)} results for query in {collection_name}")
        return items

    def find_similar(
        self,
        collection_name: str,
        item_id: str,
        n_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Find items similar to a specific item.

        Args:
            collection_name: Name of collection
            item_id: ID of item to find similar items for
            n_results: Number of results (including the item itself)

        Returns:
            List of similar items (excluding the query item)
        """
        collection = self.get_or_create_collection(collection_name)

        # Get the item's embedding
        item = collection.get(ids=[item_id], include=["embeddings"])

        if not item["embeddings"] or len(item["embeddings"]) == 0:
            logger.warning(f"Item {item_id} not found in {collection_name}")
            return []

        embedding = item["embeddings"][0]

        # Query using the embedding
        results = collection.query(
            query_embeddings=[embedding],
            n_results=n_results + 1,  # +1 because it will include the item itself
        )

        # Reformat and filter out the query item
        items = []
        if results["ids"] and len(results["ids"]) > 0:
            for i in range(len(results["ids"][0])):
                result_id = results["ids"][0][i]

                # Skip the query item itself
                if result_id == item_id:
                    continue

                items.append(
                    {
                        "id": result_id,
                        "distance": results["distances"][0][i],
                        "metadata": results["metadatas"][0][i] if results["metadatas"] else None,
                        "document": results["documents"][0][i] if results["documents"] else None,
                    }
                )

        logger.debug(f"Found {len(items)} similar items to {item_id}")
        return items[:n_results]  # Ensure we return exactly n_results

    def update_item(
        self,
        collection_name: str,
        item_id: str,
        text: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Update an item's text and/or metadata.

        Args:
            collection_name: Name of collection
            item_id: Item identifier
            text: New text (will re-embed if provided)
            metadata: New metadata
        """
        collection = self.get_or_create_collection(collection_name)

        update_params = {"ids": [item_id]}

        if text is not None:
            update_params["documents"] = [text]

        if metadata is not None:
            update_params["metadatas"] = [metadata]

        collection.update(**update_params)
        logger.debug(f"Updated {item_id} in {collection_name}")

    def delete_item(self, collection_name: str, item_id: str) -> None:
        """
        Delete an item from collection.

        Args:
            collection_name: Name of collection
            item_id: Item identifier
        """
        collection = self.get_or_create_collection(collection_name)
        collection.delete(ids=[item_id])
        logger.debug(f"Deleted {item_id} from {collection_name}")

    def get_collection_stats(self, collection_name: str) -> Dict[str, Any]:
        """
        Get statistics for a collection.

        Args:
            collection_name: Name of collection

        Returns:
            Dict with count and metadata
        """
        collection = self.get_or_create_collection(collection_name)

        return {
            "name": collection_name,
            "count": collection.count(),
            "metadata": collection.metadata,
        }

    def list_collections(self) -> List[str]:
        """
        List all collection names.

        Returns:
            List of collection names
        """
        collections = self.client.list_collections()
        return [c.name for c in collections]

    def reset_collection(self, collection_name: str) -> None:
        """
        Delete and recreate a collection (removes all items).

        Args:
            collection_name: Name of collection to reset
        """
        try:
            self.client.delete_collection(name=collection_name)
            logger.info(f"Reset collection: {collection_name}")
        except Exception as e:
            logger.warning(f"Could not delete collection {collection_name}: {e}")

        # Recreate empty collection
        self.get_or_create_collection(collection_name)


def get_embedding_store(
    collection_name: Optional[str] = None,
) -> EmbeddingStore:
    """
    Get or create embedding store in standard location.

    Args:
        collection_name: Optional collection name for convenience

    Returns:
        EmbeddingStore instance
    """
    store_dir = Path.home() / ".holocene" / "embeddings"
    return EmbeddingStore(store_dir)
