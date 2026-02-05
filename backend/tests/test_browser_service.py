import asyncio
import sys
import os
import pytest

# Add app to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.browser_service import BrowserService

@pytest.mark.asyncio
async def test_browser():
    service = BrowserService()
    
    print("Testing open_url...")
    # This should open the browser on the user's machine
    success = await service.open_url("https://www.google.com")
    print(f"open_url success: {success}")
    
    print("\nTesting prepare_workspace...")
    success = await service.prepare_workspace(["https://github.com", "https://news.ycombinator.com"])
    print(f"prepare_workspace success: {success}")
    
    print("\nTesting autonomous task (Dry run/Import check)...")
    # We won't run a full task if Ollama isn't configured for it in this environment, 
    # but we can check if the imports work.
    try:
        from browser_use import Agent
        from langchain_ollama import ChatOllama
        print("Imports for browser-use and langchain-ollama successful.")
    except ImportError as e:
        print(f"Import failed: {e}")
        print("Please run: pip install browser-use playwright langchain-ollama")

if __name__ == "__main__":
    asyncio.run(test_browser())
