"""Data models for the Sentiment Shard."""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SentimentLabel(str, Enum):
    """Sentiment classification labels."""

    VERY_NEGATIVE = "very_negative"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    POSITIVE = "positive"
    VERY_POSITIVE = "very_positive"


# --- Word lists for keyword-based scoring ---

POSITIVE_WORDS = frozenset(
    ["agree", "fair", "reasonable", "correct", "proper", "appropriate", "satisfied", "willing", "comply", "support"]
)

NEGATIVE_WORDS = frozenset(
    ["deny", "refuse", "unfair", "incorrect", "improper", "reject", "dispute", "hostile", "negligent", "breach"]
)


def score_to_label(score: float) -> SentimentLabel:
    """Convert a numeric score (-1.0 to 1.0) to a sentiment label."""
    if score <= -0.6:
        return SentimentLabel.VERY_NEGATIVE
    elif score <= -0.2:
        return SentimentLabel.NEGATIVE
    elif score <= 0.2:
        return SentimentLabel.NEUTRAL
    elif score <= 0.6:
        return SentimentLabel.POSITIVE
    else:
        return SentimentLabel.VERY_POSITIVE


def analyze_sentiment(text: str) -> Dict[str, Any]:
    """
    Perform keyword-based sentiment analysis on text.

    Returns dict with score, label, confidence, and key_passages.
    """
    words = text.lower().split()
    positive_count = sum(1 for w in words if w.strip(".,;:!?()\"'") in POSITIVE_WORDS)
    negative_count = sum(1 for w in words if w.strip(".,;:!?()\"'") in NEGATIVE_WORDS)
    total = positive_count + negative_count

    score = (positive_count - negative_count) / max(total, 1)
    label = score_to_label(score)

    # Confidence: higher when more sentiment words found relative to text length
    word_count = max(len(words), 1)
    confidence = min(total / word_count * 5.0, 1.0)  # Scale up, cap at 1.0

    # Extract key passages (sentences containing sentiment words)
    sentences = text.replace("!", ".").replace("?", ".").split(".")
    all_sentiment_words = POSITIVE_WORDS | NEGATIVE_WORDS
    key_passages = []
    for sentence in sentences:
        s_lower = sentence.lower()
        s_words = [w.strip(".,;:!?()\"'") for w in s_lower.split()]
        if any(w in all_sentiment_words for w in s_words):
            stripped = sentence.strip()
            if stripped:
                key_passages.append(stripped)

    return {
        "score": round(score, 4),
        "label": label.value,
        "confidence": round(confidence, 4),
        "key_passages": key_passages,
    }


# --- Pydantic models for API ---


class SentimentResult(BaseModel):
    """A stored sentiment analysis result."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    document_id: str
    case_id: Optional[str] = None
    overall_score: float = 0.0
    label: str = SentimentLabel.NEUTRAL.value
    confidence: float = 0.0
    passages: List[str] = Field(default_factory=list)
    entity_sentiments: Dict[str, Any] = Field(default_factory=dict)
    analyzed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None


class CreateResultRequest(BaseModel):
    """Request body for creating a sentiment result."""

    document_id: str
    case_id: Optional[str] = None
    overall_score: float = 0.0
    label: str = SentimentLabel.NEUTRAL.value
    confidence: float = 0.0
    passages: List[str] = Field(default_factory=list)
    entity_sentiments: Dict[str, Any] = Field(default_factory=dict)


class UpdateResultRequest(BaseModel):
    """Request body for updating a sentiment result."""

    overall_score: Optional[float] = None
    label: Optional[str] = None
    confidence: Optional[float] = None
    passages: Optional[List[str]] = None
    entity_sentiments: Optional[Dict[str, Any]] = None


class AnalyzeRequest(BaseModel):
    """Request body for the analyze endpoint."""

    document_id: str
    text: str


class AnalyzeResponse(BaseModel):
    """Response from the analyze endpoint."""

    document_id: str
    score: float
    label: str
    confidence: float
    key_passages: List[str]


# Legacy models kept for backward compat with existing tests
class SentimentAnalysis(BaseModel):
    id: str
    tenant_id: Optional[str] = None
    document_id: Optional[str] = None
    thread_id: Optional[str] = None
    project_id: str
    summary: str
    overall_sentiment: float
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ToneScore(BaseModel):
    id: str
    analysis_id: str
    category: str
    score: float
    reasoning: str
    evidence_segments: List[str] = Field(default_factory=list)


class SentimentPattern(BaseModel):
    id: str
    project_id: str
    type: str
    description: str
    significance_score: float
    analysis_ids: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ComparatorDiff(BaseModel):
    id: str
    project_id: str
    claimant_analysis_id: str
    comparator_analysis_id: str
    divergence_score: float
    description: str
    findings: List[str] = Field(default_factory=list)
