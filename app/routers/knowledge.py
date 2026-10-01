from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_member
from app.db import get_db
from app.embeddings import embedding_client
from app.models import KnowledgeChunk, Member

router = APIRouter(prefix="/clubs", tags=["knowledge"])


@router.get("/{club_id}/knowledge/query")
def query_knowledge(
    club_id: str,
    q: str,
    member: Member = Depends(get_current_member),
    db: Session = Depends(get_db),
):
    if club_id != member.club_id:
        raise HTTPException(status_code=403, detail="not a member of this club")

    query_vec = embedding_client.embed(q)

    results = (
        db.query(KnowledgeChunk)
        .filter(KnowledgeChunk.club_id==member.club_id)
        .order_by(KnowledgeChunk.embedding.cosine_distance(query_vec))
        .limit(5)
        .all()
    )
    return [
        {"chunk_id": r.id, "club_id": r.club_id, "title": r.title, "body": r.body}
        for r in results
    ]
