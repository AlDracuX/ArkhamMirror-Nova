"""
Export Shard - Generator Tests

Tests for standalone export format generators (CSV, JSON, Markdown).
TDD: These tests are written BEFORE the implementation.
"""

import csv
import io
import json

import pytest
from arkham_shard_export.generators import generate_csv, generate_json, generate_markdown

# === Test Data ===


@pytest.fixture
def sample_records():
    """Standard test records with various data types."""
    return [
        {"id": "1", "name": "Document Alpha", "status": "active", "count": 42},
        {"id": "2", "name": "Document Beta", "status": "archived", "count": 7},
        {"id": "3", "name": "Document Gamma", "status": "active", "count": 0},
    ]


@pytest.fixture
def records_with_special_chars():
    """Records containing CSV-hostile characters."""
    return [
        {"id": "1", "name": 'Contains "quotes"', "notes": "has, commas"},
        {"id": "2", "name": "Has\nnewline", "notes": "normal"},
        {"id": "3", "name": "Plain", "notes": "also\thas\ttabs"},
    ]


@pytest.fixture
def empty_records():
    """Empty record list."""
    return []


@pytest.fixture
def single_record():
    """Single record."""
    return [{"id": "1", "title": "Only One"}]


@pytest.fixture
def records_with_missing_keys():
    """Records where not all dicts have the same keys."""
    return [
        {"id": "1", "name": "Full", "extra": "yes"},
        {"id": "2", "name": "Partial"},
        {"id": "3", "extra": "only-extra"},
    ]


# === CSV Generator Tests ===


class TestGenerateCSV:
    """Tests for generate_csv function."""

    def test_returns_bytes(self, sample_records):
        """CSV generator returns bytes, not str."""
        result = generate_csv(sample_records)
        assert isinstance(result, bytes)

    def test_basic_csv_output(self, sample_records):
        """CSV has header row plus data rows."""
        result = generate_csv(sample_records)
        text = result.decode("utf-8")
        lines = text.strip().split("\n")
        # Header + 3 data rows
        assert len(lines) == 4

    def test_csv_with_explicit_columns(self, sample_records):
        """CSV respects explicit column list and order."""
        result = generate_csv(sample_records, columns=["name", "status"])
        text = result.decode("utf-8")
        reader = csv.reader(io.StringIO(text))
        header = next(reader)
        assert header == ["name", "status"]
        rows = list(reader)
        assert len(rows) == 3
        assert rows[0][0] == "Document Alpha"

    def test_csv_escapes_quotes(self, records_with_special_chars):
        """CSV properly escapes double quotes in values."""
        result = generate_csv(records_with_special_chars)
        text = result.decode("utf-8")
        # The csv module should handle quoting automatically
        reader = csv.reader(io.StringIO(text))
        _header = next(reader)
        row1 = next(reader)
        # Find the name column value
        assert 'Contains "quotes"' in row1

    def test_csv_escapes_commas(self, records_with_special_chars):
        """CSV properly handles commas in values."""
        result = generate_csv(records_with_special_chars)
        text = result.decode("utf-8")
        reader = csv.reader(io.StringIO(text))
        _header = next(reader)
        row1 = next(reader)
        assert "has, commas" in row1

    def test_csv_handles_newlines(self, records_with_special_chars):
        """CSV properly handles newlines in values."""
        result = generate_csv(records_with_special_chars)
        # Should be parseable back
        text = result.decode("utf-8")
        reader = csv.reader(io.StringIO(text))
        header = next(reader)
        assert "id" in header
        rows = list(reader)
        assert len(rows) == 3

    def test_csv_empty_records(self, empty_records):
        """CSV with no records returns just headers or empty bytes."""
        result = generate_csv(empty_records)
        assert isinstance(result, bytes)
        # Should be empty or minimal
        assert len(result) < 50

    def test_csv_missing_keys_filled(self, records_with_missing_keys):
        """CSV fills missing keys with empty string."""
        result = generate_csv(records_with_missing_keys)
        text = result.decode("utf-8")
        reader = csv.reader(io.StringIO(text))
        header = next(reader)
        # All unique keys should be present
        assert "id" in header
        assert "name" in header
        assert "extra" in header
        rows = list(reader)
        assert len(rows) == 3


# === JSON Generator Tests ===


class TestGenerateJSON:
    """Tests for generate_json function."""

    def test_returns_bytes(self, sample_records):
        """JSON generator returns bytes."""
        result = generate_json(sample_records)
        assert isinstance(result, bytes)

    def test_valid_json(self, sample_records):
        """Output is valid, parseable JSON."""
        result = generate_json(sample_records)
        parsed = json.loads(result.decode("utf-8"))
        assert isinstance(parsed, list)
        assert len(parsed) == 3

    def test_json_formatted(self, sample_records):
        """JSON output is indented/formatted, not minified."""
        result = generate_json(sample_records)
        text = result.decode("utf-8")
        assert "\n" in text
        assert "  " in text

    def test_json_preserves_types(self, sample_records):
        """JSON preserves numeric types."""
        result = generate_json(sample_records)
        parsed = json.loads(result.decode("utf-8"))
        assert parsed[0]["count"] == 42
        assert isinstance(parsed[0]["count"], int)

    def test_json_empty_records(self, empty_records):
        """JSON with empty records returns empty array."""
        result = generate_json(empty_records)
        parsed = json.loads(result.decode("utf-8"))
        assert parsed == []

    def test_json_single_record(self, single_record):
        """JSON with one record returns array of one."""
        result = generate_json(single_record)
        parsed = json.loads(result.decode("utf-8"))
        assert len(parsed) == 1
        assert parsed[0]["title"] == "Only One"

    def test_json_utf8_encoding(self):
        """JSON handles unicode correctly."""
        records = [{"name": "Tomas Muller", "city": "Munchen"}]
        result = generate_json(records)
        text = result.decode("utf-8")
        assert "Muller" in text


# === Markdown Generator Tests ===


class TestGenerateMarkdown:
    """Tests for generate_markdown function."""

    def test_returns_bytes(self, sample_records):
        """Markdown generator returns bytes."""
        result = generate_markdown(sample_records, title="Test Export")
        assert isinstance(result, bytes)

    def test_has_title(self, sample_records):
        """Markdown output includes the title as heading."""
        result = generate_markdown(sample_records, title="My Export")
        text = result.decode("utf-8")
        assert "# My Export" in text

    def test_has_table_header(self, sample_records):
        """Markdown table has header row with column names."""
        result = generate_markdown(sample_records, title="Export")
        text = result.decode("utf-8")
        assert "| id" in text
        assert "| name" in text
        assert "| status" in text

    def test_has_separator_row(self, sample_records):
        """Markdown table has separator row with dashes."""
        result = generate_markdown(sample_records, title="Export")
        text = result.decode("utf-8")
        lines = text.strip().split("\n")
        # Find separator line (contains only |, -, and spaces)
        separator_lines = [l for l in lines if set(l.strip()).issubset(set("|- "))]
        assert len(separator_lines) >= 1

    def test_has_data_rows(self, sample_records):
        """Markdown table has correct number of data rows."""
        result = generate_markdown(sample_records, title="Export")
        text = result.decode("utf-8")
        lines = [l for l in text.strip().split("\n") if l.startswith("|")]
        # header + separator + 3 data rows = 5 pipe-delimited lines
        assert len(lines) == 5

    def test_default_title(self, sample_records):
        """Markdown uses default title when none provided."""
        result = generate_markdown(sample_records)
        text = result.decode("utf-8")
        assert "# Export" in text

    def test_empty_records(self, empty_records):
        """Markdown with no records shows title and no-data message."""
        result = generate_markdown(empty_records, title="Empty")
        text = result.decode("utf-8")
        assert "# Empty" in text
        assert "No data" in text or "no records" in text.lower()

    def test_missing_keys_handled(self, records_with_missing_keys):
        """Markdown table handles records with different key sets."""
        result = generate_markdown(records_with_missing_keys, title="Mixed")
        text = result.decode("utf-8")
        lines = [l for l in text.strip().split("\n") if l.startswith("|")]
        # header + separator + 3 data rows
        assert len(lines) == 5

    def test_pipe_in_values_escaped(self):
        """Markdown escapes pipe characters in cell values."""
        records = [{"name": "value|with|pipes", "id": "1"}]
        result = generate_markdown(records, title="Pipes")
        text = result.decode("utf-8")
        # The pipes in the value should not break the table structure
        data_lines = [l for l in text.strip().split("\n") if l.startswith("|")]
        # Should still parse as a valid table (header + sep + 1 data row)
        assert len(data_lines) == 3
