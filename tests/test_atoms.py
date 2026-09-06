"""两原子基座(atoms + atoms_collect)—— 行为契约。

版本文件:写者脊柱,每版带 (agent, agent 版本, via, diff, 内容)。
版本 agent:每个对外效应(写/删/派发/发消息)+1 版;读等输入归到它喂养的下一版。
收集层按 0723 普查修的洞逐条钉死:命令内 cd、失败调用不落账、脚本落盘/脚本读、
删除、派发边与收件箱、Grep 工具、旧版读标记。
"""

from __future__ import annotations

import json
import os
from typing import Any

from migloop import atoms, atoms_collect

CWD = "/proj"
SID = "abcdef12-0000-0000-0000-000000000000"
MAIN_ID = "__main__:abcdef12"


def _rec(ts: str, role: str, blocks: list[dict[str, Any]] | str, **extra: Any) -> dict[str, Any]:
    r: dict[str, Any] = {"timestamp": ts, "cwd": CWD, "type": role,
                         "message": {"role": role, "content": blocks}}
    r.update(extra)
    return r


def _use(tid: str, name: str, inp: dict[str, Any]) -> dict[str, Any]:
    return {"type": "tool_use", "id": tid, "name": name, "input": inp}


def _res(tid: str, text: str = "ok", is_error: bool = False) -> dict[str, Any]:
    return {"type": "tool_result", "tool_use_id": tid, "is_error": is_error,
            "content": [{"type": "text", "text": text}]}


def _call(ts: str, tid: str, name: str, inp: dict[str, Any], out: str = "ok",
          is_error: bool = False, **res_extra: Any) -> list[dict[str, Any]]:
    """一次工具调用 = assistant 的 tool_use + user 的 tool_result(结果时刻 +1s)。"""
    ts2 = ts[:-3] + f"{int(ts[-3:-1]) + 1:02d}Z"
    return [_rec(ts, "assistant", [_use(tid, name, inp)]),
            _rec(ts2, "user", [_res(tid, out, is_error)], **res_extra)]


def _read_call(ts: str, tid: str, path: str, content: str, start: int = 1) -> list[dict[str, Any]]:
    n = content.count("\n") + 1
    return _call(ts, tid, "Read", {"file_path": path}, "…",
                 toolUseResult={"type": "text", "file": {"filePath": path, "content": content,
                                                          "startLine": start, "numLines": n,
                                                          "totalLines": n}})


def _write_jsonl(path: str, records: list[dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def _ledger(tmp_path: Any, main: list[dict[str, Any]],
            subs: dict[str, list[dict[str, Any]]] | None = None) -> atoms.Ledger:
    main_path = str(tmp_path / f"{SID}.jsonl")
    _write_jsonl(main_path, main)
    for stem, recs in (subs or {}).items():
        _write_jsonl(str(tmp_path / SID / "subagents" / f"{stem}.jsonl"), recs)
    agents = atoms_collect.collect_cc(main_path, seq=[0])
    return atoms.build_ledger(agents)


def _story(ledger: atoms.Ledger, path: str) -> Any:
    return ledger.stories[path]


# ═══════════════ 收集层:路径、失败、脚本、删除 ═══════════════

def test_cd_in_command_resolves_relative_paths() -> None:
    evs = atoms_collect.shell_file_ops(
        "cd /proj/entry && cat pages/A.ets && grep -n x ../spec/s.md", CWD, {})
    got = {(e.op, e.path) for e in evs}
    assert ("read", "/proj/entry/pages/A.ets") in got
    assert ("read", "/proj/spec/s.md") in got
    # 记录级 cwd 只是兜底;命令内没 cd 时按它解析
    evs2 = atoms_collect.shell_file_ops("grep -n x entry/pages/A.ets", CWD, {})
    assert [(e.op, e.path) for e in evs2] == [("read", "/proj/entry/pages/A.ets")]
    # 动态 cd 之后的相对路径无法解析 —— 诚实丢弃,不猜
    assert atoms_collect.shell_file_ops("cd $OUT && cat a.ets", CWD, {}) == []


def test_garbled_tokens_never_become_paths() -> None:
    # 0723 实录里引号失衡让一整段命令被当成一个"路径"进了账本 —— 带空白/引号/分隔符的一律不要
    bad = 'echo "=== self-check: FWD-REF markers ==="; grep -nE "FWD-REF" entry/A.ets || echo none'
    got = {e.path for e in atoms_collect.shell_file_ops(bad, CWD, {})}
    assert got == {"/proj/entry/A.ets"}
    assert atoms_collect.shell_file_ops('cat "a b.ets"', CWD, {}) == []


def test_failed_write_or_edit_leaves_no_trace_in_ledger(tmp_path: Any) -> None:
    main = [
        *_call("2026-01-01T00:00:00Z", "t1", "Write", {"file_path": "/proj/a.md", "content": "x\n"},
               "<tool_use_error>File has not been read yet.</tool_use_error>", is_error=True),
        *_call("2026-01-01T00:00:10Z", "t2", "Write", {"file_path": "/proj/a.md", "content": "y\n"}),
        *_call("2026-01-01T00:00:20Z", "t3", "Edit", {"file_path": "/proj/a.md",
                                                      "old_string": "nope", "new_string": "z"},
               "<tool_use_error>String to replace not found in file.</tool_use_error>", is_error=True),
    ]
    st = _story(_ledger(tmp_path, main), "/proj/a.md")
    assert [v.content for v in st.versions] == ["y\n"]
    assert st.breaks == []                       # 失败的 Edit 不是 edit-miss 断点
    acts = atoms.build_ledger(atoms_collect.collect_cc(str(tmp_path / f"{SID}.jsonl"), seq=[0])) \
        .agents[MAIN_ID].actions
    assert [(a.kind, a.ok) for a in acts] == [("write", False), ("write", True), ("write", False)]
    assert [a.ver for a in acts] == [None, 1, None]   # 失败的效应不占版本号


def test_script_mediated_writes_and_reads(tmp_path: Any) -> None:
    heredoc = "cd /proj && python3 - <<'EOF'\nimport json\nd=json.load(open('spec/in.json'))\n" \
              "open('spec/out.md','w').write(str(d))\nEOF"
    main = [
        *_call("2026-01-01T00:00:00Z", "t1", "Bash", {"command": heredoc}),
        *_call("2026-01-01T00:00:10Z", "t2", "Bash",
               {"command": "python3 -c \"import json; print(json.load(open('spec/cfg.json')))\""}),
        *_call("2026-01-01T00:00:20Z", "t3", "Write",
               {"file_path": "/tmp/gen.py",
                "content": "from pathlib import Path\nPath('ui/page.md').write_text('hi')\n"}),
        *_call("2026-01-01T00:00:30Z", "t4", "Bash", {"command": "cd /proj && python3 /tmp/gen.py"}),
    ]
    led = _ledger(tmp_path, main)
    out = led.stories["/proj/spec/out.md"].versions[0]
    assert (out.source, out.via, out.content) == ("opaque", "script", None)
    assert [r.by for r in led.stories["/proj/spec/in.json"].reads] == [MAIN_ID]
    assert led.stories["/proj/spec/cfg.json"].reads[0].by == MAIN_ID
    page = led.stories["/proj/ui/page.md"].versions[0]
    assert (page.via, page.by) == ("script", MAIN_ID)
    # 三次有写能力的脚本调用都留了"目标可能不止字面量"的标记,给窗口归属用
    runs = [a for a in led.agents[MAIN_ID].actions if a.detail.get("write_capable")]
    assert len(runs) == 2                        # heredoc 写 + 跑 gen.py(python -c 只读)


def test_rm_records_a_delete_version(tmp_path: Any) -> None:
    main = [
        *_call("2026-01-01T00:00:00Z", "t1", "Write", {"file_path": "/proj/a.md", "content": "x\n"}),
        *_call("2026-01-01T00:00:10Z", "t2", "Bash", {"command": "cd /proj && rm -f a.md"}),
    ]
    st = _story(_ledger(tmp_path, main), "/proj/a.md")
    assert [v.diff_kind for v in st.versions] == ["creation", "delete"]
    assert st.versions[1].content == "" and "-x" in (st.versions[1].diff or "")


def test_grep_tool_content_mode_binds_line_runs(tmp_path: Any) -> None:
    main = _call("2026-01-01T00:00:00Z", "t1", "Grep",
                 {"pattern": "foo", "path": "/proj", "output_mode": "content"},
                 "entry/A.ets:12:foo\nentry/A.ets:13:bar\nentry/B.ets:4:x\n")
    led = _ledger(tmp_path, main)
    a = led.stories["/proj/entry/A.ets"].reads[0]
    assert (a.start, a.n) == (12, 2)
    assert led.stories["/proj/entry/B.ets"].reads[0].start == 4


# ═══════════════ agent 版本、派发边、收件箱 ═══════════════

def _sub(stem_prompt: str, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    head = _rec("2026-01-01T00:00:05Z", "user",
                f'<teammate-message teammate_id="team-lead" summary="s">\n{stem_prompt}',
                agentId="aconv-abc123", isSidechain=True)
    return [head, *records]


def test_dispatch_and_inbox_link_parent_and_child(tmp_path: Any) -> None:
    main = [
        *_call("2026-01-01T00:00:00Z", "t1", "Agent",
               {"name": "conv", "subagent_type": "worker", "description": "转换",
                "prompt": "做转换 X\n第二行"}),
        *_call("2026-01-01T00:00:40Z", "t2", "SendMessage",
               {"to": "conv", "message": "改优先级:先出 B"}),
    ]
    child = _sub("做转换 X\n第二行", [
        *_call("2026-01-01T00:00:20Z", "c1", "Write", {"file_path": "/proj/b.ets", "content": "b\n"}),
        _rec("2026-01-01T00:00:45Z", "user",
             '<teammate-message teammate_id="team-lead" summary="p">\n改优先级:先出 B',
             agentId="aconv-abc123"),
        _rec("2026-01-01T00:00:50Z", "assistant", [{"type": "text", "text": "完成了 B。"}]),
    ])
    led = _ledger(tmp_path, main, {"agent-aconv-abc123": child})
    m, c = led.agents[MAIN_ID], led.agents["agent-aconv-abc123"]
    assert [(a.kind, a.ver) for a in m.actions] == [("dispatch", 1), ("message", 2)]
    assert m.actions[0].detail["child"] == "agent-aconv-abc123"
    assert (c.parent, c.parent_ver, c.name) == (MAIN_ID, 1, "conv")
    assert c.prompt == "做转换 X\n第二行"
    inbox = [a for a in c.actions if a.kind == "inbox"]
    assert [a.detail["text"] for a in inbox] == ["做转换 X\n第二行", "改优先级:先出 B"]
    assert c.result == "完成了 B。"
    assert c.session == "abcdef12"


def test_plain_prompt_subagent_still_links_by_prompt(tmp_path: Any) -> None:
    # 没有 name、首条 user 文本不带 teammate-message 包装的子代理(id 只有 hash)
    main = _call("2026-01-01T00:00:00Z", "t1", "Agent",
                 {"subagent_type": "fixer", "description": "修构建", "prompt": "修掉编译错误 E1"})
    child = [_rec("2026-01-01T00:00:05Z", "user", "修掉编译错误 E1", agentId="a68daf720e780b4c"),
             *_call("2026-01-01T00:00:20Z", "c1", "Write", {"file_path": "/proj/x.ets", "content": "x\n"})]
    led = _ledger(tmp_path, main, {"agent-a68daf720e780b4c": child})
    c = led.agents["agent-a68daf720e780b4c"]
    assert (c.parent, c.parent_ver, c.prompt, c.description) == (MAIN_ID, 1, "修掉编译错误 E1", "修构建")
    assert atoms.file_atom(led, "x.ets", None)["versions"][0]["by_name"] == "修构建"  # type: ignore[index]


def test_agent_versions_and_cross_refs(tmp_path: Any) -> None:
    main = [
        *_read_call("2026-01-01T00:00:00Z", "t1", "/proj/a.md", "A"),
        *_call("2026-01-01T00:00:10Z", "t2", "Write", {"file_path": "/proj/b.ets", "content": "1\n"}),
        *_read_call("2026-01-01T00:00:20Z", "t3", "/proj/c.md", "C"),
        *_call("2026-01-01T00:00:30Z", "t4", "Edit",
               {"file_path": "/proj/b.ets", "old_string": "1", "new_string": "2"}),
        *_read_call("2026-01-01T00:00:40Z", "t5", "/proj/b.ets", "2"),     # 写后自查
    ]
    led = _ledger(tmp_path, main)
    acts = led.agents[MAIN_ID].actions
    assert [(a.kind, a.ver, a.at) for a in acts] == [
        ("read", None, 1), ("write", 1, 1), ("read", None, 2), ("write", 2, 2), ("read", None, 3)]
    assert [v.by_ver for v in led.stories["/proj/b.ets"].versions] == [1, 2]
    a1 = atoms.agent_atom(led, MAIN_ID, 1)
    assert [x["path"] for x in a1["reads"]] == ["/proj/a.md"]
    assert [(x["path"], x["v"]) for x in a1["writes"]] == [("/proj/b.ets", 1)]
    assert a1["n_versions"] == 2 and a1["v"] == 1
    full = atoms.agent_atom(led, MAIN_ID, None)
    assert [x["path"] for x in full["reads"]] == ["/proj/a.md", "/proj/c.md", "/proj/b.ets"]
    assert full["reads"][-1]["after_anchor"] is True and full["reads"][-1]["self_written"] is True
    f1 = atoms.file_atom(led, "/proj/b.ets", 1)
    assert [(v["v"], v["by"], v["by_ver"]) for v in f1["versions"]] == [(1, MAIN_ID, 1)]
    assert f1["content"] == "1\n"
    f2 = atoms.file_atom(led, "/proj/b.ets", None)
    assert f2["v"] == 2 and f2["content"] == "2\n" and "+2" in f2["versions"][1]["diff"]


def test_read_of_superseded_version_is_flagged_stale(tmp_path: Any) -> None:
    main = [
        *_call("2026-01-01T00:00:00Z", "t1", "Write", {"file_path": "/proj/s.md", "content": "v1\n"}),
        *_call("2026-01-01T00:00:30Z", "t2", "Write", {"file_path": "/proj/s.md", "content": "v2\n"}),
    ]
    child = _sub("干活", [
        *_read_call("2026-01-01T00:00:10Z", "c1", "/proj/s.md", "v1"),
        *_call("2026-01-01T00:00:50Z", "c2", "Write", {"file_path": "/proj/o.ets", "content": "o\n"}),
    ])
    led = _ledger(tmp_path, main, {"agent-aconv-abc123": child})
    rd = atoms.agent_atom(led, "agent-aconv-abc123", 1)["reads"][0]
    assert (rd["path"], rd["v"], rd["latest_v"], rd["stale"]) == ("/proj/s.md", 1, 2, True)


def test_file_atom_readers_and_optional_content(tmp_path: Any) -> None:
    main = [
        *_call("2026-01-01T00:00:00Z", "t1", "Write", {"file_path": "/proj/s.md", "content": "v1\n"}),
        *_call("2026-01-01T00:00:30Z", "t2", "Write", {"file_path": "/proj/s.md", "content": "v2\n"}),
    ]
    child = _sub("干活", [
        *_read_call("2026-01-01T00:00:10Z", "c1", "/proj/s.md", "v1"),
        *_call("2026-01-01T00:00:50Z", "c2", "Write", {"file_path": "/proj/o.ets", "content": "o\n"}),
    ])
    led = _ledger(tmp_path, main, {"agent-aconv-abc123": child})
    fa = atoms.file_atom(led, "s.md", None)
    assert fa is not None
    # 读者 = 下游:谁读了哪一版,喂了它自己的第几版
    assert [(r["by"], r["v"], r["at"]) for r in fa["readers"]] == [("agent-aconv-abc123", 1, 1)]
    assert fa["content"] == "v2\n"
    lite = atoms.file_atom(led, "s.md", 1, with_diff=False, with_content=False)
    assert lite is not None and lite["content"] is None and lite["content_known"] is True
    assert lite["versions"][0]["content_known"] is True


def test_ledger_index_lists_files_and_agents(tmp_path: Any) -> None:
    main = [
        *_call("2026-01-01T00:00:00Z", "t1", "Agent",
               {"name": "conv", "subagent_type": "worker", "description": "转换", "prompt": "干活"}),
        *_read_call("2026-01-01T00:00:05Z", "t2", "/android/app/Main.java", "class Main {}"),
    ]
    child = _sub("干活", [
        *_call("2026-01-01T00:00:20Z", "c1", "Write", {"file_path": "/proj/pages/P.ets", "content": "p\n"}),
        *_call("2026-01-01T00:00:30Z", "c2", "Write", {"file_path": "/proj/spec/p.md", "content": "s\n"}),
    ])
    led = _ledger(tmp_path, main, {"agent-aconv-abc123": child})
    idx = atoms.ledger_index(led)
    files = {f["path"]: f for f in idx["files"]}
    assert files["/proj/pages/P.ets"]["kind"] == "ets" and files["/proj/pages/P.ets"]["has_writer"]
    assert files["/proj/spec/p.md"]["kind"] == "spec"
    assert files["/android/app/Main.java"]["kind"] == "src" and not files["/android/app/Main.java"]["has_writer"]
    agents = {a["id"]: a for a in idx["agents"]}
    assert agents["agent-aconv-abc123"]["parent"] == MAIN_ID
    assert agents["agent-aconv-abc123"]["n_versions"] == 2
    assert agents[MAIN_ID]["n_versions"] == 1 and agents[MAIN_ID]["label"] == "主会话"


# ═══════════════ blame / 动作细节 / 置信 / 紧凑文本 / MCP ═══════════════

def test_blame_reports_line_owner_and_introducing_version(tmp_path: Any) -> None:
    main = _call("2026-01-01T00:00:00Z", "t1", "Write", {"file_path": "/proj/a.ets", "content": "l1\nl2\nl3\n"})
    child = _sub("改一行", _call("2026-01-01T00:00:20Z", "c1", "Edit",
                                {"file_path": "/proj/a.ets", "old_string": "l2", "new_string": "L2"}))
    led = _ledger(tmp_path, main, {"agent-aconv-abc123": child})
    bl = atoms.blame(led, "a.ets", None)
    assert bl is not None and bl["v"] == 2 and bl["known"] is True
    assert [(x["ln"], x["owner"], x["since_v"]) for x in bl["lines"]] == [
        (1, MAIN_ID, 1), (2, "agent-aconv-abc123", 2), (3, MAIN_ID, 1)]
    assert [(s["owner"], s["n"]) for s in bl["summary"]] == [(MAIN_ID, 2), ("agent-aconv-abc123", 1)]
    win = atoms.blame(led, "a.ets", 2, start=2, n=1)
    assert win is not None and [x["ln"] for x in win["lines"]] == [2]
    assert atoms.blame(led, "a.ets", 1)["lines"][1]["owner"] == MAIN_ID  # type: ignore[index]


def test_blame_is_honest_when_version_content_unknown(tmp_path: Any) -> None:
    main = [
        *_call("2026-01-01T00:00:00Z", "t1", "Write", {"file_path": "/proj/a.ets", "content": "l1\n"}),
        *_call("2026-01-01T00:00:10Z", "t2", "Bash", {"command": "cd /proj && sed -i 's/l1/x/' a.ets"}),
    ]
    bl = atoms.blame(_ledger(tmp_path, main), "a.ets", None)
    assert bl is not None and bl["v"] == 2 and bl["known"] is False and bl["lines"] == []


def test_action_detail_carries_command_summary(tmp_path: Any) -> None:
    main = [
        *_call("2026-01-01T00:00:00Z", "t1", "Bash", {"command": "cd /proj && grep -n foo a.ets"}),
        *_call("2026-01-01T00:00:10Z", "t2", "Grep", {"pattern": "foo", "path": "/proj"}, "a.ets\n"),
    ]
    acts = _ledger(tmp_path, main).agents[MAIN_ID].actions
    assert acts[0].detail["cmd"].startswith("cd /proj && grep -n foo")
    assert acts[1].detail["pattern"] == "foo" and acts[1].detail["mode"] == "files_with_matches"


def test_agent_reads_carry_certainty(tmp_path: Any) -> None:
    main = [
        *_call("2026-01-01T00:00:00Z", "t1", "Bash",
               {"command": "cd /proj && python3 - <<'EOF'\nopen('x.md','w').write('a')\nEOF"}),
        *_call("2026-01-01T00:00:10Z", "t2", "Bash", {"command": "cd /proj && grep -n foo x.md"}),
    ]
    ag = atoms.agent_atom(_ledger(tmp_path, main), MAIN_ID, None)
    assert ag is not None
    rd = ag["reads"][0]
    assert (rd["path"], rd["v"], rd["certain"]) == ("/proj/x.md", 1, False)   # 盲写后就近绑定


def test_compact_text_renderers(tmp_path: Any) -> None:
    from migloop import atoms_text
    main = [
        *_read_call("2026-01-01T00:00:00Z", "t1", "/proj/spec/a.md", "A"),
        *_call("2026-01-01T00:00:10Z", "t2", "Write", {"file_path": "/proj/b.ets", "content": "1\n"}),
    ]
    led = _ledger(tmp_path, main)
    ft = atoms_text.render_file(led, "b.ets", None, root="/proj")
    assert "b.ets" in ft and "v1" in ft and "主会话" in ft and "/proj/" not in ft.splitlines()[0]
    at = atoms_text.render_agent(led, MAIN_ID, None, root="/proj")
    assert "写 b.ets@v1" in at and "spec/a.md@v1" in at
    bt = atoms_text.render_blame(led, "b.ets", None, root="/proj")
    assert "主会话" in bt and "v1" in bt
    it = atoms_text.render_index(led, kind="ets", query=None, root="/proj")
    assert "b.ets" in it and "a.md" not in it


def test_mcp_server_exposes_atom_tools() -> None:
    import asyncio

    import pytest
    pytest.importorskip("mcp")
    from migloop import mcp_server
    srv = mcp_server.build_server()
    names = {t.name for t in asyncio.run(srv.list_tools())}
    assert {"guide", "sessions", "index", "file", "agent", "blame", "diff"} <= names


# ═══════════════ 原始记录可展开 / stdout 对账 ═══════════════

def test_every_action_can_expand_to_its_raw_io(tmp_path: Any) -> None:
    main = [
        *_call("2026-01-01T00:00:00Z", "t1", "Bash",
               {"command": "cd /proj && grep -n appName spec/r.md | head -40"},
               "152:- appName 在这里\n615:- **App 显示名**: appName = x(或对应 string.json + app.json5 引用)\n"),
        *_call("2026-01-01T00:00:10Z", "t2", "Write", {"file_path": "/proj/b.ets", "content": "1\n"}),
    ]
    led = _ledger(tmp_path, main)
    ag = atoms.agent_atom(led, MAIN_ID, None)
    assert ag is not None
    seqs = [a["seq"] for a in ag["actions"]]
    assert len(seqs) == 2 and all(isinstance(s, int) for s in seqs)
    raw = atoms.action_raw(led, MAIN_ID, seqs[0])
    assert raw is not None
    assert raw["tool"] == "Bash" and raw["input"]["command"].startswith("cd /proj && grep")
    assert "615:- **App 显示名**" in raw["output"] and raw["ok"] is True
    assert atoms.action_raw(led, MAIN_ID, 999999) is None


def test_grep_output_lines_become_seen_evidence(tmp_path: Any) -> None:
    main = _call("2026-01-01T00:00:00Z", "t1", "Bash",
                 {"command": "cd /proj && grep -n appName spec/r.md | head -40"},
                 "152:- appName 在这里\n615:- App 显示名 appName\n")
    led = _ledger(tmp_path, main)
    rd = led.stories["/proj/spec/r.md"].reads[0]
    assert rd.seen == ((152, "- appName 在这里"), (615, "- App 显示名 appName"))
    ag = atoms.agent_atom(led, MAIN_ID, None)
    assert ag is not None and ag["reads"][0]["seen"] == [[152, "- appName 在这里"], [615, "- App 显示名 appName"]]
    fa = atoms.file_atom(led, "r.md", None)
    assert fa is not None and fa["readers"][0]["seen"][1][0] == 615


def test_head_prefix_output_is_partial_snapshot(tmp_path: Any) -> None:
    main = _call("2026-01-01T00:00:00Z", "t1", "Bash", {"command": "cd /proj && head -3 a.md"},
                 "l1\nl2\nl3\n")
    led = _ledger(tmp_path, main)
    rd = led.stories["/proj/a.md"].reads[0]
    assert (rd.start, rd.n) == (1, 3)
    assert rd.seen == ((1, "l1"), (2, "l2"), (3, "l3"))


def test_render_agent_marks_action_seq_and_seen_lines(tmp_path: Any) -> None:
    from migloop import atoms_text
    main = _call("2026-01-01T00:00:00Z", "t1", "Bash",
                 {"command": "cd /proj && grep -n appName spec/r.md"}, "615:- App 显示名 appName\n")
    led = _ledger(tmp_path, main)
    txt = atoms_text.render_agent(led, MAIN_ID, None, root="/proj")
    assert "#1" in txt and "615:" in txt and "App 显示名" in txt
    seq = atoms.agent_atom(led, MAIN_ID, None)["actions"][0]["seq"]  # type: ignore[index]
    raw = atoms_text.render_action(led, MAIN_ID, seq)
    assert "grep -n appName" in raw and "615:- App 显示名" in raw


def test_mcp_server_exposes_action_tool() -> None:
    import asyncio

    import pytest
    pytest.importorskip("mcp")
    from migloop import mcp_server
    names = {t.name for t in asyncio.run(mcp_server.build_server().list_tools())}
    assert "action" in names


def test_file_atom_resolves_basename_hint_and_lists_names(tmp_path: Any) -> None:
    main = _call("2026-01-01T00:00:00Z", "t1", "Agent",
                 {"name": "conv", "subagent_type": "worker", "description": "转换页", "prompt": "干活"})
    child = _sub("干活", _call("2026-01-01T00:00:20Z", "c1", "Write",
                              {"file_path": "/proj/pages/P.ets", "content": "p\n"}))
    led = _ledger(tmp_path, main, {"agent-aconv-abc123": child})
    fa = atoms.file_atom(led, "P.ets", None)
    assert fa["path"] == "/proj/pages/P.ets"
    assert fa["versions"][0]["by_name"] == "conv"
    assert atoms.file_atom(led, "nope.ets", None) is None
