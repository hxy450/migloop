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

from migloop import atoms, atoms_collect, atoms_text, filestory

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
            subs: dict[str, list[dict[str, Any]]] | None = None,
            stage_intervals: list[dict[str, Any]] | None = None) -> atoms.Ledger:
    main_path = str(tmp_path / f"{SID}.jsonl")
    _write_jsonl(main_path, main)
    for stem, recs in (subs or {}).items():
        _write_jsonl(str(tmp_path / SID / "subagents" / f"{stem}.jsonl"), recs)
    agents = atoms_collect.collect_cc(main_path, seq=[0], stage_intervals=stage_intervals)
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


def test_powershell_variable_prefixed_paths_resolve() -> None:
    # codex 在 Windows 上的常见写法:先 $p='…' 再 Get-Content "$p\x.kt";变量在同一条命令里就有字面量,可代换
    cmd = "$p='C:\\src\\app'; Get-Content \"$p\\a.kt\"; Get-Content \"$p\\b.xml\" | Select-Object -First 5"
    got = sorted(e.path for e in atoms_collect.shell_file_ops(cmd, "C:/w", {}))
    assert got == ["C:/src/app/a.kt", "C:/src/app/b.xml"]
    # 命令里没赋值的变量仍然放弃,不猜
    assert atoms_collect.shell_file_ops("Get-Content \"$HOME\\x.kt\"", "C:/w", {}) == []


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


def test_script_literal_tendency_fallback_only_for_small_scripts(tmp_path: Any) -> None:
    """0723 vv-static-B 的 gen_static.py:只写脚本里一张 24 条 .ets 路径的数据表全被当成写目标,
    凭空造出 19 条假返修链(34 条里的 56%)。全文倾向兜底只对字面量 ≤ 3 的小脚本生效;
    多了就放弃这些字面量并在动作上记「脚本字面量方向不明」—— 宁可漏,不许静默。"""
    small = "from pathlib import Path\nOUT = 'ui/page.md'\nPath(OUT).write_text('hi')\n"
    # 紧跟的字段 'wired' 以 w 开头:旧的 open(p,'w') 判据只看引号后一个字母,把它当成了写模式
    table = ("import json\nR = [\n"
             + "".join(f"  ('P{i}', 'entry/src/main/ets/pages/P{i}.ets', 'wired'),\n" for i in range(6))
             + "]\njson.dump(R, open('spec/static.json', 'w'))\n")
    main = [
        *_call("2026-01-01T00:00:00Z", "t1", "Write", {"file_path": "/tmp/small.py", "content": small}),
        *_call("2026-01-01T00:00:10Z", "t2", "Bash", {"command": "cd /proj && python3 /tmp/small.py"}),
        *_call("2026-01-01T00:00:20Z", "t3", "Write", {"file_path": "/tmp/gen_static.py", "content": table}),
        *_call("2026-01-01T00:00:30Z", "t4", "Bash", {"command": "cd /proj && python3 /tmp/gen_static.py"}),
    ]
    led = _ledger(tmp_path, main)
    assert led.stories["/proj/ui/page.md"].versions[0].via == "script"      # 小脚本:倾向兜底照旧
    assert "/proj/spec/static.json" in led.stories                            # 显式 open(...,'w') 照旧
    ets = {p: st for p, st in led.stories.items() if p.endswith(".ets")}
    assert ets and not any(st.versions for st in ets.values())               # 数据表里的路径不再是写…
    assert sum(len(st.touches) for st in ets.values()) == 6                   # …只记「碰过、方向不明」
    runs = [a for a in led.agents[MAIN_ID].actions if a.tool == "Bash"]
    assert runs[0].detail.get("unresolved") is None
    assert runs[1].detail.get("unresolved") == "脚本字面量方向不明"


def test_read_without_tool_use_result_falls_back_to_numbered_output(tmp_path: Any) -> None:
    """服务端切片与 Workflow 子代理的转录不带 toolUseResult 边车:Read 只有结果正文 "     N\\t内容"。
    DiceRoller 0903 生成方读 MainActivity.kt / activity_main.xml 的两条 Read 因此在账本里消失,盲评里
    原始转录组据此指出我们"无法确认是否读过"是错的。从行号前缀还原路径、行段与全读标记。"""
    main = [
        *_call("2026-01-01T00:00:00Z", "r1", "Read", {"file_path": "/proj/app/src/MainActivity.kt"},
               "     1\tclass MainActivity {\n     2\t  fun roll() = (1..6).random()\n     3\t}\n"),
        *_call("2026-01-01T00:00:10Z", "r2", "Read", {"file_path": "/proj/app/res/layout/activity_main.xml",
                                                      "offset": 40, "limit": 2},
               "    40\t<Button\n    41\t    android:text=\"@string/roll\" />\n"),
        *_call("2026-01-01T00:00:20Z", "t1", "Write", {"file_path": "/proj/entry/A.ets", "content": "a\n"}),
    ]
    led = _ledger(tmp_path, main)
    reads = [(ref.path, ref.ev.start, ref.ev.n, ref.ev.full) for act in led.agents[MAIN_ID].actions
             for ref in act.files if ref.op == "read"]
    assert reads == [("/proj/app/src/MainActivity.kt", 1, 3, True),
                     ("/proj/app/res/layout/activity_main.xml", 40, 2, False)]
    kt = led.stories["/proj/app/src/MainActivity.kt"]
    assert kt.reads and kt.reads[0].by == MAIN_ID                      # 外部输入被读到,进树的叶子
    assert atoms.agent_atom(led, MAIN_ID)["reads"][0]["path"].endswith("MainActivity.kt")


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


def test_dispatch_links_by_tool_result_agent_id_when_prompts_share_a_head(tmp_path: Any) -> None:
    """DiceRoller ECAT 主会话一次派 6 个修复子代理,派发词开头 120 字一模一样(仓库根目录 + 语言 + 循环轮次),
    按派发词开头对齐就按目录顺序乱配:账本把 fix-identity 的名片挂到了 fix-errobserver 的转录上,六个里只有
    第一个碰巧对上(调查 agent 在报告里点了出来)。Task 结果边车 toolUseResult.agentId 是实锤的派发边,有它就用它;
    没有边车时先比派发词全文,再退到开头。"""
    common = ("仓库根目录（工作目录即此处）：/private/tmp/claude-502/-Users-fengyi-Workspace-migbot-set-hmigbot-plus/"
              "12b07daf-a671-4616-96a1-c214864ee609/scratchpad/dice-hmos\n"
              "语言：全部输出用中文。ECAT 循环 iteration 0 修复任务。")
    assert len(common) > 120
    main = [
        *_call("2026-01-01T00:00:00Z", "t1", "Agent",
               {"name": "fix-identity", "subagent_type": "worker", "description": "Fix app.json5 identity",
                "prompt": common + "\n## 目标文件 AppScope/app.json5"},
               toolUseResult={"agentId": "azz999", "status": "completed"}),
        *_call("2026-01-01T00:00:10Z", "t2", "Agent",
               {"name": "fix-errobserver", "subagent_type": "worker", "description": "Add global error observer",
                "prompt": common + "\n## 目标文件 EntryAbility.ets"},
               toolUseResult={"agentId": "aaa111", "status": "completed"}),
        *_call("2026-01-01T00:00:12Z", "t3", "Agent",                    # 没有边车:靠派发词全文对齐
               {"name": "gate-build", "subagent_type": "worker", "description": "Run compile gate",
                "prompt": common + "\n## 编译门"}),
    ]
    ident = [_rec("2026-01-01T00:00:05Z", "user", common + "\n## 目标文件 AppScope/app.json5", agentId="azz999"),
             *_call("2026-01-01T00:00:20Z", "c1", "Write", {"file_path": "/proj/AppScope/app.json5", "content": "{}\n"})]
    errobs = [_rec("2026-01-01T00:00:15Z", "user", common + "\n## 目标文件 EntryAbility.ets", agentId="aaa111"),
              *_call("2026-01-01T00:00:30Z", "c2", "Write", {"file_path": "/proj/E.ets", "content": "e\n"})]
    gate = [_rec("2026-01-01T00:00:16Z", "user", common + "\n## 编译门", agentId="abb222"),
            *_call("2026-01-01T00:00:31Z", "c3", "Bash", {"command": "cd /proj && hvigorw assembleHap"})]
    led = _ledger(tmp_path, main, {"agent-azz999": ident, "agent-aaa111": errobs, "agent-abb222": gate})
    a, b, g = led.agents["agent-azz999"], led.agents["agent-aaa111"], led.agents["agent-abb222"]
    assert (a.name, a.description, a.parent_ver) == ("fix-identity", "Fix app.json5 identity", 1)
    assert (b.name, b.description, b.parent_ver) == ("fix-errobserver", "Add global error observer", 2)
    assert (g.name, g.description, g.parent_ver) == ("gate-build", "Run compile gate", 3)
    assert [act.detail["child"] for act in led.agents[MAIN_ID].actions if act.kind == "dispatch"] \
        == ["agent-azz999", "agent-aaa111", "agent-abb222"]


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


# ═══════════════ codex 收集器:与 CC 同一套语义 ═══════════════

CROOT = "01a0470f-6454-7b33-b561-e5a05e2ba543"
CCHILD = "01a04716-3250-7423-86c9-63ff37f01708"


def _crec(ts: str, rtype: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {"type": rtype, "timestamp": ts, "payload": payload}


def _cmsg(ts: str, mid: str, role: str, text: str) -> dict[str, Any]:
    kind = "output_text" if role == "assistant" else "input_text"
    return _crec(ts, "response_item", {"type": "message", "id": mid, "role": role,
                                       "content": [{"type": kind, "text": text}]})


def _cexec(ts: str, cid: str, js: str, out_text: str, ok: bool = True) -> list[dict[str, Any]]:
    head = ("Script completed" if ok else "Script failed") + "\nWall time 0.1 seconds\nOutput:\n"
    body = json.dumps({"chunk_id": "x", "exit_code": 0 if ok else 1, "output": out_text}) if ok else out_text
    return [_crec(ts, "response_item", {"type": "custom_tool_call", "call_id": cid, "name": "exec",
                                         "status": "completed", "input": js}),
            _crec(ts[:-3] + "1Z", "response_item", {"type": "custom_tool_call_output", "call_id": cid,
                                                    "output": [{"type": "input_text", "text": head},
                                                               {"type": "input_text", "text": body}]})]


def _cfn(ts: str, cid: str, name: str, args: dict[str, Any], out: dict[str, Any]) -> list[dict[str, Any]]:
    return [_crec(ts, "response_item", {"type": "function_call", "call_id": cid, "name": name,
                                         "namespace": "collaboration", "arguments": json.dumps(args)}),
            _crec(ts[:-3] + "1Z", "response_item", {"type": "function_call_output", "call_id": cid,
                                                    "output": json.dumps(out)})]


def _codex_tree(tmp_path: Any) -> str:
    d = tmp_path / "sessions"
    d.mkdir()
    grep_js = ('const r = await tools.exec_command({"cmd":"cd /proj && grep -n foo spec/a.md",'
               '"workdir":"/proj"});\ntext(JSON.stringify(r));')
    patch_js = ('const p = "*** Begin Patch\\n*** Add File: b.ets\\n+line1\\n*** End Patch";\n'
                'await tools.apply_patch(p);')
    bad_js = ('const p = "*** Begin Patch\\n*** Update File: b.ets\\n@@\\n-nope\\n+x\\n*** End Patch";\n'
              'await tools.apply_patch(p);')
    root = [
        _crec("2026-01-01T00:00:00Z", "session_meta",
              {"id": CROOT, "session_id": CROOT, "cwd": "/proj", "source": "cli"}),
        _cmsg("2026-01-01T00:00:01Z", "msg_u1", "user", "迁移 dice"),
        *_cexec("2026-01-01T00:00:10Z", "c1", grep_js, "3:foo bar\n"),
        *_cexec("2026-01-01T00:00:20Z", "c2", patch_js, ""),
        *_cfn("2026-01-01T00:00:30Z", "c3", "spawn_agent",
              {"task_name": "worker1", "agent_type": "worker", "fork_turns": "all", "message": "gAAAA-encrypted"},
              {"task_name": "/root/worker1"}),
        *_cfn("2026-01-01T00:00:40Z", "c4", "send_message",
              {"agent": "/root/worker1", "message": "先做 B"}, {"ok": True}),
        *_cexec("2026-01-01T00:00:50Z", "c9", bad_js, "Script error:\napply_patch verification failed", ok=False),
        _cmsg("2026-01-01T00:01:00Z", "msg_a1", "assistant", "完成"),
    ]
    child = [
        _crec("2026-01-01T00:00:31Z", "session_meta", {"id": CCHILD, "session_id": CROOT, "cwd": "/proj",
              "source": {"subagent": {"thread_spawn": {"parent_thread_id": CROOT, "agent_path": "/root/worker1",
                                                        "agent_nickname": "Wk", "agent_role": "worker", "depth": 1}}}}),
        _cmsg("2026-01-01T00:00:01Z", "msg_u1", "user", "迁移 dice"),            # fork_turns=all 复制来的父消息
        _cmsg("2026-01-01T00:00:32Z", "msg_u2", "user", "任务:实现 B"),
        *_cexec("2026-01-01T00:00:35Z", "c5",
                'const p = "*** Begin Patch\\n*** Add File: c.ets\\n+c\\n*** End Patch";\n'
                'await tools.apply_patch(p);', ""),
        _cmsg("2026-01-01T00:00:36Z", "msg_a2", "assistant", "B 完成"),
    ]
    _write_jsonl(str(d / f"rollout-{CROOT}.jsonl"), root)
    _write_jsonl(str(d / f"rollout-{CCHILD}.jsonl"), child)
    return str(d / f"rollout-{CROOT}.jsonl")


def test_codex_collector_matches_cc_semantics(tmp_path: Any) -> None:
    root = _codex_tree(tmp_path)
    agents = atoms_collect.collect_codex(root, seq=[0], sessions_root=str(tmp_path / "sessions"))
    led = atoms.build_ledger(agents)
    main_id, child_id = "__main__:" + CROOT[:8], "agent-" + CCHILD[:12]
    assert set(led.agents) == {main_id, child_id}
    m = led.agents[main_id]
    assert [(a.kind, a.ver, a.ok) for a in m.actions if a.kind != "inbox"] == [
        ("read", None, True), ("write", 1, True), ("dispatch", 2, True), ("message", 3, True), ("write", None, False)]
    assert m.actions[1].detail["cmd"].startswith("cd /proj && grep")
    rd = led.stories["/proj/spec/a.md"].reads[0]
    assert rd.seen == ((3, "foo bar"),) and rd.by == main_id                      # stdout 对账穿过 exec 外壳
    assert led.stories["/proj/b.ets"].versions[0].content == "line1\n"             # apply_patch Add File
    assert len(led.stories["/proj/b.ets"].versions) == 1                           # Script failed 的 patch 不落账
    c = led.agents[child_id]
    assert (c.parent, c.parent_ver, c.name, c.kind) == (main_id, 2, "Wk", "worker")
    assert c.prompt == "任务:实现 B" and c.result == "B 完成"
    assert [a.detail["text"] for a in c.actions if a.kind == "inbox"] == ["任务:实现 B"]   # fork 复制的父消息不算收件
    disp = next(a for a in m.actions if a.kind == "dispatch")
    assert disp.detail["child"] == child_id and disp.detail["name"] == "worker1"
    raw = atoms.action_raw(led, main_id, m.actions[1].seq)
    assert raw is not None and "exec_command" in json.dumps(raw["input"]) and "foo bar" in raw["output"]
    assert led.stories["/proj/c.ets"].versions[0].by == child_id


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


# ═══════════════ 阶段进账本:主会话 execute 之后阶段的写算修复方 ═══════════════

def _staged(recs: list[dict[str, Any]], stage: str) -> list[dict[str, Any]]:
    """harness 给每条记录盖的归属戳(attributionSkill,可带 'x:' 前缀,取冒号后)。"""
    return [dict(r, attributionSkill=f"x:{stage}") for r in recs]


def _staged_session(tmp_path: Any) -> atoms.Ledger:
    """主会话:无戳写 A → execute 派发子 agent(子写 A)→ visual-verify 亲手改 A。"""
    main = [
        *_call("2026-01-01T00:00:00Z", "t0", "Write", {"file_path": "/proj/entry/A.ets", "content": "a\n"}),
        *_staged(_call("2026-01-01T00:00:10Z", "t1", "Agent",
                       {"name": "conv", "subagent_type": "worker", "description": "转换 A", "prompt": "转 A"}),
                 "a2h-execute"),
        *_staged(_call("2026-01-01T00:01:00Z", "t2", "Edit",
                       {"file_path": "/proj/entry/A.ets", "old_string": "b", "new_string": "c"}),
                 "arkts-visual-verify"),
    ]
    child = _sub("转 A", [*_call("2026-01-01T00:00:30Z", "c1", "Write",
                                   {"file_path": "/proj/entry/A.ets", "content": "b\n"})])
    return _ledger(tmp_path, main, {"agent-aconv-abc123": child})


def test_stage_from_attribution_skill_and_inherited_by_child(tmp_path: Any) -> None:
    led = _staged_session(tmp_path)
    m, c = led.agents[MAIN_ID], led.agents["agent-aconv-abc123"]
    assert [a.stage for a in m.actions] == [None, "a2h-execute", "arkts-visual-verify"]
    assert m.stage is None                                  # 主会话横跨全程,没有单一阶段
    assert c.stage == "a2h-execute"                          # 子 agent 记录没有戳:继承派发时的阶段
    assert [a.stage for a in c.actions if a.kind == "write"] == ["a2h-execute"]
    st = led.stories["/proj/entry/A.ets"]
    assert [(v.by, v.stage) for v in st.versions] == [
        (MAIN_ID, None), ("agent-aconv-abc123", "a2h-execute"), (MAIN_ID, "arkts-visual-verify")]
    assert atoms.agent_atom(led, MAIN_ID)["actions"][2]["stage"] == "arkts-visual-verify"  # type: ignore[index]
    idx = {a["id"]: a for a in atoms.ledger_index(led)["agents"]}
    assert idx["agent-aconv-abc123"]["stage"] == "a2h-execute"


def test_collect_cc_falls_back_to_run_stage_intervals(tmp_path: Any) -> None:
    """没有归属戳的 CC 会话(ECAT 对抗循环、reviewer、loop engine 续接的 worker 都是 Driver 直接起的,
    记录上没有 attributionSkill)按 run 级阶段区间(stage-marks)以时间落阶段;有戳的记录戳优先。
    DiceRoller 0903:ECAT fixer 会话改了 .ets 却因阶段 None 被当成生成侧,一条 ECAT 返修链都没有。"""
    # 管线 mark 打在阶段结束:plan 在 00:00:00 结束,execute 在 00:01:00 结束,verify 在 00:02:00 结束;
    # ecat-refine 是起始 mark
    marks = [["2026-01-01T00:00:00Z", "a2h-plan"], ["2026-01-01T00:01:00Z", "a2h-execute"],
             ["2026-01-01T00:02:00Z", "a2h-verify"], ["2026-01-01T00:03:00Z", "ecat-refine"]]
    intervals = atoms_collect.stage_intervals_from_marks(marks)
    assert [(s["stage"], s["end_ts"]) for s in intervals] == [
        ("a2h-plan", "2026-01-01T00:00:00.000000"), ("a2h-execute", "2026-01-01T00:01:00.000000"),
        ("a2h-verify", "2026-01-01T00:02:00.000000"), ("ecat-refine", None)]
    main = [
        *_call("2026-01-01T00:00:30Z", "t0", "Write", {"file_path": "/proj/entry/A.ets", "content": "a\nb\n"}),
        # 戳是 skill 粒度(execute 期间派的 visual-verify 子代理),区间是 stage 粒度:有戳的记录戳优先,
        # 子代理没戳时继承派发那一笔的戳,不按时间落(否则会被误成 a2h-execute)
        *_staged(_call("2026-01-01T00:00:40Z", "t9", "Agent",
                       {"name": "vv", "subagent_type": "worker", "description": "视觉核对", "prompt": "核"}),
                 "arkts-visual-verify"),
        *_call("2026-01-01T00:01:30Z", "t1", "Edit",
               {"file_path": "/proj/entry/A.ets", "old_string": "b", "new_string": "c"}),
    ]
    child = _sub("核", [*_call("2026-01-01T00:00:45Z", "c1", "Write",
                                {"file_path": "/proj/entry/C.ets", "content": "c\n"})])
    led = _ledger(tmp_path, main, {"agent-avv-abc123": child}, stage_intervals=intervals)
    # 无戳记录按时间落;有戳的记录戳优先,且戳沿用到后面的无戳记录(原规则不变)
    assert [a.stage for a in led.agents[MAIN_ID].actions] == ["a2h-execute", "arkts-visual-verify",
                                                               "arkts-visual-verify"]
    assert led.agents["agent-avv-abc123"].stage == "arkts-visual-verify"     # 继承派发戳,不是区间的 execute
    assert [v.stage for v in led.stories["/proj/entry/C.ets"].versions] == ["arkts-visual-verify"]
    # 不给区间照旧:无戳 = 无阶段
    led0 = _ledger(tmp_path, main, {"agent-avv-abc123": child})
    assert [a.stage for a in led0.agents[MAIN_ID].actions] == [None, "arkts-visual-verify", "arkts-visual-verify"]
    # 纯无戳会话(reviewer / ECAT 那种):全靠区间;execute 结束后落在 verify 段的写是修复
    ecat = [
        *_call("2026-01-01T00:00:30Z", "e0", "Write", {"file_path": "/proj/entry/A.ets", "content": "a\nb\n"}),
        *_call("2026-01-01T00:01:30Z", "e1", "Edit",
               {"file_path": "/proj/entry/A.ets", "old_string": "b", "new_string": "c"}),
        *_call("2026-01-01T00:03:30Z", "e2", "Edit",
               {"file_path": "/proj/entry/A.ets", "old_string": "c", "new_string": "d"}),
    ]
    led2 = _ledger(tmp_path, ecat, stage_intervals=intervals)
    assert [v.stage for v in led2.stories["/proj/entry/A.ets"].versions] == ["a2h-execute", "a2h-verify", "ecat-refine"]
    chains = filestory.build_fix_chains(led2.stories, {}, {})
    assert [(c["file"], c["fixer"]["stage"], c["fix_versions"]) for c in chains] == [("A.ets", "a2h-verify", [2, 3])]


def test_fix_boundary_is_end_of_execute_and_time_rule_beats_stage_names(tmp_path: Any) -> None:
    """用户口径(2026-09-04):execute 阶段结束之后的都是修复。有 run 级 stage-marks 时按时间判:
    execute 期间派的 visual-verify 子代理是生成侧的收尾,execute 结束后哪怕阶段是 None 也是修复;
    没有 marks 才退回按阶段名排序。marks 兼容 Go 运行时的 [{stage, ts}] 与导出包的 [[ts, stage]]。"""
    # 管线 mark = 阶段结束时刻(Go 运行时格式 {stage, ts}):plan 00:00:00 结束、execute 00:01:00 结束、
    # verify 00:02:00 结束;ecat-refine 是起始 mark。时刻带 +00:00 也能与记录的 Z 时刻比
    marks = [{"stage": "a2h-plan", "ts": "2026-01-01T00:00:00+00:00"},
             {"stage": "a2h-execute", "ts": "2026-01-01T00:01:00+00:00"},
             {"stage": "a2h-verify", "ts": "2026-01-01T00:02:00+00:00"},
             {"stage": "ecat-refine", "ts": "2026-01-01T00:03:00+00:00"}]
    intervals = atoms_collect.stage_intervals_from_marks(marks)
    assert [s["stage"] for s in intervals] == ["a2h-plan", "a2h-execute", "a2h-verify", "ecat-refine"]
    assert atoms_collect.fix_boundary(intervals) == "2026-01-01T00:01:00.000000"
    assert atoms_collect.fix_boundary(intervals[:1]) is None            # 还没有 execute 的结束 mark:没有修复
    assert atoms_collect.fix_boundary([]) is None
    main = [
        *_staged(_call("2026-01-01T00:00:20Z", "t0", "Write", {"file_path": "/proj/entry/A.ets", "content": "a\nb\n"}),
                 "a2h-execute"),
        *_staged(_call("2026-01-01T00:00:40Z", "t1", "Edit",                  # execute 结束(00:01:00)前的 visual-verify
                       {"file_path": "/proj/entry/A.ets", "old_string": "b", "new_string": "c"}),
                 "arkts-visual-verify"),
        *_call("2026-01-01T00:01:30Z", "t2", "Edit",                           # execute 结束后,无戳
               {"file_path": "/proj/entry/A.ets", "old_string": "c", "new_string": "d"}),
    ]
    led = _ledger(tmp_path, main)
    assert [v.stage for v in led.stories["/proj/entry/A.ets"].versions] == \
        ["a2h-execute", "arkts-visual-verify", "arkts-visual-verify"]      # 无戳沿用上一枚(原规则)
    by_name = filestory.build_fix_chains(led.stories, {}, {})
    assert by_name[0]["fix_versions"] == [2, 3]                          # 没有 marks:按阶段名,v2 也算修
    timed = filestory.build_fix_chains(led.stories, {}, {}, fix_after=atoms_collect.fix_boundary(intervals))
    assert timed[0]["fix_versions"] == [3]                               # 有 marks:execute 结束后的才算
    assert timed[0]["fixer"]["stage"] == "arkts-visual-verify"


def test_build_evidence_lists_build_commands_across_pool(tmp_path: Any) -> None:
    """池子里哪些会话在什么时候跑过构建(hvigor / ohpm):报告页的「执行阶段未见构建」要看整个池子,
    不能只看主线一个 root(DiceRoller 0903 的构建都在后起的 a2h-build 会话里)。"""
    main = [
        *_call("2026-01-01T00:00:00Z", "t0", "Bash", {"command": "ls entry"}),
        *_staged(_call("2026-01-01T00:05:00Z", "t1", "Bash", {"command": "cd /proj && hvigorw assembleHap -p product=default"}),
                 "a2h-build"),
        *_call("2026-01-01T00:06:00Z", "t2", "Bash", {"command": "ohpm install --all"}),
    ]
    led = _ledger(tmp_path, main)
    ev = atoms.build_evidence(led)
    assert [(e["sid8"], e["stage"], e["ts"][11:16]) for e in ev] == [("abcdef12", "a2h-build", "00:05"),
                                                                      ("abcdef12", "a2h-build", "00:06")]
    assert ev[0]["cmd"].startswith("cd /proj && hvigorw")
    assert atoms.build_evidence(_ledger(tmp_path, main[:2])) == []


def test_main_session_verify_stage_write_is_a_fixer(tmp_path: Any) -> None:
    """正式口径不变(execute 之后全是修复),但判定下沉到逐笔版本的阶段:
    主会话在 visual-verify 亲手改 .ets 也是修复方,不再因为是 __main__ 被整体排除。"""
    led = _staged_session(tmp_path)
    chains = filestory.build_fix_chains(led.stories, {}, {})
    assert len(chains) == 1
    ch = chains[0]
    assert ch["fixer"]["id"] == MAIN_ID
    assert ch["fixer"]["stage"] == "arkts-visual-verify"
    assert "主会话" in ch["fixer"]["desc"] and "arkts-visual-verify" in ch["fixer"]["desc"]
    assert ch["fix_versions"] == [3]                          # 文件第 3 版是修复
    assert ch["fixers_all"][0]["vers"] == [3]                 # 主会话第 3 个效应(写 A、派发、改 A)
    assert ch["generator"]["id"] == "agent-aconv-abc123"      # 被改的那行 "b" 是子 agent 写的
    assert ch["generator"]["stage"] == "a2h-execute"


def test_fixer_falls_back_to_lineage_map_without_stage(tmp_path: Any) -> None:
    """没有归属戳(codex / 旧记录):沿用血缘层的 agent 级判定,主会话照旧不是修复方。"""
    main = [
        *_call("2026-01-01T00:00:10Z", "t1", "Agent",
               {"name": "conv", "subagent_type": "worker", "description": "转换 A", "prompt": "转 A"}),
        *_call("2026-01-01T00:01:00Z", "t2", "Edit",
               {"file_path": "/proj/entry/A.ets", "old_string": "b", "new_string": "c"}),
    ]
    child = _sub("转 A", [*_call("2026-01-01T00:00:30Z", "c1", "Write",
                                   {"file_path": "/proj/entry/A.ets", "content": "b\n"})])
    led = _ledger(tmp_path, main, {"agent-aconv-abc123": child})
    assert filestory.build_fix_chains(led.stories, {}, {}) == []
    chains = filestory.build_fix_chains(led.stories, {}, {"aconv-abc123": True})
    assert [c["fixer"]["id"] for c in chains] == ["agent-aconv-abc123"]


def test_chain_entry_lists_come_from_chains(tmp_path: Any) -> None:
    """链页首屏的被修文件 / 修复方直接从链来(与 02 风险点同一口径)。"""
    led = _staged_session(tmp_path)
    chains = filestory.build_fix_chains(led.stories, {}, {})
    fixes, fixers = filestory.chain_entry_lists(chains)
    assert fixes == [{"id": "/proj/entry/A.ets", "label": "A.ets"}]
    assert [f["id"] for f in fixers] == [MAIN_ID] and "主会话" in fixers[0]["label"]


def test_cross_session_pool_fixer_only_from_current_session(tmp_path: Any) -> None:
    """跨会话池:修复方只认当前会话(前序生成轮里 execute 之后的写一律生成侧,老口径保留)。"""
    def _main(sid: str, recs: list[dict[str, Any]]) -> str:
        p = str(tmp_path / f"{sid}.jsonl")
        _write_jsonl(p, recs)
        return p
    gen = _main("aaaaaaaa-0000-0000-0000-000000000000", _staged(
        _call("2026-01-01T00:00:00Z", "g1", "Write", {"file_path": "/proj/entry/A.ets", "content": "b\n"}),
        "a2h-execute") + _staged(
        _call("2026-01-01T00:00:30Z", "g2", "Edit",
              {"file_path": "/proj/entry/A.ets", "old_string": "b", "new_string": "b2"}),
        "arkts-visual-verify"))
    fix = _main("bbbbbbbb-0000-0000-0000-000000000000", _staged(
        _call("2026-01-02T00:00:00Z", "f1", "Edit",
              {"file_path": "/proj/entry/A.ets", "old_string": "b2", "new_string": "c"}),
        "arkts-visual-verify"))
    seq = [0]
    agents = {**atoms_collect.collect_cc(gen, seq), **atoms_collect.collect_cc(fix, seq)}
    led = atoms.build_ledger(agents)
    session_of = {k: a.session for k, a in led.agents.items()}
    assert session_of == {"__main__:aaaaaaaa": "aaaaaaaa", "__main__:bbbbbbbb": "bbbbbbbb"}
    # 不限会话:前序轮主会话在 verify 的那笔也算修复(两个修复方)
    free = filestory.build_fix_chains(led.stories, {}, {})
    assert {f["id"] for f in free[0]["fixers_all"]} == {"__main__:aaaaaaaa", "__main__:bbbbbbbb"}
    # 只认当前会话 bbbbbbbb:前序轮的 verify 写回到生成侧
    cur = filestory.build_fix_chains(led.stories, {}, {}, session_of=session_of, fix_sessions={"bbbbbbbb"})
    assert [f["id"] for f in cur[0]["fixers_all"]] == ["__main__:bbbbbbbb"]
    assert cur[0]["fix_versions"] == [3]
    assert {g["id"] for g in cur[0]["generators"]} == {"__main__:aaaaaaaa"}
    # 只认前序轮 aaaaaaaa:它自己 verify 那笔是修复,bbbbbbbb 的写全归生成侧
    prior = filestory.build_fix_chains(led.stories, {}, {}, session_of=session_of, fix_sessions={"aaaaaaaa"})
    assert [f["id"] for f in prior[0]["fixers_all"]] == ["__main__:aaaaaaaa"]
    assert prior[0]["fix_versions"] == [2]


def _codex_staged_tree(tmp_path: Any) -> str:
    """主线:读 a2h-execute 技能 → 派发子 rollout(子写 A)→ 5 分钟后读 arkts-visual-verify 技能 → 亲手改 A。
    codex 没有归属戳,阶段只能从主线读 SKILL.md 的动作推(短于 90s 的段会被当噪声删掉,所以隔 5 分钟)。"""
    d = tmp_path / "sessions"
    d.mkdir()

    def js_cmd(cmd: str) -> str:
        return ('const r = await tools.exec_command({"cmd":"%s","workdir":"/proj"});\n'
                'text(JSON.stringify(r));' % cmd)

    def patch_js(body: str) -> str:
        return 'const p = "%s";\nawait tools.apply_patch(p);' % body

    root = [
        _crec("2026-01-01T00:00:00Z", "session_meta",
              {"id": CROOT, "session_id": CROOT, "cwd": "/proj", "source": "cli"}),
        _cmsg("2026-01-01T00:00:01Z", "msg_u1", "user", "迁移 dice"),
        *_cexec("2026-01-01T00:00:10Z", "c1",
                js_cmd("cat /home/u/.codex/skills/a2h-execute/SKILL.md"), "# a2h-execute\n"),
        *_cfn("2026-01-01T00:00:30Z", "c2", "spawn_agent",
              {"task_name": "worker1", "agent_type": "worker", "fork_turns": "all", "message": "gAAAA-encrypted"},
              {"task_name": "/root/worker1"}),
        *_cexec("2026-01-01T00:05:00Z", "c3",
                js_cmd("cat /home/u/.codex/skills/arkts-visual-verify/SKILL.md"), "# verify\n"),
        *_cexec("2026-01-01T00:05:10Z", "c4",
                patch_js("*** Begin Patch\\n*** Update File: entry/A.ets\\n@@\\n-b\\n+c\\n*** End Patch"), ""),
        _cmsg("2026-01-01T00:08:00Z", "msg_a1", "assistant", "完成"),
    ]
    child = [
        _crec("2026-01-01T00:00:31Z", "session_meta", {"id": CCHILD, "session_id": CROOT, "cwd": "/proj",
              "source": {"subagent": {"thread_spawn": {"parent_thread_id": CROOT, "agent_path": "/root/worker1",
                                                        "agent_nickname": "Wk", "agent_role": "worker", "depth": 1}}}}),
        _cmsg("2026-01-01T00:00:32Z", "msg_u2", "user", "任务:转 A"),
        *_cexec("2026-01-01T00:00:35Z", "c5",
                patch_js("*** Begin Patch\\n*** Add File: entry/A.ets\\n+b\\n*** End Patch"), ""),
        _cmsg("2026-01-01T00:00:40Z", "msg_a2", "assistant", "A 完成"),
    ]
    _write_jsonl(str(d / f"rollout-{CROOT}.jsonl"), root)
    _write_jsonl(str(d / f"rollout-{CCHILD}.jsonl"), child)
    return str(d / f"rollout-{CROOT}.jsonl")


def test_codex_stage_backfilled_from_skill_reads(tmp_path: Any) -> None:
    """codex 与 CC 对齐:主会话每笔动作按适配器的阶段区间回填 stage,子 rollout 继承派发时阶段,
    版本文件由此有阶段 → 主会话在 verify 亲手改的也是修复方。"""
    root = _codex_staged_tree(tmp_path)
    agents = atoms_collect.collect_codex(root, seq=[0], sessions_root=str(tmp_path / "sessions"))
    led = atoms.build_ledger(agents)
    main_id, child_id = "__main__:" + CROOT[:8], "agent-" + CCHILD[:12]
    m = led.agents[main_id]
    assert [(a.kind, a.stage) for a in m.actions if a.kind in ("dispatch", "write")] == [
        ("dispatch", "a2h-execute"), ("write", "arkts-visual-verify")]
    assert led.agents[child_id].stage == "a2h-execute"
    st = led.stories["/proj/entry/A.ets"]
    assert [(v.by, v.stage) for v in st.versions] == [
        (child_id, "a2h-execute"), (main_id, "arkts-visual-verify")]
    chains = filestory.build_fix_chains(led.stories, {}, {})
    assert [c["fixer"]["id"] for c in chains] == [main_id]
    assert chains[0]["generator"]["id"] == child_id
    assert chains[0]["fixers_all"][0]["vers"] == [2]      # 主会话 v1 派发、v2 改 A


def test_agent_atom_since_window_and_seen_summary(tmp_path: Any) -> None:
    """主会话动辄几百次调用:agent(id, v, since) 只给喂养 (since, v] 的动作;文本里看见的行
    只留前 3 行 + 行号清单 + 总数(与 action 原文是同一份信息,行号是让调查员知道该展开哪次)。"""
    hits = "\n".join(f"{i}:- appName {i}" for i in (12, 40, 128, 615, 700)) + "\n"
    main = [
        *_call("2026-01-01T00:00:00Z", "t1", "Bash", {"command": "cd /proj && grep -n appName spec/r.md"}, hits),
        *_call("2026-01-01T00:00:10Z", "t2", "Write", {"file_path": "/proj/a.ets", "content": "a\n"}),
        *_read_call("2026-01-01T00:00:20Z", "t3", "/proj/b.md", "b\n"),
        *_call("2026-01-01T00:00:30Z", "t4", "Write", {"file_path": "/proj/a.ets", "content": "b\n"}),
    ]
    led = _ledger(tmp_path, main)
    ag = atoms.agent_atom(led, MAIN_ID, 2, since=1)
    assert ag is not None and ag["since"] == 1
    assert [r["path"] for r in ag["reads"]] == ["/proj/b.md"]           # 喂 v1 的 grep 读不在窗口里
    assert [a["ver"] for a in ag["actions"] if a["ver"] is not None] == [2]
    txt = atoms_text.render_agent(led, MAIN_ID, None, root="/proj")
    assert txt.count("看见 ") == 3
    assert "共 5 行" in txt and "615" in txt and "action(#" in txt
    win = atoms_text.render_agent(led, MAIN_ID, 2, root="/proj", since=1)
    assert "r.md" not in win and "b.md" in win and "窗口 v2" in win


# ═══════════════ 收集层完备性:0723 普查漏网的几类(脚本黑盒除外) ═══════════════

def test_bash_variable_assignment_paths_resolve() -> None:
    # 0723 #14384:S=…; sed -n '570,625p' $S/x —— 调查员只能从命令摘要里认出这是读,账本此前记成"其它"
    cmd = "S=/sdk/api; sed -n '570,625p' $S/bundle/App.d.ts; grep -n GET_BUNDLE $S/@ohos.bundle.d.ts | head -3"
    got = {(e.op, e.path, e.start, e.n) for e in atoms_collect.shell_file_ops(cmd, "/proj", {})}
    assert ("read", "/sdk/api/bundle/App.d.ts", 570, 56) in got
    assert ("read", "/sdk/api/@ohos.bundle.d.ts", None, None) in got
    out = atoms_collect.shell_file_ops("export OUT=/tmp/o; echo hi > $OUT/a.txt", "/proj", {})
    assert [(e.op, e.path) for e in out] == [("write", "/tmp/o/a.txt")]
    # 值不是字面量(命令替换)的变量照旧放弃,不编
    assert atoms_collect.shell_file_ops("f=$(find . -name X.kt); cat $f", "/proj", {}) == []


def test_directory_grep_reads_are_reconciled_from_stdout() -> None:
    # 0723 普查:621 次目录 grep,409 次 stdout 里就写着 path:line:,845 个文件此前全没落账
    stdout = ("app/src/A.kt:12:val mHttpUrl = x\napp/src/B.kt:40:mHttpUrl\n"
              "app/src/A.kt:13:more\nBinary file app/x.bin matches\n")
    ops = atoms_collect.shell_file_ops('cd /proj && grep -rn "mHttpUrl" --include="*.kt" app/', "/w", {},
                                       out=stdout)
    by = {o.path: o for o in ops}
    assert set(by) == {"/proj/app/src/A.kt", "/proj/app/src/B.kt"}
    assert by["/proj/app/src/A.kt"].seen == ((12, "val mHttpUrl = x"), (13, "more"))
    assert by["/proj/app/src/B.kt"].seen == ((40, "mHttpUrl"),)
    # -l 只出名字:内容没进上下文,记依赖读(agent 知道这些文件命中了模式)
    ops = atoms_collect.shell_file_ops("cd /proj && grep -rl foo app/", "/w", {},
                                       out="app/src/A.kt\napp/src/C.kt\n")
    assert sorted((o.path, o.dep) for o in ops) == [("/proj/app/src/A.kt", True), ("/proj/app/src/C.kt", True)]
    # rg 默认递归
    ops = atoms_collect.shell_file_ops("rg -n foo src/", "/proj", {}, out="src/a.ets:3:foo()\n")
    assert [(o.path, o.seen) for o in ops] == [("/proj/src/a.ets", ((3, "foo()"),))]
    # 管道里 sed 改了输出形状:行首 token 是路径就算读到了这个文件(行号不可知)
    ops = atoms_collect.shell_file_ops("cd /proj && grep -rnE Binding app/ | sed 's/:.*->/ -> /'", "/w", {},
                                       out="app/H5PayDialog.kt  ->  PayBinding\n")
    assert [(o.path, o.seen) for o in ops] == [("/proj/app/H5PayDialog.kt", None)]


def test_static_list_loop_expands_to_reads() -> None:
    cmd = "cd /proj && for f in a.md b.md; do echo \"--- $f ---\"; sed -n '1,5p' spec/$f; done"
    got = sorted((e.path, e.start, e.n) for e in atoms_collect.shell_file_ops(cmd, "/w", {}))
    assert got == [("/proj/spec/a.md", 1, 5), ("/proj/spec/b.md", 1, 5)]
    # 通配 / seq 的循环项解不开,不编
    assert atoms_collect.shell_file_ops("for f in spec/*.md; do cat $f; done", "/proj", {}) == []


def test_dotfiles_and_multi_file_head_headers() -> None:
    assert [(e.op, e.path) for e in atoms_collect.shell_file_ops("cat .gitignore", "/proj", {})] == \
        [("read", "/proj/.gitignore")]
    stdout = "==> spec/a.md <==\nl1\nl2\n\n==> spec/b.md <==\nm1\n"
    ops = atoms_collect.shell_file_ops("cd /proj && head -2 spec/a.md spec/b.md", "/w", {}, out=stdout)
    by = {o.path: o for o in ops}
    assert by["/proj/spec/a.md"].seen == ((1, "l1"), (2, "l2"))
    assert by["/proj/spec/b.md"].seen == ((1, "m1"),)


def test_unresolved_shell_reads_are_marked_not_silent(tmp_path: Any) -> None:
    """解析不了的读写不许静默:动作带原因,agent 文本标 ⚠,目录里有计数 —— 工具知道自己哪里瞎。"""
    main = [
        *_call("2026-01-01T00:00:00Z", "t1", "Bash", {"command": "cat $(find . -name X.kt)"}, "class X"),
        *_call("2026-01-01T00:00:10Z", "t2", "Bash", {"command": "cat spec/*.md | head -50"}, "..."),
        *_call("2026-01-01T00:00:20Z", "t3", "Bash", {"command": "ls -la && git status"}, "..."),
        *_call("2026-01-01T00:00:30Z", "t4", "Bash", {"command": "python3 - <<'EOF'\nprint(1)\nEOF"}, "1"),
    ]
    led = _ledger(tmp_path, main)
    acts = led.agents[MAIN_ID].actions
    assert [a.detail.get("unresolved") for a in acts] == ["命令替换路径", "通配路径", None, "脚本黑盒"]
    txt = atoms_text.render_agent(led, MAIN_ID, None, root="/proj")
    assert txt.count("⚠ 未解析读写") == 3
    idx = {a["id"]: a for a in atoms.ledger_index(led)["agents"]}
    assert idx[MAIN_ID]["n_unresolved"] == 3


def test_actions_carry_relative_time_from_pool_start(tmp_path: Any) -> None:
    """每笔动作带 T+ 相对时刻(零点 = 池子里最早一条动作),文本里动作号旁就是它;
    链带生成/修复时刻。跨 agent 对先后靠它,不靠动作号。"""
    main = [
        *_read_call("2026-01-01T00:00:00Z", "t0", "/android/Main.java", "class Main {}"),
        *_staged(_call("2026-01-01T00:05:00Z", "t1", "Agent",
                       {"name": "conv", "subagent_type": "worker", "description": "转换 A", "prompt": "转 A"}),
                 "a2h-execute"),
        *_staged(_call("2026-01-01T01:30:00Z", "t2", "Edit",
                       {"file_path": "/proj/entry/A.ets", "old_string": "b", "new_string": "c"}),
                 "arkts-visual-verify"),
    ]
    child = _sub("转 A", [*_call("2026-01-01T00:20:00Z", "c1", "Write",
                                   {"file_path": "/proj/entry/A.ets", "content": "b\n"})])
    led = _ledger(tmp_path, main, {"agent-aconv-abc123": child})
    assert led.t0 == "2026-01-01T00:00:00Z"
    assert atoms.rel_time("2026-01-01T01:30:00Z", led.t0) == "T+1:30"
    assert atoms.rel_time("2026-01-03T02:05:00Z", led.t0) == "T+50:05"      # 跨天不带日期,小时累加
    ag = atoms.agent_atom(led, MAIN_ID)
    assert [a["t"] for a in ag["actions"]] == ["T+0:00", "T+0:05", "T+1:30"]
    assert ag["reads"][0]["t"] == "T+0:00" and ag["t0"] == led.t0
    txt = atoms_text.render_agent(led, MAIN_ID, None, root="/proj")
    assert "T+1:30)" in txt and "迁移开始" in txt
    fa = atoms.file_atom(led, "A.ets", None)
    assert [v["t"] for v in fa["versions"]] == ["T+0:20", "T+1:30"]
    assert "T+0:20" in atoms_text.render_file(led, "A.ets", None, root="/proj")
    chains = filestory.build_fix_chains(led.stories, {}, {})
    assert (chains[0]["gen_at"], chains[0]["fix_at"]) == ("2026-01-01T00:20:00Z", "2026-01-01T01:30:00Z")
    line = atoms_text.render_chains({"chains": chains, "t0": led.t0}, root="/proj")
    assert "生成于 T+0:20" in line and "修复于 T+1:30" in line
    assert "修复方(按先后): 主会话(编排/直接写盘) · arkts-visual-verify 文件v2 @T+1:30" in line
    assert atoms_text._vrange([5, 6, 7, 12, 14, 15]) == "v5-7,v12,v14-15"


def test_codex_exec_shares_stdout_reconciliation_and_unresolved_marks(tmp_path: Any) -> None:
    """codex 的 exec 与 CC 的 Bash 同一套:目录 grep 按 stdout 反证成读;解析不了的标 unresolved。"""
    d = tmp_path / "sessions"
    d.mkdir()

    def js_cmd(cmd: str) -> str:
        return ('const r = await tools.exec_command({"cmd":"%s","workdir":"/proj"});\n'
                'text(JSON.stringify(r));' % cmd)

    root = [
        _crec("2026-01-01T00:00:00Z", "session_meta",
              {"id": CROOT, "session_id": CROOT, "cwd": "/proj", "source": "cli"}),
        _cmsg("2026-01-01T00:00:01Z", "msg_u1", "user", "迁移 dice"),
        *_cexec("2026-01-01T00:00:10Z", "c1", js_cmd("grep -rn mHttpUrl app/"),
                "app/src/A.kt:12:val mHttpUrl = x\napp/src/B.kt:40:mHttpUrl\n"),
        *_cexec("2026-01-01T00:00:20Z", "c2", js_cmd("cat $(find . -name X.kt)"), "class X"),
        _cmsg("2026-01-01T00:01:00Z", "msg_a1", "assistant", "完成"),
    ]
    _write_jsonl(str(d / f"rollout-{CROOT}.jsonl"), root)
    agents = atoms_collect.collect_codex(str(d / f"rollout-{CROOT}.jsonl"), seq=[0], sessions_root=str(d))
    led = atoms.build_ledger(agents)
    m = led.agents["__main__:" + CROOT[:8]]
    reads = sorted((ref.path, ref.ev.seen) for act in m.actions for ref in act.files if ref.op == "read")
    assert reads == [("/proj/app/src/A.kt", ((12, "val mHttpUrl = x"),)), ("/proj/app/src/B.kt", ((40, "mHttpUrl"),))]
    assert [a.detail.get("unresolved") for a in m.actions if a.tool == "exec"] == [None, "命令替换路径"]


# ═══════════════ 调查 agent 的 token 画像驱动的两刀(0723 基线:sessions 每次 9.5K 字符占 11%,
# 整文件 blame 三次 32K/28K/12K 占 19%,都只为找目标链和那几行) ═══════════════


def test_render_chains_can_filter_to_one_file() -> None:
    """sessions(file=…) 只回目标链:调查一条链不必把全部链读一遍。"""
    payload = {"chains": [
        {"file": "entry/src/main/ets/pages/A.ets", "file_abs": "/proj/entry/src/main/ets/pages/A.ets",
         "generator": {"id": "g1", "desc": "转 A", "stage": "a2h-execute"},
         "fixer": {"id": "f1", "desc": "修 A", "stage": "arkts-visual-verify"}},
        {"file": "entry/src/main/ets/pages/B.ets", "file_abs": "/proj/entry/src/main/ets/pages/B.ets",
         "generator": {"id": "g2", "desc": "转 B", "stage": "a2h-execute"},
         "fixer": {"id": "f1", "desc": "修 A", "stage": "arkts-visual-verify"}},
    ], "cross": None, "t0": None}
    full = atoms_text.render_chains(payload, root="/proj")
    assert full.startswith("# 返修链(2)") and "A.ets" in full and "B.ets" in full
    one = atoms_text.render_chains(payload, root="/proj", file="pages/A.ets")
    assert one.startswith("# 返修链(1/2") and "A.ets" in one and "B.ets" not in one
    assert "A.ets" in atoms_text.render_chains(payload, root="/proj", file="A.ets")       # 裸文件名也行
    assert "没有匹配" in atoms_text.render_chains(payload, root="/proj", file="Nope.ets")


def test_render_chains_labels_created_and_template_roots() -> None:
    """三种链根三种问法:rework 问为什么被改;created 问为什么生成期没有它;template(模板/外部原样,生成期没写过)
    问为什么生成期没改它。"""
    def chain(file: str, kind: str, gdesc: str) -> dict[str, Any]:
        return {"file": file.rsplit("/", 1)[-1], "file_abs": "/p/" + file, "kind": kind,
                "generator": {"id": None, "desc": gdesc, "stage": None}, "gen_at": None,
                "fix_at": "2026-01-01T01:00:00Z",
                "fixer": {"id": "f1", "desc": "修", "stage": "arkts-visual-verify"}, "fixers_all": []}
    payload = {"chains": [chain("entry/src/main/module.json5", "template", "生成期未改(模板/外部原样)"),
                          chain("entry/src/main/ets/New.ets", "created", "生成期未产出(修复期新建)")],
               "cross": None, "t0": "2026-01-01T00:00:00Z"}
    text = atoms_text.render_chains(payload, root="/p")
    assert "module.json5 | 生成期未改 · 模板/外部原样(问:为什么生成期没改它)" in text
    assert "New.ets | 生成期未产出 · 修复期新建(问:为什么生成期没有它)" in text
    assert "生成于" not in text and text.count("| 修复于 T+1:00") == 2       # 没有生成侧时刻就不写"生成于 "


def test_render_agent_without_window_keeps_early_reads(tmp_path: Any) -> None:
    """不带窗口的 agent(id, v) 整段给,早期版本的读一条不少 —— 0723 对照实验变体 B 试过默认折叠
    非目标版本,总字符没省反而把 AboutUsPage 从「spec 写错」误判成「漏读」(v1 读的 spec 页被折进一行)。"""
    main = [
        *_read_call("2026-01-01T00:00:00Z", "r1", "/proj/spec/a.md", "spec a\n"),
        *_call("2026-01-01T00:00:10Z", "t1", "Write", {"file_path": "/proj/entry/A.ets", "content": "a\n"}),
        *_read_call("2026-01-01T00:00:20Z", "r2", "/proj/src/B.kt", "class B\n"),
        *_call("2026-01-01T00:00:30Z", "t2", "Write", {"file_path": "/proj/entry/B.ets", "content": "b\n"}),
    ]
    led = _ledger(tmp_path, main)
    full = atoms_text.render_agent(led, MAIN_ID, 2, root="/proj")
    assert "读 spec/a.md@v1" in full and "读 src/B.kt@v1" in full and "写 entry/A.ets@v1" in full
    windowed = atoms_text.render_agent(led, MAIN_ID, 2, root="/proj", since=1)
    assert "读 src/B.kt@v1" in windowed and "读 spec/a.md@v1" not in windowed


def test_blame_changed_lists_only_lines_the_fix_replaced(tmp_path: Any) -> None:
    """blame(path, v_fix, changed=True):只列修复版替换/删除的那些行及其原作者 —— 调查第 4 步要的正是这个。"""
    main = [
        *_call("2026-01-01T00:00:00Z", "t0", "Write", {"file_path": "/proj/entry/A.ets", "content": "a\nb\nc\n"}),
        *_call("2026-01-01T00:00:10Z", "t1", "Agent",
               {"name": "fix", "subagent_type": "worker", "description": "修 A", "prompt": "修"}),
    ]
    child = _sub("修", [*_call("2026-01-01T00:00:30Z", "c1", "Edit",
                                {"file_path": "/proj/entry/A.ets", "old_string": "b\nc\n", "new_string": "B\nc\nd\n"})])
    led = _ledger(tmp_path, main, {"agent-afix-abc123": child})
    bl = atoms.blame(led, "A.ets", 2, changed=True)
    assert bl is not None and bl["changed"] is True and bl["prev_v"] == 1 and bl["known"]
    assert [(x["ln"], x["text"], x["owner"], x["since_v"]) for x in bl["lines"]] == [(2, "b", MAIN_ID, 1)]
    assert bl["added"] == 2                                   # B、d 是新增侧
    assert [(s["owner"], s["n"]) for s in bl["summary"]] == [(MAIN_ID, 1)]
    text = atoms_text.render_blame(led, "A.ets", 2, root="/proj", changed=True)
    assert "v2 替换/删除了 v1 的 1 行" in text and "新增 2 行" in text
    assert "| b" in text and "| c" not in text and "| a" not in text
    first = atoms.blame(led, "A.ets", 1, changed=True)
    assert first is not None and first["lines"] == [] and first["prev_v"] is None and "创建版" in first["note"]


def test_grep_hit_reads_are_not_labeled_full_text(tmp_path: Any) -> None:
    """0723 AboutUsPage 重跑:slice6-risk 对 AppFormInfoManager.ets 只有一次 grep 方法名(命中 6 行),账本按 stdout
    对账记成读是对的,但 file 的读者列表把它标成「全文」,调查 agent 据此判「读全了仍写错」—— 原始转录组戳穿了。
    读的范围三种说法:全文快照 / 行段 / 命中 N 行(grep、head 前缀对账出来的);都不是的写「范围未知」,不许冒充全文。"""
    main = [
        *_call("2026-01-01T00:00:00Z", "t0", "Write", {"file_path": "/proj/entry/A.ets", "content": "a\nfoo\nc\n"}),
        *_call("2026-01-01T00:00:10Z", "t1", "Bash", {"command": "cd /proj && grep -n foo entry/A.ets"}, out="2:foo\n"),
        *_read_call("2026-01-01T00:00:20Z", "t2", "/proj/entry/A.ets", "a\nfoo\nc\n"),
        *_call("2026-01-01T00:00:30Z", "t3", "Read", {"file_path": "/proj/entry/A.ets", "offset": 2, "limit": 1}, "…",
               toolUseResult={"type": "text", "file": {"filePath": "/proj/entry/A.ets", "content": "foo\n",
                                                        "startLine": 2, "numLines": 1, "totalLines": 3}}),
    ]
    led = _ledger(tmp_path, main)
    readers = atoms.file_atom(led, "A.ets", None)["readers"]        # type: ignore[index]
    assert [(r["seen_n"], r["full"], r["start"]) for r in readers] == [(1, False, None), (0, True, 1), (0, False, 2)]
    text = atoms_text.render_file(led, "A.ets", None, root="/proj")
    lines = [ln for ln in text.splitlines() if ln.startswith("- 主会话")]
    assert "命中 1 行" in lines[0] and "全文" not in lines[0]
    assert "全文" in lines[1]
    assert "2-2行" in lines[2]
    agent_txt = atoms_text.render_agent(led, MAIN_ID, None, root="/proj")
    assert "[命中 1 行 写前读]" in agent_txt and "[2-2行 写前读]" in agent_txt


def test_script_touch_shows_on_file_atom_and_index(tmp_path: Any) -> None:
    """0723 AboutUsPage:修复方用 python heredoc 读改写 F012ViewModel.ets(既读又写,方向不猜),账本只在修复方的
    时间线上挂 ⚠,file(F012ViewModel) 显示只有一版 —— 从文件这边看不见有人碰过它。碰过的路径记成 touch:不立版本、
    不猜方向,file 原子列出来带动作号;版本脊柱也带写它那次调用的动作号,展开一跳可达;从没写过只被碰过的文件也进目录。"""
    script = ("cd /proj && python3 - <<'PYEOF'\np='entry/F.ets'\ns=open(p).read()\nopen(p,'w').write(s.replace('a','b'))\n"
              "q='entry/New.ets'\nt=open(q).read()\nopen(q,'w').write(t)\nPYEOF")
    main = [
        *_call("2026-01-01T00:00:00Z", "t0", "Write", {"file_path": "/proj/entry/F.ets", "content": "a\n"}),
        *_call("2026-01-01T00:00:10Z", "t1", "Bash", {"command": script}, out="ok"),
    ]
    led = _ledger(tmp_path, main)
    write_act = next(a for a in led.agents[MAIN_ID].actions if a.tool == "Write")
    bash = next(a for a in led.agents[MAIN_ID].actions if a.tool == "Bash")
    assert bash.detail.get("unresolved") and bash.detail["touched"] == ["/proj/entry/F.ets", "/proj/entry/New.ets"]
    assert len(led.stories["/proj/entry/F.ets"].versions) == 1                       # 没猜出一版写
    fa = atoms.file_atom(led, "F.ets", None)
    assert fa["versions"][0]["seq"] == write_act.seq                                 # 写 v1 那次调用的动作号
    assert [(t["by"], t["seq"], t["reason"]) for t in fa["touches"]] == [(MAIN_ID, bash.seq, bash.detail["unresolved"])]
    text = atoms_text.render_file(led, "F.ets", None, root="/proj")
    assert f"(#{write_act.seq})" in text and "碰过它、方向不明" in text and f"action(#{bash.seq})" in text
    new = atoms.file_atom(led, "New.ets", None)
    assert new is not None and new["n_versions"] == 0 and len(new["touches"]) == 1
    assert "只被脚本碰过(方向不明)" in atoms_text.render_index(led, "ets", None, root="/proj")


def test_render_chains_lists_fix_period_touches() -> None:
    """sessions 末尾列出修复期被脚本碰过、方向不明的工程文件:不在链里,但指针在,模型看到就能展开。"""
    payload = {"chains": [], "cross": None, "t0": "2026-01-01T00:00:00Z",
               "touched": [{"path": "/p/entry/src/main/ets/viewmodels/F012ViewModel.ets", "file": "F012ViewModel.ets",
                            "by": "agent-afix", "by_name": "fixer-r1", "by_ver": 17, "ts": "2026-01-01T01:00:00Z",
                            "seq": 23261, "reason": "脚本黑盒", "has_versions": True}]}
    text = atoms_text.render_chains(payload, root="/p")
    assert "修复期被脚本碰过、方向不明的工程文件(1 个文件,1 次)" in text
    assert "- entry/src/main/ets/viewmodels/F012ViewModel.ets | 1 次 | fixer-r1 v17 #23261 T+1:00 脚本黑盒" in text
    assert "fixer-r1 = agent-afix" in text                                    # 展开要 agent id,给一张对照表


def test_script_literal_used_as_mapping_value_is_not_a_write(tmp_path: Any) -> None:
    """DiceRoller 0903 主会话 v55:heredoc python 初始化 progress.json,正文里
    "hmos_page_map": {"MainActivity": "entry/src/main/ets/pages/Index.ets"} 只是数据值,却被全文倾向兜底
    当成写目标,凭空给 Index.ets 造出一版"修复"(链的修复方 / 修复时刻全错)。紧跟在 `:` 后面的字面量是
    映射的值,不是文件操作的目标 —— 放弃并记「方向不明」;同一脚本里真写的 progress.json 照旧。"""
    script = ('import json\nfrom pathlib import Path\np = Path("spec/visual-verify/progress.json")\n'
              'prog = {"current_round": 1, "hmos_page_map": {"MainActivity": "entry/src/main/ets/pages/Index.ets"}}\n'
              'p.write_text(json.dumps(prog))\n')
    main = [*_call("2026-01-01T00:00:00Z", "t1", "Bash",
                   {"command": "cd /proj\nmkdir -p spec/fix/round-1/ui\npython3 - <<EOF\n" + script
                               + "EOF\nls spec/visual-verify/"})]
    led = _ledger(tmp_path, main)
    assert "/proj/spec/visual-verify/progress.json" in led.stories
    assert not any(p.endswith(".ets") for p in led.stories)
    run = next(a for a in led.agents[MAIN_ID].actions if a.tool == "Bash")
    assert run.detail.get("unresolved") == "脚本字面量方向不明"


def test_render_chains_with_file_only_lists_that_files_touches() -> None:
    """sessions 带 file 时,末尾的「碰过」附录也只列这个文件:0723 上不过滤会把 54 个不相干文件(6.5K 字)
    塞进每一根调查的上下文。只被碰过、没有链的文件,带 file 问它也要能看到自己的碰过记录。"""
    touched = [{"path": "/p/entry/src/main/ets/viewmodels/F012ViewModel.ets", "file": "F012ViewModel.ets",
                "by": "agent-afix", "by_name": "fixer-r1", "by_ver": 17, "ts": "2026-01-01T01:00:00Z",
                "seq": 23261, "reason": "脚本黑盒", "has_versions": True},
               {"path": "/p/entry/src/main/ets/pages/AboutUsPage.ets", "file": "AboutUsPage.ets",
                "by": "agent-afix", "by_name": "fixer-r1", "by_ver": 18, "ts": "2026-01-01T01:05:00Z",
                "seq": 23300, "reason": "脚本黑盒", "has_versions": True}]
    chain = {"file": "entry/src/main/ets/pages/AboutUsPage.ets", "file_abs": "/p/entry/src/main/ets/pages/AboutUsPage.ets",
             "kind": "rework", "generator": {"desc": "slice6", "stage": "gen", "id": "agent-ag"},
             "fixer": {"desc": "fixer-r1", "stage": "fix", "id": "agent-afix"}}
    payload = {"chains": [chain], "cross": None, "t0": "2026-01-01T00:00:00Z", "touched": touched}
    text = atoms_text.render_chains(payload, root="/p", file="AboutUsPage.ets")
    assert "修复期被脚本碰过、方向不明的工程文件(1 个文件,1 次)" in text
    assert "- entry/src/main/ets/pages/AboutUsPage.ets | 1 次 | fixer-r1 v18 #23300" in text
    assert "F012ViewModel" not in text
    text2 = atoms_text.render_chains(payload, root="/p", file="F012ViewModel.ets")
    assert "返修链(0/1,只看 F012ViewModel.ets)" in text2
    assert "- entry/src/main/ets/viewmodels/F012ViewModel.ets | 1 次 | fixer-r1 v17 #23261" in text2
    assert "AboutUsPage" not in text2
