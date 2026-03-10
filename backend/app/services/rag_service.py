"""
RAG Service - Enhanced Retrieval Augmented Generation.

Features:
- Query expansion for better recall
- Hybrid search (vector + keyword)
- Cross-encoder reranking
- Source tracking and citations
"""

import json
import logging
import re
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass

from app.services.ai_service import AIService, get_ai_service
from app.services.vector_service import VectorService, get_vector_service
from app.services.prompt_service import get_prompt_service

logger = logging.getLogger(__name__)


@dataclass
class RetrievedDocument:
    """A document retrieved from the knowledge base."""
    id: str
    title: str
    content: str
    score: float
    source_type: str  # block, entry, fact
    metadata: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content[:500],  # Truncate for response
            "score": self.score,
            "source_type": self.source_type,
        }


@dataclass
class RAGResult:
    """Result of a RAG query."""
    answer: str
    sources: List[RetrievedDocument]
    confidence: float
    reasoning: Optional[str] = None


class RAGService:
    """Enhanced RAG service with query expansion and reranking."""
    
    def __init__(self):
        self.ai_service = get_ai_service()
        self.vector_service = get_vector_service()
        self.prompt_service = get_prompt_service()
    
    async def query(
        self,
        question: str,
        user_id: Optional[str] = None,
        max_sources: int = 5,
        rerank: bool = True,
        expand_query: bool = True,
        memory_context: str = "",
    ) -> RAGResult:
        """
        Answer a question using RAG.
        
        Args:
            question: User's question
            user_id: Optional user ID for personalization
            max_sources: Maximum sources to include
            rerank: Whether to rerank results
            expand_query: Whether to expand query
            memory_context: Additional context from memory
            
        Returns:
            RAGResult with answer, sources, and confidence
        """
        # Step 1: Expand query for better recall
        queries = [question]
        if expand_query:
            expanded = await self._expand_query(question)
            queries.extend(expanded)
        
        # Step 2: Retrieve documents from all queries
        all_docs = []
        seen_ids = set()
        
        for q in queries:
            docs = await self._retrieve(q, limit=max_sources * 2)
            for doc in docs:
                if doc.id not in seen_ids:
                    all_docs.append(doc)
                    seen_ids.add(doc.id)
        
        # Step 3: Rerank if enabled and we have enough docs
        if rerank and len(all_docs) > max_sources:
            all_docs = await self._rerank(question, all_docs, top_k=max_sources)
        else:
            # Sort by score and take top
            all_docs.sort(key=lambda x: x.score, reverse=True)
            all_docs = all_docs[:max_sources]
        
        # Step 4: Generate answer with context
        answer, confidence, reasoning = await self._generate_answer(
            question,
            all_docs,
            memory_context,
        )
        
        return RAGResult(
            answer=answer,
            sources=all_docs,
            confidence=confidence,
            reasoning=reasoning,
        )
    
    async def _expand_query(self, query: str) -> List[str]:
        """Generate alternative query phrasings."""
        try:
            prompt = self.prompt_service.render(
                "query_expansion",
                query=query,
            )
            
            response = await self.ai_service.chat(
                message=prompt,
                system_prompt="Generate query expansions. Return only JSON array.",
                temperature=0.7,
            )
            
            # Parse JSON
            response = response.strip()
            if response.startswith("```"):
                response = response.split("```")[1]
                if response.startswith("json"):
                    response = response[4:]
            
            expansions = json.loads(response)
            return expansions[:3] if isinstance(expansions, list) else []
            
        except Exception as e:
            logger.error("Query expansion failed: %s", e)
            return []
    
    async def _retrieve(
        self,
        query: str,
        limit: int = 10,
    ) -> List[RetrievedDocument]:
        """Retrieve documents using vector search."""
        if not await self.vector_service.is_available():
            return []
        
        try:
            results = await self.vector_service.semantic_search(
                query=query,
                limit=limit,
                score_threshold=0.3,
            )
            
            docs = []
            for r in results:
                doc = RetrievedDocument(
                    id=r.get("id", ""),
                    title=r.get("title", "Untitled"),
                    content=r.get("text", ""),
                    score=r.get("score", 0.0),
                    source_type=r.get("content_type", "block"),
                    metadata=r.get("metadata", {}),
                )
                docs.append(doc)
            
            return docs
            
        except Exception as e:
            logger.error("Retrieval failed: %s", e)
            return []
    
    async def _rerank(
        self,
        query: str,
        documents: List[RetrievedDocument],
        top_k: int = 5,
    ) -> List[RetrievedDocument]:
        """
        Rerank documents using the LLM as a cross-encoder.
        
        This is slower but more accurate than vector similarity alone.
        """
        if not documents:
            return []
        
        # Build reranking prompt
        docs_text = "\n".join([
            f"[{i}] {doc.title}: {doc.content[:200]}"
            for i, doc in enumerate(documents)
        ])
        
        rerank_prompt = f"""Rank these documents by relevance to the query.

Query: "{query}"

Documents:
{docs_text}

Return JSON array of document indices ordered by relevance (most relevant first):
[0, 2, 1, ...]

Only return the JSON array of indices."""
        
        try:
            response = await self.ai_service.chat(
                message=rerank_prompt,
                system_prompt="You rank documents by relevance. Return only JSON array of indices.",
                temperature=0.1,
            )
            
            # Parse indices
            response = response.strip()
            if response.startswith("```"):
                response = response.split("```")[1]
                if response.startswith("json"):
                    response = response[4:]
            
            indices = json.loads(response)
            
            # Reorder documents
            reranked = []
            for idx in indices[:top_k]:
                if 0 <= idx < len(documents):
                    doc = documents[idx]
                    # Boost score based on new rank
                    doc.score = 1.0 - (len(reranked) * 0.1)
                    reranked.append(doc)
            
            # Add any remaining docs not in ranking
            for doc in documents:
                if doc not in reranked and len(reranked) < top_k:
                    reranked.append(doc)
            
            return reranked
            
        except Exception as e:
            logger.error("Reranking failed: %s", e)
            # Fall back to original order
            return documents[:top_k]
    
    async def _generate_answer(
        self,
        question: str,
        sources: List[RetrievedDocument],
        memory_context: str = "",
    ) -> Tuple[str, float, str]:
        """Generate answer using retrieved context."""
        # Build context from sources
        if sources:
            context = "\n\n".join([
                f"[{doc.title}]\n{doc.content}"
                for doc in sources
            ])
        else:
            context = "No relevant documents found."
        
        # Generate answer
        prompt = self.prompt_service.render(
            "response_with_sources",
            context=context,
            question=question,
            memory_context=memory_context,
        )
        
        answer = await self.ai_service.chat(
            message=prompt,
            temperature=0.7,
        )
        
        # Assess confidence
        confidence, reasoning = await self._assess_confidence(
            question,
            answer,
            sources,
        )
        
        return answer, confidence, reasoning
    
    async def _assess_confidence(
        self,
        question: str,
        answer: str,
        sources: List[RetrievedDocument],
    ) -> Tuple[float, str]:
        """Assess confidence in the answer."""
        try:
            sources_desc = ", ".join([s.title for s in sources]) if sources else "none"
            
            prompt = self.prompt_service.render(
                "confidence_assessment",
                question=question,
                response=answer[:500],
                sources=sources_desc,
            )
            
            response = await self.ai_service.chat(
                message=prompt,
                system_prompt="Assess confidence. Return only JSON.",
                temperature=0.1,
            )
            
            # Parse JSON
            response = response.strip()
            if response.startswith("```"):
                response = response.split("```")[1]
                if response.startswith("json"):
                    response = response[4:]
            
            data = json.loads(response)
            return (
                float(data.get("confidence", 0.5)),
                data.get("reasoning", ""),
            )
            
        except Exception:
            # Default confidence based on source count
            if not sources:
                return 0.3, "No sources available"
            elif len(sources) >= 3:
                return 0.8, "Multiple relevant sources"
            else:
                return 0.6, "Limited sources"


# Singleton
_rag_service: Optional[RAGService] = None


def get_rag_service() -> RAGService:
    """Get the RAG service singleton."""
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService()
    return _rag_service
