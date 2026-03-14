"""
Parse Shard - Regex NER and Date Normalization Tests

Tests for extract_entities_regex() and normalize_dates() methods.
TDD: These tests are written BEFORE implementation.
"""

import pytest
from arkham_shard_parse.shard import ParseShard


class TestExtractEntitiesRegex:
    """Tests for regex-based NER extraction (no spaCy dependency)."""

    @pytest.fixture
    def shard(self):
        """Create a ParseShard instance (uninitialised - no frame needed for regex)."""
        return ParseShard()

    # --- DATE entity type ---

    def test_iso_date(self, shard):
        """Detect ISO 8601 dates like 2024-03-15."""
        results = shard.extract_entities_regex("The deadline is 2024-03-15.")
        dates = [r for r in results if r["type"] == "DATE"]
        assert any(r["text"] == "2024-03-15" for r in dates)

    def test_uk_date_dd_mm_yyyy(self, shard):
        """Detect UK dates like 15/03/2024."""
        results = shard.extract_entities_regex("Filed on 15/03/2024 at court.")
        dates = [r for r in results if r["type"] == "DATE"]
        assert any(r["text"] == "15/03/2024" for r in dates)

    def test_month_year(self, shard):
        """Detect month-year like March 2024."""
        results = shard.extract_entities_regex("Employment started March 2024.")
        dates = [r for r in results if r["type"] == "DATE"]
        assert any("March 2024" in r["text"] for r in dates)

    def test_ordinal_date(self, shard):
        """Detect dates like 1st March 2024."""
        results = shard.extract_entities_regex("Hearing on 1st March 2024.")
        dates = [r for r in results if r["type"] == "DATE"]
        assert any("1st March 2024" in r["text"] for r in dates)

    def test_relative_date_yesterday(self, shard):
        """Detect relative dates like yesterday, today, tomorrow."""
        results = shard.extract_entities_regex("I submitted it yesterday.")
        dates = [r for r in results if r["type"] == "DATE"]
        assert any(r["text"] == "yesterday" for r in dates)

    def test_relative_date_last_week(self, shard):
        """Detect relative dates like last week, next month."""
        results = shard.extract_entities_regex("The meeting was last week.")
        dates = [r for r in results if r["type"] == "DATE"]
        assert any("last week" in r["text"] for r in dates)

    # --- MONEY entity type ---

    def test_money_pounds(self, shard):
        """Detect GBP amounts like GBP 25,000."""
        results = shard.extract_entities_regex("The claim is for GBP 25,000.")
        money = [r for r in results if r["type"] == "MONEY"]
        assert len(money) >= 1

    def test_money_pound_sign(self, shard):
        """Detect amounts with pound sign."""
        results = shard.extract_entities_regex("Damages of \u00a350,000.00 awarded.")
        money = [r for r in results if r["type"] == "MONEY"]
        assert len(money) >= 1
        assert any("\u00a350,000.00" in r["text"] for r in money)

    def test_money_simple(self, shard):
        """Detect simple pound amounts."""
        results = shard.extract_entities_regex("Paid \u00a3500 for costs.")
        money = [r for r in results if r["type"] == "MONEY"]
        assert len(money) >= 1

    # --- EMAIL entity type ---

    def test_email(self, shard):
        """Detect email addresses."""
        results = shard.extract_entities_regex("Contact john.smith@example.com for details.")
        emails = [r for r in results if r["type"] == "EMAIL"]
        assert len(emails) == 1
        assert emails[0]["text"] == "john.smith@example.com"

    def test_email_position(self, shard):
        """Email entity has correct start/end positions."""
        text = "Email me at test@test.co.uk please."
        results = shard.extract_entities_regex(text)
        emails = [r for r in results if r["type"] == "EMAIL"]
        assert len(emails) == 1
        assert text[emails[0]["start"] : emails[0]["end"]] == "test@test.co.uk"

    # --- PHONE entity type ---

    def test_uk_phone_mobile(self, shard):
        """Detect UK mobile numbers."""
        results = shard.extract_entities_regex("Call 07700 900123 for info.")
        phones = [r for r in results if r["type"] == "PHONE"]
        assert len(phones) >= 1

    def test_uk_phone_landline(self, shard):
        """Detect UK landline numbers."""
        results = shard.extract_entities_regex("Office: 020 7946 0958.")
        phones = [r for r in results if r["type"] == "PHONE"]
        assert len(phones) >= 1

    def test_uk_phone_international(self, shard):
        """Detect UK international format."""
        results = shard.extract_entities_regex("Call +44 7700 900123.")
        phones = [r for r in results if r["type"] == "PHONE"]
        assert len(phones) >= 1

    # --- PERSON entity type ---

    def test_person_name(self, shard):
        """Detect capitalized word pairs as PERSON (not at sentence start)."""
        results = shard.extract_entities_regex("The claimant John Smith filed a claim.")
        persons = [r for r in results if r["type"] == "PERSON"]
        assert any("John Smith" in r["text"] for r in persons)

    def test_person_not_sentence_start(self, shard):
        """First capitalized words at sentence start should NOT be tagged as PERSON."""
        results = shard.extract_entities_regex("The cat sat. John Smith arrived.")
        # "The cat" should NOT be a person, but "John Smith" should be
        persons = [r for r in results if r["type"] == "PERSON"]
        assert not any(r["text"] == "The" for r in persons)

    # --- REFERENCE entity type ---

    def test_et_reference(self, shard):
        """Detect Employment Tribunal case references."""
        results = shard.extract_entities_regex("Case ET/1234/2024 was filed.")
        refs = [r for r in results if r["type"] == "REFERENCE"]
        assert len(refs) >= 1
        assert any("ET/1234/2024" in r["text"] for r in refs)

    def test_ukeat_reference(self, shard):
        """Detect EAT case references."""
        results = shard.extract_entities_regex("Appeal UKEAT/0123/24 was lodged.")
        refs = [r for r in results if r["type"] == "REFERENCE"]
        assert len(refs) >= 1

    def test_case_number_format(self, shard):
        """Detect case number format like 6013156/2024."""
        results = shard.extract_entities_regex("Case number 6013156/2024 at Bristol.")
        refs = [r for r in results if r["type"] == "REFERENCE"]
        assert len(refs) >= 1

    def test_eat_appeal_reference(self, shard):
        """Detect EAT appeal references like EA-2025-001649-AT."""
        results = shard.extract_entities_regex("The appeal EA-2025-001649-AT was filed.")
        refs = [r for r in results if r["type"] == "REFERENCE"]
        assert len(refs) >= 1

    # --- Return format ---

    def test_return_format(self, shard):
        """Each entity has text, type, start, end keys."""
        results = shard.extract_entities_regex("Filed on 2024-01-15.")
        assert len(results) >= 1
        for r in results:
            assert "text" in r
            assert "type" in r
            assert "start" in r
            assert "end" in r

    def test_return_type_is_list(self, shard):
        """Return type is a list of dicts."""
        results = shard.extract_entities_regex("No entities here maybe.")
        assert isinstance(results, list)

    def test_empty_text(self, shard):
        """Empty text returns empty list."""
        results = shard.extract_entities_regex("")
        assert results == []

    # --- Multiple entities ---

    def test_multiple_entity_types(self, shard):
        """Detect multiple entity types in one text."""
        text = "John Smith emailed john@example.com on 2024-03-15 about case ET/1234/2024 for \u00a35,000."
        results = shard.extract_entities_regex(text)
        types = {r["type"] for r in results}
        assert "EMAIL" in types
        assert "DATE" in types
        assert "REFERENCE" in types
        assert "MONEY" in types

    def test_no_duplicates(self, shard):
        """Same span should not produce duplicate entities of the same type."""
        text = "Meeting on 2024-03-15."
        results = shard.extract_entities_regex(text)
        date_texts = [(r["text"], r["start"], r["end"]) for r in results if r["type"] == "DATE"]
        assert len(date_texts) == len(set(date_texts))


class TestNormalizeDates:
    """Tests for date normalization to ISO 8601."""

    @pytest.fixture
    def shard(self):
        return ParseShard()

    def test_iso_passthrough(self, shard):
        """ISO dates pass through normalized."""
        results = shard.normalize_dates("The date is 2024-03-15.")
        assert any(r["normalized"] == "2024-03-15" for r in results)

    def test_uk_date_dd_mm_yyyy(self, shard):
        """DD/MM/YYYY normalizes to ISO."""
        results = shard.normalize_dates("Filed on 01/03/2024.")
        assert any(r["normalized"] == "2024-03-01" for r in results)

    def test_ordinal_date(self, shard):
        """1st March 2024 normalizes to ISO."""
        results = shard.normalize_dates("Hearing on 1st March 2024.")
        assert any(r["normalized"] == "2024-03-01" for r in results)

    def test_written_date(self, shard):
        """March 15, 2024 normalizes to ISO."""
        results = shard.normalize_dates("Started March 15, 2024.")
        assert any(r["normalized"] == "2024-03-15" for r in results)

    def test_month_year_only(self, shard):
        """March 2024 normalizes to YYYY-MM (day unknown)."""
        results = shard.normalize_dates("Employment began March 2024.")
        assert any(r["normalized"] == "2024-03" for r in results)

    def test_return_format(self, shard):
        """Each result has original, normalized, start, end."""
        results = shard.normalize_dates("Date: 2024-01-15.")
        assert len(results) >= 1
        for r in results:
            assert "original" in r
            assert "normalized" in r
            assert "start" in r
            assert "end" in r

    def test_empty_text(self, shard):
        """Empty text returns empty list."""
        assert shard.normalize_dates("") == []

    def test_multiple_dates(self, shard):
        """Multiple dates in one text are all normalized."""
        text = "From 01/03/2024 to 2024-12-31."
        results = shard.normalize_dates(text)
        assert len(results) == 2

    def test_invalid_date_skipped(self, shard):
        """Invalid dates like 32/13/2024 are skipped."""
        results = shard.normalize_dates("Date: 32/13/2024.")
        assert len(results) == 0
