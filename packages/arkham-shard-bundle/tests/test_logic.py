"""
Bundle Shard - Logic Tests

Tests for models, API handler logic, and bundle compilation.
All external dependencies are mocked.
"""

import json
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arkham_shard_bundle.api import (
    CompileRequest,
    CreateBundleRequest,
    UpdateBundleRequest,
)
from arkham_shard_bundle.models import (
    Bundle,
    BundleIndex,
    BundleIndexEntry,
    BundlePage,
    BundleStatus,
    BundleVersion,
    DocumentStatus,
    IndexEntryType,
)
from arkham_shard_bundle.shard import BundleShard
from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_events():
    events = AsyncMock()
    events.emit = AsyncMock()
    events.subscribe = AsyncMock()
    events.unsubscribe = AsyncMock()
    return events


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.execute = AsyncMock()
    db.fetch_all = AsyncMock(return_value=[])
    db.fetch_one = AsyncMock(return_value=None)
    db.transaction = MagicMock()
    db.transaction.return_value.__aenter__ = AsyncMock()
    db.transaction.return_value.__aexit__ = AsyncMock()
    return db


@pytest.fixture
def mock_frame(mock_events, mock_db):
    frame = MagicMock()
    frame.database = mock_db
    frame.get_service = MagicMock(
        side_effect=lambda name: {
            "events": mock_events,
            "llm": None,
            "database": mock_db,
            "vectors": None,
            "documents": None,
        }.get(name)
    )
    return frame


# ---------------------------------------------------------------------------
# Model Tests
# ---------------------------------------------------------------------------


class TestModels:
    """Verify dataclass construction and enum values."""

    def test_bundle_defaults(self):
        b = Bundle(id="b1")
        assert b.id == "b1"
        assert b.title == ""
        assert b.status == BundleStatus.DRAFT
        assert b.version == 1

    def test_bundle_status_enum(self):
        assert BundleStatus.DRAFT == "draft"
        assert BundleStatus.COMPILED == "compiled"

    def test_document_status_enum(self):
        assert DocumentStatus.AGREED == "agreed"
        assert DocumentStatus.DISPUTED == "disputed"

    def test_index_entry_type_enum(self):
        assert IndexEntryType.DOCUMENT == "document"
        assert IndexEntryType.SECTION_HEADER == "section_header"

    def test_bundle_page_range(self):
        p = BundlePage(
            id="p1",
            bundle_id="b1",
            version_id="v1",
            document_id="d1",
            bundle_page_start=10,
            bundle_page_end=14,
        )
        assert p.page_range == "pp.10-14"
        p.bundle_page_end = 10
        assert p.page_range == "p.10"

    def test_bundle_index_entry_page_range(self):
        e = BundleIndexEntry(
            entry_type=IndexEntryType.DOCUMENT,
            position=0,
            bundle_page_start=1,
            bundle_page_end=5,
        )
        assert e.page_range == "pp.1-5"
        e.bundle_page_start = None
        assert e.page_range == ""

    def test_bundle_index_to_dict(self):
        entry = BundleIndexEntry(
            entry_type=IndexEntryType.DOCUMENT,
            position=0,
            document_id="d1",
            bundle_page_start=1,
            bundle_page_end=5,
        )
        idx = BundleIndex(
            id="idx1",
            bundle_id="b1",
            version_id="v1",
            entries=[entry],
            document_count=1,
            total_pages=5,
        )
        d = idx.to_dict()
        assert d["id"] == "idx1"
        assert len(d["entries"]) == 1
        assert d["entries"][0]["document_id"] == "d1"

    def test_bundle_version_defaults(self):
        v = BundleVersion(id="v1", bundle_id="b1")
        assert v.version_number == 1
        assert v.total_pages == 0


# ---------------------------------------------------------------------------
# Schema Creation Tests
# ---------------------------------------------------------------------------


class TestSchemaCreation:
    """Verify tables are created during initialize()."""

    @pytest.mark.asyncio
    async def test_all_tables_created(self, mock_frame, mock_db):
        shard = BundleShard()
        await shard.initialize(mock_frame)

        executed_sql = " ".join(str(c.args[0]) for c in mock_db.execute.call_args_list)

        assert "CREATE SCHEMA IF NOT EXISTS arkham_bundle" in executed_sql
        assert "arkham_bundle.bundles" in executed_sql
        assert "arkham_bundle.versions" in executed_sql
        assert "arkham_bundle.pages" in executed_sql
        assert "arkham_bundle.indices" in executed_sql

    @pytest.mark.asyncio
    async def test_indexes_created(self, mock_frame, mock_db):
        shard = BundleShard()
        await shard.initialize(mock_frame)

        index_calls = [str(c.args[0]) for c in mock_db.execute.call_args_list if "CREATE INDEX" in str(c.args[0])]
        assert len(index_calls) >= 5


# ---------------------------------------------------------------------------
# API Logic Tests
# ---------------------------------------------------------------------------


class TestAPILogic:
    """Test the API module-level handler functions via direct import."""

    def setup_method(self):
        import arkham_shard_bundle.api as api_mod

        self.api = api_mod

    @pytest.mark.asyncio
    async def test_list_bundles_no_db(self):
        self.api._db = None
        with pytest.raises(HTTPException) as exc:
            await self.api.list_bundles()
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_list_bundles(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_all.return_value = [{"id": "b1", "title": "Test Bundle"}]
        result = await self.api.list_bundles(project_id="p1", status="draft")
        assert result["count"] == 1
        assert result["bundles"][0]["id"] == "b1"
        assert "project_id = :project_id" in mock_db.fetch_all.call_args[0][0]

    @pytest.mark.asyncio
    async def test_get_bundle_not_found(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_one.return_value = None
        with pytest.raises(HTTPException) as exc:
            await self.api.get_bundle("b1")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_create_bundle(self, mock_db, mock_events):
        self.api._db = mock_db
        self.api._event_bus = mock_events
        self.api._shard = None
        req = CreateBundleRequest(title="New Bundle", project_id="p1")
        result = await self.api.create_bundle(req)
        assert result["title"] == "New Bundle"
        mock_db.execute.assert_called_once()
        mock_events.emit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_bundle(self, mock_db, mock_events):
        self.api._db = mock_db
        self.api._event_bus = mock_events
        req = UpdateBundleRequest(title="Updated Title")
        result = await self.api.update_bundle("b1", req)
        assert result["status"] == "updated"
        mock_db.execute.assert_called_once()
        assert "title = :title" in mock_db.execute.call_args[0][0]

    @pytest.mark.asyncio
    async def test_update_bundle_no_fields(self, mock_db):
        self.api._db = mock_db
        req = UpdateBundleRequest()
        with pytest.raises(HTTPException) as exc:
            await self.api.update_bundle("b1", req)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_delete_bundle(self, mock_db, mock_events):
        self.api._db = mock_db
        self.api._event_bus = mock_events
        result = await self.api.delete_bundle("b1")
        assert result["status"] == "deleted"
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_compile_bundle(self, mock_db, mock_events):
        self.api._db = mock_db
        self.api._event_bus = mock_events

        # Mock bundle fetch
        mock_db.fetch_one.return_value = {"id": "b1", "version": 1, "title": "Test Bundle"}

        req = CompileRequest(
            document_ids=["d1", "d2"],
            document_overrides={"d1": {"page_count": 2, "title": "Doc 1"}, "d2": {"page_count": 3, "title": "Doc 2"}},
            section_headers={"0": "Section A"},
            change_notes="Initial compile",
        )

        result = await self.api.compile_bundle("b1", req)

        assert result["status"] == "compiled"
        assert result["total_pages"] == 5
        assert result["version_number"] == 2

        # Verify transaction used
        assert mock_db.transaction.called
        # Verify inserts (Version, Pages, Index, Update Bundle)
        # 1 version + 2 docs + 1 index + 1 update = 5 calls
        assert mock_db.execute.call_count == 5

        # Verify event
        mock_events.emit.assert_called_with(
            "bundle.bundle.compiled",
            {"bundle_id": "b1", "version_id": result["version_id"], "pages": 5},
            source="bundle-shard",
        )

    @pytest.mark.asyncio
    async def test_compile_bundle_not_found(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_one.return_value = None
        req = CompileRequest(document_ids=[])
        with pytest.raises(HTTPException) as exc:
            await self.api.compile_bundle("b1", req)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_list_versions(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_all.return_value = [{"id": "v1", "version_number": 1}]
        result = await self.api.list_versions("b1")
        assert len(result["versions"]) == 1

    @pytest.mark.asyncio
    async def test_get_version_pages(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_all.return_value = [{"id": "p1", "document_id": "d1"}]
        result = await self.api.get_version_pages("v1")
        assert len(result["pages"]) == 1

    @pytest.mark.asyncio
    async def test_get_version_index(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_one.return_value = {"id": "idx1", "entries": "[]"}
        result = await self.api.get_version_index("v1")
        assert result["id"] == "idx1"

    @pytest.mark.asyncio
    async def test_get_version_index_not_found(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_one.return_value = None
        with pytest.raises(HTTPException) as exc:
            await self.api.get_version_index("v1")
        assert exc.value.status_code == 404
