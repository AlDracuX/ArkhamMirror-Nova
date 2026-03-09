"""
ArkhamMirror Shattered Frame - Services

Core services that Frame provides to shards.
"""

from .ai_analyst import (
    AIJuniorAnalystService,
    AnalysisDepth,
    AnalysisRequest,
    AnalysisResponse,
)
from .ai_analyst import (
    Message as AnalystMessage,
)
from .chunks import (
    ChunkConfig,
    ChunkService,
    ChunkServiceError,
    ChunkStrategy,
    TextChunk,
    TokenizerError,
)
from .config import ConfigService
from .database import (
    DatabaseError,
    DatabaseService,
    QueryExecutionError,
    SchemaExistsError,
    SchemaNotFoundError,
)
from .documents import (
    BatchResult,
    Chunk,
    Document,
    DocumentError,
    DocumentNotFoundError,
    DocumentService,
    DocumentStatus,
    Page,
    SearchResult,
)
from .entities import (
    CanonicalEntity,
    CanonicalNotFoundError,
    CoOccurrence,
    Entity,
    EntityError,
    EntityNotFoundError,
    EntityRelationship,
    EntityService,
    EntityType,
    RelationshipNotFoundError,
    RelationshipType,
)
from .events import EventBus, EventDeliveryError, EventValidationError
from .export import (
    ExportError,
    ExportFormat,
    ExportFormatError,
    ExportOptions,
    ExportRenderError,
    ExportResult,
    ExportService,
)
from .export import (
    TemplateNotFoundError as ExportTemplateNotFoundError,
)
from .llm import (
    JSONExtractionError,
    LLMError,
    LLMRequestError,
    LLMResponse,
    LLMService,
    LLMUnavailableError,
    PromptNotFoundError,
    PromptTemplate,
    StreamChunk,
)
from .notifications import (
    ChannelNotFoundError,
    ChannelType,
    ConfigurationError,
    DeliveryError,
    DeliveryStatus,
    Notification,
    NotificationError,
    NotificationService,
    NotificationType,
)
from .projects import (
    Project,
    ProjectError,
    ProjectExistsError,
    ProjectNotFoundError,
    ProjectService,
    ProjectStats,
)
from .resources import (
    CPUAllocationError,
    GPUMemoryError,
    PoolConfig,
    ResourceError,
    ResourceService,
    ResourceTier,
    SystemResources,
)
from .scheduler import (
    InvalidScheduleError,
    JobExecutionError,
    JobNotFoundError,
    JobResult,
    JobStatus,
    ScheduledJob,
    SchedulerError,
    SchedulerService,
    TriggerType,
)
from .storage import (
    FileInfo,
    InvalidPathError,
    StorageError,
    StorageFullError,
    StorageService,
    StorageStats,
)
from .storage import (
    FileNotFoundError as StorageFileNotFoundError,
)
from .templates import (
    RenderResult,
    Template,
    TemplateError,
    TemplateNotFoundError,
    TemplateRenderError,
    TemplateService,
    TemplateSyntaxError,
)
from .vectors import (
    EMBEDDING_DIMENSIONS,
    CollectionExistsError,
    CollectionInfo,
    CollectionNotFoundError,
    DistanceMetric,
    EmbeddingError,
    VectorDimensionError,
    VectorPoint,
    VectorService,
    VectorServiceError,
    VectorStoreUnavailableError,
)
from .vectors import (
    SearchResult as VectorSearchResult,
)
from .workers import QueueUnavailableError, WorkerError, WorkerNotFoundError, WorkerService

__all__ = [
    # Services
    "ConfigService",
    "DatabaseService",
    "DocumentService",
    "EntityService",
    "ProjectService",
    "VectorService",
    "LLMService",
    "ChunkService",
    "EventBus",
    "WorkerService",
    "ResourceService",
    "StorageService",
    "ExportService",
    "TemplateService",
    "NotificationService",
    "SchedulerService",
    "AIJuniorAnalystService",
    # Entity types and enums
    "EntityType",
    "RelationshipType",
    "Entity",
    "CanonicalEntity",
    "EntityRelationship",
    "CoOccurrence",
    # Vector types
    "VectorPoint",
    "CollectionInfo",
    "VectorSearchResult",
    "DistanceMetric",
    "EMBEDDING_DIMENSIONS",
    # LLM types
    "LLMResponse",
    "StreamChunk",
    "PromptTemplate",
    # Chunk types
    "TextChunk",
    "ChunkConfig",
    "ChunkStrategy",
    # Resource types
    "ResourceTier",
    "SystemResources",
    "PoolConfig",
    # Storage types
    "FileInfo",
    "StorageStats",
    # Document types
    "DocumentStatus",
    "Document",
    "Chunk",
    "Page",
    "SearchResult",
    "BatchResult",
    # Project types
    "Project",
    "ProjectStats",
    # Exceptions
    "DatabaseError",
    "SchemaNotFoundError",
    "SchemaExistsError",
    "QueryExecutionError",
    "DocumentNotFoundError",
    "DocumentError",
    "EntityNotFoundError",
    "CanonicalNotFoundError",
    "RelationshipNotFoundError",
    "EntityError",
    "ProjectNotFoundError",
    "ProjectExistsError",
    "ProjectError",
    "VectorServiceError",
    "VectorStoreUnavailableError",
    "CollectionNotFoundError",
    "CollectionExistsError",
    "EmbeddingError",
    "VectorDimensionError",
    "LLMError",
    "LLMUnavailableError",
    "LLMRequestError",
    "JSONExtractionError",
    "PromptNotFoundError",
    "ChunkServiceError",
    "TokenizerError",
    "EventValidationError",
    "EventDeliveryError",
    "WorkerError",
    "WorkerNotFoundError",
    "QueueUnavailableError",
    "ResourceError",
    "GPUMemoryError",
    "CPUAllocationError",
    "StorageError",
    "StorageFileNotFoundError",
    "StorageFullError",
    "InvalidPathError",
    # Export types
    "ExportFormat",
    "ExportOptions",
    "ExportResult",
    "ExportError",
    "ExportFormatError",
    "ExportRenderError",
    "ExportTemplateNotFoundError",
    # Template types
    "Template",
    "RenderResult",
    "TemplateError",
    "TemplateNotFoundError",
    "TemplateRenderError",
    "TemplateSyntaxError",
    # Notification types
    "NotificationType",
    "ChannelType",
    "DeliveryStatus",
    "Notification",
    "NotificationError",
    "DeliveryError",
    "ConfigurationError",
    "ChannelNotFoundError",
    # Scheduler types
    "JobStatus",
    "TriggerType",
    "ScheduledJob",
    "JobResult",
    "SchedulerError",
    "JobNotFoundError",
    "JobExecutionError",
    "InvalidScheduleError",
    # AI Analyst types
    "AnalysisRequest",
    "AnalysisResponse",
    "AnalysisDepth",
    "AnalystMessage",
]
