#!/usr/bin/env python3
"""Scaffold a new Arkham shard package.

Generates the full directory structure for a new shard based on the
arkham-shard-ach reference implementation. Creates both backend (Python)
and frontend (React/TypeScript) boilerplate.

Usage:
    python scripts/scaffold_shard.py \\
        --shard-name myshard \\
        --class-name My \\
        --label "My Shard" \\
        --description "Description of my shard" \\
        --category Analysis \\
        --order 35 \\
        --icon Star \\
        --api-prefix /api/myshard

    The class name is the base name -- 'Shard' is appended automatically.
    e.g. --class-name ACH produces ACHShard, --class-name My produces MyShard.
    If you pass --class-name MyShard, the trailing 'Shard' is stripped automatically.
"""

from __future__ import annotations

import argparse
import os
import sys
import textwrap
from pathlib import Path

# ---------------------------------------------------------------------------
# Resolve repo root relative to this script's location
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent


# ===================================================================
# Template generators
# ===================================================================


def gen_shard_yaml(
    shard_name: str,
    class_name: str,
    label: str,
    description: str,
    category: str,
    order: int,
    icon: str,
    api_prefix: str,
) -> str:
    return textwrap.dedent(f"""\
        # {class_name} Shard - {label}
        # Production Manifest v1.0
        # Compliant with shard_manifest_schema_prod.md

        name: {shard_name}
        version: "0.1.0"
        description: {description}
        entry_point: arkham_shard_{shard_name}:{class_name}Shard
        api_prefix: {api_prefix}
        requires_frame: ">=0.1.0"

        # Navigation - Shell integration
        navigation:
          category: {category}
          order: {order}
          icon: {icon}
          label: {label}
          route: /{shard_name}
          badge_endpoint: {api_prefix}/items/count
          badge_type: count
          sub_routes: []

        # Dependencies - Frame service names
        dependencies:
          services:
            - database
            - events
          optional:
            - llm
            - vectors
          shards: []

        # Capabilities
        capabilities:
          - item_management
          - data_export

        # Events - Format: {{shard}}.{{entity}}.{{action}}
        events:
          publishes:
            - {shard_name}.item.created
            - {shard_name}.item.updated
            - {shard_name}.item.deleted
          subscribes: []

        # State Management
        state:
          strategy: url
          url_params:
            - itemId
            - tab
            - view
          local_keys: []

        # UI Configuration
        ui:
          has_custom_ui: true
    """)


def gen_pyproject_toml(
    shard_name: str,
    class_name: str,
    description: str,
) -> str:
    return textwrap.dedent(f"""\
        [project]
        name = "arkham-shard-{shard_name}"
        version = "0.1.0"
        description = "{description}"
        license = {{text = "MIT"}}
        readme = "README.md"
        requires-python = ">=3.10"

        dependencies = [
            "arkham-frame>=0.1.0",
            "pydantic>=2.0.0",
        ]

        [project.optional-dependencies]
        dev = ["pytest", "pytest-asyncio", "black", "mypy"]

        [project.entry-points."arkham.shards"]
        {shard_name} = "arkham_shard_{shard_name}:{class_name}Shard"

        [build-system]
        requires = ["hatchling"]
        build-backend = "hatchling.build"
    """)


def gen_init_py(shard_name: str, class_name: str) -> str:
    return textwrap.dedent(f"""\
        \"\"\"ArkhamFrame {class_name} Shard - {class_name}.\"\"\"

        from .shard import {class_name}Shard

        __version__ = "0.1.0"
        __all__ = ["{class_name}Shard"]
    """)


def gen_shard_py(shard_name: str, class_name: str, description: str) -> str:
    schema_name = f"arkham_{shard_name}"
    return textwrap.dedent(f"""\
        \"\"\"{class_name} Shard - {description}.\"\"\"

        import logging
        from typing import Any, Dict, List, Optional

        from arkham_frame.shard_interface import ArkhamShard

        from .api import init_api, router

        logger = logging.getLogger(__name__)


        class {class_name}Shard(ArkhamShard):
            \"\"\"
            {class_name} shard for ArkhamFrame.

            {description}
            \"\"\"

            name = "{shard_name}"
            version = "0.1.0"
            description = "{description}"

            def __init__(self):
                super().__init__()  # Auto-loads manifest from shard.yaml
                self._frame = None
                self._db = None
                self._event_bus = None
                self._llm_service = None
                self._vectors_service = None

            async def initialize(self, frame) -> None:
                \"\"\"Initialize the {class_name} shard with Frame services.\"\"\"
                self._frame = frame

                logger.info("Initializing {class_name} Shard...")

                # Get Frame services
                self._db = frame.database
                self._event_bus = frame.get_service("events")
                self._llm_service = frame.get_service("llm")
                self._vectors_service = frame.get_service("vectors")

                # Create database schema
                await self._create_schema()

                # Initialize API with our instances
                init_api(
                    db=self._db,
                    event_bus=self._event_bus,
                    llm_service=self._llm_service,
                    shard=self,
                )

                # Register self in app state for API access
                if hasattr(frame, "app") and frame.app:
                    frame.app.state.{shard_name}_shard = self
                    logger.debug("{class_name} Shard registered on app.state")

                logger.info("{class_name} Shard initialized")

            async def shutdown(self) -> None:
                \"\"\"Clean up shard resources.\"\"\"
                logger.info("Shutting down {class_name} Shard...")
                logger.info("{class_name} Shard shutdown complete")

            def get_routes(self):
                \"\"\"Return FastAPI router for this shard.\"\"\"
                return router

            # --- Database Schema ---

            async def _create_schema(self) -> None:
                \"\"\"Create database schema for {class_name} tables.\"\"\"
                if not self._db:
                    logger.warning("Database service not available - persistence disabled")
                    return

                try:
                    # Create schema
                    await self._db.execute("CREATE SCHEMA IF NOT EXISTS {schema_name}")

                    # Items table
                    # tenant_id is nullable to allow operation without multi-tenancy
                    await self._db.execute(\"\"\"
                        CREATE TABLE IF NOT EXISTS {schema_name}.items (
                            id TEXT PRIMARY KEY,
                            tenant_id UUID,
                            title TEXT NOT NULL,
                            description TEXT,
                            project_id TEXT,
                            status TEXT DEFAULT 'active',
                            metadata JSONB DEFAULT '{{}}',
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            created_by TEXT
                        )
                    \"\"\")

                    # Add tenant_id column if it doesn't exist (migration for existing data)
                    await self._db.execute(\"\"\"
                        DO $$
                        BEGIN
                            IF NOT EXISTS (
                                SELECT 1 FROM information_schema.columns
                                WHERE table_schema = '{schema_name}'
                                  AND table_name = 'items'
                                  AND column_name = 'tenant_id'
                            ) THEN
                                ALTER TABLE {schema_name}.items ADD COLUMN tenant_id UUID;
                            END IF;
                        END $$;
                    \"\"\")

                    # Indexes
                    await self._db.execute(
                        "CREATE INDEX IF NOT EXISTS idx_{shard_name}_items_project "
                        "ON {schema_name}.items(project_id)"
                    )
                    await self._db.execute(
                        "CREATE INDEX IF NOT EXISTS idx_{shard_name}_items_tenant "
                        "ON {schema_name}.items(tenant_id)"
                    )

                    logger.info("{class_name} database schema created")

                except Exception as e:
                    logger.error(f"Failed to create {class_name} schema: {{e}}")
    """)


def gen_api_py(shard_name: str, class_name: str, api_prefix: str) -> str:
    return textwrap.dedent(f"""\
        \"\"\"{class_name} Shard API endpoints.\"\"\"

        import logging
        from typing import TYPE_CHECKING

        from fastapi import APIRouter, HTTPException, Query, Request
        from pydantic import BaseModel

        if TYPE_CHECKING:
            from .shard import {class_name}Shard

        logger = logging.getLogger(__name__)


        def get_shard(request: Request) -> "{class_name}Shard":
            \"\"\"Get the {class_name} shard instance from app state.\"\"\"
            shard = getattr(request.app.state, "{shard_name}_shard", None)
            if not shard:
                raise HTTPException(status_code=503, detail="{class_name} shard not available")
            return shard


        router = APIRouter(prefix="{api_prefix}", tags=["{shard_name}"])

        # Module-level references set during initialization
        _db = None
        _event_bus = None
        _llm_service = None
        _shard = None


        def init_api(
            db,
            event_bus,
            llm_service=None,
            shard=None,
        ):
            \"\"\"Initialize API with shard dependencies.\"\"\"
            global _db, _event_bus, _llm_service, _shard
            _db = db
            _event_bus = event_bus
            _llm_service = llm_service
            _shard = shard


        # --- Request/Response Models ---


        class CreateItemRequest(BaseModel):
            title: str
            description: str = ""
            project_id: str | None = None
            created_by: str | None = None


        class UpdateItemRequest(BaseModel):
            title: str | None = None
            description: str | None = None
            status: str | None = None


        # --- Endpoints ---


        @router.get("/items")
        async def list_items(
            project_id: str | None = None,
            status: str | None = None,
        ):
            \"\"\"List items with optional filtering.\"\"\"
            if not _db:
                raise HTTPException(status_code=503, detail="{class_name} service not initialized")

            query = "SELECT * FROM arkham_{shard_name}.items WHERE 1=1"
            params: dict = {{}}

            if project_id:
                query += " AND project_id = :project_id"
                params["project_id"] = project_id
            if status:
                query += " AND status = :status"
                params["status"] = status

            query += " ORDER BY created_at DESC"

            rows = await _db.fetch_all(query, params)
            return {{
                "count": len(rows),
                "items": [dict(row) for row in rows],
            }}


        @router.get("/items/count")
        async def get_items_count():
            \"\"\"Get count of active items for badge display.\"\"\"
            if not _db:
                return {{"count": 0}}

            row = await _db.fetch_one(
                "SELECT COUNT(*) as cnt FROM arkham_{shard_name}.items WHERE status = 'active'"
            )
            return {{"count": row["cnt"] if row else 0}}


        @router.get("/items/{{item_id}}")
        async def get_item(item_id: str):
            \"\"\"Get an item by ID.\"\"\"
            if not _db:
                raise HTTPException(status_code=503, detail="{class_name} service not initialized")

            row = await _db.fetch_one(
                "SELECT * FROM arkham_{shard_name}.items WHERE id = :id",
                {{"id": item_id}},
            )
            if not row:
                raise HTTPException(status_code=404, detail=f"Item not found: {{item_id}}")

            return dict(row)


        @router.post("/items")
        async def create_item(request: CreateItemRequest):
            \"\"\"Create a new item.\"\"\"
            import uuid

            if not _db:
                raise HTTPException(status_code=503, detail="{class_name} service not initialized")

            item_id = str(uuid.uuid4())

            # Get tenant_id for multi-tenancy
            tenant_id = _shard.get_tenant_id_or_none() if _shard else None

            await _db.execute(
                \"\"\"
                INSERT INTO arkham_{shard_name}.items
                (id, tenant_id, title, description, project_id, created_by)
                VALUES (:id, :tenant_id, :title, :description, :project_id, :created_by)
                \"\"\",
                {{
                    "id": item_id,
                    "tenant_id": str(tenant_id) if tenant_id else None,
                    "title": request.title,
                    "description": request.description,
                    "project_id": request.project_id,
                    "created_by": request.created_by,
                }},
            )

            # Emit event
            if _event_bus:
                await _event_bus.emit(
                    "{shard_name}.item.created",
                    {{"item_id": item_id, "title": request.title}},
                    source="{shard_name}-shard",
                )

            return {{"item_id": item_id, "title": request.title, "status": "active"}}


        @router.put("/items/{{item_id}}")
        async def update_item(item_id: str, request: UpdateItemRequest):
            \"\"\"Update an item.\"\"\"
            if not _db:
                raise HTTPException(status_code=503, detail="{class_name} service not initialized")

            # Build dynamic UPDATE
            sets = []
            params: dict = {{"id": item_id}}
            if request.title is not None:
                sets.append("title = :title")
                params["title"] = request.title
            if request.description is not None:
                sets.append("description = :description")
                params["description"] = request.description
            if request.status is not None:
                sets.append("status = :status")
                params["status"] = request.status

            if not sets:
                raise HTTPException(status_code=400, detail="No fields to update")

            sets.append("updated_at = CURRENT_TIMESTAMP")
            set_clause = ", ".join(sets)

            await _db.execute(
                f"UPDATE arkham_{shard_name}.items SET {{set_clause}} WHERE id = :id",
                params,
            )

            # Emit event
            if _event_bus:
                await _event_bus.emit(
                    "{shard_name}.item.updated",
                    {{"item_id": item_id}},
                    source="{shard_name}-shard",
                )

            return {{"item_id": item_id, "status": "updated"}}


        @router.delete("/items/{{item_id}}")
        async def delete_item(item_id: str):
            \"\"\"Delete an item.\"\"\"
            if not _db:
                raise HTTPException(status_code=503, detail="{class_name} service not initialized")

            await _db.execute(
                "DELETE FROM arkham_{shard_name}.items WHERE id = :id",
                {{"id": item_id}},
            )

            # Emit event
            if _event_bus:
                await _event_bus.emit(
                    "{shard_name}.item.deleted",
                    {{"item_id": item_id}},
                    source="{shard_name}-shard",
                )

            return {{"status": "deleted", "item_id": item_id}}
    """)


def gen_models_py(shard_name: str, class_name: str) -> str:
    return textwrap.dedent(f"""\
        \"\"\"Data models for the {class_name} Shard.\"\"\"

        from dataclasses import dataclass, field
        from datetime import datetime
        from enum import Enum
        from typing import Any, Optional


        class ItemStatus(str, Enum):
            \"\"\"Status of an item.\"\"\"

            ACTIVE = "active"
            ARCHIVED = "archived"
            DELETED = "deleted"


        @dataclass
        class Item:
            \"\"\"A {class_name} item with multi-tenancy support.\"\"\"

            id: str
            tenant_id: str | None = None
            title: str = ""
            description: str = ""
            project_id: str | None = None
            status: ItemStatus = ItemStatus.ACTIVE
            metadata: dict[str, Any] = field(default_factory=dict)
            created_at: datetime = field(default_factory=datetime.utcnow)
            updated_at: datetime = field(default_factory=datetime.utcnow)
            created_by: str | None = None
    """)


def gen_test_initialize_py(shard_name: str, class_name: str) -> str:
    return textwrap.dedent(f"""\
        \"\"\"
        {class_name} Shard - Initialization Tests

        Tests for {class_name}Shard with mocked Frame services.
        \"\"\"

        from unittest.mock import AsyncMock, MagicMock

        import pytest
        from arkham_shard_{shard_name}.shard import {class_name}Shard


        # === Fixtures ===


        @pytest.fixture
        def mock_events():
            \"\"\"Create a mock events service.\"\"\"
            events = AsyncMock()
            events.emit = AsyncMock()
            events.subscribe = AsyncMock()
            events.unsubscribe = AsyncMock()
            return events


        @pytest.fixture
        def mock_db():
            \"\"\"Create a mock database service.\"\"\"
            db = AsyncMock()
            db.execute = AsyncMock()
            db.fetch_all = AsyncMock(return_value=[])
            db.fetch_one = AsyncMock(return_value=None)
            return db


        @pytest.fixture
        def mock_frame(mock_events, mock_db):
            \"\"\"Create a mock Frame with all services.\"\"\"
            frame = MagicMock()
            frame.database = mock_db
            frame.get_service = MagicMock(
                side_effect=lambda name: {{
                    "events": mock_events,
                    "llm": None,
                    "database": mock_db,
                    "vectors": None,
                    "documents": None,
                }}.get(name)
            )
            return frame


        # === Tests ===


        class TestShardInitialization:
            \"\"\"Tests for shard initialization and shutdown.\"\"\"

            def test_shard_class_attributes(self):
                \"\"\"Verify shard has required class-level attributes.\"\"\"
                shard = {class_name}Shard()
                assert shard.name == "{shard_name}"
                assert shard.version == "0.1.0"
                assert shard.description != ""

            @pytest.mark.asyncio
            async def test_initialize(self, mock_frame):
                \"\"\"Test shard initialization with Frame.\"\"\"
                shard = {class_name}Shard()
                await shard.initialize(mock_frame)

                assert shard._frame is mock_frame
                assert shard._db is not None
                assert shard._event_bus is not None

            @pytest.mark.asyncio
            async def test_schema_creation(self, mock_frame, mock_db):
                \"\"\"Test database schema is created on init.\"\"\"
                shard = {class_name}Shard()
                await shard.initialize(mock_frame)

                # Verify CREATE SCHEMA was called
                calls = [str(c) for c in mock_db.execute.call_args_list]
                schema_calls = [c for c in calls if "CREATE SCHEMA" in c]
                assert len(schema_calls) > 0, "CREATE SCHEMA not called"

            @pytest.mark.asyncio
            async def test_shutdown(self, mock_frame):
                \"\"\"Test shard shutdown.\"\"\"
                shard = {class_name}Shard()
                await shard.initialize(mock_frame)
                await shard.shutdown()
                # Should not raise

            def test_get_routes(self):
                \"\"\"Test that get_routes returns the router.\"\"\"
                shard = {class_name}Shard()
                routes = shard.get_routes()
                assert routes is not None
    """)


def gen_tests_init_py() -> str:
    return ""


# ===================================================================
# Frontend templates
# ===================================================================


def gen_frontend_index_ts(class_name: str) -> str:
    return textwrap.dedent(f"""\
        export {{ {class_name}Page }} from './{class_name}Page';
    """)


def gen_frontend_types_ts(shard_name: str, class_name: str) -> str:
    return textwrap.dedent(f"""\
        /**
         * {class_name} Types
         *
         * Type definitions matching the backend {class_name} shard models.
         */

        // Item status
        export type ItemStatus = 'active' | 'archived' | 'deleted';

        // Item in the {class_name} shard
        export interface {class_name}Item {{
          id: string;
          tenant_id: string | null;
          title: string;
          description: string;
          project_id: string | null;
          status: ItemStatus;
          metadata: Record<string, unknown>;
          created_at: string;
          updated_at: string;
          created_by: string | null;
        }}

        // List item (summary view)
        export interface {class_name}ListItem {{
          id: string;
          title: string;
          description: string;
          status: ItemStatus;
          created_at: string;
          updated_at: string;
        }}

        // API response types
        export interface {class_name}ListResponse {{
          count: number;
          items: {class_name}ListItem[];
        }}

        export const STATUS_OPTIONS: {{ value: ItemStatus; label: string }}[] = [
          {{ value: 'active', label: 'Active' }},
          {{ value: 'archived', label: 'Archived' }},
          {{ value: 'deleted', label: 'Deleted' }},
        ];
    """)


def gen_frontend_api_ts(shard_name: str, class_name: str, api_prefix: str) -> str:
    return textwrap.dedent(f"""\
        /**
         * {class_name} API Service
         *
         * API client for the {class_name} shard backend.
         */

        import type {{
          {class_name}Item,
          {class_name}ListResponse,
        }} from './types';

        const API_PREFIX = '{api_prefix}';

        // Generic fetch wrapper with error handling
        async function fetchAPI<T>(endpoint: string, options?: RequestInit): Promise<T> {{
          const response = await fetch(`${{API_PREFIX}}${{endpoint}}`, {{
            headers: {{
              'Content-Type': 'application/json',
              ...options?.headers,
            }},
            ...options,
          }});

          if (!response.ok) {{
            const error = await response.json().catch(() => ({{ detail: response.statusText }}));
            throw new Error(error.detail || error.message || `HTTP ${{response.status}}`);
          }}

          return response.json();
        }}

        // ============================================
        // Item Operations
        // ============================================

        export async function listItems(
          projectId?: string,
          status?: string
        ): Promise<{class_name}ListResponse> {{
          const params = new URLSearchParams();
          if (projectId) params.set('project_id', projectId);
          if (status) params.set('status', status);

          const query = params.toString();
          return fetchAPI<{class_name}ListResponse>(`/items${{query ? `?${{query}}` : ''}}`);
        }}

        export async function getItem(itemId: string): Promise<{class_name}Item> {{
          return fetchAPI<{class_name}Item>(`/items/${{itemId}}`);
        }}

        export async function createItem(data: {{
          title: string;
          description?: string;
          project_id?: string;
          created_by?: string;
        }}): Promise<{{ item_id: string; title: string; status: string }}> {{
          return fetchAPI('/items', {{
            method: 'POST',
            body: JSON.stringify(data),
          }});
        }}

        export async function updateItem(
          itemId: string,
          data: {{
            title?: string;
            description?: string;
            status?: string;
          }}
        ): Promise<{{ item_id: string; status: string }}> {{
          return fetchAPI(`/items/${{itemId}}`, {{
            method: 'PUT',
            body: JSON.stringify(data),
          }});
        }}

        export async function deleteItem(
          itemId: string
        ): Promise<{{ status: string; item_id: string }}> {{
          return fetchAPI(`/items/${{itemId}}`, {{
            method: 'DELETE',
          }});
        }}
    """)


def gen_frontend_page_tsx(shard_name: str, class_name: str, label: str, icon: str) -> str:
    return textwrap.dedent(f"""\
        /**
         * {class_name}Page - {label} shard
         *
         * Main page component for the {label} shard.
         */

        import {{ useState, useEffect, useCallback }} from 'react';
        import {{ useSearchParams }} from 'react-router-dom';
        import {{ useToast }} from '../../context/ToastContext';
        import {{ Icon }} from '../../components/common/Icon';
        import {{ LoadingSkeleton }} from '../../components/common/LoadingSkeleton';

        import * as api from './api';
        import type {{ {class_name}ListItem }} from './types';

        export function {class_name}Page() {{
          const [searchParams] = useSearchParams();
          const itemId = searchParams.get('itemId');

          if (itemId) {{
            return <ItemDetailView itemId={{itemId}} />;
          }}

          return <ItemListView />;
        }}

        // ============================================
        // List View
        // ============================================

        function ItemListView() {{
          const {{ toast }} = useToast();
          const [items, setItems] = useState<{class_name}ListItem[]>([]);
          const [loading, setLoading] = useState(true);

          const loadItems = useCallback(async () => {{
            try {{
              setLoading(true);
              const data = await api.listItems();
              setItems(data.items);
            }} catch (err) {{
              toast.error(`Failed to load items: ${{err}}`);
            }} finally {{
              setLoading(false);
            }}
          }}, [toast]);

          useEffect(() => {{
            loadItems();
          }}, [loadItems]);

          if (loading) {{
            return <LoadingSkeleton />;
          }}

          return (
            <div className="{shard_name}-page">
              <header className="page-header" style={{{{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1.5rem' }}}}>
                <Icon name="{icon}" size={{28}} />
                <h1 style={{{{ margin: 0 }}}}>{label}</h1>
                <span style={{{{ color: 'var(--arkham-text-muted)', fontSize: '0.875rem' }}}}>
                  {{items.length}} items
                </span>
              </header>

              {{items.length === 0 ? (
                <div style={{{{ textAlign: 'center', padding: '3rem', color: 'var(--arkham-text-muted)' }}}}>
                  <Icon name="{icon}" size={{48}} />
                  <p>No items yet. Create your first item to get started.</p>
                </div>
              ) : (
                <div style={{{{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}}}>
                  {{items.map((item) => (
                    <div
                      key={{item.id}}
                      style={{{{
                        padding: '1rem',
                        background: 'var(--arkham-bg-secondary)',
                        borderRadius: '0.5rem',
                        border: '1px solid var(--arkham-border)',
                        cursor: 'pointer',
                      }}}}
                    >
                      <h3 style={{{{ margin: '0 0 0.25rem 0' }}}}>{{item.title}}</h3>
                      <p style={{{{ margin: 0, color: 'var(--arkham-text-muted)', fontSize: '0.875rem' }}}}>
                        {{item.description || 'No description'}}
                      </p>
                    </div>
                  ))}}
                </div>
              )}}
            </div>
          );
        }}

        // ============================================
        // Detail View
        // ============================================

        function ItemDetailView({{ itemId }}: {{ itemId: string }}) {{
          const {{ toast }} = useToast();
          const [item, setItem] = useState<Record<string, unknown> | null>(null);
          const [loading, setLoading] = useState(true);

          useEffect(() => {{
            (async () => {{
              try {{
                setLoading(true);
                const data = await api.getItem(itemId);
                setItem(data as unknown as Record<string, unknown>);
              }} catch (err) {{
                toast.error(`Failed to load item: ${{err}}`);
              }} finally {{
                setLoading(false);
              }}
            }})();
          }}, [itemId, toast]);

          if (loading) {{
            return <LoadingSkeleton />;
          }}

          if (!item) {{
            return <div>Item not found</div>;
          }}

          return (
            <div className="{shard_name}-detail">
              <header className="page-header" style={{{{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1.5rem' }}}}>
                <Icon name="{icon}" size={{28}} />
                <h1 style={{{{ margin: 0 }}}}>{{String(item.title)}}</h1>
              </header>
              <p>{{String(item.description || 'No description')}}</p>
            </div>
          );
        }}
    """)


# ===================================================================
# Main logic
# ===================================================================


def scaffold(args: argparse.Namespace) -> None:
    shard_name = args.shard_name
    class_name = args.class_name
    # Normalize: strip trailing "Shard" if user included it (e.g. "MyShard" -> "My")
    # The templates append "Shard" themselves (matching ACH -> ACHShard convention)
    if class_name.endswith("Shard") and len(class_name) > 5:
        class_name = class_name[:-5]
    label = args.label
    description = args.description
    category = args.category
    order = args.order
    icon = args.icon
    api_prefix = args.api_prefix
    force = args.force

    pkg_name = f"arkham_shard_{shard_name}"
    pkg_dir = REPO_ROOT / "packages" / f"arkham-shard-{shard_name}"
    src_dir = pkg_dir / pkg_name
    tests_dir = pkg_dir / "tests"
    fe_dir = REPO_ROOT / "packages" / "arkham-shard-shell" / "src" / "pages" / shard_name

    # Safety check: do not overwrite without --force
    if pkg_dir.exists() and not force:
        print(f"ERROR: Package directory already exists: {pkg_dir}")
        print("       Use --force to overwrite.")
        sys.exit(1)

    if fe_dir.exists() and not force:
        print(f"ERROR: Frontend directory already exists: {fe_dir}")
        print("       Use --force to overwrite.")
        sys.exit(1)

    # --- Create backend structure ---
    print(f"Creating backend package: {pkg_dir}")
    src_dir.mkdir(parents=True, exist_ok=True)
    tests_dir.mkdir(parents=True, exist_ok=True)

    files: dict[Path, str] = {
        # Backend
        pkg_dir / "shard.yaml": gen_shard_yaml(
            shard_name, class_name, label, description, category, order, icon, api_prefix
        ),
        pkg_dir / "pyproject.toml": gen_pyproject_toml(shard_name, class_name, description),
        src_dir / "__init__.py": gen_init_py(shard_name, class_name),
        src_dir / "shard.py": gen_shard_py(shard_name, class_name, description),
        src_dir / "api.py": gen_api_py(shard_name, class_name, api_prefix),
        src_dir / "models.py": gen_models_py(shard_name, class_name),
        tests_dir / "__init__.py": gen_tests_init_py(),
        tests_dir / "test_initialize.py": gen_test_initialize_py(shard_name, class_name),
    }

    # --- Create frontend structure ---
    print(f"Creating frontend pages: {fe_dir}")
    fe_dir.mkdir(parents=True, exist_ok=True)

    files.update(
        {
            fe_dir / "index.ts": gen_frontend_index_ts(class_name),
            fe_dir / "types.ts": gen_frontend_types_ts(shard_name, class_name),
            fe_dir / "api.ts": gen_frontend_api_ts(shard_name, class_name, api_prefix),
            fe_dir / f"{class_name}Page.tsx": gen_frontend_page_tsx(shard_name, class_name, label, icon),
        }
    )

    # --- Write all files ---
    for filepath, content in files.items():
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")
        rel = filepath.relative_to(REPO_ROOT)
        print(f"  Created: {rel}")

    print()
    print(f"Shard '{shard_name}' scaffolded successfully!")
    print()
    print("Next steps:")
    print(f"  1. Install the shard:  pip install -e packages/arkham-shard-{shard_name}")
    print(f"  2. Add route to App.tsx for /{shard_name}")
    print("  3. Customize models, API, and frontend pages")
    print(f"  4. Run tests:  pytest packages/arkham-shard-{shard_name}/tests/")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scaffold a new Arkham shard package",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Example:
              python scripts/scaffold_shard.py \\
                  --shard-name myshard \\
                  --class-name MyShard \\
                  --label "My Shard" \\
                  --description "Description of my shard" \\
                  --category Analysis \\
                  --order 35 \\
                  --icon Star \\
                  --api-prefix /api/myshard
        """),
    )

    parser.add_argument("--shard-name", required=True, help="Snake_case shard name (e.g. 'myshard')")
    parser.add_argument(
        "--class-name",
        required=True,
        help="PascalCase base name without 'Shard' suffix (e.g. 'ACH' for ACHShard, 'MyAnalysis' for MyAnalysisShard)",
    )
    parser.add_argument("--label", required=True, help="Human-readable label (e.g. 'My Shard')")
    parser.add_argument("--description", required=True, help="Short description of the shard")
    parser.add_argument(
        "--category",
        required=True,
        help="Navigation category (System, Data, Search, Analysis, Visualize, Export)",
    )
    parser.add_argument("--order", required=True, type=int, help="Navigation order within category")
    parser.add_argument("--icon", required=True, help="Lucide icon name (e.g. 'Star', 'Scale')")
    parser.add_argument("--api-prefix", required=True, help="API route prefix (e.g. '/api/myshard')")
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Overwrite existing directories",
    )

    args = parser.parse_args()
    scaffold(args)


if __name__ == "__main__":
    main()
