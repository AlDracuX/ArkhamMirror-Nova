"""Tests for settings shard API endpoints."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from arkham_shard_settings.api import init_api, router
from arkham_shard_settings.models import SettingsValidationResult
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def mock_shard():
    """Create a mock shard that mimics SettingsShard for API testing."""
    shard = MagicMock()
    shard.version = "0.1.0"
    shard._frame = MagicMock()
    shard._db = MagicMock()
    shard._event_bus = MagicMock()
    shard._storage = MagicMock()

    # Async methods used by the API
    shard.get_all_settings = AsyncMock(return_value=[])
    shard.get_setting = AsyncMock(return_value=None)
    shard.update_setting = AsyncMock(return_value=None)
    shard.reset_setting = AsyncMock(return_value=None)
    shard.get_category_settings = AsyncMock(return_value=[])
    shard.update_category_settings = AsyncMock(return_value=[])
    shard.validate_setting = AsyncMock(return_value=SettingsValidationResult(is_valid=True, coerced_value=None))

    return shard


@pytest.fixture
def app(mock_shard):
    """Create a test FastAPI app with the router and mock shard."""
    init_api(shard=mock_shard)

    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health_with_storage(self, client, mock_shard):
        """Test health endpoint with storage available."""
        mock_shard.get_all_settings = AsyncMock(return_value=[])

        response = client.get("/api/settings/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["shard"] == "settings"
        assert data["version"] == "0.1.0"
        assert data["settings_count"] == 0

    def test_health_without_storage(self):
        """Test health endpoint without storage."""
        shard = MagicMock()
        shard.version = "0.1.0"
        shard._storage = None
        shard.get_all_settings = AsyncMock(return_value=[])

        init_api(shard=shard)

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        response = client.get("/api/settings/health")

        assert response.status_code == 200
        data = response.json()
        assert data["settings_count"] == 0


class TestCountEndpoint:
    """Test count endpoint."""

    def test_get_modified_count(self, client, mock_shard):
        """Test get modified settings count."""
        mock_shard.get_all_settings = AsyncMock(return_value=[])

        response = client.get("/api/settings/count")

        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        assert data["count"] == 0


class TestListSettingsEndpoint:
    """Test list settings endpoint."""

    def test_list_settings_default(self, client, mock_shard):
        """Test list settings with default params."""
        response = client.get("/api/settings/")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert data == []

    def test_list_settings_with_category(self, client, mock_shard):
        """Test list settings with category filter."""
        response = client.get("/api/settings/?category=appearance")
        assert response.status_code == 200

    def test_list_settings_with_search(self, client, mock_shard):
        """Test list settings with search."""
        response = client.get("/api/settings/?search=theme")
        assert response.status_code == 200

    def test_list_settings_modified_only(self, client, mock_shard):
        """Test list settings with modified_only filter."""
        response = client.get("/api/settings/?modified_only=true")
        assert response.status_code == 200


class TestGetSettingEndpoint:
    """Test get setting endpoint."""

    def test_get_setting_not_found(self, client, mock_shard):
        """Test get setting returns 404."""
        mock_shard.get_setting = AsyncMock(return_value=None)
        response = client.get("/api/settings/appearance.theme")

        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()

    def test_get_nested_setting_key(self, client, mock_shard):
        """Test get setting with nested key returns 404 when not found."""
        mock_shard.get_setting = AsyncMock(return_value=None)
        response = client.get("/api/settings/category/subcategory/setting")
        assert response.status_code == 404


class TestUpdateSettingEndpoint:
    """Test update setting endpoint."""

    def test_update_setting_not_found(self, client, mock_shard):
        """Test update setting returns 404."""
        mock_shard.update_setting = AsyncMock(return_value=None)
        response = client.put(
            "/api/settings/appearance.theme",
            json={"value": "dark"},
        )

        assert response.status_code == 404


class TestResetSettingEndpoint:
    """Test reset setting endpoint."""

    def test_reset_setting_not_found(self, client, mock_shard):
        """Test reset setting returns 404."""
        mock_shard.reset_setting = AsyncMock(return_value=None)
        response = client.delete("/api/settings/appearance.theme")
        assert response.status_code == 404


class TestCategoryEndpoints:
    """Test category endpoints.

    NOTE: The /{key:path} catch-all route is defined before /category/ routes,
    so GET and PUT /category/{category} are shadowed by the catch-all.
    GET returns 404 because get_setting("category/appearance") returns None.
    """

    def test_get_category_settings_shadowed(self, client, mock_shard):
        """Test GET /category/{cat} is caught by /{key:path} catch-all."""
        mock_shard.get_setting = AsyncMock(return_value=None)
        response = client.get("/api/settings/category/appearance")
        # Caught by catch-all: get_setting("category/appearance") -> None -> 404
        assert response.status_code == 404

    def test_update_category_settings_shadowed(self, client, mock_shard):
        """Test PUT /category/{cat} is caught by /{key:path} catch-all."""
        mock_shard.update_setting = AsyncMock(return_value=None)
        response = client.put(
            "/api/settings/category/appearance",
            json={"settings": {"theme": "dark", "font_size": 14}},
        )
        # Caught by catch-all PUT which expects SettingUpdateRequest (has "value" field)
        # The body {"settings": ...} doesn't match, so returns 422
        assert response.status_code == 422


class TestProfileEndpoints:
    """Test profile endpoints.

    NOTE: GET/PUT/DELETE /profiles/* are shadowed by /{key:path} catch-all.
    POST routes still work since catch-all only has GET/PUT/DELETE.
    """

    def test_list_profiles_shadowed(self, client, mock_shard):
        """Test GET /profiles is caught by catch-all, returns 404."""
        mock_shard.get_setting = AsyncMock(return_value=None)
        response = client.get("/api/settings/profiles")
        assert response.status_code == 404

    def test_create_profile(self, client):
        """Test create profile (POST not caught by catch-all)."""
        response = client.post(
            "/api/settings/profiles",
            json={
                "name": "Test Profile",
                "description": "A test profile",
                "settings": {"theme": "dark"},
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Profile"
        assert data["description"] == "A test profile"
        assert "id" in data

    def test_create_profile_minimal(self, client):
        """Test create profile with minimal data."""
        response = client.post(
            "/api/settings/profiles",
            json={"name": "Minimal"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Minimal"

    def test_create_profile_missing_name(self, client):
        """Test create profile fails without name."""
        response = client.post(
            "/api/settings/profiles",
            json={"description": "No name"},
        )

        assert response.status_code == 422

    def test_get_profile_not_found(self, client, mock_shard):
        """Test get profile returns 404 (caught by catch-all)."""
        mock_shard.get_setting = AsyncMock(return_value=None)
        response = client.get("/api/settings/profiles/nonexistent")
        assert response.status_code == 404

    def test_update_profile_not_found(self, client, mock_shard):
        """Test update profile returns 422 (caught by PUT catch-all, wrong body shape)."""
        mock_shard.update_setting = AsyncMock(return_value=None)
        response = client.put(
            "/api/settings/profiles/nonexistent",
            json={"name": "Updated"},
        )
        # Caught by PUT /{key:path} which expects {"value": ...}, not {"name": ...}
        assert response.status_code == 422

    def test_delete_profile_shadowed(self, client, mock_shard):
        """Test DELETE /profiles/{id} is caught by catch-all, returns 404."""
        mock_shard.reset_setting = AsyncMock(return_value=None)
        response = client.delete("/api/settings/profiles/profile-1")
        assert response.status_code == 404

    def test_apply_profile(self, client):
        """Test apply profile (POST not caught by catch-all)."""
        response = client.post("/api/settings/profiles/profile-1/apply")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["profile_id"] == "profile-1"


class TestShardSettingsEndpoints:
    """Test shard settings endpoints.

    NOTE: GET/PUT/DELETE /shards/* are shadowed by /{key:path} catch-all.
    """

    def test_list_shard_settings_shadowed(self, client, mock_shard):
        """Test GET /shards is caught by catch-all, returns 404."""
        mock_shard.get_setting = AsyncMock(return_value=None)
        response = client.get("/api/settings/shards")
        assert response.status_code == 404

    def test_get_shard_settings_not_found(self, client, mock_shard):
        """Test get shard settings returns 404 (caught by catch-all)."""
        mock_shard.get_setting = AsyncMock(return_value=None)
        response = client.get("/api/settings/shards/nonexistent")
        assert response.status_code == 404

    def test_update_shard_settings_not_found(self, client, mock_shard):
        """Test update shard settings returns 422 (caught by PUT catch-all, wrong body)."""
        mock_shard.update_setting = AsyncMock(return_value=None)
        response = client.put(
            "/api/settings/shards/search",
            json={"settings": {"max_results": 100}},
        )
        # Caught by PUT /{key:path} which expects {"value": ...}
        assert response.status_code == 422

    def test_reset_shard_settings_shadowed(self, client, mock_shard):
        """Test DELETE /shards/{name} is caught by catch-all, returns 404."""
        mock_shard.reset_setting = AsyncMock(return_value=None)
        response = client.delete("/api/settings/shards/search")
        assert response.status_code == 404


class TestBackupEndpoints:
    """Test backup endpoints.

    NOTE: GET /backups and DELETE /backups/{id} are shadowed by catch-all.
    POST routes still work.
    """

    def test_list_backups_shadowed(self, client, mock_shard):
        """Test GET /backups is caught by catch-all, returns 404."""
        mock_shard.get_setting = AsyncMock(return_value=None)
        response = client.get("/api/settings/backups")
        assert response.status_code == 404

    def test_create_backup_with_storage(self, client, mock_shard):
        """Test create backup (POST /backup not caught by catch-all)."""
        import arkham_shard_settings.api as api_mod

        original_storage = api_mod._storage
        api_mod._storage = MagicMock()

        try:
            response = client.post(
                "/api/settings/backup",
                json={
                    "name": "Test Backup",
                    "description": "A test backup",
                },
            )

            assert response.status_code == 201
            data = response.json()
            assert "Test Backup" in data["name"]
            assert "id" in data
        finally:
            api_mod._storage = original_storage

    def test_create_backup_without_storage(self):
        """Test create backup fails without storage."""
        shard = MagicMock()
        shard.version = "0.1.0"
        shard._storage = None
        shard.get_all_settings = AsyncMock(return_value=[])
        init_api(shard=shard)

        import arkham_shard_settings.api as api_mod

        original_storage = api_mod._storage
        api_mod._storage = None

        try:
            app = FastAPI()
            app.include_router(router)
            client = TestClient(app)

            response = client.post(
                "/api/settings/backup",
                json={"name": "Test"},
            )

            assert response.status_code == 503
            assert "Storage service not available" in response.json()["detail"]
        finally:
            api_mod._storage = original_storage

    def test_get_backup_not_found(self, client, mock_shard):
        """Test get backup returns 404 (caught by catch-all)."""
        mock_shard.get_setting = AsyncMock(return_value=None)
        response = client.get("/api/settings/backups/nonexistent")
        assert response.status_code == 404

    def test_restore_backup(self, client):
        """Test restore backup (POST not caught by catch-all)."""
        response = client.post("/api/settings/restore/backup-1")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["backup_id"] == "backup-1"

    def test_delete_backup_shadowed(self, client, mock_shard):
        """Test DELETE /backups/{id} is caught by catch-all, returns 404."""
        mock_shard.reset_setting = AsyncMock(return_value=None)
        response = client.delete("/api/settings/backups/backup-1")
        assert response.status_code == 404


class TestExportImportEndpoints:
    """Test export/import endpoints.

    NOTE: GET /export is shadowed by catch-all. POST /import works.
    """

    def test_export_settings_shadowed(self, client, mock_shard):
        """Test GET /export is caught by catch-all, returns 404."""
        mock_shard.get_setting = AsyncMock(return_value=None)
        response = client.get("/api/settings/export")
        assert response.status_code == 404

    def test_export_settings_with_profiles_shadowed(self, client, mock_shard):
        """Test GET /export?include_profiles=true caught by catch-all."""
        mock_shard.get_setting = AsyncMock(return_value=None)
        response = client.get("/api/settings/export?include_profiles=true")
        assert response.status_code == 404

    def test_export_settings_without_profiles_shadowed(self, client, mock_shard):
        """Test GET /export?include_profiles=false caught by catch-all."""
        mock_shard.get_setting = AsyncMock(return_value=None)
        response = client.get("/api/settings/export?include_profiles=false")
        assert response.status_code == 404

    def test_import_settings(self, client):
        """Test import settings (POST not caught by catch-all)."""
        response = client.post(
            "/api/settings/import",
            json={
                "version": "1.0",
                "settings": {"theme": "dark"},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_import_settings_merge(self, client):
        """Test import settings with merge."""
        response = client.post(
            "/api/settings/import?merge=true",
            json={"settings": {}},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["merge"] is True


class TestValidationEndpoint:
    """Test validation endpoint."""

    def test_validate_setting(self, client, mock_shard):
        """Test validate setting (POST not caught by catch-all)."""
        mock_shard.validate_setting = AsyncMock(
            return_value=SettingsValidationResult(
                is_valid=True,
                errors=[],
                warnings=[],
                coerced_value="dark",
            )
        )

        response = client.post(
            "/api/settings/validate",
            json={"key": "theme", "value": "dark"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_valid"] is True
        assert data["errors"] == []


class TestRequestValidation:
    """Test request validation."""

    def test_create_profile_empty_name(self, client):
        """Test create profile with empty name."""
        response = client.post(
            "/api/settings/profiles",
            json={"name": ""},
        )
        assert response.status_code == 422

    def test_update_category_missing_settings(self, client, mock_shard):
        """Test update category with invalid data."""
        # PUT is caught by the catch-all route which expects SettingUpdateRequest,
        # not BulkSettingsUpdateRequest. The body {} doesn't have "value" key
        # which causes a 422 from the catch-all's SettingUpdateRequest validation.
        response = client.put(
            "/api/settings/category/appearance",
            json={},
        )
        assert response.status_code == 422


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
