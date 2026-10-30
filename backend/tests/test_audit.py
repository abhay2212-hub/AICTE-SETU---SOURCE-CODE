# Owner: Dev B
from app.core.audit import GENESIS, append_event, canonical, compute_hash, verify_chain


def make_chain(n: int = 5) -> list[dict]:
    chain, prev = [], GENESIS
    for i in range(n):
        event = append_event(prev, {"id": i + 1, "action": "test", "payload": {"n": i}})
        chain.append(event)
        prev = event["hash"]
    return chain


def test_canonical_is_stable():
    assert canonical({"b": 1, "a": "é"}) == '{"a":"é","b":1}'


def test_compute_hash_depends_on_prev():
    assert compute_hash(GENESIS, {"a": 1}) != compute_hash("1" * 64, {"a": 1})


def test_valid_chain():
    assert verify_chain(make_chain()) is None
    assert verify_chain([]) is None


def test_edited_payload():
    chain = make_chain()
    chain[2]["payload"] = {"n": 999}
    assert verify_chain(chain) == 2


def test_deleted_event():
    chain = make_chain()
    del chain[3]
    assert verify_chain(chain) == 3


def test_deleted_first_event():
    chain = make_chain()
    del chain[0]
    assert verify_chain(chain) == 0


def test_reordered_events():
    chain = make_chain()
    chain[1], chain[2] = chain[2], chain[1]
    assert verify_chain(chain) == 1


def test_mock_audit_chain_is_intact(client):
    body = client.get("/audit/verify").json()
    assert body == {"ok": True, "first_broken_index": None, "checked": 5}
