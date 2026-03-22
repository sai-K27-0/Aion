"""
Study Service - AI-powered study assistance.

Features:
- Study plan generation
- Timetable creation
- Topic explanations
- Practice question generation
- Spaced repetition scheduling
- Flashcard generation
"""

import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict

from app.services.ai_service import get_ai_service
from app.services.smart_model_router import get_smart_router, TaskType


@dataclass
class StudyTopic:
    """A topic in a study plan."""
    name: str
    description: str
    difficulty: str  # easy, medium, hard
    estimated_hours: float
    subtopics: List[str]
    resources: List[Dict[str, str]]  # {type, title, url}
    order: int


@dataclass
class StudySession:
    """A scheduled study session."""
    date: str  # YYYY-MM-DD
    start_time: str  # HH:MM
    duration_minutes: int
    topic: str
    activity: str  # learn, review, practice, test
    completed: bool = False


@dataclass
class StudyPlan:
    """A complete study plan."""
    id: str
    subject: str
    topics: List[StudyTopic]
    sessions: List[StudySession]
    exam_date: Optional[str]
    created_at: str
    total_hours: float
    daily_hours: float


@dataclass
class Flashcard:
    """A flashcard for studying."""
    id: str
    front: str  # Question
    back: str   # Answer
    topic: str
    difficulty: str
    last_reviewed: Optional[str] = None
    review_count: int = 0
    ease_factor: float = 2.5  # For spaced repetition


@dataclass
class QuizQuestion:
    """A quiz/practice question."""
    id: str
    question: str
    options: List[str]  # For multiple choice
    correct_answer: str
    explanation: str
    topic: str
    difficulty: str


class StudyService:
    """
    Comprehensive study assistance service.
    
    Helps users:
    - Create personalized study plans
    - Generate timetables
    - Get topic explanations
    - Practice with flashcards and quizzes
    - Track progress with spaced repetition
    
    Uses smart model routing to select optimal model for each task:
    - deepseek-r1 for study plans and explanations (quality)
    - llama3.2 for quick tasks (speed)
    """
    
    def __init__(self):
        self.ai_service = get_ai_service()
        self.smart_router = get_smart_router()
    
    async def create_study_plan(
        self,
        subject: str,
        topics: Optional[List[str]] = None,
        exam_date: Optional[str] = None,
        daily_hours: float = 2.0,
        user_profile: Optional[Dict[str, Any]] = None,
    ) -> StudyPlan:
        """
        Generate a personalized study plan.
        
        Args:
            subject: The subject to study
            topics: Specific topics (if known)
            exam_date: Target exam date
            daily_hours: Available study hours per day
            user_profile: User preferences for personalization
        """
        # Calculate days until exam
        days_available = 14  # Default 2 weeks
        if exam_date:
            try:
                exam = datetime.strptime(exam_date, "%Y-%m-%d")
                days_available = max(1, (exam - datetime.now()).days)
            except:
                pass
        
        # Generate topic breakdown using AI
        prompt = f"""Create a study plan for: {subject}

{"Topics to cover: " + ", ".join(topics) if topics else "Identify the key topics to cover."}
Days available: {days_available}
Hours per day: {daily_hours}

Respond in JSON format:
{{
    "topics": [
        {{
            "name": "Topic name",
            "description": "What this topic covers",
            "difficulty": "easy|medium|hard",
            "estimated_hours": 2.0,
            "subtopics": ["subtopic1", "subtopic2"],
            "order": 1
        }}
    ],
    "recommended_resources": [
        {{"type": "video|article|practice", "title": "Resource name", "url": "URL or search term"}}
    ],
    "study_tips": ["tip1", "tip2"]
}}
"""
        
        # Use deepseek-r1 for study plan generation (complex reasoning)
        study_model = await self.smart_router.get_model_for_task(TaskType.STUDY_PLAN)
        
        response = await self.ai_service.chat(
            message=prompt,
            system_prompt="You are an expert tutor creating personalized study plans. Always respond with valid JSON.",
            temperature=0.3,
            model=study_model,
        )
        
        # Parse response
        try:
            start = response.find("{")
            end = response.rfind("}") + 1
            data = json.loads(response[start:end])
        except:
            # Fallback structure
            data = {
                "topics": [{"name": subject, "description": f"Study {subject}", "difficulty": "medium", "estimated_hours": daily_hours * days_available, "subtopics": topics or [], "order": 1}],
                "recommended_resources": [],
                "study_tips": [],
            }
        
        # Build topic objects
        study_topics = []
        for i, t in enumerate(data.get("topics", [])):
            study_topics.append(StudyTopic(
                name=t.get("name", f"Topic {i+1}"),
                description=t.get("description", ""),
                difficulty=t.get("difficulty", "medium"),
                estimated_hours=float(t.get("estimated_hours", 2)),
                subtopics=t.get("subtopics", []),
                resources=t.get("resources", data.get("recommended_resources", [])),
                order=t.get("order", i + 1),
            ))
        
        # Generate sessions
        sessions = await self._generate_sessions(
            topics=study_topics,
            days_available=days_available,
            daily_hours=daily_hours,
            exam_date=exam_date,
        )
        
        total_hours = sum(t.estimated_hours for t in study_topics)
        
        return StudyPlan(
            id=f"plan_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            subject=subject,
            topics=study_topics,
            sessions=sessions,
            exam_date=exam_date,
            created_at=datetime.now().isoformat(),
            total_hours=total_hours,
            daily_hours=daily_hours,
        )
    
    async def _generate_sessions(
        self,
        topics: List[StudyTopic],
        days_available: int,
        daily_hours: float,
        exam_date: Optional[str] = None,
    ) -> List[StudySession]:
        """Generate study sessions from topics."""
        sessions = []
        current_date = datetime.now()
        
        # Sort topics by order
        sorted_topics = sorted(topics, key=lambda t: t.order)
        
        # Distribute topics across days
        topic_idx = 0
        remaining_hours_today = daily_hours
        
        for day in range(days_available):
            session_date = (current_date + timedelta(days=day)).strftime("%Y-%m-%d")
            daily_remaining = daily_hours
            
            while daily_remaining > 0 and topic_idx < len(sorted_topics):
                topic = sorted_topics[topic_idx]
                
                # Determine session duration
                session_duration = min(daily_remaining, topic.estimated_hours, 1.5)  # Max 90 min sessions
                
                # Add learning session
                sessions.append(StudySession(
                    date=session_date,
                    start_time="09:00",  # Default time
                    duration_minutes=int(session_duration * 60),
                    topic=topic.name,
                    activity="learn" if day < days_available // 2 else "review",
                ))
                
                daily_remaining -= session_duration
                topic.estimated_hours -= session_duration
                
                if topic.estimated_hours <= 0:
                    topic_idx += 1
            
            # Add practice session at end of day if time permits
            if daily_remaining >= 0.5 and topic_idx > 0:
                sessions.append(StudySession(
                    date=session_date,
                    start_time="16:00",
                    duration_minutes=30,
                    topic=sorted_topics[min(topic_idx, len(sorted_topics)-1)].name,
                    activity="practice",
                ))
        
        # Add final review sessions before exam
        if exam_date and days_available > 3:
            review_date = (datetime.strptime(exam_date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
            sessions.append(StudySession(
                date=review_date,
                start_time="10:00",
                duration_minutes=120,
                topic="All Topics",
                activity="test",
            ))
        
        return sessions
    
    async def create_timetable(
        self,
        activities: List[Dict[str, Any]],
        start_time: str = "09:00",
        include_breaks: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Create a timetable from activities.
        
        Args:
            activities: List of {name, duration_minutes}
            start_time: Start time (HH:MM)
            include_breaks: Add break periods
        """
        timetable = []
        current_time = datetime.strptime(start_time, "%H:%M")
        work_minutes = 0
        
        for activity in activities:
            name = activity.get("name", "Activity")
            duration = int(activity.get("duration_minutes", 30))
            
            # Add break after 90 minutes of work
            if include_breaks and work_minutes >= 90:
                timetable.append({
                    "time": current_time.strftime("%H:%M"),
                    "activity": "Break",
                    "duration_minutes": 15,
                    "type": "break",
                })
                current_time += timedelta(minutes=15)
                work_minutes = 0
            
            timetable.append({
                "time": current_time.strftime("%H:%M"),
                "activity": name,
                "duration_minutes": duration,
                "type": "study",
            })
            
            current_time += timedelta(minutes=duration)
            work_minutes += duration
        
        return timetable
    
    async def explain_topic(
        self,
        topic: str,
        depth: str = "medium",
        user_level: str = "intermediate",
        include_examples: bool = True,
    ) -> Dict[str, Any]:
        """
        Generate an explanation of a topic.
        
        Args:
            topic: The topic to explain
            depth: brief, medium, detailed
            user_level: beginner, intermediate, advanced
            include_examples: Include worked examples
        """
        prompt = f"""Explain this topic: {topic}

Target audience: {user_level}
Depth level: {depth}
{"Include practical examples." if include_examples else ""}

Structure your response as:
1. Overview (1-2 sentences)
2. Key concepts
3. {"Worked examples" if include_examples else "Summary"}
4. Common mistakes to avoid
5. Practice suggestions
"""
        
        # Use deepseek-r1 for explanations (quality over speed)
        explain_model = await self.smart_router.get_model_for_task(TaskType.TOPIC_EXPLAIN)
        
        response = await self.ai_service.chat(
            message=prompt,
            system_prompt=f"You are an expert tutor explaining concepts to a {user_level} student. Be clear, concise, and use analogies when helpful.",
            temperature=0.5,
            model=explain_model,
        )
        
        return {
            "topic": topic,
            "explanation": response,
            "depth": depth,
            "level": user_level,
            "model_used": explain_model,
        }
    
    async def generate_flashcards(
        self,
        topic: str,
        count: int = 10,
        difficulty: str = "mixed",
        notes_content: Optional[str] = None,
    ) -> List[Flashcard]:
        """
        Generate flashcards for a topic.
        
        Args:
            topic: Topic to create flashcards for
            count: Number of flashcards
            difficulty: easy, medium, hard, mixed
            notes_content: Optional notes to base flashcards on
        """
        notes_section = f"Based on these notes:\n{notes_content[:2000]}" if notes_content else ""
        prompt = f"""Create {count} flashcards for: {topic}

{notes_section}

Difficulty: {difficulty}

Respond in JSON format:
[
    {{
        "front": "Question or term",
        "back": "Answer or definition",
        "difficulty": "easy|medium|hard"
    }}
]

Create cards that test understanding, not just memorization.
"""
        
        # Use deepseek-r1 for flashcard generation (quality content)
        flashcard_model = await self.smart_router.get_model_for_task(TaskType.FLASHCARDS)
        
        response = await self.ai_service.chat(
            message=prompt,
            system_prompt="You are an expert at creating effective study flashcards. Always respond with valid JSON array.",
            temperature=0.4,
            model=flashcard_model,
        )
        
        # Parse response
        try:
            start = response.find("[")
            end = response.rfind("]") + 1
            cards_data = json.loads(response[start:end])
        except:
            cards_data = []
        
        flashcards = []
        for i, card in enumerate(cards_data[:count]):
            flashcards.append(Flashcard(
                id=f"fc_{datetime.now().strftime('%Y%m%d%H%M%S')}_{i}",
                front=card.get("front", ""),
                back=card.get("back", ""),
                topic=topic,
                difficulty=card.get("difficulty", "medium"),
            ))
        
        return flashcards
    
    async def generate_quiz(
        self,
        topic: str,
        count: int = 5,
        question_types: List[str] = ["multiple_choice"],
    ) -> List[QuizQuestion]:
        """
        Generate quiz questions for testing.
        
        Args:
            topic: Topic to quiz on
            count: Number of questions
            question_types: Types of questions to include
        """
        prompt = f"""Create {count} quiz questions about: {topic}

Question types: {', '.join(question_types)}

Respond in JSON format:
[
    {{
        "question": "The question text",
        "options": ["A) Option 1", "B) Option 2", "C) Option 3", "D) Option 4"],
        "correct_answer": "A",
        "explanation": "Why this is correct",
        "difficulty": "easy|medium|hard"
    }}
]
"""
        
        # Use deepseek-r1 for quiz generation (quality questions)
        quiz_model = await self.smart_router.get_model_for_task(TaskType.QUIZ)
        
        response = await self.ai_service.chat(
            message=prompt,
            system_prompt="You are an expert at creating educational assessments. Create challenging but fair questions. Always respond with valid JSON.",
            temperature=0.4,
            model=quiz_model,
        )
        
        try:
            start = response.find("[")
            end = response.rfind("]") + 1
            questions_data = json.loads(response[start:end])
        except:
            questions_data = []
        
        questions = []
        for i, q in enumerate(questions_data[:count]):
            questions.append(QuizQuestion(
                id=f"q_{datetime.now().strftime('%Y%m%d%H%M%S')}_{i}",
                question=q.get("question", ""),
                options=q.get("options", []),
                correct_answer=q.get("correct_answer", ""),
                explanation=q.get("explanation", ""),
                topic=topic,
                difficulty=q.get("difficulty", "medium"),
            ))
        
        return questions
    
    async def get_study_suggestions(
        self,
        current_topic: str,
        performance: Optional[Dict[str, float]] = None,
        time_available: int = 30,
    ) -> Dict[str, Any]:
        """
        Get personalized study suggestions.
        
        Args:
            current_topic: What they're currently studying
            performance: Optional scores by topic
            time_available: Minutes available
        """
        prompt = f"""The student is studying: {current_topic}
Time available: {time_available} minutes
{"Previous performance: " + str(performance) if performance else ""}

Suggest:
1. What to focus on
2. Study technique to use
3. A mini-goal for this session
4. A break activity suggestion
"""
        
        response = await self.ai_service.chat(
            message=prompt,
            system_prompt="You are a supportive study coach. Give concise, actionable suggestions.",
            temperature=0.6,
        )
        
        return {
            "topic": current_topic,
            "suggestions": response,
            "time_available": time_available,
        }
    
    def study_plan_to_blocks(self, plan: StudyPlan) -> List[Dict[str, Any]]:
        """Convert a study plan to block/task structures for the frontend."""
        blocks = []
        
        # Main block
        main_block = {
            "id": plan.id,
            "name": f"{plan.subject} Study Plan",
            "type": "project",
            "icon": "📚",
            "notes": f"Study plan for {plan.subject}\nExam: {plan.exam_date or 'Not set'}\nTotal hours: {plan.total_hours}",
            "children": [],
            "todos": [],
        }
        
        # Topic sub-blocks
        for topic in plan.topics:
            topic_block = {
                "id": f"{plan.id}_{topic.name.replace(' ', '_')}",
                "name": topic.name,
                "type": "note",
                "icon": "📖",
                "notes": topic.description,
                "parentId": plan.id,
                "todos": [
                    {"text": st, "status": "not_started"} 
                    for st in topic.subtopics
                ],
            }
            blocks.append(topic_block)
            main_block["children"].append(topic_block["id"])
        
        blocks.insert(0, main_block)
        
        # Calendar tasks from sessions
        calendar_tasks = []
        for session in plan.sessions:
            calendar_tasks.append({
                "title": f"{session.activity.title()}: {session.topic}",
                "start": session.date,
                "end": session.date,
                "status": "completed" if session.completed else "not_started",
            })
        
        return {"blocks": blocks, "calendar_tasks": calendar_tasks}


# Singleton
_study_service: Optional[StudyService] = None


def get_study_service() -> StudyService:
    """Get the study service singleton."""
    global _study_service
    if _study_service is None:
        _study_service = StudyService()
    return _study_service
