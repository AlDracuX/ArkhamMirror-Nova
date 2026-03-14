"""Tests for Reports Engine — pure report generation logic."""

import pytest
from arkham_shard_reports.engine import (
    generate_report,
    get_report_data,
)


class TestGetReportData:
    """Tests for structured data extraction by section type."""

    def test_document_stats(self):
        raw = {"documents": [{"id": "d1", "status": "processed"}, {"id": "d2", "status": "pending"}]}
        result = get_report_data("document_stats", raw)
        assert result["total"] == 2
        assert "processed" in result["by_status"]
        assert result["by_status"]["processed"] == 1

    def test_entity_summary(self):
        raw = {
            "entities": [
                {"id": "e1", "name": "Bylor Ltd", "type": "organization"},
                {"id": "e2", "name": "Alex Dalton", "type": "person"},
                {"id": "e3", "name": "TLT Solicitors", "type": "organization"},
            ]
        }
        result = get_report_data("entity_summary", raw)
        assert result["total"] == 3
        assert result["by_type"]["organization"] == 2
        assert result["by_type"]["person"] == 1

    def test_timeline_overview(self):
        raw = {
            "events": [
                {"id": "t1", "date": "2024-01-15", "description": "Claim filed"},
                {"id": "t2", "date": "2024-03-04", "description": "Hearing"},
            ]
        }
        result = get_report_data("timeline_overview", raw)
        assert result["total_events"] == 2
        assert result["date_range"]["earliest"] == "2024-01-15"
        assert result["date_range"]["latest"] == "2024-03-04"

    def test_claim_status(self):
        raw = {
            "claims": [
                {"id": "c1", "status": "verified", "text": "Claim A"},
                {"id": "c2", "status": "unverified", "text": "Claim B"},
                {"id": "c3", "status": "verified", "text": "Claim C"},
            ]
        }
        result = get_report_data("claim_status", raw)
        assert result["total"] == 3
        assert result["verified"] == 2
        assert result["unverified"] == 1

    def test_unknown_section_type(self):
        result = get_report_data("unknown_type", {})
        assert result["total"] == 0
        assert "error" in result or "message" in result

    def test_empty_data(self):
        result = get_report_data("document_stats", {})
        assert result["total"] == 0

    def test_entity_summary_empty_entities(self):
        result = get_report_data("entity_summary", {"entities": []})
        assert result["total"] == 0
        assert result["by_type"] == {}

    def test_timeline_single_event(self):
        raw = {"events": [{"id": "t1", "date": "2024-06-01", "description": "Event"}]}
        result = get_report_data("timeline_overview", raw)
        assert result["total_events"] == 1
        assert result["date_range"]["earliest"] == "2024-06-01"
        assert result["date_range"]["latest"] == "2024-06-01"

    def test_timeline_no_events(self):
        result = get_report_data("timeline_overview", {"events": []})
        assert result["total_events"] == 0


class TestGenerateReport:
    """Tests for report rendering from template + data."""

    def test_basic_report_generation(self):
        data_sources = {"document_stats": {"documents": [{"id": "d1", "status": "processed"}]}}
        result = generate_report("summary", data_sources)
        assert isinstance(result, str)
        assert "Document" in result or "document" in result

    def test_markdown_format(self):
        data_sources = {"document_stats": {"documents": [{"id": "d1", "status": "ok"}]}}
        result = generate_report("summary", data_sources, format="markdown")
        assert "#" in result  # Markdown heading

    def test_includes_all_provided_sections(self):
        data_sources = {
            "document_stats": {"documents": [{"id": "d1", "status": "ok"}]},
            "entity_summary": {"entities": [{"id": "e1", "name": "X", "type": "person"}]},
            "claim_status": {"claims": [{"id": "c1", "status": "verified", "text": "C"}]},
        }
        result = generate_report("summary", data_sources)
        assert "Document" in result or "document" in result
        assert "Entit" in result or "entit" in result
        assert "Claim" in result or "claim" in result

    def test_document_stats_section_content(self):
        data_sources = {
            "document_stats": {
                "documents": [
                    {"id": "d1", "status": "processed"},
                    {"id": "d2", "status": "pending"},
                ]
            }
        }
        result = generate_report("summary", data_sources)
        assert "2" in result  # Total count

    def test_entity_summary_section_content(self):
        data_sources = {
            "entity_summary": {
                "entities": [
                    {"id": "e1", "name": "Bylor Ltd", "type": "organization"},
                ]
            }
        }
        result = generate_report("summary", data_sources)
        assert "1" in result

    def test_timeline_section_content(self):
        data_sources = {
            "timeline_overview": {
                "events": [
                    {"id": "t1", "date": "2024-01-15", "description": "Filed claim"},
                ]
            }
        }
        result = generate_report("summary", data_sources)
        assert "2024-01-15" in result or "Filed claim" in result or "1" in result

    def test_claim_status_section_content(self):
        data_sources = {
            "claim_status": {
                "claims": [
                    {"id": "c1", "status": "verified", "text": "Claim A"},
                    {"id": "c2", "status": "unverified", "text": "Claim B"},
                ]
            }
        }
        result = generate_report("summary", data_sources)
        assert "2" in result  # Total

    def test_empty_data_sources(self):
        result = generate_report("summary", {})
        assert isinstance(result, str)
        assert len(result) > 0

    def test_report_has_generated_timestamp(self):
        result = generate_report("summary", {})
        assert "Generated" in result or "generated" in result

    def test_custom_template(self):
        data_sources = {"document_stats": {"documents": []}}
        result = generate_report("custom", data_sources)
        assert isinstance(result, str)
