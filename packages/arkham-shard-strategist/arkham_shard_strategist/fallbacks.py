"""Heuristic fallback templates for when LLM is unavailable.

Provides template-based analysis drawn from common UK Employment Tribunal
patterns. These are not a substitute for LLM analysis but ensure the
Strategist shard produces useful output even without an LLM connection.
"""

from typing import Any

# =============================================================================
# Claim-type -> template respondent arguments
# =============================================================================

_CLAIM_ARGUMENTS: dict[str, list[dict[str, Any]]] = {
    "s13_discrimination": [
        {
            "argument": "Legitimate business reason unrelated to protected characteristic",
            "confidence": 0.8,
            "reasoning": "[heuristic] Standard s.13 EqA 2010 defence — respondent asserts non-discriminatory motive",
            "likely_evidence": ["Business case documents", "Decision-maker witness statement"],
        },
        {
            "argument": "No knowledge of the claimant's protected characteristic",
            "confidence": 0.7,
            "reasoning": "[heuristic] Respondent denies awareness of the relevant protected characteristic",
            "likely_evidence": ["HR records", "Recruitment files", "Management correspondence"],
        },
        {
            "argument": "Comparator relied upon is not in materially similar circumstances",
            "confidence": 0.65,
            "reasoning": "[heuristic] Challenge the validity of the comparator under s.23 EqA 2010",
            "likely_evidence": ["Comparator job description", "Comparator disciplinary records"],
        },
        {
            "argument": "Proportionate means of achieving a legitimate aim (justification)",
            "confidence": 0.6,
            "reasoning": "[heuristic] If indirect discrimination alleged, respondent raises objective justification",
            "likely_evidence": ["Policy documents", "Business impact assessments"],
        },
    ],
    "s26_harassment": [
        {
            "argument": "Conduct was not related to a protected characteristic",
            "confidence": 0.75,
            "reasoning": "[heuristic] Standard s.26 defence — deny the protected characteristic nexus",
            "likely_evidence": ["Context of interactions", "Witness statements"],
        },
        {
            "argument": "Reasonable steps were taken to prevent the conduct",
            "confidence": 0.7,
            "reasoning": "[heuristic] Employer's s.109(4) EqA 2010 statutory defence",
            "likely_evidence": ["Anti-harassment policy", "Training records", "Investigation notes"],
        },
        {
            "argument": "Conduct did not have the purpose or effect of violating dignity",
            "confidence": 0.65,
            "reasoning": "[heuristic] Challenge the subjective and objective perception test under s.26(4)",
            "likely_evidence": ["Contemporaneous communications", "Claimant's responses at the time"],
        },
        {
            "argument": "Alleged conduct amounts to reasonable management instruction or banter",
            "confidence": 0.55,
            "reasoning": "[heuristic] Characterise conduct as proportionate management or workplace norms",
            "likely_evidence": ["Meeting minutes", "Management guidance documents"],
        },
    ],
    "s27_victimisation": [
        {
            "argument": "No protected act was done by the claimant",
            "confidence": 0.7,
            "reasoning": "[heuristic] Deny that any communication constituted a protected act under s.27(2)",
            "likely_evidence": ["Claimant's grievance/complaint text", "HR correspondence"],
        },
        {
            "argument": "Detrimental treatment was unrelated to any protected act",
            "confidence": 0.75,
            "reasoning": "[heuristic] Assert the treatment would have occurred regardless",
            "likely_evidence": ["Decision timeline", "Business justification documents"],
        },
        {
            "argument": "Decision-maker had no knowledge of the protected act",
            "confidence": 0.65,
            "reasoning": "[heuristic] Challenge causal link by showing decision-maker was unaware",
            "likely_evidence": ["Communication records", "Organisational chart", "Decision-maker statement"],
        },
    ],
    "unfair_dismissal": [
        {
            "argument": "Dismissal was for a fair reason: capability or conduct",
            "confidence": 0.8,
            "reasoning": "[heuristic] Assert s.98(2) ERA 1996 — potentially fair reason for dismissal",
            "likely_evidence": ["Performance reviews", "Disciplinary records", "Warning letters"],
        },
        {
            "argument": "Fair procedure was followed including ACAS Code compliance",
            "confidence": 0.75,
            "reasoning": "[heuristic] Demonstrate procedural fairness under s.98(4) ERA 1996",
            "likely_evidence": ["Investigation notes", "Disciplinary hearing minutes", "Appeal outcome letter"],
        },
        {
            "argument": "Dismissal fell within the range of reasonable responses",
            "confidence": 0.7,
            "reasoning": "[heuristic] Apply the Burchell test / range of reasonable responses test",
            "likely_evidence": ["Comparable sanctions for similar conduct", "Policy documents"],
        },
        {
            "argument": "Claimant contributed to dismissal through own conduct",
            "confidence": 0.6,
            "reasoning": "[heuristic] Argue contributory fault to reduce compensation under s.123(6) ERA 1996",
            "likely_evidence": ["Claimant conduct records", "Witness statements on behaviour"],
        },
    ],
}

# General arguments applicable to any claim type
_GENERAL_ARGUMENTS: list[dict[str, Any]] = [
    {
        "argument": "Claim is out of time and no just and equitable extension should be granted",
        "confidence": 0.6,
        "reasoning": "[heuristic] Time limitation defence — standard preliminary objection",
        "likely_evidence": ["ACAS early conciliation certificate dates", "ET1 filing date"],
    },
    {
        "argument": "Claimant failed to exhaust internal procedures before bringing claim",
        "confidence": 0.55,
        "reasoning": "[heuristic] Procedural defence to reduce credibility or compensation",
        "likely_evidence": ["Grievance policy", "HR records of complaints"],
    },
    {
        "argument": "Claimant failed to mitigate their loss",
        "confidence": 0.5,
        "reasoning": "[heuristic] Standard remedy-stage argument to reduce compensation",
        "likely_evidence": ["Job search records", "Claimant's financial disclosure"],
    },
]


def fallback_predict_arguments(claim_id: str | None = None) -> list[dict[str, Any]]:
    """Return template respondent arguments based on claim type.

    Checks for exact match and substring match against known claim types.
    Falls back to general arguments if claim type is not recognised.
    """
    if claim_id:
        # Exact match first
        if claim_id in _CLAIM_ARGUMENTS:
            return [dict(a) for a in _CLAIM_ARGUMENTS[claim_id]]

        # Substring match (e.g. claim_id might contain the type key)
        claim_lower = claim_id.lower()
        for key, args in _CLAIM_ARGUMENTS.items():
            if key in claim_lower or claim_lower in key:
                return [dict(a) for a in args]

    # Fall back to general arguments
    return [dict(a) for a in _GENERAL_ARGUMENTS]


# =============================================================================
# SWOT heuristic fallback
# =============================================================================


def fallback_swot(context_data: dict[str, Any] | None = None) -> dict[str, list[dict[str, str]]]:
    """Generate heuristic SWOT from available context data.

    context_data may contain:
      - predictions: list of dicts with predicted_argument and confidence
    """
    preds = (context_data or {}).get("predictions", [])
    num_preds = len(preds)
    high_conf = [p for p in preds if p.get("confidence", 0) >= 0.7]

    strengths: list[dict[str, str]] = []
    weaknesses: list[dict[str, str]] = []
    opportunities: list[dict[str, str]] = []
    threats: list[dict[str, str]] = []

    # --- Dynamic items based on DB context ---
    if num_preds > 0:
        strengths.append(
            {
                "item": "Respondent arguments identified in advance",
                "detail": f"{num_preds} predicted respondent argument(s) mapped — enables targeted preparation",
            }
        )

    if high_conf:
        opportunities.append(
            {
                "item": "High-confidence respondent arguments are predictable",
                "detail": (
                    f"{len(high_conf)} argument(s) rated >= 0.7 confidence — prepare specific rebuttals "
                    "and evidence bundles for these known lines of attack"
                ),
            }
        )

    if num_preds == 0:
        weaknesses.append(
            {
                "item": "Limited adversarial intelligence",
                "detail": "No predicted respondent arguments available — case preparation lacks adversarial modelling",
            }
        )

    # --- Generic template items (always included) ---
    strengths.extend(
        [
            {
                "item": "Documentary evidence trail",
                "detail": "Contemporaneous documents (emails, meeting notes) corroborate the claimant's account",
            },
            {
                "item": "Legal framework supports claims",
                "detail": "Claims grounded in established statutory protections (EqA 2010, ERA 1996)",
            },
        ]
    )

    weaknesses.extend(
        [
            {
                "item": "Potential gaps in timeline",
                "detail": "Periods without contemporaneous evidence may be challenged as unreliable recollection",
            },
            {
                "item": "Unverified claims require corroboration",
                "detail": "Assertions without documentary or witness support are vulnerable to challenge",
            },
        ]
    )

    opportunities.extend(
        [
            {
                "item": "Respondent procedural breaches",
                "detail": "Failure to follow own policies or ACAS Code of Practice strengthens claimant's position",
            },
            {
                "item": "Disclosure failures by respondent",
                "detail": "Incomplete or delayed disclosure may indicate concealment of unfavourable evidence",
            },
        ]
    )

    threats.extend(
        [
            {
                "item": "Limitation issues on some claims",
                "detail": "Claims outside the primary limitation period require just and equitable extension arguments",
            },
            {
                "item": "Witness credibility challenges",
                "detail": "Cross-examination may undermine witness reliability if accounts are inconsistent",
            },
        ]
    )

    return {
        "strengths": strengths,
        "weaknesses": weaknesses,
        "opportunities": opportunities,
        "threats": threats,
    }


# =============================================================================
# Red team heuristic fallback
# =============================================================================

_TEMPLATE_WEAKNESSES: list[dict[str, str]] = [
    {
        "area": "Burden of proof gaps",
        "vulnerability": "Insufficient evidence to shift the burden of proof to the respondent under s.136 EqA 2010",
        "exploitation_method": (
            "Challenge each factual allegation individually, arguing no prima facie case "
            "is established before the burden shifts"
        ),
    },
    {
        "area": "Hearsay reliance",
        "vulnerability": "Key assertions rely on hearsay or second-hand accounts rather than direct evidence",
        "exploitation_method": (
            "Object to hearsay evidence weight, demand original sources, "
            "and cross-examine on reliability of indirect accounts"
        ),
    },
    {
        "area": "Timeline inconsistencies",
        "vulnerability": "Gaps or contradictions in the chronological narrative undermine credibility",
        "exploitation_method": (
            "Map detailed timeline and highlight discrepancies between witness statement, "
            "ET1, and contemporaneous documents during cross-examination"
        ),
    },
    {
        "area": "Witness credibility",
        "vulnerability": "Witnesses may have personal relationships or interests that affect impartiality",
        "exploitation_method": (
            "Explore bias, motive, and relationship with claimant to undermine "
            "witness testimony during cross-examination"
        ),
    },
    {
        "area": "Evidence preservation",
        "vulnerability": "Potential gaps in document preservation or missing metadata",
        "exploitation_method": (
            "Request specific disclosure of metadata, audit logs, and deleted communications "
            "to expose incomplete evidence trails"
        ),
    },
]


def fallback_red_team() -> dict[str, Any]:
    """Return template vulnerability patterns for red team analysis."""
    return {
        "weaknesses": [dict(w) for w in _TEMPLATE_WEAKNESSES],
        "overall_risk": 0.5,
    }
