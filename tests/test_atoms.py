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
               {"command": "cd /proj && python3 - <<'EOF'\nopen('x.md','w').write(str(1))\nEOF"}),   # 算出来的内容:盲写
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
    assert "#1" in txt and "行号 615" in txt and "App 显示名" not in txt      # 默认只留行号
    assert "App 显示名" in atoms_text.render_agent(led, MAIN_ID, None, root="/proj", seen=True)
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
    assert "行号 12, 40, 128, 615, 700" in txt and "看见" not in txt        # 默认只留行号
    full = atoms_text.render_agent(led, MAIN_ID, None, root="/proj", seen=True)
    assert full.count("看见 ") == 3 and "共 5 行" in full and "action(#" in full
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
    text = atoms_text.render_file(led, "A.ets", None, root="/proj", readers=True)
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
    # 循环里读改写:ast 层不展开循环,字面量层判不出方向 —— 这才是黑盒(规整的单文件 s.replace 已能解成 edit)
    script = ("cd /proj && python3 - <<'PYEOF'\nfor p in ['entry/F.ets', 'entry/New.ets']:\n    s=open(p).read()\n"
              "    open(p,'w').write(s.replace('a','b'))\nPYEOF")
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
    assert f"(#{write_act.seq}@L" in text and "碰过它、方向不明" in text and f"action(#{bash.seq}@L" in text
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


# ═══════════════ 第 1 步:读写记录修对(0723 复盘出的四类洞) ═══════════════

def test_existence_probe_does_not_create_external_version(tmp_path: Any) -> None:
    """0723 主会话 #837 查进度:for f in …; do if [ -f X ]; then wc -l < X …。循环展开后 wc 的输入重定向
    被当成读,给还不存在的 20 个页面文件立了「外部输入」v1,转换器随后的创建反而成了 v2、diff 退成 unknown。
    存在性守卫里的读不算读,只记「探测」;真正的创建必须是 v1 creation。"""
    loop = ('for f in A B; do if [ -f "entry/pages/$f.ets" ]; then lines=$(wc -l < "entry/pages/$f.ets"); '
            'echo "$f: $lines"; else echo "$f: 未生成"; fi; done')
    main = [*_call("2026-01-01T00:00:00Z", "t1", "Bash", {"command": loop}, "A: 未生成\nB: 未生成"),
            *_call("2026-01-01T00:01:00Z", "t2", "Write",
                   {"file_path": "/proj/entry/pages/A.ets", "content": "x\n"},
                   "File created successfully at: /proj/entry/pages/A.ets")]
    led = _ledger(tmp_path, main)
    st = led.stories["/proj/entry/pages/A.ets"]
    assert [v.source for v in st.versions] == ["full"] and st.versions[0].diff_kind == "creation"
    assert any("探测" in t.reason for t in st.touches)          # 指针不丢:谁探过它,能展开
    b = led.stories.get("/proj/entry/pages/B.ets")
    assert b is None or not b.versions


def test_script_literal_short_name_becomes_touch_on_real_file(tmp_path: Any) -> None:
    """0723 有 327 条幽灵路径:脚本里一个短文件名被按当时的 cwd 拼成新文件(spec/baseline/ui/SplashPage.ets、
    entry/src/main/ets/SplashPage.ets、只有文件名的 SplashPage.ets…)。短名字要先对已知文件,对上就把指针挂过去,
    不造文件、不立版本。"""
    real = "/proj/entry/src/main/ets/pages/SplashPage.ets"
    main = [*_read_call("2026-01-01T00:00:00Z", "t1", real, "@Entry\n"),
            *_call("2026-01-01T00:01:00Z", "t2", "Bash",
                   {"command": "cd spec/baseline/ui && python3 - <<'PY'\ns=open(\"SplashPage.ets\").read()\nprint(len(s))\nPY"},
                   "12")]
    led = _ledger(tmp_path, main)
    assert "/proj/spec/baseline/ui/SplashPage.ets" not in led.stories
    assert any("按文件名对上" in t.reason for t in led.stories[real].touches)


def test_regex_literal_is_not_a_path(tmp_path: Any) -> None:
    """entry/src/main/ets/[A-Za-z0-9_/]+/.ets 曾被当成文件进了账本(0723 主会话 #1383)。"""
    main = [*_call("2026-01-01T00:00:00Z", "t1", "Bash",
                   {"command": "python3 -c \"import re; m=re.search('entry/src/main/ets/[A-Za-z0-9_/]+\\\\.ets', s)\""}, "")]
    led = _ledger(tmp_path, main)
    assert not any("[A-Za-z" in p for p in led.stories)


def test_touch_and_out_flag_count_as_writes(tmp_path: Any) -> None:
    """0723 漏掉的写:touch 建的 .keep、脚本 --out 指定的输出文件都成了「外部输入」。--out 指到目录的,
    记成目录级线索(out_dirs),给后面冒出来的文件挂指针用。"""
    main = [*_call("2026-01-01T00:00:00Z", "t1", "Bash",
                   {"command": "mkdir -p spec/x && touch spec/x/.keep && python3 gen.py --out spec/baseline/module-dep-graph.json"},
                   "ok"),
            *_call("2026-01-01T00:01:00Z", "t2", "Bash",
                   {"command": "python3 gen2.py --out spec/baseline/ui"}, "ok")]
    led = _ledger(tmp_path, main)
    assert led.stories["/proj/spec/x/.keep"].versions[0].by == MAIN_ID
    assert led.stories["/proj/spec/baseline/module-dep-graph.json"].versions[0].by == MAIN_ID
    acts = [a for a in led.agents[MAIN_ID].actions if a.tool == "Bash"]
    assert acts[-1].detail.get("out_dirs") == ["/proj/spec/baseline/ui"]


def test_heredoc_script_body_used_when_run(tmp_path: Any) -> None:
    """gen_page_specs.py 是 cat > … <<EOF 落盘的,之后 python3 它时账本当黑盒,102 份页面 spec 全成外部输入。
    heredoc 落盘的脚本也进脚本表,运行时按它的内容推断读写。"""
    main = [*_call("2026-01-01T00:00:00Z", "t1", "Bash",
                   {"command": "cat > /tmp/s/gen.py <<'EOF'\nopen('spec/baseline/ui/page_1.md','w').write('x')\nEOF"}, ""),
            *_call("2026-01-01T00:01:00Z", "t2", "Bash", {"command": "python3 /tmp/s/gen.py"}, "")]
    led = _ledger(tmp_path, main)
    st = led.stories["/proj/spec/baseline/ui/page_1.md"]
    assert st.versions and st.versions[0].by == MAIN_ID and st.versions[0].via == "script"


def test_out_dir_hint_marks_files_appearing_under_dir(tmp_path: Any) -> None:
    """脚本算出路径生成的文件(资源图片、缺陷单、autofix 日志,0723 有 500 多个):建了目录、跑了脚本,
    紧接着该目录下冒出来的文件挂「可能由此次运行生成」的指针,不立版本不猜。"""
    main = [*_call("2026-01-01T00:00:00Z", "t1", "Bash", {"command": "mkdir -p spec/out && python3 build_out.py"}, "done"),
            *_read_call("2026-01-01T00:05:00Z", "t2", "/proj/spec/out/a.md", "generated\n")]
    led = _ledger(tmp_path, main)
    st = led.stories["/proj/spec/out/a.md"]
    assert st.versions[0].source == "generated" and st.versions[0].by == MAIN_ID      # 脚本跑出来的:写者是跑脚本的 agent
    assert any("可能由此次运行生成" in t.reason and t.seq == led.agents[MAIN_ID].actions[0].seq for t in st.touches)


def test_single_cat_after_cd_binds_to_cd_target(tmp_path: Any) -> None:
    """0723 剩下的幽灵路径大头:`cd /android/AIPPT && cat common.gradle` 的全文快照被按记录 cwd 记到
    工程根下的 common.gradle,安卓侧那条读反而没有内容。快照要挂到沿 cd 链解析出的那条读上。"""
    main = [*_call("2026-01-01T00:00:00Z", "t1", "Bash",
                   {"command": "cd /android/AIPPT && cat common.gradle"}, "apply plugin: 'x'\n")]
    led = _ledger(tmp_path, main)
    assert "/proj/common.gradle" not in led.stories
    st = led.stories["/android/AIPPT/common.gradle"]
    assert st.reads[0].full and st.versions[0].content == "apply plugin: 'x'\n"


def test_single_cat_without_cd_uses_record_cwd(tmp_path: Any) -> None:
    main = [*_call("2026-01-01T00:00:00Z", "t1", "Bash", {"command": "cat spec/x.md"}, "hello\n")]
    led = _ledger(tmp_path, main)
    assert led.stories["/proj/spec/x.md"].reads[0].full


def test_ls_listing_in_stdout_is_not_a_read(tmp_path: Any) -> None:
    """0723 剩下的幽灵路径大头:命令里既有 ls pages/ 又有 grep,grep 的 stdout 对账把 ls 打印的裸文件名
    也当成路径按当时目录拼出来(ROOT/SplashPage.ets、entry/src/main/ets/SplashPage.ets…)。
    有列目录命令时,stdout 里不带 / 的裸名字不算读。"""
    main = [*_call("2026-01-01T00:00:00Z", "t1", "Bash",
                   {"command": 'cd /proj && ls entry/pages/ && grep -rn "x" entry/pages/Index.ets'},
                   "A.ets\nB.ets\nentry/pages/Index.ets:3:x")]
    led = _ledger(tmp_path, main)
    assert "/proj/A.ets" not in led.stories and "/proj/B.ets" not in led.stories
    assert led.stories["/proj/entry/pages/Index.ets"].reads[0].seen == ((3, "x"),)


def test_stdout_bare_name_under_wrong_dir_becomes_touch_on_real_file(tmp_path: Any) -> None:
    """stdout 推出来的路径和脚本字面量一样不算实锤:拼错了目录、同名真文件另有其人时,改挂指针。"""
    real = "/proj/entry/pages/SplashPage.ets"
    main = [*_read_call("2026-01-01T00:00:00Z", "t1", real, "@Entry\n"),
            *_call("2026-01-01T00:01:00Z", "t2", "Bash", {"command": "cd spec && grep -l Splash *.md"}, "SplashPage.ets")]
    led = _ledger(tmp_path, main)
    assert "/proj/spec/SplashPage.ets" not in led.stories
    assert any("按文件名对上" in t.reason for t in led.stories[real].touches)


def test_script_dir_literal_gives_out_dir_hint(tmp_path: Any) -> None:
    """gen_page_specs.py 里写着 OUT = ROOT / "spec/baseline/ui",102 份页面 spec 的路径在脚本里拼出来;
    运行它的那次动作要带上这个目录的线索。生成后几小时才被读的文件也要挂上:线索看「首见之前的运行」,不看时间窗。"""
    body = ("import os\nOUT = 'spec/baseline/ui'\nfor i in range(3):\n"
            "    open(os.path.join(OUT, f'page_{i}.md'), 'w').write('x')\n")
    main = [*_call("2026-01-01T00:00:00Z", "t1", "Bash", {"command": "cat > /tmp/s/gen.py <<'EOF'\n" + body + "EOF"}, ""),
            *_call("2026-01-01T00:01:00Z", "t2", "Bash", {"command": "python3 /tmp/s/gen.py"}, "ok"),
            *_read_call("2026-01-01T05:00:00Z", "t3", "/proj/spec/baseline/ui/page_1.md", "generated\n")]
    led = _ledger(tmp_path, main)
    run = [a for a in led.agents[MAIN_ID].actions if a.tool == "Bash"][1]
    assert run.detail.get("out_dirs") == ["/proj/spec/baseline/ui"]
    st = led.stories["/proj/spec/baseline/ui/page_1.md"]
    assert any("可能由此次运行生成" in t.reason and t.seq == run.seq for t in st.touches)


# ═══════════════ 第 2 步:记录补全 —— agent 原子覆盖整份转录 ═══════════════

def test_assistant_text_blocks_are_indexed_and_expandable(tmp_path: Any) -> None:
    """agent 中途说的话只留了最后一段当收尾,中间的全丢;0723 主会话 670 段 12 万字,「这是我的执行疏漏」
    「我决定推翻源布局」都在里面,原始组多追的跳全靠它。每段正文一条记录,和动作同一套编号,标喂哪一版,能展开。"""
    sub = [_rec("2026-01-01T00:00:00Z", "user", "转换 HomePage"),
           _rec("2026-01-01T00:00:05Z", "assistant", [{"type": "text", "text": "先看布局"}]),
           *_read_call("2026-01-01T00:00:10Z", "t1", "/proj/a.xml", "<x/>\n"),
           _rec("2026-01-01T00:00:20Z", "assistant", [{"type": "text", "text": "源布局是白底,但我决定推翻源布局"}]),
           *_call("2026-01-01T00:00:30Z", "t2", "Write", {"file_path": "/proj/H.ets", "content": "dark\n"},
                  "File created successfully at: /proj/H.ets"),
           _rec("2026-01-01T00:00:40Z", "assistant", [{"type": "text", "text": "完成"}])]
    main = [*_call("2026-01-01T00:00:00Z", "m1", "Agent", {"name": "conv-home", "prompt": "转换 HomePage"}, "done")]
    led = _ledger(tmp_path, main, {"agent-a1": sub})
    a = led.agents["agent-a1"]
    says = [x for x in a.actions if x.kind == "say"]
    assert [s.detail["text"][:4] for s in says] == ["先看布局", "源布局是", "完成"]
    write = next(x for x in a.actions if x.kind == "write")
    assert says[1].at == write.ver and says[1].ver is None           # 喂养这一版,不占版本号
    raw = atoms.action_raw(led, "agent-a1", says[1].seq)
    assert raw and "推翻源布局" in str(raw["input"])
    assert "推翻源布局" in atoms_text.render_agent(led, "agent-a1", root="/proj")


def test_teammate_message_with_prefix_is_inbox_on_main(tmp_path: Any) -> None:
    """子 agent 干完汇报回主会话的记录开头是「Another Claude session sent a message:」,收件匹配只认裸的
    <teammate-message>,0723 主会话 149 条汇报一条没记 —— 子 agent 结果喂主会话下一次决策的边就断在这。"""
    main = [_rec("2026-01-01T00:00:00Z", "user",
                 'Another Claude session sent a message: <teammate-message teammate_id="conv-home" color="blue" '
                 'summary="首页转换完成">已完成,底栏按深色。</teammate-message>')]
    led = _ledger(tmp_path, main)
    inbox = [x for x in led.agents[MAIN_ID].actions if x.kind == "inbox"]
    assert len(inbox) == 1 and inbox[0].detail["from"] == "conv-home"
    assert inbox[0].detail["summary"] == "首页转换完成" and "深色" in inbox[0].detail["text"]
    assert atoms.action_raw(led, MAIN_ID, inbox[0].seq)


def test_main_instructions_and_slash_commands_are_indexed(tmp_path: Any) -> None:
    """主会话没有派发词,操作者的指令就是它的派发词:纯文本指令和 /技能 调用都入账;本地命令回显不算。"""
    main = [_rec("2026-01-01T00:00:00Z", "user", "开始迁移,先跑 spec"),
            _rec("2026-01-01T00:01:00Z", "user",
                 "<command-name>/a2h-spec</command-name><command-message>a2h-spec</command-message>"
                 "<command-args>--fast</command-args>"),
            _rec("2026-01-01T00:01:01Z", "user", "<local-command-stdout>Set model to Opus</local-command-stdout>")]
    led = _ledger(tmp_path, main)
    ins = [x for x in led.agents[MAIN_ID].actions if x.kind == "instruction"]
    assert [x.detail["text"] for x in ins] == ["开始迁移,先跑 spec", "/a2h-spec --fast"]
    assert not [x for x in led.agents[MAIN_ID].actions if x.kind not in ("instruction",)]


def test_skill_injection_is_indexed_with_reader_edge(tmp_path: Any) -> None:
    """灌给 agent 的技能全文(fixer-r1 被灌 12 份 15 万字)一个字不在账上:记成「注入」,
    并在那份 SKILL.md 上挂一个读者,「指南缺条款」这类归因才能从文件侧走到所有被灌过的 agent。"""
    main = [_rec("2026-01-01T00:00:00Z", "user",
                 "<command-message>arkts-x</command-message>\n<command-name>arkts-x</command-name>\n"
                 "<skill-format>true</skill-format>Base rules…")]
    led = _ledger(tmp_path, main)
    inj = [x for x in led.agents[MAIN_ID].actions if x.kind == "inject"]
    assert len(inj) == 1 and inj[0].detail["skill"] == "arkts-x"
    st = led.stories["/proj/.claude/skills/arkts-x/SKILL.md"]
    assert st.reads and st.reads[0].via == "inject" and st.reads[0].by == MAIN_ID


def test_thinking_and_system_reminder_are_indexed(tmp_path: Any) -> None:
    main = [_rec("2026-01-01T00:00:00Z", "assistant", [{"type": "thinking", "thinking": "底栏该用白色"}]),
            _rec("2026-01-01T00:00:10Z", "user", "<system-reminder>build hook: 3 errors</system-reminder>")]
    led = _ledger(tmp_path, main)
    assert [x.kind for x in led.agents[MAIN_ID].actions] == ["think", "system"]
    assert "白色" in str(atoms.action_raw(led, MAIN_ID, led.agents[MAIN_ID].actions[0].seq)["input"])


def test_skill_injection_split_across_blocks_is_one_inject(tmp_path: Any) -> None:
    """0723 的技能注入记录拆成两个 text 块:<command-message> 一块、<command-name>+正文一块;按块归类会记成
    一条 instruction 加一条 inject。user 侧文本按整条记录归类。"""
    main = [_rec("2026-01-01T00:00:00Z", "user",
                 [{"type": "text", "text": "<command-message>arkts-y</command-message>"},
                  {"type": "text", "text": "<command-name>arkts-y</command-name>\n<skill-format>true</skill-format>Body"}])]
    led = _ledger(tmp_path, main)
    assert [x.kind for x in led.agents[MAIN_ID].actions] == ["inject"]


# ═══════════════ 第 3 步:agent 视图索引化 ═══════════════

def test_render_agent_groups_reads_and_hides_seen_by_default(tmp_path: Any) -> None:
    """slice6 到 v14 那份 3.3 万字里读记录行 1.7 万、看见的行 8 千,报告只引用了 6 个文件名和 6 次「看见」:
    同一次调用读的几个文件合成一行,安卓路径缩短,看见的行默认只留行号,想看原文用 seen=True。"""
    main = [*_call("2026-01-01T00:00:00Z", "t1", "Bash",
                   {"command": "cat /android/AIPPT/app/x.kt /android/AIPPT/app/y.kt"}, "a\nb\n"),
            *_call("2026-01-01T00:00:10Z", "t2", "Grep",
                   {"pattern": "hello", "path": "/proj/spec", "output_mode": "content"}, "/proj/spec/a.md:3:hello world"),
            *_call("2026-01-01T00:00:20Z", "t3", "Write", {"file_path": "/proj/out.ets", "content": "z\n"},
                   "File created successfully at: /proj/out.ets")]
    led = _ledger(tmp_path, main)
    text = atoms_text.render_agent(led, MAIN_ID, root="/proj")
    assert "读 2 个文件" in text and "x.kt@v1" in text and "y.kt@v1" in text
    assert "/android/AIPPT/app/x.kt" not in text                       # 安卓路径不整条铺
    assert "看见" not in text and "行号 3" in text
    assert "看见 3: hello world" in atoms_text.render_agent(led, MAIN_ID, root="/proj", seen=True)
    assert "读 3 条" in atoms_text.render_agent(led, MAIN_ID, root="/proj", reads=False)


def test_agent_and_action_accept_names(tmp_path: Any) -> None:
    """模型用「vv-t2-A01」「conv-aboutus」这种名字调 agent 落空过好几次:名字唯一就认。"""
    sub = [_rec("2026-01-01T00:00:01Z", "user", "转换首页"),
           *_call("2026-01-01T00:00:05Z", "s1", "Write", {"file_path": "/proj/H.ets", "content": "x\n"},
                  "File created successfully at: /proj/H.ets")]
    main = [*_call("2026-01-01T00:00:00Z", "m1", "Agent", {"name": "conv-home", "prompt": "转换首页"}, "done",
                   toolUseResult={"agentId": "a1"})]
    led = _ledger(tmp_path, main, {"agent-a1": sub})
    assert "H.ets" in atoms_text.render_agent(led, "conv-home", root="/proj")
    seq = next(x.seq for x in led.agents["agent-a1"].actions if x.kind == "write")
    assert atoms.action_raw(led, "conv-home", seq)


def test_refs_carry_transcript_line(tmp_path: Any) -> None:
    """盲评 17:2 更信原始组,理由几乎全是「行号+时间戳可回查」:动作号旁带转录行号,file 的脊柱和读者行也带。"""
    main = [*_call("2026-01-01T00:00:00Z", "t1", "Write", {"file_path": "/proj/a.ets", "content": "x\n"},
                   "File created successfully at: /proj/a.ets"),
            *_read_call("2026-01-01T00:00:10Z", "t2", "/proj/a.ets", "x\n")]
    led = _ledger(tmp_path, main)
    assert "@L1" in atoms_text.render_agent(led, MAIN_ID, root="/proj")
    ftext = atoms_text.render_file(led, "a.ets", root="/proj", readers=True)
    assert "@L1" in ftext and "@L3" in ftext


def test_render_agent_inbox_as_index_lines(tmp_path: Any) -> None:
    """主会话 149 条汇报 35 万字,收件箱默认一行一条,全文按指针展开。"""
    main = [_rec(f"2026-01-01T00:0{i}:00Z", "user",
                 f'Another Claude session sent a message: <teammate-message teammate_id="w{i}" summary="done {i}">'
                 + "正文" * 200 + "</teammate-message>") for i in range(3)]
    led = _ledger(tmp_path, main)
    text = atoms_text.render_agent(led, MAIN_ID, root="/proj")
    assert "来自 w0" in text and "done 0" in text and text.count("正文") < 300


# ═══════════════ 第 4 步:带起点的 search ═══════════════

def test_search_agent_is_anchored_and_grouped(tmp_path: Any) -> None:
    """原始组 38% 的调用是「这个词出现在这个 agent 的哪些记录里」,再往前翻几条记录。我们的版本是带起点的:
    只看喂养第 v 版及之前的记录,派发词 / 读到的内容 / 写入内容 / 命令 / 结果 / 自述都查,按种类分组,
    每条带动作号、喂哪一版、下一跳;锚点之后的单列计数,不混进因果。"""
    sub = [_rec("2026-01-01T00:00:00Z", "user", "底部导航深色背景 #202022,选中 #5B3CFF"),
           *_read_call("2026-01-01T00:00:10Z", "r1", "/proj/activity_home.xml",
                       '<LinearLayout\n  android:background="@color/white"\n/>\n'),
           _rec("2026-01-01T00:00:20Z", "assistant", [{"type": "text", "text": "源布局是白底,但我决定按派发词用深色"}]),
           *_call("2026-01-01T00:00:30Z", "w1", "Write", {"file_path": "/proj/HomePage.ets", "content": "// 深色底栏 #202022\n"},
                  "File created successfully at: /proj/HomePage.ets"),
           *_read_call("2026-01-01T00:00:40Z", "r2", "/proj/other.xml", "white again\n")]
    main = [*_call("2026-01-01T00:00:00Z", "m1", "Agent", {"name": "conv-home", "prompt": "转换首页"}, "done",
                   toolUseResult={"agentId": "a1"})]
    led = _ledger(tmp_path, main, {"agent-a1": sub})
    res = atoms.search_agent(led, "conv-home", "white", v=1)
    assert res is not None and res["excluded_after"] == 1                     # v1 之后那次读不算
    hit = next(h for h in res["hits"] if h["kind"] == "read")
    assert hit["target"] == "/proj/activity_home.xml" and hit["snips"][0][0] == 2   # 命中在读到内容的第 2 行
    txt = atoms_text.render_search(led, "white", agent="conv-home", v=1, root="/proj")
    assert "activity_home.xml@v1" in txt and "第 2 行" in txt and "锚点之后另有 1 条" in txt and "file(" in txt
    txt2 = atoms_text.render_search(led, "#202022", agent="conv-home", root="/proj")
    assert "派发词" in txt2 and "写 HomePage.ets@v1" in txt2
    txt3 = atoms_text.render_search(led, "决定", agent="conv-home", root="/proj")
    assert "说" in txt3 and "决定按派发词" in txt3


def test_search_agent_time_window_for_dispatcher(tmp_path: Any) -> None:
    """派发者后来说的话(主会话 FV-1 时的「这是我的执行疏漏」)在转换器的版本窗口之外,但在文件时间线上:
    用文件两个版本的时刻做区间来查,不给整段。"""
    main = [*_call("2026-01-01T00:00:00Z", "t1", "Write", {"file_path": "/proj/a.ets", "content": "x\n"},
                   "File created successfully at: /proj/a.ets"),
            _rec("2026-01-01T01:00:00Z", "assistant", [{"type": "text", "text": "icon 自愈没跑,这是我的执行疏漏"}]),
            *_call("2026-01-01T02:00:00Z", "t2", "Write", {"file_path": "/proj/a.ets", "content": "y\n"}, "ok")]
    led = _ledger(tmp_path, main)
    res = atoms.search_agent(led, MAIN_ID, "疏漏", since_ts="2026-01-01T00:00:00Z", until_ts="2026-01-01T02:00:00Z")
    assert res is not None and [h["kind"] for h in res["hits"]] == ["say"]
    assert not atoms.search_agent(led, MAIN_ID, "疏漏", since_ts="2026-01-01T00:00:00Z", until_ts="2026-01-01T00:30:00Z")["hits"]


def test_search_file_first_appearance_and_reader_hits(tmp_path: Any) -> None:
    """这个词第一次出现在第几版、谁写的;哪些读者的读结果里命中过它 —— blame 只回答给定版本的行归属,回答不了首次出现。"""
    main = [*_call("2026-01-01T00:00:00Z", "w1", "Write", {"file_path": "/proj/spec/p.md", "content": "a\n"},
                   "File created successfully at: /proj/spec/p.md"),
            *_call("2026-01-01T00:01:00Z", "w2", "Write", {"file_path": "/proj/spec/p.md", "content": "a\nappName from label\n"}, "ok"),
            *_call("2026-01-01T00:02:00Z", "g1", "Bash", {"command": "grep -n appName /proj/spec/p.md"}, "2:appName from label")]
    led = _ledger(tmp_path, main)
    res = atoms.search_file(led, "p.md", "appName")
    assert res is not None and res["first"] == 2 and [x["v"] for x in res["versions"]] == [2]
    txt = atoms_text.render_search(led, "appName", file="p.md", root="/proj")
    assert "首次出现: v2" in txt and "第 2 行" in txt and "读者" in txt


def test_search_requires_anchor(tmp_path: Any) -> None:
    led = _ledger(tmp_path, [])
    assert "只允许带时间上限" in atoms_text.render_search(led, "x", root="/proj")


def test_render_agent_omits_result_before_last_version(tmp_path: Any) -> None:
    """agent(id, v) 问的是它写第 v 版时手里有什么;v 不是最后一版,收尾输出是之后的事,不给。"""
    main = [*_call("2026-01-01T00:00:00Z", "t1", "Write", {"file_path": "/proj/a.ets", "content": "x\n"},
                   "File created successfully at: /proj/a.ets"),
            *_call("2026-01-01T00:00:10Z", "t2", "Write", {"file_path": "/proj/b.ets", "content": "y\n"},
                   "File created successfully at: /proj/b.ets"),
            _rec("2026-01-01T00:00:20Z", "assistant", [{"type": "text", "text": "全部完成,两个文件已落盘"}])]
    led = _ledger(tmp_path, main)
    assert "收尾输出" not in atoms_text.render_agent(led, MAIN_ID, 1, root="/proj")
    assert "两个文件已落盘" in atoms_text.render_agent(led, MAIN_ID, 2, root="/proj")
    assert "两个文件已落盘" in atoms_text.render_agent(led, MAIN_ID, root="/proj")


def test_render_agent_result_is_an_index_line(tmp_path: Any) -> None:
    """除派发指令外 agent 全是索引:收尾只给开头和那段「说」的动作号,全文 action 展开。"""
    long = "收尾:" + "生成了很多文件," * 60
    main = [*_call("2026-01-01T00:00:00Z", "t1", "Write", {"file_path": "/proj/a.ets", "content": "x\n"},
                   "File created successfully at: /proj/a.ets"),
            _rec("2026-01-01T00:00:20Z", "assistant", [{"type": "text", "text": long}])]
    led = _ledger(tmp_path, main)
    txt = atoms_text.render_agent(led, MAIN_ID, root="/proj")
    tail = txt.split("## 收尾输出", 1)[1]
    say = [a for a in led.agents[MAIN_ID].actions if a.kind == "say"][-1]
    assert f"#{say.seq}@L" in tail and "action" in tail and len(tail) < len(long)
    assert long in str(atoms.action_raw(led, MAIN_ID, say.seq)["input"])


def test_render_file_readers_off_by_default(tmp_path: Any) -> None:
    """单根往上追只看写者;读者是下游,归并阶段(指南漏条款波及了哪些页)才用。file() 默认一行计数,readers=1 展开。"""
    main = [*_call("2026-01-01T00:00:00Z", "t1", "Write", {"file_path": "/proj/g.md", "content": "rule\n"},
                   "File created successfully at: /proj/g.md"),
            *_read_call("2026-01-01T00:00:10Z", "t2", "/proj/g.md", "rule\n"),
            *_read_call("2026-01-01T00:00:20Z", "t3", "/proj/g.md", "rule\n")]
    led = _ledger(tmp_path, main)
    text = atoms_text.render_file(led, "g.md", root="/proj")
    assert "读者 2 个" in text and "readers=1" in text and "| 全文 (#" not in text            # 读者行不铺
    full = atoms_text.render_file(led, "g.md", root="/proj", readers=True)
    assert full.count("| 全文 (#") == 2


def test_search_write_hit_shows_matching_content_line(tmp_path: Any) -> None:
    """写入 / 派发命中要显示命中的那一行,不是工具输入 JSON 的开头。"""
    main = [*_call("2026-01-01T00:00:00Z", "w1", "Write", {"file_path": "/proj/a.ets", "content": "x\nfoo bar\ny\n"},
                   "File created successfully at: /proj/a.ets")]
    led = _ledger(tmp_path, main)
    txt = atoms_text.render_search(led, "foo", agent=MAIN_ID, root="/proj")
    assert "foo bar" in txt and "file_path" not in txt


def test_search_file_collapses_unchanged_versions(tmp_path: Any) -> None:
    """HomePage.ets 29 版里同一处命中被原样列了 29 遍(9 千字):命中行没变的版本折成一行。"""
    main = [*_call("2026-01-01T00:00:00Z", "w1", "Write", {"file_path": "/proj/h.ets", "content": "a\nappName here\n"},
                   "File created successfully at: /proj/h.ets"),
            *_call("2026-01-01T00:01:00Z", "w2", "Write", {"file_path": "/proj/h.ets", "content": "a\nappName here\nb\n"}, "ok"),
            *_call("2026-01-01T00:02:00Z", "w3", "Write", {"file_path": "/proj/h.ets", "content": "a\nappName here\nb\nc\n"}, "ok"),
            *_call("2026-01-01T00:03:00Z", "w4", "Write", {"file_path": "/proj/h.ets", "content": "appName moved\n"}, "ok")]
    led = _ledger(tmp_path, main)
    txt = atoms_text.render_search(led, "appName", file="h.ets", root="/proj")
    assert "首次出现: v1" in txt and "v2–v3 命中行未变" in txt and txt.count("appName here") == 1
    assert "- v4" in txt and "appName moved" in txt


def test_render_chains_gives_dispatcher_interval_hint() -> None:
    """两次四根验收,模型都没去主会话的生成→修复区间里查「执行疏漏」这类话:sessions 带文件时把派发者和区间摆出来。"""
    payload = {"chains": [{"file": "entry/src/main/ets/components/MineComponent.ets",
                           "file_abs": "/p/entry/src/main/ets/components/MineComponent.ets", "kind": "rework",
                           "generator": {"desc": "conv-minefrag", "stage": "a2h-execute", "id": "agent-aconv",
                                         "parent": "__main__:9b3105a2", "parent_name": "主会话·9b3105a2"},
                           "fixer": {"desc": "fixer-r1", "stage": "fix", "id": "agent-afix"},
                           "gen_at": "2026-07-24T06:28:42Z", "fix_at": "2026-07-26T20:42:48Z"}],
               "cross": None, "t0": "2026-07-23T12:02:56Z", "touched": []}
    text = atoms_text.render_chains(payload, root="/p", file="MineComponent.ets")
    assert "派发者 主会话·9b3105a2" in text
    assert 'search(q, agent="__main__:9b3105a2", since_ts="2026-07-24T06:28:42Z", until_ts="2026-07-26T20:42:48Z")' in text


def test_ledger_meta_carries_parent_for_chains(tmp_path: Any) -> None:
    """链的生成方名片要带派发者 id 与名字,sessions 才能给出区间提示。"""
    from migloop import service
    sub = [_rec("2026-01-01T00:00:01Z", "user", "转换首页"),
           *_call("2026-01-01T00:00:05Z", "s1", "Write", {"file_path": "/proj/H.ets", "content": "x\n"},
                  "File created successfully at: /proj/H.ets")]
    main = [*_call("2026-01-01T00:00:00Z", "m1", "Agent", {"name": "conv-home", "prompt": "转换首页"}, "done",
                   toolUseResult={"agentId": "a1"})]
    led = _ledger(tmp_path, main, {"agent-a1": sub})
    meta = service._merge_ledger_meta({}, led)
    assert meta["a1"]["parent"] == MAIN_ID and meta["a1"]["parent_name"]


def test_agent_window_does_not_reprint_prompt(tmp_path: Any) -> None:
    """agent(id, v, since) 问的是一段窗口:派发指令在 v0 就有了,窗口里不重印(每次 3K,窗口本身才 1.4K)。"""
    sub = [_rec("2026-01-01T00:00:00Z", "user", "转换首页,底栏深色"),
           *_call("2026-01-01T00:00:10Z", "s1", "Write", {"file_path": "/proj/a.ets", "content": "1\n"},
                  "File created successfully at: /proj/a.ets"),
           *_call("2026-01-01T00:00:20Z", "s2", "Write", {"file_path": "/proj/b.ets", "content": "2\n"},
                  "File created successfully at: /proj/b.ets")]
    main = [*_call("2026-01-01T00:00:00Z", "m1", "Agent", {"name": "conv-home", "prompt": "转换首页,底栏深色"}, "done",
                   toolUseResult={"agentId": "a1"})]
    led = _ledger(tmp_path, main, {"agent-a1": sub})
    win = atoms_text.render_agent(led, "conv-home", 2, root="/proj", since=1)
    assert "底栏深色" not in win and "派发指令: 见 agent" in win
    assert "底栏深色" in atoms_text.render_agent(led, "conv-home", 2, root="/proj")


def test_sub_agent_header_notes_definition_outside_transcript(tmp_path: Any) -> None:
    """conv-mine 的「固有尺寸交 icon-sizing 自愈」在它全部记录里没有来源:来自类型定义(系统提示),转录不含。头部要说。"""
    sub = [_rec("2026-01-01T00:00:00Z", "user", "转换"),
           *_call("2026-01-01T00:00:10Z", "s1", "Write", {"file_path": "/proj/a.ets", "content": "1\n"},
                  "File created successfully at: /proj/a.ets")]
    main = [*_call("2026-01-01T00:00:00Z", "m1", "Agent", {"name": "conv-x", "subagent_type": "a2h-activity-converter",
                                                            "prompt": "转换"}, "done", toolUseResult={"agentId": "a1"})]
    led = _ledger(tmp_path, main, {"agent-a1": sub})
    text = atoms_text.render_agent(led, "conv-x", root="/proj")
    assert "a2h-activity-converter" in text and "不在转录里" in text


def test_fix_basis_lists_docs_read_before_first_fix_write(tmp_path: Any) -> None:
    """链上的「修因」以前是修复方的收尾摘要(51/51 处理完…),对这个文件没信息;换成它写第一笔修复前读的单。"""
    from migloop import filestory, service
    main = [*_call("2026-01-01T00:00:00Z", "t1", "Write", {"file_path": "/proj/entry/A.ets", "content": "a\n"},
                   "File created successfully at: /proj/entry/A.ets"),
            *_read_call("2026-01-01T02:00:00Z", "t2", "/proj/spec/fix/round-1/ui/ALIGN_A_bug.md", "fix it\n"),
            *_call("2026-01-01T02:00:10Z", "t3", "Write", {"file_path": "/proj/entry/A.ets", "content": "b\n"}, "ok")]
    led = _ledger(tmp_path, main)
    chains = filestory.build_fix_chains(led.stories, {}, {}, root="/proj", fix_after="2026-01-01T01:00:00Z")
    assert chains and chains[0]["file"] == "A.ets"
    service.attach_fix_basis(chains, led)
    basis = chains[0]["fixers_all"][0]["basis"]
    assert [b["file"] for b in basis] == ["ui/ALIGN_A_bug.md"] and basis[0]["seq"]
    text = atoms_text.render_chains({"chains": chains, "cross": None, "t0": led.t0, "touched": []}, root="/proj")
    assert "依据" in text and "ALIGN_A_bug.md" in text


# ═══════════════ 批量生成:脚本跑出来的文件有写者,不是外部输入 ═══════════════

def test_script_generated_files_get_the_run_as_writer(tmp_path: Any) -> None:
    """0723 的 102 份页面 spec、112 份 ui-snapshots 是主会话跑 gen_page_specs.py 一次生成的,账本却记「外部输入」,
    归因到 spec 就断了。首版记成「批量生成」:写者 = 跑脚本的 agent(喂养它当时的版本),候选运行的动作号、同批文件数都带上;
    真正池子外的文件(没人跑过任何脚本指向它)仍是外部输入。"""
    body = ("import os\nOUT = 'spec/baseline/ui'\nfor i in range(3):\n"
            "    open(os.path.join(OUT, f'page_{i}.md'), 'w').write('x')\n")
    main = [*_call("2026-01-01T00:00:00Z", "t1", "Bash", {"command": "cat > /tmp/s/gen.py <<'EOF'\n" + body + "EOF"}, ""),
            *_call("2026-01-01T00:01:00Z", "t2", "Bash", {"command": "python3 /tmp/s/gen.py"}, "ok"),
            *_read_call("2026-01-01T03:00:00Z", "t3", "/proj/spec/baseline/ui/page_1.md", "generated 1\n"),
            *_read_call("2026-01-01T03:01:00Z", "t4", "/proj/spec/baseline/ui/page_2.md", "generated 2\n"),
            *_read_call("2026-01-01T03:02:00Z", "t5", "/android/app/res/values/colors.xml", "<c/>\n")]
    led = _ledger(tmp_path, main)
    run = [a for a in led.agents[MAIN_ID].actions if a.tool == "Bash"][1]
    v1 = led.stories["/proj/spec/baseline/ui/page_1.md"].versions[0]
    assert v1.source == "generated" and v1.by == MAIN_ID and v1.via == "script-run"
    assert v1.gen_runs == (run.seq,) and v1.batch == 2 and v1.act_seq == run.seq
    assert led.stories["/android/app/res/values/colors.xml"].versions[0].source == "external"
    text = atoms_text.render_file(led, "page_1.md", root="/proj")
    assert "批量生成" in text and "同批 2 个" in text and f"#{run.seq}@L" in text


def test_generated_writer_prefers_specific_earliest_run_not_project_root(tmp_path: Any) -> None:
    """page_0031 曾挂到三次 api-inventory 脚本上:脚本里 ROOT = Path("/proj") 被当成输出目录,全工程都匹配。
    工程根这种覆盖面过大的目录不算线索;脚本里的相对目录按脚本自己的 ROOT 解析;候选按前缀最长、时间最早排。"""
    gen = ("from pathlib import Path\nROOT = Path('/proj')\nOUT = ROOT / 'spec/baseline/ui'\n"
           "for i in range(3):\n    (OUT / f'page_{i}.md').write_text('x')\n")
    other = "from pathlib import Path\nROOT = Path('/proj')\n(ROOT / 'spec/baseline/api/inv.json').write_text('{}')\n"
    main = [*_call("2026-01-01T00:00:00Z", "t1", "Bash", {"command": "cat > /tmp/s/gen.py <<'EOF'\n" + gen + "EOF"}, ""),
            *_call("2026-01-01T00:01:00Z", "t2", "Bash", {"command": "cd /tmp/s && python3 gen.py"}, "ok"),
            *_call("2026-01-01T01:00:00Z", "t3", "Bash", {"command": "python3 - <<'PYEOF'\n" + other + "PYEOF"}, "ok"),
            *_read_call("2026-01-01T02:00:00Z", "t4", "/proj/spec/baseline/ui/page_1.md", "p1\n"),
            *_read_call("2026-01-01T02:00:10Z", "t5", "/proj/entry/src/main/ets/X.ets", "x\n")]
    led = _ledger(tmp_path, main)
    run = [a for a in led.agents[MAIN_ID].actions if a.tool == "Bash"][1]
    v1 = led.stories["/proj/spec/baseline/ui/page_1.md"].versions[0]
    assert v1.source == "generated" and v1.act_seq == run.seq and v1.gen_runs == (run.seq,)
    assert led.stories["/proj/entry/src/main/ets/X.ets"].versions[0].source == "external"   # 工程根不算线索


def test_fix_basis_looks_back_three_versions(tmp_path: Any) -> None:
    """AboutUsPage:修复方 v16 读缺陷单、v17 写 F012ViewModel、v18 才写本文件;依据要往前看几版。"""
    from migloop import filestory, service
    main = [*_call("2026-01-01T00:00:00Z", "t1", "Write", {"file_path": "/proj/entry/A.ets", "content": "a\n"},
                   "File created successfully at: /proj/entry/A.ets"),
            *_read_call("2026-01-01T02:00:00Z", "t2", "/proj/spec/fix/round-1/ui/ALIGN_A.md", "fix\n"),
            *_call("2026-01-01T02:00:05Z", "t3", "Write", {"file_path": "/proj/entry/B.ets", "content": "b\n"},
                   "File created successfully at: /proj/entry/B.ets"),
            *_call("2026-01-01T02:00:10Z", "t4", "Write", {"file_path": "/proj/entry/A.ets", "content": "b\n"}, "ok")]
    led = _ledger(tmp_path, main)
    chains = filestory.build_fix_chains(led.stories, {}, {}, root="/proj", fix_after="2026-01-01T01:00:00Z")
    service.attach_fix_basis(chains, led)
    a = next(c for c in chains if c["file"] == "A.ets")
    assert [b["file"] for b in a["fixers_all"][0]["basis"]] == ["ui/ALIGN_A.md"]


def test_cat_concatenation_is_a_derived_write_with_known_content(tmp_path: Any) -> None:
    """resource-mapping.md 是 `cat doc_head.md doc_mid.md doc_tail.md > resource-mapping.md` 拼出来的,三段内容都在账上,
    拼接结果却记「内容未知」,第 615 行是谁写的就查不到。cat 拼接算派生写入:各段已知就拼出来。"""
    main = [*_call("2026-01-01T00:00:00Z", "t1", "Write", {"file_path": "/proj/tmp/a.md", "content": "A1\nA2\n"},
                   "File created successfully at: /proj/tmp/a.md"),
            *_call("2026-01-01T00:00:10Z", "t2", "Write", {"file_path": "/proj/tmp/b.md", "content": "B1\n"},
                   "File created successfully at: /proj/tmp/b.md"),
            *_call("2026-01-01T00:00:20Z", "t3", "Bash", {"command": "cat tmp/a.md tmp/b.md > spec/all.md"}, "")]
    led = _ledger(tmp_path, main)
    st = led.stories["/proj/spec/all.md"]
    assert st.versions[0].content == "A1\nA2\nB1\n" and st.versions[0].source == "derived"
    assert atoms.blame(led, "all.md")["known"]


def test_blame_changed_marks_bridged_owners(tmp_path: Any) -> None:
    """MineComponent v26 的 blame 曾给「归属未知(断点后)」:v14 edit-miss、v19 实录外修改,之后的行全丢归属。
    重锚版里和断点前同文的行沿用原作者并标「跨断点同文推定」。"""
    main = [*_call("2026-01-01T00:00:00Z", "t1", "Write", {"file_path": "/proj/m.ets", "content": "a\nb\nc\n"},
                   "File created successfully at: /proj/m.ets"),
            *_call("2026-01-01T00:01:00Z", "t2", "Edit", {"file_path": "/proj/m.ets", "old_string": "zzz", "new_string": "q"}, "ok"),
            *_read_call("2026-01-01T00:02:00Z", "t3", "/proj/m.ets", "a\nB\nc\n"),
            *_call("2026-01-01T00:03:00Z", "t4", "Write", {"file_path": "/proj/m.ets", "content": "X\nB\nc\n"}, "ok")]
    led = _ledger(tmp_path, main)
    bl = atoms.blame(led, "m.ets", 4, changed=True)
    assert bl["lines"][0]["owner"] == MAIN_ID and bl["lines"][0]["inferred"] and bl["unknown"] == 0
    txt = atoms_text.render_blame(led, "m.ets", 4, root="/proj", changed=True)
    assert "跨断点同文推定" in txt


def test_fix_basis_reports_what_fix_side_saw_that_generation_did_not(tmp_path: Any) -> None:
    """app.json5 那根的结论不是「谁写错」,是修复侧拿到了生成侧没有的一类信息:有人把应用跑起来看了这一页。
    链行要写出来:依据的单是谁写的、那人写单之前看的是真机 dump / 截图 / 安卓基线 哪一类。"""
    from migloop import filestory, service
    vv = [_rec("2026-01-01T02:00:00Z", "user", "验证 AboutUs 页"),
          *_read_call("2026-01-01T02:00:10Z", "v1", "/proj/spec/visual-verify/dump/AboutUs.hmos.xml", "<node text=\"$string:app_name\"/>\n"),
          *_read_call("2026-01-01T02:00:20Z", "v2", "/proj/spec/visual-verify/sbs/AboutUs.jpeg", "\x00"),
          *_call("2026-01-01T02:00:30Z", "v3", "Write", {"file_path": "/proj/spec/fix/round-1/feat/AboutUs_01.md", "content": "actual: $string:app_name\n"},
                 "File created successfully at: /proj/spec/fix/round-1/feat/AboutUs_01.md")]
    main = [*_call("2026-01-01T00:00:00Z", "t1", "Write", {"file_path": "/proj/entry/A.ets", "content": "a\n"},
                   "File created successfully at: /proj/entry/A.ets"),
            *_call("2026-01-01T01:59:00Z", "m1", "Agent", {"name": "vv-1", "prompt": "验证 AboutUs 页"}, "done",
                   toolUseResult={"agentId": "v1"}),
            *_read_call("2026-01-01T03:00:00Z", "t2", "/proj/spec/fix/round-1/feat/AboutUs_01.md", "actual: $string:app_name\n"),
            *_call("2026-01-01T03:00:10Z", "t3", "Write", {"file_path": "/proj/entry/A.ets", "content": "b\n"}, "ok")]
    led = _ledger(tmp_path, main, {"agent-v1": vv})
    chains = filestory.build_fix_chains(led.stories, {}, {}, root="/proj", fix_after="2026-01-01T01:00:00Z")
    service.attach_fix_basis(chains, led)
    b = chains[0]["fixers_all"][0]["basis"][0]
    assert b["file"] == "feat/AboutUs_01.md" and b["writer"] == "agent-v1" and b["writer_how"] == "写"
    assert b["evidence"] == {"真机 dump": 1, "截图": 1}
    text = atoms_text.render_chains({"chains": chains, "cross": None, "t0": led.t0, "touched": []}, root="/proj")
    assert "依据单的来历" in text and "真机 dump" in text and "vv-1" in text


def test_fix_basis_skips_skill_injection(tmp_path: Any) -> None:
    """DiceRoller app.json5:修复方开工前系统注入了六份 SKILL.md(via=inject),它们把「依据」占满,真正读的单反而被挤掉。
    技能定义不是依据。"""
    from migloop import filestory, service
    skill = ("<command-message>a2h-execute</command-message>\n<command-name>a2h-execute</command-name>\n"
             "<skill-format>true</skill-format># a2h-execute\n做事\n")
    main = [*_call("2026-01-01T00:00:00Z", "t1", "Write", {"file_path": "/proj/entry/A.ets", "content": "a\n"},
                   "File created successfully at: /proj/entry/A.ets"),
            _rec("2026-01-01T02:00:00Z", "user", skill),
            *_read_call("2026-01-01T02:00:05Z", "t2", "/proj/spec/fix/round-1/ui/ALIGN_A.md", "fix\n"),
            *_call("2026-01-01T02:00:10Z", "t3", "Write", {"file_path": "/proj/entry/A.ets", "content": "b\n"}, "ok")]
    led = _ledger(tmp_path, main)
    chains = filestory.build_fix_chains(led.stories, {}, {}, root="/proj", fix_after="2026-01-01T01:00:00Z")
    service.attach_fix_basis(chains, led)
    files = [b["file"] for b in chains[0]["fixers_all"][0]["basis"]]
    assert files == ["ui/ALIGN_A.md"], files


# ═══════════════ 子代理亲手追 DiceRoller Index.ets 撞出的四条 ═══════════════

def test_action_long_output_is_addressable(tmp_path: Any) -> None:
    """think #4218 有 9.8 万字,action 只回前两万且不说截在哪;调查员要的决策句在后面,只能拿 search 撞。
    截断处要明说「剩余多少、offset 多少继续」,offset= 从中间起,find= 直接跳到关键词前。"""
    body = "a" * 5000 + "DECISION keep Roll" + "b" * 5000
    main = [*_call("2026-01-01T00:00:00Z", "t1", "Bash", {"command": "echo"}, body)]
    led = _ledger(tmp_path, main)
    seq = led.agents[MAIN_ID].actions[0].seq
    head = atoms_text.render_action(led, MAIN_ID, seq, max_chars=1000)
    assert "共 10018 字" in head and "剩余 9018 字" in head and "offset=1000" in head
    mid = atoms_text.render_action(led, MAIN_ID, seq, max_chars=1000, offset=4900)
    assert "DECISION keep Roll" in mid and "第 4901-5900 字" in mid
    found = atoms_text.render_action(led, MAIN_ID, seq, max_chars=400, find="DECISION")
    assert "DECISION keep Roll" in found and "offset=" in found
    miss = atoms_text.render_action(led, MAIN_ID, seq, max_chars=400, find="NOPE")
    assert "未命中" in miss


def test_image_read_is_a_read(tmp_path: Any) -> None:
    """修复方 Read 了双端拼图 MainActivity.jpeg(#4431),结果是图片没有正文,收集器整条丢掉:时间线里只剩裸 Read,
    「修复侧多看到的截图」就数不到。图片读记 via=image,不立版本,时间线带文件名。"""
    jpg = "/proj/spec/visual-verify/sbs/MainActivity.jpeg"
    main = [*_call("2026-01-01T00:00:00Z", "t1", "Read", {"file_path": jpg}, "",
                   toolUseResult={"type": "image", "file": {"base64": "x", "type": "image/jpeg"}}),
            *_call("2026-01-01T00:00:10Z", "t2", "Write", {"file_path": "/proj/entry/A.ets", "content": "a\n"},
                   "File created successfully at: /proj/entry/A.ets")]
    led = _ledger(tmp_path, main)
    act = led.agents[MAIN_ID].actions[0]
    assert [(r.op, r.path, r.ev.via) for r in act.files] == [("read", jpg, "image")]
    ag = atoms.agent_atom(led, MAIN_ID, None)
    assert [r["path"] for r in ag["reads"]] == [jpg]
    text = atoms_text.render_agent(led, MAIN_ID, None, root="/proj")
    assert "MainActivity.jpeg" in text and "图片" in text


def test_fix_chain_reports_reads_fixer_had_that_generator_lacked(tmp_path: Any) -> None:
    """Index.ets:修复方读了 button.d.ts(接口)和 build.gradle(配置)才敢定 Material 默认形态,生成方两样都没读;
    「修复侧多看到的」只列了单,漏掉真正解释修复方为什么更强的两类输入。读取集差集按类型分组摆到链行上。"""
    from migloop import filestory, service
    gen = [_rec("2026-01-01T00:00:00Z", "user", "转换 A"),
           *_read_call("2026-01-01T00:00:10Z", "g1", "/proj/android/A.kt", "class A\n"),
           *_call("2026-01-01T00:00:20Z", "g2", "Write", {"file_path": "/proj/entry/A.ets", "content": "a\n"},
                  "File created successfully at: /proj/entry/A.ets")]
    fix = [_rec("2026-01-01T02:00:00Z", "user", "修 A"),
           *_read_call("2026-01-01T02:00:05Z", "f1", "/proj/spec/fix/round-1/ui/ALIGN_A.md", "fix\n"),
           *_read_call("2026-01-01T02:00:10Z", "f2", "/sdk/api/@internal/component/ets/button.d.ts", "declare\n"),
           *_read_call("2026-01-01T02:00:15Z", "f3", "/proj/android/app/build.gradle", "material 1.4\n"),
           *_read_call("2026-01-01T02:00:18Z", "f4", "/proj/android/A.kt", "class A\n"),
           *_call("2026-01-01T02:00:20Z", "f5", "Write", {"file_path": "/proj/entry/A.ets", "content": "b\n"}, "ok")]
    main = [*_call("2026-01-01T00:00:00Z", "m1", "Agent", {"name": "conv-a", "prompt": "转换 A"}, "done",
                   toolUseResult={"agentId": "g"}),
            *_call("2026-01-01T02:00:00Z", "m2", "Agent", {"name": "fixer", "prompt": "修 A"}, "done",
                   toolUseResult={"agentId": "f"})]
    led = _ledger(tmp_path, main, {"agent-g": gen, "agent-f": fix})
    chains = filestory.build_fix_chains(led.stories, {}, {}, root="/proj", fix_after="2026-01-01T01:00:00Z")
    service.attach_fix_basis(chains, led)
    gap = chains[0]["fixers_all"][0]["read_gap"]
    assert gap == {"接口": ["/sdk/api/@internal/component/ets/button.d.ts"],
                   "配置": ["/proj/android/app/build.gradle"],
                   "单/文档": ["/proj/spec/fix/round-1/ui/ALIGN_A.md"]}, gap
    text = atoms_text.render_chains({"chains": chains, "cross": None, "t0": led.t0, "touched": []}, root="/proj")
    assert "修复方读了而生成方没读: 接口 button.d.ts · 配置 build.gradle · 单/文档 ALIGN_A.md" in text


def test_agent_timeline_lists_skill_injection_once(tmp_path: Any) -> None:
    """注入一份技能在时间线里出现两次(「注入技能」行 + 「读 SKILL.md · 注入」行),12 份就是 24 行噪声。只留注入行。"""
    main = [_rec("2026-01-01T00:00:00Z", "user",
                 "<command-message>arkts-x</command-message>\n<command-name>arkts-x</command-name>\n"
                 "<skill-format>true</skill-format>Base rules…"),
            *_call("2026-01-01T00:00:10Z", "t1", "Write", {"file_path": "/proj/entry/A.ets", "content": "a\n"},
                   "File created successfully at: /proj/entry/A.ets")]
    led = _ledger(tmp_path, main)
    text = atoms_text.render_agent(led, MAIN_ID, None, root="/proj")
    assert text.count("arkts-x") == 1 and "读 " not in text.split("## 逐版时间线")[1].split("注入技能")[0]
    assert "SKILL.md" not in text


# ═══════════════ 子代理亲手追 DiceRoller app.json5 撞出的四条 ═══════════════

def test_fix_basis_writer_is_the_writer_of_the_version_the_fixer_read(tmp_path: Any) -> None:
    """decision-ledger.md 修复方读的是 v1(主会话·81e0a463 写),链行却说「← 主会话·1d2ef418 写」—— 那是修复之后 39 分钟
    才写的 v2。写者按读到的那一版取。"""
    from migloop import filestory, service
    doc = "/proj/spec/decision-ledger.md"
    w1 = [*_call("2026-01-01T00:30:00Z", "w1", "Write", {"file_path": doc, "content": "D-003 skip icon\n"},
                 f"File created successfully at: {doc}")]
    w2 = [*_call("2026-01-01T03:00:00Z", "w2", "Write", {"file_path": doc, "content": "D-003 skip icon\nD-010\n"}, "ok")]
    main = [*_call("2026-01-01T00:00:00Z", "t1", "Write", {"file_path": "/proj/entry/A.ets", "content": "a\n"},
                   "File created successfully at: /proj/entry/A.ets"),
            *_call("2026-01-01T00:29:00Z", "m1", "Agent", {"name": "ledger-writer", "prompt": "写 ledger"}, "done",
                   toolUseResult={"agentId": "w1"}),
            *_read_call("2026-01-01T02:00:00Z", "t2", doc, "D-003 skip icon\n"),
            *_call("2026-01-01T02:00:10Z", "t3", "Write", {"file_path": "/proj/entry/A.ets", "content": "b\n"}, "ok"),
            *_call("2026-01-01T02:59:00Z", "m2", "Agent", {"name": "ledger-later", "prompt": "补 ledger"}, "done",
                   toolUseResult={"agentId": "w2"})]
    led = _ledger(tmp_path, main, {"agent-w1": w1, "agent-w2": w2})
    chains = filestory.build_fix_chains(led.stories, {}, {}, root="/proj", fix_after="2026-01-01T01:00:00Z")
    service.attach_fix_basis(chains, led)
    b = chains[0]["fixers_all"][0]["basis"][0]
    assert b["v"] == 1 and b["writer"] == "agent-w1", b
    text = atoms_text.render_chains({"chains": chains, "cross": None, "t0": led.t0, "touched": []}, root="/proj")
    assert "依据单的来历: spec/decision-ledger.md@v1 ← ledger-writer 写" in text and "ledger-later" not in text


def test_agent_result_points_at_parent_dispatch_action(tmp_path: Any) -> None:
    """fix-identity 的收尾摘要标「截断,共 4249 字 (#1001)」,按它展开得到的是一句 162 字的 say:收尾全文在父会话那条
    派发调用的结果里。坐标要指向父的派发动作。"""
    child = [_rec("2026-01-01T00:00:00Z", "user", "修 A"),
             *_call("2026-01-01T00:00:10Z", "c1", "Write", {"file_path": "/proj/entry/A.ets", "content": "a\n"},
                    "File created successfully at: /proj/entry/A.ets"),
             _rec("2026-01-01T00:00:20Z", "assistant", [{"type": "text", "text": "done."}])]
    main = [*_call("2026-01-01T00:00:00Z", "m1", "Agent", {"name": "fixer", "prompt": "修 A"},
                   "## 收尾汇报\n" + "vendor 取 diceroller,依据 …" * 40, toolUseResult={"agentId": "c"})]
    led = _ledger(tmp_path, main, {"agent-c": child})
    seq = next(a.seq for a in led.agents[MAIN_ID].actions if a.kind == "dispatch")
    text = atoms_text.render_agent(led, "agent-c", None, root="/proj")
    assert f"action({MAIN_ID}, {seq})" in text and "收尾输出" in text


def test_agent_timeline_collapses_many_skill_injections(tmp_path: Any) -> None:
    """一个 agent 被灌 17 份技能,时间线里 17 行「注入技能」;与本链有关的只有 1 份。超过三份折成一行点名。"""
    main = [_rec(f"2026-01-01T00:00:0{i}Z", "user",
                 f"<command-message>sk{i}</command-message>\n<command-name>sk{i}</command-name>\n"
                 "<skill-format>true</skill-format>rules…") for i in range(5)]
    main += _call("2026-01-01T00:01:00Z", "t1", "Write", {"file_path": "/proj/entry/A.ets", "content": "a\n"},
                  "File created successfully at: /proj/entry/A.ets")
    led = _ledger(tmp_path, main)
    text = atoms_text.render_agent(led, MAIN_ID, None, root="/proj")
    assert "注入技能 5 份: sk0, sk1, sk2, sk3, sk4" in text and text.count("注入技能") == 1


# ═══════════════ 子代理亲手追 0723 PreferenceKeys / WXEntryAbility 撞出的 ═══════════════

def test_file_diff_only_shows_the_anchor_version(tmp_path: Any) -> None:
    """PreferenceKeys.ets@v2 只加了 9 行,file(v=2, diff=1) 却先倒出 v1 的 320 行创建 diff,目标版被截掉,2.3 万字零信息。
    diff=1 只给第 v 版的 diff;创建版且 content=1 时不再把全文打两遍。"""
    big = "".join(f"line{i}\n" for i in range(300))
    main = [*_call("2026-01-01T00:00:00Z", "t1", "Write", {"file_path": "/proj/entry/A.ets", "content": big},
                   "File created successfully at: /proj/entry/A.ets"),
            *_call("2026-01-01T00:00:10Z", "t2", "Edit", {"file_path": "/proj/entry/A.ets", "old_string": "line299\n",
                                                          "new_string": "line299\nNEWKEY\n"}, "ok")]
    led = _ledger(tmp_path, main)
    text = atoms_text.render_file(led, "A.ets", 2, root="/proj", diff=True)
    assert "+NEWKEY" in text and "+line150" not in text and "diff(path, v)" in text
    creation = atoms_text.render_file(led, "A.ets", 1, root="/proj", diff=True, content=True)
    assert creation.count("line150") == 1


def test_fix_basis_prefers_docs_about_the_file(tmp_path: Any) -> None:
    """WXEntryAbility.ets:修复方同一窗口里读了 4 张 MineFragment 的 ALIGN 单和 1 张 WXCallbackActivity_01 单,链行列的是前四张,
    真正的依据不在列表里 —— 照它走会追进错误分支。单名含文件词干、或单的内容提到该文件的排前,其余只计数。"""
    from migloop import filestory, service
    other = "/proj/spec/fix/round-1/ui/ALIGN_PMineFragment_layout.md"
    mine = "/proj/spec/fix/round-1/feat/WXCallbackActivity_01_no_wxentry.md"
    main = [*_call("2026-01-01T00:00:00Z", "t0", "Write", {"file_path": "/proj/entry/B.ets", "content": "b\n"},
                   "File created successfully at: /proj/entry/B.ets"),
            *_read_call("2026-01-01T02:00:00Z", "t1", other, "MineFragment 指示器颜色\n"),
            *_read_call("2026-01-01T02:00:05Z", "t2", mine, "缺 WXEntryAbility.ets:回调 Ability 未建\n"),
            *_call("2026-01-01T02:00:10Z", "t3", "Write", {"file_path": "/proj/entry/wxapi/WXEntryAbility.ets",
                                                          "content": "export default class WXEntryAbility {}\n"},
                   "File created successfully at: /proj/entry/wxapi/WXEntryAbility.ets")]
    led = _ledger(tmp_path, main)
    chains = filestory.build_fix_chains(led.stories, {}, {}, root="/proj", fix_after="2026-01-01T01:00:00Z")
    service.attach_fix_basis(chains, led)
    c = next(c for c in chains if c["file"] == "WXEntryAbility.ets")
    ff = c["fixers_all"][0]
    assert [b["path"] for b in ff["basis"]] == [mine] and ff["basis_other"] == 1
    text = atoms_text.render_chains({"chains": chains, "cross": None, "t0": led.t0, "touched": []}, root="/proj")
    assert "WXCallbackActivity_01_no_wxentry.md" in text and "另 1 张单与本文件无关" in text


def test_index_marks_versions_with_unknown_content(tmp_path: Any) -> None:
    main = [*_call("2026-01-01T00:00:00Z", "t1", "Bash", {"command": "python gen.py > /proj/entry/F.ets"}, "")]
    led = _ledger(tmp_path, main)
    text = atoms_text.render_index(led, "ets", "F.ets", root="/proj")
    assert "1 版内容未知" in text


def test_guide_carries_the_hands_on_lessons() -> None:
    from migloop import mcp_server
    g = mcp_server.GUIDE
    assert "search(q, agent=主会话" in g and "blame(path, v, start=行号, n=1)" in g
    assert "offset=" in g and "find=" in g and "created 链先问三件事" in g
    assert "传递 / 错 / 缺" in g and "故障进入点" in g


# ═══════════════ 真会话复核后的四条 ═══════════════

def test_image_read_without_sidecar_is_still_a_read(tmp_path: Any) -> None:
    """DiceRoller #4431 Read MainActivity.jpeg:CC 转录里这条没有 toolUseResult 边车,结果正文也是空 —— 只剩扩展名可认。"""
    jpg = "/proj/spec/visual-verify/sbs/MainActivity.jpeg"
    main = [*_call("2026-01-01T00:00:00Z", "t1", "Read", {"file_path": jpg}, "")]
    led = _ledger(tmp_path, main)
    act = led.agents[MAIN_ID].actions[0]
    assert [(r.op, r.path, r.ev.via) for r in act.files] == [("read", jpg, "image")]


def test_chain_generator_is_an_agent_even_when_replaced_lines_are_external(tmp_path: Any) -> None:
    """app.json5:v1 外部输入(模板默认值,内容首见于 Read)、v2 app-identity 改版本号、v3 修复改 bundleName。
    被修的 3 行来自 v1,blame 归到外部输入是对的;但链的「生成方」要是 app-identity(生成期真写过它的 agent),
    「原作者」里外部来源写成人话。"""
    from migloop import filestory
    f = "/proj/AppScope/app.json5"
    main = [*_read_call("2026-01-01T00:00:00Z", "r1", f, "bundleName: com.example.app\nversion: 1.0.0\n"),
            *_call("2026-01-01T00:00:10Z", "e1", "Edit", {"file_path": f, "old_string": "1.0.0", "new_string": "1.0"}, "ok"),
            *_call("2026-01-01T02:00:00Z", "e2", "Edit", {"file_path": f, "old_string": "com.example.app",
                                                          "new_string": "com.example.dice"}, "ok")]
    led = _ledger(tmp_path, main)
    chains = filestory.build_fix_chains(led.stories, {}, {}, root="/proj", fix_after="2026-01-01T01:00:00Z")
    c = chains[0]
    assert c["generator"]["id"] == MAIN_ID
    assert c["lines"]["from"][0]["id"] == filestory.EXTERNAL and "外部输入" in c["lines"]["from"][0]["desc"]
    text = atoms_text.render_chains({"chains": chains, "cross": None, "t0": led.t0, "touched": []}, root="/proj")
    assert "原作者 外部输入(模板/脚手架默认值)(1行" in text and "生成方 __external__" not in text


def test_action_find_works_on_thinking_text(tmp_path: Any) -> None:
    """think #4218 的 9.8 万字在 action 的「输入」里,输出为空;find=AC14 报「未命中」是找错了侧。"""
    body = "x" * 3000 + "DECISION keep Roll" + "y" * 3000
    main = [_rec("2026-01-01T00:00:00Z", "assistant", [{"type": "thinking", "thinking": body}])]
    led = _ledger(tmp_path, main)
    seq = led.agents[MAIN_ID].actions[0].seq
    text = atoms_text.render_action(led, MAIN_ID, seq, max_chars=500, find="decision")   # 不分大小写,和 search 一样
    assert "DECISION keep Roll" in text and "未命中" not in text and "offset=" in text


def test_read_gap_render_dedups_basenames_and_flags_mixed_window() -> None:
    chains = [{"kind": "rework", "file": "A.ets", "file_abs": "/p/A.ets", "gen_at": None, "fix_at": None,
               "generator": {"id": "g", "desc": "g"}, "generators": [], "fixer": {"id": "f", "desc": "f"},
               "fixers_all": [{"id": "f", "desc": "f", "vers": [1], "fvers": [2], "at": "2026-01-01T00:00:00Z",
                               "basis": [], "basis_other": 2,
                               "read_gap": {"鸿蒙源码": ["/p/a/X.ets", "/p/b/X.ets", "/p/c/X.ets"]}}],
               "lines": None, "blame_broken": None, "fix_versions": [2], "breaks": [], "diff": []}]
    text = atoms_text.render_chains({"chains": chains, "cross": None, "t0": None, "touched": []}, root="/p")
    assert "鸿蒙源码 X.ets ×3" in text and "窗口内混有别的文件的读" in text


# ═══════════════ python heredoc 的规整读改写不是黑盒 ═══════════════

_PY_REPLACE = ("python3 - <<'PYEOF'\n"
               "p='/proj/entry/A.ets'\n"
               "s=open(p).read()\n"
               "old = \"\"\"a\n\"\"\"\n"
               "new = \"\"\"b\n\"\"\"\n"
               "assert old in s\n"
               "s=s.replace(old,new,1)\n"
               "open(p,'w').write(s)\n"
               "print('ok')\n"
               "PYEOF")


def test_python_heredoc_replace_is_an_edit(tmp_path: Any) -> None:
    """0723 fixer-r1 改 MemberCenterPage.ets 全是 python heredoc 的 s.replace(old, new):账本记「脚本黑盒」不立版本,
    链的修复方成了后面只放宽 private 的 build-verify-r1,故障进入点落错。规整的读改写要解成 edit。"""
    main = [*_call("2026-01-01T00:00:00Z", "t1", "Write", {"file_path": "/proj/entry/A.ets", "content": "a\nc\n"},
                   "File created successfully at: /proj/entry/A.ets"),
            *_call("2026-01-01T00:00:10Z", "t2", "Bash", {"command": _PY_REPLACE}, "ok")]
    led = _ledger(tmp_path, main)
    act = led.agents[MAIN_ID].actions[1]
    assert [(r.ev.kind, r.ev.via) for r in act.files if r.op != "read"] == [("edit", "script")]
    st = led.stories["/proj/entry/A.ets"]
    assert len(st.versions) == 2 and st.versions[1].content == "b\nc\n" and st.versions[1].by == MAIN_ID
    assert not act.detail.get("unresolved") and not act.detail.get("touched")


def test_python_heredoc_literal_write_is_a_full_write(tmp_path: Any) -> None:
    """vv 代理用 python 把缺陷单正文写成文件(open(p,'w').write(\"\"\"…\"\"\") / with open … as f),账本记外部输入、内容未知。"""
    cmd1 = ("python3 - <<'EOF'\nopen('/proj/spec/fix/x.md','w').write(\"\"\"# x\nbody\n\"\"\")\nEOF")
    cmd2 = ("python3 - <<'EOF'\nfrom pathlib import Path\ntext = '# y\\n'\nPath('/proj/spec/fix/y.md').write_text(text)\nEOF")
    cmd3 = ("python3 - <<'EOF'\np = '/proj/spec/fix/z.md'\nwith open(p, 'w') as f:\n    f.write('# z\\n')\nEOF")
    main = [*_call("2026-01-01T00:00:00Z", "t1", "Bash", {"command": cmd1}, ""),
            *_call("2026-01-01T00:00:10Z", "t2", "Bash", {"command": cmd2}, ""),
            *_call("2026-01-01T00:00:20Z", "t3", "Bash", {"command": cmd3}, "")]
    led = _ledger(tmp_path, main)
    for path, body in (("/proj/spec/fix/x.md", "# x\nbody\n"), ("/proj/spec/fix/y.md", "# y\n"), ("/proj/spec/fix/z.md", "# z\n")):
        st = led.stories[path]
        assert st.versions[0].by == MAIN_ID and st.versions[0].content == body, (path, st.versions[0])


def test_python_script_with_loops_stays_a_black_box(tmp_path: Any) -> None:
    """解不出来的(循环写多个文件、正则替换)照旧当黑盒 + 碰过,不猜。"""
    cmd = ("python3 - <<'EOF'\nimport re\np='/proj/entry/A.ets'\ns=open(p).read()\ns=re.sub(r'x+','y',s)\nopen(p,'w').write(s)\nEOF")
    main = [*_call("2026-01-01T00:00:00Z", "t1", "Write", {"file_path": "/proj/entry/A.ets", "content": "xx\n"},
                   "File created successfully at: /proj/entry/A.ets"),
            *_call("2026-01-01T00:00:10Z", "t2", "Bash", {"command": cmd}, "")]
    led = _ledger(tmp_path, main)
    act = led.agents[MAIN_ID].actions[1]
    writes = [r for r in act.files if r.op != "read"]
    assert [(r.op, r.ev.content) for r in writes] == [("write", None)]      # 写了、内容未知:盲写不是黑盒
    st = led.stories["/proj/entry/A.ets"]
    assert len(st.versions) == 2 and st.versions[1].content is None


def test_python_write_replace_inline_is_an_edit_and_unchanged_writeback_is_not_a_version(tmp_path: Any) -> None:
    script = ("cd /proj && python3 - <<'PYEOF'\np='entry/F.ets'\ns=open(p).read()\nopen(p,'w').write(s.replace('a','b'))\n"
              "q='entry/New.ets'\nt=open(q).read()\nopen(q,'w').write(t)\nPYEOF")
    main = [*_call("2026-01-01T00:00:00Z", "t0", "Write", {"file_path": "/proj/entry/F.ets", "content": "a\n"},
                   "File created successfully at: /proj/entry/F.ets"),
            *_call("2026-01-01T00:00:10Z", "t1", "Bash", {"command": script}, out="ok")]
    led = _ledger(tmp_path, main)
    bash = next(a for a in led.agents[MAIN_ID].actions if a.tool == "Bash")
    assert [(r.ev.kind, r.path.rsplit("/", 1)[-1]) for r in bash.files] == [("read", "F.ets"), ("edit", "F.ets"), ("read", "New.ets")]
    assert not bash.detail.get("unresolved")
    assert led.stories["/proj/entry/F.ets"].versions[-1].content == "b\n"
    assert not led.stories["/proj/entry/New.ets"].versions or led.stories["/proj/entry/New.ets"].versions[0].source == "external"


# ═══════════════ 零命中必须带范围;全池只允许带时间上限 ═══════════════

def test_pool_search_is_time_bounded_and_states_scope(tmp_path: Any) -> None:
    """SplashPage:工具组只在 conv-splash 的记录里搜 windowFullscreen,零命中就写成「生成期各输入里零命中」;
    实际 AIPPT_design.md@v1:471 和主会话读 themes.xml 都在池里。全池查要带时间上限,结果自带范围。"""
    w1 = [*_call("2026-01-01T00:30:00Z", "w1", "Write", {"file_path": "/proj/spec/ref/AIPPT_design.md",
                                                        "content": "# design\nwindowFullscreen = true\n"},
                 "File created successfully at: /proj/spec/ref/AIPPT_design.md")]
    main = [*_read_call("2026-01-01T00:20:00Z", "t1", "/proj/android/values/themes.xml",
                        "<item name=\"android:windowFullscreen\">true</item>\n"),
            *_call("2026-01-01T00:29:00Z", "m1", "Agent", {"name": "ref-doc", "prompt": "分析设计稿"}, "done",
                   toolUseResult={"agentId": "w1"}),
            *_call("2026-01-01T02:00:00Z", "t2", "Bash", {"command": "python3 - <<'EOF'\nopen('/proj/entry/B.ets','w').write(str(1))\nEOF"}, "")]
    led = _ledger(tmp_path, main, {"agent-w1": w1})
    res = atoms.search_pool(led, "windowFullscreen", until_ts="2026-01-01T01:00:00Z")
    # 安卓源码(外部输入)的已知内容也在池里 —— 「生成期没人见过」要连它一起否
    assert {(r["path"], r["v"], r["by"]) for r in res["files"]} == {("/proj/spec/ref/AIPPT_design.md", 1, "agent-w1"),
                                                                     ("/proj/android/values/themes.xml", 1, "__external__")}
    # 写者的 Write 输入里也有这个词:它也算「见过」
    assert [a["agent"] for a in res["agents"]] == [MAIN_ID, "agent-w1"] and res["agents"][0]["n"] == 1
    text = atoms_text.render_search(led, "windowFullscreen", until_ts="2026-01-01T01:00:00Z", root="/proj")
    assert "全池" in text and "范围:" in text and "AIPPT_design.md@v1" in text and "themes.xml" in text
    early = atoms_text.render_search(led, "windowFullscreen", until_ts="2026-01-01T00:10:00Z", root="/proj")
    assert "零命中" in early and "范围:" in early
    late = atoms.search_pool(led, "windowFullscreen", until_ts="2026-01-01T03:00:00Z")
    assert late["unknown_versions"] == 1                     # B.ets 那版内容未知:范围行要说出来
    assert "只允许带时间上限" in atoms_text.render_search(led, "windowFullscreen", root="/proj")


def test_agent_and_file_search_state_their_scope(tmp_path: Any) -> None:
    main = [*_call("2026-01-01T00:00:00Z", "t1", "Write", {"file_path": "/proj/entry/A.ets", "content": "a\n"},
                   "File created successfully at: /proj/entry/A.ets"),
            *_call("2026-01-01T00:00:10Z", "t2", "Bash", {"command": "python3 - <<'EOF'\nopen('/proj/entry/A.ets','w').write(str(1))\nEOF"}, "")]
    led = _ledger(tmp_path, main)
    ag = atoms_text.render_search(led, "zzz", agent=MAIN_ID, root="/proj")
    assert "范围: 只有这个 agent" in ag and "until_ts" in ag
    fl = atoms_text.render_search(led, "zzz", file="A.ets", root="/proj")
    assert "内容未知 1 版查不了" in fl and "范围:" in fl


# ═══════════════ 上游最长链:建账时 DP 预存 ═══════════════

def test_upstream_depth_counts_every_agent_file_transition(tmp_path: Any) -> None:
    """spec.md(池外)→ conv 读 → 写 A.ets@v1 → fixer 读 → 写 A.ets@v2:四次转换,A.ets@v2 上游 4 跳;
    派发也算一跳(conv 由主会话派发,主会话没读过东西,派发边不加长)。"""
    from migloop import filestory, service
    conv = [_rec("2026-01-01T00:00:00Z", "user", "转换 A"),
            *_read_call("2026-01-01T00:00:10Z", "c1", "/proj/spec/pages/A.md", "spec\n"),
            *_call("2026-01-01T00:00:20Z", "c2", "Write", {"file_path": "/proj/entry/A.ets", "content": "a\n"},
                   "File created successfully at: /proj/entry/A.ets")]
    fix = [_rec("2026-01-01T02:00:00Z", "user", "修 A"),
           *_read_call("2026-01-01T02:00:10Z", "f1", "/proj/entry/A.ets", "a\n"),
           *_call("2026-01-01T02:00:20Z", "f2", "Write", {"file_path": "/proj/entry/A.ets", "content": "b\n"}, "ok")]
    main = [*_call("2026-01-01T00:00:00Z", "m1", "Agent", {"name": "conv-a", "prompt": "转换 A"}, "done",
                   toolUseResult={"agentId": "c"}),
            *_call("2026-01-01T02:00:00Z", "m2", "Agent", {"name": "fixer", "prompt": "修 A"}, "done",
                   toolUseResult={"agentId": "f"})]
    led = _ledger(tmp_path, main, {"agent-c": conv, "agent-f": fix})
    assert led.depth_max[("f", "/proj/spec/pages/A.md", 1)] == 0
    assert led.depth_max[("a", "agent-c", 1)] == 1 and led.depth_max[("f", "/proj/entry/A.ets", 1)] == 2
    assert led.depth_max[("a", "agent-f", 1)] == 3 and led.depth_max[("f", "/proj/entry/A.ets", 2)] == 4
    assert led.depth_win[("f", "/proj/entry/A.ets", 2)] == 4
    assert "上游 4/4 跳" in atoms_text.render_file(led, "A.ets", 2, root="/proj")
    assert "上游 3/3 跳" in atoms_text.render_agent(led, "agent-f", 1, root="/proj")
    assert "上游 4/4 跳" in atoms_text.render_index(led, "ets", "A.ets", root="/proj")
    chains = filestory.build_fix_chains(led.stories, {}, {}, root="/proj", fix_after="2026-01-01T01:00:00Z")
    service.attach_fix_basis(chains, led)
    text = atoms_text.render_chains({"chains": chains, "cross": None, "t0": led.t0, "touched": []}, root="/proj")
    assert "上游 4/4 跳" in text


def test_upstream_depth_window_vs_cumulative(tmp_path: Any) -> None:
    """主会话 v1 读了 spec、v2 才写 A.ets:累计口径把 v1 的读也算进 v2(上下文是累积的),窗口口径只算 v1 之后读的。"""
    main = [*_read_call("2026-01-01T00:00:00Z", "t1", "/proj/spec/pages/A.md", "spec\n"),
            *_call("2026-01-01T00:00:10Z", "t2", "Write", {"file_path": "/proj/entry/B.ets", "content": "b\n"},
                   "File created successfully at: /proj/entry/B.ets"),
            *_call("2026-01-01T00:00:20Z", "t3", "Write", {"file_path": "/proj/entry/A.ets", "content": "a\n"},
                   "File created successfully at: /proj/entry/A.ets")]
    led = _ledger(tmp_path, main)
    assert led.depth_max[("f", "/proj/entry/A.ets", 1)] == 2 and led.depth_win[("f", "/proj/entry/A.ets", 1)] == 1


# ═══════════════ 循环 + echo 分隔的多文件读:stdout 切给各文件 ═══════════════

def test_loop_with_echo_separator_attaches_sections_as_seen_lines(tmp_path: Any) -> None:
    """0723 fixer-r1 #25708 用 for 循环 + echo 分隔读四张缺陷单,账本只记「范围未知」;开屏状态栏那张点名了 EntryAbility.ets,
    工具组据此写成「该文件没进修复轮」。分隔行能对上就把每段挂到对应的读上(行号未知)。"""
    cmd = ("cd /proj/spec && for f in a.md b.md; do echo \"══ $f\"; sed -n '/^## 2/,/^## 4/p' \"$f\" | head -5; done")
    out = "══ a.md\n## 2. 期望\nEntryAbility.ets:unknown 未调用 setWindowSystemBarEnable\n══ b.md\n## 2. 期望\n无\n"
    main = [*_call("2026-01-01T00:00:00Z", "t1", "Bash", {"command": cmd}, out)]
    led = _ledger(tmp_path, main)
    act = led.agents[MAIN_ID].actions[0]
    seen = {r.path.rsplit("/", 1)[-1]: r.ev.seen for r in act.files if r.op == "read"}
    assert seen["a.md"] == ((0, "## 2. 期望"), (0, "EntryAbility.ets:unknown 未调用 setWindowSystemBarEnable"))
    assert seen["b.md"] == ((0, "## 2. 期望"), (0, "无"))
    res = atoms.search_file(led, "a.md", "EntryAbility")
    assert res and res["readers"] and res["readers"][0]["n"] == 1
    text = atoms_text.render_search(led, "EntryAbility", file="a.md", root="/proj")
    assert "读者的读结果里命中过" in text and "行号未知" in text and "第 0 行" not in text
    agent_txt = atoms_text.render_agent(led, MAIN_ID, None, root="/proj", seen=True)
    assert "看见 2 行,行号未知" in agent_txt


# ═══════════════ 脚本渲染出的文件:字面量正文记成「部分内容」 ═══════════════

_FILL = ("python3 - <<'PYEOF'\nfrom pathlib import Path\nUI = Path('spec/fix/round-1/ui')\n"
         "def fill(p, exp, act):\n    t = p.read_text()\n    p.write_text(t.replace('<<EXP>>', exp).replace('<<ACT>>', act))\n"
         "fill(UI/'ALIGN_PSplashActivity_extra_element_status-bar.md',\n"
         "     exp=\"\"\"安卓开屏页顶部没有状态栏,全屏沉浸(themes.xml windowFullscreen=true)\"\"\",\n"
         "     act=\"\"\"鸿蒙开屏页顶部多一条灰带;源码缺口 entry/src/main/ets/entryability/EntryAbility.ets:unknown 未调用 setWindowSystemBarEnable\"\"\")\n"
         "print('filled')\nPYEOF")


def test_script_literal_body_becomes_partial_content_and_writer(tmp_path: Any) -> None:
    """vv-t1-A01 #26723 的 fill(UI/'ALIGN_….md', exp=…, act=…) 把缺陷单正文当参数传给渲染器;文件由渲染器写出,
    账本记「外部输入、内容无法复原」,工具组据此判「缺」。字面量正文要记成该文件首版的部分内容,写者是跑脚本的 agent。"""
    doc = "/proj/spec/fix/round-1/ui/ALIGN_PSplashActivity_extra_element_status-bar.md"
    vv = [_rec("2026-01-01T00:00:00Z", "user", "写单"),
          *_call("2026-01-01T00:00:10Z", "v1", "Bash", {"command": _FILL}, "filled")]
    main = [*_call("2026-01-01T00:00:00Z", "m1", "Agent", {"name": "vv-1", "prompt": "写单"}, "done",
                   toolUseResult={"agentId": "v1"}),
            *_call("2026-01-01T01:00:00Z", "t1", "Bash", {"command": f"sed -n '1,3p' {doc}"}, "# ALIGN\n## 2. 期望\n")]
    led = _ledger(tmp_path, main, {"agent-v1": vv})
    act = led.agents["agent-v1"].actions[1]
    assert act.detail["partials"][0][0] == "ALIGN_PSplashActivity_extra_element_status-bar.md"
    st = led.stories[doc]
    v0 = st.versions[0]
    assert v0.source == "generated" and v0.by == "agent-v1" and v0.content is None
    assert v0.partial and "EntryAbility.ets:unknown" in v0.partial
    res = atoms.search_file(led, doc, "EntryAbility")
    assert res and res["first"] == 1 and res["versions"][0]["partial"]
    text = atoms_text.render_file(led, doc, 1, root="/proj", content=True)
    assert "部分已知" in text and "EntryAbility.ets:unknown" in text
    assert "内容未知" not in text and "同批 0" not in text
    pool = atoms.search_pool(led, "setWindowSystemBarEnable", until_ts="2026-01-01T02:00:00Z")
    assert [r["path"] for r in pool["files"]] == [doc]


def test_partial_literals_survive_a_failed_command(tmp_path: Any) -> None:
    """vv-t1-A01 #26723:落盘 fill.py 的 heredoc 与首次运行合在一条命令里,运行报错被标 is_error,下一条修好脚本再跑成功。
    字面量正文是它写下的话,与命令成败无关。"""
    doc = "/proj/spec/fix/round-1/ui/ALIGN_PSplashActivity_extra_element_status-bar.md"
    vv = [_rec("2026-01-01T00:00:00Z", "user", "写单"),
          *_call("2026-01-01T00:00:10Z", "v1", "Bash", {"command": _FILL}, "Exit code 1\nTraceback …", is_error=True),
          *_call("2026-01-01T00:00:20Z", "v2", "Bash", {"command": "python3 fill.py"}, "filled")]
    main = [*_call("2026-01-01T00:00:00Z", "m1", "Agent", {"name": "vv-1", "prompt": "写单"}, "done",
                   toolUseResult={"agentId": "v1"}),
            *_call("2026-01-01T01:00:00Z", "t1", "Bash", {"command": f"sed -n '1,3p' {doc}"}, "# ALIGN\n")]
    led = _ledger(tmp_path, main, {"agent-v1": vv})
    v0 = led.stories[doc].versions[0]
    assert v0.by == "agent-v1" and v0.partial and "EntryAbility.ets:unknown" in v0.partial


def test_guide_tells_how_to_check_fix_round_mentions_of_untouched_files() -> None:
    from migloop import mcp_server
    assert "search(q=文件名, since_ts=修复开始" in mcp_server.GUIDE
