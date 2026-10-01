from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_member
from app.config import settings
from app.db import get_db
from app.models import Member, MemberAttribute

router = APIRouter(prefix="/introductions", tags=["introductions"])


@router.get("/{member_a_id}/{member_b_id}")
def generate_reason(
    member_a_id: int,
    member_b_id: int,
    reason: str,
    db: Session = Depends(get_db),
    member: Member = Depends(get_current_member),
):
    target_ids = {member_a_id, member_b_id}
    targets = (
        db.query(Member)
        .filter(Member.id.in_(target_ids), Member.club_id == member.club_id)
        .all()
    )
    # Same 404 for missing and foreign-club targets so neither case discloses membership.
    if {target.id for target in targets} != target_ids:
        raise HTTPException(status_code=404, detail="member not found")

    attrs = (
        db.query(MemberAttribute)
        .filter(
            MemberAttribute.member_id.in_(target_ids),
            MemberAttribute.club_id == member.club_id,
            MemberAttribute.restricted.is_(False),
            MemberAttribute.confidence >= settings.introduction_min_confidence,
        )
        .order_by(MemberAttribute.id)
        .all()
    )

    a_text = "; ".join(a.text for a in attrs if a.member_id == member_a_id)
    b_text = "; ".join(a.text for a in attrs if a.member_id == member_b_id)
    return {"reason_text": f"Because {a_text} and {b_text} — a good {reason} match."}
