import json
import os
from datetime import datetime
from uuid import uuid4
from typing import List, Dict, Optional
from pydantic import BaseModel
from pathlib import Path

# Allowed base directory for storage files
ALLOWED_DATA_DIR = Path("data").resolve()

class UserRule(BaseModel):
    id: str
    content: str
    category: str
    is_active: bool
    created_at: str

class PersonaService:
    def __init__(self, storage_path: str = "data/user_rules.json"):
        # Validate and sanitize storage path to prevent path traversal
        self.storage_path = self._validate_path(storage_path)
        self._ensure_storage()
    
    def _validate_path(self, path: str) -> str:
        """Validate that path is within allowed data directory."""
        # Resolve to absolute path
        resolved = Path(path).resolve()
        
        # Ensure it's within the allowed directory
        try:
            resolved.relative_to(ALLOWED_DATA_DIR)
        except ValueError:
            # Path is outside allowed directory, use default safe path
            resolved = ALLOWED_DATA_DIR / "user_rules.json"
        
        return str(resolved)

    def _ensure_storage(self):
        """Ensure the storage file and directory exist."""
        storage_path = Path(self.storage_path)
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        if not storage_path.exists():
            with open(self.storage_path, 'w') as f:
                json.dump([], f)

    def _load_rules(self) -> List[UserRule]:
        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
                return [UserRule(**item) for item in data]
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _save_rules(self, rules: List[UserRule]):
        with open(self.storage_path, 'w') as f:
            json.dump([rule.model_dump() for rule in rules], f, indent=2)

    async def add_rule(self, content: str, category: str = "general") -> UserRule:
        """Add a new rule to the user's persona."""
        rules = self._load_rules()
        new_rule = UserRule(
            id=str(uuid4()),
            content=content,
            category=category,
            is_active=True,
            created_at=datetime.utcnow().isoformat()
        )
        rules.append(new_rule)
        self._save_rules(rules)
        return new_rule

    async def get_active_rules(self) -> List[UserRule]:
        """Get all active rules."""
        rules = self._load_rules()
        return [r for r in rules if r.is_active]

    async def delete_rule(self, rule_id: str) -> bool:
        """Delete a rule by ID."""
        rules = self._load_rules()
        initial_len = len(rules)
        rules = [r for r in rules if r.id != rule_id]
        if len(rules) < initial_len:
            self._save_rules(rules)
            return True
        return False

    async def get_system_prompt_addition(self) -> str:
        """Format active rules for injection into the system prompt."""
        rules = await self.get_active_rules()
        if not rules:
            return ""
        
        prompt_lines = ["\n\n## USER PREFERENCES & PERSONA RULES", "You MUST follow these rules without exception:"]
        for rule in rules:
            prompt_lines.append(f"- [{rule.category.upper()}] {rule.content}")
            
        return "\n".join(prompt_lines)

# Singleton instance
_persona_service_instance = None

def get_persona_service() -> PersonaService:
    global _persona_service_instance
    if _persona_service_instance is None:
        _persona_service_instance = PersonaService()
    return _persona_service_instance
