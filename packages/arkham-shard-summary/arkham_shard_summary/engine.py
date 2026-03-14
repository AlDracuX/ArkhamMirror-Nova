"""
SummaryEngine — Pure algorithmic extractive summarization.

No LLM dependency. Uses TF-IDF-like sentence scoring with position weighting.
Stdlib only, under 200 LOC.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import List

# Sentence boundary regex — handles common abbreviations
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")
_WORD_RE = re.compile(r"\b[a-z]+\b")

# Common English stop words (minimal set for TF-IDF filtering)
_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "is",
        "it",
        "as",
        "was",
        "are",
        "be",
        "has",
        "had",
        "have",
        "this",
        "that",
        "not",
        "no",
        "so",
        "if",
        "its",
        "they",
        "their",
        "them",
        "he",
        "she",
        "his",
        "her",
        "we",
        "our",
        "you",
        "your",
        "will",
        "would",
        "can",
        "could",
        "may",
        "do",
        "did",
        "been",
        "being",
        "were",
        "which",
        "who",
        "whom",
        "what",
        "when",
        "where",
        "how",
        "than",
        "then",
        "also",
        "into",
        "about",
        "all",
        "each",
        "any",
        "such",
        "very",
        "more",
        "most",
        "some",
        "only",
    }
)


def _split_sentences(text: str) -> List[str]:
    """Split text into sentences using regex boundary detection."""
    text = text.replace("\n", " ").strip()
    if not text:
        return []
    parts = _SENTENCE_RE.split(text)
    return [s.strip() for s in parts if s.strip()]


def _tokenize(text: str) -> List[str]:
    """Extract lowercase words, filtering stop words."""
    return [w for w in _WORD_RE.findall(text.lower()) if w not in _STOP_WORDS]


class SummaryEngine:
    """Extractive summarization engine using TF-IDF scoring and position weighting."""

    def summarize_document(self, text: str, max_length: int = 500) -> str:
        """
        Produce an extractive summary by scoring and selecting top sentences.

        Args:
            text: Source document text.
            max_length: Maximum character length of the summary.

        Returns:
            Summary string, guaranteed <= max_length characters.
        """
        stripped = text.strip()
        if not stripped:
            return ""

        sentences = _split_sentences(stripped)
        if not sentences:
            return stripped[:max_length]

        if len(sentences) == 1:
            return sentences[0][:max_length]

        # If the full text fits, return it
        if len(stripped) <= max_length:
            return stripped

        scores = self._score_sentences(sentences)

        # Select top sentences preserving original order
        ranked = sorted(range(len(sentences)), key=lambda i: scores[i], reverse=True)
        selected: list[int] = []
        current_length = 0

        for idx in ranked:
            sent = sentences[idx]
            addition = len(sent) + (2 if selected else 0)  # account for ". " join
            if current_length + addition <= max_length:
                selected.append(idx)
                current_length += addition

        # Preserve original document order
        selected.sort()
        return " ".join(sentences[i] for i in selected)

    def summarize_case(self, documents: List[str], max_length: int = 500) -> str:
        """
        Aggregate summaries across multiple documents.

        Args:
            documents: List of document texts.
            max_length: Maximum character length of the combined summary.

        Returns:
            Aggregated summary string.
        """
        if not documents:
            return ""

        valid_docs = [d for d in documents if d.strip()]
        if not valid_docs:
            return ""

        # Budget per document, then re-summarize the aggregate
        per_doc_budget = max(100, max_length // max(len(valid_docs), 1))
        doc_summaries = [self.summarize_document(doc, max_length=per_doc_budget) for doc in valid_docs]

        combined = " ".join(s for s in doc_summaries if s)

        # If combined fits, return it; otherwise re-summarize
        if len(combined) <= max_length:
            return combined

        return self.summarize_document(combined, max_length=max_length)

    # ------------------------------------------------------------------
    # Internal scoring
    # ------------------------------------------------------------------

    def _score_sentences(self, sentences: List[str]) -> List[float]:
        """Score each sentence using TF-IDF weighting + position bias."""
        n = len(sentences)

        # Build document frequency across sentences
        doc_freq: Counter[str] = Counter()
        sentence_tokens: list[list[str]] = []

        for sent in sentences:
            tokens = _tokenize(sent)
            sentence_tokens.append(tokens)
            for word in set(tokens):
                doc_freq[word] += 1

        scores: list[float] = []

        for i, tokens in enumerate(sentence_tokens):
            if not tokens:
                scores.append(0.0)
                continue

            # TF-IDF score: sum of tf * idf for each term in sentence
            tf = Counter(tokens)
            tfidf = 0.0
            for word, count in tf.items():
                tf_val = count / len(tokens)
                idf_val = math.log((n + 1) / (doc_freq[word] + 1)) + 1
                tfidf += tf_val * idf_val

            # Position weight: first and last sentences get a boost
            position_weight = 1.0
            if i == 0:
                position_weight = 1.5
            elif i == n - 1:
                position_weight = 1.3
            elif i == 1:
                position_weight = 1.1

            # Length normalization: prefer medium-length sentences
            length_factor = min(len(tokens) / 8.0, 1.5)

            scores.append(tfidf * position_weight * length_factor)

        return scores
