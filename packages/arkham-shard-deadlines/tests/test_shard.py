"""Tests for deadlines shard implementation."""

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arkham_shard_deadlines.models import (
    CaseType,
    Deadline,
    DeadlineFilter,
    DeadlineRule,
    DeadlineStats,
    DeadlineStatus,
    DeadlineType,
    UrgencyLevel,
)
from arkham_shard_deadlines.shard import DEFAULT_RULES, DeadlinesShard, _parse_json_field


@pytest.fixture
def mock_frame():
    """Create a mock ArkhamFrame instance."""
    frame = MagicMock()
    frame.database = MagicMock()
    frame.get_service = MagicMock(return_value=MagicMock())

    frame.database.execute = AsyncMock()
    frame.database.fetch_one = AsyncMock()
    frame.database.fetch_all = AsyncMock()

    events = frame.get_service.return_value
    events.subscribe = AsyncMock()
    events.unsubscribe = AsyncMock()
    events.emit = AsyncMock()

    return frame


@pytest.fixture
async def shard(mock_frame):
    """Create an initialized DeadlinesShard instance."""
    # Prevent seed from running by default
    mock_frame.database.fetch_one.return_value = {"cnt": 1}
    s = DeadlinesShard()
    await s.initialize(mock_frame)
    return s


# === Initialization Tests ===


@pytest.mark.asyncio
async def test_shard_initialization(mock_frame):
    """Test shard initializes correctly."""
    mock_frame.database.fetch_one.return_value = {"cnt": 1}
    s = DeadlinesShard()
    assert s.name == "deadlines"
    assert s.version == "0.1.0"
    await s.initialize(mock_frame)
    assert s._db is mock_frame.database


@pytest.mark.asyncio
async def test_shard_shutdown(shard, mock_frame):
    """Test shard shutdown."""
    await shard.shutdown()
    assert shard._db is None
    assert shard._event_bus is None


@pytest.mark.asyncio
async def test_seed_default_rules(mock_frame):
    """Test seeding default rules when none exist."""
    mock_frame.database.fetch_one.return_value = {"cnt": 0}
    s = DeadlinesShard()
    await s.initialize(mock_frame)
    # execute calls: schema creation + seeding rules
    assert mock_frame.database.execute.call_count > len(DEFAULT_RULES)


# === Urgency Calculation Tests ===


def test_urgency_overdue():
    """Test urgency for past dates."""
    past = date.today() - timedelta(days=5)
    assert DeadlinesShard.calculate_urgency(past) == UrgencyLevel.OVERDUE


def test_urgency_critical():
    """Test urgency for 0-2 days."""
    today = date.today()
    assert DeadlinesShard.calculate_urgency(today) == UrgencyLevel.CRITICAL
    assert DeadlinesShard.calculate_urgency(today + timedelta(days=1)) == UrgencyLevel.CRITICAL
    assert DeadlinesShard.calculate_urgency(today + timedelta(days=2)) == UrgencyLevel.CRITICAL


def test_urgency_high():
    """Test urgency for 3-7 days."""
    future = date.today() + timedelta(days=5)
    assert DeadlinesShard.calculate_urgency(future) == UrgencyLevel.HIGH


def test_urgency_medium():
    """Test urgency for 8-14 days."""
    future = date.today() + timedelta(days=10)
    assert DeadlinesShard.calculate_urgency(future) == UrgencyLevel.MEDIUM


def test_urgency_low():
    """Test urgency for 15-30 days."""
    future = date.today() + timedelta(days=20)
    assert DeadlinesShard.calculate_urgency(future) == UrgencyLevel.LOW


def test_urgency_future():
    """Test urgency for 31+ days."""
    future = date.today() + timedelta(days=60)
    assert DeadlinesShard.calculate_urgency(future) == UrgencyLevel.FUTURE


# === Working Days Calculation ===


def test_add_working_days_zero():
    """Test adding zero working days."""
    d = date(2026, 3, 16)  # Monday
    assert DeadlinesShard.add_working_days(d, 0) == d


def test_add_working_days_forward():
    """Test adding working days skips weekends."""
    monday = date(2026, 3, 16)  # Monday
    result = DeadlinesShard.add_working_days(monday, 5)
    assert result == date(2026, 3, 23)  # Next Monday


def test_add_working_days_from_friday():
    """Test adding 1 working day from Friday goes to Monday."""
    friday = date(2026, 3, 20)
    result = DeadlinesShard.add_working_days(friday, 1)
    assert result == date(2026, 3, 23)  # Monday


def test_add_working_days_negative():
    """Test subtracting working days."""
    wednesday = date(2026, 3, 18)
    result = DeadlinesShard.add_working_days(wednesday, -1)
    assert result == date(2026, 3, 17)  # Tuesday


def test_calculate_deadline_from_rule_calendar_days():
    """Test calculating deadline with calendar days."""
    shard = DeadlinesShard()
    rule = DeadlineRule(id="r-1", name="Test", days_from_trigger=28, working_days_only=False)
    base = date(2026, 3, 1)
    result = shard.calculate_deadline_from_rule(rule, base)
    assert result == date(2026, 3, 29)


def test_calculate_deadline_from_rule_working_days():
    """Test calculating deadline with working days."""
    shard = DeadlinesShard()
    rule = DeadlineRule(id="r-1", name="Test", days_from_trigger=5, working_days_only=True)
    monday = date(2026, 3, 16)
    result = shard.calculate_deadline_from_rule(rule, monday)
    assert result == date(2026, 3, 23)  # 5 working days from Monday = next Monday


# === Deadline CRUD Tests ===


@pytest.mark.asyncio
async def test_create_deadline(shard, mock_frame):
    """Test creating a deadline."""
    future_date = date.today() + timedelta(days=14)
    now = datetime.utcnow()

    mock_frame.database.fetch_one.return_value = {
        "id": "dl-1",
        "title": "ET3 Response",
        "deadline_date": future_date,
        "deadline_time": None,
        "deadline_type": "response",
        "status": "pending",
        "urgency": "medium",
        "description": "",
        "case_type": "et",
        "case_reference": "6013156/2024",
        "source_document": "",
        "source_order_date": None,
        "rule_reference": "",
        "auto_calculated": False,
        "calculation_base_date": None,
        "calculation_days": None,
        "notes": "",
        "completed_at": None,
        "completed_by": "",
        "linked_document_ids": "[]",
        "created_at": now,
        "updated_at": now,
        "metadata": "{}",
    }

    dl = await shard.create_deadline(
        {
            "title": "ET3 Response",
            "deadline_date": future_date.isoformat(),
            "deadline_type": "response",
            "case_reference": "6013156/2024",
        }
    )

    assert dl.title == "ET3 Response"
    mock_frame.database.execute.assert_called()


@pytest.mark.asyncio
async def test_get_deadline(shard, mock_frame):
    """Test retrieving a deadline by ID."""
    future_date = date.today() + timedelta(days=7)
    mock_frame.database.fetch_one.return_value = {
        "id": "dl-1",
        "title": "Test Deadline",
        "deadline_date": future_date,
        "deadline_time": None,
        "deadline_type": "custom",
        "status": "pending",
        "urgency": "high",
        "description": "",
        "case_type": "et",
        "case_reference": "",
        "source_document": "",
        "source_order_date": None,
        "rule_reference": "",
        "auto_calculated": False,
        "calculation_base_date": None,
        "calculation_days": None,
        "notes": "",
        "completed_at": None,
        "completed_by": "",
        "linked_document_ids": "[]",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "metadata": "{}",
    }

    dl = await shard.get_deadline("dl-1")
    assert dl is not None
    assert dl.id == "dl-1"


@pytest.mark.asyncio
async def test_get_deadline_not_found(shard, mock_frame):
    """Test retrieving non-existent deadline."""
    mock_frame.database.fetch_one.return_value = None
    dl = await shard.get_deadline("nonexistent")
    assert dl is None


@pytest.mark.asyncio
async def test_list_deadlines(shard, mock_frame):
    """Test listing deadlines."""
    future_date = date.today() + timedelta(days=10)
    mock_frame.database.fetch_all.return_value = [
        {
            "id": "dl-1",
            "title": "Deadline A",
            "deadline_date": future_date,
            "deadline_time": None,
            "deadline_type": "custom",
            "status": "pending",
            "urgency": "medium",
            "description": "",
            "case_type": "et",
            "case_reference": "",
            "source_document": "",
            "source_order_date": None,
            "rule_reference": "",
            "auto_calculated": False,
            "calculation_base_date": None,
            "calculation_days": None,
            "notes": "",
            "completed_at": None,
            "completed_by": "",
            "linked_document_ids": "[]",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "metadata": "{}",
        },
    ]

    deadlines = await shard.list_deadlines()
    assert len(deadlines) == 1
    assert deadlines[0].title == "Deadline A"


@pytest.mark.asyncio
async def test_list_deadlines_with_filters(shard, mock_frame):
    """Test listing deadlines with filters."""
    mock_frame.database.fetch_all.return_value = []

    filters = DeadlineFilter(
        status=DeadlineStatus.PENDING,
        deadline_type=DeadlineType.FILING,
        case_type=CaseType.ET,
        urgency=UrgencyLevel.HIGH,
        search_text="appeal",
        show_completed=False,
    )
    deadlines = await shard.list_deadlines(filters=filters)
    assert deadlines == []


@pytest.mark.asyncio
async def test_delete_deadline(shard, mock_frame):
    """Test deleting a deadline."""
    result = await shard.delete_deadline("dl-1")
    assert result is True


@pytest.mark.asyncio
async def test_complete_deadline(shard, mock_frame):
    """Test completing a deadline."""
    future_date = date.today() + timedelta(days=5)
    mock_frame.database.fetch_one.return_value = {
        "id": "dl-1",
        "title": "Completed",
        "deadline_date": future_date,
        "deadline_time": None,
        "deadline_type": "custom",
        "status": "completed",
        "urgency": "high",
        "description": "",
        "case_type": "et",
        "case_reference": "",
        "source_document": "",
        "source_order_date": None,
        "rule_reference": "",
        "auto_calculated": False,
        "calculation_base_date": None,
        "calculation_days": None,
        "notes": "",
        "completed_at": datetime.utcnow(),
        "completed_by": "Alex",
        "linked_document_ids": "[]",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "metadata": "{}",
    }

    dl = await shard.complete_deadline("dl-1", "Alex")
    assert dl is not None
    mock_frame.database.execute.assert_called()
    mock_frame.get_service.return_value.emit.assert_called()


@pytest.mark.asyncio
async def test_extend_deadline(shard, mock_frame):
    """Test extending a deadline."""
    new_date = date.today() + timedelta(days=30)
    mock_frame.database.fetch_one.return_value = {
        "id": "dl-1",
        "title": "Extended",
        "deadline_date": new_date,
        "deadline_time": None,
        "deadline_type": "custom",
        "status": "extended",
        "urgency": "low",
        "description": "",
        "case_type": "et",
        "case_reference": "",
        "source_document": "",
        "source_order_date": None,
        "rule_reference": "",
        "auto_calculated": False,
        "calculation_base_date": None,
        "calculation_days": None,
        "notes": "",
        "completed_at": None,
        "completed_by": "",
        "linked_document_ids": "[]",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "metadata": "{}",
    }

    dl = await shard.extend_deadline("dl-1", new_date, "Judge granted extension")
    assert dl is not None


# === Breach Detection ===


@pytest.mark.asyncio
async def test_check_breaches(shard, mock_frame):
    """Test breach detection for overdue deadlines."""
    past_date = date.today() - timedelta(days=3)
    mock_frame.database.fetch_all.return_value = [
        {
            "id": "dl-1",
            "title": "Overdue Deadline",
            "deadline_date": past_date,
            "deadline_time": None,
            "deadline_type": "response",
            "status": "pending",
            "urgency": "overdue",
            "description": "",
            "case_type": "et",
            "case_reference": "",
            "source_document": "",
            "source_order_date": None,
            "rule_reference": "",
            "auto_calculated": False,
            "calculation_base_date": None,
            "calculation_days": None,
            "notes": "",
            "completed_at": None,
            "completed_by": "",
            "linked_document_ids": "[]",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "metadata": "{}",
        },
    ]

    breached = await shard.check_breaches()
    assert len(breached) == 1
    mock_frame.database.execute.assert_called()
    mock_frame.get_service.return_value.emit.assert_called()


@pytest.mark.asyncio
async def test_check_breaches_none(shard, mock_frame):
    """Test breach detection when no overdue deadlines."""
    mock_frame.database.fetch_all.return_value = []
    breached = await shard.check_breaches()
    assert len(breached) == 0


# === Stats ===


@pytest.mark.asyncio
async def test_get_stats(shard, mock_frame):
    """Test getting deadline statistics."""
    mock_frame.database.fetch_all.return_value = [
        {"status": "pending", "urgency": "high", "case_type": "et", "cnt": 5},
        {"status": "completed", "urgency": "future", "case_type": "et", "cnt": 3},
        {"status": "breached", "urgency": "overdue", "case_type": "eat", "cnt": 1},
    ]
    mock_frame.database.fetch_one.return_value = {
        "id": "dl-next",
        "title": "Next DL",
        "deadline_date": date.today(),
        "urgency": "critical",
    }

    stats = await shard.get_stats()
    assert stats.total == 9
    assert stats.pending == 5
    assert stats.breached == 1
    assert stats.completed == 3
    assert stats.next_deadline is not None


# === ICS Export ===


@pytest.mark.asyncio
async def test_export_ics(shard, mock_frame):
    """Test ICS calendar export."""
    future_date = date.today() + timedelta(days=7)
    mock_frame.database.fetch_all.return_value = [
        {
            "id": "dl-1",
            "title": "Hearing",
            "deadline_date": future_date,
            "deadline_time": None,
            "deadline_type": "hearing",
            "status": "pending",
            "urgency": "high",
            "description": "Final hearing",
            "case_type": "et",
            "case_reference": "",
            "source_document": "",
            "source_order_date": None,
            "rule_reference": "",
            "auto_calculated": False,
            "calculation_base_date": None,
            "calculation_days": None,
            "notes": "",
            "completed_at": None,
            "completed_by": "",
            "linked_document_ids": "[]",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "metadata": "{}",
        },
    ]

    ics = await shard.export_ics()
    assert "BEGIN:VCALENDAR" in ics
    assert "BEGIN:VEVENT" in ics
    assert "Hearing" in ics
    assert "END:VCALENDAR" in ics


# === Rules ===


@pytest.mark.asyncio
async def test_list_rules(shard, mock_frame):
    """Test listing deadline rules."""
    mock_frame.database.fetch_all.return_value = [
        {
            "id": "r-1",
            "name": "ET Response",
            "description": "28 days",
            "case_type": "et",
            "deadline_type": "response",
            "days_from_trigger": 28,
            "trigger_event": "ET1 served",
            "working_days_only": False,
            "created_at": datetime.utcnow(),
        },
    ]

    rules = await shard.list_rules()
    assert len(rules) == 1
    assert rules[0].name == "ET Response"


@pytest.mark.asyncio
async def test_create_rule(shard, mock_frame):
    """Test creating a deadline rule."""
    rule = await shard.create_rule(
        {
            "name": "Custom Rule",
            "days_from_trigger": 14,
            "working_days_only": True,
        }
    )
    assert rule.name == "Custom Rule"
    mock_frame.database.execute.assert_called()


# === Helper Tests ===


def test_parse_json_field_none():
    """Test _parse_json_field with None."""
    assert _parse_json_field(None) == []


def test_parse_json_field_string():
    """Test _parse_json_field with JSON string."""
    assert _parse_json_field('["a","b"]') == ["a", "b"]


def test_parse_json_field_invalid():
    """Test _parse_json_field with invalid JSON."""
    assert _parse_json_field("invalid") == []


# === Model Tests ===


def test_deadline_defaults():
    """Test Deadline dataclass defaults."""
    dl = Deadline(id="dl-1", title="Test", deadline_date=date.today())
    assert dl.status == DeadlineStatus.PENDING
    assert dl.deadline_type == DeadlineType.CUSTOM
    assert dl.urgency == UrgencyLevel.FUTURE
    assert dl.case_type == CaseType.ET
    assert dl.linked_document_ids == []


def test_deadline_rule_defaults():
    """Test DeadlineRule defaults."""
    rule = DeadlineRule(id="r-1", name="Test")
    assert rule.days_from_trigger == 14
    assert rule.working_days_only is True
    assert rule.case_type == CaseType.ET


def test_deadline_filter_defaults():
    """Test DeadlineFilter defaults."""
    f = DeadlineFilter()
    assert f.status is None
    assert f.show_completed is False


def test_deadline_stats_defaults():
    """Test DeadlineStats defaults."""
    stats = DeadlineStats()
    assert stats.total == 0
    assert stats.pending == 0
    assert stats.breached == 0
    assert stats.by_urgency == {}


def test_default_rules_populated():
    """Test that DEFAULT_RULES constant has expected rules."""
    assert len(DEFAULT_RULES) >= 7
    rule_names = [r["name"] for r in DEFAULT_RULES]
    assert any("ET3" in n for n in rule_names)
    assert any("EAT" in n for n in rule_names)
    assert any("Appeal" in n for n in rule_names)


def test_urgency_boundaries():
    """Test urgency level boundary conditions."""
    today = date.today()
    # Exact boundary: 2 days = critical
    assert DeadlinesShard.calculate_urgency(today + timedelta(days=2)) == UrgencyLevel.CRITICAL
    # 3 days = high
    assert DeadlinesShard.calculate_urgency(today + timedelta(days=3)) == UrgencyLevel.HIGH
    # 7 days = high
    assert DeadlinesShard.calculate_urgency(today + timedelta(days=7)) == UrgencyLevel.HIGH
    # 8 days = medium
    assert DeadlinesShard.calculate_urgency(today + timedelta(days=8)) == UrgencyLevel.MEDIUM
    # 14 days = medium
    assert DeadlinesShard.calculate_urgency(today + timedelta(days=14)) == UrgencyLevel.MEDIUM
    # 15 days = low
    assert DeadlinesShard.calculate_urgency(today + timedelta(days=15)) == UrgencyLevel.LOW
    # 30 days = low
    assert DeadlinesShard.calculate_urgency(today + timedelta(days=30)) == UrgencyLevel.LOW
    # 31 days = future
    assert DeadlinesShard.calculate_urgency(today + timedelta(days=31)) == UrgencyLevel.FUTURE
