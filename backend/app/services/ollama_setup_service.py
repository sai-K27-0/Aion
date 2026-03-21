"""
Ollama Setup Service - Detect, install, and manage Ollama on any device.

Responsibilities:
- Detect if Ollama is installed and running
- Provide platform-specific installation instructions
- Pull (download) models with progress tracking
- Health check Ollama instances (local or remote)
- Verify models work correctly after installation
"""

import json
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# Ollama Install Instructions Per Platform
# ═══════════════════════════════════════════════════════════════════════════

INSTALL_INSTRUCTIONS = {
    "windows": {
        "install_method": "manual",
        "download_url": "https://ollama.com/download/OllamaSetup.exe",
        "instructions": [
            "Download the Ollama installer from https://ollama.com/download",
            "Run OllamaSetup.exe and follow the installation wizard",
            "Ollama will start automatically and run in the system tray",
            "Verify by opening a terminal and running: ollama --version",
        ],
    },
    "macos": {
        "install_method": "auto",
        "install_command": "brew install ollama && brew services start ollama",
        "download_url": "https://ollama.com/download/Ollama-darwin.zip",
        "instructions": [
            "Option A (Homebrew): Run 'brew install ollama' in Terminal",
            "Then start it: 'brew services start ollama'",
            "Option B (Manual): Download from https://ollama.com/download",
            "Drag Ollama.app to Applications and open it",
            "Ollama runs as a menu bar app",
        ],
    },
    "linux": {
        "install_method": "auto",
        "install_command": "curl -fsSL https://ollama.com/install.sh | sh",
        "download_url": "https://ollama.com/download",
        "instructions": [
            "Run this command in your terminal:",
            "curl -fsSL https://ollama.com/install.sh | sh",
            "Start the service: 'systemctl start ollama'",
            "Enable on boot: 'systemctl enable ollama'",
        ],
    },
    "android": {
        "install_method": "manual",
        "download_url": "https://f-droid.org/packages/com.termux/",
        "instructions": [
            "Install Termux from F-Droid (not Play Store)",
            "Open Termux and run: pkg update && pkg install ollama",
            "Start Ollama: ollama serve &",
            "Pull a lightweight model: ollama pull phi3:mini",
            "Note: Use small models (phi3:mini, tinyllama) on phones",
        ],
    },
    "ios": {
        "install_method": "not_supported",
        "instructions": [
            "Ollama is not directly available on iOS",
            "Recommended: Use a cloud AI provider (OpenRouter, OpenAI)",
            "Alternative: Connect to Ollama running on another device",
            "Set AI Source to 'Remote Ollama' and enter your Mac/PC's IP",
        ],
    },
}


class OllamaSetupService:
    """Service for detecting, installing, and managing Ollama."""

    def __init__(self):
        self._http_timeout = 10.0  # seconds for health checks

    # ── Health Check ───────────────────────────────────────────────────

    async def check_health(self, ollama_url: str = "http://localhost:11434") -> dict:
        """
        Check if an Ollama instance is reachable and get its status.

        Returns dict with: reachable, version, models_installed, model_details, gpu_available
        """
        result = {
            "reachable": False,
            "url": ollama_url,
            "version": None,
            "models_installed": [],
            "model_details": [],
            "gpu_available": False,
            "error": None,
        }

        async with httpx.AsyncClient(timeout=self._http_timeout) as client:
            # Check version
            try:
                resp = await client.get(f"{ollama_url}/api/version")
                if resp.status_code == 200:
                    result["reachable"] = True
                    data = resp.json()
                    result["version"] = data.get("version", "unknown")
                else:
                    result["error"] = f"Ollama returned status {resp.status_code}"
                    return result
            except httpx.ConnectError:
                result["error"] = "Cannot connect to Ollama. Is it running?"
                return result
            except httpx.TimeoutException:
                result["error"] = "Connection timed out. Ollama may be starting up."
                return result
            except Exception as e:
                result["error"] = f"Connection error: {str(e)}"
                return result

            # List installed models
            try:
                resp = await client.get(f"{ollama_url}/api/tags")
                if resp.status_code == 200:
                    data = resp.json()
                    models = data.get("models", [])
                    result["models_installed"] = [m["name"] for m in models]
                    result["model_details"] = [
                        {
                            "name": m["name"],
                            "size_bytes": m.get("size", 0),
                            "size_gb": round(m.get("size", 0) / (1024**3), 2),
                            "family": m.get("details", {}).get("family", "unknown"),
                            "parameter_size": m.get("details", {}).get("parameter_size", "unknown"),
                            "quantization": m.get("details", {}).get("quantization_level", "unknown"),
                        }
                        for m in models
                    ]
            except Exception as e:
                logger.warning(f"Could not list models from {ollama_url}: {e}")

        return result

    # ── Installation Instructions ──────────────────────────────────────

    def get_install_instructions(self, platform: str) -> dict:
        """
        Get platform-specific Ollama installation instructions.

        Args:
            platform: "windows", "macos", "linux", "android", "ios"
        """
        platform = platform.lower()
        info = INSTALL_INSTRUCTIONS.get(platform, INSTALL_INSTRUCTIONS["linux"])

        return {
            "platform": platform,
            "install_method": info["install_method"],
            "install_command": info.get("install_command"),
            "download_url": info.get("download_url"),
            "instructions": info["instructions"],
            "post_install_check": "http://localhost:11434/api/version",
        }

    # ── Model Pull (Download) ─────────────────────────────────────────

    async def pull_model(
        self,
        model_name: str,
        ollama_url: str = "http://localhost:11434",
    ) -> dict:
        """
        Pull (download) a model via Ollama API.

        This is a blocking call that waits for the download to complete.
        For progress tracking, use pull_model_stream().

        Returns dict with: status, model_name, error
        """
        try:
            async with httpx.AsyncClient(timeout=600.0) as client:
                resp = await client.post(
                    f"{ollama_url}/api/pull",
                    json={"name": model_name, "stream": False},
                )
                if resp.status_code == 200:
                    return {"status": "complete", "model_name": model_name, "error": None}
                else:
                    return {
                        "status": "error",
                        "model_name": model_name,
                        "error": f"Ollama returned status {resp.status_code}: {resp.text}",
                    }
        except httpx.TimeoutException:
            return {
                "status": "error",
                "model_name": model_name,
                "error": "Download timed out (>10 minutes). Try again or use a smaller model.",
            }
        except Exception as e:
            return {"status": "error", "model_name": model_name, "error": str(e)}

    async def pull_model_stream(
        self,
        model_name: str,
        ollama_url: str = "http://localhost:11434",
    ):
        """
        Pull a model with streaming progress updates.

        Yields dicts with: status, progress_percent, downloaded_gb, total_gb
        """
        try:
            async with httpx.AsyncClient(timeout=600.0) as client:
                async with client.stream(
                    "POST",
                    f"{ollama_url}/api/pull",
                    json={"name": model_name, "stream": True},
                ) as resp:
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            status = data.get("status", "")

                            progress = {
                                "model_name": model_name,
                                "status": "downloading",
                                "progress_percent": None,
                                "downloaded_gb": None,
                                "total_gb": None,
                                "error": None,
                            }

                            total = data.get("total", 0)
                            completed = data.get("completed", 0)

                            if total > 0:
                                progress["progress_percent"] = round(
                                    (completed / total) * 100, 1
                                )
                                progress["total_gb"] = round(total / (1024**3), 2)
                                progress["downloaded_gb"] = round(
                                    completed / (1024**3), 2
                                )

                            if "pulling" in status:
                                progress["status"] = "downloading"
                            elif "verifying" in status:
                                progress["status"] = "verifying"
                                progress["progress_percent"] = 99.0
                            elif "writing" in status:
                                progress["status"] = "installing"
                                progress["progress_percent"] = 99.5
                            elif "success" in status:
                                progress["status"] = "complete"
                                progress["progress_percent"] = 100.0

                            yield progress
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            yield {
                "model_name": model_name,
                "status": "error",
                "progress_percent": None,
                "downloaded_gb": None,
                "total_gb": None,
                "error": str(e),
            }

    # ── Model Verification ─────────────────────────────────────────────

    async def verify_model(
        self,
        model_name: str,
        ollama_url: str = "http://localhost:11434",
    ) -> dict:
        """
        Verify a model works by sending a simple test prompt.

        Returns dict with: working, model_name, response_time_ms, error
        """
        import time

        start = time.time()
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{ollama_url}/api/chat",
                    json={
                        "model": model_name,
                        "messages": [
                            {"role": "user", "content": "Reply with exactly: OK"}
                        ],
                        "stream": False,
                        "options": {"num_predict": 10},
                    },
                )
                elapsed_ms = int((time.time() - start) * 1000)

                if resp.status_code == 200:
                    data = resp.json()
                    content = data.get("message", {}).get("content", "")
                    return {
                        "working": True,
                        "model_name": model_name,
                        "test_response": content.strip()[:100],
                        "response_time_ms": elapsed_ms,
                        "error": None,
                    }
                else:
                    return {
                        "working": False,
                        "model_name": model_name,
                        "test_response": None,
                        "response_time_ms": elapsed_ms,
                        "error": f"Status {resp.status_code}",
                    }
        except Exception as e:
            elapsed_ms = int((time.time() - start) * 1000)
            return {
                "working": False,
                "model_name": model_name,
                "test_response": None,
                "response_time_ms": elapsed_ms,
                "error": str(e),
            }

    async def verify_embedding_model(
        self,
        model_name: str,
        ollama_url: str = "http://localhost:11434",
    ) -> dict:
        """Verify an embedding model works."""
        import time

        start = time.time()
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{ollama_url}/api/embeddings",
                    json={"model": model_name, "prompt": "test embedding"},
                )
                elapsed_ms = int((time.time() - start) * 1000)

                if resp.status_code == 200:
                    data = resp.json()
                    embedding = data.get("embedding", [])
                    return {
                        "working": True,
                        "model_name": model_name,
                        "embedding_dimensions": len(embedding),
                        "response_time_ms": elapsed_ms,
                        "error": None,
                    }
                else:
                    return {
                        "working": False,
                        "model_name": model_name,
                        "embedding_dimensions": 0,
                        "response_time_ms": elapsed_ms,
                        "error": f"Status {resp.status_code}",
                    }
        except Exception as e:
            elapsed_ms = int((time.time() - start) * 1000)
            return {
                "working": False,
                "model_name": model_name,
                "embedding_dimensions": 0,
                "response_time_ms": elapsed_ms,
                "error": str(e),
            }


# Singleton
_ollama_setup_service: Optional[OllamaSetupService] = None


def get_ollama_setup_service() -> OllamaSetupService:
    """Get the Ollama setup service singleton."""
    global _ollama_setup_service
    if _ollama_setup_service is None:
        _ollama_setup_service = OllamaSetupService()
    return _ollama_setup_service
