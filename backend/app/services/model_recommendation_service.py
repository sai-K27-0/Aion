"""
Model Recommendation Service - Recommends optimal AI models based on device hardware.

Takes device specs (RAM, GPU, disk) and recommends:
- Which chat model to use (llama3.2, phi3, tinyllama, etc.)
- Which embedding model to use
- Whether to use cloud API instead
- Warnings about device limitations
"""

import logging
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Model Catalog — all models the system knows about
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ModelInfo:
    """Information about an Ollama model."""
    name: str              # Ollama model name (for pulling)
    display_name: str      # Human-readable name
    description: str       # Short description
    size_gb: float         # Download size in GB
    ram_required_gb: float # Minimum RAM to run
    speed_description: str # e.g., "~40 tokens/sec on M2"
    category: str          # "chat", "embedding", "vision", "coding"
    parameters: str        # e.g., "8B", "3.8B"
    quality_tier: int      # 1-5 (5 = best quality)
    speed_tier: int        # 1-5 (5 = fastest)


MODEL_CATALOG = {
    # ── Chat Models (sorted by size, largest first) ────────────────────
    "llama3.1:70b-q4_K_M": ModelInfo(
        name="llama3.1:70b-q4_K_M",
        display_name="Llama 3.1 70B (Quantized)",
        description="Most capable open model. Needs beefy hardware.",
        size_gb=40.0, ram_required_gb=48.0,
        speed_description="~5 tokens/sec on high-end GPU",
        category="chat", parameters="70B", quality_tier=5, speed_tier=1,
    ),
    "llama3.2": ModelInfo(
        name="llama3.2",
        display_name="Llama 3.2 (8B)",
        description="Best balance of speed and quality. Recommended for most devices.",
        size_gb=4.7, ram_required_gb=6.0,
        speed_description="~40 tokens/sec on M-series, ~15 on CPU",
        category="chat", parameters="8B", quality_tier=4, speed_tier=4,
    ),
    "mistral": ModelInfo(
        name="mistral",
        display_name="Mistral 7B",
        description="Fast and efficient. Great for general conversation.",
        size_gb=4.1, ram_required_gb=5.0,
        speed_description="~45 tokens/sec on M-series, ~18 on CPU",
        category="chat", parameters="7B", quality_tier=3, speed_tier=4,
    ),
    "deepseek-r1": ModelInfo(
        name="deepseek-r1",
        display_name="DeepSeek R1",
        description="Excellent reasoning. Best for study, analysis, problem solving.",
        size_gb=4.7, ram_required_gb=6.0,
        speed_description="~30 tokens/sec on M-series",
        category="chat", parameters="7B", quality_tier=5, speed_tier=3,
    ),
    "phi3:mini": ModelInfo(
        name="phi3:mini",
        display_name="Phi-3 Mini (3.8B)",
        description="Surprisingly smart for its size. Great for phones and low-RAM devices.",
        size_gb=2.2, ram_required_gb=4.0,
        speed_description="~20 tokens/sec on phone, ~30 on PC",
        category="chat", parameters="3.8B", quality_tier=3, speed_tier=5,
    ),
    "gemma2:2b": ModelInfo(
        name="gemma2:2b",
        display_name="Gemma 2 (2B)",
        description="Google's lightweight model. Fast on constrained devices.",
        size_gb=1.6, ram_required_gb=3.0,
        speed_description="~25 tokens/sec on phone",
        category="chat", parameters="2B", quality_tier=2, speed_tier=5,
    ),
    "tinyllama": ModelInfo(
        name="tinyllama",
        display_name="TinyLlama (1.1B)",
        description="Ultra-lightweight. Basic tasks only. Very low battery usage.",
        size_gb=0.64, ram_required_gb=2.0,
        speed_description="~40 tokens/sec on phone",
        category="chat", parameters="1.1B", quality_tier=1, speed_tier=5,
    ),

    # ── Embedding Models ───────────────────────────────────────────────
    "nomic-embed-text": ModelInfo(
        name="nomic-embed-text",
        display_name="Nomic Embed Text",
        description="Best embedding model for semantic search. 768 dimensions.",
        size_gb=0.27, ram_required_gb=1.0,
        speed_description="Instant",
        category="embedding", parameters="137M", quality_tier=4, speed_tier=5,
    ),
    "all-minilm": ModelInfo(
        name="all-minilm",
        display_name="All-MiniLM",
        description="Tiny embedding model. Good for phones with limited storage.",
        size_gb=0.046, ram_required_gb=0.5,
        speed_description="Instant",
        category="embedding", parameters="22M", quality_tier=3, speed_tier=5,
    ),

    # ── Vision Models ──────────────────────────────────────────────────
    "llava": ModelInfo(
        name="llava",
        display_name="LLaVA (Vision)",
        description="Understands images and screenshots. Needed for screen analysis.",
        size_gb=4.7, ram_required_gb=6.0,
        speed_description="~10 tokens/sec",
        category="vision", parameters="7B", quality_tier=4, speed_tier=2,
    ),

    # ── Coding Models ──────────────────────────────────────────────────
    "codellama": ModelInfo(
        name="codellama",
        display_name="Code Llama (7B)",
        description="Specialized for code generation and debugging.",
        size_gb=3.8, ram_required_gb=5.0,
        speed_description="~35 tokens/sec",
        category="coding", parameters="7B", quality_tier=4, speed_tier=3,
    ),
}

# ── Cloud alternatives ─────────────────────────────────────────────────

CLOUD_ALTERNATIVES = [
    {
        "model_name": "openrouter/auto",
        "display_name": "OpenRouter (Auto)",
        "description": "Automatically picks the best model. Some free models available.",
        "category": "cloud",
        "provider": "openrouter",
        "cost_description": "Free tier available, paid models ~$0.01-0.05/query",
    },
    {
        "model_name": "gpt-4o-mini",
        "display_name": "GPT-4o Mini (OpenAI)",
        "description": "Fast, cheap, and capable. Great as a fallback.",
        "category": "cloud",
        "provider": "openai",
        "cost_description": "$0.15 per 1M input tokens",
    },
    {
        "model_name": "claude-3-haiku-20240307",
        "display_name": "Claude 3 Haiku (Anthropic)",
        "description": "Fast and affordable Claude model.",
        "category": "cloud",
        "provider": "anthropic",
        "cost_description": "$0.25 per 1M input tokens",
    },
]


class ModelRecommendationService:
    """Recommends AI models based on device hardware capabilities."""

    def get_device_tier(
        self,
        ram_gb: Optional[float] = None,
        gpu_name: Optional[str] = None,
        gpu_vram_gb: Optional[float] = None,
        free_disk_gb: Optional[float] = None,
    ) -> str:
        """
        Classify device into a performance tier.

        Returns: "high", "medium", "low", "minimal"
        """
        if ram_gb is None:
            return "medium"  # Default assumption

        has_gpu = bool(gpu_name and gpu_name.lower() not in ["", "none", "unknown"])

        if ram_gb >= 16 and has_gpu:
            return "high"
        elif ram_gb >= 16:
            return "high"  # Apple Silicon counts as GPU
        elif ram_gb >= 8:
            return "medium"
        elif ram_gb >= 4:
            return "low"
        else:
            return "minimal"

    def get_device_summary(
        self,
        ram_gb: Optional[float],
        gpu_name: Optional[str],
        free_disk_gb: Optional[float],
        device_type: Optional[str] = None,
        tier: Optional[str] = None,
    ) -> str:
        """Generate a human-readable summary of device capabilities."""
        if tier is None:
            tier = self.get_device_tier(ram_gb, gpu_name)

        summaries = {
            "high": "Your device can run powerful AI models locally. Full local AI recommended.",
            "medium": "Your device can run mid-size AI models. Good local AI experience.",
            "low": "Your device can run lightweight AI models. Small models recommended.",
            "minimal": "Limited hardware for local AI. Cloud AI provider recommended.",
        }

        base = summaries.get(tier, summaries["medium"])

        if device_type in ("phone", "tablet"):
            base += " Battery usage will be moderate with local AI."

        return base

    def recommend_models(
        self,
        ram_gb: Optional[float] = None,
        gpu_name: Optional[str] = None,
        gpu_vram_gb: Optional[float] = None,
        free_disk_gb: Optional[float] = None,
        device_type: Optional[str] = None,
        platform: Optional[str] = None,
    ) -> dict:
        """
        Generate model recommendations based on device hardware.

        Returns full recommendation set with chat models, embedding models,
        cloud alternatives, and the recommended picks.
        """
        tier = self.get_device_tier(ram_gb, gpu_name, gpu_vram_gb, free_disk_gb)
        summary = self.get_device_summary(ram_gb, gpu_name, free_disk_gb, device_type, tier)

        effective_ram = ram_gb or 4.0
        effective_disk = free_disk_gb or 10.0

        # ── Select chat models ─────────────────────────────────────────
        chat_models = []
        recommended_chat = None

        for name, info in MODEL_CATALOG.items():
            if info.category != "chat":
                continue

            can_run = (
                effective_ram >= info.ram_required_gb
                and effective_disk >= info.size_gb
            )

            warning = None
            if not can_run:
                if effective_ram < info.ram_required_gb:
                    warning = f"Needs {info.ram_required_gb}GB RAM (you have {effective_ram}GB)"
                elif effective_disk < info.size_gb:
                    warning = f"Needs {info.size_gb}GB disk space (you have {effective_disk}GB free)"

            # Determine if this is the recommended model
            is_recommended = False
            if can_run and recommended_chat is None:
                if tier == "high" and info.name in ("llama3.2", "deepseek-r1"):
                    is_recommended = True
                elif tier == "medium" and info.name in ("llama3.2", "mistral"):
                    is_recommended = True
                elif tier == "low" and info.name in ("phi3:mini", "gemma2:2b"):
                    is_recommended = True
                elif tier == "minimal" and info.name == "tinyllama":
                    is_recommended = True

            if is_recommended:
                recommended_chat = info.name

            chat_models.append({
                "model_name": info.name,
                "display_name": info.display_name,
                "description": info.description,
                "size_gb": info.size_gb,
                "ram_required_gb": info.ram_required_gb,
                "speed_description": info.speed_description,
                "category": info.category,
                "recommended": is_recommended,
                "reason": f"Best fit for your {tier}-tier device" if is_recommended else "",
                "can_run_on_device": can_run,
                "warning": warning,
            })

        # ── Select embedding models ────────────────────────────────────
        embedding_models = []
        recommended_embedding = None

        for name, info in MODEL_CATALOG.items():
            if info.category != "embedding":
                continue

            can_run = effective_ram >= info.ram_required_gb and effective_disk >= info.size_gb

            is_recommended = False
            if can_run and recommended_embedding is None:
                if effective_ram >= 4:
                    if info.name == "nomic-embed-text":
                        is_recommended = True
                else:
                    if info.name == "all-minilm":
                        is_recommended = True

            if is_recommended:
                recommended_embedding = info.name

            embedding_models.append({
                "model_name": info.name,
                "display_name": info.display_name,
                "description": info.description,
                "size_gb": info.size_gb,
                "ram_required_gb": info.ram_required_gb,
                "speed_description": info.speed_description,
                "category": info.category,
                "recommended": is_recommended,
                "reason": f"Best embedding model for your device" if is_recommended else "",
                "can_run_on_device": can_run,
                "warning": None,
            })

        # ── Cloud alternatives ─────────────────────────────────────────
        cloud_models = []
        for alt in CLOUD_ALTERNATIVES:
            cloud_models.append({
                "model_name": alt["model_name"],
                "display_name": alt["display_name"],
                "description": alt["description"] + f" ({alt['cost_description']})",
                "size_gb": 0.0,
                "ram_required_gb": 0.0,
                "speed_description": "Fast (cloud)",
                "category": alt["category"],
                "recommended": tier == "minimal",
                "reason": "Recommended for devices with limited hardware" if tier == "minimal" else "Available as fallback",
                "can_run_on_device": True,
                "warning": None,
            })

        # ── Calculate totals ───────────────────────────────────────────
        total_download = 0.0
        if recommended_chat and recommended_chat in MODEL_CATALOG:
            total_download += MODEL_CATALOG[recommended_chat].size_gb
        if recommended_embedding and recommended_embedding in MODEL_CATALOG:
            total_download += MODEL_CATALOG[recommended_embedding].size_gb

        # Rough estimate: 50 Mbps average broadband
        estimated_minutes = round((total_download * 1024) / (50 / 8 * 60), 1) if total_download > 0 else 0

        return {
            "device_tier": tier,
            "device_summary": summary,
            "chat_models": chat_models,
            "embedding_models": embedding_models,
            "cloud_alternatives": cloud_models,
            "recommended_chat": recommended_chat,
            "recommended_embedding": recommended_embedding,
            "total_download_gb": round(total_download, 2),
            "estimated_download_minutes": estimated_minutes,
        }


# Singleton
_recommendation_service: Optional[ModelRecommendationService] = None


def get_recommendation_service() -> ModelRecommendationService:
    """Get the model recommendation service singleton."""
    global _recommendation_service
    if _recommendation_service is None:
        _recommendation_service = ModelRecommendationService()
    return _recommendation_service
