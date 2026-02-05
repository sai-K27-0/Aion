"""
Search Service - Performs web searches using DuckDuckGo.
"""

import logging
from typing import Any, Optional
from duckduckgo_search import DDGS

logger = logging.getLogger(__name__)

class SearchService:
    """Service for searching the web."""
    
    def __init__(self):
        self.ddgs = DDGS()
    
    async def search(self, query: str, num_results: int = 5) -> list[dict[str, Any]]:
        """
        Perform a web search for a given query.
        """
        logger.info(f"Performing web search for: {query}")
        try:
            results = []
            for r in self.ddgs.text(query, region='wt-wt', safesearch='moderate', timelimit=None):
                results.append(r)
                if len(results) >= num_results:
                    break
            return results
        except Exception as e:
            logger.error(f"Web search failed: {e}")
            return []

    async def scrape_url(self, url: str) -> Optional[str]:
        """
        Extract main text content from a URL using trafilatura.
        """
        import trafilatura
        import httpx
        
        logger.info(f"Scraping URL: {url}")
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
                response = await client.get(url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                })
                if response.status_code == 200:
                    text = trafilatura.extract(response.text)
                    if text:
                        return text[:5000] # Limit to 5000 chars for LLM context
            return None
        except Exception as e:
            logger.error(f"Scraping failed for {url}: {e}")
            return None

# Singleton (Optional, or use dependency injection)
_search_service = None

def get_search_service() -> SearchService:
    global _search_service
    if _search_service is None:
        _search_service = SearchService()
    return _search_service
