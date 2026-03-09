"""
ArkhamMirror Dashboard Shard

System monitoring, LLM configuration, database controls, and worker management.
"""

__version__ = "0.1.0"

from .models import (
    DashboardStats,
    DatabaseInfo,
    ErrorInfo,
    ErrorListResponse,
    EventInfo,
    EventListResponse,
    LLMConfig,
    LLMTestResult,
    MigrationResult,
    QueueStats,
    ResetDatabaseRequest,
    ScaleWorkersRequest,
    ScaleWorkersResult,
    ServiceHealth,
    ServiceStatus,
    ShardInfo,
    StartWorkerRequest,
    StartWorkerResult,
    StopWorkerRequest,
    StopWorkerResult,
    SystemHealth,
    SystemInfo,
    UpdateLLMRequest,
    VacuumResult,
    WorkerInfo,
)
from .shard import DashboardShard

__all__ = [
    "DashboardShard",
    "__version__",
    # Service models
    "ServiceStatus",
    "ServiceHealth",
    "SystemHealth",
    # LLM models
    "LLMConfig",
    "UpdateLLMRequest",
    "LLMTestResult",
    # Database models
    "DatabaseInfo",
    "MigrationResult",
    "ResetDatabaseRequest",
    "VacuumResult",
    # Worker models
    "WorkerInfo",
    "QueueStats",
    "ScaleWorkersRequest",
    "ScaleWorkersResult",
    "StartWorkerRequest",
    "StartWorkerResult",
    "StopWorkerRequest",
    "StopWorkerResult",
    # Event models
    "EventInfo",
    "EventListResponse",
    "ErrorInfo",
    "ErrorListResponse",
    # System models
    "ShardInfo",
    "SystemInfo",
    "DashboardStats",
]
