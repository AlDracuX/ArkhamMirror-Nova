"""
ArkhamMirror Shattered Frame

The core infrastructure for document intelligence.
Provides services that shards consume through a unified API.
"""

__version__ = "0.1.0"

# Shard interface
# Frame class
from .frame import ArkhamFrame, get_frame

# Pipeline
from .pipeline import (
    EmbedStage,
    IngestStage,
    OCRStage,
    ParseStage,
    PipelineCoordinator,
    PipelineError,
    PipelineStage,
    StageResult,
)

# Services
# Exceptions
from .services import (
    ConfigService,
    # Database
    DatabaseError,
    # Documents
    DocumentNotFoundError,
    EmbeddingError,
    # Entities
    EntityNotFoundError,
    EventDeliveryError,
    # Events
    EventValidationError,
    JSONExtractionError,
    # LLM
    LLMError,
    LLMRequestError,
    LLMUnavailableError,
    ProjectExistsError,
    # Projects
    ProjectNotFoundError,
    QueryExecutionError,
    QueueUnavailableError,
    SchemaExistsError,
    SchemaNotFoundError,
    # Vectors
    VectorServiceError,
    VectorStoreUnavailableError,
    # Workers
    WorkerError,
    WorkerNotFoundError,
)
from .shard_interface import ArkhamShard, ShardManifest

__all__ = [
    # Version
    "__version__",
    # Shard interface
    "ArkhamShard",
    "ShardManifest",
    # Frame
    "ArkhamFrame",
    "get_frame",
    # Services
    "ConfigService",
    # Exceptions
    "DatabaseError",
    "SchemaNotFoundError",
    "SchemaExistsError",
    "QueryExecutionError",
    "DocumentNotFoundError",
    "EntityNotFoundError",
    "ProjectNotFoundError",
    "ProjectExistsError",
    "VectorServiceError",
    "VectorStoreUnavailableError",
    "EmbeddingError",
    "LLMError",
    "LLMUnavailableError",
    "LLMRequestError",
    "JSONExtractionError",
    "EventValidationError",
    "EventDeliveryError",
    "WorkerError",
    "WorkerNotFoundError",
    "QueueUnavailableError",
    # Pipeline
    "PipelineStage",
    "PipelineError",
    "StageResult",
    "IngestStage",
    "OCRStage",
    "ParseStage",
    "EmbedStage",
    "PipelineCoordinator",
]
