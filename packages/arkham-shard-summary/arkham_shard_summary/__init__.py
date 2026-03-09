"""
Summary Shard - Auto-summarization for ArkhamFrame

Provides LLM-powered summarization of documents, collections, and analysis results.
"""

from .models import (
    SourceType,
    Summary,
    SummaryFilter,
    SummaryLength,
    SummaryRequest,
    SummaryResult,
    SummaryStatistics,
    SummaryStatus,
    SummaryType,
)
from .shard import SummaryShard

__version__ = "0.1.0"

__all__ = [
    "SummaryShard",
    "Summary",
    "SummaryType",
    "SummaryStatus",
    "SourceType",
    "SummaryLength",
    "SummaryRequest",
    "SummaryResult",
    "SummaryFilter",
    "SummaryStatistics",
]
