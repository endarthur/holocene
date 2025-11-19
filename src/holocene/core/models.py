"""Core data models for Holocene."""

from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class ActivityType(str, Enum):
    """Types of activities that can be logged."""

    CODING = "coding"
    RESEARCH = "research"
    DOCUMENTATION = "documentation"
    MEETING = "meeting"
    COMMUNICATION = "communication"
    LEARNING = "learning"
    PLANNING = "planning"
    BREAK = "break"
    OTHER = "other"


class Context(str, Enum):
    """Context/environment where activity occurred."""

    WORK = "work"
    PERSONAL = "personal"
    OPEN_SOURCE = "open_source"
    UNKNOWN = "unknown"


class Activity(BaseModel):
    """An activity record in Holocene."""

    id: Optional[int] = None
    timestamp: datetime = Field(default_factory=datetime.now)
    activity_type: ActivityType = ActivityType.OTHER
    context: Context = Context.UNKNOWN
    description: str = Field(..., min_length=1, max_length=500)
    tags: List[str] = Field(default_factory=list)
    duration_minutes: Optional[int] = None
    source: str = "manual"  # manual, browser, window, journel, etc.
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "activity_type": self.activity_type.value,
            "context": self.context.value,
            "description": self.description,
            "tags": ",".join(self.tags),  # Store as comma-separated
            "duration_minutes": self.duration_minutes,
            "source": self.source,
            "metadata": str(self.metadata),  # Store as string for SQLite
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Activity":
        """Create from dictionary (from storage)."""
        # Parse tags from comma-separated string
        tags = data.get("tags", "").split(",") if data.get("tags") else []
        tags = [t.strip() for t in tags if t.strip()]

        # Parse timestamps
        timestamp = datetime.fromisoformat(data["timestamp"])
        created_at = datetime.fromisoformat(data.get("created_at", data["timestamp"]))

        # Parse metadata (stored as string in SQLite)
        import ast
        metadata = {}
        if data.get("metadata"):
            try:
                metadata = ast.literal_eval(data["metadata"])
            except:
                metadata = {}

        return cls(
            id=data.get("id"),
            timestamp=timestamp,
            activity_type=ActivityType(data["activity_type"]),
            context=Context(data["context"]),
            description=data["description"],
            tags=tags,
            duration_minutes=data.get("duration_minutes"),
            source=data["source"],
            metadata=metadata,
            created_at=created_at,
        )
