"""Authentication module for ArkhamFrame."""

from .audit import (
    AuditEventCreate,
    AuditEventRead,
    AuditListResponse,
    AuditStats,
    ensure_audit_schema,
    export_audit_events,
    get_audit_events,
    get_audit_stats,
    log_audit_event,
)
from .dependencies import (
    create_db_and_tables,
    current_active_user,
    current_optional_user,
    current_superuser,
    get_async_session,
    require_admin,
    require_analyst,
    require_delete,
    require_manage_users,
    require_permission,
    require_role,
    require_write,
)
from .models import Tenant, User, UserRole
from .router import router as auth_router
from .schemas import TenantCreate, TenantRead, UserCreate, UserRead, UserUpdate

__all__ = [
    # Dependencies
    "current_active_user",
    "current_superuser",
    "current_optional_user",
    "require_role",
    "require_permission",
    "require_admin",
    "require_analyst",
    "require_write",
    "require_delete",
    "require_manage_users",
    "get_async_session",
    "create_db_and_tables",
    # Models
    "User",
    "Tenant",
    "UserRole",
    # Schemas
    "UserRead",
    "UserCreate",
    "UserUpdate",
    "TenantRead",
    "TenantCreate",
    # Router
    "auth_router",
    # Audit
    "log_audit_event",
    "get_audit_events",
    "get_audit_stats",
    "export_audit_events",
    "ensure_audit_schema",
    "AuditEventCreate",
    "AuditEventRead",
    "AuditListResponse",
    "AuditStats",
]
