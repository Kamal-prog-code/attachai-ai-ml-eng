from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth import get_current_member
from app.db import get_db
from app.llm_client import LLMClient, get_llm_client
from app.models import Member
from app.services.extraction_service import extract_batch

router = APIRouter(prefix="/clubs", tags=["extraction"])


class ExtractAttributesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message_ids: list[Annotated[int, Field(strict=True, gt=0)]] = Field(min_length=1, max_length=100)


class MessageExtractionResult(BaseModel):
    message_id: int
    status: Literal["extracted", "empty", "skipped", "not_found", "failed"]
    attribute_count: int
    error: str | None = None


class ExtractAttributesOut(BaseModel):
    results: list[MessageExtractionResult]


def require_club_extractor(club_id: str, member: Member = Depends(get_current_member)) -> Member:
    if member.role not in {"admin", "service"} or member.club_id != club_id:
        raise HTTPException(status_code=403, detail="admin/service access to this club required")
    return member


@router.post(
    "/{club_id}/extract-attributes",
    response_model=ExtractAttributesOut,
    response_model_exclude_none=True,
)
def extract_attributes(
    club_id: str,
    payload: ExtractAttributesIn,
    member: Member = Depends(require_club_extractor),
    db: Session = Depends(get_db),
    llm: LLMClient = Depends(get_llm_client),
):
    return {"results": extract_batch(db, club_id, payload.message_ids, llm)}