"""Casemap Shard API endpoints."""

import logging
from typing import TYPE_CHECKING, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

if TYPE_CHECKING:
    from .shard import CasemapShard

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/casemap", tags=["casemap"])

_shard: Optional["CasemapShard"] = None
_event_bus = None


def init_api(shard=None, event_bus=None):
    global _shard, _event_bus
    _shard = shard
    _event_bus = event_bus


def get_shard(request: Request) -> "CasemapShard":
    shard = _shard or getattr(request.app.state, "casemap_shard", None)
    if not shard:
        raise HTTPException(status_code=503, detail="Casemap shard not available")
    return shard


# === Request Models ===


class TheoryCreate(BaseModel):
    title: str
    claim_type: str = "custom"
    description: str = ""
    statutory_basis: str = ""
    respondent_ids: list = []
    status: str = "active"
    notes: str = ""
    metadata: dict = {}
    seed_elements: bool = False


class TheoryUpdate(BaseModel):
    title: Optional[str] = None
    claim_type: Optional[str] = None
    description: Optional[str] = None
    statutory_basis: Optional[str] = None
    respondent_ids: Optional[list] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    metadata: Optional[dict] = None


class ElementCreate(BaseModel):
    title: str
    description: str = ""
    burden: str = "claimant"
    status: str = "unproven"
    required: bool = True
    statutory_reference: str = ""
    notes: str = ""
    display_order: Optional[int] = None


class ElementUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    burden: Optional[str] = None
    status: Optional[str] = None
    required: Optional[bool] = None
    statutory_reference: Optional[str] = None
    notes: Optional[str] = None
    display_order: Optional[int] = None


class EvidenceLinkCreate(BaseModel):
    document_id: Optional[str] = None
    witness_id: Optional[str] = None
    description: str = ""
    strength: str = "neutral"
    source_reference: str = ""
    supports_element: bool = True
    notes: str = ""


class SeedRequest(BaseModel):
    claim_type: str


# === Theory Endpoints ===


@router.get("/theories")
async def list_theories(
    request: Request,
    claim_type: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    min_strength: Optional[int] = None,
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
):
    shard = get_shard(request)
    from .models import ClaimType, TheoryFilter, TheoryStatus

    filters = TheoryFilter(
        claim_type=ClaimType(claim_type) if claim_type else None,
        status=TheoryStatus(status) if status else None,
        search_text=search,
        min_strength=min_strength,
    )
    theories = await shard.list_theories(filters=filters, limit=limit, offset=offset)
    from .shard import _theory_dict

    return {"theories": [_theory_dict(t) for t in theories], "total": len(theories)}


@router.get("/theories/count")
async def count_theories(request: Request):
    shard = get_shard(request)
    count = await shard.count_theories()
    return {"count": count}


@router.post("/theories")
async def create_theory(request: Request, body: TheoryCreate):
    shard = get_shard(request)
    data = body.model_dump(exclude_none=True)
    seed = data.pop("seed_elements", False)
    theory = await shard.create_theory(data)

    from .shard import _theory_dict

    result = _theory_dict(theory)

    if seed and body.claim_type != "custom":
        elements = await shard.seed_elements(theory.id, body.claim_type)
        from .shard import _element_dict

        result["seeded_elements"] = [_element_dict(e) for e in elements]

    return result


@router.get("/theories/{theory_id}")
async def get_theory(request: Request, theory_id: str):
    shard = get_shard(request)
    theory = await shard.get_theory(theory_id)
    if not theory:
        raise HTTPException(status_code=404, detail="Theory not found")
    from .shard import _element_dict, _theory_dict

    result = _theory_dict(theory)
    elements = await shard.list_elements(theory_id)
    result["elements"] = [_element_dict(e) for e in elements]
    return result


@router.put("/theories/{theory_id}")
async def update_theory(request: Request, theory_id: str, body: TheoryUpdate):
    shard = get_shard(request)
    theory = await shard.update_theory(theory_id, body.model_dump(exclude_none=True))
    if not theory:
        raise HTTPException(status_code=404, detail="Theory not found")
    from .shard import _theory_dict

    return _theory_dict(theory)


@router.delete("/theories/{theory_id}")
async def delete_theory(request: Request, theory_id: str):
    shard = get_shard(request)
    await shard.delete_theory(theory_id)
    return {"deleted": True}


# === Element Endpoints ===


@router.post("/theories/{theory_id}/elements")
async def create_element(request: Request, theory_id: str, body: ElementCreate):
    shard = get_shard(request)
    elem = await shard.create_element(theory_id, body.model_dump(exclude_none=True))
    from .shard import _element_dict

    return _element_dict(elem)


@router.get("/theories/{theory_id}/elements")
async def list_elements(request: Request, theory_id: str):
    shard = get_shard(request)
    elements = await shard.list_elements(theory_id)
    from .shard import _element_dict

    return {"elements": [_element_dict(e) for e in elements]}


@router.put("/elements/{element_id}")
async def update_element(request: Request, element_id: str, body: ElementUpdate):
    shard = get_shard(request)
    elem = await shard.update_element(element_id, body.model_dump(exclude_none=True))
    if not elem:
        raise HTTPException(status_code=404, detail="Element not found")
    from .shard import _element_dict

    return _element_dict(elem)


@router.delete("/elements/{element_id}")
async def delete_element(request: Request, element_id: str):
    shard = get_shard(request)
    await shard.delete_element(element_id)
    return {"deleted": True}


# === Evidence Endpoints ===


@router.post("/elements/{element_id}/evidence")
async def link_evidence(request: Request, element_id: str, body: EvidenceLinkCreate):
    shard = get_shard(request)
    link = await shard.link_evidence(element_id, body.model_dump(exclude_none=True))
    from .shard import _evidence_dict

    return _evidence_dict(link)


@router.get("/elements/{element_id}/evidence")
async def list_evidence(request: Request, element_id: str):
    shard = get_shard(request)
    evidence = await shard.list_evidence(element_id)
    from .shard import _evidence_dict

    return {"evidence": [_evidence_dict(e) for e in evidence]}


@router.delete("/evidence/{link_id}")
async def delete_evidence(request: Request, link_id: str):
    shard = get_shard(request)
    await shard.delete_evidence(link_id)
    return {"deleted": True}


# === Analysis Endpoints ===


@router.get("/theories/{theory_id}/strength")
async def assess_strength(request: Request, theory_id: str):
    shard = get_shard(request)
    assessment = await shard.assess_strength(theory_id)
    return {
        "theory_id": assessment.theory_id,
        "total_elements": assessment.total_elements,
        "proven_count": assessment.proven_count,
        "contested_count": assessment.contested_count,
        "unproven_count": assessment.unproven_count,
        "overall_score": assessment.overall_score,
        "gaps": assessment.gaps,
        "weaknesses": assessment.weaknesses,
        "strengths": assessment.strengths,
    }


@router.get("/theories/{theory_id}/gaps")
async def identify_gaps(request: Request, theory_id: str):
    shard = get_shard(request)
    gaps = await shard.identify_gaps(theory_id)
    return {"gaps": gaps, "gap_count": len(gaps)}


@router.get("/theories/{theory_id}/matrix")
async def get_matrix(request: Request, theory_id: str):
    shard = get_shard(request)
    return await shard.get_evidence_matrix(theory_id)


@router.get("/theories/{theory_id}/tree")
async def get_tree(request: Request, theory_id: str):
    shard = get_shard(request)
    return await shard.get_theory_tree(theory_id)


@router.post("/theories/{theory_id}/seed")
async def seed_elements(request: Request, theory_id: str, body: SeedRequest):
    shard = get_shard(request)
    elements = await shard.seed_elements(theory_id, body.claim_type)
    from .shard import _element_dict

    return {"seeded": len(elements), "elements": [_element_dict(e) for e in elements]}


# === Claim Type Templates ===


@router.get("/templates")
async def list_templates():
    """List available claim type element templates."""
    from .models import CLAIM_ELEMENT_TEMPLATES

    return {"templates": {k: {"element_count": len(v), "elements": v} for k, v in CLAIM_ELEMENT_TEMPLATES.items()}}
