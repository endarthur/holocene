"""Tests for database storage."""

import pytest
from datetime import datetime, timedelta
from pathlib import Path
import tempfile

from holocene.core.models import Activity, ActivityType, Context
from holocene.storage.database import Database


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)
        yield db
        db.close()


def test_insert_and_get_activity(temp_db):
    """Test inserting and retrieving an activity."""
    activity = Activity(
        description="Test activity",
        activity_type=ActivityType.CODING,
        context=Context.PERSONAL,
        tags=["test", "python"],
        duration_minutes=30,
    )

    # Insert
    activity_id = temp_db.insert_activity(activity)
    assert activity_id > 0

    # Retrieve
    retrieved = temp_db.get_activity(activity_id)
    assert retrieved is not None
    assert retrieved.description == "Test activity"
    assert retrieved.activity_type == ActivityType.CODING
    assert retrieved.tags == ["test", "python"]
    assert retrieved.duration_minutes == 30


def test_get_nonexistent_activity(temp_db):
    """Test retrieving non-existent activity returns None."""
    activity = temp_db.get_activity(99999)
    assert activity is None


def test_get_activities_with_filters(temp_db):
    """Test filtering activities by various criteria."""
    now = datetime.now()

    # Insert activities with different types and times
    activities = [
        Activity(
            description="Activity 1",
            activity_type=ActivityType.CODING,
            timestamp=now - timedelta(hours=2),
        ),
        Activity(
            description="Activity 2",
            activity_type=ActivityType.RESEARCH,
            timestamp=now - timedelta(hours=1),
        ),
        Activity(
            description="Activity 3",
            activity_type=ActivityType.CODING,
            timestamp=now,
        ),
    ]

    for activity in activities:
        temp_db.insert_activity(activity)

    # Filter by type
    coding_activities = temp_db.get_activities(activity_type="coding")
    assert len(coding_activities) == 2

    # Filter by date range
    recent = temp_db.get_activities(start_date=now - timedelta(hours=1, minutes=30))
    assert len(recent) == 2

    # Filter with limit
    limited = temp_db.get_activities(limit=1)
    assert len(limited) == 1


def test_get_activities_today(temp_db):
    """Test getting today's activities."""
    now = datetime.now()
    yesterday = now - timedelta(days=1)

    # Insert today and yesterday
    temp_db.insert_activity(Activity(
        description="Today",
        timestamp=now,
    ))
    temp_db.insert_activity(Activity(
        description="Yesterday",
        timestamp=yesterday,
    ))

    today_activities = temp_db.get_activities_today()
    assert len(today_activities) == 1
    assert today_activities[0].description == "Today"


def test_delete_activity(temp_db):
    """Test deleting an activity."""
    activity = Activity(description="To be deleted")
    activity_id = temp_db.insert_activity(activity)

    # Delete
    deleted = temp_db.delete_activity(activity_id)
    assert deleted is True

    # Verify deletion
    retrieved = temp_db.get_activity(activity_id)
    assert retrieved is None


def test_count_activities(temp_db):
    """Test counting activities."""
    now = datetime.now()

    # Insert 3 activities
    for i in range(3):
        temp_db.insert_activity(Activity(
            description=f"Activity {i}",
            timestamp=now - timedelta(hours=i),
        ))

    # Count all
    total = temp_db.count_activities()
    assert total == 3

    # Count in date range
    recent = temp_db.count_activities(start_date=now - timedelta(hours=1, minutes=30))
    assert recent == 2
