"""ArkhamFrame Ingest Shard - Document ingestion and processing."""

from .intake import ValidationError
from .shard import IngestShard

__version__ = "0.1.0"
__all__ = ["IngestShard", "ValidationError"]
