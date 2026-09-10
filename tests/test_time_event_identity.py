"""One source event has the same spelling in atom navigation and changes."""
from migloop import atoms, investigation
from tests.test_temporal_atom import call, pool, result, ts


def test_file_agent_and_change_inventory_share_the_write_event_id(tmp_path):
    ledger, aid, _ = pool(tmp_path, [call(1, "write-id", "Write", file_path="/project/A.ets", content="value"),
                                   result(2, "write-id")])
    file = investigation.query(ledger, "file", {"path": "/project/A.ets", "at": ts(3)})
    agent = investigation.query(ledger, "agent", {"id": aid, "at": ts(3)})
    changes = investigation.query(ledger, "changes", {"path": "/project/A.ets", "at": ts(3), "related_limit": 0})
    file_row, = file["sections"]["writes"]["rows"]
    agent_row, = agent["sections"]["writes"]["rows"]
    changed, = changes["rows"]
    assert file_row["id"] == agent_row["id"] == changed["id"] == changed["event_id"]
    assert file_row["operation"]["status"] == "confirmed"
    assert investigation._delivery(file)["records"] == []  # ID is still navigation, not delivered body.
    diff = investigation.query(ledger, "diff", {"path": "/project/A.ets", "at": ts(3)})
    assert diff["rows"][0]["event_id"] == changed["id"]


def test_known_action_identity_is_constant_time_and_not_sequence_identity(tmp_path, monkeypatch):
    ledger, aid, _ = pool(tmp_path, [call(1, "stable-native-id", "Write", file_path="/project/A.ets", content="value"),
                                   result(2, "stable-native-id")])
    owner = ledger.agents[aid]
    action = next(action for action in owner.actions if action.tuid == "stable-native-id")
    old = atoms.event_id(ledger, aid, action.seq)
    action.seq += 100  # More recognized actions must not rename a native event.
    assert atoms.event_id_for_action(owner, action) == old
    def fail_lookup(*_args, **_kwargs):
        raise AssertionError("already-held Action must not cause another whole-agent lookup")
    monkeypatch.setattr(atoms, "event_id", fail_lookup)
    file = investigation.query(ledger, "file", {"path": "/project/A.ets", "at": ts(3)})
    changes = investigation.query(ledger, "changes", {"path": "/project/A.ets", "at": ts(3), "related_limit": 0})
    assert file["sections"]["writes"]["rows"][0]["id"] == changes["rows"][0]["id"] == old
