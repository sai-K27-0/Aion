"""
User Profile Service - Learn and adapt to user personality.

Features:
- Extract preferences from conversations
- Build personality profile
- Adapt response style
- Remember user facts
- Track learning patterns
"""

import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict
from enum import Enum

from app.services.ai_service import get_ai_service


class PreferenceCategory(str, Enum):
    """Categories of user preferences."""
    LEARNING_STYLE = "learning_style"
    COMMUNICATION = "communication"
    SCHEDULE = "schedule"
    INTERESTS = "interests"
    GOALS = "goals"
    HABITS = "habits"
    PERSONALITY = "personality"
    WORK_PATTERN = "work_pattern"


@dataclass
class UserFact:
    """A fact learned about the user."""
    id: str
    category: PreferenceCategory
    fact: str
    confidence: float
    source: str  # conversation, explicit, inferred
    created_at: str
    last_referenced: str
    reference_count: int = 1


@dataclass
class UserProfile:
    """Complete user profile."""
    user_id: str
    facts: List[UserFact]
    summary: str
    learning_style: Optional[str]
    communication_preference: Optional[str]
    best_study_time: Optional[str]
    interests: List[str]
    goals: List[str]
    created_at: str
    updated_at: str


class UserProfileService:
    """
    Service for learning and adapting to user personality.
    
    Extracts preferences from:
    - Explicit statements ("I prefer...")
    - Behavior patterns (when they study, how long)
    - Corrections to AI suggestions
    - Conversation topics
    """
    
    # Patterns to look for in messages
    PREFERENCE_PATTERNS = [
        ("i prefer", PreferenceCategory.COMMUNICATION),
        ("i like", PreferenceCategory.INTERESTS),
        ("i want to", PreferenceCategory.GOALS),
        ("i usually", PreferenceCategory.HABITS),
        ("i'm a", PreferenceCategory.PERSONALITY),
        ("i work best", PreferenceCategory.WORK_PATTERN),
        ("i study", PreferenceCategory.LEARNING_STYLE),
        ("my goal", PreferenceCategory.GOALS),
        ("i need to", PreferenceCategory.GOALS),
    ]
    
    def __init__(self):
        self.ai_service = get_ai_service()
        self._profiles: Dict[str, UserProfile] = {}  # In-memory cache
        self._facts: Dict[str, List[UserFact]] = {}  # user_id -> facts
    
    async def extract_facts(
        self,
        user_id: str,
        message: str,
        context: Optional[str] = None,
    ) -> List[UserFact]:
        """
        Extract learnable facts from a user message.
        
        Args:
            user_id: User identifier
            message: The user's message
            context: Optional conversation context
        """
        # Quick pattern matching first
        quick_facts = self._quick_extract(message)
        
        # Use AI for deeper extraction
        ai_facts = await self._ai_extract(message, context)
        
        # Combine and deduplicate
        all_facts = quick_facts + ai_facts
        
        # Store facts
        if user_id not in self._facts:
            self._facts[user_id] = []
        
        new_facts = []
        for fact in all_facts:
            # Check for duplicates
            if not self._is_duplicate(user_id, fact):
                fact.id = f"fact_{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{len(self._facts[user_id])}"
                self._facts[user_id].append(fact)
                new_facts.append(fact)
        
        return new_facts
    
    def _quick_extract(self, message: str) -> List[UserFact]:
        """Quick pattern-based extraction."""
        facts = []
        message_lower = message.lower()
        
        for pattern, category in self.PREFERENCE_PATTERNS:
            if pattern in message_lower:
                # Extract the relevant part
                idx = message_lower.find(pattern)
                # Get rest of sentence
                end_idx = message.find(".", idx)
                if end_idx == -1:
                    end_idx = len(message)
                
                fact_text = message[idx:end_idx].strip()
                
                facts.append(UserFact(
                    id="",
                    category=category,
                    fact=fact_text,
                    confidence=0.7,
                    source="explicit",
                    created_at=datetime.now().isoformat(),
                    last_referenced=datetime.now().isoformat(),
                ))
        
        return facts
    
    async def _ai_extract(
        self,
        message: str,
        context: Optional[str] = None,
    ) -> List[UserFact]:
        """Use AI to extract deeper insights."""
        prompt = f"""Analyze this user message for facts about them:

Message: "{message}"
{"Context: " + context if context else ""}

Extract any facts about:
- Learning preferences (visual, auditory, reading, hands-on)
- Communication style (brief, detailed, casual, formal)
- Work patterns (morning person, night owl, break preferences)
- Interests and topics they care about
- Goals (short-term, long-term)
- Personality traits
- Schedule preferences

Respond in JSON:
[
    {{
        "category": "learning_style|communication|schedule|interests|goals|habits|personality|work_pattern",
        "fact": "The extracted fact",
        "confidence": 0.0-1.0
    }}
]

Only include facts you're confident about. Return [] if no clear facts.
"""
        
        try:
            response = await self.ai_service.chat(
                message=prompt,
                system_prompt="You are analyzing user messages to learn about them. Be conservative - only extract clear facts.",
                temperature=0.2,
            )
            
            start = response.find("[")
            end = response.rfind("]") + 1
            if start >= 0 and end > start:
                data = json.loads(response[start:end])
                
                facts = []
                for item in data:
                    try:
                        category = PreferenceCategory(item.get("category", "interests"))
                    except:
                        category = PreferenceCategory.INTERESTS
                    
                    facts.append(UserFact(
                        id="",
                        category=category,
                        fact=item.get("fact", ""),
                        confidence=float(item.get("confidence", 0.5)),
                        source="inferred",
                        created_at=datetime.now().isoformat(),
                        last_referenced=datetime.now().isoformat(),
                    ))
                return facts
        except:
            pass
        
        return []
    
    def _is_duplicate(self, user_id: str, new_fact: UserFact) -> bool:
        """Check if fact already exists."""
        if user_id not in self._facts:
            return False
        
        for existing in self._facts[user_id]:
            # Simple similarity check
            if (existing.category == new_fact.category and 
                existing.fact.lower() == new_fact.fact.lower()):
                # Update reference
                existing.last_referenced = datetime.now().isoformat()
                existing.reference_count += 1
                return True
        
        return False
    
    async def get_profile(self, user_id: str) -> UserProfile:
        """Get or create user profile."""
        if user_id in self._profiles:
            return self._profiles[user_id]
        
        # Build profile from facts
        facts = self._facts.get(user_id, [])
        
        # Analyze facts to build summary
        summary = await self._build_summary(facts)
        
        profile = UserProfile(
            user_id=user_id,
            facts=facts,
            summary=summary,
            learning_style=self._get_category_summary(facts, PreferenceCategory.LEARNING_STYLE),
            communication_preference=self._get_category_summary(facts, PreferenceCategory.COMMUNICATION),
            best_study_time=self._get_category_summary(facts, PreferenceCategory.SCHEDULE),
            interests=self._get_category_list(facts, PreferenceCategory.INTERESTS),
            goals=self._get_category_list(facts, PreferenceCategory.GOALS),
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        )
        
        self._profiles[user_id] = profile
        return profile
    
    def _get_category_summary(
        self,
        facts: List[UserFact],
        category: PreferenceCategory,
    ) -> Optional[str]:
        """Get summary for a specific category."""
        category_facts = [f for f in facts if f.category == category and f.confidence > 0.5]
        if not category_facts:
            return None
        
        # Return highest confidence fact
        best = max(category_facts, key=lambda f: f.confidence)
        return best.fact
    
    def _get_category_list(
        self,
        facts: List[UserFact],
        category: PreferenceCategory,
    ) -> List[str]:
        """Get list of facts for a category."""
        return [
            f.fact for f in facts 
            if f.category == category and f.confidence > 0.5
        ][:10]  # Limit to 10
    
    async def _build_summary(self, facts: List[UserFact]) -> str:
        """Build a natural language summary of the profile."""
        if not facts:
            return "New user - learning preferences."
        
        facts_text = "\n".join([f"- {f.category.value}: {f.fact}" for f in facts[:20]])
        
        prompt = f"""Summarize this user profile in 2-3 sentences:

Facts:
{facts_text}

Write a brief, natural description of this person's preferences and style.
"""
        
        try:
            response = await self.ai_service.chat(
                message=prompt,
                system_prompt="Write a brief, friendly summary.",
                temperature=0.5,
            )
            return response
        except:
            return "User with diverse interests and preferences."
    
    async def adapt_response(
        self,
        user_id: str,
        response: str,
    ) -> str:
        """
        Adapt a response based on user preferences.
        
        Args:
            user_id: User identifier
            response: The original response
        """
        profile = await self.get_profile(user_id)
        
        # If no strong preferences, return original
        if not profile.communication_preference and not profile.learning_style:
            return response
        
        prompt = f"""Adapt this response for the user's preferences:

Original response: "{response}"

User preferences:
{f"- Communication: {profile.communication_preference}" if profile.communication_preference else ""}
{f"- Learning style: {profile.learning_style}" if profile.learning_style else ""}
{f"- Interests: {', '.join(profile.interests[:5])}" if profile.interests else ""}

Rewrite to match their style while keeping the same information.
If original is already good, return it unchanged.
"""
        
        try:
            adapted = await self.ai_service.chat(
                message=prompt,
                system_prompt="Adapt the response to match user preferences. Be concise.",
                temperature=0.4,
            )
            return adapted
        except:
            return response
    
    def get_context_for_prompt(self, user_id: str) -> str:
        """Get profile context to inject into AI prompts."""
        if user_id not in self._facts:
            return ""
        
        facts = self._facts[user_id]
        if not facts:
            return ""
        
        # Get top facts by reference count and confidence
        sorted_facts = sorted(
            facts,
            key=lambda f: f.reference_count * f.confidence,
            reverse=True,
        )[:10]
        
        context_lines = ["User profile:"]
        for fact in sorted_facts:
            context_lines.append(f"- {fact.fact}")
        
        return "\n".join(context_lines)
    
    async def learn_from_correction(
        self,
        user_id: str,
        ai_suggestion: Dict[str, Any],
        user_action: Dict[str, Any],
    ) -> Optional[UserFact]:
        """
        Learn from when user corrects AI suggestion.
        
        Args:
            user_id: User identifier
            ai_suggestion: What AI suggested
            user_action: What user actually did
        """
        # Compare suggestion vs action
        prompt = f"""The AI suggested: {json.dumps(ai_suggestion)}
The user instead did: {json.dumps(user_action)}

What preference does this reveal? Be specific.
Respond in JSON: {{"category": "...", "fact": "...", "confidence": 0.0-1.0}}
Return {{"fact": null}} if no clear preference.
"""
        
        try:
            response = await self.ai_service.chat(
                message=prompt,
                system_prompt="Analyze user corrections to learn preferences.",
                temperature=0.2,
            )
            
            start = response.find("{")
            end = response.rfind("}") + 1
            data = json.loads(response[start:end])
            
            if data.get("fact"):
                fact = UserFact(
                    id=f"fact_{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_correction",
                    category=PreferenceCategory(data.get("category", "preference")),
                    fact=data["fact"],
                    confidence=float(data.get("confidence", 0.6)),
                    source="correction",
                    created_at=datetime.now().isoformat(),
                    last_referenced=datetime.now().isoformat(),
                )
                
                if user_id not in self._facts:
                    self._facts[user_id] = []
                self._facts[user_id].append(fact)
                
                # Invalidate cached profile
                if user_id in self._profiles:
                    del self._profiles[user_id]
                
                return fact
        except:
            pass
        
        return None
    
    def get_facts(self, user_id: str) -> List[UserFact]:
        """Get all facts for a user."""
        return self._facts.get(user_id, [])
    
    def add_explicit_fact(
        self,
        user_id: str,
        category: PreferenceCategory,
        fact: str,
    ) -> UserFact:
        """Add an explicitly stated fact."""
        new_fact = UserFact(
            id=f"fact_{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_explicit",
            category=category,
            fact=fact,
            confidence=0.9,  # High confidence for explicit facts
            source="explicit",
            created_at=datetime.now().isoformat(),
            last_referenced=datetime.now().isoformat(),
        )
        
        if user_id not in self._facts:
            self._facts[user_id] = []
        self._facts[user_id].append(new_fact)
        
        # Invalidate cached profile
        if user_id in self._profiles:
            del self._profiles[user_id]
        
        return new_fact


# Singleton
_profile_service: Optional[UserProfileService] = None


def get_profile_service() -> UserProfileService:
    """Get the profile service singleton."""
    global _profile_service
    if _profile_service is None:
        _profile_service = UserProfileService()
    return _profile_service
