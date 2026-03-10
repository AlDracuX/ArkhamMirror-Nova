"""
Packets Shard - API Tests

Tests for the FastAPI routes.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arkham_shard_packets.api import router
from arkham_shard_packets.models import (
    ContentType,
    ExportFormat,
    Packet,
    PacketContent,
    PacketExportResult,
    PacketImportResult,
    PacketShare,
    PacketStatistics,
    PacketStatus,
    PacketVersion,
    PacketVisibility,
    SharePermission,
)
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient


@pytest.fixture
def mock_shard():
    """Create a mock PacketsShard."""
    shard = MagicMock()
    shard.name = "packets"
    shard.version = "0.1.0"

    # Mock async methods
    shard.create_packet = AsyncMock()
    shard.get_packet = AsyncMock()
    shard.list_packets = AsyncMock()
    shard.update_packet = AsyncMock()
    shard.finalize_packet = AsyncMock()
    shard.archive_packet = AsyncMock()
    shard.add_content = AsyncMock()
    shard.get_packet_contents = AsyncMock()
    shard.remove_content = AsyncMock()
    shard.share_packet = AsyncMock()
    shard.get_packet_shares = AsyncMock()
    shard.revoke_share = AsyncMock()
    shard.export_packet = AsyncMock()
    shard.import_packet = AsyncMock()
    shard.get_packet_versions = AsyncMock()
    shard._create_version_snapshot = AsyncMock()
    shard.get_statistics = AsyncMock()
    shard.get_count = AsyncMock()

    return shard


@pytest.fixture
def client(mock_shard):
    """Create test client with mocked shard on app state."""
    app = FastAPI()
    app.include_router(router)
    app.state.packets_shard = mock_shard
    with TestClient(app) as c:
        yield c


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    def test_health_check(self, client, mock_shard):
        """Test health check returns shard info."""
        response = client.get("/api/packets/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["shard"] == "packets"
        assert data["version"] == "0.1.0"


class TestCountEndpoint:
    """Tests for count endpoint."""

    def test_get_count(self, client, mock_shard):
        """Test getting packet count."""
        mock_shard.get_count.return_value = 42
        response = client.get("/api/packets/count")
        assert response.status_code == 200
        assert response.json()["count"] == 42

    def test_get_count_with_filter(self, client, mock_shard):
        """Test getting packet count with status filter."""
        mock_shard.get_count.return_value = 15
        response = client.get("/api/packets/count?status=draft")
        assert response.status_code == 200
        assert response.json()["count"] == 15


class TestPacketCRUDEndpoints:
    """Tests for packet CRUD endpoints."""

    def test_create_packet(self, client, mock_shard):
        """Test creating a packet."""
        now = datetime.utcnow()
        packet = Packet(
            id="test-id",
            name="Test Packet",
            description="Test",
            created_at=now,
            updated_at=now,
        )
        mock_shard.create_packet.return_value = packet

        response = client.post(
            "/api/packets/",
            json={"name": "Test Packet", "description": "Test"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "test-id"
        assert data["name"] == "Test Packet"

    def test_get_packet_success(self, client, mock_shard):
        """Test getting an existing packet."""
        now = datetime.utcnow()
        packet = Packet(
            id="test-id",
            name="Test Packet",
            created_at=now,
            updated_at=now,
        )
        mock_shard.get_packet.return_value = packet

        response = client.get("/api/packets/test-id")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "test-id"
        assert data["name"] == "Test Packet"

    def test_get_packet_not_found(self, client, mock_shard):
        """Test getting a non-existent packet."""
        mock_shard.get_packet.return_value = None
        response = client.get("/api/packets/nonexistent")
        assert response.status_code == 404

    def test_list_packets(self, client, mock_shard):
        """Test listing packets."""
        now = datetime.utcnow()
        packets = [
            Packet(id="p1", name="Packet 1", created_at=now, updated_at=now),
            Packet(id="p2", name="Packet 2", created_at=now, updated_at=now),
        ]
        mock_shard.list_packets.return_value = packets
        mock_shard.get_count.return_value = 2

        response = client.get("/api/packets/")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 2

    def test_update_packet(self, client, mock_shard):
        """Test updating a packet."""
        now = datetime.utcnow()
        packet = Packet(
            id="test-id",
            name="Updated Name",
            created_at=now,
            updated_at=now,
        )
        mock_shard.update_packet.return_value = packet

        response = client.put(
            "/api/packets/test-id",
            json={"name": "Updated Name"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"

    def test_delete_packet(self, client, mock_shard):
        """Test deleting a packet."""
        now = datetime.utcnow()
        packet = Packet(
            id="test-id",
            name="Test",
            status=PacketStatus.ARCHIVED,
            created_at=now,
            updated_at=now,
        )
        mock_shard.archive_packet.return_value = packet
        response = client.delete("/api/packets/test-id")
        assert response.status_code == 204


class TestPacketStatusEndpoints:
    """Tests for packet status endpoints."""

    def test_finalize_packet(self, client, mock_shard):
        """Test finalizing a packet."""
        now = datetime.utcnow()
        packet = Packet(
            id="test-id",
            name="Test",
            status=PacketStatus.FINALIZED,
            created_at=now,
            updated_at=now,
        )
        mock_shard.finalize_packet.return_value = packet

        response = client.post("/api/packets/test-id/finalize")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "finalized"

    def test_archive_packet(self, client, mock_shard):
        """Test archiving a packet."""
        now = datetime.utcnow()
        packet = Packet(
            id="test-id",
            name="Test",
            status=PacketStatus.ARCHIVED,
            created_at=now,
            updated_at=now,
        )
        mock_shard.archive_packet.return_value = packet

        response = client.post("/api/packets/test-id/archive")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "archived"


class TestContentEndpoints:
    """Tests for content management endpoints."""

    def test_get_packet_contents(self, client, mock_shard):
        """Test getting packet contents."""
        now = datetime.utcnow()
        packet = Packet(id="p1", name="Test", created_at=now, updated_at=now)
        contents = [
            PacketContent(
                id="c1",
                packet_id="p1",
                content_type=ContentType.DOCUMENT,
                content_id="doc-1",
                content_title="Document 1",
                added_at=now,
            ),
        ]
        mock_shard.get_packet.return_value = packet
        mock_shard.get_packet_contents.return_value = contents

        response = client.get("/api/packets/p1/contents")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["content_title"] == "Document 1"

    def test_add_packet_content(self, client, mock_shard):
        """Test adding content to packet."""
        now = datetime.utcnow()
        content = PacketContent(
            id="c1",
            packet_id="p1",
            content_type=ContentType.ENTITY,
            content_id="ent-1",
            content_title="Entity 1",
            added_at=now,
        )
        mock_shard.add_content.return_value = content

        response = client.post(
            "/api/packets/p1/contents",
            json={
                "content_type": "entity",
                "content_id": "ent-1",
                "content_title": "Entity 1",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["content_type"] == "entity"

    def test_remove_packet_content(self, client, mock_shard):
        """Test removing content from packet."""
        mock_shard.remove_content.return_value = True
        response = client.delete("/api/packets/p1/contents/c1")
        assert response.status_code == 204


class TestShareEndpoints:
    """Tests for sharing endpoints."""

    def test_share_packet(self, client, mock_shard):
        """Test sharing a packet."""
        now = datetime.utcnow()
        share = PacketShare(
            id="s1",
            packet_id="p1",
            shared_with="user-123",
            permissions=SharePermission.VIEW,
            shared_at=now,
            access_token="token-abc",
        )
        mock_shard.share_packet.return_value = share

        response = client.post(
            "/api/packets/p1/share",
            json={"shared_with": "user-123"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["shared_with"] == "user-123"
        assert data["access_token"] == "token-abc"

    def test_get_packet_shares(self, client, mock_shard):
        """Test getting packet shares."""
        now = datetime.utcnow()
        packet = Packet(id="p1", name="Test", created_at=now, updated_at=now)
        shares = [
            PacketShare(
                id="s1",
                packet_id="p1",
                shared_with="user-1",
                shared_at=now,
                access_token="token-1",
            ),
        ]
        mock_shard.get_packet.return_value = packet
        mock_shard.get_packet_shares.return_value = shares

        response = client.get("/api/packets/p1/shares")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1

    def test_revoke_share(self, client, mock_shard):
        """Test revoking a share."""
        mock_shard.revoke_share.return_value = True
        response = client.delete("/api/packets/p1/shares/s1")
        assert response.status_code == 204


class TestExportImportEndpoints:
    """Tests for export/import endpoints."""

    def test_export_packet(self, client, mock_shard):
        """Test exporting a packet."""
        now = datetime.utcnow()
        result = PacketExportResult(
            packet_id="p1",
            export_format=ExportFormat.ZIP,
            file_path="/exports/p1.zip",
            file_size_bytes=1024,
            exported_at=now,
            contents_exported=5,
        )
        mock_shard.export_packet.return_value = result

        response = client.post(
            "/api/packets/p1/export",
            json={"format": "zip"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["export_format"] == "zip"
        assert data["contents_exported"] == 5

    def test_import_packet(self, client, mock_shard):
        """Test importing a packet."""
        now = datetime.utcnow()
        result = PacketImportResult(
            packet_id="p-new",
            import_source="/imports/packet.zip",
            imported_at=now,
            contents_imported=10,
            merge_mode="replace",
        )
        mock_shard.import_packet.return_value = result

        response = client.post(
            "/api/packets/import",
            json={"file_path": "/imports/packet.zip"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["packet_id"] == "p-new"
        assert data["contents_imported"] == 10


class TestVersionEndpoints:
    """Tests for version endpoints."""

    def test_get_packet_versions(self, client, mock_shard):
        """Test getting packet versions."""
        now = datetime.utcnow()
        packet = Packet(id="p1", name="Test", created_at=now, updated_at=now)
        versions = [
            PacketVersion(
                id="v1",
                packet_id="p1",
                version_number=1,
                created_at=now,
                changes_summary="Initial version",
                snapshot_path="/snapshots/p1_v1.json",
            ),
        ]
        mock_shard.get_packet.return_value = packet
        mock_shard.get_packet_versions.return_value = versions

        response = client.get("/api/packets/p1/versions")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["version_number"] == 1


class TestStatisticsEndpoints:
    """Tests for statistics endpoints."""

    def test_get_statistics(self, client, mock_shard):
        """Test getting packet statistics."""
        stats = PacketStatistics(
            total_packets=100,
            by_status={"draft": 40, "finalized": 50, "shared": 10},
            total_contents=500,
            total_shares=25,
            avg_contents_per_packet=5.0,
        )
        mock_shard.get_statistics.return_value = stats

        response = client.get("/api/packets/stats/overview")
        assert response.status_code == 200
        data = response.json()
        assert data["total_packets"] == 100
        assert data["avg_contents_per_packet"] == 5.0


class TestFilteredListEndpoints:
    """Tests for filtered list endpoints."""

    def test_list_draft_packets(self, client, mock_shard):
        """Test listing draft packets."""
        now = datetime.utcnow()
        packets = [
            Packet(
                id="p1",
                name="Draft 1",
                status=PacketStatus.DRAFT,
                created_at=now,
                updated_at=now,
            ),
        ]
        mock_shard.list_packets.return_value = packets
        mock_shard.get_count.return_value = 1

        response = client.get("/api/packets/status/draft")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["status"] == "draft"

    def test_list_finalized_packets(self, client, mock_shard):
        """Test listing finalized packets."""
        now = datetime.utcnow()
        packets = [
            Packet(
                id="p1",
                name="Final 1",
                status=PacketStatus.FINALIZED,
                created_at=now,
                updated_at=now,
            ),
        ]
        mock_shard.list_packets.return_value = packets
        mock_shard.get_count.return_value = 1

        response = client.get("/api/packets/status/finalized")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1

    def test_list_shared_packets(self, client, mock_shard):
        """Test listing shared packets."""
        now = datetime.utcnow()
        packets = [
            Packet(
                id="p1",
                name="Shared 1",
                status=PacketStatus.SHARED,
                created_at=now,
                updated_at=now,
            ),
        ]
        mock_shard.list_packets.return_value = packets
        mock_shard.get_count.return_value = 1

        response = client.get("/api/packets/status/shared")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
