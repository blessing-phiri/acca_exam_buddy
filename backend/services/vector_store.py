"""
Vector Store Service
Handles all ChromaDB operations for the knowledge base
"""

import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions
import os
import json
import hashlib
from typing import List, Dict, Optional, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class VectorStore:
    """Wrapper for ChromaDB operations"""
    
    def __init__(self, persist_directory: str = "data/chroma_db"):
        """
        Initialize ChromaDB client with persistence
        
        Args:
            persist_directory: Where to store the vector database files
        """
        self.persist_directory = persist_directory
        
        # Ensure directory exists
        os.makedirs(persist_directory, exist_ok=True)
        
        # Initialize client with persistence
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        # Use Google's embedding function (free tier)
        self.embedding_function = embedding_functions.GooglePalmEmbeddingFunction(
            api_key=os.getenv("GOOGLE_API_KEY", ""),
            model_name="models/embedding-004"
        )
        
        # Initialize collections
        self.collections = {}
        self._init_collections()
        
        logger.info(f"VectorStore initialized at {persist_directory}")
    
    def _init_collections(self):
        """Initialize or get existing collections"""
        
        # Collection for marking schemes
        self.collections["marking_schemes"] = self._get_or_create_collection(
            "marking_schemes",
            metadata={"description": "Official ACCA marking schemes"}
        )
        
        # Collection for examiner reports
        self.collections["examiner_reports"] = self._get_or_create_collection(
            "examiner_reports",
            metadata={"description": "Examiner comments and guidance"}
        )
        
        # Collection for technical articles
        self.collections["technical_articles"] = self._get_or_create_collection(
            "technical_articles",
            metadata={"description": "ACCA technical articles and study notes"}
        )
        
        # Collection for student answers (for consistency checking)
        self.collections["student_answers"] = self._get_or_create_collection(
            "student_answers",
            metadata={"description": "Anonymized student answers for consistency"}
        )
    
    def _get_or_create_collection(self, name: str, metadata: Dict = None):
        """Get existing collection or create new one"""
        try:
            return self.client.get_collection(
                name=name,
                embedding_function=self.embedding_function
            )
        except:
            return self.client.create_collection(
                name=name,
                metadata=metadata,
                embedding_function=self.embedding_function
            )
    
    def add_document_chunks(self, 
                           collection_name: str,
                           chunks: List[str],
                           metadatas: List[Dict],
                           ids: Optional[List[str]] = None) -> List[str]:
        """
        Add document chunks to vector store
        
        Args:
            collection_name: Which collection to add to
            chunks: List of text chunks
            metadatas: List of metadata dicts for each chunk
            ids: Optional list of IDs (generated if not provided)
        
        Returns:
            List of generated IDs
        """
        if collection_name not in self.collections:
            raise ValueError(f"Collection {collection_name} not found")
        
        collection = self.collections[collection_name]
        
        # Generate IDs if not provided
        if ids is None:
            ids = [hashlib.md5(chunk.encode()).hexdigest()[:16] for chunk in chunks]
        
        # Add to collection
        collection.add(
            documents=chunks,
            metadatas=metadatas,
            ids=ids
        )
        
        logger.info(f"Added {len(chunks)} chunks to {collection_name}")
        return ids
    
    def search(self,
              collection_name: str,
              query: str,
              n_results: int = 5,
              filter_dict: Optional[Dict] = None) -> List[Dict]:
        """
        Search for similar chunks
        
        Args:
            collection_name: Which collection to search
            query: Search query text
            n_results: Number of results to return
            filter_dict: Metadata filters (e.g., {"paper": "AA"})
        
        Returns:
            List of results with documents, metadata, and distances
        """
        if collection_name not in self.collections:
            raise ValueError(f"Collection {collection_name} not found")
        
        collection = self.collections[collection_name]
        
        results = collection.query(
            query_texts=[query],
            n_results=n_results,
            where=filter_dict
        )
        
        # Format results
        formatted_results = []
        if results['documents'] and results['documents'][0]:
            for i in range(len(results['documents'][0])):
                formatted_results.append({
                    'document': results['documents'][0][i],
                    'metadata': results['metadatas'][0][i] if results['metadatas'] else {},
                    'distance': results['distances'][0][i] if results['distances'] else 0,
                    'id': results['ids'][0][i] if results['ids'] else None
                })
        
        return formatted_results
    
    def hybrid_search(self,
                     collection_name: str,
                     query: str,
                     keywords: List[str] = None,
                     n_results: int = 5) -> List[Dict]:
        """
        Hybrid search combining semantic and keyword matching
        
        Args:
            collection_name: Which collection to search
            query: Semantic search query
            keywords: Optional keywords for filtering
            n_results: Number of results to return
        """
        # First get semantic results
        semantic_results = self.search(collection_name, query, n_results * 2)
        
        if not keywords:
            return semantic_results[:n_results]
        
        # Boost results that contain keywords
        for result in semantic_results:
            keyword_score = 0
            doc_lower = result['document'].lower()
            for keyword in keywords:
                if keyword.lower() in doc_lower:
                    keyword_score += 0.1  # Boost by 0.1 per keyword
            
            # Combine scores (lower distance = better match)
            # Convert distance to similarity (1 - distance for cosine)
            similarity = 1 - result['distance']
            combined_score = similarity + keyword_score
            
            result['combined_score'] = combined_score
            result['semantic_score'] = similarity
            result['keyword_score'] = keyword_score
        
        # Sort by combined score
        semantic_results.sort(key=lambda x: x.get('combined_score', 0), reverse=True)
        
        return semantic_results[:n_results]
    
    def delete_document(self, collection_name: str, document_id: str):
        """Delete a document chunk by ID"""
        if collection_name not in self.collections:
            raise ValueError(f"Collection {collection_name} not found")
        
        self.collections[collection_name].delete(ids=[document_id])
        logger.info(f"Deleted {document_id} from {collection_name}")
    
    def get_collection_stats(self, collection_name: str) -> Dict:
        """Get statistics about a collection"""
        if collection_name not in self.collections:
            raise ValueError(f"Collection {collection_name} not found")
        
        collection = self.collections[collection_name]
        count = collection.count()
        
        return {
            "name": collection_name,
            "count": count,
            "metadata": collection.metadata
        }
    
    def reset_collection(self, collection_name: str):
        """Reset/clear a collection (careful!)"""
        if collection_name not in self.collections:
            raise ValueError(f"Collection {collection_name} not found")
        
        self.client.delete_collection(collection_name)
        self._init_collections()
        logger.warning(f"Reset collection {collection_name}")