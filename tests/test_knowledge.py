from fastapi.testclient import TestClient

from app.embeddings import embedding_client
from app.main import app
from app.models import Club, KnowledgeChunk, Member

client = TestClient(app)


def test_query_own_club_returns_results(db):
    db.add(Club(id="riverside", name="Riverside"))
    db.add(Member(club_id="riverside", name="A", email="a@example.com", token="tok-a", role="member"))
    db.add(
        KnowledgeChunk(
            club_id="riverside",
            title="Fees",
            body="Guest fees are $50.",
            embedding=embedding_client.embed("Guest fees are $50."),
        )
    )
    db.commit()

    resp = client.get(
        "/clubs/riverside/knowledge/query",
        params={"q": "guest fees"},
        headers={"X-Member-Token": "tok-a"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_query_rejects_non_member(db):
    db.add(Club(id="riverside", name="Riverside"))
    db.add(Club(id="oakhurst", name="Oakhurst"))
    db.add(Member(club_id="riverside", name="A", email="a@example.com", token="tok-a", role="member"))
    db.commit()

    resp = client.get(
        "/clubs/oakhurst/knowledge/query",
        params={"q": "guest fees"},
        headers={"X-Member-Token": "tok-a"},
    )
    assert resp.status_code == 403


def test_query_excludes_other_clubs_chunks_even_when_closer_match(db):
    db.add_all([Club(id="riverside", name="Riverside"), Club(id="oakhurst", name="Oakhurst")])
    db.add(Member(club_id="riverside", name="A", email="a@example.com", token="tok-a", role="member"))
    db.add(
        KnowledgeChunk(
            club_id="oakhurst",
            title="Oakhurst Fees",
            body="guest fees are fifty dollars",
            embedding=embedding_client.embed("guest fees are fifty dollars"),
        )
    )
    riverside_chunk = KnowledgeChunk(
        club_id="riverside",
        title="Riverside Pool Hours",
        body="the pool closes at nine pm",
        embedding=embedding_client.embed("the pool closes at nine pm"),
    )
    db.add(riverside_chunk)
    db.commit()

    # Query text is identical to the oakhurst chunk's body, so without a club
    # filter it would be the nearest match and rank first.
    resp = client.get(
        "/clubs/riverside/knowledge/query",
        params={"q": "guest fees are fifty dollars"},
        headers={"X-Member-Token": "tok-a"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert all(r["club_id"] == "riverside" for r in body)
    assert [r["chunk_id"] for r in body] == [riverside_chunk.id]


def test_query_returns_multiple_same_club_results_only(db):
    db.add_all([Club(id="riverside", name="Riverside"), Club(id="oakhurst", name="Oakhurst")])
    db.add(Member(club_id="riverside", name="A", email="a@example.com", token="tok-a", role="member"))
    riverside_ids = []
    for i in range(3):
        chunk = KnowledgeChunk(
            club_id="riverside",
            title=f"Riverside Topic {i}",
            body=f"riverside policy detail number {i}",
            embedding=embedding_client.embed(f"riverside policy detail number {i}"),
        )
        db.add(chunk)
        db.flush()
        riverside_ids.append(chunk.id)
    db.add(
        KnowledgeChunk(
            club_id="oakhurst",
            title="Oakhurst Topic",
            body="riverside policy detail number 0",
            embedding=embedding_client.embed("riverside policy detail number 0"),
        )
    )
    db.commit()

    resp = client.get(
        "/clubs/riverside/knowledge/query",
        params={"q": "riverside policy detail number 0"},
        headers={"X-Member-Token": "tok-a"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 3
    assert {r["chunk_id"] for r in body} == set(riverside_ids)
    assert all(r["club_id"] == "riverside" for r in body)
