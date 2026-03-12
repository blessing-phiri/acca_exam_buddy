"""
Vector store service.
Handles ChromaDB operations for ingestion and retrieval.
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions

logger = logging.getLogger(__name__)


class HashEmbeddingFunction:
    """
    Local deterministic embedding fallback.

    This is not semantically rich like transformer embeddings, but it is stable,
    fast, and avoids external dependencies so ingestion/search remain operational.
    """

    def __init__(self, dimension: int = 256) -> None:
        self.dimension = dimension

    def __call__(self, input: List[str]) -> List[List[float]]:
        vectors: List[List[float]] = []
        for text in input:
            vec = [0.0] * self.dimension
            for index, byte in enumerate(text.encode("utf-8", errors="ignore")):
                vec[index % self.dimension] += byte / 255.0

            norm = math.sqrt(sum(value * value for value in vec))
            if norm > 0:
                vec = [value / norm for value in vec]
            vectors.append(vec)
        return vectors


class VectorStore:
    """Wrapper around ChromaDB operations."""

    def __init__(self, persist_directory: str = "data/chroma_db") -> None:
        self.persist_directory = persist_directory
        os.makedirs(self.persist_directory, exist_ok=True)

        self.client = chromadb.PersistentClient(
            path=self.persist_directory,
            settings=Settings(anonymized_telemetry=False, allow_reset=True),
        )

        self.embedding_function = self._build_embedding_function()
        self.embedding_provider = type(self.embedding_function).__name__

        self.collections: Dict[str, Any] = {}
        self._init_collections()

        logger.info("VectorStore initialized at %s using %s", self.persist_directory, self.embedding_provider)

    def _build_embedding_function(self):
        provider = os.getenv("EMBEDDING_PROVIDER", "auto").strip().lower()

        if provider in {"auto", "openai"}:
            openai_key = os.getenv("OPENAI_API_KEY", "").strip()
            if openai_key:
                model_name = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
                try:
                    return embedding_functions.OpenAIEmbeddingFunction(api_key=openai_key, model_name=model_name)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("OpenAI embedding init failed: %s", exc)

        if provider == "google":
            google_key = os.getenv("GOOGLE_API_KEY", "").strip() or os.getenv("GEMINI_API_KEY", "").strip()
            if not google_key:
                logger.warning("EMBEDDING_PROVIDER=google but no GOOGLE_API_KEY/GEMINI_API_KEY found")
            else:
                os.environ.setdefault("GEMINI_API_KEY", google_key)
                for class_name, kwargs in [
                    ("GoogleGenaiEmbeddingFunction", {"model_name": "gemini-embedding-001"}),
                    (
                        "GoogleGenerativeAiEmbeddingFunction",
                        {"api_key": google_key, "model_name": "gemini-embedding-001"},
                    ),
                    ("GooglePalmEmbeddingFunction", {"api_key": google_key, "model_name": "models/embedding-004"}),
                ]:
                    embedding_class = getattr(embedding_functions, class_name, None)
                    if embedding_class is None:
                        continue
                    try:
                        return embedding_class(**kwargs)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("Google embedding init failed via %s: %s", class_name, exc)

        if provider == "default":
            try:
                default_func = embedding_functions.DefaultEmbeddingFunction()
                _ = default_func(["embedding-healthcheck"])
                return default_func
            except Exception as exc:  # noqa: BLE001
                logger.warning("Default embedding init failed, using local hash fallback: %s", exc)

        return HashEmbeddingFunction()

    def _init_collections(self) -> None:
        self.collections["marking_schemes"] = self._get_or_create_collection(
            "marking_schemes", metadata={"description": "Official ACCA marking schemes"}
        )
        self.collections["examiner_reports"] = self._get_or_create_collection(
            "examiner_reports", metadata={"description": "Examiner comments and guidance"}
        )
        self.collections["technical_articles"] = self._get_or_create_collection(
            "technical_articles", metadata={"description": "ACCA technical articles and study notes"}
        )
        self.collections["student_answers"] = self._get_or_create_collection(
            "student_answers", metadata={"description": "Anonymized student answers for consistency"}
        )

    def _get_or_create_collection(self, name: str, metadata: Optional[Dict] = None):
        try:
            return self.client.get_collection(name=name)
        except Exception:  # noqa: BLE001
            try:
                return self.client.create_collection(name=name, metadata=metadata or {})
            except Exception:  # noqa: BLE001
                return self.client.get_collection(name=name)

    def add_document_chunks(
        self,
        collection_name: str,
        chunks: List[str],
        metadatas: List[Dict],
        ids: Optional[List[str]] = None,
    ) -> List[str]:
        if collection_name not in self.collections:
            raise ValueError(f"Collection {collection_name} not found")
        if len(chunks) != len(metadatas):
            raise ValueError("chunks and metadatas must have the same length")
        if not chunks:
            return []

        collection = self.collections[collection_name]
        safe_metadatas = [self._sanitize_metadata(metadata) for metadata in metadatas]

        if ids is None:
            generated_ids: List[str] = []
            for index, chunk in enumerate(chunks):
                source_hint = safe_metadatas[index].get("source_file") or safe_metadatas[index].get("source_url") or "source"
                raw = f"{collection_name}:{source_hint}:{index}:{hashlib.sha1(chunk.encode('utf-8')).hexdigest()}"
                generated_ids.append(hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24])
            ids = generated_ids

        embeddings = self.embedding_function(chunks)
        collection.upsert(documents=chunks, embeddings=embeddings, metadatas=safe_metadatas, ids=ids)
        logger.info("Upserted %d chunks into %s", len(chunks), collection_name)
        return ids

    def search(
        self,
        collection_name: str,
        query: str,
        n_results: int = 5,
        filter_dict: Optional[Dict] = None,
    ) -> List[Dict]:
        if collection_name not in self.collections:
            raise ValueError(f"Collection {collection_name} not found")

        collection = self.collections[collection_name]
        query_embedding = self.embedding_function([query])[0]
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=filter_dict,
        )

        documents = results.get("documents") or [[]]
        metadatas = results.get("metadatas") or [[]]
        distances = results.get("distances") or [[]]
        ids = results.get("ids") or [[]]

        formatted_results: List[Dict] = []
        for index, document in enumerate(documents[0] if documents else []):
            formatted_results.append(
                {
                    "document": document,
                    "metadata": metadatas[0][index] if metadatas and metadatas[0] else {},
                    "distance": distances[0][index] if distances and distances[0] else 0.0,
                    "id": ids[0][index] if ids and ids[0] else None,
                }
            )
        return formatted_results

    def hybrid_search(
        self,
        collection_name: str,
        query: str,
        keywords: Optional[List[str]] = None,
        n_results: int = 5,
        filter_dict: Optional[Dict] = None,
    ) -> List[Dict]:
        semantic_results = self.search(collection_name, query, n_results * 2, filter_dict=filter_dict)
        if not keywords:
            return semantic_results[:n_results]

        for result in semantic_results:
            keyword_score = 0.0
            document_lower = result["document"].lower()
            for keyword in keywords:
                if keyword.lower() in document_lower:
                    keyword_score += 0.1

            similarity = 1 - float(result.get("distance", 0.0))
            result["semantic_score"] = similarity
            result["keyword_score"] = keyword_score
            result["combined_score"] = similarity + keyword_score

        semantic_results.sort(key=lambda item: item.get("combined_score", 0.0), reverse=True)
        return semantic_results[:n_results]

    def get_documents(
        self,
        collection_name: str,
        document_ids: Optional[List[str]] = None,
        filter_dict: Optional[Dict] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict:
        if collection_name not in self.collections:
            raise ValueError(f"Collection {collection_name} not found")

        collection = self.collections[collection_name]
        return collection.get(ids=document_ids, where=filter_dict, limit=limit, offset=offset)

    def delete_document(self, collection_name: str, document_id: str) -> None:
        self.delete_documents(collection_name, [document_id])

    def delete_documents(self, collection_name: str, document_ids: List[str]) -> int:
        if collection_name not in self.collections:
            raise ValueError(f"Collection {collection_name} not found")
        if not document_ids:
            return 0

        self.collections[collection_name].delete(ids=document_ids)
        logger.info("Deleted %d chunks from %s", len(document_ids), collection_name)
        return len(document_ids)

    def get_collection_stats(self, collection_name: str) -> Dict:
        if collection_name not in self.collections:
            raise ValueError(f"Collection {collection_name} not found")

        collection = self.collections[collection_name]
        return {
            "name": collection_name,
            "count": collection.count(),
            "metadata": collection.metadata,
            "embedding_provider": self.embedding_provider,
        }

    def reset_collection(self, collection_name: str) -> None:
        if collection_name not in self.collections:
            raise ValueError(f"Collection {collection_name} not found")

        self.client.delete_collection(collection_name)
        self._init_collections()
        logger.warning("Reset collection %s", collection_name)

    def _sanitize_metadata(self, metadata: Dict) -> Dict:
        """Ensure metadata values are primitives accepted by Chroma."""
        sanitized: Dict = {}
        for key, value in metadata.items():
            if value is None:
                continue
            if isinstance(value, (str, int, float, bool)):
                sanitized[key] = value
            else:
                sanitized[key] = str(value)
        return sanitized
