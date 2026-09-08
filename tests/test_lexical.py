"""词法层第二批(评审排序):输出里的提及、提及分档与折叠、分页、版本窗口、断点窗口候选数、search 命中带可能文件、
agent 槽里带「可能碰了」与 until 截断。原则:底层索引一条不丢;默认回复可折叠可分页,但没返回的不算模型看过。"""

from __future__ import annotations

from typing import Any

from migloop import atoms, atoms_text

from tests.test_atoms import MAIN_ID, _call, _ledger, _read_call, _rec

A = "/proj/entry/A.ets"


def at(hms: str) -> str:
    return f"2026-01-01T{hms}Z"


def _base(tmp_path: Any, extra: list[dict[str, Any]]) -> Any:
    main = [*_call(at("00:00:00"), "t0", "Write", {"file_path": A, "content": "a\n"}), *extra]
    return _ledger(tmp_path, main)


def test_output_mentions_are_recorded_and_tagged(tmp_path: Any) -> None:
    """git status 的输出点名了文件,命令行里没有:提及层也要收输出(评审 I),标「输出里」。"""
    led = _base(tmp_path, [*_call(at("00:01:00"), "t1", "Bash", {"command": "cd /proj && git status --short"},
                                  out=" M entry/A.ets\n?? entry/New.ets\n")])
    ms = led.mentions[A]
    assert [m.where for m in ms] == ["out"]
    text = atoms_text.render_file(led, "A.ets", None, root="/proj")
    assert "输出里" in text and "git status" in text


def test_mentions_classified_readonly_folded_by_default(tmp_path: Any) -> None:
    """改动类(perl -pi,分析器解不出的就地改)和正文提到(heredoc 体)逐条列;只读检查(wc -l)折成计数,m_all=1 才铺。"""
    led = _base(tmp_path, [
        *_call(at("00:01:00"), "t1", "Bash", {"command": f"wc -l {A}"}, out="1"),
        *_call(at("00:02:00"), "t2", "Bash", {"command": "cd /proj && perl -pi -e 's/x/y/' entry/A.ets"}, out=""),
        *_call(at("00:03:00"), "t3", "Bash", {"command": "cat > /proj/notes.md <<'EOF'\nsee entry/A.ets\nEOF"}, out=""),
    ])
    cls = {m.seq: m.cls for m in led.mentions[A]}
    acts = {a.detail.get("cmd", "")[:3]: a.seq for a in led.agents[MAIN_ID].actions if a.tool == "Bash"}
    assert cls[acts["wc "]] == "readonly" and cls[acts["cd "]] == "change" and cls[acts["cat"]] == "body"
    text = atoms_text.render_file(led, "A.ets", None, root="/proj")
    sec = text.split("提到它的命令")[1]
    assert "perl -pi" in sec and "see entry/A.ets" in sec and "wc -l" not in sec
    assert "只读检查 1 条" in sec and "[改动类]" in sec and "[正文提到]" in sec
    full = atoms_text.render_file(led, "A.ets", None, root="/proj", m_all=True)
    assert "wc -l" in full.split("提到它的命令")[1]


def test_mentions_are_paged_not_truncated(tmp_path: Any) -> None:
    extra = []
    for i in range(45):
        extra += _call(at(f"00:{i:02d}:30"), f"g{i}", "Bash", {"command": f"cd /proj && perl -pi -e 's/x/y/' entry/A.ets  # {i}"}, out="")
    led = _base(tmp_path, extra)
    text = atoms_text.render_file(led, "A.ets", None, root="/proj")
    sec = text.split("提到它的命令")[1]
    assert sec.count("perl -pi") == 40 and "第 1–40 条 / 共 45 条" in sec and "m_from=41" in sec
    rest = atoms_text.render_file(led, "A.ets", None, root="/proj", m_from=41).split("提到它的命令")[1]
    assert rest.count("perl -pi") == 5 and "第 41–45 条 / 共 45 条" in rest


def test_version_windows_and_break_window_candidates(tmp_path: Any) -> None:
    """提及按时刻落到版本窗口;内容未知的版本行给「窗口内提及 N 条」和「窗口内有写能力的命令 N 条(全池)」的查法,
    不自动铺;search(kind=write, since_ts, until_ts) 才列出来。"""
    led = _base(tmp_path, [
        *_call(at("00:05:00"), "t1", "Bash", {"command": "cd /proj && perl -pi -e 's/x/y/' entry/A.ets"}, out=""),
        *_call(at("00:07:00"), "t2", "Bash", {"command": "cd /proj && sed -i 's/x/y/' entry/Other.ets"}, out=""),
        *_call(at("00:10:00"), "t3", "Bash", {"command": f"cp /tmp/x.ets {A}"}, out=""),
        *_call(at("00:15:00"), "t4", "Bash", {"command": "cd /proj && perl -pi -e 's/x/y/' entry/A.ets"}, out=""),
    ])
    fa = atoms.file_atom(led, "A.ets", None)
    wins = [m["win"] for m in fa["mentions"] if m["effect"] is None]
    assert wins == [2, None]                                         # 00:05 落在 v2 的窗口;00:15 在最新版之后
    text = atoms_text.render_file(led, "A.ets", None, root="/proj")
    v2 = next(ln for ln in text.splitlines() if ln.startswith("- v2"))
    assert "窗口内提及 1 条(改动类 1)" in v2
    assert "窗口内有写能力的命令" in v2 and "kind=write" in v2
    sec = text.split("提到它的命令")[1]
    assert "v2 窗口" in sec and "最新版之后" in sec
    listing = atoms_text.render_search(led, "", kind="write", since_ts=at("00:00:00"), until_ts=at("00:10:00"), root="/proj")
    assert "sed -i" in listing and "范围" in listing and "00:15" not in listing      # 窗口外的不列


def test_search_hits_show_possible_files(tmp_path: Any) -> None:
    led = _base(tmp_path, [*_call(at("00:02:00"), "t1", "Bash", {"command": "cd /proj && perl -pi -e 's/x/y/' entry/A.ets"}, out="")])
    text = atoms_text.render_search(led, "perl", agent=MAIN_ID, root="/proj", after=True)
    assert "可能碰到 entry/A.ets" in text


def test_mentions_cover_dispatch_words_and_written_content(tmp_path: Any) -> None:
    """完备性差集(评审 K):转录里提到这个文件的行,账本得有入口。派发词点名(谁被告知了它)默认列;
    别的文件的写入内容里提到它(spec 清单)折叠成计数;说 / 想 / 收件里提到的也折叠但能 m_all=1 铺。"""
    led = _base(tmp_path, [
        *_call(at("00:01:00"), "m1", "Write", {"file_path": "/proj/spec/list.md", "content": "- entry/A.ets 待修\n"}),
        *_call(at("00:02:00"), "m2", "Agent", {"name": "fixer", "prompt": "请修 entry/A.ets 的返回键"}, "done",
               toolUseResult={"agentId": "s"}),
        _rec(at("00:03:00"), "assistant", [{"type": "text", "text": "先看 entry/A.ets 再说"}]),
    ])
    cls = sorted(m.cls for m in led.mentions[A])
    assert cls == ["content", "dispatch", "text"]
    text = atoms_text.render_file(led, "A.ets", None, root="/proj")
    sec = text.split("提到它的命令")[1]
    assert "[派发词]" in sec and "请修 entry/A.ets" in sec
    assert "写入内容 1 条" in sec and "正文 1 条" in sec and "待修" not in sec
    assert "待修" in atoms_text.render_file(led, "A.ets", None, root="/proj", m_all=True)


def test_agent_slot_shows_possible_touch_and_until_cut(tmp_path: Any) -> None:
    """agent 槽里解不出效应的命令直接带「可能碰了 A.ets@v1」;until=#n 把槽截到那条命令,之后的输入不算这一版的依据。"""
    led = _base(tmp_path, [
        *_call(at("00:02:00"), "t1", "Bash", {"command": "cd /proj && perl -pi -e 's/x/y/' entry/A.ets"}, out=""),
        *_read_call(at("00:03:00"), "t2", "/proj/spec/s.md", "spec\n"),
    ])
    co = next(a for a in led.agents[MAIN_ID].actions if a.tool == "Bash")
    text = atoms_text.render_agent(led, MAIN_ID, None, root="/proj")
    assert "可能碰了 entry/A.ets@v1" in text and "spec/s.md" in text
    cut = atoms_text.render_agent(led, MAIN_ID, None, root="/proj", until=co.seq)
    assert "可能碰了 entry/A.ets@v1" in cut and "spec/s.md" not in cut and f"截到 #{co.seq}" in cut
