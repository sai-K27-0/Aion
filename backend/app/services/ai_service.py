"""
AI Service - Interface for local and cloud LLM capabilities.

This service provides:
- Chat completion via Ollama (default), OpenAI, or Anthropic
- Text embeddings for semantic search
- Vision/screen understanding via LLaVA
- Context-aware assistance based on screen content
"""

import base64
from pathlib import Path
from typing import Optional, AsyncGenerator

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings

# Provider preference when multiple keys exist
def _chat_provider() -> str:
    """Return which provider to use for chat: openai | anthropic | ollama."""
    p = (settings.ai_provider or "ollama").lower()
    if p == "openai" and settings.openai_api_key:
        return "openai"
    if p == "anthropic" and settings.anthropic_api_key:
        return "anthropic"
    return "ollama"


class AIService:
    """
    Service for interacting with local AI models via Ollama.
    
    Capabilities:
    - Chat: Natural language conversation
    - Embeddings: Vector representations for semantic search
    - Vision: Understand screenshots and images
    """
    
    def __init__(self):
        self.base_url = settings.ollama_url
        self.model = settings.ollama_model
        self.embedding_model = settings.ollama_embedding_model
        self.vision_model = "llava"  # For screen understanding
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=120.0,  # LLM responses can be slow
            )
        return self._client
    
    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
    
    # ========================================================================
    # Health Check
    # ========================================================================
    
    async def is_available(self) -> bool:
        """Check if the configured AI provider (Ollama, OpenAI, or Anthropic) is available."""
        provider = _chat_provider()
        if provider == "openai":
            return bool(settings.openai_api_key)
        if provider == "anthropic":
            return bool(settings.anthropic_api_key)
        try:
            client = await self._get_client()
            response = await client.get("/api/tags")
            return response.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> list[str]:
        """List available models for the current provider."""
        provider = _chat_provider()
        if provider == "openai":
            return ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"]
        if provider == "anthropic":
            return ["claude-sonnet-4-20250514", "claude-3-5-sonnet-20241022", "claude-3-haiku-20240307"]
        try:
            client = await self._get_client()
            response = await client.get("/api/tags")
            if response.status_code == 200:
                data = response.json()
                return [model["name"] for model in data.get("models", [])]
            return []
        except Exception:
            return []
    
    # ========================================================================
    # Chat Completion
    # ========================================================================
    
    async def _get_system_context(self, system_prompt: Optional[str] = None) -> str:
        """Helper to build a context-aware system prompt with accuracy guidelines."""
        from datetime import datetime
        from app.services.persona_service import get_persona_service
        # Add dynamic context
        # "Spoken Time" for natural voice (e.g. "6:42 PM, Monday")
        now = datetime.now()
        spoken_time = now.strftime("%I:%M %p, %A")
        iso_time = now.isoformat(timespec='seconds')
        
        base_context = f"""
        Current Date/Time: {iso_time}
        (Speak as: "{spoken_time}")
        
        **VOICE MODE INSTRUCTIONS**:
        - You are talking to the user via Voice.
        - Be EXTREMELY concise. Avoid fluff.
        - Speak naturally. Say "It's 6:40" instead of "The time is 18:40:00".
        - Do not read out lists unless asked. Summarize.
        - Do not output markdown or code blocks if in voice mode.
        """
        
        # Inject user persona rules
        persona_rules = ""
        from app.services.persona_service import get_persona_service
        try:
            persona = get_persona_service()
            persona_rules = await persona.get_system_prompt_addition()
        except Exception:
            pass
            
        full_context = base_context + persona_rules
        
        if system_prompt:
            return full_context + "\n\n" + system_prompt
        return full_context + "\n\nYou are Aion, an intelligent voice assistant."

    async def get_enriched_context(self, query: str) -> str:
        """
        Perform RAG (Retrieval-Augmented Generation) to get relevant block data.
        """
        from app.services.vector_service import get_vector_service
        vector_service = get_vector_service()
        if not await vector_service.is_available():
            return ""

        # Search for top 5 relevant snippets
        results = await vector_service.semantic_search(query, limit=5)
        if not results:
            return ""

        context_parts = ["--- RELEVANT NEURAL MEMORY ---"]
        for res in results:
            context_parts.append(f"Block: {res['title']} (Type: {res['content_type']})\nContent: {res['text']}\n")
        
        return "\n".join(context_parts) + "\n"

    async def _chat_via_ollama(
        self,
        messages: list[dict],
        model: str,
        temperature: float = 0.7,
    ) -> str:
        """Call Ollama /api/chat."""
        client = await self._get_client()
        response = await client.post(
            "/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": temperature, "num_predict": 2048},
            },
        )
        response.raise_for_status()
        data = response.json()
        return (data.get("message") or {}).get("content", "")

    async def _chat_via_openai(
        self,
        messages: list[dict],
        model: str,
        temperature: float = 0.7,
    ) -> str:
        """Call OpenAI Chat Completions API."""
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        # OpenAI expects system as first message or in messages
        openai_messages = []
        for m in messages:
            role = m.get("role", "user")
            if role == "system":
                openai_messages.append({"role": "system", "content": m.get("content", "")})
            else:
                openai_messages.append({"role": role, "content": m.get("content", "")})
        r = await client.chat.completions.create(
            model=model or "gpt-4o-mini",
            messages=openai_messages,
            temperature=temperature,
        )
        return (r.choices[0].message.content or "").strip()

    async def _chat_via_anthropic(
        self,
        messages: list[dict],
        model: str,
        temperature: float = 0.7,
    ) -> str:
        """Call Anthropic Messages API."""
        from anthropic import AsyncAnthropic
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        system = ""
        chat_messages = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "") or ""
            if role == "system":
                system = system + content + "\n\n" if system else content
            else:
                chat_messages.append({"role": "user" if role == "user" else "assistant", "content": content})
        if not chat_messages:
            return ""
        r = await client.messages.create(
            model=model or "claude-3-5-sonnet-20241022",
            max_tokens=2048,
            system=system or "You are a helpful assistant.",
            messages=chat_messages,
            temperature=temperature,
        )
        return (r.content[0].text if r.content else "").strip()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def chat(
        self,
        message: str,
        system_prompt: Optional[str] = None,
        context: Optional[list[dict]] = None,
        temperature: float = 0.7,
        model: Optional[str] = None,
    ) -> str:
        """
        Send a chat message and get a response.
        Uses Ollama, OpenAI, or Anthropic based on config (API keys / ai_provider).
        """
        enriched_context = await self.get_enriched_context(message)
        system_prompt = await self._get_system_context(system_prompt)
        if enriched_context:
            system_prompt = f"{system_prompt}\n\n{enriched_context}"

        messages = [{"role": "system", "content": system_prompt}]
        if context:
            messages.extend(context)
        messages.append({"role": "user", "content": message})

        provider = _chat_provider()
        used_model = model or self.model

        if provider == "openai":
            return await self._chat_via_openai(messages, used_model, temperature)
        if provider == "anthropic":
            return await self._chat_via_anthropic(messages, used_model, temperature)
        return await self._chat_via_ollama(messages, used_model, temperature)
    
    async def chat_stream(
        self,
        message: str,
        system_prompt: Optional[str] = None,
        context: Optional[list[dict]] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream a chat response token by token. Uses Ollama streaming; for OpenAI/Anthropic yields full response.
        """
        if _chat_provider() != "ollama":
            # Non-Ollama: yield full response in one chunk
            text = await self.chat(message=message, system_prompt=system_prompt, context=context)
            if text:
                yield text
            return

        messages = []
        enriched_context = await self.get_enriched_context(message)
        system_prompt = await self._get_system_context(system_prompt)

        if enriched_context:
            system_prompt = f"{system_prompt}\n\n{enriched_context}"

        messages.append({"role": "system", "content": system_prompt})
        if context:
            messages.extend(context)
        messages.append({"role": "user", "content": message})

        client = await self._get_client()
        async with client.stream(
            "POST",
            "/api/chat",
            json={
                "model": self.model,
                "messages": messages,
                "stream": True,
            },
            timeout=120.0
        ) as response:
            async for line in response.aiter_lines():
                if line:
                    try:
                        import json
                        data = json.loads(line)
                        content = data.get("message", {}).get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue
    
    # ========================================================================
    # Embeddings
    # ========================================================================
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def embed(self, text: str) -> list[float]:
        """
        Generate embedding vector for text.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector (typically 768 or 1024 dimensions)
        """
        client = await self._get_client()
        response = await client.post(
            "/api/embeddings",
            json={
                "model": self.embedding_model,
                "prompt": text,
            },
        )
        response.raise_for_status()
        
        data = response.json()
        return data.get("embedding", [])
    
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for multiple texts.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
        """
        embeddings = []
        for text in texts:
            embedding = await self.embed(text)
            embeddings.append(embedding)
        return embeddings
    
    # ========================================================================
    # Vision / Screen Understanding
    # ========================================================================
    
    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=30))
    async def understand_screen(
        self,
        image_path: Optional[str] = None,
        image_bytes: Optional[bytes] = None,
        query: str = "Describe what you see on this screen. Focus on the main application, any text content, and key UI elements.",
    ) -> str:
        """
        Analyze a screenshot using vision AI.
        
        Args:
            image_path: Path to screenshot file
            image_bytes: Raw image bytes
            query: Question to ask about the image
            
        Returns:
            Description and analysis of the screen content
        """
        # Get image as base64
        if image_path:
            with open(image_path, "rb") as f:
                image_bytes = f.read()
        
        if not image_bytes:
            raise ValueError("Either image_path or image_bytes must be provided")
        
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")
        
        client = await self._get_client()
        response = await client.post(
            "/api/chat",
            json={
                "model": self.vision_model,
                "messages": [
                    {
                        "role": "user",
                        "content": query,
                        "images": [image_base64],
                    }
                ],
                "stream": False,
            },
        )
        response.raise_for_status()
        
        data = response.json()
        return data.get("message", {}).get("content", "")
    
    async def extract_text_from_screen(
        self,
        image_path: Optional[str] = None,
        image_bytes: Optional[bytes] = None,
    ) -> str:
        """
        Extract all visible text from a screenshot.
        
        Uses vision model as a backup OCR when traditional OCR fails.
        """
        query = """Extract ALL visible text from this screenshot. 
        Include:
        - Window titles
        - Menu items
        - Button labels
        - Document content
        - Any other readable text
        
        Format the text in a readable way, preserving the general layout."""
        
        return await self.understand_screen(
            image_path=image_path,
            image_bytes=image_bytes,
            query=query,
        )
    
    async def get_contextual_suggestions(
        self,
        screen_description: str,
        user_blocks: list[dict],
    ) -> list[dict]:
        """
        Generate contextual suggestions based on screen content and user's blocks.
        
        Args:
            screen_description: Description of current screen content
            user_blocks: List of user's relevant blocks (name, description, type)
            
        Returns:
            List of suggestions with action, description, and relevance
        """
        blocks_context = "\n".join([
            f"- {b['name']}: {b.get('description', 'No description')}"
            for b in user_blocks[:10]  # Limit to top 10 relevant blocks
        ])
        
        system_prompt = """You are an intelligent assistant helping organize and manage information.
        Based on the current screen content and the user's existing organizational blocks, 
        suggest helpful actions they might want to take.
        
        Respond in JSON format with an array of suggestions:
        [
            {
                "action": "create_note" | "add_to_block" | "create_task" | "link_to_block",
                "title": "Short title for the suggestion",
                "description": "Explanation of why this would be helpful",
                "target_block": "Name of relevant block if applicable",
                "relevance": 0.0-1.0
            }
        ]
        """
        
        message = f"""Current screen shows:
{screen_description}

User's organizational blocks:
{blocks_context}

What actions would be helpful right now?"""
        
        response = await self.chat(
            message=message,
            system_prompt=system_prompt,
            temperature=0.5,
        )
        
        # Parse JSON response
        try:
            import json
            # Find JSON array in response
            start = response.find("[")
            end = response.rfind("]") + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
        except Exception:
            pass
        return []

    async def generate_task_steps(self, goal: str) -> str:
        """
        Decompose a complex goal into a structured JSON array of steps.
        """
        system_prompt = """You are Aion's Strategic Planning Module.
        Your job is to break down a user's goal into logical, sequential steps.
        Available Actions:
        - web_search(query: str): Find information online.
        - browser_task(task: str): Perform complex web automation.
        - create_block(name: str, description: str, block_type: str): Store information in a block.
        - update_block(block_id: str, content: str): Update an existing block.
        - focus_mode(topic: str): Prepare the environment for work.

        Respond ONLY with a JSON list of objects:
        [{"description": "...", "action_type": "...", "parameters": {...}, "reasoning": "..."}]
        """
        
        return await self.chat(
            message=f"Goal: {goal}",
            system_prompt=system_prompt,
            temperature=0.2
        )


# Singleton instance
_ai_service: Optional[AIService] = None


def get_ai_service() -> AIService:
    """Get the AI service singleton."""
    global _ai_service
    if _ai_service is None:
        _ai_service = AIService()
    return _ai_service
