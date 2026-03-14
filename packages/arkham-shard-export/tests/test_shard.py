"""
Export Shard - Shard Class Tests

Tests for ExportShard with mocked Frame services.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arkham_shard_export.models import (
    ExportFilter,
    ExportFormat,
    ExportOptions,
    ExportStatus,
    ExportTarget,
)
from arkham_shard_export.shard import ExportShard

# === Fixtures ===


@pytest.fixture
def mock_db():
    """Create a mock database service."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.fetch_one = AsyncMock(return_value=None)
    db.fetch_all = AsyncMock(return_value=[])
    return db


@pytest.fixture
def mock_events():
    """Create a mock events service."""
    events = AsyncMock()
    events.emit = AsyncMock()
    events.subscribe = AsyncMock()
    events.unsubscribe = AsyncMock()
    return events


@pytest.fixture
def mock_storage():
    """Create a mock storage service."""
    storage = MagicMock()
    storage.save = AsyncMock()
    storage.get_url = MagicMock(return_value="/storage/file.json")
    return storage


@pytest.fixture
def mock_frame(mock_db, mock_events, mock_storage):
    """Create a mock Frame with all services."""
    frame = MagicMock()
    frame.database = mock_db
    frame.db = mock_db
    frame.events = mock_events
    frame.storage = mock_storage
    return frame


@pytest.fixture
async def initialized_shard(mock_frame):
    """Create an initialized ExportShard."""
    shard = ExportShard()
    await shard.initialize(mock_frame)
    return shard


# === Shard Metadata Tests ===


class TestShardMetadata:
    """Tests for shard metadata and properties."""

    def test_shard_name(self):
        """Verify shard name is correct."""
        shard = ExportShard()
        assert shard.name == "export"

    def test_shard_version(self):
        """Verify shard version is correct."""
        shard = ExportShard()
        assert shard.version == "0.1.0"

    def test_shard_description(self):
        """Verify shard description exists."""
        shard = ExportShard()
        assert "export" in shard.description.lower()


# === Initialization Tests ===


class TestInitialization:
    """Tests for shard initialization and shutdown."""

    @pytest.mark.asyncio
    async def test_initialize_with_frame(self, mock_frame):
        """Test shard initializes correctly with frame."""
        shard = ExportShard()
        await shard.initialize(mock_frame)

        assert shard.frame == mock_frame
        assert shard._db == mock_frame.database
        assert shard._events == mock_frame.events
        assert shard._initialized is True

    @pytest.mark.asyncio
    async def test_schema_creation(self, mock_frame):
        """Test database schema is created on initialization."""
        shard = ExportShard()
        await shard.initialize(mock_frame)

        # Verify execute was called for table creation
        assert mock_frame.database.execute.called
        calls = [str(call) for call in mock_frame.database.execute.call_args_list]
        assert any("arkham_export_jobs" in str(call) for call in calls)

    @pytest.mark.asyncio
    async def test_shutdown(self, initialized_shard):
        """Test shard shuts down correctly."""
        await initialized_shard.shutdown()
        assert initialized_shard._initialized is False

    @pytest.mark.asyncio
    async def test_get_routes(self, initialized_shard):
        """Test get_routes returns a router."""
        router = initialized_shard.get_routes()
        assert router is not None
        assert hasattr(router, "routes")


# === Export Job Tests ===


class TestExportJobs:
    """Tests for export job creation and management."""

    @pytest.mark.asyncio
    async def test_create_export_job(self, initialized_shard, mock_frame):
        """Test creating an export job."""
        # Mock _fetch_data to avoid real HTTP calls
        with patch.object(
            initialized_shard, "_fetch_data", new_callable=AsyncMock, return_value=[{"id": "1", "title": "Test"}]
        ):
            job = await initialized_shard.create_export_job(
                format=ExportFormat.JSON,
                target=ExportTarget.DOCUMENTS,
            )

        assert job is not None
        assert job.format == ExportFormat.JSON
        assert job.target == ExportTarget.DOCUMENTS
        assert job.status == ExportStatus.COMPLETED  # Processed immediately in stub

        # Verify events were emitted
        assert mock_frame.events.emit.called

    @pytest.mark.asyncio
    async def test_create_job_with_options(self, initialized_shard, mock_frame):
        """Test creating a job with export options."""
        options = ExportOptions(
            include_metadata=False,
            flatten=True,
            max_records=100,
        )

        with patch.object(
            initialized_shard, "_fetch_data", new_callable=AsyncMock, return_value=[{"id": "1", "name": "Test"}]
        ):
            job = await initialized_shard.create_export_job(
                format=ExportFormat.CSV,
                target=ExportTarget.ENTITIES,
                options=options,
            )

        assert job.format == ExportFormat.CSV
        assert job.options.flatten is True
        assert job.options.max_records == 100

    @pytest.mark.asyncio
    async def test_get_job_status(self, initialized_shard, mock_frame):
        """Test getting job status."""
        mock_frame.database.fetch_one.return_value = {
            "id": "job-1",
            "format": "json",
            "target": "documents",
            "status": "completed",
            "created_at": datetime.utcnow().isoformat(),
            "started_at": datetime.utcnow().isoformat(),
            "completed_at": datetime.utcnow().isoformat(),
            "file_path": "/tmp/export.json",
            "file_size": 1024,
            "download_url": "/api/export/jobs/job-1/download",
            "expires_at": datetime.utcnow().isoformat(),
            "error": None,
            "filters": "{}",
            "options": "{}",
            "record_count": 10,
            "processing_time_ms": 500.0,
            "created_by": "system",
            "metadata": "{}",
        }

        job = await initialized_shard.get_job_status("job-1")
        assert job is not None
        assert job.id == "job-1"
        assert job.format == ExportFormat.JSON

    @pytest.mark.asyncio
    async def test_get_job_not_found(self, initialized_shard, mock_frame):
        """Test getting a non-existent job."""
        mock_frame.database.fetch_one.return_value = None

        job = await initialized_shard.get_job_status("nonexistent")
        assert job is None

    @pytest.mark.asyncio
    async def test_list_jobs(self, initialized_shard, mock_frame):
        """Test listing export jobs."""
        mock_frame.database.fetch_all.return_value = []

        jobs = await initialized_shard.list_jobs()
        assert jobs == []

    @pytest.mark.asyncio
    async def test_list_jobs_with_filter(self, initialized_shard, mock_frame):
        """Test listing jobs with filter."""
        filter = ExportFilter(
            status=ExportStatus.COMPLETED,
            format=ExportFormat.CSV,
        )

        await initialized_shard.list_jobs(filter=filter, limit=10, offset=0)

        # Verify query includes filter conditions
        mock_frame.database.fetch_all.assert_called()

    @pytest.mark.asyncio
    async def test_cancel_job(self, initialized_shard, mock_frame):
        """Test cancelling a pending job."""
        mock_frame.database.fetch_one.return_value = {
            "id": "job-1",
            "format": "json",
            "target": "documents",
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
            "started_at": None,
            "completed_at": None,
            "file_path": None,
            "file_size": None,
            "download_url": None,
            "expires_at": datetime.utcnow().isoformat(),
            "error": None,
            "filters": "{}",
            "options": "{}",
            "record_count": 0,
            "processing_time_ms": 0,
            "created_by": "system",
            "metadata": "{}",
        }

        job = await initialized_shard.cancel_job("job-1")
        assert job is not None
        assert job.status == ExportStatus.CANCELLED

        # Verify event was emitted
        mock_frame.events.emit.assert_called()

    @pytest.mark.asyncio
    async def test_get_download_url(self, initialized_shard, mock_frame):
        """Test getting download URL for completed job."""
        from datetime import timedelta

        expires_at = datetime.utcnow() + timedelta(hours=24)

        mock_frame.database.fetch_one.return_value = {
            "id": "job-1",
            "format": "json",
            "target": "documents",
            "status": "completed",
            "created_at": datetime.utcnow().isoformat(),
            "started_at": datetime.utcnow().isoformat(),
            "completed_at": datetime.utcnow().isoformat(),
            "file_path": "/tmp/export.json",
            "file_size": 1024,
            "download_url": "/api/export/jobs/job-1/download",
            "expires_at": expires_at.isoformat(),
            "error": None,
            "filters": "{}",
            "options": "{}",
            "record_count": 10,
            "processing_time_ms": 500.0,
            "created_by": "system",
            "metadata": "{}",
        }

        url = await initialized_shard.get_download_url("job-1")
        assert url == "/api/export/jobs/job-1/download"

    @pytest.mark.asyncio
    async def test_get_download_url_expired(self, initialized_shard, mock_frame):
        """Test getting download URL for expired job."""
        from datetime import timedelta

        expires_at = datetime.utcnow() - timedelta(hours=1)

        mock_frame.database.fetch_one.return_value = {
            "id": "job-1",
            "format": "json",
            "target": "documents",
            "status": "completed",
            "created_at": datetime.utcnow().isoformat(),
            "started_at": datetime.utcnow().isoformat(),
            "completed_at": datetime.utcnow().isoformat(),
            "file_path": "/tmp/export.json",
            "file_size": 1024,
            "download_url": "/api/export/jobs/job-1/download",
            "expires_at": expires_at.isoformat(),
            "error": None,
            "filters": "{}",
            "options": "{}",
            "record_count": 10,
            "processing_time_ms": 500.0,
            "created_by": "system",
            "metadata": "{}",
        }

        url = await initialized_shard.get_download_url("job-1")
        assert url is None


# === Statistics Tests ===


class TestStatistics:
    """Tests for statistics retrieval."""

    @pytest.mark.asyncio
    async def test_get_statistics(self, initialized_shard, mock_frame):
        """Test getting export statistics."""
        mock_frame.database.fetch_one.side_effect = [
            {"count": 100},  # total
            {"total_records": 1000, "total_size": 50000, "avg_time": 2500.0},  # aggregates
            {"oldest": None},  # oldest pending
        ]
        mock_frame.database.fetch_all.side_effect = [
            [{"status": "completed", "count": 80}, {"status": "pending", "count": 20}],
            [{"format": "json", "count": 60}, {"format": "csv", "count": 40}],
            [{"target": "documents", "count": 70}, {"target": "entities", "count": 30}],
        ]

        stats = await initialized_shard.get_statistics()

        assert stats.total_jobs == 100

    @pytest.mark.asyncio
    async def test_get_count(self, initialized_shard, mock_frame):
        """Test getting job count."""
        mock_frame.database.fetch_one.return_value = {"count": 15}

        count = await initialized_shard.get_count()
        assert count == 15

    @pytest.mark.asyncio
    async def test_get_count_by_status(self, initialized_shard, mock_frame):
        """Test getting count filtered by status."""
        mock_frame.database.fetch_one.return_value = {"count": 5}

        count = await initialized_shard.get_count(status="completed")
        assert count == 5


# === Format and Target Tests ===


class TestFormatsAndTargets:
    """Tests for format and target info."""

    def test_get_supported_formats(self, initialized_shard):
        """Test getting supported formats."""
        formats = initialized_shard.get_supported_formats()

        assert len(formats) == 5
        format_names = [f.format.value for f in formats]
        assert "json" in format_names
        assert "csv" in format_names
        assert "pdf" in format_names
        assert "docx" in format_names
        assert "xlsx" in format_names

        # Verify JSON format is not a placeholder
        json_format = next(f for f in formats if f.format == ExportFormat.JSON)
        assert json_format.placeholder is False

    def test_get_export_targets(self, initialized_shard):
        """Test getting export targets."""
        targets = initialized_shard.get_export_targets()

        assert len(targets) == 6
        target_names = [t.target.value for t in targets]
        assert "documents" in target_names
        assert "entities" in target_names
        assert "claims" in target_names
        assert "timeline" in target_names
        assert "graph" in target_names
        assert "matrix" in target_names

        # Check available formats
        docs_target = next(t for t in targets if t.target == ExportTarget.DOCUMENTS)
        assert ExportFormat.JSON in docs_target.available_formats
        assert ExportFormat.CSV in docs_target.available_formats


# === File Generation Tests ===


class TestFileGeneration:
    """Tests for export file generation."""

    @pytest.mark.asyncio
    async def test_generate_json_file(self, initialized_shard, mock_frame):
        """Test generating JSON export file."""
        from arkham_shard_export.models import ExportJob

        job = ExportJob(
            id="job-1",
            format=ExportFormat.JSON,
            target=ExportTarget.DOCUMENTS,
        )

        with patch.object(
            initialized_shard, "_fetch_data", new_callable=AsyncMock, return_value=[{"id": "1", "title": "Test Doc"}]
        ):
            file_path, record_count = await initialized_shard._generate_export_file(job)

        assert file_path is not None
        assert file_path.endswith(".json")
        import os

        assert os.path.exists(file_path)

        # Verify file content
        import json

        with open(file_path, "r") as f:
            data = json.load(f)
        assert data["export_info"]["target"] == "documents"
        assert "data" in data

    @pytest.mark.asyncio
    async def test_generate_csv_file(self, initialized_shard, mock_frame):
        """Test generating CSV export file."""
        from arkham_shard_export.models import ExportJob

        job = ExportJob(
            id="job-2",
            format=ExportFormat.CSV,
            target=ExportTarget.ENTITIES,
        )

        with patch.object(
            initialized_shard, "_fetch_data", new_callable=AsyncMock, return_value=[{"id": "1", "name": "Entity"}]
        ):
            file_path, record_count = await initialized_shard._generate_export_file(job)

        assert file_path is not None
        assert file_path.endswith(".csv")
        import os

        assert os.path.exists(file_path)

    @pytest.mark.asyncio
    async def test_generate_pdf_placeholder(self, initialized_shard, mock_frame):
        """Test generating PDF placeholder file."""
        from arkham_shard_export.models import ExportJob

        job = ExportJob(
            id="job-3",
            format=ExportFormat.PDF,
            target=ExportTarget.CLAIMS,
        )

        with patch.object(
            initialized_shard, "_fetch_data", new_callable=AsyncMock, return_value=[{"id": "1", "text": "Claim"}]
        ):
            file_path, record_count = await initialized_shard._generate_export_file(job)

        assert file_path is not None
        assert file_path.endswith(".pdf")

    def test_get_file_extension(self):
        """Test getting file extension for formats."""
        shard = ExportShard()

        assert shard._get_file_extension(ExportFormat.JSON) == "json"
        assert shard._get_file_extension(ExportFormat.CSV) == "csv"
        assert shard._get_file_extension(ExportFormat.PDF) == "pdf"
        assert shard._get_file_extension(ExportFormat.DOCX) == "docx"
        assert shard._get_file_extension(ExportFormat.XLSX) == "xlsx"


# === Direct Export Generation Tests ===


class TestGenerateExport:
    """Tests for the generate_export convenience method."""

    @pytest.mark.asyncio
    async def test_generate_export_json(self, initialized_shard):
        """Test generating JSON export bytes directly."""
        sample_data = [
            {"id": "1", "title": "Doc One", "status": "active"},
            {"id": "2", "title": "Doc Two", "status": "archived"},
        ]
        with patch.object(initialized_shard, "_fetch_data", new_callable=AsyncMock, return_value=sample_data):
            result = await initialized_shard.generate_export(
                format="json", target="documents", filters={"status": "active"}
            )

        import json as json_mod

        assert isinstance(result, bytes)
        parsed = json_mod.loads(result.decode("utf-8"))
        assert "export_info" in parsed
        assert parsed["export_info"]["target"] == "documents"
        assert parsed["export_info"]["record_count"] == 2
        assert len(parsed["data"]) == 2
        assert parsed["data"][0]["title"] == "Doc One"

    @pytest.mark.asyncio
    async def test_generate_export_csv(self, initialized_shard):
        """Test generating CSV export bytes directly."""
        sample_data = [
            {"id": "1", "name": "Entity A", "type": "person"},
            {"id": "2", "name": "Entity B", "type": "org"},
        ]
        with patch.object(initialized_shard, "_fetch_data", new_callable=AsyncMock, return_value=sample_data):
            result = await initialized_shard.generate_export(format="csv", target="entities")

        assert isinstance(result, bytes)
        csv_text = result.decode("utf-8")
        # Should have header + 2 data rows
        lines = csv_text.strip().split("\n")
        assert len(lines) == 3  # header + 2 rows
        assert "id" in lines[0]
        assert "name" in lines[0]

    @pytest.mark.asyncio
    async def test_generate_export_csv_empty(self, initialized_shard):
        """Test CSV export with no data returns empty marker."""
        with patch.object(initialized_shard, "_fetch_data", new_callable=AsyncMock, return_value=[]):
            result = await initialized_shard.generate_export(format="csv", target="claims")

        assert b"No data" in result

    @pytest.mark.asyncio
    async def test_generate_export_invalid_format(self, initialized_shard):
        """Test that unsupported format raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported direct export format"):
            await initialized_shard.generate_export(format="pdf", target="documents")

    @pytest.mark.asyncio
    async def test_generate_export_invalid_target(self, initialized_shard):
        """Test that unsupported target raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported export target"):
            await initialized_shard.generate_export(format="json", target="nonexistent")

    @pytest.mark.asyncio
    async def test_generate_export_timeline_json(self, initialized_shard):
        """Test JSON export for timeline target."""
        timeline_data = [
            {"id": "e1", "date_start": "2024-01-15", "description": "Event 1"},
            {"id": "e2", "date_start": "2024-02-20", "description": "Event 2"},
        ]
        with patch.object(initialized_shard, "_fetch_data", new_callable=AsyncMock, return_value=timeline_data):
            result = await initialized_shard.generate_export(format="json", target="timeline")

        import json as json_mod

        parsed = json_mod.loads(result.decode("utf-8"))
        assert parsed["export_info"]["target"] == "timeline"
        assert len(parsed["data"]) == 2


# === Preview Data Tests ===


class TestPreviewData:
    """Tests for the preview_data method."""

    @pytest.mark.asyncio
    async def test_preview_data_documents(self, initialized_shard):
        """Test previewing document data."""
        sample_data = [{"id": str(i), "title": f"Doc {i}"} for i in range(20)]
        with patch.object(initialized_shard, "_fetch_data", new_callable=AsyncMock, return_value=sample_data):
            result = await initialized_shard.preview_data(format="json", target="documents", max_preview_records=5)

        assert result["target"] == "documents"
        assert result["estimated_record_count"] == 20
        assert len(result["preview_records"]) == 5
        assert result["estimated_file_size_bytes"] > 0

    @pytest.mark.asyncio
    async def test_preview_data_invalid_target(self, initialized_shard):
        """Test preview with invalid target returns empty result."""
        result = await initialized_shard.preview_data(format="json", target="invalid_target")

        assert result["estimated_record_count"] == 0
        assert result["preview_records"] == []

    @pytest.mark.asyncio
    async def test_preview_data_fetch_error(self, initialized_shard):
        """Test preview handles fetch errors gracefully."""
        with patch.object(initialized_shard, "_fetch_data", new_callable=AsyncMock, side_effect=Exception("API down")):
            result = await initialized_shard.preview_data(format="json", target="documents")

        assert result["estimated_record_count"] == 0
        assert result["preview_records"] == []
