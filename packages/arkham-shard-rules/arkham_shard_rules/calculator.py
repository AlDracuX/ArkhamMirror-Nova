"""Deadline calculation engine for the Rules shard.

Handles calendar/working day arithmetic, breach detection,
compliance checking, and unless-order risk assessment.
"""

import logging
import uuid
from datetime import date, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# UK Bank Holidays (England & Wales) — pre-computed for 2024-2028
# In production this would be fetched from gov.uk API; hard-coded here
# for deterministic, offline-safe calculations.
# ---------------------------------------------------------------------------

UK_BANK_HOLIDAYS: set[date] = {
    # 2024
    date(2024, 1, 1),  # New Year's Day
    date(2024, 3, 29),  # Good Friday
    date(2024, 4, 1),  # Easter Monday
    date(2024, 5, 6),  # Early May bank holiday
    date(2024, 5, 27),  # Spring bank holiday
    date(2024, 8, 26),  # Summer bank holiday
    date(2024, 12, 25),  # Christmas Day
    date(2024, 12, 26),  # Boxing Day
    # 2025
    date(2025, 1, 1),  # New Year's Day
    date(2025, 4, 18),  # Good Friday
    date(2025, 4, 21),  # Easter Monday
    date(2025, 5, 5),  # Early May bank holiday
    date(2025, 5, 26),  # Spring bank holiday
    date(2025, 8, 25),  # Summer bank holiday
    date(2025, 12, 25),  # Christmas Day
    date(2025, 12, 26),  # Boxing Day
    # 2026
    date(2026, 1, 1),  # New Year's Day
    date(2026, 4, 3),  # Good Friday
    date(2026, 4, 6),  # Easter Monday
    date(2026, 5, 4),  # Early May bank holiday
    date(2026, 5, 25),  # Spring bank holiday
    date(2026, 8, 31),  # Summer bank holiday
    date(2026, 12, 25),  # Christmas Day
    date(2026, 12, 28),  # Boxing Day (substitute)
    # 2027
    date(2027, 1, 1),  # New Year's Day
    date(2027, 3, 26),  # Good Friday
    date(2027, 3, 29),  # Easter Monday
    date(2027, 5, 3),  # Early May bank holiday
    date(2027, 5, 31),  # Spring bank holiday
    date(2027, 8, 30),  # Summer bank holiday
    date(2027, 12, 27),  # Christmas Day (substitute)
    date(2027, 12, 28),  # Boxing Day (substitute)
    # 2028
    date(2028, 1, 3),  # New Year's Day (substitute)
    date(2028, 4, 14),  # Good Friday
    date(2028, 4, 17),  # Easter Monday
    date(2028, 5, 1),  # Early May bank holiday
    date(2028, 5, 29),  # Spring bank holiday
    date(2028, 8, 28),  # Summer bank holiday
    date(2028, 12, 25),  # Christmas Day
    date(2028, 12, 26),  # Boxing Day
}


class DeadlineCalculator:
    """Calculate procedural deadlines according to ET Rules of Procedure.

    Supports calendar days, working days, weeks, and months arithmetic.
    Detects breaches and assesses unless-order risk.
    """

    def __init__(self, db=None, event_bus=None):
        self._db = db
        self._event_bus = event_bus

    # ------------------------------------------------------------------
    # Date arithmetic
    # ------------------------------------------------------------------

    def add_working_days(self, start: date, days: int) -> date:
        """Add N working days (Mon-Fri, excluding UK bank holidays).

        The start date itself is NOT counted; counting begins on the
        next day, consistent with ET procedural practice.
        """
        if days <= 0:
            return start

        current = start
        added = 0
        while added < days:
            current += timedelta(days=1)
            if self._is_working_day(current):
                added += 1
        return current

    def add_calendar_days(self, start: date, days: int) -> date:
        """Add N calendar days to a start date."""
        return start + timedelta(days=days)

    def add_weeks(self, start: date, weeks: int) -> date:
        """Add N weeks to a start date."""
        return start + timedelta(weeks=weeks)

    def add_months(self, start: date, months: int) -> date:
        """Add N calendar months, clamping to end-of-month if needed."""
        month = start.month - 1 + months
        year = start.year + month // 12
        month = month % 12 + 1
        # Clamp day to valid range for target month
        import calendar

        max_day = calendar.monthrange(year, month)[1]
        day = min(start.day, max_day)
        return date(year, month, day)

    def compute_deadline(self, trigger_date: date, deadline_days: int, deadline_type: str) -> date:
        """Compute a deadline date from a trigger date, day count, and type."""
        if deadline_type == "working_days":
            return self.add_working_days(trigger_date, deadline_days)
        elif deadline_type == "weeks":
            return self.add_weeks(trigger_date, deadline_days)
        elif deadline_type == "months":
            return self.add_months(trigger_date, deadline_days)
        else:  # calendar_days (default)
            return self.add_calendar_days(trigger_date, deadline_days)

    # ------------------------------------------------------------------
    # Full calculation workflow
    # ------------------------------------------------------------------

    async def calculate(self, rule_id: str, trigger_date: date, trigger_type: str) -> dict:
        """Fetch rule, apply deadline arithmetic, store and return Calculation record."""
        if not self._db:
            raise RuntimeError("Database not available")

        # Fetch the rule
        rule = await self._db.fetch_one(
            "SELECT * FROM arkham_rules.rules WHERE id = :id",
            {"id": rule_id},
        )
        if not rule:
            raise ValueError(f"Rule not found: {rule_id}")

        deadline_days = rule.get("deadline_days") or rule["deadline_days"]
        deadline_type = rule.get("deadline_type", "calendar_days")
        if deadline_days is None:
            raise ValueError(f"Rule {rule_id} has no deadline_days defined")

        deadline_date = self.compute_deadline(trigger_date, deadline_days, deadline_type)

        calc_id = str(uuid.uuid4())
        rule_number = rule.get("rule_number", "")
        rule_title = rule.get("title", "")
        description = f"{rule_title} - {deadline_days} {deadline_type} from {trigger_date}"

        await self._db.execute(
            """
            INSERT INTO arkham_rules.calculations
            (id, rule_id, rule_number, rule_title, trigger_date, trigger_type,
             deadline_date, deadline_days, deadline_type, description)
            VALUES (:id, :rule_id, :rule_number, :rule_title, :trigger_date, :trigger_type,
                    :deadline_date, :deadline_days, :deadline_type, :description)
            """,
            {
                "id": calc_id,
                "rule_id": rule_id,
                "rule_number": rule_number,
                "rule_title": rule_title,
                "trigger_date": trigger_date,
                "trigger_type": trigger_type,
                "deadline_date": deadline_date,
                "deadline_days": deadline_days,
                "deadline_type": deadline_type,
                "description": description,
            },
        )

        if self._event_bus:
            await self._event_bus.emit(
                "rules.deadline.calculated",
                {"calculation_id": calc_id, "rule_id": rule_id, "deadline_date": str(deadline_date)},
                source="rules-shard",
            )

        return {
            "id": calc_id,
            "rule_id": rule_id,
            "rule_number": rule_number,
            "rule_title": rule_title,
            "trigger_date": str(trigger_date),
            "trigger_type": trigger_type,
            "deadline_date": str(deadline_date),
            "deadline_days": deadline_days,
            "deadline_type": deadline_type,
            "description": description,
        }

    # ------------------------------------------------------------------
    # Breach detection
    # ------------------------------------------------------------------

    async def detect_breaches(self, project_id: str) -> list[dict]:
        """Scan calculations for a project and detect missed deadlines.

        A breach is created when:
        - deadline_date < today
        - No completion has been recorded (metadata->>'completed' is null)
        """
        if not self._db:
            raise RuntimeError("Database not available")

        today = date.today()
        rows = await self._db.fetch_all(
            """
            SELECT * FROM arkham_rules.calculations
            WHERE project_id = :project_id
              AND deadline_date < :today
              AND (metadata->>'completed') IS NULL
            """,
            {"project_id": project_id, "today": today},
        )

        breaches = []
        for row in rows:
            breach_id = str(uuid.uuid4())
            rule_id = row.get("rule_id", "")
            rule_number = row.get("rule_number", "")
            rule_title = row.get("rule_title", "")
            deadline_date = row.get("deadline_date")

            await self._db.execute(
                """
                INSERT INTO arkham_rules.breaches
                (id, rule_id, rule_number, rule_title, breaching_party, breach_date,
                 deadline_date, description, severity, status, project_id)
                VALUES (:id, :rule_id, :rule_number, :rule_title, :breaching_party, :breach_date,
                        :deadline_date, :description, :severity, :status, :project_id)
                """,
                {
                    "id": breach_id,
                    "rule_id": rule_id,
                    "rule_number": rule_number,
                    "rule_title": rule_title,
                    "breaching_party": "Unknown",
                    "breach_date": today,
                    "deadline_date": deadline_date,
                    "description": f"Missed deadline for {rule_title} (due {deadline_date})",
                    "severity": "moderate",
                    "status": "detected",
                    "project_id": project_id,
                },
            )

            breach = {
                "id": breach_id,
                "rule_id": rule_id,
                "rule_number": rule_number,
                "rule_title": rule_title,
                "deadline_date": str(deadline_date) if deadline_date else None,
                "breach_date": str(today),
                "severity": "moderate",
                "status": "detected",
            }
            breaches.append(breach)

            if self._event_bus:
                await self._event_bus.emit(
                    "rules.breach.detected",
                    {"breach_id": breach_id, "rule_id": rule_id, "project_id": project_id},
                    source="rules-shard",
                )

        return breaches

    # ------------------------------------------------------------------
    # Compliance checking
    # ------------------------------------------------------------------

    async def check_compliance(self, document_id: str, submission_type: str) -> dict:
        """Validate a document against applicable rules for its submission_type.

        Returns a dict with issues_found, passed_checks, and score.
        """
        if not self._db:
            raise RuntimeError("Database not available")

        # Fetch rules applicable to this submission type
        rules = await self._db.fetch_all(
            """
            SELECT * FROM arkham_rules.rules
            WHERE trigger_type = :submission_type
               OR category = :submission_type
            """,
            {"submission_type": submission_type},
        )

        issues_found: list[str] = []
        passed_checks: list[str] = []
        warnings: list[str] = []
        rules_checked: list[str] = []

        for rule in rules:
            rule_id = rule.get("id", "")
            rule_number = rule.get("rule_number", "")
            rule_title = rule.get("title", "")
            is_mandatory = rule.get("is_mandatory", True)
            rules_checked.append(rule_id)

            # Check if deadline exists for this rule + document
            calc = await self._db.fetch_one(
                """
                SELECT * FROM arkham_rules.calculations
                WHERE rule_id = :rule_id AND document_id = :document_id
                """,
                {"rule_id": rule_id, "document_id": document_id},
            )

            if calc:
                deadline_date = calc.get("deadline_date")
                completed = (
                    calc.get("metadata", {}).get("completed") if isinstance(calc.get("metadata"), dict) else None
                )
                if deadline_date and deadline_date < date.today() and not completed:
                    issues_found.append(f"{rule_number} ({rule_title}): deadline missed")
                else:
                    passed_checks.append(f"{rule_number} ({rule_title}): compliant")
            else:
                if is_mandatory:
                    warnings.append(f"{rule_number} ({rule_title}): no calculation found")
                else:
                    passed_checks.append(f"{rule_number} ({rule_title}): discretionary, no action needed")

        total = len(rules_checked) or 1
        score = len(passed_checks) / total

        result_status = "compliant"
        if issues_found:
            result_status = "non_compliant"
        elif warnings:
            result_status = "borderline"

        check_id = str(uuid.uuid4())
        await self._db.execute(
            """
            INSERT INTO arkham_rules.compliance_checks
            (id, document_id, submission_type, rules_checked, result,
             issues_found, warnings, passed_checks, score)
            VALUES (:id, :document_id, :submission_type, :rules_checked, :result,
                    :issues_found, :warnings, :passed_checks, :score)
            """,
            {
                "id": check_id,
                "document_id": document_id,
                "submission_type": submission_type,
                "rules_checked": str(rules_checked),
                "result": result_status,
                "issues_found": str(issues_found),
                "warnings": str(warnings),
                "passed_checks": str(passed_checks),
                "score": score,
            },
        )

        if self._event_bus:
            await self._event_bus.emit(
                "rules.compliance.checked",
                {"check_id": check_id, "document_id": document_id, "result": result_status},
                source="rules-shard",
            )

        return {
            "id": check_id,
            "document_id": document_id,
            "submission_type": submission_type,
            "rules_checked": rules_checked,
            "result": result_status,
            "issues_found": issues_found,
            "warnings": warnings,
            "passed_checks": passed_checks,
            "score": score,
        }

    # ------------------------------------------------------------------
    # Unless order risk assessment
    # ------------------------------------------------------------------

    async def assess_unless_order_risk(self, breach_id: str) -> dict:
        """Given a breach, assess unless-order viability.

        Considers: severity, is_mandatory, strike_out_risk, number of prior breaches.
        Returns a risk assessment dict with score and recommendation.
        """
        if not self._db:
            raise RuntimeError("Database not available")

        breach = await self._db.fetch_one(
            "SELECT * FROM arkham_rules.breaches WHERE id = :id",
            {"id": breach_id},
        )
        if not breach:
            raise ValueError(f"Breach not found: {breach_id}")

        rule_id = breach.get("rule_id", "")
        breaching_party = breach.get("breaching_party", "")
        severity = breach.get("severity", "moderate")
        project_id = breach.get("project_id")

        # Fetch the rule to check strike_out_risk and is_mandatory
        rule = await self._db.fetch_one(
            "SELECT * FROM arkham_rules.rules WHERE id = :id",
            {"id": rule_id},
        )

        is_mandatory = rule.get("is_mandatory", True) if rule else True
        strike_out_risk = rule.get("strike_out_risk", False) if rule else False
        unless_order_applicable = rule.get("unless_order_applicable", False) if rule else False

        # Count prior breaches by same party in same project
        prior_breaches_row = await self._db.fetch_one(
            """
            SELECT COUNT(*) as count FROM arkham_rules.breaches
            WHERE breaching_party = :party
              AND project_id = :project_id
              AND id != :breach_id
            """,
            {"party": breaching_party, "project_id": project_id, "breach_id": breach_id},
        )
        prior_count = prior_breaches_row.get("count", 0) if prior_breaches_row else 0

        # Score calculation
        score = 0.0
        factors = []

        # Severity factor
        severity_scores = {"minor": 0.1, "moderate": 0.3, "serious": 0.6, "egregious": 0.9}
        severity_score = severity_scores.get(severity, 0.3)
        score += severity_score
        factors.append(f"Severity ({severity}): +{severity_score}")

        # Mandatory rule factor
        if is_mandatory:
            score += 0.2
            factors.append("Mandatory rule: +0.2")

        # Strike-out risk factor
        if strike_out_risk:
            score += 0.3
            factors.append("Strike-out risk: +0.3")

        # Prior breaches factor
        if prior_count >= 3:
            score += 0.3
            factors.append(f"Pattern of non-compliance ({prior_count} prior): +0.3")
        elif prior_count >= 1:
            score += 0.15
            factors.append(f"Prior breach(es) ({prior_count}): +0.15")

        # Cap at 1.0
        score = min(score, 1.0)

        # Recommendation
        if score >= 0.7:
            recommendation = "Strong case for unless order application"
            risk_level = "high"
        elif score >= 0.4:
            recommendation = "Moderate case - consider unless order with supporting evidence"
            risk_level = "medium"
        else:
            recommendation = "Weak case - consider alternative remedies first"
            risk_level = "low"

        return {
            "breach_id": breach_id,
            "rule_id": rule_id,
            "breaching_party": breaching_party,
            "severity": severity,
            "is_mandatory": is_mandatory,
            "strike_out_risk": strike_out_risk,
            "unless_order_applicable": unless_order_applicable,
            "prior_breach_count": prior_count,
            "risk_score": round(score, 2),
            "risk_level": risk_level,
            "recommendation": recommendation,
            "factors": factors,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_working_day(self, d: date) -> bool:
        """Return True if d is a working day (Mon-Fri, not a bank holiday)."""
        if d.weekday() >= 5:  # Saturday=5, Sunday=6
            return False
        if d in UK_BANK_HOLIDAYS:
            return False
        return True
