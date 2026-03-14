"""Tests for Packets Engine — pure packet assembly and indexing logic."""

import pytest
from arkham_shard_packets.engine import (
    assemble_packet,
    create_version,
    generate_index,
)


class TestAssemblePacket:
    """Tests for document assembly into ordered packets."""

    def test_basic_assembly(self):
        docs = [
            {"id": "doc-1", "title": "Witness Statement"},
            {"id": "doc-2", "title": "Employment Contract"},
        ]
        result = assemble_packet(docs, "Trial Bundle", "Documents for hearing")
        assert result["title"] == "Trial Bundle"
        assert result["description"] == "Documents for hearing"
        assert len(result["items"]) == 2

    def test_preserves_document_order(self):
        docs = [
            {"id": "d1", "title": "First"},
            {"id": "d2", "title": "Second"},
            {"id": "d3", "title": "Third"},
        ]
        result = assemble_packet(docs, "Bundle", "Test")
        assert result["items"][0]["title"] == "First"
        assert result["items"][1]["title"] == "Second"
        assert result["items"][2]["title"] == "Third"

    def test_assigns_sequential_order_numbers(self):
        docs = [{"id": f"d{i}", "title": f"Doc {i}"} for i in range(5)]
        result = assemble_packet(docs, "Bundle", "")
        for i, item in enumerate(result["items"]):
            assert item["order"] == i + 1

    def test_empty_documents_raises(self):
        with pytest.raises(ValueError, match="[Dd]ocument"):
            assemble_packet([], "Empty", "No docs")

    def test_includes_packet_id(self):
        docs = [{"id": "d1", "title": "Doc"}]
        result = assemble_packet(docs, "Bundle", "Desc")
        assert "id" in result
        assert isinstance(result["id"], str)
        assert len(result["id"]) > 0

    def test_includes_created_timestamp(self):
        docs = [{"id": "d1", "title": "Doc"}]
        result = assemble_packet(docs, "Bundle", "Desc")
        assert "created_at" in result

    def test_initial_version_is_one(self):
        docs = [{"id": "d1", "title": "Doc"}]
        result = assemble_packet(docs, "Bundle", "Desc")
        assert result["version"] == 1

    def test_document_metadata_preserved(self):
        docs = [{"id": "d1", "title": "Statement", "type": "witness", "pages": 12}]
        result = assemble_packet(docs, "Bundle", "Desc")
        item = result["items"][0]
        assert item["id"] == "d1"
        assert item["title"] == "Statement"


class TestGenerateIndex:
    """Tests for table of contents generation."""

    def test_basic_index(self):
        packet = {
            "title": "Trial Bundle",
            "items": [
                {"order": 1, "title": "Witness Statement", "id": "d1"},
                {"order": 2, "title": "Contract", "id": "d2"},
            ],
        }
        result = generate_index(packet)
        assert "Trial Bundle" in result
        assert "1" in result
        assert "Witness Statement" in result
        assert "Contract" in result

    def test_index_is_markdown(self):
        packet = {
            "title": "Bundle",
            "items": [{"order": 1, "title": "Doc", "id": "d1"}],
        }
        result = generate_index(packet)
        assert "#" in result  # Has markdown heading

    def test_empty_packet_returns_empty_index(self):
        packet = {"title": "Empty Bundle", "items": []}
        result = generate_index(packet)
        assert "Empty Bundle" in result
        assert "No items" in result or "empty" in result.lower()

    def test_index_item_numbering(self):
        items = [{"order": i, "title": f"Document {i}", "id": f"d{i}"} for i in range(1, 4)]
        packet = {"title": "Bundle", "items": items}
        result = generate_index(packet)
        assert "1." in result or "1 " in result
        assert "2." in result or "2 " in result
        assert "3." in result or "3 " in result

    def test_includes_page_numbers_when_available(self):
        packet = {
            "title": "Bundle",
            "items": [
                {"order": 1, "title": "Doc A", "id": "d1", "pages": 5},
                {"order": 2, "title": "Doc B", "id": "d2", "pages": 10},
            ],
        }
        result = generate_index(packet)
        assert "5" in result or "p." in result


class TestCreateVersion:
    """Tests for packet version tracking."""

    def test_creates_version_record(self):
        packet = {"id": "pkt-1", "version": 1, "title": "Bundle"}
        result = create_version(packet, "Initial assembly")
        assert result["packet_id"] == "pkt-1"
        assert result["version_number"] == 2
        assert result["changes_summary"] == "Initial assembly"

    def test_increments_version(self):
        packet = {"id": "pkt-1", "version": 3, "title": "Bundle"}
        result = create_version(packet, "Added new document")
        assert result["version_number"] == 4

    def test_includes_timestamp(self):
        packet = {"id": "pkt-1", "version": 1, "title": "Bundle"}
        result = create_version(packet, "Change")
        assert "created_at" in result

    def test_includes_version_id(self):
        packet = {"id": "pkt-1", "version": 1, "title": "Bundle"}
        result = create_version(packet, "Change")
        assert "id" in result
        assert isinstance(result["id"], str)

    def test_empty_changes_summary(self):
        packet = {"id": "pkt-1", "version": 1, "title": "Bundle"}
        result = create_version(packet, "")
        assert result["changes_summary"] == ""
