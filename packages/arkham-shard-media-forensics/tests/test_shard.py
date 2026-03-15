"""Tests for media-forensics shard implementation."""

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arkham_shard_media_forensics.models import (
    AnalysisStats,
    AnalyzeRequest,
    CountResponse,
    ELAAssessment,
    ELARequest,
    ELAResult,
    HashType,
    IntegrityStatus,
    MediaAnalysis,
    SimilarImage,
    SimilarSearchRequest,
    SunPositionRequest,
    SunVerification,
    SunVerificationStatus,
)
from arkham_shard_media_forensics.shard import MediaForensicsShard, _make_json_safe


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
    """Create an initialized MediaForensicsShard instance."""
    s = MediaForensicsShard()
    await s.initialize(mock_frame)
    return s


# === Initialization Tests ===


@pytest.mark.asyncio
async def test_shard_initialization(mock_frame):
    """Test shard initializes with correct name and version."""
    s = MediaForensicsShard()
    assert s.name == "media-forensics"
    assert s.version == "0.1.0"

    await s.initialize(mock_frame)
    assert s._db is mock_frame.database
    mock_frame.database.execute.assert_called()


@pytest.mark.asyncio
async def test_shard_shutdown(shard, mock_frame):
    """Test shard shutdown clears services."""
    await shard.shutdown()
    assert shard.exif_extractor is None
    assert shard.hash_service is None
    assert shard.c2pa_parser is None
    assert shard.ela_analyzer is None
    assert shard.sun_position is None


@pytest.mark.asyncio
async def test_get_routes(shard):
    """Test get_routes returns the router."""
    routes = shard.get_routes()
    assert routes is not None


# === Analysis Retrieval Tests ===


@pytest.mark.asyncio
async def test_get_analysis(shard, mock_frame):
    """Test retrieving an analysis by ID."""
    mock_frame.database.fetch_one.return_value = {
        "id": "a-1",
        "document_id": "doc-1",
        "tenant_id": None,
        "filename": "photo.jpg",
        "file_path": "/tmp/photo.jpg",
        "file_type": "jpeg",
        "file_size": 1024,
        "width": 800,
        "height": 600,
        "sha256": "abc123",
        "md5": "def456",
        "phash": "0011001100110011",
        "dhash": None,
        "ahash": None,
        "exif_data": '{"Make": "Canon"}',
        "camera_make": "Canon",
        "camera_model": "EOS R5",
        "software": None,
        "datetime_original": "2026-01-15 10:30:00",
        "datetime_digitized": None,
        "datetime_modified": None,
        "gps_latitude": 51.5074,
        "gps_longitude": -0.1278,
        "gps_altitude": None,
        "c2pa_data": "{}",
        "has_c2pa": 0,
        "c2pa_signer": None,
        "c2pa_timestamp": None,
        "warnings": "[]",
        "anomalies": "[]",
        "integrity_status": "unverified",
        "confidence_score": 0.5,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    analysis = await shard.get_analysis("a-1")
    assert analysis is not None
    assert analysis["id"] == "a-1"


@pytest.mark.asyncio
async def test_get_analysis_not_found(shard, mock_frame):
    """Test retrieving non-existent analysis."""
    mock_frame.database.fetch_one.return_value = None
    analysis = await shard.get_analysis("nonexistent")
    assert analysis is None


@pytest.mark.asyncio
async def test_get_analysis_no_db(shard):
    """Test get_analysis when database unavailable."""
    shard._db = None
    result = await shard.get_analysis("a-1")
    assert result is None


@pytest.mark.asyncio
async def test_get_analysis_by_document(shard, mock_frame):
    """Test retrieving analysis by document ID."""
    mock_frame.database.fetch_one.return_value = {
        "id": "a-1",
        "document_id": "doc-1",
        "tenant_id": None,
        "filename": "photo.jpg",
        "file_path": None,
        "file_type": "jpeg",
        "file_size": 1024,
        "width": 800,
        "height": 600,
        "sha256": None,
        "md5": None,
        "phash": None,
        "dhash": None,
        "ahash": None,
        "exif_data": "{}",
        "camera_make": None,
        "camera_model": None,
        "software": None,
        "datetime_original": None,
        "datetime_digitized": None,
        "datetime_modified": None,
        "gps_latitude": None,
        "gps_longitude": None,
        "gps_altitude": None,
        "c2pa_data": "{}",
        "has_c2pa": 0,
        "c2pa_signer": None,
        "c2pa_timestamp": None,
        "warnings": "[]",
        "anomalies": "[]",
        "integrity_status": "unknown",
        "confidence_score": 0.0,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    analysis = await shard.get_analysis_by_document("doc-1")
    assert analysis is not None


@pytest.mark.asyncio
async def test_get_analysis_by_document_not_found(shard, mock_frame):
    """Test retrieving analysis by non-existent document ID."""
    mock_frame.database.fetch_one.return_value = None
    analysis = await shard.get_analysis_by_document("nonexistent")
    assert analysis is None


# === List and Count Tests ===


@pytest.mark.asyncio
async def test_list_analyses(shard, mock_frame):
    """Test listing analyses."""
    mock_frame.database.fetch_all.return_value = [
        {
            "id": "a-1",
            "document_id": "doc-1",
            "tenant_id": None,
            "filename": "photo1.jpg",
            "file_path": None,
            "file_type": "jpeg",
            "file_size": 1024,
            "width": 800,
            "height": 600,
            "sha256": None,
            "md5": None,
            "phash": None,
            "dhash": None,
            "ahash": None,
            "exif_data": "{}",
            "camera_make": None,
            "camera_model": None,
            "software": None,
            "datetime_original": None,
            "datetime_digitized": None,
            "datetime_modified": None,
            "gps_latitude": None,
            "gps_longitude": None,
            "gps_altitude": None,
            "c2pa_data": "{}",
            "has_c2pa": 0,
            "c2pa_signer": None,
            "c2pa_timestamp": None,
            "warnings": "[]",
            "anomalies": "[]",
            "integrity_status": "unverified",
            "confidence_score": 0.5,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        },
    ]

    analyses = await shard.list_analyses(limit=50, offset=0)
    assert len(analyses) == 1


@pytest.mark.asyncio
async def test_list_analyses_no_db(shard):
    """Test listing analyses when DB unavailable."""
    shard._db = None
    result = await shard.list_analyses()
    assert result == []


@pytest.mark.asyncio
async def test_list_analyses_with_filters(shard, mock_frame):
    """Test listing analyses with various filters."""
    mock_frame.database.fetch_all.return_value = []

    result = await shard.list_analyses(
        integrity_status="verified",
        has_c2pa=True,
        has_warnings=False,
        doc_id="doc-1",
    )
    assert result == []
    mock_frame.database.fetch_all.assert_called()


@pytest.mark.asyncio
async def test_get_analysis_count(shard, mock_frame):
    """Test getting analysis count."""
    mock_frame.database.fetch_one.return_value = {"count": 42}
    count = await shard.get_analysis_count()
    assert count == 42


@pytest.mark.asyncio
async def test_get_analysis_count_no_db(shard):
    """Test analysis count when DB unavailable."""
    shard._db = None
    count = await shard.get_analysis_count()
    assert count == 0


@pytest.mark.asyncio
async def test_get_analysis_count_empty(shard, mock_frame):
    """Test analysis count when none exist."""
    mock_frame.database.fetch_one.return_value = None
    count = await shard.get_analysis_count()
    assert count == 0


# === ELA Tests ===


@pytest.mark.asyncio
async def test_generate_ela_no_analyzer(shard):
    """Test ELA generation when analyzer unavailable."""
    shard.ela_analyzer = None
    result = await shard.generate_ela("a-1")
    assert result["success"] is False
    assert "not available" in result["error"]


@pytest.mark.asyncio
async def test_generate_ela_analysis_not_found(shard, mock_frame):
    """Test ELA when analysis not found."""
    shard.ela_analyzer = MagicMock()
    mock_frame.database.fetch_one.return_value = None
    result = await shard.generate_ela("nonexistent")
    assert result["success"] is False
    assert "not found" in result["error"]


# === Event Handler Tests ===


@pytest.mark.asyncio
async def test_handle_document_ingested_image(shard, mock_frame):
    """Test auto-analysis trigger for image documents."""
    shard.analyze_document = AsyncMock(return_value={"analysis_id": "a-1"})

    await shard._handle_document_ingested(
        {
            "document_id": "doc-1",
            "doc_type": "image/jpeg",
        }
    )

    shard.analyze_document.assert_called_once_with("doc-1")


@pytest.mark.asyncio
async def test_handle_document_ingested_non_image(shard, mock_frame):
    """Test that non-image documents are not auto-analyzed."""
    shard.analyze_document = AsyncMock()

    await shard._handle_document_ingested(
        {
            "document_id": "doc-1",
            "doc_type": "application/pdf",
        }
    )

    shard.analyze_document.assert_not_called()


@pytest.mark.asyncio
async def test_handle_document_ingested_error(shard, mock_frame):
    """Test graceful handling of auto-analysis errors."""
    shard.analyze_document = AsyncMock(side_effect=Exception("File not found"))

    # Should not raise
    await shard._handle_document_ingested(
        {
            "document_id": "doc-1",
            "doc_type": "image/png",
        }
    )


# === _make_json_safe Tests ===


def test_make_json_safe_none():
    """Test _make_json_safe with None."""
    assert _make_json_safe(None) is None


def test_make_json_safe_primitives():
    """Test _make_json_safe with primitive types."""
    assert _make_json_safe("hello") == "hello"
    assert _make_json_safe(42) == 42
    assert _make_json_safe(3.14) == 3.14
    assert _make_json_safe(True) is True


def test_make_json_safe_bytes():
    """Test _make_json_safe with bytes."""
    result = _make_json_safe(b"hello")
    assert result == "hello"


def test_make_json_safe_dict():
    """Test _make_json_safe with nested dict."""
    data = {"key": "value", "nested": {"num": 42}}
    result = _make_json_safe(data)
    assert result == {"key": "value", "nested": {"num": 42}}


def test_make_json_safe_list():
    """Test _make_json_safe with list."""
    data = [1, "two", 3.0, None]
    result = _make_json_safe(data)
    assert result == [1, "two", 3.0, None]


def test_make_json_safe_tuple():
    """Test _make_json_safe with tuple converts to list."""
    result = _make_json_safe((1, 2, 3))
    assert result == [1, 2, 3]


def test_make_json_safe_non_serializable():
    """Test _make_json_safe falls back to string representation."""

    class Custom:
        def __str__(self):
            return "custom_obj"

    result = _make_json_safe(Custom())
    assert result == "custom_obj"


# === Model Tests ===


def test_media_analysis_defaults():
    """Test MediaAnalysis dataclass defaults."""
    ma = MediaAnalysis(id="a-1", document_id="doc-1")
    assert ma.integrity_status == "unknown"
    assert ma.confidence_score == 0.0
    assert ma.warnings == []
    assert ma.anomalies == []
    assert ma.exif_data == {}
    assert ma.has_c2pa is False


def test_similar_image():
    """Test SimilarImage dataclass."""
    si = SimilarImage(
        id="s-1",
        source_analysis_id="a-1",
        target_analysis_id="a-2",
        hash_type="phash",
        hamming_distance=5,
        similarity_score=0.92,
    )
    assert si.hamming_distance == 5
    assert si.similarity_score == 0.92


def test_ela_result_defaults():
    """Test ELAResult defaults."""
    ela = ELAResult(id="e-1", analysis_id="a-1")
    assert ela.quality == 95
    assert ela.uniform_regions == []
    assert ela.anomalous_regions == []


def test_sun_verification_defaults():
    """Test SunVerification defaults."""
    sv = SunVerification(id="sv-1", analysis_id="a-1")
    assert sv.verification_status == "unknown"
    assert sv.latitude is None
    assert sv.longitude is None


def test_analysis_stats_defaults():
    """Test AnalysisStats defaults."""
    stats = AnalysisStats()
    assert stats.total_analyses == 0
    assert stats.with_exif == 0
    assert stats.with_c2pa == 0
    assert stats.ai_generated_detected == 0


def test_integrity_status_enum():
    """Test IntegrityStatus enum values."""
    assert IntegrityStatus.UNKNOWN.value == "unknown"
    assert IntegrityStatus.VERIFIED.value == "verified"
    assert IntegrityStatus.FLAGGED.value == "flagged"
    assert IntegrityStatus.UNVERIFIED.value == "unverified"


def test_hash_type_enum():
    """Test HashType enum values."""
    assert HashType.PHASH.value == "phash"
    assert HashType.DHASH.value == "dhash"
    assert HashType.AHASH.value == "ahash"


def test_ela_assessment_enum():
    """Test ELAAssessment enum values."""
    assert ELAAssessment.UNIFORM.value == "uniform"
    assert ELAAssessment.VARIABLE.value == "variable"


def test_sun_verification_status_enum():
    """Test SunVerificationStatus enum values."""
    assert SunVerificationStatus.CONSISTENT.value == "consistent"
    assert SunVerificationStatus.INCONSISTENT.value == "inconsistent"
    assert SunVerificationStatus.UNAVAILABLE.value == "unavailable"


# === Pydantic Request Models ===


def test_analyze_request_model():
    """Test AnalyzeRequest pydantic model."""
    req = AnalyzeRequest(document_id="doc-1")
    assert req.document_id == "doc-1"


def test_ela_request_model():
    """Test ELARequest pydantic model with defaults."""
    req = ELARequest(analysis_id="a-1")
    assert req.quality == 95
    assert req.scale == 15


def test_ela_request_model_validation():
    """Test ELARequest validation bounds."""
    req = ELARequest(analysis_id="a-1", quality=70, scale=5)
    assert req.quality == 70
    assert req.scale == 5

    with pytest.raises(ValueError):
        ELARequest(analysis_id="a-1", quality=60)  # Below minimum

    with pytest.raises(ValueError):
        ELARequest(analysis_id="a-1", scale=35)  # Above maximum


def test_sun_position_request_model():
    """Test SunPositionRequest model."""
    req = SunPositionRequest(latitude=51.5, longitude=-0.12, datetime="2026-03-15T10:00:00")
    assert req.latitude == 51.5

    with pytest.raises(ValueError):
        SunPositionRequest(latitude=100, longitude=0, datetime="2026-01-01")  # lat > 90


def test_count_response_model():
    """Test CountResponse pydantic model."""
    resp = CountResponse(count=42)
    assert resp.count == 42
