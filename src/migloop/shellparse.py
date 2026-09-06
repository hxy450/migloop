"""shell 命令的读写解析 —— 纯 session、零磁盘。

MigLoop 的输入只有会话实录;agent 六成以上的动作是一条 shell 命令 + 它的输出。
本模块从**命令文本本身**解析出文件级读写,不依赖被迁移工程在本机。

原则(与写侧的两级置信同一纪律,宁可漏、不可错):
1. 分段优先 —— 续行反斜杠、heredoc 体、$(...)/反引号命令替换、引号先摘干净,
   再按 ``&& || ; | & 换行`` 切成简单命令。此前的正则原型全部误判(commit
   message 里的路径、heredoc 体内的 cat、``[ -f x ]`` 轮询)都死于没分段。
2. 白名单命令词 —— 只认语义明确的读写命令;未知命令(python xxx.py 的实参
   语义不可知)只处理通用重定向,实参一律放弃。``$VAR`` 命令/路径同理:动态
   即黑盒,与脚本同类,放弃留白。
3. 行级尽量,不编造 —— 命令自带区间的(sed -n 'A,Bp' / head -N /
   Get-Content -TotalCount N)记进 spans;cat 整篇、tail(起点未知)只记文件级。
4. 产物三档:
   - content_reads  内容真进了上下文(cat/sed -n/head/grep 命中行…)
   - dep_reads      数据依赖但内容未进上下文(cp 的源、< 的输入)
   - writes         落盘目标(重定向/tee/sed -i/cp 的目标…)
   heredoc 体进 scripts,交给脚本正文解析层(那是另一档)。

词表覆盖率按真实语料校准:0723 全部 482 条命令 / 4035 个简单段,未知命令带
路径实参的仅 0.8%,其中大半是变量命令(原则性放弃)。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class ShellIO:
    content_reads: list[str] = field(default_factory=list)
    dep_reads: list[str] = field(default_factory=list)
    writes: list[str] = field(default_factory=list)
    scripts: dict[str, str] = field(default_factory=dict)   # 内联体:<hd0>… -> 正文
    #: path -> (起始行, 行数) —— 只记命令自带、确定无疑的区间
    spans: dict[str, tuple[int, int]] = field(default_factory=dict)


#: 输出即文件内容的读命令
_READERS = {"cat", "type", "head", "tail", "more", "less", "nl", "tac",
            "strings", "gc", "get-content"}
#: 匹配行进上下文的搜索命令(names-only 旗标另判)
_GREPPERS = {"grep", "rg", "egrep", "fgrep", "select-string", "findstr"}
#: 明确不构成内容读取的命令/关键字 —— 实参里出现路径也不算
_NEUTRAL = {"ls", "dir", "wc", "stat", "du", "file", "test", "[", "[[", "find",
            "if", "then", "elif", "else", "fi", "for", "while", "until", "do",
            "done", "case", "esac", "echo", "printf", "cd", "pushd", "popd",
            "mkdir", "rm", "rmdir", "touch", "sleep", "seq", "true", "false",
            "exit", "return", "break", "continue", "export", "local", "set",
            "unset", "source", "git", "chmod", "chown", "which", "date", "pwd",
            "test-path", "get-childitem", "write-output", "write-host",
            "start-sleep", "new-item", "remove-item"}
_PREFIX_SKIP = {"sudo", "env", "nohup", "time", "command", "exec", "timeout"}

_HD_OPEN = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*")
_SUBST = re.compile(r"\$\(([^()]*)\)|`([^`]*)`")
_VAR_ASSIGN = re.compile(r"^[A-Za-z_]\w*=")
#: 实参要长得像带扩展名的文件路径;变量/通配一律放弃
_PATHISH = re.compile(r"^.+\.[A-Za-z0-9]{1,6}$")
_SED_RANGE = re.compile(r"^(\d+),(\d+)p$")
_NUM = re.compile(r"^\d+[smh]?$")


def _path_of(tok: str, quoted: bool = False) -> str | None:
    if not tok or "$" in tok or "*" in tok or "?" in tok or tok.startswith("-"):
        return None
    if not _PATHISH.match(tok):
        return None
    if " " in tok and not quoted:       # 裸空格 = 多半是分词错;引号包的才算
        return None
    return tok.replace("\\", "/")


def _strip_heredocs(text: str) -> tuple[str, list[str]]:
    """摘掉 heredoc 体(保留 ``<<DELIM`` 标记行);体内不是本命令的实参。"""
    bodies: list[str] = []
    out: list[str] = []
    pos = 0
    while True:
        m = _HD_OPEN.search(text, pos)
        if not m:
            out.append(text[pos:])
            break
        line_end = text.find("\n", m.end())
        if line_end < 0:
            out.append(text[pos:])
            break
        out.append(text[pos:line_end + 1])
        rest = text[line_end + 1:]
        endm = re.search(r"^[ \t]*" + re.escape(m.group(2)) + r"[ \t]*$", rest, re.M)
        if endm is None:
            bodies.append(rest)
            break
        bodies.append(rest[:endm.start()])
        pos = line_end + 1 + endm.end()
    return "".join(out), bodies


def _split_segments(text: str) -> list[str]:
    """引号感知地按 && || ; | & 换行切段;未引号的 #… 注释与 (){} 分组符当分隔。"""
    segs: list[str] = []
    buf: list[str] = []
    quote = ""
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = ""
            i += 1
            continue
        if ch in "'\"":
            quote = ch
            buf.append(ch)
            i += 1
            continue
        if ch == "#" and (not buf or buf[-1].isspace()):
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        two = text[i:i + 2]
        if two in ("&&", "||") or ch in ";|&\n" or ch in "(){}":
            if "".join(buf).strip():
                segs.append("".join(buf).strip())
            buf = []
            i += 2 if two in ("&&", "||") else 1
            continue
        buf.append(ch)
        i += 1
    if "".join(buf).strip():
        segs.append("".join(buf).strip())
    return segs


def _tokenize(seg: str) -> list[tuple[str, bool, str]]:
    """→ [(值, 是否被引号包裹, 操作符)]:操作符 ∈ {'>','>>','<','<<','2>','&>',''}。"""
    toks: list[tuple[str, bool, str]] = []
    buf: list[str] = []
    quoted_any = False
    quote = ""

    def flush() -> None:
        nonlocal buf, quoted_any
        if buf:
            toks.append(("".join(buf), quoted_any, ""))
        buf, quoted_any = [], False

    i, n = 0, len(seg)
    while i < n:
        ch = seg[i]
        if quote:
            if ch == quote:
                quote = ""
            else:
                buf.append(ch)
            i += 1
            continue
        if ch in "'\"":
            quote = ch
            quoted_any = True
            i += 1
            continue
        if ch.isspace():
            flush()
            i += 1
            continue
        if ch in "<>":
            # fd 前缀(2>)与 &> 归并成一个操作符;<< 是 heredoc 标记
            if buf and "".join(buf) in ("2", "1", "&"):
                fd = "".join(buf)
                buf = []
                op = fd + ">"
            else:
                flush()
                op = ch
            if i + 1 < n and seg[i + 1] == ch:
                op = op + ch
                i += 1
            toks.append((op, False, op))
            i += 1
            continue
        buf.append(ch)
        i += 1
    flush()
    return toks


def _head_count(cmd: str, rest: list[tuple[str, bool]]) -> int | None:
    """head/Get-Content 的行数参数;tail 的起点未知,不在此列。"""
    for k, (v, _q) in enumerate(rest):
        if cmd in ("gc", "get-content"):
            if v.lower() == "-totalcount" and k + 1 < len(rest) and rest[k + 1][0].isdigit():
                return int(rest[k + 1][0])
            continue
        if v.startswith("-") and v[1:].isdigit():
            return int(v[1:])
        if v == "-n" and k + 1 < len(rest) and rest[k + 1][0].isdigit():
            return int(rest[k + 1][0])
    return None


def _classify(seg: str, io: ShellIO) -> None:
    toks = _tokenize(seg)
    args: list[tuple[str, bool]] = []
    i = 0
    while i < len(toks):
        op = toks[i][2]
        nxt = toks[i + 1][0] if i + 1 < len(toks) else None
        nxt_q = toks[i + 1][1] if i + 1 < len(toks) else False
        if op in (">", ">>"):
            p = _path_of(nxt or "", nxt_q)
            if p:
                io.writes.append(p)
            i += 2
            continue
        if op == "<":
            p = _path_of(nxt or "", nxt_q)
            if p:
                io.dep_reads.append(p)
            i += 2
            continue
        if op in ("2>", "&>", "<<"):
            i += 2
            continue
        args.append((toks[i][0], toks[i][1]))
        i += 1

    while args and (_VAR_ASSIGN.match(args[0][0]) or args[0][0].lower() in _PREFIX_SKIP):
        head = args.pop(0)[0].lower()
        if head == "timeout" and args and _NUM.match(args[0][0]):
            args.pop(0)                 # timeout 30 cmd… 的时长参数
    if not args:
        return
    cmd = args[0][0].rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower()
    cmd = cmd[:-4] if cmd.endswith(".exe") else cmd
    rest = args[1:]
    flags = [v for v, _q in rest if v.startswith("-")]
    paths = [p for v, q in rest if (p := _path_of(v, q))]

    if cmd in _NEUTRAL:
        return
    if cmd in _READERS:
        io.content_reads.extend(paths)
        n = _head_count(cmd, rest)
        if n and cmd in ("head", "gc", "get-content"):   # tail 起点未知,不编
            for p in paths:
                io.spans.setdefault(p, (1, n))
        return
    if cmd in _GREPPERS:
        if any(c in f for f in flags for c in "lLcq"):
            return                      # 只出名字/计数,内容没进上下文
        # 第一个非旗标实参是模式串,不是文件 —— 0723 实测两类误判:
        # grep -viE "schemas.android|w3.org" (纯管道过滤)、grep "X::class.java" f.kt
        nonflag = [(v, q) for v, q in rest if not v.startswith("-")]
        io.content_reads.extend(
            p for v, q in nonflag[1:] if (p := _path_of(v, q)))
        return
    if cmd == "sed":
        if any(f == "-i" or (f.startswith("-i") and len(f) <= 3) for f in flags):
            io.writes.extend(paths)
            return
        io.content_reads.extend(paths)
        rng = next((m for v, _q in rest if (m := _SED_RANGE.match(v))), None)
        if rng:
            a, b = int(rng.group(1)), int(rng.group(2))
            for p in paths:
                io.spans.setdefault(p, (a, max(1, b - a + 1)))
        return
    if cmd == "awk":
        io.content_reads.extend(paths)
        return
    if cmd == "diff":
        io.content_reads.extend(paths)  # 两边的差异行都进上下文
        return
    if cmd in ("jq", "cut", "sort", "uniq", "paste", "join", "comm", "column"):
        # 内容(或其确定性变换)进上下文;jq 的过滤器实参不是路径,天然被 pathish 挡
        io.content_reads.extend(paths)
        return
    if cmd == "tee":
        io.writes.extend(paths)
        return
    if cmd in ("cp", "mv", "copy-item", "move-item", "copy", "move"):
        if len(paths) >= 2:
            io.dep_reads.extend(paths[:-1])
            io.writes.append(paths[-1])
        return
    if cmd in ("set-content", "add-content", "out-file"):
        io.writes.extend(paths)
        return
    # 未知命令(python xxx.py / $VAR 等):实参语义不可知,只有上面的通用重定向作数


def parse_shell(command: str) -> ShellIO:
    io = ShellIO()
    text = (command or "").replace("\\\n", " ")      # 续行拼回一行再分段
    text, bodies = _strip_heredocs(text)
    for k, b in enumerate(bodies):
        io.scripts[f"<hd{k}>"] = b
    # 命令替换先递归解析再从原文摘除($(seq …) 这类中性的解析后自然为空)
    while True:
        m = _SUBST.search(text)
        if not m:
            break
        inner = parse_shell(m.group(1) or m.group(2) or "")
        io.content_reads += inner.content_reads
        io.dep_reads += inner.dep_reads
        io.writes += inner.writes
        io.scripts.update(inner.scripts)
        io.spans.update(inner.spans)
        text = text[:m.start()] + " " + text[m.end():]
    for seg in _split_segments(text):
        _classify(seg, io)
    io.content_reads = list(dict.fromkeys(io.content_reads))
    io.dep_reads = list(dict.fromkeys(io.dep_reads))
    io.writes = list(dict.fromkeys(io.writes))
    return io
