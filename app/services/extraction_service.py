"""Per-message extraction transactions over the existing attributes schema."""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm_client import ExtractionError, LLMClient, ExtractedAttribute, validate_attributes
from app.models import ConversationMessage, Member, MemberAttribute

logger = logging.getLogger(__name__)


def extract_message_text(message_text: str, llm: LLMClient) -> list[ExtractedAttribute]:
    return validate_attributes(llm.extract_attributes(message_text))


def extract_batch(db: Session, club_id: str, message_ids: list[int], llm: LLMClient) -> list[dict]:
    results = []
    for message_id in dict.fromkeys(message_ids):
        try:
            message = db.scalar(
                select(ConversationMessage)
                .join(Member, Member.id == ConversationMessage.member_id)
                .where(
                    ConversationMessage.id == message_id,
                    ConversationMessage.club_id == club_id,
                    Member.club_id == club_id,
                )
                .with_for_update(of=ConversationMessage)
            )
            if message is None:
                db.rollback()
                results.append({"message_id": message_id, "status": "not_found", "attribute_count": 0})
                continue

            existing_ids = db.scalars(
                select(MemberAttribute.id).where(
                    MemberAttribute.source_message_id == message.id,
                    MemberAttribute.club_id == club_id,
                )
            ).all()
            if existing_ids:
                db.commit()
                results.append(
                    {"message_id": message_id, "status": "skipped", "attribute_count": len(existing_ids)}
                )
                continue

            attributes = extract_message_text(message.body, llm)
            db.add_all(
                [
                    MemberAttribute(
                        member_id=message.member_id,
                        club_id=club_id,
                        source_message_id=message.id,
                        **attribute,
                    )
                    for attribute in attributes
                ]
            )
            db.commit()
            results.append(
                {
                    "message_id": message_id,
                    "status": "extracted" if attributes else "empty",
                    "attribute_count": len(attributes),
                }
            )
        except Exception as exc:
            db.rollback()
            error_code = exc.code if isinstance(exc, ExtractionError) else "extraction_failed"
            logger.warning("extraction failed message_id=%s code=%s", message_id, error_code)
            results.append(
                {"message_id": message_id, "status": "failed", "attribute_count": 0, "error": error_code}
            )
    return results