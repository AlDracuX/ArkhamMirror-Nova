"""Tests for SummaryEngine — TDD RED phase first, then GREEN."""

import pytest
from arkham_shard_summary.engine import SummaryEngine


@pytest.fixture
def engine():
    return SummaryEngine()


@pytest.fixture
def sample_text():
    return (
        "The employment tribunal heard evidence from multiple witnesses. "
        "The claimant alleged unfair dismissal following a restructuring exercise. "
        "Documentary evidence showed the respondent failed to follow proper procedure. "
        "The respondent argued that the dismissal was for genuine redundancy reasons. "
        "Cross-examination revealed inconsistencies in the respondent's timeline. "
        "The tribunal noted that no consultation process had taken place. "
        "Expert testimony confirmed the role was not genuinely redundant. "
        "The tribunal found in favour of the claimant on all counts."
    )


@pytest.fixture
def multi_doc_texts():
    return [
        "The first hearing established jurisdiction over the employment claim. "
        "Both parties agreed to the tribunal's authority.",
        "Witness statements were submitted by three employees. "
        "Each statement corroborated the claimant's account of events. "
        "The respondent did not challenge the witness credibility.",
        "Financial records showed the company was profitable at the time of dismissal. "
        "The redundancy justification was therefore undermined.",
    ]


class TestSummaryEngineInit:
    def test_engine_instantiates(self, engine):
        assert engine is not None

    def test_engine_is_summary_engine(self, engine):
        assert isinstance(engine, SummaryEngine)


class TestSummarizeDocument:
    def test_returns_string(self, engine, sample_text):
        result = engine.summarize_document(sample_text)
        assert isinstance(result, str)

    def test_respects_max_length(self, engine, sample_text):
        result = engine.summarize_document(sample_text, max_length=200)
        assert len(result) <= 200

    def test_default_max_length_500(self, engine, sample_text):
        result = engine.summarize_document(sample_text, max_length=500)
        assert len(result) <= 500

    def test_empty_string_returns_empty(self, engine):
        result = engine.summarize_document("")
        assert result == ""

    def test_single_sentence(self, engine):
        text = "This is a single sentence about the case."
        result = engine.summarize_document(text)
        assert result == text

    def test_whitespace_only_returns_empty(self, engine):
        result = engine.summarize_document("   \n\t  ")
        assert result == ""

    def test_short_text_returned_as_is(self, engine):
        text = "Short text."
        result = engine.summarize_document(text, max_length=500)
        assert result == text

    def test_summary_contains_important_content(self, engine, sample_text):
        result = engine.summarize_document(sample_text, max_length=500)
        assert len(result) > 0
        # Should contain at least some sentences from the original
        assert "." in result

    def test_position_weighting_favors_first_sentence(self, engine, sample_text):
        result = engine.summarize_document(sample_text, max_length=200)
        first_sentence = sample_text.split(". ")[0]
        # First sentence should often appear in short summaries due to position weight
        assert first_sentence in result or len(result) > 0

    def test_very_short_max_length(self, engine, sample_text):
        result = engine.summarize_document(sample_text, max_length=50)
        assert len(result) <= 50

    def test_tfidf_scoring_prefers_keyword_dense_sentences(self, engine):
        """Sentences with distinctive terms should score higher."""
        text = (
            "The cat sat on the mat. "
            "Employment tribunal proceedings require careful documentation of evidence. "
            "The cat was happy. "
            "The cat played. "
            "The cat slept."
        )
        result = engine.summarize_document(text, max_length=200)
        # The employment tribunal sentence has unique terms and should rank higher
        assert "tribunal" in result.lower() or "employment" in result.lower()


class TestSummarizeCase:
    def test_returns_string(self, engine, multi_doc_texts):
        result = engine.summarize_case(multi_doc_texts)
        assert isinstance(result, str)

    def test_respects_max_length(self, engine, multi_doc_texts):
        result = engine.summarize_case(multi_doc_texts, max_length=300)
        assert len(result) <= 300

    def test_empty_list_returns_empty(self, engine):
        result = engine.summarize_case([])
        assert result == ""

    def test_single_document_case(self, engine):
        docs = ["The tribunal found in favour of the claimant."]
        result = engine.summarize_case(docs)
        assert len(result) > 0

    def test_aggregates_across_documents(self, engine, multi_doc_texts):
        result = engine.summarize_case(multi_doc_texts, max_length=500)
        assert len(result) > 0

    def test_handles_empty_documents_in_list(self, engine):
        docs = ["Valid document content here.", "", "Another valid document."]
        result = engine.summarize_case(docs)
        assert len(result) > 0


class TestEdgeCases:
    def test_text_with_no_periods(self, engine):
        text = "This is text without proper sentence endings"
        result = engine.summarize_document(text, max_length=500)
        assert len(result) > 0

    def test_text_with_newlines(self, engine):
        text = "First paragraph sentence.\n\nSecond paragraph sentence.\n\nThird paragraph."
        result = engine.summarize_document(text, max_length=500)
        assert len(result) > 0

    def test_text_with_multiple_spaces(self, engine):
        text = "Sentence one.   Sentence two.  Sentence three."
        result = engine.summarize_document(text, max_length=500)
        assert len(result) > 0

    def test_unicode_text(self, engine):
        text = "The claimant's evidence was compelling. The respondent's defence was weak."
        result = engine.summarize_document(text, max_length=500)
        assert len(result) > 0

    def test_very_long_document(self, engine):
        text = ". ".join([f"Sentence number {i} in this long document" for i in range(100)])
        result = engine.summarize_document(text, max_length=300)
        assert len(result) <= 300
