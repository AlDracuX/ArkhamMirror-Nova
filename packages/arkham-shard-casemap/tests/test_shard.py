"""Tests for casemap shard implementation."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arkham_shard_casemap.models import (
    CLAIM_ELEMENT_TEMPLATES,
    BurdenOfProof,
    ClaimType,
    ElementStatus,
    EvidenceLink,
    EvidenceStrength,
    LegalElement,
    LegalTheory,
    StrengthAssessment,
    TheoryFilter,
    TheoryStatus,
)
from arkham_shard_casemap.shard import CasemapShard, _parse_json_field


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
    """Create an initialized CasemapShard instance."""
    s = CasemapShard()
    await s.initialize(mock_frame)
    return s


# === Initialization Tests ===


@pytest.mark.asyncio
async def test_shard_initialization(mock_frame):
    """Test shard initializes with correct name, version, and services."""
    s = CasemapShard()
    assert s.name == "casemap"
    assert s.version == "0.1.0"

    await s.initialize(mock_frame)
    assert s._db is mock_frame.database
    assert s._event_bus is not None
    mock_frame.database.execute.assert_called()


@pytest.mark.asyncio
async def test_shard_shutdown(shard, mock_frame):
    """Test shard shutdown clears references."""
    await shard.shutdown()
    assert shard._db is None
    assert shard._event_bus is None


@pytest.mark.asyncio
async def test_get_routes(shard):
    """Test get_routes returns the router."""
    routes = shard.get_routes()
    assert routes is not None


# === Theory CRUD Tests ===


@pytest.mark.asyncio
async def test_create_theory(shard, mock_frame):
    """Test creating a legal theory."""
    now = datetime.utcnow()
    mock_frame.database.fetch_one.return_value = {
        "id": "theory-123",
        "title": "Unfair Dismissal Claim",
        "claim_type": "unfair_dismissal",
        "description": "Test theory",
        "statutory_basis": "ERA 1996",
        "respondent_ids": "[]",
        "status": "active",
        "overall_strength": 0,
        "notes": "",
        "created_at": now,
        "updated_at": now,
        "metadata": "{}",
    }

    theory = await shard.create_theory(
        {
            "title": "Unfair Dismissal Claim",
            "claim_type": "unfair_dismissal",
            "description": "Test theory",
            "statutory_basis": "ERA 1996",
        }
    )

    assert theory.title == "Unfair Dismissal Claim"
    assert theory.claim_type == "unfair_dismissal"
    mock_frame.database.execute.assert_called()
    mock_frame.get_service.return_value.emit.assert_called()


@pytest.mark.asyncio
async def test_get_theory(shard, mock_frame):
    """Test retrieving a theory by ID."""
    now = datetime.utcnow()
    mock_frame.database.fetch_one.return_value = {
        "id": "theory-123",
        "title": "Test Theory",
        "claim_type": "custom",
        "description": "",
        "statutory_basis": "",
        "respondent_ids": "[]",
        "status": "active",
        "overall_strength": 0,
        "notes": "",
        "created_at": now,
        "updated_at": now,
        "metadata": "{}",
    }

    theory = await shard.get_theory("theory-123")
    assert theory is not None
    assert theory.id == "theory-123"
    assert theory.title == "Test Theory"


@pytest.mark.asyncio
async def test_get_theory_not_found(shard, mock_frame):
    """Test retrieving non-existent theory returns None."""
    mock_frame.database.fetch_one.return_value = None
    theory = await shard.get_theory("nonexistent")
    assert theory is None


@pytest.mark.asyncio
async def test_list_theories(shard, mock_frame):
    """Test listing theories."""
    now = datetime.utcnow()
    mock_frame.database.fetch_all.return_value = [
        {
            "id": "t-1",
            "title": "Theory A",
            "claim_type": "unfair_dismissal",
            "description": "",
            "statutory_basis": "",
            "respondent_ids": "[]",
            "status": "active",
            "overall_strength": 50,
            "notes": "",
            "created_at": now,
            "updated_at": now,
            "metadata": "{}",
        },
        {
            "id": "t-2",
            "title": "Theory B",
            "claim_type": "discrimination",
            "description": "",
            "statutory_basis": "",
            "respondent_ids": "[]",
            "status": "active",
            "overall_strength": 75,
            "notes": "",
            "created_at": now,
            "updated_at": now,
            "metadata": "{}",
        },
    ]

    theories = await shard.list_theories(limit=100, offset=0)
    assert len(theories) == 2
    assert theories[0].title == "Theory A"
    assert theories[1].title == "Theory B"


@pytest.mark.asyncio
async def test_list_theories_with_filter(shard, mock_frame):
    """Test listing theories with filters."""
    mock_frame.database.fetch_all.return_value = []

    filters = TheoryFilter(
        claim_type=ClaimType.UNFAIR_DISMISSAL,
        status=TheoryStatus.ACTIVE,
        search_text="test",
        min_strength=50,
    )
    theories = await shard.list_theories(filters=filters, limit=10, offset=0)
    assert theories == []
    mock_frame.database.fetch_all.assert_called()


@pytest.mark.asyncio
async def test_count_theories(shard, mock_frame):
    """Test counting theories."""
    mock_frame.database.fetch_one.return_value = {"cnt": 5}
    count = await shard.count_theories()
    assert count == 5


@pytest.mark.asyncio
async def test_count_theories_empty(shard, mock_frame):
    """Test counting theories when none exist."""
    mock_frame.database.fetch_one.return_value = None
    count = await shard.count_theories()
    assert count == 0


@pytest.mark.asyncio
async def test_update_theory(shard, mock_frame):
    """Test updating a theory."""
    now = datetime.utcnow()
    mock_frame.database.fetch_one.return_value = {
        "id": "theory-123",
        "title": "Updated Title",
        "claim_type": "custom",
        "description": "Updated",
        "statutory_basis": "",
        "respondent_ids": "[]",
        "status": "active",
        "overall_strength": 0,
        "notes": "",
        "created_at": now,
        "updated_at": now,
        "metadata": "{}",
    }

    theory = await shard.update_theory("theory-123", {"title": "Updated Title", "description": "Updated"})
    assert theory is not None
    assert theory.title == "Updated Title"
    mock_frame.database.execute.assert_called()
    mock_frame.get_service.return_value.emit.assert_called()


@pytest.mark.asyncio
async def test_delete_theory(shard, mock_frame):
    """Test deleting a theory."""
    result = await shard.delete_theory("theory-123")
    assert result is True
    mock_frame.database.execute.assert_called()
    mock_frame.get_service.return_value.emit.assert_called()


# === Element CRUD Tests ===


@pytest.mark.asyncio
async def test_create_element(shard, mock_frame):
    """Test creating a legal element."""
    now = datetime.utcnow()
    mock_frame.database.fetch_one.side_effect = [
        {"next_ord": 1},  # auto-increment
        {  # get_element result
            "id": "elem-1",
            "theory_id": "theory-123",
            "title": "Employee status",
            "description": "",
            "burden": "claimant",
            "status": "unproven",
            "required": True,
            "statutory_reference": "ERA 1996 s.108",
            "notes": "",
            "display_order": 1,
            "created_at": now,
            "updated_at": now,
        },
    ]

    elem = await shard.create_element(
        "theory-123",
        {
            "title": "Employee status",
            "burden": "claimant",
            "statutory_reference": "ERA 1996 s.108",
        },
    )

    assert elem.title == "Employee status"
    assert elem.burden == "claimant"


@pytest.mark.asyncio
async def test_list_elements(shard, mock_frame):
    """Test listing elements for a theory."""
    now = datetime.utcnow()
    mock_frame.database.fetch_all.return_value = [
        {
            "id": "elem-1",
            "theory_id": "theory-123",
            "title": "Element A",
            "description": "",
            "burden": "claimant",
            "status": "unproven",
            "required": True,
            "statutory_reference": "",
            "notes": "",
            "display_order": 1,
            "created_at": now,
            "updated_at": now,
        },
    ]

    elements = await shard.list_elements("theory-123")
    assert len(elements) == 1
    assert elements[0].title == "Element A"


@pytest.mark.asyncio
async def test_delete_element(shard, mock_frame):
    """Test deleting an element."""
    result = await shard.delete_element("elem-1")
    assert result is True


# === Evidence Link Tests ===


@pytest.mark.asyncio
async def test_link_evidence(shard, mock_frame):
    """Test linking evidence to an element."""
    link = await shard.link_evidence(
        "elem-1",
        {
            "document_id": "doc-1",
            "description": "Key contract",
            "strength": "strong",
            "supports_element": True,
        },
    )

    assert link.element_id == "elem-1"
    assert link.document_id == "doc-1"
    assert link.strength == "strong"
    assert link.supports_element is True
    mock_frame.get_service.return_value.emit.assert_called()


@pytest.mark.asyncio
async def test_list_evidence(shard, mock_frame):
    """Test listing evidence for an element."""
    now = datetime.utcnow()
    mock_frame.database.fetch_all.return_value = [
        {
            "id": "ev-1",
            "element_id": "elem-1",
            "document_id": "doc-1",
            "witness_id": None,
            "description": "Contract",
            "strength": "strong",
            "source_reference": "Page 3",
            "supports_element": True,
            "notes": "",
            "created_at": now,
        },
    ]

    evidence = await shard.list_evidence("elem-1")
    assert len(evidence) == 1
    assert evidence[0].description == "Contract"


@pytest.mark.asyncio
async def test_delete_evidence(shard, mock_frame):
    """Test deleting evidence link."""
    result = await shard.delete_evidence("ev-1")
    assert result is True


# === Strength Assessment Tests ===


@pytest.mark.asyncio
async def test_assess_strength_no_elements(shard, mock_frame):
    """Test strength assessment with no elements."""
    mock_frame.database.fetch_all.return_value = []

    assessment = await shard.assess_strength("theory-123")
    assert assessment.theory_id == "theory-123"
    assert assessment.total_elements == 0
    assert assessment.overall_score == 0


@pytest.mark.asyncio
async def test_assess_strength_proven_elements(shard, mock_frame):
    """Test strength assessment with proven elements."""
    now = datetime.utcnow()

    # list_elements returns elements
    mock_frame.database.fetch_all.side_effect = [
        [
            {
                "id": "elem-1",
                "theory_id": "t-1",
                "title": "Element 1",
                "burden": "claimant",
                "status": "proven",
                "required": True,
                "description": "",
                "statutory_reference": "",
                "notes": "",
                "display_order": 1,
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": "elem-2",
                "theory_id": "t-1",
                "title": "Element 2",
                "burden": "claimant",
                "status": "contested",
                "required": True,
                "description": "",
                "statutory_reference": "",
                "notes": "",
                "display_order": 2,
                "created_at": now,
                "updated_at": now,
            },
        ],
        # list_evidence for elem-1: one supporting
        [
            {
                "id": "ev-1",
                "element_id": "elem-1",
                "document_id": "d1",
                "witness_id": None,
                "description": "",
                "strength": "strong",
                "source_reference": "",
                "supports_element": True,
                "notes": "",
                "created_at": now,
            },
        ],
        # list_evidence for elem-2: no evidence
        [],
    ]

    assessment = await shard.assess_strength("t-1")
    assert assessment.total_elements == 2
    assert assessment.proven_count == 1
    assert assessment.contested_count == 1
    assert assessment.overall_score == 75  # (100 + 50) / 2


# === Gap Identification ===


@pytest.mark.asyncio
async def test_identify_gaps(shard, mock_frame):
    """Test identifying evidence gaps for required elements."""
    now = datetime.utcnow()

    mock_frame.database.fetch_all.side_effect = [
        # list_elements
        [
            {
                "id": "elem-1",
                "theory_id": "t-1",
                "title": "Required Element",
                "burden": "claimant",
                "status": "unproven",
                "required": True,
                "description": "",
                "statutory_reference": "ERA s.108",
                "notes": "",
                "display_order": 1,
                "created_at": now,
                "updated_at": now,
            },
        ],
        # list_evidence for elem-1: empty (gap)
        [],
    ]

    gaps = await shard.identify_gaps("t-1")
    assert len(gaps) == 1
    assert gaps[0]["element_id"] == "elem-1"
    assert gaps[0]["title"] == "Required Element"
    mock_frame.get_service.return_value.emit.assert_called()


@pytest.mark.asyncio
async def test_identify_gaps_no_gaps(shard, mock_frame):
    """Test gap identification when all elements have evidence."""
    now = datetime.utcnow()

    mock_frame.database.fetch_all.side_effect = [
        [
            {
                "id": "elem-1",
                "theory_id": "t-1",
                "title": "Element",
                "burden": "claimant",
                "status": "proven",
                "required": True,
                "description": "",
                "statutory_reference": "",
                "notes": "",
                "display_order": 1,
                "created_at": now,
                "updated_at": now,
            },
        ],
        [
            {
                "id": "ev-1",
                "element_id": "elem-1",
                "document_id": "d1",
                "witness_id": None,
                "description": "",
                "strength": "strong",
                "source_reference": "",
                "supports_element": True,
                "notes": "",
                "created_at": now,
            },
        ],
    ]

    gaps = await shard.identify_gaps("t-1")
    assert len(gaps) == 0


# === Seed Templates ===


@pytest.mark.asyncio
async def test_seed_elements_unfair_dismissal(shard, mock_frame):
    """Test seeding elements from unfair dismissal template."""
    now = datetime.utcnow()
    template = CLAIM_ELEMENT_TEMPLATES["unfair_dismissal"]

    # Each create_element call does: fetch_one (next_ord) + execute + fetch_one (get_element)
    fetch_one_results = []
    for i, tmpl in enumerate(template):
        fetch_one_results.append({"next_ord": i + 1})
        fetch_one_results.append(
            {
                "id": f"elem-{i}",
                "theory_id": "t-1",
                "title": tmpl["title"],
                "burden": tmpl["burden"],
                "status": "unproven",
                "required": tmpl.get("required", True),
                "description": "",
                "statutory_reference": tmpl.get("statutory_reference", ""),
                "notes": "",
                "display_order": i + 1,
                "created_at": now,
                "updated_at": now,
            }
        )

    mock_frame.database.fetch_one.side_effect = fetch_one_results

    elements = await shard.seed_elements("t-1", "unfair_dismissal")
    assert len(elements) == len(template)


@pytest.mark.asyncio
async def test_seed_elements_unknown_type(shard, mock_frame):
    """Test seeding with unknown claim type returns empty list."""
    elements = await shard.seed_elements("t-1", "nonexistent_type")
    assert elements == []


# === Helper Function Tests ===


def test_parse_json_field_none():
    """Test _parse_json_field with None."""
    assert _parse_json_field(None) == []
    assert _parse_json_field(None, {}) == {}


def test_parse_json_field_list():
    """Test _parse_json_field with list."""
    assert _parse_json_field([1, 2, 3]) == [1, 2, 3]


def test_parse_json_field_dict():
    """Test _parse_json_field with dict."""
    assert _parse_json_field({"key": "val"}) == {"key": "val"}


def test_parse_json_field_json_string():
    """Test _parse_json_field with JSON string."""
    assert _parse_json_field('["a","b"]') == ["a", "b"]


def test_parse_json_field_invalid_json():
    """Test _parse_json_field with invalid JSON string."""
    assert _parse_json_field("not json") == []
    assert _parse_json_field("not json", {}) == {}


# === Model Tests ===


def test_legal_theory_defaults():
    """Test LegalTheory default values."""
    theory = LegalTheory(id="t-1", title="Test", claim_type=ClaimType.CUSTOM)
    assert theory.status == TheoryStatus.ACTIVE
    assert theory.overall_strength == 0
    assert theory.respondent_ids == []
    assert theory.metadata == {}


def test_legal_element_defaults():
    """Test LegalElement default values."""
    elem = LegalElement(id="e-1", theory_id="t-1", title="Test")
    assert elem.burden == BurdenOfProof.CLAIMANT
    assert elem.status == ElementStatus.UNPROVEN
    assert elem.required is True
    assert elem.display_order == 0


def test_evidence_link_defaults():
    """Test EvidenceLink default values."""
    link = EvidenceLink(id="ev-1", element_id="e-1")
    assert link.document_id is None
    assert link.witness_id is None
    assert link.strength == EvidenceStrength.NEUTRAL
    assert link.supports_element is True


def test_strength_assessment_defaults():
    """Test StrengthAssessment default values."""
    sa = StrengthAssessment(theory_id="t-1")
    assert sa.total_elements == 0
    assert sa.proven_count == 0
    assert sa.overall_score == 0
    assert sa.gaps == []
    assert sa.weaknesses == []


def test_claim_type_enum_values():
    """Test ClaimType enum has expected values."""
    assert ClaimType.UNFAIR_DISMISSAL.value == "unfair_dismissal"
    assert ClaimType.DISCRIMINATION.value == "discrimination"
    assert ClaimType.WHISTLEBLOWING.value == "whistleblowing"


def test_claim_element_templates_exist():
    """Test that claim element templates are populated."""
    assert "unfair_dismissal" in CLAIM_ELEMENT_TEMPLATES
    assert "constructive_dismissal" in CLAIM_ELEMENT_TEMPLATES
    assert "discrimination" in CLAIM_ELEMENT_TEMPLATES
    assert "whistleblowing" in CLAIM_ELEMENT_TEMPLATES
    assert "harassment" in CLAIM_ELEMENT_TEMPLATES
    assert "victimisation" in CLAIM_ELEMENT_TEMPLATES
    # Each has elements
    for claim_type, elements in CLAIM_ELEMENT_TEMPLATES.items():
        assert len(elements) >= 3, f"{claim_type} should have at least 3 elements"


def test_theory_filter_defaults():
    """Test TheoryFilter default values."""
    f = TheoryFilter()
    assert f.claim_type is None
    assert f.status is None
    assert f.search_text is None
    assert f.min_strength is None
