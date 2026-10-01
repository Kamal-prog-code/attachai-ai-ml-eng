from fastapi.testclient import TestClient

from app.main import app
from app.models import Club, Member, MemberAttribute

client = TestClient(app)


def test_generate_reason_includes_attributes(db):
    db.add(Club(id="riverside", name="Riverside"))
    m1 = Member(club_id="riverside", name="A", email="a@example.com", token="tok-a", role="member")
    m2 = Member(club_id="riverside", name="B", email="b@example.com", token="tok-b", role="member")
    db.add_all([m1, m2])
    db.commit()

    db.add(MemberAttribute(member_id=m1.id, club_id="riverside", kind="need", text="needs a CFO", confidence=0.9))
    db.add(MemberAttribute(member_id=m2.id, club_id="riverside", kind="offer", text="offers CFO services", confidence=0.9))
    db.commit()

    resp = client.get(
        f"/introductions/{m1.id}/{m2.id}",
        params={"reason": "business"},
        headers={"X-Member-Token": "tok-a"},
    )
    assert resp.status_code == 200
    assert "CFO" in resp.json()["reason_text"]


def test_generate_reason_excludes_low_confidence_attributes(db):
    db.add(Club(id="riverside", name="Riverside"))
    m1 = Member(club_id="riverside", name="A", email="a@example.com", token="tok-a", role="member")
    m2 = Member(club_id="riverside", name="B", email="b@example.com", token="tok-b", role="member")
    db.add_all([m1, m2])
    db.commit()

    db.add(MemberAttribute(member_id=m1.id, club_id="riverside", kind="need", text="needs a CFO", confidence=0.9))
    db.add(
        MemberAttribute(
            member_id=m2.id, club_id="riverside", kind="offer", text="maybe offers CFO services", confidence=0.4
        )
    )
    db.commit()

    resp = client.get(
        f"/introductions/{m1.id}/{m2.id}",
        params={"reason": "business"},
        headers={"X-Member-Token": "tok-a"},
    )
    assert resp.status_code == 200
    assert "maybe offers CFO services" not in resp.json()["reason_text"]


def test_generate_reason_rejects_foreign_target_as_member_a(db):
    db.add_all([Club(id="riverside", name="Riverside"), Club(id="oakhurst", name="Oakhurst")])
    caller = Member(club_id="riverside", name="A", email="a@example.com", token="tok-a", role="member")
    foreign = Member(club_id="oakhurst", name="F", email="f@example.com", token="tok-f", role="member")
    same_club = Member(club_id="riverside", name="B", email="b@example.com", token="tok-b", role="member")
    db.add_all([caller, foreign, same_club])
    db.commit()

    resp = client.get(
        f"/introductions/{foreign.id}/{same_club.id}",
        params={"reason": "business"},
        headers={"X-Member-Token": "tok-a"},
    )
    assert resp.status_code == 404


def test_generate_reason_rejects_foreign_target_as_member_b(db):
    db.add_all([Club(id="riverside", name="Riverside"), Club(id="oakhurst", name="Oakhurst")])
    caller = Member(club_id="riverside", name="A", email="a@example.com", token="tok-a", role="member")
    foreign = Member(club_id="oakhurst", name="F", email="f@example.com", token="tok-f", role="member")
    same_club = Member(club_id="riverside", name="B", email="b@example.com", token="tok-b", role="member")
    db.add_all([caller, foreign, same_club])
    db.commit()

    resp = client.get(
        f"/introductions/{same_club.id}/{foreign.id}",
        params={"reason": "business"},
        headers={"X-Member-Token": "tok-a"},
    )
    assert resp.status_code == 404


def test_generate_reason_rejects_missing_target(db):
    db.add(Club(id="riverside", name="Riverside"))
    caller = Member(club_id="riverside", name="A", email="a@example.com", token="tok-a", role="member")
    same_club = Member(club_id="riverside", name="B", email="b@example.com", token="tok-b", role="member")
    db.add_all([caller, same_club])
    db.commit()

    missing_id = same_club.id + 999

    resp = client.get(
        f"/introductions/{same_club.id}/{missing_id}",
        params={"reason": "business"},
        headers={"X-Member-Token": "tok-a"},
    )
    assert resp.status_code == 404


def test_generate_reason_admin_caller_same_club(db):
    db.add(Club(id="riverside", name="Riverside"))
    admin = Member(club_id="riverside", name="Admin", email="admin@example.com", token="tok-admin", role="admin")
    m1 = Member(club_id="riverside", name="A", email="a@example.com", token="tok-a", role="member")
    m2 = Member(club_id="riverside", name="B", email="b@example.com", token="tok-b", role="member")
    db.add_all([admin, m1, m2])
    db.commit()

    db.add(MemberAttribute(member_id=m1.id, club_id="riverside", kind="need", text="needs a CFO", confidence=0.9))
    db.add(MemberAttribute(member_id=m2.id, club_id="riverside", kind="offer", text="offers CFO services", confidence=0.9))
    db.commit()

    resp = client.get(
        f"/introductions/{m1.id}/{m2.id}",
        params={"reason": "business"},
        headers={"X-Member-Token": "tok-admin"},
    )
    assert resp.status_code == 200
    assert "CFO" in resp.json()["reason_text"]


def test_generate_reason_admin_caller_rejects_foreign_target(db):
    db.add_all([Club(id="riverside", name="Riverside"), Club(id="oakhurst", name="Oakhurst")])
    admin = Member(club_id="riverside", name="Admin", email="admin@example.com", token="tok-admin", role="admin")
    foreign = Member(club_id="oakhurst", name="F", email="f@example.com", token="tok-f", role="member")
    same_club = Member(club_id="riverside", name="B", email="b@example.com", token="tok-b", role="member")
    db.add_all([admin, foreign, same_club])
    db.commit()

    resp = client.get(
        f"/introductions/{same_club.id}/{foreign.id}",
        params={"reason": "business"},
        headers={"X-Member-Token": "tok-admin"},
    )
    assert resp.status_code == 404


def test_generate_reason_excludes_restricted_attributes(db):
    db.add(Club(id="riverside", name="Riverside"))
    m1 = Member(club_id="riverside", name="A", email="a@example.com", token="tok-a", role="member")
    m2 = Member(club_id="riverside", name="B", email="b@example.com", token="tok-b", role="member")
    db.add_all([m1, m2])
    db.commit()

    db.add(MemberAttribute(member_id=m1.id, club_id="riverside", kind="need", text="needs a CFO", confidence=0.9))
    db.add(
        MemberAttribute(
            member_id=m2.id,
            club_id="riverside",
            kind="offer",
            text="secret medical detail",
            confidence=0.9,
            restricted=True,
        )
    )
    db.add(MemberAttribute(member_id=m2.id, club_id="riverside", kind="offer", text="offers CFO services", confidence=0.9))
    db.commit()

    resp = client.get(
        f"/introductions/{m1.id}/{m2.id}",
        params={"reason": "business"},
        headers={"X-Member-Token": "tok-a"},
    )
    assert resp.status_code == 200
    reason_text = resp.json()["reason_text"]
    assert "offers CFO services" in reason_text
    assert "secret medical detail" not in reason_text


def test_generate_reason_excludes_attribute_with_misassigned_club(db):
    db.add_all([Club(id="riverside", name="Riverside"), Club(id="oakhurst", name="Oakhurst")])
    m1 = Member(club_id="riverside", name="A", email="a@example.com", token="tok-a", role="member")
    m2 = Member(club_id="riverside", name="B", email="b@example.com", token="tok-b", role="member")
    db.add_all([m1, m2])
    db.commit()

    db.add(MemberAttribute(member_id=m1.id, club_id="riverside", kind="need", text="needs a CFO", confidence=0.9))
    # Data-integrity edge case: attribute row tagged with the wrong club despite a same-club member_id.
    db.add(MemberAttribute(member_id=m2.id, club_id="oakhurst", kind="offer", text="offers CFO services", confidence=0.9))
    db.commit()

    resp = client.get(
        f"/introductions/{m1.id}/{m2.id}",
        params={"reason": "business"},
        headers={"X-Member-Token": "tok-a"},
    )
    assert resp.status_code == 200
    reason_text = resp.json()["reason_text"]
    assert "needs a CFO" in reason_text
    assert "offers CFO services" not in reason_text
