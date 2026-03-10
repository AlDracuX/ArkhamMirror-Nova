# PROJECT KNOWLEDGE BASE

**Generated:** 2026-03-09T14:10:55Z
**Commit:** 960522f
**Branch:** main

## OVERVIEW
SHATTERED is a modular "Voltron-style" platform for document analysis. It uses an immutable **ArkhamFrame** (Python core) to load plug-and-play **Shards** (feature modules) rendered via **arkham-shell** (React frontend).

## STRUCTURE
```
.
├── packages/
│   ├── arkham-frame/          # IMMUTABLE core infrastructure (DB, LLM, Events)
│   ├── arkham-shard-shell/    # React/TS UI renderer and navigation
│   └── arkham-shard-*/        # 25+ self-contained feature modules (ACH, Graph, etc.)
├── docs/                      # Architecture and shard development guides
├── migrations/                # Global database consolidation scripts
└── Makefile                   # Centralized dev/test/build entry point
```

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Core Infrastructure | `packages/arkham-frame/AGENTS.md` | Database, Vector, LLM, Workers, Events |
| UI & Navigation | `packages/arkham-shard-shell/AGENTS.md` | Shell rendering, hooks, and URL state |
| Analytic Techniques | `packages/arkham-shard-ach/AGENTS.md` | Reference ACH implementation and AI scoring |
| Shard Interface | `packages/arkham-frame/arkham_frame/shard_interface.py` | `ArkhamShard` ABC & Manifest v5 |
| UI Rendering | `packages/arkham-shard-shell/src/pages/generic/` | Generic list/form fallback logic |

## CODE MAP
| Symbol | Type | Location | Role |
|--------|------|----------|------|
| `ArkhamShard` | Class | `arkham_frame/shard_interface.py` | Base class all shards must implement |
| `ShardManifest` | Class | `arkham_frame/shard_interface.py` | Shard configuration schema (v5) |
| `EventBus` | Service | `arkham_frame/services/events.py` | Primary inter-shard communication channel |
| `load_shards` | Function | `arkham_frame/main.py` | Dynamic entry-point discovery & loading |

## CONVENTIONS
- **Immutable Frame**: Shards MUST NOT modify `arkham-frame`.
- **Shard Isolation**: No direct imports between shards. Use `EventBus` for coupling.
- **Self-Contained**: Shards include both backend (Python) and frontend (React pages).
- **Schema Isolation**: Each shard owns its PostgreSQL schema (`arkham_{shard_name}`).

## ANTI-PATTERNS (THIS PROJECT)
- **Direct Shard Imports**: Forbidden. Use Pub/Sub via `EventBus`.
- **Relative Paths**: Always use absolute paths (starting with `/`).
- **Emoji Usage**: Forbidden in system-level documentation and agent responses.
- **Manual DB Migrations**: Shards should define schema in `initialize()`.

## COMMANDS
```bash
make install-all    # Install frame and all shards in editable mode
make run-frame      # Start the FastAPI backend (Port 8100)
make run-shell      # Start the Vite dev server
make test-shard S=ach # Run tests for a specific shard
make pmat           # Full quality gate (complexity, SATD, security, entropy)
make pmat-score     # Repo health score (0-100)
make pmat-hotspots  # Top complexity hotspots
```

## QUALITY TOOLS
- **PMAT** (`pmat`): Code quality analysis — complexity, tech debt, dead code, security. Config in `.pmat-gates.toml`.
- **Ruff**: Python linting and formatting. Config in root `pyproject.toml`.
- **ESLint/Prettier**: TypeScript linting in `packages/arkham-shard-shell/`.
- When creating or modifying shards, run `make pmat-complexity` to check cyclomatic complexity stays under 50 per function.

## NOTES
- **Voltron Philosophy**: Every feature is a shard; the shell is just a lens.
- **Local-First**: Designed for air-gapped or local-only operation with pgvector.
