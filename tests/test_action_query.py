import asyncio
import pytest

from migloop import action_query, atom_queries, atoms_text, mcp_server, probe, service
from tests.test_verdict import _pool


def sample(tmp_path):
    ledger = _pool(tmp_path)
    owner = ledger.agents["agent-c"]
    act = next(a for a in owner.actions if a.tool == "Write")
    ref = atoms_text._core(act.seq, ledger.locs[act.seq])
    return ledger, owner, act, ref


def test_copied_citation_resolves_actual_owner_without_treating_tag_as_id(tmp_path):
    ledger, owner, act, ref = sample(tmp_path)
    got = action_query.resolve(ledger, ref=ref)
    assert (got.agent, got.seq, got.status) == (owner.id, act.seq, "ok")
    by_id = atom_queries.render_text(ledger, "/proj", "action", {"id": owner.id, "seq": act.seq})
    by_ref = atom_queries.render_text(ledger, "/proj", "action", {"ref": ref})
    assert by_ref == by_id
    assert "原文引用: " + ref in by_ref
    assert probe._step_node(ledger, "action", {"ref": ref}) == {
        "kind": "agent", "aid": owner.id, "v": act.ver, "action": act.seq}
    assert ref in probe._step_scope("action", {"ref": ref, "part": "input"})


def test_human_writer_labels_also_supply_the_actual_callable_id(tmp_path):
    ledger, owner, act, ref = sample(tmp_path)
    assert f"id={owner.id}" in atoms_text._who(ledger, owner.id, act.ver)
    assert f"id={owner.id}" in atoms_text._who(ledger, owner.id, owner.n_versions + 1)
    assert "id=" not in atoms_text._who(ledger, "__external__", None)


def test_ref_drift_uses_unique_location_and_exposes_it_not_old_number(tmp_path):
    ledger, owner, act, ref = sample(tmp_path)
    drifted = ref.replace(f":{act.seq}@", ":999999@")
    got = action_query.resolve(ledger, ref=drifted)
    assert got.seq == act.seq and got.status == "drifted"
    text = atom_queries.render_text(ledger, "/proj", "action", {"ref": drifted})
    assert "序号已漂移" in text and "原文引用: " + ref in text
    raw = atom_queries.json_data(ledger, "action", {"ref": drifted})
    assert raw["query_reference"] == {"ref": drifted, "status": "drifted", "agent": owner.id, "seq": act.seq}
    legacy = atom_queries.json_data(ledger, "action", {"id": owner.id, "seq": act.seq})
    assert {k: v for k, v in raw.items() if k != "query_reference"} == legacy


@pytest.mark.parametrize("change", ["untagged", "line_zero", "number_zero", "wrong_line", "prose", "node", "ambiguous"])
def test_bad_reference_has_no_sequence_fallback(tmp_path, change):
    ledger, owner, act, ref = sample(tmp_path)
    if change == "untagged": ref = f"#{act.seq}@L{act.src[1]+1}"
    if change == "line_zero": ref = ref.split("@L")[0] + "@L0"
    if change == "number_zero": ref = ref.replace(f":{act.seq}@", ":0@")
    if change == "wrong_line": ref = ref.split("@L")[0] + "@L9999999"
    if change == "prose": ref = "please read " + ref
    if change == "node": ref = "file:/proj/A.ets@v1"
    if change == "ambiguous":
        tag = ref[1:].split(":")[0]
        ledger.loc_ambiguous.add((tag, act.src[1] + 1, act.blk))
    with pytest.raises(ValueError):
        atom_queries.render_text(ledger, "/proj", "action", {"ref": ref})
    assert probe._step_node(ledger, "action", {"ref": ref}) is None


def test_source_pointer_disagreement_is_not_a_located_reference(tmp_path):
    ledger, owner, act, ref = sample(tmp_path)
    act.src = (act.src[0], act.src[1] + 1, act.src[2])
    with pytest.raises(ValueError, match="指针不一致"):
        action_query.resolve(ledger, ref=ref)


def test_duplicate_action_owner_is_ambiguous(tmp_path):
    ledger, owner, act, ref = sample(tmp_path)
    owner.actions.append(act)
    with pytest.raises(ValueError, match="归属缺失或歧义"):
        action_query.resolve(ledger, ref=ref)


@pytest.mark.parametrize("extra", [{"id": "agent-c"}, {"seq": 1}, {"id": "agent-c", "seq": 1}])
def test_ref_and_legacy_address_cannot_be_mixed(extra):
    with pytest.raises(ValueError, match="二选一"):
        atom_queries.parameters("action", {"ref": "#tag:1@L1", **extra})


@pytest.mark.parametrize("args", [{}, {"id": "agent-c"}, {"seq": 1}])
def test_action_still_requires_a_complete_address(args):
    with pytest.raises(ValueError, match="action 需要"):
        atom_queries.parameters("action", args)


def test_bad_owner_does_not_map_to_some_other_agent_by_global_sequence(tmp_path):
    ledger, owner, act, ref = sample(tmp_path)
    assert probe._step_node(ledger, "action", {"id": "wrong-transcript-tag", "seq": act.seq}) is None
    for seq in (True, 1.7):
        assert probe._step_node(ledger, "action", {"id": owner.id, "seq": seq}) is None
    assert probe._step_node(ledger, "action", {"id": "agent-f", "seq": act.seq}) is None


@pytest.mark.parametrize("alias", ["conv-a", "c"])
def test_legacy_unique_aliases_are_explicit_and_never_fall_back_to_another_owner(tmp_path, alias):
    ledger, owner, act, ref = sample(tmp_path)
    got = action_query.resolve(ledger, id=alias, seq=act.seq)
    assert got.status == "legacy_alias" and got.agent == owner.id and got.requested_id == alias
    text = atom_queries.render_text(ledger, "/proj", "action", {"id": alias, "seq": act.seq})
    assert "旧代理别名" in text and f"id={owner.id}" in text
    other = next(a for a in ledger.agents["agent-f"].actions if a.tool == "Write")
    assert action_query.step(ledger, action_query.resolve(ledger, id=alias, seq=other.seq)) is None
    missing = atom_queries.render_text(ledger, "/proj", "action", {"id": alias, "seq": other.seq})
    assert "没有这个动作" in missing and "原文引用:" not in missing


def test_ambiguous_name_is_not_resolved_by_matching_sequence(tmp_path):
    ledger, owner, act, ref = sample(tmp_path)
    owner.name = ledger.agents["agent-f"].name = "same-name"
    got = action_query.resolve(ledger, id="same-name", seq=act.seq)
    assert got.status == "missing_owner" and action_query.step(ledger, got) is None


def test_tail_reference_locates_original_action_without_creating_effect_version(tmp_path):
    ledger, owner, act, ref = sample(tmp_path)
    act.ver = None
    act.at = owner.n_versions + 2
    address = action_query.resolve(ledger, ref=ref)
    assert action_query.step(ledger, address) == {
        "kind": "agent", "aid": owner.id, "v": None, "action": act.seq}


def test_mcp_http_and_json_use_same_reference_resolver_and_preserve_windows(tmp_path, monkeypatch):
    ledger, owner, act, ref = sample(tmp_path)
    monkeypatch.setattr(service, "session_ledger", lambda _: ledger)
    monkeypatch.setattr(service, "session_cwd", lambda _: "/proj")
    args = {"ref": ref, "part": "input", "max_chars": 30, "offset": 1}
    expected = atom_queries.render_text(ledger, "/proj", "action", args)
    assert service.atom_text("unused", "action", args) == expected
    pytest.importorskip("mcp")

    class Backend:
        async def get_ledger(self, sid): return ledger
        async def get_session_cwd(self, sid): return "/proj"

    blocks = asyncio.run(mcp_server.build_server(Backend()).call_tool("action", {"sid": "unused", **args}))
    assert len(blocks) == 1 and blocks[0].text == expected
