"""证据层回归集(2026-09-08 评审):不让推断越级成为事实。

每条测试对应评审给出的一个反例。验收:解析能力升级后旧事件 id 不变;候选不会升级成作者;写之后才返回的内容不进写之前的
输入;截断、未解析、未完成、条件分支都有计数或标记;每个引用能定位到正确原文,伪造行号失败。
"""

from __future__ import annotations

from typing import Any

from migloop import atoms, atoms_text, filestory, service

from tests.test_atoms import MAIN_ID, SID, _call, _ledger, _read_call, _rec, _res, _use

A = "/proj/entry/A.ets"


def at(hms: str) -> str:
    return f"2026-01-01T{hms}Z"


# ═══════════════ ④ 封口状态机 ═══════════════

def test_snapshot_after_blind_edit_seals_latest_unknown_version(tmp_path: Any) -> None:
    """Write a → 不透明写(cp 源未知)→ Edit b→c(状态未知时的盲写)→ Read 得 c。
    快照只证明「这个观测点文件是 c」,该封在最后一次未知写(v3)上;v2 仍未知;读绑 v3。
    原来封到了 v2,v3 留白,读却绑 v3 且 certain —— 内容和归属都错。"""
    main = [
        *_call(at("00:00:00"), "t1", "Write", {"file_path": A, "content": "a\n"}),
        *_call(at("00:00:10"), "t2", "Bash", {"command": f"cp /tmp/x.ets {A}"}),
        *_call(at("00:00:20"), "t3", "Edit", {"file_path": A, "old_string": "b", "new_string": "c"}),
        *_read_call(at("00:00:30"), "t4", A, "c\n"),
    ]
    led = _ledger(tmp_path, main)
    st = led.stories[A]
    assert [v.content for v in st.versions] == ["a\n", None, "c\n"]
    assert st.versions[2].sealed and not st.versions[1].sealed
    assert st.reads[-1].version == 3 and st.reads[-1].certain


# ═══════════════ ③ 时间边界:读取完成时刻 ═══════════════

def test_read_completed_after_a_write_is_not_that_writes_input(tmp_path: Any) -> None:
    """00:00 发起 Read,00:10 Write,00:20 Read 才返回:返回的内容不可能是 00:10 那次写的依据。
    读喂的版本按完成时刻算,不按发起时刻。"""
    spec = "/proj/spec/s.md"
    recs = [
        _rec(at("00:00:00"), "assistant", [_use("r1", "Read", {"file_path": spec})]),
        _rec(at("00:00:10"), "assistant", [_use("w1", "Write", {"file_path": A, "content": "a\n"})]),
        _rec(at("00:00:11"), "user", [_res("w1", "ok")]),
        _rec(at("00:00:20"), "user", [_res("r1", "…")],
             toolUseResult={"type": "text", "file": {"filePath": spec, "content": "spec\n", "startLine": 1,
                                                     "numLines": 1, "totalLines": 1}}),
    ]
    led = _ledger(tmp_path, recs)
    acts = led.agents[MAIN_ID].actions
    rd = next(a for a in acts if a.tool == "Read")
    wr = next(a for a in acts if a.tool == "Write")
    assert wr.ver == 1
    assert rd.done_ts == at("00:00:20")
    assert rd.at == 2                                   # 喂 v2,不是 v1


# ═══════════════ ① 候选不升级成作者 ═══════════════

def test_directory_candidate_run_never_becomes_author(tmp_path: Any) -> None:
    """跑过一个可能输出到某目录的脚本,不能证明该目录下后来首见的文件是它生成的。候选保留在 gen_runs,作者仍是外部输入。"""
    main = [
        *_call(at("00:00:00"), "t1", "Bash", {"command": "cd /proj && python3 external.py --out-dir /proj/spec/out"},
               out="nothing changed"),
        *_read_call(at("00:10:00"), "t2", "/proj/spec/out/existing.md", "# old\n"),
    ]
    led = _ledger(tmp_path, main)
    v0 = led.stories["/proj/spec/out/existing.md"].versions[0]
    run = next(a for a in led.agents[MAIN_ID].actions if a.tool == "Bash")
    assert v0.source == "external" and v0.by == filestory.EXTERNAL and v0.by_ver is None
    assert v0.gen_runs == (run.seq,)                       # 候选保留,不升级
    text = atoms_text.render_file(led, "existing.md", None, root="/proj")
    assert "候选" in text and f"#{run.seq}" in text and "批量生成(脚本跑出来的" not in text


# ═══════════════ ② 稳定身份 ═══════════════

def test_event_identity_is_transcript_native(tmp_path: Any) -> None:
    """事件身份 = 会话 + 转录 + tool_use_id;解析器多认出一条读,动作号会变,身份不变。action 输出印出来。"""
    main = [*_call(at("00:00:00"), "w1", "Write", {"file_path": A, "content": "a\n"})]
    led = _ledger(tmp_path, main)
    wr = next(a for a in led.agents[MAIN_ID].actions if a.tool == "Write")
    eid = atoms.event_id(led, MAIN_ID, wr.seq)
    assert eid == f"{SID[:8]}:{SID}:w1"
    main2 = [*_read_call(at("00:00:00"), "r0", "/proj/spec/s.md", "x\n"), *main]
    led2 = _ledger(tmp_path / "b", main2)
    wr2 = next(a for a in led2.agents[MAIN_ID].actions if a.tool == "Write")
    assert wr2.seq != wr.seq and atoms.event_id(led2, MAIN_ID, wr2.seq) == eid
    assert f"事件 id {eid}" in atoms_text.render_action(led, MAIN_ID, wr.seq)


# ═══════════════ 证据分层 ═══════════════

def test_versions_carry_evidence_labels(tmp_path: Any) -> None:
    """每一版说清自己凭什么:工具写是「报告成功」,heredoc 是「推导」,cp 是「推导·黑盒写」,快照封口是「观测」。"""
    main = [
        *_call(at("00:00:00"), "t1", "Write", {"file_path": A, "content": "a\n"}),
        *_call(at("00:00:10"), "t2", "Bash", {"command": f"cat > {A} <<'EOF'\nb\nEOF"}),
        *_call(at("00:00:20"), "t3", "Bash", {"command": f"cp /tmp/x.ets {A}"}),
        *_read_call(at("00:00:30"), "t4", A, "c\n"),
    ]
    led = _ledger(tmp_path, main)
    text = atoms_text.render_file(led, "A.ets", None, root="/proj")
    lines = [ln for ln in text.splitlines() if ln.startswith("- v")]
    assert "工具写·报告成功" in lines[0]
    assert "推导·heredoc 全文" in lines[1]
    assert "推导·黑盒写" in lines[2] and "观测封口" in lines[2]      # cp 在收集层是黑盒写(源内容没进上下文)


# ═══════════════ ⑤ 失败 / 条件分支 ═══════════════

def test_failed_command_keeps_pointer_and_candidate(tmp_path: Any) -> None:
    """`printf x > A; exit 1` 实际写了文件,工具却报失败。失败不等于没改:不立版本,但指针保留、标「效应未知」,
    目标文件挂一条候选。"""
    main = [
        *_call(at("00:00:00"), "t1", "Write", {"file_path": A, "content": "a\n"}),
        *_call(at("00:00:10"), "t2", "Bash", {"command": f"printf x > {A}; exit 1"}, out="", is_error=True),
    ]
    led = _ledger(tmp_path, main)
    bash = next(a for a in led.agents[MAIN_ID].actions if a.tool == "Bash")
    assert bash.ok is False and bash.src is not None and bash.tuid == "t2"
    assert "失败" in str(bash.detail.get("unresolved"))
    st = led.stories[A]
    assert len(st.versions) == 1
    assert [(t.seq, t.reason) for t in st.touches] == [(bash.seq, bash.detail["unresolved"])]


def test_conditional_branch_write_is_flagged_not_asserted(tmp_path: Any) -> None:
    """`false && cp b A; true` 实际没执行 cp。&& / || 之后的操作标「条件分支,是否执行未知」;
    cd / mkdir / echo 这种几乎不失败的前件不算条件。"""
    main = [
        *_call(at("00:00:00"), "t1", "Write", {"file_path": A, "content": "a\n"}),
        *_call(at("00:00:10"), "t2", "Bash", {"command": f"false && cp /tmp/b.ets {A}; true"}, out=""),
    ]
    led = _ledger(tmp_path, main)
    st = led.stories[A]
    assert len(st.versions) == 2 and st.versions[1].conditional
    assert "条件分支" in atoms_text.render_file(led, "A.ets", None, root="/proj")
    main2 = [
        *_call(at("00:00:00"), "t1", "Write", {"file_path": A, "content": "a\n"}),
        *_call(at("00:00:10"), "t2", "Bash", {"command": "cd /proj && cp /tmp/b.ets entry/A.ets"}, out=""),
    ]
    led2 = _ledger(tmp_path / "b", main2)
    assert not led2.stories[A].versions[1].conditional


# ═══════════════ ⑥ 词法层完整性 ═══════════════

def test_lexical_layer_discloses_truncation_mention_only_files_and_unfinished_calls(tmp_path: Any) -> None:
    many = " ".join(f"/proj/x/f{i}.ets" for i in range(45))
    recs = [
        *_call(at("00:00:00"), "t0", "Write", {"file_path": A, "content": "a\n"}),
        *_call(at("00:00:10"), "t1", "Bash", {"command": f"ls {many}"}, out=""),
        *_call(at("00:00:20"), "t2", "Bash", {"command": "git log --oneline -- /proj/entry/Never.ets"}, out="abc"),
        _rec(at("00:00:30"), "assistant", [_use("t3", "Bash", {"command": f"sed -i 's/a/b/' {A}"})]),   # 没等到结果
    ]
    led = _ledger(tmp_path, recs)
    acts = led.agents[MAIN_ID].actions
    ls = next(a for a in acts if str(a.detail.get("cmd", "")).startswith("ls "))
    assert len(ls.detail["mentions"]) == 40 and ls.detail["mentions_truncated"] == 5
    # 只被提到、从没读写过的文件也有入口(目录已知才建,免得输出里的垃圾路径灌进目录)
    assert "/proj/entry/Never.ets" in led.stories and not led.stories["/proj/entry/Never.ets"].versions
    idx = atoms_text.render_index(led, "ets", None, root="/proj")
    assert "Never.ets" in idx and "只被提到" in idx
    # 未完成的调用:指针、tool_use_id、提及都保留,标 unfinished
    pend = next(a for a in acts if a.tool == "Bash" and a.ok is None)
    assert pend.src is not None and pend.tuid == "t3" and pend.detail.get("unfinished")
    assert any(str(m[0]).endswith("A.ets") for m in pend.detail["mentions"])
    assert any(m.seq == pend.seq for m in led.mentions[A])


# ═══════════════ ③ 脚本表按时间取版本 ═══════════════

def test_script_body_is_taken_from_the_version_that_existed_at_run_time(tmp_path: Any) -> None:
    """子代理 00:10 跑 fix.py,主会话 00:40 才写出 fix.py:不能拿 00:40 的正文解释 00:10 的运行(原来主会话先走、脚本表共享,
    就穿越了)。反过来,子代理 00:05 写的脚本主会话 00:10 跑,不管转录先走谁都要解出来。"""
    body = f"p='{A}'\ns=open(p).read()\nopen(p,'w').write(s.replace('a','b'))\n"
    sub = [_rec(at("00:10:00"), "user", "跑脚本"),
           *_call(at("00:10:00"), "s1", "Bash", {"command": "cd /proj && python3 /tmp/fix.py"}, out="")]
    main = [
        *_call(at("00:00:00"), "m0", "Write", {"file_path": A, "content": "a\n"}),
        *_call(at("00:05:00"), "m1", "Agent", {"name": "runner", "prompt": "跑脚本"}, "done", toolUseResult={"agentId": "s"}),
        *_call(at("00:40:00"), "m2", "Write", {"file_path": "/tmp/fix.py", "content": body}),
    ]
    led = _ledger(tmp_path, main, {"agent-s": sub})
    assert len(led.stories[A].versions) == 1
    run = next(a for a in led.agents["agent-s"].actions if a.tool == "Bash")
    assert run.detail.get("unresolved")

    sub2 = [_rec(at("00:05:00"), "user", "写脚本"),
            *_call(at("00:05:00"), "s1", "Write", {"file_path": "/tmp/fix.py", "content": body})]
    main2 = [
        *_call(at("00:00:00"), "m0", "Write", {"file_path": A, "content": "a\n"}),
        *_call(at("00:04:00"), "m1", "Agent", {"name": "writer", "prompt": "写脚本"}, "done", toolUseResult={"agentId": "s"}),
        *_call(at("00:10:00"), "m2", "Bash", {"command": "cd /proj && python3 /tmp/fix.py"}, out=""),
    ]
    led2 = _ledger(tmp_path / "b", main2, {"agent-s": sub2})
    assert len(led2.stories[A].versions) == 2


# ═══════════════ 缓存键要看整个池子 ═══════════════

def test_ledger_cache_key_covers_subagent_transcripts(tmp_path: Any) -> None:
    main = [*_call(at("00:00:00"), "t1", "Write", {"file_path": A, "content": "a\n"})]
    sub = [_rec(at("00:01:00"), "user", "x")]
    _ledger(tmp_path, main, {"agent-s": sub})
    root = str(tmp_path / f"{SID}.jsonl")
    k1 = service.pool_key([root])
    with open(tmp_path / SID / "subagents" / "agent-s.jsonl", "a", encoding="utf-8") as fh:
        fh.write("\n" + '{"timestamp":"2026-01-01T00:02:00Z","type":"user","message":{"role":"user","content":"y"}}\n')
    assert service.pool_key([root]) != k1


def test_refs_carry_transcript_tag_and_resolve_by_location(tmp_path: Any) -> None:
    """(#n@L行·转录标识):#n 是本次建账的句柄,会漂;@L行·标识是转录里的位置,不漂。by_loc 按位置反查动作号。"""
    main = [*_call(at("00:00:00"), "w1", "Write", {"file_path": A, "content": "a\n"})]
    led = _ledger(tmp_path, main)
    wr = next(a for a in led.agents[MAIN_ID].actions if a.tool == "Write")
    tag = SID[:8]
    assert led.locs[wr.seq] == f"{led.lines[wr.seq]}·{tag}" and led.by_loc[(tag, led.lines[wr.seq])] == wr.seq
    text = atoms_text.render_file(led, "A.ets", None, root="/proj")
    assert f"(#{wr.seq}@L{led.lines[wr.seq]}·{tag})" in text
    assert atoms.transcript_tag("/x/agent-a68daf720e780b4c2.jsonl") == "a68daf72"
