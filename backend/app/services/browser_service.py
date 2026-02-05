"""
Browser Service - Controls the web browser for the AI.
"""

import logging
import webbrowser
from typing import Optional, List
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

class BrowserService:
    """Service to handle browser-related operations."""
    
    def __init__(self):
        self.playwright = None
        self.browser = None
    
    async def open_url(self, url: str) -> bool:
        """
        Open a URL in the user's default web browser.
        Used for preparing focused work environments.
        """
        try:
            logger.info(f"Opening URL in default browser: {url}")
            webbrowser.open(url)
            return True
        except Exception as e:
            logger.error(f"Failed to open URL: {e}")
            return False

    async def prepare_workspace(self, urls: List[str]) -> bool:
        """
        Open multiple URLs to prepare a workspace.
        """
        success = True
        for url in urls:
            if not await self.open_url(url):
                success = False
        return success

    async def execute_browser_task(self, task: str) -> str:
        """
        Execute an autonomous browsing task using browser-use.
        """
        try:
            from browser_use import Agent
            from langchain_ollama import ChatOllama
            
            # Using local Ollama for the browser agent
            # We assume Ollama is running correctly as verified by AIService
            llm = ChatOllama(model="llama3") # Or another capable model
            
            agent = Agent(
                task=task,
                llm=llm,
            )
            
            result = await agent.run()
            return str(result)
        except ImportError:
             return "Error: browser-use or playwright not installed. Run 'pip install browser-use playwright' and 'playwright install'."
        except Exception as e:
            logger.error(f"Browser task failed: {e}")
            return f"Error executing browser task: {str(e)}"

# Singleton
_browser_service: Optional[BrowserService] = None

def get_browser_service() -> BrowserService:
    global _browser_service
    if _browser_service is None:
        _browser_service = BrowserService()
    return _browser_service
