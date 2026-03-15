"""Tests for deadlines shard API endpoints."""

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from arkham_shard_deadlines.api import init_api, router
from arkham_shard_deadlines.models import (
    Deadline,
    DeadlineRule,
    DeadlineStats,
    DeadlineStatus,
    DeadlineType,
    UrgencyLevel,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def mock_shard():
    """Create a mock DeadlinesShard."""
    shard = MagicMock()
    shard.create_deadline = AsyncMock()
    shard.get_deadline = AsyncMock()
    shard.list_deadlines = AsyncMock()
    shard.count_upcoming = AsyncMock()
    shard.get_upcoming = AsyncMock()
    shard.update_deadline = AsyncMock()
    shard.delete_deadline = AsyncMock()
    shard.complete_deadline = AsyncMock()
    shard.extend_deadline = AsyncMock()
    shard.check_breaches = AsyncMock()
    shard.get_stats = AsyncMock()
    shard.export_ics = AsyncMock()
    shard.list_rules = AsyncMock()
    shard.create_rule = AsyncMock()
    shard.calculate_from_rule = AsyncMock()
    return shard


@pytest.fixture
def sample_deadline():
    """Create a sample Deadline."""
    return Deadline(
        id="dl-123",
        title="ET3 Response",
        deadline_date=date.today() + timedelta(days=14),
        deadline_type=DeadlineType.RESPONSE,
        status=DeadlineStatus.PENDING,
        urgency=UrgencyLevel.MEDIUM,
        case_type="et",
        case_reference="6013156/2024",
        description="Respond to ET1 claim",
    )


@pytest.fixture
def client(mock_shard):
    """Create test client with mocked shard."""
    init_api(shard=mock_shard, event_bus=MagicMock())
    app = FastAPI()
    app.include_router(router)
    yield TestClient(app)
    init_api(shard=None, event_bus=None)


def test_list_deadlines(client, mock_shard, sample_deadline):
    """Test GET /api/deadlines/."""
    mock_shard.list_deadlines.return_value = [sample_deadline]

    response = client.get("/api/deadlines/")
    assert response.status_code == 200
    data = response.json()
    assert len(data["deadlines"]) == 1
    assert data["deadlines"][0]["title"] == "ET3 Response"
    assert "days_remaining" in data["deadlines"][0]


def test_count_upcoming(client, mock_shard):
    """Test GET /api/deadlines/upcoming/count."""
    mock_shard.count_upcoming.return_value = 7

    response = client.get("/api/deadlines/upcoming/count")
    assert response.status_code == 200
    assert response.json()["count"] == 7


def test_get_upcoming(client, mock_shard, sample_deadline):
    """Test GET /api/deadlines/upcoming."""
    mock_shard.get_upcoming.return_value = [sample_deadline]

    response = client.get("/api/deadlines/upcoming?days=30")
    assert response.status_code == 200
    assert len(response.json()["deadlines"]) == 1


def test_create_deadline(client, mock_shard, sample_deadline):
    """Test POST /api/deadlines/."""
    mock_shard.create_deadline.return_value = sample_deadline

    response = client.post(
        "/api/deadlines/",
        json={
            "title": "ET3 Response",
            "deadline_date": (date.today() + timedelta(days=14)).isoformat(),
            "deadline_type": "response",
        },
    )
    assert response.status_code == 200
    assert response.json()["title"] == "ET3 Response"


def test_get_stats(client, mock_shard):
    """Test GET /api/deadlines/stats."""
    mock_shard.get_stats.return_value = DeadlineStats(
        total=10,
        pending=5,
        breached=1,
        completed=4,
        by_urgency={"high": 3, "medium": 2},
        by_case_type={"et": 8, "eat": 2},
        next_deadline={"id": "dl-1", "title": "Next", "deadline_date": "2026-04-01", "urgency": "high"},
    )

    response = client.get("/api/deadlines/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 10
    assert data["pending"] == 5
    assert data["next_deadline"]["title"] == "Next"


def test_export_ics(client, mock_shard):
    """Test GET /api/deadlines/export/ics."""
    mock_shard.export_ics.return_value = "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR"

    response = client.get("/api/deadlines/export/ics")
    assert response.status_code == 200
    assert "BEGIN:VCALENDAR" in response.text


def test_list_rules(client, mock_shard):
    """Test GET /api/deadlines/rules."""
    mock_shard.list_rules.return_value = [
        DeadlineRule(id="r-1", name="ET Response", days_from_trigger=28),
    ]

    response = client.get("/api/deadlines/rules")
    assert response.status_code == 200
    assert len(response.json()["rules"]) == 1


def test_create_rule(client, mock_shard):
    """Test POST /api/deadlines/rules."""
    mock_shard.create_rule.return_value = DeadlineRule(id="r-new", name="Custom Rule")

    response = client.post(
        "/api/deadlines/rules",
        json={
            "name": "Custom Rule",
            "days_from_trigger": 14,
            "working_days_only": True,
        },
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Custom Rule"


def test_calculate_from_rule(client, mock_shard):
    """Test POST /api/deadlines/calculate."""
    mock_shard.calculate_from_rule.return_value = {
        "rule_name": "ET Response",
        "base_date": "2026-03-15",
        "calculated_date": "2026-04-12",
        "days": 28,
        "working_days_only": False,
        "urgency": "low",
    }

    response = client.post(
        "/api/deadlines/calculate",
        json={
            "rule_id": "r-1",
            "base_date": "2026-03-15",
        },
    )
    assert response.status_code == 200
    assert response.json()["calculated_date"] == "2026-04-12"


def test_check_breaches(client, mock_shard, sample_deadline):
    """Test POST /api/deadlines/check-breaches."""
    mock_shard.check_breaches.return_value = [sample_deadline]

    response = client.post("/api/deadlines/check-breaches")
    assert response.status_code == 200
    data = response.json()
    assert data["breached_count"] == 1


def test_get_deadline(client, mock_shard, sample_deadline):
    """Test GET /api/deadlines/{deadline_id}."""
    mock_shard.get_deadline.return_value = sample_deadline

    response = client.get("/api/deadlines/dl-123")
    assert response.status_code == 200
    assert response.json()["id"] == "dl-123"


def test_get_deadline_not_found(client, mock_shard):
    """Test GET /api/deadlines/{deadline_id} not found."""
    mock_shard.get_deadline.return_value = None

    response = client.get("/api/deadlines/nonexistent")
    assert response.status_code == 404


def test_update_deadline(client, mock_shard, sample_deadline):
    """Test PUT /api/deadlines/{deadline_id}."""
    sample_deadline.title = "Updated"
    mock_shard.update_deadline.return_value = sample_deadline

    response = client.put("/api/deadlines/dl-123", json={"title": "Updated"})
    assert response.status_code == 200
    assert response.json()["title"] == "Updated"


def test_update_deadline_not_found(client, mock_shard):
    """Test PUT /api/deadlines/{deadline_id} not found."""
    mock_shard.update_deadline.return_value = None

    response = client.put("/api/deadlines/nonexistent", json={"title": "X"})
    assert response.status_code == 404


def test_delete_deadline(client, mock_shard):
    """Test DELETE /api/deadlines/{deadline_id}."""
    response = client.delete("/api/deadlines/dl-123")
    assert response.status_code == 200
    assert response.json()["deleted"] is True


def test_complete_deadline(client, mock_shard, sample_deadline):
    """Test POST /api/deadlines/{deadline_id}/complete."""
    mock_shard.complete_deadline.return_value = sample_deadline

    response = client.post("/api/deadlines/dl-123/complete", json={"completed_by": "Alex"})
    assert response.status_code == 200


def test_extend_deadline(client, mock_shard, sample_deadline):
    """Test POST /api/deadlines/{deadline_id}/extend."""
    mock_shard.extend_deadline.return_value = sample_deadline

    new_date = (date.today() + timedelta(days=30)).isoformat()
    response = client.post(
        "/api/deadlines/dl-123/extend",
        json={
            "new_date": new_date,
            "reason": "Judge granted extension",
        },
    )
    assert response.status_code == 200
