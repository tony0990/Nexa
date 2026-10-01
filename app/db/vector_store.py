import chromadb
from chromadb.config import Settings
import os

class VectorStore:
    """
    Production Vector Store wrapper using ChromaDB.
    Handles persistence and collection management.
    """
    def __init__(self, persist_directory: str = "./chroma_db"):
        self.client = chromadb.PersistentClient(path=persist_directory)
        self.collection = self.client.get_or_create_collection(
            name="action_items",
            metadata={"hnsw:space": "cosine"}
        )

    def upsert_action(self, extraction_id: str, embedding: list, metadata: dict):
        """Adds or updates an action item in the index."""
        self.collection.upsert(
            ids=[extraction_id],
            embeddings=[embedding],
            metadatas=[metadata]
        )

    def query(self, query_embedding: list, n_results: int = 5, where: dict = None):
        """Retrieves the most similar action items."""
        return self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where
        )

    def delete(self, extraction_id: str):
        self.collection.delete(ids=[extraction_id])
