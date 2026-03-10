# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SHATTERED is a modular "distro-style" litigation analysis platform. **Shards** (feature modules) are loaded into an immutable **Frame** (core infrastructure) and rendered by a **Shell** (React UI). Follows the "Voltron" philosophy: plug-and-play components that combine into a unified application.

## Architecture

```
Frame (Python/FastAPI)  →  discovers shards via entry_points("arkham.shards")
  ├── services/: database, vectors, llm, events, workers, storage, etc.
  └── shard_interface.py: ArkhamShard ABC + ShardManifest v5 dataclasses

Shell (React/TypeScript/Vite)  →  renders navigation from shard manifests
  ├── pages/{shard-name}/: custom UI per shard
  └── pages/generic/: fallback list/form rendering

Shards (Python packages)  →  self-contained feature modules (~47 shards)
  ├── shard.py: extends ArkhamShard, owns its PostgreSQL schema
  ├── api.py: FastAPI routes mounted at /api/{name}
  └── shard.yaml: manifest v5 (navigation, events, capabilities)
```

## Critical Rules

- **Frame is IMMUTABLE** — shards MUST NOT modify `packages/arkham-frame/`
- **No shard-to-shard imports** — use EventBus for inter-shard communication
- **Schema isolation** — each shard owns its own PostgreSQL schema (`arkham_{name}`)
- **Shards depend on frame, never the reverse**

## Development Commands

```bash
# Backend
pip install -e packages/arkham-frame              # Install frame (editable)
pip install -e packages/arkham-shard-{name}       # Install a shard (editable)
python -m uvicorn arkham_frame.main:app --host 127.0.0.1 --port 8100  # Run backend

# Frontend
cd packages/arkham-shard-shell && npm install     # Install UI deps
cd packages/arkham-shard-shell && npm run dev     # Run Vite dev server
cd packages/arkham-shard-shell && npm run build   # Production build (tsc + vite build)

# Docker (full stack)
docker compose up -d                              # Start app + postgres (pgvector)
docker compose logs -f app                        # View logs
docker build -t shattered .                       # Rebuild image

# Quality
make lint                    # ruff check packages/
make lint-fix                # ruff check packages/ --fix
make format                  # ruff format packages/
make test                    # pytest packages/ -v --tb=short
make test-shard SHARD=ach    # Test single shard
make shell-lint              # ESLint on shell UI
make shell-format            # Prettier check
make check                   # All checks (lint + format + shell)
make fix                     # Auto-fix all
pre-commit run --all-files   # Pre-commit hooks (ruff + file hygiene)
```

## Testing

- pytest config in root `pyproject.toml` — asyncio_mode is `auto`, import-mode is `importlib`
- Tests live in `packages/arkham-shard-{name}/tests/`
- Run single test: `python -m pytest packages/arkham-shard-ach/tests/test_logic.py::TestClassName::test_name -v`

## Linting

- Python: ruff (config in root `pyproject.toml`) — line-length 120, target py310
- TypeScript: ESLint + Prettier (in `packages/arkham-shard-shell/`)
- Pre-commit: ruff lint+format, trailing whitespace, YAML/TOML/JSON checks, large file detection

## Key Files

| File | Purpose |
|------|---------|
| `packages/arkham-frame/arkham_frame/shard_interface.py` | `ArkhamShard` ABC and Manifest v5 dataclasses |
| `packages/arkham-frame/arkham_frame/main.py` | `load_shards()` — entry_point discovery and route mounting |
| `packages/arkham-frame/arkham_frame/frame.py` | `ArkhamFrame` — service container (db, vectors, llm, events, workers) |
| `packages/arkham-frame/arkham_frame/services/` | All frame services (database, vectors, llm, events, workers, storage) |
| `packages/arkham-shard-shell/src/pages/` | Per-shard UI pages + generic fallback rendering |
| `packages/arkham-shard-ach/` | Reference shard implementation |

## Shard Discovery

Shards register via `pyproject.toml` entry points:
```toml
[project.entry-points."arkham.shards"]
ach = "arkham_shard_ach:AchShard"
```
The frame discovers all installed shards at startup via `importlib.metadata.entry_points(group="arkham.shards")`.

## EventBus Communication

```python
# Publish
await self.frame.events.emit("ach.matrix.created", {"matrix_id": id}, source="ach-shard")

# Subscribe (in initialize())
self.frame.events.subscribe("document.processed", self.handle_document)
```

## Navigation Categories

Shards declare their category in `shard.yaml`: System, Data, Search, Analysis, Visualize, Export.

## Infrastructure

- **Database**: PostgreSQL 15 with pgvector (structured data + vector embeddings + job queue via SKIP LOCKED)
- **No Redis/Qdrant** — PostgreSQL handles everything
- **Embedding**: configurable model via `EMBED_MODEL` env var (default: all-MiniLM-L6-v2)
- **LLM**: optional, configured via `LLM_ENDPOINT` / `LM_STUDIO_URL` env vars
- **GPU**: Docker compose reserves NVIDIA GPU; set `TORCH_INDEX_URL` build arg for CPU-only
- **Frontend serving**: In production, FastAPI serves the built shell via `ARKHAM_SERVE_SHELL=true`

## New Shard Checklist

1. Copy `packages/arkham-shard-skeleton/` as template
2. Create `pyproject.toml` with `arkham.shards` entry point
3. Create `shard.yaml` manifest v5 (see `packages/arkham-shard-ach/shard.yaml` for reference)
4. Implement shard class extending `ArkhamShard` with `initialize()`, `shutdown()`, `get_routes()`
5. Add UI page in `packages/arkham-shard-shell/src/pages/{name}/`
6. Add package path to `pythonpath` in root `pyproject.toml` for pytest
7. Add COPY lines to `Dockerfile` (both shard directory and manifest)
