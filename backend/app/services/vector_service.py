"""
Vector Service - Interface for Qdrant vector database.

This service provides:
- Storing embeddings for blocks and content
- Semantic similarity search
- Hybrid search (vector + keyword)
"""

from typing import Optional
from uuid import uuid4

from qdrant_client import QdrantClient, AsyncQdrantClient
from qdrant_client.http import models as qdrant_models
from qdrant_client.http.exceptions import UnexpectedResponse

from app.config import settings
from app.services.ai_service import get_ai_service


class VectorService:
    """
    Service for managing vector embeddings in Qdrant.
    
    Used for:
    - Semantic search across all content
    - Finding related blocks
    - AI context retrieval
    """
    
    COLLECTION_NAME = settings.qdrant_collection
    VECTOR_SIZE = 768  # nomic-embed-text dimension
    
    def __init__(self):
        self.client: Optional[AsyncQdrantClient] = None
        self.ai_service = get_ai_service()
    
    async def _get_client(self) -> AsyncQdrantClient:
        """Get or create Qdrant client."""
        if self.client is None:
            self.client = AsyncQdrantClient(
                host=settings.qdrant_host,
                port=settings.qdrant_port,
            )
        return self.client
    
    async def close(self):
        """Close the client connection."""
        if self.client:
            await self.client.close()
            self.client = None
    
    # ========================================================================
    # Setup
    # ========================================================================
    
    async def ensure_collection(self) -> bool:
        """
        Ensure the collection exists with proper configuration.
        
        Returns:
            True if collection exists or was created
        """
        client = await self._get_client()
        
        try:
            await client.get_collection(self.COLLECTION_NAME)
            return True
        except UnexpectedResponse:
            # Collection doesn't exist, create it
            await client.create_collection(
                collection_name=self.COLLECTION_NAME,
                vectors_config=qdrant_models.VectorParams(
                    size=self.VECTOR_SIZE,
                    distance=qdrant_models.Distance.COSINE,
                ),
            )
            
            # Create payload indexes for filtering
            await client.create_payload_index(
                collection_name=self.COLLECTION_NAME,
                field_name="block_id",
                field_schema=qdrant_models.PayloadSchemaType.KEYWORD,
            )
            await client.create_payload_index(
                collection_name=self.COLLECTION_NAME,
                field_name="content_type",
                field_schema=qdrant_models.PayloadSchemaType.KEYWORD,
            )
            
            return True
    
    async def is_available(self) -> bool:
        """Check if Qdrant is accessible."""
        try:
            client = await self._get_client()
            await client.get_collections()
            return True
        except Exception:
            return False
    
    # ========================================================================
    # Indexing
    # ========================================================================
    
    async def index_block(
        self,
        block_id: str,
        name: str,
        description: Optional[str] = None,
        content: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        """
        Index a block's content for semantic search.
        
        Args:
            block_id: Block ID
            name: Block name
            description: Block description
            content: Additional text content
            metadata: Extra metadata to store
            
        Returns:
            Vector point ID
        """
        # Combine text for embedding
        text_parts = [name]
        if description:
            text_parts.append(description)
        if content:
            text_parts.append(content)
        
        text = " | ".join(text_parts)
        
        # Generate embedding
        embedding = await self.ai_service.embed(text)
        
        # Create point
        point_id = str(uuid4())
        client = await self._get_client()
        
        await client.upsert(
            collection_name=self.COLLECTION_NAME,
            points=[
                qdrant_models.PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload={
                        "block_id": block_id,
                        "content_type": "block",
                        "name": name,
                        "description": description,
                        "text": text[:1000],  # Store truncated text for display
                        **(metadata or {}),
                    },
                )
            ],
        )
        
        return point_id
    
    async def index_content(
        self,
        block_id: str,
        content_id: str,
        title: Optional[str],
        content: str,
        content_type: str = "note",
    ) -> str:
        """
        Index block content (notes, documents).
        
        Args:
            block_id: Parent block ID
            content_id: Content ID
            title: Content title
            content: Text content
            content_type: Type of content (note, document, etc.)
            
        Returns:
            Vector point ID
        """
        # Combine for embedding
        text = f"{title or 'Untitled'}: {content}"
        
        # Generate embedding
        embedding = await self.ai_service.embed(text)
        
        # Create point
        point_id = str(uuid4())
        client = await self._get_client()
        
        await client.upsert(
            collection_name=self.COLLECTION_NAME,
            points=[
                qdrant_models.PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload={
                        "block_id": block_id,
                        "content_id": content_id,
                        "content_type": content_type,
                        "title": title,
                        "text": content[:1000],  # Truncate for display
                    },
                )
            ],
        )
        
        return point_id
    
    async def delete_block_vectors(self, block_id: str) -> bool:
        """
        Delete all vectors for a block.
        
        Returns:
            True if deletion completed successfully, False otherwise
        """
        client = await self._get_client()
        
        result = await client.delete(
            collection_name=self.COLLECTION_NAME,
            points_selector=qdrant_models.FilterSelector(
                filter=qdrant_models.Filter(
                    must=[
                        qdrant_models.FieldCondition(
                            key="block_id",
                            match=qdrant_models.MatchValue(value=block_id),
                        )
                    ]
                )
            ),
        )
        
        return result.status == "completed"
    
    # ========================================================================
    # Search
    # ========================================================================
    
    async def semantic_search(
        self,
        query: str,
        limit: int = 10,
        block_id: Optional[str] = None,
        content_types: Optional[list[str]] = None,
        score_threshold: float = 0.5,
    ) -> list[dict]:
        """
        Perform semantic search across indexed content.
        
        Args:
            query: Natural language search query
            limit: Maximum results
            block_id: Filter to specific block and descendants
            content_types: Filter by content type
            score_threshold: Minimum similarity score
            
        Returns:
            List of search results with score, block_id, and metadata
        """
        # Generate query embedding
        query_embedding = await self.ai_service.embed(query)
        
        # Build filters
        filter_conditions = []
        
        if block_id:
            filter_conditions.append(
                qdrant_models.FieldCondition(
                    key="block_id",
                    match=qdrant_models.MatchValue(value=block_id),
                )
            )
        
        if content_types:
            filter_conditions.append(
                qdrant_models.FieldCondition(
                    key="content_type",
                    match=qdrant_models.MatchAny(any=content_types),
                )
            )
        
        search_filter = None
        if filter_conditions:
            search_filter = qdrant_models.Filter(must=filter_conditions)
        
        # Search using query_points (modern API)
        client = await self._get_client()
        
        results = await client.query_points(
            collection_name=self.COLLECTION_NAME,
            query=query_embedding,
            limit=limit,
            query_filter=search_filter,
            score_threshold=score_threshold,
        )
        
        return [
            {
                "score": hit.score,
                "block_id": hit.payload.get("block_id"),
                "content_id": hit.payload.get("content_id"),
                "content_type": hit.payload.get("content_type"),
                "title": hit.payload.get("title") or hit.payload.get("name"),
                "text": hit.payload.get("text"),
            }
            for hit in results.points
        ]
    
    async def find_similar_blocks(
        self,
        block_id: str,
        limit: int = 5,
    ) -> list[dict]:
        """
        Find blocks similar to a given block.
        
        Args:
            block_id: Source block ID
            limit: Maximum results
            
        Returns:
            List of similar blocks with scores
        """
        client = await self._get_client()
        
        # First, find the block's vector
        search_results = await client.scroll(
            collection_name=self.COLLECTION_NAME,
            scroll_filter=qdrant_models.Filter(
                must=[
                    qdrant_models.FieldCondition(
                        key="block_id",
                        match=qdrant_models.MatchValue(value=block_id),
                    ),
                    qdrant_models.FieldCondition(
                        key="content_type",
                        match=qdrant_models.MatchValue(value="block"),
                    ),
                ]
            ),
            limit=1,
            with_vectors=True,
        )
        
        # Check if search_results has any results
        if not search_results or not search_results[0]:
            return []
        
        # Get the first result's vector
        first_result = search_results[0]
        if not first_result:
            return []
        
        source_vector = first_result[0].vector
        
        # Search for similar (excluding self)
        results = await client.query_points(
            collection_name=self.COLLECTION_NAME,
            query=source_vector,
            limit=limit,
            query_filter=qdrant_models.Filter(
                must=[
                    qdrant_models.FieldCondition(
                        key="content_type",
                        match=qdrant_models.MatchValue(value="block"),
                    ),
                ],
                must_not=[
                    qdrant_models.FieldCondition(
                        key="block_id",
                        match=qdrant_models.MatchValue(value=block_id),
                    ),
                ],
            ),
        )
        
        return [
            {
                "score": hit.score,
                "block_id": hit.payload.get("block_id"),
                "name": hit.payload.get("name"),
                "description": hit.payload.get("description"),
            }
            for hit in results.points
        ]

    async def get_semantic_graph(self, limit: int = 50) -> dict:
        """
        Export a graph of blocks and their semantic connections.
        
        Returns:
            Dictionary with nodes and links.
        """
        client = await self._get_client()
        
        # 1. Fetch all block vectors
        scroll_results = await client.scroll(
            collection_name=self.COLLECTION_NAME,
            scroll_filter=qdrant_models.Filter(
                must=[
                    qdrant_models.FieldCondition(
                        key="content_type",
                        match=qdrant_models.MatchValue(value="block"),
                    )
                ]
            ),
            limit=limit,
            with_vectors=True,
        )
        
        points = scroll_results[0]
        nodes = []
        links = []
        node_ids = set()
        
        # 2. Build nodes and compute links
        for point in points:
            bid = point.payload.get("block_id")
            if not bid: continue
            
            nodes.append({
                "id": bid,
                "name": point.payload.get("name"),
                "type": point.payload.get("content_type"),
            })
            node_ids.add(bid)
            
            # Find neighbors for this point
            neighbors = await client.query_points(
                collection_name=self.COLLECTION_NAME,
                query=point.vector,
                limit=4,  # Connect to top 3 (excluding self)
                query_filter=qdrant_models.Filter(
                    must=[
                        qdrant_models.FieldCondition(
                            key="content_type",
                            match=qdrant_models.MatchValue(value="block"),
                        )
                    ],
                    must_not=[
                        qdrant_models.FieldCondition(
                            key="block_id",
                            match=qdrant_models.MatchValue(value=bid),
                        )
                    ]
                ),
                score_threshold=0.6,
            )
            
            for neighbor in neighbors.points:
                nbid = neighbor.payload.get("block_id")
                if nbid:
                    links.append({
                        "source": bid,
                        "target": nbid,
                        "value": float(neighbor.score),
                    })
        
        return {"nodes": nodes, "links": links}


# Singleton instance
_vector_service: Optional[VectorService] = None


def get_vector_service() -> VectorService:
    """Get the vector service singleton."""
    global _vector_service
    if _vector_service is None:
        _vector_service = VectorService()
    return _vector_service
