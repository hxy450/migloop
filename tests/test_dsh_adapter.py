# -*- coding: utf-8 -*-
"""DeepSeek Harness (dsh) source: log decoding, report adapter, CLI lookup.

Fixtures are real dsh 0.2.2-rc.1 recordings (deepseek-flash), scrubbed by the
recording harness: a migration Session that dispatched one sub-agent and wrote
three files, its sub-agent Session (also stored Zstandard-compressed the way dsh
writes it), and a separate repair Session that made two fix commits.
"""
import json
import os
import shutil
from pathlib import Path

import pytest

from migloop import adapters
from migloop.adapters import dsh, dsh_source
from migloop.render import build_html, load_template

FIX = Path(__file__).resolve().parent / "fixtures" / "dsh"
ROOT = FIX / "sessions"
PROJECT = ROOT / "--C-work-toyapp--"
MIGRATION = "session-638f5638-1c32-4aa4-acd1-74c70755228b"
CHILD = "4bcd89b1-6820-4d3c-9994-a8c21c6fab6b"
REPAIR = "session-449c8f06-ee79-45f1-8e19-016d480a7352"
DISPATCH_CALL = "call_00_ET_QaFEMl43McEFPt90rtG23944"


def gen(sid):
    return str(PROJECT / sid / "session.v4.jsonl")


def zstd_backend():
    try:
        dsh_source.decompress(b"\x28\xb5\x2f\xfd\x20\x00\x01\x00\x00", [(0, 9)])
        return True
    except (dsh_source.ZstdUnavailable, ValueError, OSError):
        return False


# --------------------------------------------------------------------------- log decoding

def test_generation_selection_and_header():
    assert dsh_source.generation_of("session.jsonl") == (0, False)
    assert dsh_source.generation_of("session.v4.jsonl.zstd") == (4, True)
    assert dsh_source.generation_of("session.v12.jsonl") == (12, False)
    assert dsh_source.generation_of("session.lock") is None
    assert dsh_source.resolve(str(PROJECT / MIGRATION)) == gen(MIGRATION)
    header = dsh_source.read_header(gen(CHILD))
    assert header["parentSession"] == MIGRATION and header["origin"] == "subagent"


def test_highest_generation_wins(tmp_path):
    sdir = tmp_path / "proj" / "s1"
    sdir.mkdir(parents=True)
    (sdir / "session.v3.jsonl").write_text('{"type":"session","version":3,"id":"s1"}\n', encoding="utf-8")
    shutil.copy(gen(REPAIR), sdir / "session.v4.jsonl")
    assert dsh_source.select_generation(str(sdir)).endswith("session.v4.jsonl")


def test_unsupported_version_is_refused(tmp_path):
    p = tmp_path / "proj" / "s1" / "session.v3.jsonl"
    p.parent.mkdir(parents=True)
    p.write_text('{"type":"session","version":3,"id":"s1"}\n{"type":"turn/start","seq":0,"time":1,"data":{}}\n',
                 encoding="utf-8")
    with pytest.raises(dsh_source.UnsupportedSessionFormat):
        dsh_source.read_session(str(p))
    assert dsh_source.peek_header(str(p)) is None
    assert not dsh.is_session(str(p))


def test_torn_final_line_is_discarded(tmp_path):
    p = tmp_path / "proj" / "s1" / "session.v4.jsonl"
    p.parent.mkdir(parents=True)
    data = Path(gen(REPAIR)).read_text(encoding="utf-8")
    p.write_text(data + '{"type":"turn/start","seq":999,', encoding="utf-8")
    header, events, _ = dsh_source.read_session(str(p))
    assert header["id"] == REPAIR and events[-1]["seq"] != 999


def test_descendants_follow_parent_session():
    index = dsh_source.header_index(str(ROOT))
    assert set(index) == {MIGRATION, CHILD, REPAIR}
    kids = dsh_source.descendants(str(ROOT), MIGRATION, index)
    assert [h["id"] for h, _ in kids] == [CHILD]
    assert dsh_source.descendants(str(ROOT), REPAIR, index) == []


def test_zstd_frames_are_scanned_one_by_one():
    raw = (FIX / "zstd" / CHILD / "session.v4.jsonl.zstd").read_bytes()
    frames = dsh_source.zstd_frames(raw)
    assert len(frames) > 2 and frames[0][0] == 0 and frames[-1][1] == len(raw)
    # a torn tail keeps every complete frame
    assert dsh_source.zstd_frames(raw[:-3]) == frames[:-1]


@pytest.mark.skipif(not zstd_backend(), reason="no Zstandard decoder (zstandard / Python 3.14 / node)")
def test_zstd_log_decodes_to_the_same_events():
    h1, e1, _ = dsh_source.read_session(str(FIX / "zstd" / CHILD))
    h2, e2, _ = dsh_source.read_session(gen(CHILD))
    assert h1 == h2 and e1 == e2
    assert dsh_source.read_header(str(FIX / "zstd" / CHILD / "session.v4.jsonl.zstd"))["id"] == CHILD


def test_freeze_tree_layout_and_native_identity(tmp_path):
    manifest = dsh_source.freeze_tree(gen(MIGRATION), str(tmp_path / "pool"), str(ROOT))
    names = [s["name"] for s in manifest["sources"]]
    assert names == [MIGRATION + ".jsonl", MIGRATION + "/subagents/" + CHILD + ".jsonl"]
    rows = [json.loads(x) for x in (tmp_path / "pool" / names[0]).read_text(encoding="utf-8").splitlines()]
    assert rows[0]["type"] == "dsh_session" and rows[0]["session"]["id"] == MIGRATION
    assert all(r["format"] == "dsh-events/1" and r["timestamp"].endswith("+00:00") for r in rows)
    assert rows[1]["uuid"] == "%s#%s" % (MIGRATION, rows[1]["seq"])
    with pytest.raises(ValueError):
        dsh_source.freeze_tree(gen(MIGRATION), str(tmp_path / "pool"), str(ROOT))   # never overwrites


def test_fork_prefix_keeps_parent_as_owner():
    header = {"id": "child", "parentSession": "parent", "isSeeded": True, "cwd": "C:\\w"}
    events = [{"type": "user/message", "seq": 0, "time": 1, "data": {}},
              {"type": "session/end-seed", "seq": 1, "time": 2, "data": {"inherited": True}},
              {"type": "turn/start", "seq": 2, "time": 3, "data": {"turn": 1}}]
    rows = list(dsh_source.frozen_rows(header, events, "session.v4.jsonl"))
    assert [r.get("uuid") for r in rows[1:]] == ["parent#0", "child#1", "child#2"]


# --------------------------------------------------------------------------- report adapter

def test_registry_detects_dsh_and_lists_roots_only():
    assert adapters.detect(gen(MIGRATION)) is dsh
    assert adapters.detect(str(PROJECT / REPAIR)) is dsh
    rows = list(dsh.iter_sessions(str(ROOT)))
    assert {r.session_id for r in rows} == {MIGRATION, REPAIR}
    assert all(r.format == "dsh" and r.project == "toyapp" for r in rows)


def test_claude_transcript_is_not_taken(tmp_path):
    p = tmp_path / "1234abcd-0000-0000-0000-000000000000.jsonl"
    p.write_text('{"type":"user","sessionId":"x","message":{"role":"user","content":"hi"}}\n', encoding="utf-8")
    assert not dsh.is_session(str(p))


def test_migration_trace_with_subagent():
    t = dsh.extract(gen(MIGRATION))
    m, tot = t["meta"], t["totals"]
    assert (m["session_format"], m["session_id"], m["model"]) == ("dsh", MIGRATION, "deepseek-flash")
    assert (tot["tool_calls"], tot["agent_calls"], tot["subagent_transcripts"], tot["user_prompts"]) == (24, 1, 1, 1)
    assert (tot["main_output_tokens"], tot["subagent_output_tokens"]) == (13635, 39190)
    # billing = parent + child requests; uncached input stays separate from cache reads
    assert t["billing"] == {"deepseek-flash": {"req": 26, "inp": 41041, "cread": 707968, "cw5": 0, "cw1h": 0,
                                               "out": 52825}}
    assert len(t["context_timeline"]) == 15
    (agent,) = t["agents"]
    assert agent["agent_id"] == "subagent:" + CHILD and agent["tuid"] == DISPATCH_CALL
    assert (agent["desc"], agent["status"], agent["model"]) == ("Analyze Android screen", "completed", "deepseek-flash")
    assert agent["tool_counts"]["Read"] == 12 and agent["tool_counts"]["Write"] == 1
    dispatch = next(x for x in t["tools"] if x["name"] == "Agent")
    assert dispatch["tuid"] == DISPATCH_CALL and dispatch["agent_id"] == agent["agent_id"]
    assert [p["text"][:7] for p in t["prompts"]] == ["Migrate"]   # injected context is not a prompt
    lineage = {a["agent_id"]: a for a in t["lineage"]["agents"]}
    assert lineage["subagent:" + CHILD]["writes_spec"] == ["spec/ui-spec.md"]
    assert lineage["subagent:" + CHILD]["n_android"] == 4
    assert lineage["__main__:session"]["writes_ets"] == ["entry/src/main/ets/pages/Index.ets"]


def test_repair_trace_resolves_relative_paths():
    t = dsh.extract(gen(REPAIR))
    assert t["agents"] == [] and t["totals"]["tool_calls"] == 30
    writes = sorted({x["brief"] for x in t["tools"] if x["name"] in ("Write", "Edit")})
    assert writes == ["C:\\work\\toyapp\\entry\\src\\main\\ets\\entryability\\EntryAbility.ets",
                      "C:\\work\\toyapp\\entry\\src\\main\\ets\\pages\\Index.ets",
                      "C:\\work\\toyapp\\entry\\src\\main\\resources\\base\\profile\\main_pages.json"]
    main = t["lineage"]["agents"][0]
    assert main["writes_ets"] == ["entry/src/main/ets/entryability/EntryAbility.ets", "entry/src/main/ets/pages/Index.ets"]
    shells = [x for x in t["tools"] if x["name"] == "PowerShell"]
    assert shells and all(x["audit"]["kind"] == "shell" for x in shells)


def test_report_html_names_the_source():
    html = build_html(dsh.extract(gen(MIGRATION)), load_template())
    assert '"session_format": "dsh"' in html or '"session_format":"dsh"' in html
    assert "DeepSeek Harness" in html


def test_cli_resolves_bare_uuid_prefix(monkeypatch):
    from migloop import cli
    monkeypatch.setenv("DSH_SESSIONS_ROOT", str(ROOT))
    empty = str(FIX / "no-such-root")
    assert cli.resolve_target("638f5638", empty, empty, empty) == gen(MIGRATION)
    assert cli.resolve_target(str(PROJECT / REPAIR), empty, empty, empty) == gen(REPAIR)
