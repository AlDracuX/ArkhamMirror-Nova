"""
Templates Shard - Template Management for ArkhamFrame

Provides template creation, editing, versioning, and rendering
capabilities for reports, letters, exports, and custom documents.
"""

from .models import (
    OutputFormat,
    Template,
    TemplateCreate,
    TemplatePlaceholder,
    TemplateRenderRequest,
    TemplateRenderResult,
    TemplateType,
    TemplateUpdate,
    TemplateVersion,
)
from .shard import TemplatesShard

__version__ = "0.1.0"

__all__ = [
    "TemplatesShard",
    "Template",
    "TemplateCreate",
    "TemplateUpdate",
    "TemplateType",
    "TemplatePlaceholder",
    "TemplateVersion",
    "TemplateRenderRequest",
    "TemplateRenderResult",
    "OutputFormat",
]
