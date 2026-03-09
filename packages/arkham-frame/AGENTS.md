# ARKHAM FRAME KNOWLEDGE BASE

## OVERVIEW
The ArkhamFrame is the immutable core infrastructure providing shared services and shard orchestration for the SHATTERED platform.

## STRUCTURE
```
.
├── api/             # FastAPI route definitions for frame services
├── auth/            # Multi-tenant authentication and security
├── middleware/      # Tenant context and security headers
├── models/          # Shared Pydantic schemas and database models
├── pipeline/        # Core document processing workflows
├── services/        # 17 core service implementations
└── workers/         # Job queue management and worker pools
```

## WHERE TO LOOK
| Component | Location | Role |
|-----------|----------|------|
| Shard Interface | `/mnt/media_backup/PROJECTS/ArkhamMirror-Nova/packages/arkham-frame/arkham_frame/shard_interface.py` | Contract all shards must implement |
| Service Registry | `/mnt/media_backup/PROJECTS/ArkhamMirror-Nova/packages/arkham-frame/arkham_frame/frame.py` | Singleton holding service instances |
| Shard Loader | `/mnt/media_backup/PROJECTS/ArkhamMirror-Nova/packages/arkham-frame/arkham_frame/main.py` | Entry-point discovery and loading logic |
| Core Services | `/mnt/media_backup/PROJECTS/ArkhamMirror-Nova/packages/arkham-frame/arkham_frame/services/` | Implementations for all platform features |

## CONVENTIONS
- Frame Immutability: Shards must never modify frame code or state directly.
- Shard Isolation: Direct imports between shards are strictly forbidden. Use the EventBus for communication.
- Absolute Paths: Always use absolute paths starting with /mnt/media_backup/PROJECTS/ArkhamMirror-Nova/.
- Service Access: Shards must access all platform functionality through the frame object provided during initialization.

## ANTI-PATTERNS
- Direct Shard Imports: Importing any module from arkham-shard-* into the frame or other shards.
- Relative Paths: Using ../ or ./ for file references outside the current shard.
- Frame Modification: Attempting to monkey-patch or extend frame services from within a shard.

## SERVICES MAP
| Service | Implementation | Primary Role |
|---------|----------------|--------------|
| `DatabaseService` | `services/database.py` | PostgreSQL access with per-shard schema isolation |
| `VectorService` | `services/vectors.py` | pgvector-based storage and similarity search |
| `LLMService` | `services/llm.py` | OpenAI-compatible model abstraction and extraction |
| `EventBus` | `services/events.py` | Asynchronous pub/sub messaging for shard decoupling |
| `WorkerService` | `services/workers.py` | Job queue management with specialized CPU/GPU pools |

## SHARD LOADING
Shards are discovered dynamically using Python entry points registered in the arkham.shards group within each shard's pyproject.toml. The load_shards function in arkham_frame/main.py performs the following sequence:
1. Discovers all entry points for arkham.shards.
2. Loads the shard class and instantiates it with no arguments.
3. Calls await shard.initialize(frame) passing the singleton frame instance.
4. Registers the shard's FastAPI router if shard.get_routes() returns one.
5. Adds the initialized shard to the frame.shards registry.
