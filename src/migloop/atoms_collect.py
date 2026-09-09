"""CC 会话实录 → 两原子账本的动作流(atoms.AgentRec)。

与 filestory_collect 的差别就是 0723 普查钉出来的几条:
- 相对路径按「记录 cwd + 命令内 cd 链」解析;cd 到变量之后的相对路径解析不了就丢,不猜
- 工具调用先等结果:is_error 的不落账、不占版本号
- 脚本:有限 straight-line AST 才建立操作;路径字面量仅提及,未知执行单列候选(via=script)
- rm / git rm / Remove-Item → 删除版本;git checkout/restore <path> → 内容未知的写
- Grep 工具 content 模式的命中行 → 带行段的读
- Agent 派发 / SendMessage 是效应;收件箱从自己实录里的 teammate-message 读

agent 身份:主线 = ``__main__:<sid8>``,子代理 = 其 transcript 文件 stem(自带会话 hash)。
"""

from __future__ import annotations

import ast
import bisect
import glob
import json
import os
import posixpath
import re
import warnings
from dataclasses import dataclass, field
from functools import cache
from typing import Any

from migloop.atoms import Action, AgentRec, FileRef
from migloop.audit import stage_order
from migloop.evidence import CONFIRMED_BASES, FileProof, proof_payload
from migloop.filestory import Ev, ts_norm
from migloop.filestory_collect import _clean_single_cat
from migloop.shellparse import (
    _PREFIX_SKIP,
    _VAR_ASSIGN,
    _path_of,
    _split_segments,
    _strip_heredocs,
    _tokenize,
    parse_shell,
)

_EXT = r"(?:md|ets|ts|js|mjs|json5?|py|sh|txt|ya?ml|xml|csv|html|properties|gradle|kts|java|kt)"
#: 含 [ ] ( ) + \ 的不是路径是正则:entry/src/main/ets/[A-Za-z0-9_/]+/.ets 曾进过账本
_LIT = re.compile(r"""['"]([^'"\n{}$*?<>|\[\]()\\+]{2,240}\.""" + _EXT + r""")['"]""")
_WRITEISH = re.compile(r"write_text|write_bytes|open\([^)]*['\"][wa]|\.write\(|json\.dump\(|"
                       r"shutil\.(?:copy|move)|writelines|writeFile|Set-Content|Out-File|"
                       r"os\.rename|\.rename\(|os\.remove|unlink\(", re.I)
_READISH = re.compile(r"read_text|\.read\(\)|json\.load\(|readlines|open\(|readFile|"
                      r"Get-Content|glob\(", re.I)
#: 主会话里收到的汇报带一句前缀「Another Claude session sent a message:」—— 0723 149 条汇报曾因此一条没记
_TEAM = re.compile(r'^\s*(?:Another Claude session sent a message:\s*)?'
                   r'<teammate-message\s+teammate_id="([^"]*)"(?:[^>]*?\ssummary="([^"]*)")?[^>]*>\n?', re.S)
#: 正文类记录在索引行里只留开头;全文按指针展开
_TEXT_HEAD = 600


def _head(text: str) -> str:
    return text.strip()[:_TEXT_HEAD]


def _classify_user_text(raw: str, cwd: object) -> tuple[str | None, dict[str, Any], FileOp | None]:
    """user 侧不是工具结果、不是收件的文本:技能注入 / 操作者指令(含 /技能 调用)/ 系统提示 / 任务通知 / 打断。
    本地命令回显(<local-command-*>)是噪音。注入的技能同时算那份 SKILL.md 的一次读(via=inject),
    让「指南缺条款」这类归因能从文件侧走到所有被灌过它的 agent。"""
    s = raw.lstrip()
    if not s:
        return None, {}, None
    head = s[:600]
    if "<skill-format>true</skill-format>" in head:
        m = re.search(r"<command-name>([^<]+)</command-name>", head)
        name = (m.group(1) if m else "?").strip().lstrip("/")
        body = s.split("</skill-format>", 1)[1] if "</skill-format>" in s else s
        p = _resolve(f".claude/skills/{name}/SKILL.md", _resolve(cwd, None))
        op = FileOp("read", p, "inject") if p else None
        return "inject", {"skill": name, "text": _head(body), "chars": len(body)}, op
    if s.startswith(("<command-name>", "<command-message>")):
        m = re.search(r"<command-name>([^<]+)</command-name>", head)
        a = re.search(r"<command-args>([^<]*)</command-args>", head)
        return "instruction", {"text": ((m.group(1) if m else "") + " " + (a.group(1) if a else "")).strip(),
                               "slash": True}, None
    if s.startswith(("<local-command-stdout>", "<local-command-caveat>")):
        return None, {}, None
    if s.startswith("<system-reminder>"):
        return "system", {"text": _head(s)}, None
    if s.startswith("<task-notification>"):
        return "notify", {"text": _head(s)}, None
    if s.startswith("[Request interrupted"):
        return "interrupt", {"text": _head(s)}, None
    return "instruction", {"text": _head(s)}, None
_SCRIPT_RUN = re.compile(r"\.(?:py|js|mjs|sh)$")
_SCRIPT_EXT_HINT = re.compile(r"\.(?:py|js|mjs|sh)\b")


class ScriptTable(dict[str, list[tuple[str, str | None]]]):
    """精确路径 → [(可用时刻, 正文或未知墓碑)]。全池预扫描唯一写入,收集时冻结查历史。
    正文在调用完成后才可供后续运行推导;未知覆盖、删除、失败和重叠效应使正文失效。"""

    def __init__(self) -> None:
        super().__init__()
        self.frozen = False
        self.busy_until: dict[str, str] = {}

    def put(self, key: str, ts: str, content: str | None) -> None:
        if self.frozen:
            return                          # 预扫描是唯一写者;正式收集只查历史,不能再执行一次 Edit
        ts = ts_norm(ts)
        rows = self.setdefault(key, [])
        rows.append((ts, content))
        rows.sort(key=lambda row: row[0])    # 同时刻按事件顺序,不能按正文排序;None 是未知/删除墓碑

    def body(self, key: str, ts: str | None = None) -> str | None:
        rows = self.get(key) or []
        if not rows:
            return None
        if ts is None:
            return rows[-1][1]
        cutoff = ts_norm(ts)
        prior = [c for t, c in rows if t <= cutoff]
        return prior[-1] if prior else None


def _script_body(scripts: dict[str, Any], key: str, ts: str | None = None) -> str | None:
    if isinstance(scripts, ScriptTable):
        return scripts.body(key, ts)
    v = scripts.get(key)
    return str(v) if isinstance(v, str) else None


def _script_lookup(scripts: dict[str, Any], run: str, base: str | None, ts: str | None) -> str | None:
    """历史表严格按运行路径查;纯 dict 仅保留 shell_file_ops 调用者提供的显式名字映射。"""
    full = _resolve(run, base)
    body = _script_body(scripts, full, ts) if full else None
    if body is not None:
        return body
    if isinstance(scripts, ScriptTable):
        return None                         # cwd 已确定的裸文件名同样是精确路径;唯一同名不证明是同一文件
    if full and (full in scripts or "/" in run.replace("\\", "/")):
        return None                         # 明确路径缺失或已失效,不能借另一个同名文件
    name = os.path.basename(run.replace("\\", "/"))
    return _script_body(scripts, name, ts)


def _script_put(scripts: dict[str, Any], key: str, ts: str | None, content: str | None) -> None:
    if isinstance(scripts, ScriptTable):
        scripts.put(key, ts or "", content)
    else:
        scripts[key] = content


def _update_scripts(scripts: dict[str, Any], ops: list[FileOp], ts: str | None,
                    done_ts: str | None = None) -> None:
    """每次文件效应只入表一次。未知覆盖/删除/条件写均使旧正文失效。"""
    if isinstance(scripts, ScriptTable) and scripts.frozen:
        return
    contents: dict[str, str | None] = {}
    for op in ops:
        if op.op == "read" or not _SCRIPT_RUN.search(op.path):
            continue
        content = None
        if not op.conditional:
            if op.op == "write":
                content = op.content
            elif op.op == "edit":
                cur = contents[op.path] if op.path in contents else _script_body(scripts, op.path, ts)
                if cur is not None and op.old and op.old in cur:
                    content = cur.replace(op.old, op.new or "", -1 if op.replace_all else 1)
        contents[op.path] = content
    for path, content in contents.items():
        end = done_ts or ts
        if isinstance(scripts, ScriptTable) and ts and done_ts:
            prior_end = scripts.busy_until.get(path, "")
            if prior_end >= ts:
                content = None                         # 重叠调用的完成顺序不证明实际写入顺序
                end = max(prior_end, done_ts)
            scripts.busy_until[path] = end
        if done_ts and done_ts != ts:
            _script_put(scripts, path, ts, None)       # 调用尚未返回时不能供其它运行借用
        _script_put(scripts, path, end, content)
        if not isinstance(scripts, ScriptTable):
            _script_put(scripts, os.path.basename(path), end, content)


@cache
def _split_segments_ops(text: str) -> list[tuple[str, str]]:
    """同 _split_segments,但带上每段前面的分隔符(&& / || / 其他)—— 条件分支要靠它判。"""
    segs: list[tuple[str, str]] = []
    buf: list[str] = []
    quote = ""
    sep = ""
    i, n = 0, len(text)

    def flush(next_sep: str) -> None:
        nonlocal buf, sep
        if "".join(buf).strip():
            segs.append((sep, "".join(buf).strip()))
        buf = []
        sep = next_sep

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
        if two in ("&&", "||"):
            flush(two)
            i += 2
            continue
        if ch in ";|&\n" or ch in "(){}":
            flush(ch)
            i += 1
            continue
        buf.append(ch)
        i += 1
    flush("")
    return segs
_MENTION = re.compile(r"[\w./\\~:-]*\w\.[A-Za-z][A-Za-z0-9]{0,5}(?![\w.])")
_RUN_WORD = re.compile(r"[\w./\\~:-]+\.(?:py|js|mjs|sh)\b")


_MENTION_CAP = 2000          # 收集层上限(展示层另行分页);超出记 mentions_truncated
_SCAN_LIMIT = 2_000_000      # 每段文本的扫描预算(字符);超出记 mentions_scan_truncated,查询端能看到没扫的区域
_HEREDOC_BODY = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?[^\n]*\n(.*?)\n[ \t]*\1[ \t]*(?:\n|$)", re.S)
_SEG_SEP = re.compile(r"&&|\|\||[;|\n]")
_CHANGE_HEADS = frozenset({"cp", "mv", "rm", "tee", "truncate", "install", "ln", "python", "python3", "python2", "node",
                           "bash", "sh", "zsh", "chmod", "touch", "dd", "rsync", "unzip", "tar", "patch"})
_READONLY_HEADS = frozenset({"cat", "head", "tail", "grep", "rg", "egrep", "fgrep", "wc", "ls", "stat", "test", "[", "[[",
                             "diff", "find", "file", "less", "more", "md5sum", "sha1sum", "sha256sum", "echo", "printf",
                             "tree", "du", "sort", "uniq", "cut", "tr", "awk", "jq", "realpath", "dirname", "basename"})
_GIT_CHANGE = frozenset({"checkout", "restore", "stash", "apply", "mv", "rm", "reset", "clean", "revert", "merge",
                         "rebase", "pull", "am", "cherry-pick"})


_REDIR_TARGET = re.compile(r">>?\s*['\"]?([^\s'\"|;&]+)")


def _heredoc_spans(cmd: str) -> list[tuple[int, int]]:
    return [(m.start(2), m.end(2)) for m in _HEREDOC_BODY.finditer(cmd)]


def _segment_bounds(cmd: str) -> list[tuple[int, int]]:
    """按 && || ; | 换行切出的各段 (起, 止),一次算好;分档按词所在的段判(原来每个词从头扫一遍,长命令 O(n²))。"""
    bounds: list[tuple[int, int]] = []
    a = 0
    for m in _SEG_SEP.finditer(cmd):
        bounds.append((a, m.start()))
        a = m.end()
    bounds.append((a, len(cmd)))
    return bounds


def _mention_class(seg: str, tok: str) -> str:
    """这一段命令能对这个路径做什么:change / readonly / other。按段头判,sed / perl 看 -i,git 看子命令,
    重定向目标算改动。判不出的算 other,和 change 一样逐条列 —— 分档错误只影响默认折不折,不影响可达。"""
    if tok in _REDIR_TARGET.findall(seg):
        return "change"
    words = [w for w in seg.split() if "=" not in w or w.startswith("-")]
    words = [w for w in words if w not in ("sudo", "env", "time", "nohup", "nice")]
    head = os.path.basename(words[0]) if words else ""
    if head in ("sed", "perl"):
        # -i / -i.bak / -pi / -pie / --in-place 都是就地改
        return ("change" if any(w.startswith("-") and not w.startswith("--e") and "i" in w.split("=")[0]
                                for w in words[1:]) else "readonly")
    if head == "git":
        rest, i = words[1:], 0
        while i < len(rest) and rest[i].startswith("-"):
            i += 2 if rest[i] in ("-C", "-c", "--git-dir", "--work-tree") else 1     # git -C /proj restore …
        return "change" if (i < len(rest) and rest[i] in _GIT_CHANGE) else "readonly"
    if head == "find":
        return "change" if any(w in ("-delete", "-exec", "-execdir", "-ok", "-okdir") for w in words) else "readonly"
    if head in _CHANGE_HEADS:
        return "change"
    if head in _READONLY_HEADS:
        return "readonly"
    return "other"


def _path_mentions(cmd: str, scripts: dict[str, Any], cwd: object = None, ts: str | None = None,
                   where: str = "in", cls: str | None = None,
                   audit: dict[str, Any] | None = None) -> tuple[list[tuple[str, str, str | None, str, str]], int]:
    """命令行 + heredoc 体 + 它跑的脚本正文(或工具输出,where="out")里,长得像路径的词
    → ([(词, 前后文, 解析出的绝对路径|None, 出处 in/body/out, 分档 change/readonly/body/out/other)], 截断数)。
    不判读写,只记词法候选;不是全转录完备证明。超过上限记录截断数和未扫描字符数。"""
    def bounded(text: str, room: int, source: str) -> str:
        skipped = max(0, len(text) - room)
        if skipped and audit is not None:
            audit["mentions_scan_truncated"] = audit.get("mentions_scan_truncated", 0) + skipped
            audit.setdefault("mentions_scan_sources", []).append(source)
        return text[:room]

    text = bounded(cmd or "", _SCAN_LIMIT, where)
    cmd_len = len(text)
    spans = _heredoc_spans(text) if where == "in" else []
    bounds = _segment_bounds(text) if where == "in" else []
    starts = [b[0] for b in bounds]
    base = _resolve(cwd, None) if isinstance(cwd, str) and cwd else None
    if where == "in":
        for m in _RUN_WORD.finditer(text):
            body = _script_lookup(scripts, m.group(0), base, ts)
            if body:
                text += bounded("\n" + body, max(0, _SCAN_LIMIT - len(text)), "script")
    out: list[tuple[str, str, str | None, str, str]] = []
    seen: set[str] = set()
    total = 0
    for m in _MENTION.finditer(text):
        tok = re.sub(r"^(\./)+", "", m.group(0).replace("\\", "/"))
        if not tok or ("/" not in tok and len(tok) < 4) or tok in seen:
            continue
        seen.add(tok)
        total += 1
        if len(out) >= _MENTION_CAP:
            continue
        ctx = " ".join(text[max(0, m.start() - 60):m.end() + 60].split())
        if cls is not None:
            src, kind = where, cls                 # 派发词 / 写入内容 / 正文 / 消息:整段一个种类
        elif where == "out":
            src, kind = "out", "out"
        elif m.start() >= cmd_len or any(s <= m.start() < e for s, e in spans):
            src, kind = "body", "body"
        else:
            i = bisect.bisect_right(starts, m.start()) - 1
            seg = text[bounds[i][0]:bounds[i][1]] if i >= 0 else text[:cmd_len]
            src, kind = "in", _mention_class(seg, m.group(0))
        out.append((tok, ctx[:150], _resolve(tok, base) if "/" in tok else None, src, kind))
    return out, max(0, total - _MENTION_CAP)
_PS_ASSIGN = re.compile(r"\$(\w+)\s*=\s*(['\"])([^'\"\n]+)\2")
_PATHLINE = re.compile(r"^(.+?):(\d+)[:-]")
_LINEONLY = re.compile(r"^(\d+)[:-]")
_ERRISH = ("no such file", "cat:")
_PY = {"python", "python3", "py"}
_RUNNERS = _PY | {"node", "bash", "sh", "zsh"}
#: 存在性守卫:[ -f X ] / [[ -e X ]] / test -s X —— 守卫里对 X 的 < 输入读不算读(文件可能根本不存在)
_PROBE = re.compile(r"(?:\[\[?|\btest)\s+-[efsdrwxL]\s+(\"[^\"]+\"|'[^']+'|[^\s\]]+)")
#: 脚本/工具的输出实参:指到文件的是写(内容未知),指到目录的是目录级线索
_OUT_FLAGS = ("--out", "-o", "--output", "--out-dir", "--outdir", "--output-dir", "--dest")
_OUT_FLAGS_EQ = tuple(f + "=" for f in _OUT_FLAGS)
#: 脚本正文里的目录字面量("spec/baseline/ui" / "/abs/dir"):脚本有写倾向时当输出目录线索
_DIR_LIT = re.compile(r"""['"]((?:/[\w.\-]+)+/?|(?:[\w.\-]+/)+[\w.\-]*)['"]""")
_PATH_VAR = re.compile(r"(\w+)\s*=\s*Path\(\s*['\"]([^'\"]+)['\"]\s*\)")


def _dir_hints(code: str, base: str | None) -> list[str]:
    """脚本(-c 代码 / heredoc / 账本里有内容的 .py)有写倾向时,正文里的目录字面量就是它可能写到的地方。
    gen_page_specs.py 的 OUT = ROOT / "spec/baseline/ui" 就是这么被接上的;文件字面量另走 _literal_ops。"""
    if not _WRITEISH.search(code):
        return []
    lits = [m.group(1).rstrip("/") for m in _DIR_LIT.finditer(code)]
    lits = [x for x in lits if x and not re.search(r"\.\w{1,6}$", x.rsplit("/", 1)[-1])]
    # 脚本自己定义的绝对根(ROOT = Path("/…/aippt_0723") 且后面出现 ROOT / …):相对目录字面量也按它解析;
    # 根本身只是解析基,不是输出目录 —— 0723 的工程根曾让全工程的文件都挂到 api-inventory 的脚本上
    is_abs = lambda x: x.startswith("/") or (len(x) > 1 and x[1] == ":")  # noqa: E731
    base_vars = {m.group(1): m.group(2).rstrip("/") for m in _PATH_VAR.finditer(code)}
    base_paths = {p for v, p in base_vars.items() if is_abs(p) and re.search(r"\b" + re.escape(v) + r"\s*/", code)}
    roots = [x for x in lits if is_abs(x)]
    out: list[str] = []
    for lit in lits:
        if lit in base_paths:
            continue
        bases = [base, *roots] if not is_abs(lit) else [None]
        for b in bases:
            d = _resolve(lit, b)
            if d and d not in out:
                out.append(d)
    return out


@dataclass
class FileOp:
    op: str                        # read | write | delete | edit
    path: str
    via: str = "shell"
    content: str | None = None     # write 全文 / read 快照
    full: bool = False
    start: int | None = None
    n: int | None = None
    dep: bool = False
    old: str | None = None
    new: str | None = None
    replace_all: bool = False
    seen: tuple[tuple[int, str], ...] | None = None
    created: bool = False          # Write 结果说 File created:写之前文件不存在(假前身作废的依据)
    sources: tuple[str, ...] = ()  # cat a b > f 的各段:内容已知就能拼出 f
    conditional: bool = False      # 在 && / || 的条件分支里,是否执行了未知
    proof: FileProof | None = None


@dataclass
class ScriptAnalysis:
    ops: list[FileOp] = field(default_factory=list)
    effect_candidates: list[str] = field(default_factory=list)
    mentions: list[str] = field(default_factory=list)
    probes: list[str] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)
    write_capable: bool = False


# ═══════════════ 路径 ═══════════════

_DRIVE_ALIAS = re.compile(r"^/(?:mnt/)?([a-zA-Z])(?=/|$)")


def _norm_abs(p: str) -> str:
    q = p.replace("\\", "/")
    m = _DRIVE_ALIAS.match(q)
    if m and (q.startswith("/mnt/") or len(q) <= 2 or q[2] == "/"):
        q = m.group(1).upper() + ":" + q[m.end():]        # Git Bash /c/… 与 WSL /mnt/c/… 都是 C:/…
    if len(q) > 1 and q[1] == ":":
        return q[:2].upper() + posixpath.normpath(q[2:] or "/")
    return posixpath.normpath(q)


def _collapse_repeat(path: str) -> str:
    """相对路径拼到 cwd 上产生的段落重复(…/a/b/c/a/b/c/x):连续重复 ≥3 段的折掉一份。"""
    segs = path.split("/")
    for k in range(min(8, len(segs) // 2), 2, -1):
        for i in range(0, len(segs) - 2 * k + 1):
            if segs[i:i + k] == segs[i + k:i + 2 * k]:
                return "/".join(segs[:i + k] + segs[i + 2 * k:])
    return path


_BAD_PATH_CHARS = frozenset(" \t\n;|\"'<>=")


@cache
def _resolve_str(p: str, base: str | None) -> str | None:
    # 带空白/引号/分隔符的 token 是分词失衡的残渣,不是路径 —— 宁可漏
    if not p or any(c in _BAD_PATH_CHARS for c in p):
        return None
    q = p.replace("\\", "/")
    if q.startswith("/") or (len(q) > 1 and q[1] == ":"):
        return _norm_abs(q)
    if base is None:
        return None
    return _collapse_repeat(_norm_abs(base.rstrip("/") + "/" + q))


def _resolve(p: object, base: str | None) -> str | None:
    """路径解析按 (词, cwd) 记忆化:0723 一次建账调 8 万次,大半是重复的。"""
    if not isinstance(p, str):
        return None
    return _resolve_str(p, base)


# ═══════════════ 脚本字面量 ═══════════════

def _parse_py(code: str) -> ast.Module | None:
    """脚本正文按 python 解析;解析不了返回 None,脚本里的非法转义(\\`)这类 SyntaxWarning 不往 stderr 刷。"""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        try:
            return ast.parse(code)
        except (SyntaxError, ValueError):
            return None


def _py_script_ops(code: str, base: str | None) -> ScriptAnalysis:
    """Finite Python operation recognition; process success confirms only the supported execution domain.
    s = open(p).read() → 读;s = s.replace(old, new[, n]) 后 open(p,'w').write(s) → edit;
    open(p,'w').write(常量) / Path(p).write_text(常量) / with open(p,'w') as f: f.write(常量) → 全文写;
    Unknown execution stays candidate; an admitted opaque write can have an author but no snapshot.
    This does not execute code or model arbitrary control flow, aliases or user-defined call semantics."""
    tree = _parse_py(code)
    analysis = ScriptAnalysis()
    literals = _literal_ops(code, base)
    analysis.mentions = literals.mentions
    analysis.probes = literals.probes
    analysis.effect_candidates = literals.effect_candidates
    if tree is None:
        analysis.unsupported.append("Python syntax not supported")
        return analysis
    consts: dict[str, str] = {}
    path_vars: set[str] = set()
    read_path: dict[str, str] = {}                     # 变量 → 它是哪个文件读出来的内容
    edits: dict[str, list[tuple[str, str, bool]]] = {}  # 变量 → 累计的 replace
    dirty: set[str] = set()                            # 变量被解不出的运算改过:写回只能算内容未知
    ops: list[FileOp] = []
    replacers: dict[str, bool] = {}
    shadowed: set[str] = set()

    def invalidate(name: str) -> None:
        """Every binding replacement expires all capabilities of the old value."""
        consts.pop(name, None)
        read_path.pop(name, None)
        edits.pop(name, None)
        dirty.discard(name)
        path_vars.discard(name)
        replacers.pop(name, None)
        if name in {"open", "Path", "print", "pathlib", "io", "codecs", "json", "re", "os"}:
            shadowed.add(name)

    def cs(node: ast.AST | None) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            return consts.get(node.id)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            a, b = cs(node.left), cs(node.right)
            return a + b if a is not None and b is not None else None
        if isinstance(node, ast.Call) and node.args and (
                isinstance(node.func, ast.Name) and node.func.id == "Path" or
                isinstance(node.func, ast.Attribute) and node.func.attr == "Path"):
            return cs(node.args[0])
        return None

    def opened(call: ast.AST) -> tuple[str | None, str]:
        """Resolve standard open and Path-instance open without treating mode as a path."""
        if isinstance(call, ast.Name) and call.id in path_vars:
            return consts.get(call.id), ""
        if not isinstance(call, ast.Call):
            return None, ""
        f = call.func
        name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
        if name not in ("open", "Path"):
            return None, ""
        if name == "Path":
            return (cs(call.args[0]), "") if call.args else (None, "")
        module_open = (isinstance(f, ast.Name) and f.id == "open" or isinstance(f, ast.Attribute)
                       and isinstance(f.value, ast.Name) and f.value.id in {"io", "codecs"})
        if module_open:
            path = cs(call.args[0]) if call.args else None
            mode = cs(call.args[1]) if len(call.args) > 1 else "r"
        else:
            path, _ = opened(f.value) if isinstance(f, ast.Attribute) else (None, "")
            mode = cs(call.args[0]) if call.args else "r"
        for kw in call.keywords:
            if kw.arg == "mode":
                mode = cs(kw.value)
        return path, mode or "unknown"

    def replace_count(call: ast.Call) -> bool | None:
        if len(call.args) < 3:
            return True
        count = call.args[2]
        return False if isinstance(count, ast.Constant) and type(count.value) is int and count.value == 1 else None

    def emit_write(p: str | None, arg: ast.AST, mode: str = "w") -> None:
        rp = _resolve(p, base) if p else None
        if not rp:
            return
        if mode not in ("w", "wt", "wb", "w+", "wt+", "w+b", "wb+"):
            ops.append(FileOp("write", rp, "script"))  # append/r+ payload is not a full file snapshot
            return
        content = cs(arg)
        if content is not None:
            ops.append(FileOp("write", rp, "script", content=content))
            return
        # write(s.replace(a, b)):就地替换的另一种写法
        if (isinstance(arg, ast.Call) and isinstance(arg.func, ast.Attribute) and arg.func.attr == "replace"
                and isinstance(arg.func.value, ast.Name) and read_path.get(arg.func.value.id) == rp
                and arg.func.value.id not in dirty and len(arg.args) >= 2):
            old, new = cs(arg.args[0]), cs(arg.args[1])
            count = replace_count(arg)
            if old is not None and new is not None and count is not None:
                for o2, n2, a2 in edits.pop(arg.func.value.id, []):
                    ops.append(FileOp("edit", rp, "script", old=o2, new=n2, replace_all=a2))
                ops.append(FileOp("edit", rp, "script", old=old, new=new, replace_all=count))
                return
        if isinstance(arg, ast.Name) and read_path.get(arg.id) == rp and arg.id not in dirty:
            if edits.get(arg.id):
                for old, new, all_ in edits.pop(arg.id):
                    ops.append(FileOp("edit", rp, "script", old=old, new=new, replace_all=all_))
            return                     # 原样写回:内容没变,不立版本(读已经记了)
        ops.append(FileOp("write", rp, "script"))

    def handle(stmt: ast.stmt) -> None:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
            name, val = stmt.targets[0].id, stmt.value
            # Evaluate the finite RHS abstract value before replacing its target binding (s=s.replace).
            s = cs(val)
            source = val.func.value.id if (isinstance(val, ast.Call) and isinstance(val.func, ast.Attribute)
                                          and val.func.attr == "replace" and isinstance(val.func.value, ast.Name)) else None
            inherited_path = read_path.get(source)
            inherited_edits = list(edits.get(source, []))
            inherited_dirty = source in dirty
            replacement = ((cs(val.args[0]), cs(val.args[1]), replace_count(val))
                           if source and len(val.args) >= 2 else None)
            opening = (opened(val.func.value) if isinstance(val, ast.Call) and isinstance(val.func, ast.Attribute)
                       and val.func.attr in ("read", "read_text") else (None, ""))
            json_opening = (opened(val.args[0]) if isinstance(val, ast.Call) and isinstance(val.func, ast.Attribute)
                            and val.func.attr == "load" and val.args else (None, ""))
            invalidate(name)
            if s is not None:
                consts[name] = s
                if isinstance(val, ast.Call) and ((isinstance(val.func, ast.Name) and val.func.id == "Path")
                                                  or (isinstance(val.func, ast.Attribute) and val.func.attr == "Path")):
                    path_vars.add(name)
                return
            if isinstance(val, ast.Call) and isinstance(val.func, ast.Attribute):
                if val.func.attr == "load" and isinstance(val.func.value, ast.Name) and val.func.value.id == "json" and val.args:
                    p, _mode = json_opening
                    rp = _resolve(p, base) if p else None
                    if rp:
                        ops.append(FileOp("read", rp, "script", dep=True))
                    return
                if val.func.attr in ("read", "read_text"):
                    p, _mode = opening
                    rp = _resolve(p, base) if p else None
                    if rp:
                        read_path[name] = rp
                        ops.append(FileOp("read", rp, "script", dep=True))
                    return
                if inherited_path and replacement:
                    read_path[name] = inherited_path
                    edits[name] = inherited_edits
                    if inherited_dirty:
                        dirty.add(name)
                    old, new, count = replacement
                    if old is not None and new is not None and count is not None:
                        edits.setdefault(name, []).append((old, new, count))
                    else:
                        dirty.add(name)
                    return
            return
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            call = stmt.value
            fn = call.func
            if isinstance(fn, ast.Attribute) and fn.attr in ("write", "write_text") and call.args:
                p, _mode = opened(fn.value)
                if p:
                    emit_write(p, call.args[0], "w" if fn.attr == "write_text" else _mode)
            if isinstance(fn, ast.Attribute) and fn.attr == "dump" and isinstance(fn.value, ast.Name) and fn.value.id == "json" and len(call.args) >= 2:
                p, _mode = opened(call.args[1])
                rp = _resolve(p, base) if p else None
                if rp:
                    ops.append(FileOp("write", rp, "script"))
            for nested in ast.walk(call):
                if (isinstance(nested, ast.Call) and isinstance(nested.func, ast.Attribute) and nested.func.attr == "load"
                        and isinstance(nested.func.value, ast.Name) and nested.func.value.id == "json" and nested.args):
                    p, _mode = opened(nested.args[0])
                    rp = _resolve(p, base) if p else None
                    if rp and not any(o.path == rp and o.op == "read" for o in ops):
                        ops.append(FileOp("read", rp, "script", dep=True))
            return
        if isinstance(stmt, ast.With) and len(stmt.items) == 1:
            item = stmt.items[0]
            p, _mode = opened(item.context_expr)
            var = item.optional_vars.id if isinstance(item.optional_vars, ast.Name) else None
            if p and var:
                invalidate(var)
                writes = [inner for inner in stmt.body if isinstance(inner, ast.Expr) and isinstance(inner.value, ast.Call)
                          and isinstance(inner.value.func, ast.Attribute) and inner.value.func.attr == "write"
                          and isinstance(inner.value.func.value, ast.Name) and inner.value.func.value.id == var]
                if len(writes) > 1:
                    rp = _resolve(p, base)
                    if rp:
                        ops.append(FileOp("write", rp, "script"))
                    return  # one open handle's writes accumulate; do not emit independent full snapshots
                for inner in stmt.body:
                    if (isinstance(inner, ast.Expr) and isinstance(inner.value, ast.Call)
                            and isinstance(inner.value.func, ast.Attribute) and inner.value.func.attr == "write"
                            and isinstance(inner.value.func.value, ast.Name) and inner.value.func.value.id == var
                            and inner.value.args):
                        emit_write(p, inner.value.args[0], _mode)
                    elif (isinstance(inner, ast.Assign) and len(inner.targets) == 1 and isinstance(inner.targets[0], ast.Name)
                          and isinstance(inner.value, ast.Call) and isinstance(inner.value.func, ast.Attribute)
                          and inner.value.func.attr == "read" and isinstance(inner.value.func.value, ast.Name)
                          and inner.value.func.value.id == var):
                        rp = _resolve(p, base)
                        if rp:
                            invalidate(inner.targets[0].id)
                            read_path[inner.targets[0].id] = rp
                            ops.append(FileOp("read", rp, "script", dep=True))
            return

    supported = True
    unconfirmed_targets: set[str] = set()
    pure_names = {"print", "len", "str", "int", "float", "bool", "list", "tuple", "set", "dict",
                  "range", "enumerate", "sorted", "zip", "min", "max", "open", "Path"}
    pure_attrs = {"read", "read_text", "write", "write_text", "replace", "count", "strip", "lstrip", "rstrip",
                  "split", "splitlines", "join", "startswith", "endswith", "format", "encode", "decode",
                  "exists", "is_file", "is_dir", "stat", "glob", "iterdir", "open", "Path",
                  "sub", "search", "match", "fullmatch", "findall", "compile", "escape", "load", "loads", "dump", "dumps"}

    def supported_stmt(stmt: ast.stmt) -> bool:
        local_handles = {item.optional_vars.id for item in stmt.items
                         if isinstance(item.optional_vars, ast.Name) and opened(item.context_expr)[0]} if isinstance(stmt, ast.With) else set()

        def known_value(value: ast.AST) -> bool:
            if isinstance(value, ast.Name):
                return value.id not in shadowed and value.id in set(consts) | set(read_path) | path_vars | local_handles | {"io", "codecs", "pathlib", "json", "re", "os"}
            if isinstance(value, ast.Constant):
                return True
            if isinstance(value, ast.Attribute):
                return known_value(value.value)
            if isinstance(value, ast.Call):
                fn = value.func
                return (isinstance(fn, ast.Name) and fn.id in pure_names and fn.id not in shadowed
                        or isinstance(fn, ast.Attribute) and fn.attr in pure_attrs and known_value(fn.value))
            return False
        if isinstance(stmt, (ast.Import, ast.ImportFrom)):
            if isinstance(stmt, ast.ImportFrom):
                return stmt.module == "pathlib" and all(n.name == "Path" and n.asname is None for n in stmt.names)
            return all(n.name in {"pathlib", "io", "codecs", "re", "json", "os"} and n.asname is None for n in stmt.names)
        if isinstance(stmt, ast.FunctionDef):
            return not stmt.decorator_list and not stmt.args.defaults and not stmt.args.kw_defaults
        if not isinstance(stmt, (ast.Assign, ast.Expr, ast.Assert, ast.With, ast.Pass)):
            return False
        if any(isinstance(n, ast.Assign) and (len(n.targets) != 1 or not isinstance(n.targets[0], ast.Name))
               for n in ast.walk(stmt)):
            return False  # unpacking/chained/attribute stores are outside this finite abstract domain
        if any(isinstance(n, (ast.If, ast.For, ast.While, ast.Try, ast.Raise, ast.Return, ast.Lambda,
                              ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp, ast.NamedExpr)) for n in ast.walk(stmt)):
            return False
        for node in ast.walk(stmt):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            if isinstance(fn, ast.Name):
                if fn.id in shadowed or fn.id not in pure_names | set(replacers):
                    return False
                if fn.id in replacers and shadowed & {"open", "Path", "io", "codecs", "pathlib"}:
                    return False
            elif isinstance(fn, ast.Attribute):
                if fn.attr not in pure_attrs or not known_value(fn.value):
                    return False
                if isinstance(fn.value, ast.Name) and fn.value.id in shadowed:
                    return False
            else:
                return False
        return True

    for stmt in tree.body:
        supported = supported and supported_stmt(stmt)
        if isinstance(stmt, (ast.FunctionDef, ast.ClassDef)):
            invalidate(stmt.name)
            if supported and isinstance(stmt, ast.FunctionDef):
                replacers.update(_replace_helpers(ast.Module(body=[stmt], type_ignores=[])))
        elif isinstance(stmt, ast.Assign) and (len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name)):
            for target in stmt.targets:
                for node in ast.walk(target):
                    if isinstance(node, ast.Name):
                        invalidate(node.id)
        if not supported:
            analysis.unsupported.append(f"unsupported execution domain at Python line {stmt.lineno}")
            unconfirmed_targets.update(_literal_ops(ast.get_source_segment(code, stmt) or "", base).effect_candidates)
        start_ops = len(ops)
        if (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call) and isinstance(stmt.value.func, ast.Name)
                and stmt.value.func.id in replacers and len(stmt.value.args) >= 2):
            rp = _resolve(cs(stmt.value.args[0]), base) if cs(stmt.value.args[0]) else None
            pairs = stmt.value.args[1]
            items = pairs.elts if isinstance(pairs, (ast.List, ast.Tuple)) else []
            if rp and items:
                ops.append(FileOp("read", rp, "script", dep=True))
                for it in items:
                    if isinstance(it, (ast.Tuple, ast.List)) and len(it.elts) == 2:
                        old, new = cs(it.elts[0]), cs(it.elts[1])
                        if old is not None and new is not None:
                            ops.append(FileOp("edit", rp, "script", old=old, new=new, replace_all=replacers[stmt.value.func.id]))
                            continue
                    ops.append(FileOp("write", rp, "script"))       # 有一对算不出:写回内容未知
                    break
        else:
            handle(stmt)
        if supported:
            for op in ops[start_ops:]:
                op.proof = FileProof("supported_python", "unknown", "dependency" if op.dep else "none",
                                     "unknown", f"Python straight-line statement L{stmt.lineno}")
        else:
            unconfirmed_targets.update(o.path for o in ops[start_ops:] if o.op != "read")
            del ops[start_ops:]
    solved = {o.path for o in ops}
    analysis.ops = ops
    analysis.effect_candidates = sorted((set(analysis.effect_candidates) - solved) | unconfirmed_targets)
    # A literal loop binding is enough to locate potential targets, not to assert execution.
    for loop in (n for n in ast.walk(tree) if isinstance(n, ast.For) and isinstance(n.target, ast.Name)
                 and isinstance(n.iter, (ast.List, ast.Tuple))):
        variable = loop.target.id
        writes_variable = any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "open"
                              and n.args and isinstance(n.args[0], ast.Name) and n.args[0].id == variable
                              and len(n.args) > 1 and isinstance(n.args[1], ast.Constant)
                              and str(n.args[1].value).startswith(("w", "a")) for stmt in loop.body for n in ast.walk(stmt))
        if writes_variable:
            analysis.effect_candidates.extend(p for item in loop.iter.elts if (p := _resolve(cs(item), base)))
    analysis.write_capable = bool(analysis.effect_candidates) or any(o.op != "read" for o in ops)
    return analysis


def _replace_helpers(tree: ast.Module) -> dict[str, bool]:
    """Only the complete same-file read/replace/write template, not co-occurring keywords."""
    out: dict[str, bool] = {}
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or len(node.args.args) < 2:
            continue
        path_name, pairs_name = node.args.args[0].arg, node.args.args[1].arg

        def io_call(value: ast.AST, methods: set[str]) -> bool:
            if not (isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute) and value.func.attr in methods):
                return False
            opening = value.func.value
            return (isinstance(opening, ast.Call) and opening.args and isinstance(opening.args[0], ast.Name)
                    and opening.args[0].id == path_name and
                    (isinstance(opening.func, ast.Name) and opening.func.id in {"open", "Path"}
                     or isinstance(opening.func, ast.Attribute) and opening.func.attr in {"open", "Path"}
                     and isinstance(opening.func.value, ast.Name) and opening.func.value.id in {"io", "codecs", "pathlib"}))

        phase, text_name, replacement = 0, None, None
        valid = True
        for stmt in node.body:
            if isinstance(stmt, ast.Expr) and (isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str)
                                               or isinstance(stmt.value, ast.Call) and isinstance(stmt.value.func, ast.Name)
                                               and stmt.value.func.id == "print" and all(isinstance(a, (ast.Name, ast.Constant)) for a in stmt.value.args)):
                continue
            if phase == 0 and isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name) and io_call(stmt.value, {"read", "read_text"}):
                text_name = stmt.targets[0].id
                valid = text_name != path_name
                phase = 1
            elif phase == 1 and isinstance(stmt, ast.For) and isinstance(stmt.iter, ast.Name) and stmt.iter.id == pairs_name and isinstance(stmt.target, (ast.Tuple, ast.List)) and len(stmt.target.elts) == 2 and all(isinstance(e, ast.Name) for e in stmt.target.elts):
                names = [e.id for e in stmt.target.elts]
                for inner in stmt.body:
                    if isinstance(inner, ast.Assert) and not any(isinstance(n, ast.Call) for n in ast.walk(inner)):
                        continue
                    call = inner.value if isinstance(inner, ast.Assign) else None
                    if (not isinstance(inner, ast.Assign) or len(inner.targets) != 1 or not isinstance(inner.targets[0], ast.Name)
                            or inner.targets[0].id != text_name or not isinstance(call, ast.Call)
                            or not isinstance(call.func, ast.Attribute) or call.func.attr != "replace"
                            or not isinstance(call.func.value, ast.Name) or call.func.value.id != text_name
                            or len(call.args) not in (2, 3) or not all(isinstance(a, ast.Name) and a.id == n for a, n in zip(call.args[:2], names))
                            or len(call.args) == 3 and not (isinstance(call.args[2], ast.Constant) and type(call.args[2].value) is int and call.args[2].value == 1)):
                        valid = False
                        break
                    replacement = len(call.args) == 2
                phase = 2
            elif phase == 2 and isinstance(stmt, ast.Expr) and io_call(stmt.value, {"write", "write_text"}) and len(stmt.value.args) == 1 and isinstance(stmt.value.args[0], ast.Name) and stmt.value.args[0].id == text_name:
                opening = stmt.value.func.value
                mode = opening.args[1].value if len(opening.args) > 1 and isinstance(opening.args[1], ast.Constant) else "w"
                valid = mode == "w"
                phase = 3
            else:
                valid = False
            if not valid:
                break
        if valid and phase == 3 and replacement is not None:
            out[node.name] = replacement
    return out


_DOC_EXT = re.compile(r"\.(?:md|json5?|txt|ya?ml|csv)$", re.I)


def _py_partial_writes(code: str) -> list[tuple[str, str]]:
    """python 正文里「某个调用把一个文档路径和几段长字符串一起传进去」(fill(UI/'x.md', exp=…, act=…)):
    渲染器写出来的文件账本拿不到全文,但正文就在这些字面量里 —— 按文件名记成「部分内容」。"""
    tree = _parse_py(code)
    if tree is None:
        return []
    out: list[tuple[str, str]] = []

    def doc_name(node: ast.AST) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and _DOC_EXT.search(node.value):
            return node.value.rsplit("/", 1)[-1]
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            return doc_name(node.right)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Path" and node.args:
            return doc_name(node.args[0])
        return None

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        args = list(node.args) + [kw.value for kw in node.keywords]
        names = [n for n in (doc_name(a) for a in args) if n]
        texts = [a.value for a in args if isinstance(a, ast.Constant) and isinstance(a.value, str)
                 and len(a.value) >= 20 and not _DOC_EXT.search(a.value)]
        if len(names) == 1 and texts:
            out.append((names[0], "\n".join(texts)))
    return out


def _literal_ops(code: str, base: str | None) -> ScriptAnalysis:
    """Lexical paths are mentions, never formal operations or blanket write barriers."""
    result = ScriptAnalysis()
    for m in _LIT.finditer(code):
        p = _resolve(m.group(1), base)
        if not p:
            continue
        result.mentions.append(p)
        after = code[m.end():m.end() + 40]
        before = code[max(0, m.start() - 40):m.start()]
        # 紧跟在 : 后面的是映射的值("hmos_page_map": {"MainActivity": "…/Index.ets"}),不是文件操作的
        # 目标:DiceRoller 0903 主会话初始化 progress.json 的 heredoc 曾借倾向兜底给 Index.ets 造出一版假修复
        if re.search(r":\s*$", before):
            continue
        # open(p, 'w') / 'a' / 'wb' / 'w+':模式串必须是完整的短 token,后面紧跟 , 或 ) ——
        # 只看引号后一个字母会把数据表里紧跟的 'wired' 之类字段当成写模式
        if re.match(r"\s*,\s*['\"][wa][bt+]{0,2}['\"]\s*[,)]", after) or re.match(r"\s*\)\s*\.write", after):
            result.effect_candidates.append(p)
        elif re.match(r"\s*\)\s*\.(?:exists|is_file|is_dir|stat|iterdir|glob)\b", after):
            result.probes.append(p)
    return result


#: bash 习惯:S=/sdk/api; sed -n '570,625p' $S/x.d.ts —— 同一条命令里赋了字面量的变量可代换;
#: 值里带 $ / 反引号 / 通配的(f=$(find …))不是字面量,照旧放弃
_SH_ASSIGN = re.compile(r"(?:^|[;&|(]\s*|\b(?:export|local)\s+)([A-Za-z_]\w*)="
                        r"(?:(['\"])([^'\"\n$`]*)\2|([^\s;&|()$`*?]+))")
#: 静态列表循环:for f in a.md b.md; do …$f…; done —— 项全是字面量时展开成逐项命令
_FOR_LOOP = re.compile(r"\bfor\s+(\w+)\s+in\s+([^;\n]+?)\s*;\s*do\s+(.*?)\s*;?\s*done\b", re.S)
_HDR = re.compile(r"^==> (.+?) <==$", re.M)
_READ_VERB = re.compile(r"\b(cat|sed|head|tail|grep|rg|egrep|fgrep|awk|Get-Content|Select-String)\b")
_WRITE_VERB = re.compile(r"(>>?|\btee\b|\bcp\b|\bmv\b|sed -i)")


def _substitute_vars(text: str) -> str:
    """同一条命令里赋了字面量的变量代换到引用处(PowerShell $p='…' 与 bash S=… 两种写法)。"""
    subs: dict[str, str] = {}
    for m in _PS_ASSIGN.finditer(text):
        subs[m.group(1)] = m.group(3)
    for m in _SH_ASSIGN.finditer(text):
        val = m.group(3) if m.group(3) is not None else m.group(4)
        if val:
            subs.setdefault(m.group(1), val)
    for name, lit in subs.items():
        esc = re.escape(name)
        pat = r"\$\{" + esc + r"\}|\$" + esc + r"(?!\w)"
        text = re.sub(pat, lit.replace("\\", "\\\\"), text)   # 替换串里的反斜杠要自转义
    return text


_ECHO_SEP = re.compile(r"""echo\s+(?:"([^"]*)"|'([^']*)'|(\S+))""")


def _loop_sections(text: str, out: str) -> dict[str, list[str]]:
    """for X in 静态列表; do echo "<前缀>$X<后缀>"; …; done:stdout 按 echo 出来的分隔行切成 {项: 段落行}。
    只在每一项的分隔行都能在 stdout 里找到时才认 —— 宁可漏。"""
    m = _FOR_LOOP.search(text)
    if m is None or not out:
        return {}
    var, items_s, body = m.group(1), m.group(2), m.group(3)
    if re.search(r"[$`*?{]", items_s):
        return {}
    items = [w.strip("'\"") for w in items_s.split()]
    em = _ECHO_SEP.search(body)
    if em is None:
        return {}
    tpl = next(g for g in em.groups() if g is not None)
    pat = re.compile(r"\$\{" + re.escape(var) + r"\}|\$" + re.escape(var) + r"(?!\w)")
    if not pat.search(tpl):
        return {}
    seps = {it: pat.sub(lambda _m, it=it: it, tpl) for it in items}
    lines = out.split("\n")
    starts: list[tuple[int, str]] = []
    for it, sep in seps.items():
        idx = next((i for i, ln in enumerate(lines) if ln.strip() == sep.strip()), None)
        if idx is None:
            return {}
        starts.append((idx, it))
    starts.sort()
    sections: dict[str, list[str]] = {}
    for n, (idx, it) in enumerate(starts):
        end = starts[n + 1][0] if n + 1 < len(starts) else len(lines)
        sections[it] = [ln for ln in lines[idx + 1:end] if ln.strip()]
    return sections


def _attach_loop_sections(text: str, out: str, ops: list[FileOp]) -> None:
    """循环里逐个读的文件,把 stdout 的对应段落挂成「看见的行」(行号未知记 0);已有快照 / 命中行的不动。"""
    sections = _loop_sections(text, out)
    if not sections:
        return
    for op in ops:
        if op.op != "read" or op.content is not None or op.seen:
            continue
        for it, sec in sections.items():
            if sec and (op.path == it or op.path.endswith("/" + it.lstrip("./"))):
                op.seen = tuple((0, ln) for ln in sec[:200])
                break


def _expand_loops(text: str) -> str:
    """静态列表循环展开;项里有变量/通配/命令替换(for f in *.md / $(seq …))解不开,原样留着。"""
    def rep(m: re.Match[str]) -> str:
        var, items_s, body = m.group(1), m.group(2), m.group(3)
        if re.search(r"[$`*?{]", items_s) or re.search(r"\b(for|while|until)\b", body):
            return m.group(0)
        items = [w.strip("'\"") for w in items_s.split()]
        if not items or len(items) > 200:
            return m.group(0)
        pat = re.compile(r"\$\{" + re.escape(var) + r"\}|\$" + re.escape(var) + r"(?!\w)")
        return "; ".join(pat.sub(lambda _m, it=it: it.replace("\\", "\\\\"), body) for it in items)
    return _FOR_LOOP.sub(rep, text)


def _grep_stdout_reads(out: str, base: str | None, has_n: bool, names_only: bool,
                       ops: list[FileOp], listing: bool = False) -> list[FileOp]:
    """目录 grep / rg / 通配目标:命令里看不出读了哪些文件,stdout 里写着(path:line:text /
    -l 的文件名清单)—— 按 stdout 反证成读。已有显式目标的读只补 seen。
    listing=命令里还有 ls/find 之类列目录的段:stdout 里不带 / 的裸名字多半是目录清单,不算读
    (0723 的 ROOT/SplashPage.ets 这类幽灵路径就是这么来的)。推出来的读标 via=stdout,不算实锤。"""
    if not out.strip() or out.lower().startswith(_ERRISH):
        return []
    have = {o.path: o for o in ops if o.op == "read"}
    new: list[FileOp] = []
    if names_only:
        for line in out.splitlines():
            tok = re.sub(r":\d+$", "", line.strip())      # grep -c 的 path:count
            if not tok or tok.startswith("Binary file") or not _path_of(tok):
                continue
            if listing and "/" not in tok:
                continue
            p = _resolve(tok, base)
            if p and p not in have:
                op = FileOp("read", p, "stdout", dep=True)
                have[p] = op
                new.append(op)
        return new
    hits: dict[str, list[tuple[int, str]]] = {}
    for line in out.splitlines():
        if line.startswith("Binary file"):
            continue
        if has_n:
            m = _HITLINE.match(line)
            if not m or not m.group("p") or not _path_of(m.group("p")):
                continue
            p = _resolve(m.group("p"), base)
            if p:
                hits.setdefault(p, []).append((int(m.group("ln")), m.group("t")))
        else:
            m2 = re.match(r"^([^\s:]+?):(.*)$", line)
            if not m2 or not _path_of(m2.group(1)):
                continue
            p = _resolve(m2.group(1), base)
            if p:
                hits.setdefault(p, [])
    if not hits:
        # 管道里 sed/awk 把 grep 输出改了形状(path  ->  X):行首 token 是路径就算读到了这个文件
        for line in out.splitlines():
            lead = re.match(r"^\s*(\S+?)(?=\s|:|$)", line)
            if not lead or not _path_of(lead.group(1)):
                continue
            if listing and "/" not in lead.group(1):
                continue
            p = _resolve(lead.group(1), base)
            if p:
                hits.setdefault(p, [])
    for p, pairs in hits.items():
        seen = tuple(sorted({num: t for num, t in pairs}.items())) or None
        if p in have:
            if seen and not have[p].seen:
                have[p].seen = seen
            continue
        op = FileOp("read", p, "stdout", seen=seen)
        have[p] = op
        new.append(op)
    return new


def _head_header_reads(out: str, base: str | None, ops: list[FileOp]) -> list[FileOp]:
    """head 多个文件的 stdout 按 ==> path <== 分段:每段就是该文件被看见的前几行。"""
    parts = _HDR.split(out)
    if len(parts) < 3:
        return []
    have = {o.path: o for o in ops if o.op == "read"}
    new: list[FileOp] = []
    for raw_path, body in zip(parts[1::2], parts[2::2], strict=False):
        p = _resolve(raw_path.strip(), base) if _path_of(raw_path.strip()) else None
        if not p:
            continue
        lines = body.strip("\n").split("\n") if body.strip("\n") else []
        seen = tuple((i + 1, t) for i, t in enumerate(lines))
        if p in have:
            have[p].seen, have[p].start, have[p].n = seen or None, 1, len(lines) or None
            continue
        op = FileOp("read", p, "shell", start=1, n=len(lines) or None, seen=seen or None)
        have[p] = op
        new.append(op)
    return new


def _unresolved_reason(cmd: str) -> str | None:
    """解析不出读写、但命令明显在读写文件:给出原因,进动作 detail —— 不许静默。"""
    if re.search(r"python3? -c|node -e|<<\s*['\"]?\w+", cmd):
        return "脚本黑盒"
    if not _READ_VERB.search(cmd) and not _WRITE_VERB.search(cmd):
        return None
    if re.search(r"\$\(|`", cmd):
        return "命令替换路径"
    if re.search(r"\$\{?[A-Za-z_]\w*\}?", cmd):
        return "变量路径"
    if re.search(r"[*?]", cmd):
        return "通配路径"
    return None


def _head_word(words: list[str]) -> tuple[str, list[str]]:
    ws = list(words)
    while ws and (_VAR_ASSIGN.match(ws[0]) or ws[0].lower() in _PREFIX_SKIP):
        ws.pop(0)
    if not ws:
        return "", []
    head = ws[0].rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower()
    return (head[:-4] if head.endswith(".exe") else head), ws[1:]


def _shell_analyze(cmd: str, cwd: object, scripts: dict[str, Any],
                   out: str = "", ts: str | None = None,
                   success: bool = False) -> tuple[list[FileOp], bool, int, list[str], dict[str, list[str]]]:
    """一条 shell 命令 → (文件读写, 「有写能力但目标不全可知」标记, 放弃方向判定的脚本字面量数, 放弃的路径,
    线索 {probed: 只探了存在的路径, out_dirs: 输出目录})。
    out = stdout,目录 grep / 多文件 head 这类命令里看不出目标的,按 stdout 反证。"""
    ops: list[FileOp] = []
    capable = False
    undetermined = 0
    touched: list[str] = []
    probed: set[str] = set()
    probe_hits: list[str] = []
    out_dirs: list[str] = []
    mk_dirs: list[str] = []
    ran_script = False
    listing = False
    script_mentions: list[str] = []
    script_unsupported: list[str] = []
    text, bodies = _strip_heredocs((cmd or "").replace("\\\n", " "))
    # 同一条命令里赋了字面量的变量代换到引用处(PowerShell / bash 两种写法);静态列表循环展开。
    # 没赋值的($HOME 等)、项带通配的循环照旧放弃
    text = _expand_loops(_substitute_vars(text))
    grep_ctx: list[tuple[str | None, bool, bool]] = []   # (当时的 cwd, 有 -n, 只出名字)
    base = _resolve(cwd, None) if isinstance(cwd, str) and cwd else None
    hd_target: str | None = None
    if bodies and ">" in (cmd or ""):
        # 整条只在 heredoc 落盘时解析一次(找唯一的重定向目标);其余按段解析已够,
        # 省掉的这一遍 parse_shell 是 collect_cc 里最贵的一段(2505 次调用 ~1.5s)
        whole = parse_shell(text)
        if len(whole.writes) == 1 and len(bodies) == 1:
            hd_target = _resolve(whole.writes[0], base)

    def add(op: str, raw: str, via: str = "shell", **kw: Any) -> None:
        p = _resolve(raw, base)
        if p:
            ops.append(FileOp(op, p, via, **kw))

    def add_script(code: str, script_base: str | None) -> None:
        nonlocal capable
        analysis = _py_script_ops(code, script_base)
        ops.extend(analysis.ops)
        touched.extend(analysis.effect_candidates)
        script_mentions.extend(analysis.mentions)
        probe_hits.extend(analysis.probes)
        script_unsupported.extend(analysis.unsupported)
        capable = capable or analysis.write_capable

    unknown_scripts: list[str] = []
    segments = _split_segments_ops(text)
    # 只有完整、简单 AND 链的成功返回能证明所有前件成功。cd/mkdir/echo 等也会失败,
    # 后面有 ; true / || / 管道时,整个调用成功不等于分支执行过。
    control_heads = {"exit", "return", "exec", "if", "then", "else", "for", "while", "until",
                     "case", "eval", "source", ".", "!", "trap", "fi", "do", "done", "elif", "esac"}
    opaque_control = (any(sep in ("(", ")", "{", "}") for sep, _ in segments)
                      or any(_head_word([t[0] for t in _tokenize(seg) if t[2] == ""])[0]
                             in control_heads for _, seg in segments))
    simple_and_ok = (success and all(sep in ("", "&&") for sep, _ in segments)
                     and not opaque_control)
    seg_cond = False
    seg_start = 0
    heredoc_context: list[tuple[bool, str | None]] = []
    for sep, seg in segments:
        if seg_cond:
            for o in ops[seg_start:]:
                o.conditional = True      # && / || 之后:前件成败未知,这一步是否执行了也未知(评审反例 false && cp)
        seg_start = len(ops)
        seg_cond = sep in ("&&", "||") and not simple_and_ok
        if opaque_control:
            seg = re.sub(r"^(?:then|do|else)\s+", "", seg, count=1)  # 仅收条件候选,不求值控制流
        if "<<" in seg:
            heredoc_context.append((seg_cond, base))
        for pm in _PROBE.finditer(seg):
            pp = _resolve(pm.group(1).strip("'\""), base)
            if pp:
                probed.add(pp)
        words = [t[0] for t in _tokenize(seg) if t[2] == ""]
        head, args = _head_word(words)
        if not head:
            continue
        if head in ("cd", "pushd", "set-location", "push-location"):
            tgt = next((w for w in args if not w.startswith("-")), None)
            base = None if (tgt is None or "$" in tgt or tgt == "-") else _resolve(tgt, base)
            continue
        if head in ("ls", "find", "tree", "dir", "get-childitem"):
            listing = True
        if head in ("grep", "rg", "egrep", "fgrep"):
            short = [a for a in args if a.startswith("-") and not a.startswith("--")]
            longf = [a for a in args if a.startswith("--")]
            names_only = (any(c in f for f in short for c in "lLc")
                          or any(f.startswith(("--files-with", "--count")) for f in longf))
            recursive = (head == "rg" or any(c in f for f in short for c in "rR")
                         or any(f.startswith(("--recursive", "--include")) for f in longf))
            has_n = any("n" in f for f in short) or "--line-number" in longf
            targets = [a for a in args if not a.startswith("-")][1:]
            if recursive or not targets or any(_path_of(t) is None for t in targets):
                grep_ctx.append((base, has_n, names_only))
        io = parse_shell(seg)
        if head == "cat" and len(io.writes) == 1 and io.content_reads and not bodies:
            # cat a b > f:各段是依赖读(内容没进上下文),f 是拼接派生的写 —— resource-mapping.md 就是三段拼的
            srcs = tuple(q for q in (_resolve(p, base) for p in io.content_reads) if q)
            tgt = _resolve(io.writes[0], base)
            if tgt and srcs:
                ops.append(FileOp("write", tgt, "shell", sources=srcs))
                for q in srcs:
                    ops.append(FileOp("read", q, "shell", dep=True))
                continue
        for p in io.writes:
            add("write", p)
        for p in io.content_reads:
            sp = io.spans.get(p)
            add("read", p, start=sp[0] if sp else None, n=sp[1] if sp else None)
        for p in io.dep_reads:
            rp = _resolve(p, base)
            if rp is not None and rp in probed:
                probe_hits.append(rp)          # 守卫里的 wc -l < X:文件可能不存在,只记探测
                continue
            add("read", p, dep=True)
        pathish = [pq for w in args if (pq := _path_of(w))]
        if head in ("mkdir", "new-item"):
            mk_dirs += [d for w in args if not w.startswith("-") and not any(c in w for c in "{}$*?")
                        and (d := _resolve(w, base))]
        if head not in ("grep", "rg", "egrep", "fgrep", "sed", "awk"):
            for i, w in enumerate(args):
                val = args[i + 1] if w in _OUT_FLAGS and i + 1 < len(args) else (
                    w.split("=", 1)[1] if w.startswith(_OUT_FLAGS_EQ) else None)
                if not val or any(c in val for c in "{}$*?"):
                    continue
                capable = True
                if _path_of(val, True):
                    add("write", val)          # --out x.json:目标明确,内容未知
                else:
                    od = _resolve(val, base)
                    if od:
                        out_dirs.append(od)
        if head in ("rm", "remove-item") or (head == "git" and args[:1] == ["rm"]):
            for p in pathish:
                add("delete", p)
        elif head == "git" and args[:1] in (["checkout"], ["restore"]):
            for p in pathish:
                add("write", p)
        elif head in ("mv", "move-item", "move"):
            for p in io.dep_reads:
                add("delete", p)
        if head in _PY and "-c" in args and args.index("-c") + 1 < len(args):
            code = args[args.index("-c") + 1]
            add_script(code, base)
            out_dirs += _dir_hints(code, base)
        if head in _RUNNERS:
            run = next((w for w in args if _SCRIPT_RUN.search(w) and not w.startswith("-")), None)
            if run:
                ran_script = True
                body = _script_lookup(scripts, run, base, ts)
                if body is None:
                    capable = True                # 会话外脚本 / 运行时尚未写出:目标不可知
                    unknown_scripts.append(run)
                else:
                    # 跑的 .py 脚本和 heredoc 一样先走 ast:规整的读改写解成 edit,字面量层只补 ast 没解出的路径
                    add_script(body, base)
                    out_dirs += _dir_hints(body, base)
    if seg_cond:
        for o in ops[seg_start:]:
            o.conditional = True
    if out and grep_ctx:
        gb, has_n, names_only = grep_ctx[-1]
        ops += _grep_stdout_reads(out, gb, has_n, names_only, ops, listing)
    if out and "==> " in out and any(_head_word([t[0] for t in _tokenize(s) if t[2] == ""])[0]
                                       in ("head", "tail") for s in _split_segments(text)):
        ops += _head_header_reads(out, base, ops)
    if out and _FOR_LOOP.search(cmd or ""):
        _attach_loop_sections((cmd or "").replace("\\\n", " "), out, ops)
    for body_index, body in enumerate(bodies):
        if hd_target is not None:
            for op in ops:
                if op.op == "write" and op.path == hd_target:
                    op.content, op.via = body, "shell"
            continue
        conditional, body_base = (heredoc_context[body_index] if body_index < len(heredoc_context)
                                  else (True, None))
        body_start = len(ops)
        add_script(body, body_base)
        for op in ops[body_start:]:
            op.conditional = conditional
        out_dirs += _dir_hints(body, base)
    if ran_script or capable:
        out_dirs += mk_dirs
    if opaque_control or any(sep not in ("", "&&") for sep, _ in segments):
        for op in ops:
            op.conditional = True             # 复合调用成功不能证明被 || / ; / 管道掩盖的前件成功
    return ops, capable, undetermined, touched, {"probed": probe_hits, "out_dirs": list(dict.fromkeys(out_dirs)),
                                                 "unknown_scripts": unknown_scripts, "script_mentions": script_mentions,
                                                 "unsupported_execution": script_unsupported}


def shell_file_ops(cmd: str, cwd: object, scripts: dict[str, Any], out: str = "") -> list[FileOp]:
    return _shell_analyze(cmd, cwd, scripts, out)[0]


def _note_touched(detail: dict[str, Any], touched: list[str], ops: list[FileOp]) -> None:
    """Only possible effects enter this compatibility bucket; pure mentions must not be state barriers."""
    tch = sorted(set(touched))
    if tch:
        detail["effect_candidates"] = sorted(set(detail.get("effect_candidates") or []) | set(tch))
        detail["touched"] = sorted(set(detail.get("touched") or []) | set(tch))


def _admit_ops(ops: list[FileOp], detail: dict[str, Any], *, succeeded: bool) -> list[FileOp]:
    """One admission rule for both transcript formats; binding is not operation proof."""
    admitted = []
    for op in ops:
        basis = op.proof.operation_basis if op.proof else (
            "native_tool" if op.via in {"tool", "inject", "image"} else
            "supported_shell" if op.via == "shell" else "output_locator" if op.via == "stdout" else "legacy")
        established = succeeded and not op.conditional and basis in CONFIRMED_BASES
        delivery = ("dependency" if op.dep else "content" if op.op == "read" and (op.content is not None or op.seen)
                    else "unknown" if op.op == "read" else "none")
        op.proof = FileProof(basis, "confirmed" if established else "unknown", delivery,
                             "full" if op.content is not None and (op.op != "read" or op.full) else
                             "partial" if op.content is not None or op.seen else "unknown",
                             op.proof.rule if op.proof else op.via + ":" + op.op)
        if established:
            admitted.append(op)
        elif op.op == "read":
            detail.setdefault("read_candidates", []).append({"path": op.path, "via": op.via,
                "start": op.start, "n": op.n, "seen": [list(row) for row in op.seen] if op.seen else None,
                "proof": proof_payload(op.proof)})
        else:
            _note_touched(detail, [op.path], [])
    return admitted


# ═══════════════ 工具 → 动作 ═══════════════

def _text_of(raw: object) -> str:
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        return "\n".join(str(x.get("text", "")) for x in raw if isinstance(x, dict))
    return ""


_HITLINE = re.compile(r"^(?:(?P<p>[^:\n]+?):)?(?P<ln>\d+)[:-](?P<t>.*)$")


def _grep_ops(inp: dict[str, Any], out: str, cwd: object) -> list[FileOp]:
    root = _resolve(inp.get("path"), _resolve(cwd, None)) if inp.get("path") else _resolve(cwd, None)
    single = root if root and re.search(r"\.\w{1,6}$", root) else None
    base = root if single is None else posixpath.dirname(single)
    hits: dict[str, list[tuple[int, str]]] = {}
    for line in out.splitlines():
        if single is not None and (m1 := _LINEONLY.match(line)):
            hits.setdefault(single, []).append((int(m1.group(1)), line[m1.end():]))
            continue
        m = _HITLINE.match(line)
        if not m or not m.group("p"):
            continue
        p = _resolve(m.group("p"), base)
        if p:
            hits.setdefault(p, []).append((int(m.group("ln")), m.group("t")))
    ops: list[FileOp] = []
    for p, raw_pairs in hits.items():
        pairs = sorted({num: t for num, t in raw_pairs}.items())
        run: list[tuple[int, str]] = []
        for num, t in pairs:
            if run and num != run[-1][0] + 1:
                ops.append(FileOp("read", p, "tool", start=run[0][0], n=len(run), seen=tuple(run)))
                run = []
            run.append((num, t))
        if run:
            ops.append(FileOp("read", p, "tool", start=run[0][0], n=len(run), seen=tuple(run)))
    return ops


def _attach_single_cat(tgt: str, out: str, ops: list[FileOp], cwd: object, cmd: str) -> None:
    """整条命令就是一次 cat:全文进了上下文。目标以 _shell_analyze 沿 cd 链解析出的那条读为准 ——
    0723 里 `cd 安卓工程 && cat common.gradle` 曾被按记录 cwd 记到工程根下,还带着全文(幽灵路径的大头)。
    没对上且命令里没有 cd,才按记录 cwd 解析;有 cd 却对不上就放弃,不猜。"""
    tq = tgt.replace("\\", "/")
    nt = _norm_abs(tq) if (tq.startswith("/") or (len(tq) > 1 and tq[1] == ":")) else tq.lstrip("./")
    tail = "/" + nt.lstrip("/")
    reads = [o for o in ops if o.op == "read" and not o.dep
             and (o.path == nt or o.path.endswith(tail))]
    if len(reads) == 1:
        reads[0].content, reads[0].full = out, True
        return
    if re.search(r"(^|[;&|\s])cd\s", cmd):
        return
    p = _resolve(tgt, _resolve(cwd, None))
    if p:
        ops.append(FileOp("read", p, "shell", content=out, full=True))


def _attach_stdout(cmd: str, text: str, out: str, ops: list[FileOp]) -> None:
    """把 shell 读的 stdout 对账到读记录上:grep -n 的命中行 / head 前缀。
    只在能唯一归属时才认(单一内容读目标),对不上就不动 —— 宁可漏。"""
    reads = [o for o in ops if o.op == "read" and not o.dep and o.content is None]
    if len(reads) != 1 or not out.strip() or out.lower().startswith(_ERRISH):
        return
    target = reads[0]
    segs = [_head_word([t[0] for t in _tokenize(s) if t[2] == ""]) for s in _split_segments(text)]
    grep_n = any(h in ("grep", "rg", "egrep", "fgrep") and any(a.startswith("-") and "n" in a for a in args)
                 for h, args in segs)
    if grep_n:
        pairs = []
        for ln in out.splitlines():
            m = _HITLINE.match(ln)
            if m and (not m.group("p") or target.path.endswith(m.group("p").replace("\\", "/").lstrip("./"))):
                pairs.append((int(m.group("ln")), m.group("t")))
        if pairs:
            target.seen = tuple(pairs)
        return
    head_n = next((int(a[1:]) if a[1:].isdigit() else None
                   for h, args in segs if h == "head" for a in args if a.startswith("-")), None)
    if head_n is None and target.start == 1 and target.n:
        head_n = target.n                        # head -N <path> / Get-Content -TotalCount N
    if head_n:
        lines = out.split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        if 0 < len(lines) <= head_n:
            target.start, target.n = 1, len(lines)
            target.seen = tuple((i + 1, t) for i, t in enumerate(lines))


def _basic_detail(name: str, inp: dict[str, Any]) -> dict[str, Any]:
    """成败都要留的调用摘要 —— 调查 agent 定"grep 到过没 / 构建跑了什么"靠它。"""
    if name in ("Bash", "PowerShell"):
        return {"cmd": " ".join(str(inp.get("command") or "").split())[:200]}
    if name in ("Grep", "Glob"):
        return {"pattern": inp.get("pattern"), "path": inp.get("path")}
    if name == "WebFetch":
        return {"url": inp.get("url")}
    if name == "Read":
        return {"path": inp.get("file_path")}
    return {}


_NUMBERED = re.compile(r"^\s*(\d+)\t(.*)$")
_IMAGE_EXT = re.compile(r"\.(?:jpe?g|png|webp|gif|bmp|pdf)$", re.I)


def _numbered_lines(out: str) -> list[tuple[int, str]]:
    """Read 工具结果正文的 cat -n 形态("     12\\t内容")→ [(行号, 内容)];非该形态返回空。"""
    rows: list[tuple[int, str]] = []
    for line in (out or "").splitlines():
        m = _NUMBERED.match(line)
        if m is None:
            if rows:
                break                       # 正文之后的系统提示 / 截断说明,不再是文件行
            continue
        rows.append((int(m.group(1)), m.group(2)))
    return rows


def _file_ops(name: str, inp: dict[str, Any], out: str, tur: Any, cwd: object,
              scripts: dict[str, Any], ts: str | None = None,
              update_scripts: bool = True) -> tuple[list[FileOp], dict[str, Any]]:
    """成功的调用 → 文件读写 + 附加细节。"""
    detail: dict[str, Any] = _basic_detail(name, inp)
    ops: list[FileOp] = []
    cond_ops: list[FileOp] = []
    if name == "Read":
        f = tur.get("file") if isinstance(tur, dict) else None
        if isinstance(f, dict) and isinstance(f.get("content"), str) and f.get("numLines"):
            p = _resolve(f.get("filePath"), _resolve(cwd, None))
            if p:
                full = (f.get("startLine") or 1) == 1 and f.get("numLines") == f.get("totalLines")
                ops.append(FileOp("read", p, "tool", content=f["content"], full=bool(full),
                                  start=f.get("startLine") or 1, n=f["numLines"]))
        elif isinstance(tur, dict):
            detail["result_type"] = tur.get("type")
            # 图片 / PDF:结果没有正文,读却真实发生(修复方看双端拼图 MainActivity.jpeg 才知道按钮是 ROLL);
            # 记 via=image 的依赖读,不立版本 —— 丢了它,「修复侧多看到的截图」就数不到
            ftype = str((f or {}).get("type") or "") if isinstance(f, dict) else ""
            p = _resolve(inp.get("file_path"), _resolve(cwd, None))
            if p and (tur.get("type") == "image" or ftype.startswith(("image/", "application/pdf"))):
                ops.append(FileOp("read", p, "image", dep=True))
        elif _IMAGE_EXT.search(str(inp.get("file_path") or "")):
            # 没有边车、结果正文也空(DiceRoller #4431 Read MainActivity.jpeg):只剩扩展名可认
            p = _resolve(inp.get("file_path"), _resolve(cwd, None))
            if p:
                ops.append(FileOp("read", p, "image", dep=True))
        else:
            # 没有 toolUseResult 边车(服务端切片、Workflow 子代理转录):从结果正文的 "N\t内容" 行号
            # 前缀还原。DiceRoller 0903 生成方读 MainActivity.kt / activity_main.xml 的两条 Read 曾因此消失,
            # 调查员只能说"无法确认读过"。缺边车时仅连续无额外正文的从头默认读可作全文。
            numbered = _numbered_lines(out)
            p = _resolve(inp.get("file_path"), _resolve(cwd, None))
            if p and numbered:
                start = numbered[0][0]
                contiguous = [n for n, _ in numbered] == list(range(start, start + len(numbered)))
                full = (start == 1 and not inp.get("offset") and not inp.get("limit") and contiguous
                        and all(_NUMBERED.match(line) for line in out.splitlines() if line.strip()))
                ops.append(FileOp("read", p, "tool", content="\n".join(t for _, t in numbered) if full else None,
                                  seen=tuple(numbered), full=full, start=start, n=len(numbered)))
    elif name == "Write":
        p = _resolve(inp.get("file_path"), _resolve(cwd, None))
        if p:
            content = str(inp.get("content") or "")
            ops.append(FileOp("write", p, "tool", content=content,
                              created="created successfully" in (out or "").lower()))
    elif name in ("Edit", "MultiEdit"):
        p = _resolve(inp.get("file_path"), _resolve(cwd, None))
        edits = inp.get("edits") if name == "MultiEdit" else [inp]
        for e in edits or []:
            if p and isinstance(e, dict):
                ops.append(FileOp("edit", p, "tool", old=str(e.get("old_string") or ""),
                                  new=str(e.get("new_string") or ""),
                                  replace_all=bool(e.get("replace_all"))))
    elif name == "NotebookEdit":
        p = _resolve(inp.get("notebook_path"), _resolve(cwd, None))
        if p:
            ops.append(FileOp("write", p, "tool"))
    elif name in ("Bash", "PowerShell"):
        cmd = str(inp.get("command") or "")
        ops, capable, undetermined, touched, hints = _shell_analyze(cmd, cwd, scripts, out, ts=ts, success=True)
        # 挂可对账输出;条件读仍须退候选,通用 stdout 不能证明它来自哪个分支。
        tgt = _clean_single_cat(cmd)
        if tgt and out.strip() and not out.lower().startswith(_ERRISH):
            _attach_single_cat(tgt, out, ops, cwd, cmd)
        else:
            _attach_stdout(cmd, _strip_heredocs(cmd.replace("\\\n", " "))[0], out, ops)
        cond_ops = [o for o in ops if o.conditional and o.op != "read"]
        if cond_ops:
            # 条件分支里的效应不进正式状态:只记候选路径(build_ledger 挂成「条件分支,是否执行未知(候选写)」),
            # 评审反例:false && 写 A,文件没变,账本却多出一版 b 和一次「实录外修改」
            detail["conditional"] = sorted({o.path for o in cond_ops})
            _admit_ops(cond_ops, detail, succeeded=True)
            ops = [o for o in ops if not (o.conditional and o.op != "read")]
        # 通用 stdout 挂接无法区分分支输出和后续 echo/另一路输出,不能给条件读背书。
        uncertain_reads = [o for o in ops if o.conditional and o.op == "read"]
        if uncertain_reads:
            detail["conditional_reads"] = sorted({o.path for o in uncertain_reads})
            _admit_ops(uncertain_reads, detail, succeeded=True)
            ops = [o for o in ops if o not in uncertain_reads]
        if capable:
            detail["write_capable"] = True
        if not ops:
            why = _unresolved_reason(cmd)
            if why:
                detail["unresolved"] = why      # 不许静默:解析不了的读写要能报出自己
        if hints.get("unknown_scripts"):
            # 已识别出脚本落盘/其他读写,不代表同调用里运行该脚本的效应也已解析。
            # 只保留执行处的知识缺口;不提前使用本调用随后登记的脚本正文推断目标。
            detail["unknown_scripts"] = list(dict.fromkeys(hints["unknown_scripts"]))
            unknown = "脚本执行效应未解析(静态解析未关联到执行用的脚本正文)"
            detail["unresolved"] = (detail["unresolved"] + "；" if detail.get("unresolved") else "") + unknown
        if undetermined and "unresolved" not in detail:
            detail["unresolved"] = "脚本字面量方向不明"
        _note_touched(detail, touched, ops)
        for key in ("script_mentions", "unsupported_execution"):
            if hints.get(key):
                detail[key] = list(dict.fromkeys(hints[key]))
        if hints["probed"]:
            detail["probed"] = hints["probed"]
        if hints["out_dirs"]:
            detail["out_dirs"] = hints["out_dirs"]
    elif name == "Grep":
        mode = str(inp.get("output_mode") or "files_with_matches")
        detail["mode"] = mode
        if mode == "content":
            ops = _grep_ops(inp, out, cwd)
    elif name in ("Agent", "Task"):
        detail.update({"name": inp.get("name"), "subagent_type": inp.get("subagent_type"),
                       "description": inp.get("description"), "model": inp.get("model"),
                       "prompt": inp.get("prompt")})
        # Task 结果边车里的 agentId 是实锤的派发边:并行派发的几条派发词开头常常一模一样
        # (仓库根目录 + 语言 + 轮次),按开头对齐会把名片挂错转录
        aid = tur.get("agentId") if isinstance(tur, dict) else None
        if aid:
            detail["child"] = "agent-" + str(aid)
    elif name == "SendMessage":
        detail.update({"to": inp.get("to") or inp.get("recipient"),
                       "summary": inp.get("summary"),
                       "text": inp.get("message") or inp.get("content")})
    elif name == "Skill":
        detail["skill"] = inp.get("skill")
    ops = _admit_ops(ops, detail, succeeded=True)
    if update_scripts:
        _update_scripts(scripts, ops + cond_ops, ts)
    return ops, detail


def _kind_of(name: str, ops: list[FileOp]) -> str:
    if name in ("Agent", "Task"):
        return "dispatch"
    if name == "SendMessage":
        return "message"
    if name == "Skill":
        return "skill"
    if name in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        return "write"                        # 失败的写也是写的企图,只是不占版本号
    if any(o.op in ("write", "edit", "delete") for o in ops):
        return "write" if any(o.op != "delete" for o in ops) else "delete"
    if any(o.op == "read" for o in ops):
        return "read"
    return "other"


def _to_ev(op: FileOp, agent: str, ts: str, seq: int, stage: str | None = None,
           *, use_ts: str | None = None, done_ts: str | None = None) -> Ev:
    kind = {"read": "read", "delete": "delete", "edit": "edit",
            "write": "wfull" if op.content is not None else ("wconcat" if op.sources else "wopaque")}[op.op]
    return Ev(ts, seq, kind, op.path, agent, content=op.content, old=op.old, new=op.new,
              replace_all=op.replace_all, start=op.start, n=op.n, full=op.full, dep=op.dep,
              via=op.via, seen=op.seen, stage=stage, created=op.created, sources=op.sources,
              conditional=op.conditional, use_ts=use_ts, done_ts=done_ts,
              proof=op.proof or (FileProof("native_tool", "confirmed", "content" if op.content is not None else "dependency",
                                          "full" if op.full else "partial", "injected input") if op.via == "inject" else None))


#: 管线技能在阶段**收尾**时调 ``a2h mark-stage``:这些 mark 的时刻是该阶段的结束(DiceRoller 0903 实测,
#: 五个管线 mark 都落在对应归属戳末条之后 6–100 秒);a2h-init(init_helper)与 ecat-refine(ecat 插件)
#: 是在开始时打的。把结束 mark 当起点用,会把整个 verify 段(含 visual verify)算进 execute —— 踩过
_END_MARK_STAGES = frozenset({"a2h-spec", "a2h-plan", "a2h-execute", "a2h-verify", "a2h-retrospect", "a2h-build"})


def stage_intervals_from_marks(marks: list[Any]) -> list[dict[str, Any]]:
    """run 级阶段标记 → codex.stage_at 吃的区间表 [{stage, start_ts, end_ts}],时刻已归一(ts_norm)。
    两种来源形状都收:Go 运行时 stage-marks.json 的 [{stage, ts}],导出包 manifest 的 [[ts, stage]]。
    结束 mark 的阶段占 (上一边界, mark];起始 mark 的阶段占 [mark, 下一边界);起始 mark 后面紧跟别的
    阶段的结束 mark 时(a2h-init 只有几秒),那一段归结束 mark 的阶段。"""
    rows: list[tuple[str, str]] = []
    for m in marks or []:
        if isinstance(m, dict) and m.get("stage") and m.get("ts"):
            rows.append((ts_norm(str(m["ts"])), str(m["stage"])))
        elif isinstance(m, (list, tuple)) and len(m) >= 2:
            rows.append((ts_norm(str(m[0])), str(m[1])))
    rows.sort(key=lambda x: x[0])
    out: list[dict[str, Any]] = []
    prev: str | None = None
    for i, (ts, st) in enumerate(rows):
        nxt = rows[i + 1] if i + 1 < len(rows) else None
        if st in _END_MARK_STAGES:
            out.append({"stage": st, "start_ts": prev or ts, "end_ts": ts})
            prev = ts
        elif nxt is not None and nxt[1] in _END_MARK_STAGES:
            prev = ts
        else:
            out.append({"stage": st, "start_ts": ts, "end_ts": nxt[0] if nxt else None})
            prev = nxt[0] if nxt else ts
    return out


def fix_boundary(intervals: list[dict[str, Any]]) -> str | None:
    """用户口径(2026-09-04):execute 阶段结束之后的都是修复。结束时刻 = 最后一段 a2h-execute 的 end_ts
    (结束 mark 的时刻);没有 execute 段 = 还没结束 → None(退回按阶段名判)。"""
    ends = [s for s in intervals if str(s.get("stage")) == "a2h-execute" and s.get("end_ts")]
    return str(ends[-1]["end_ts"]) if ends else None


def _walk(path: str, agent_id: str, session: str, seq: list[int],
          scripts: dict[str, Any], stage_intervals: list[dict[str, Any]] | None = None) -> AgentRec:
    rec = AgentRec(id=agent_id, session=session)
    pend: dict[str, tuple[str, str, Any, Any, int, str | None, int]] = {}   # id -> (ts, name, inp, cwd, 行号, 阶段, 块号)

    def nxt() -> int:
        seq[0] += 1
        return seq[0]

    last_text: str | None = None
    is_sub = not agent_id.startswith("__main__")
    # 管线阶段来自 harness 给每条记录盖的归属戳(attributionSkill,取冒号后),无戳的记录沿用上一枚;
    # 子 agent 自己的第一枚戳就是它的阶段(没有戳时由 build_ledger 继承派发时父的阶段)。
    # 整份转录一枚戳都还没见到时,退回 run 级阶段区间按时间落阶段:ECAT 对抗循环、reviewer、
    # loop engine 续接的 worker 都是 Driver 直接起的会话,记录上没有戳,但 stage-marks 有它们的时段
    from migloop.adapters import codex
    from migloop.adapters.claude import PIPELINE_SKILLS
    cur_stage: str | None = None

    def stage_now(ts: str) -> str | None:
        if cur_stage is not None or not stage_intervals:
            return cur_stage
        return codex.stage_at(stage_intervals, ts_norm(ts))      # 区间表的时刻已归一,记录时刻同样归一再比
    with open(path, encoding="utf-8", errors="ignore") as stream:
        for line_no, line in enumerate(stream):
            try:
                r = json.loads(line)
            except Exception:
                continue
            ts = str(r.get("timestamp") or "")
            cwd = r.get("cwd")
            attr = str(r.get("attributionSkill") or "").split(":")[-1]
            # 管线词表之外、但修复方口径认得的阶段名(ecat-*、*-verify 等)也算戳,别把它们当没戳
            if attr in PIPELINE_SKILLS or (attr and stage_order(attr) is not None):
                cur_stage = attr
                if is_sub and rec.stage is None:
                    rec.stage = attr
            if r.get("isCompactSummary"):
                rec.actions.append(Action(ts, nxt(), "compact", "compact"))
            m = r.get("message")
            if not isinstance(m, dict):
                continue
            content = m.get("content")
            blocks = content if isinstance(content, list) else \
                [{"type": "text", "text": content}] if isinstance(content, str) else []
            said: list[str] = []
            thought: list[str] = []
            utexts: list[str] = []
            text_blocks: dict[str, int] = {}
            for block_index, b in enumerate(blocks):
                if not isinstance(b, dict):
                    continue
                text_blocks.setdefault(str(b.get("type")), block_index)
                if b.get("type") == "text" and m.get("role") == "user":
                    utexts.append(str(b.get("text") or ""))       # 整条记录合起来归类(见下)
                elif b.get("type") == "text" and m.get("role") == "assistant":
                    if str(b.get("text") or "").strip():
                        last_text = str(b["text"]).strip()
                        said.append(last_text)
                elif b.get("type") == "thinking" and str(b.get("thinking") or "").strip():
                    thought.append(str(b["thinking"]).strip())
                elif b.get("type") == "tool_use":
                    pend[str(b.get("id"))] = (ts, str(b.get("name")), b.get("input") or {}, cwd, line_no,
                                               stage_now(ts), block_index)
                elif b.get("type") == "tool_result" and str(b.get("tool_use_id")) in pend:
                    tuid = str(b.get("tool_use_id"))
                    uts, name, inp, ucwd, use_line, stage, blk = pend.pop(tuid)
                    ok = not b.get("is_error", False)
                    ops: list[FileOp] = []
                    detail: dict[str, Any] = _basic_detail(name, inp)
                    if ok:
                        ops, detail = _file_ops(name, inp, _text_of(b.get("content")),
                                                r.get("toolUseResult"), ucwd, scripts, ts=uts)
                    if name in ("Bash", "PowerShell"):
                        cmd_text = str(inp.get("command") or "")
                        if not ok:
                            # 失败不等于没改:`printf x > A; exit 1` 已经写了。不立版本,目标记成候选,指针保留
                            f_ops = _shell_analyze(cmd_text, ucwd, scripts, "", ts=uts)[0]
                            detail["unresolved"] = "命令失败,效应未知(可能已部分执行)"
                            tch = sorted({o.path for o in f_ops if o.op != "read"})
                            if tch:
                                detail["touched"] = tch
                        # 脚本字面量里的正文是「agent 写下了这段话」的证据,与命令成败无关
                        # (vv-t1-A01 落盘 fill.py 的 heredoc 被标 is_error,缺陷单正文就全丢了)
                        partials = [pw for body in _strip_heredocs(cmd_text.replace("\\\n", " "))[1]
                                    for pw in _py_partial_writes(body)]
                        if partials:
                            detail["partials"] = partials
                        mentions, trunc = _path_mentions(cmd_text, scripts, ucwd, uts, audit=detail)
                        if ok:
                            # 输出里点名的文件(git status 的 modified、ls、构建报错、grep -rl):命令行里没有,输出里有
                            out_full = _text_of(b.get("content"))
                            om, otrunc = _path_mentions(out_full, {}, ucwd, uts, where="out", audit=detail)
                            head_cmd = " ".join(cmd_text.split())[:60]
                            om = [(t, (head_cmd + " ⇒ " + c)[:150], ab, w, k) for t, c, ab, w, k in om]
                            mentions, trunc = mentions + om, trunc + otrunc
                        if mentions:
                            detail["mentions"] = mentions
                        if trunc:
                            detail["mentions_truncated"] = trunc
                    elif name in ("Grep", "Glob") and ok:
                        out_full = _text_of(b.get("content"))
                        om, otrunc = _path_mentions(out_full, {}, ucwd, uts, where="out", audit=detail)
                        if om:
                            detail["mentions"] = om
                        if otrunc:
                            detail["mentions_truncated"] = otrunc
                    else:
                        # 派发词点名了谁、发消息说了谁、写别的文件时清单里列了谁:也是「转录里提到它」的行,词法层要有入口
                        im = _input_text_mentions(name, inp, ucwd, uts, audit=detail)
                        if im[0]:
                            detail["mentions"] = im[0]
                        if im[1]:
                            detail["mentions_truncated"] = im[1]
                    if not ok and name in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
                        target = _resolve(inp.get("file_path") or inp.get("notebook_path"), _resolve(ucwd, None))
                        if target:
                            detail["touched"] = [target]
                            detail["unresolved"] = "调用失败,效应未知(可能已部分执行)"
                    act = Action(uts, nxt(), name, _kind_of(name, ops), ok=ok, detail=detail,
                                 src=(path, use_line, line_no), tuid=tuid, stage=stage, done_ts=ts, blk=blk)
                    for op in ops:
                        # 写在调用时刻发生,读的内容在结果时刻进上下文
                        ev = _to_ev(op, agent_id, ts if op.op == "read" else uts, nxt(), stage,
                                    use_ts=uts, done_ts=ts)
                        act.files.append(FileRef("read" if op.op == "read" else
                                                 "delete" if op.op == "delete" else "write",
                                                 op.path, ev))
                    rec.actions.append(act)
            if utexts and m.get("role") == "user":
                raw = "\n".join(utexts)
                tm = _TEAM.match(raw)
                is_sub = not agent_id.startswith("__main__")
                if tm or (is_sub and rec.prompt is None and raw.strip()
                          and not raw.lstrip().startswith("<")):
                    # teammate-message 是收件;子代理没包装的首条文本就是派发词本身
                    text = raw[tm.end():] if tm else raw
                    text = re.sub(r"\s*</teammate-message>\s*$", "", text)
                    ib_detail: dict[str, Any] = {"from": tm.group(1) if tm else "dispatcher",
                                                 "summary": tm.group(2) if tm else None, "text": text}
                    ib_m, ib_t = _path_mentions(text, {}, cwd, ts, where="text", cls="text", audit=ib_detail)
                    if ib_m:
                        ib_detail["mentions"] = ib_m
                    if ib_t:
                        ib_detail["mentions_truncated"] = ib_t
                    rec.actions.append(Action(ts, nxt(), "inbox", "inbox", detail=ib_detail,
                                              src=(path, line_no, line_no), stage=stage_now(ts),
                                              blk=text_blocks.get("text", 0)))
                    if rec.prompt is None and is_sub:
                        rec.prompt = text
                else:
                    ukind, udetail, uop = _classify_user_text(raw, cwd)
                    if ukind:
                        um, ut = _path_mentions(raw, {}, cwd, ts, where="text", cls="text", audit=udetail)
                        if um:
                            udetail["mentions"] = um
                        if ut:
                            udetail["mentions_truncated"] = ut
                        uact = Action(ts, nxt(), ukind, ukind, detail=udetail,
                                      src=(path, line_no, line_no), stage=stage_now(ts),
                                      blk=text_blocks.get("text", 0))
                        if uop is not None:
                            uact.files.append(FileRef("read", uop.path,
                                                      _to_ev(uop, agent_id, ts, nxt(), stage_now(ts))))
                        rec.actions.append(uact)
            # agent 自己说的话 / 想的话:一条记录一条索引,喂养下一版;全文按指针展开
            for kind, texts in (("say", said), ("think", thought)):
                if texts:
                    full = "\n".join(texts)
                    st_detail: dict[str, Any] = {"text": _head(full)}
                    st_m, st_t = _path_mentions(full, {}, cwd, ts, where="text", cls="text", audit=st_detail)
                    if st_m:
                        st_detail["mentions"] = st_m
                    if st_t:
                        st_detail["mentions_truncated"] = st_t
                    rec.actions.append(Action(ts, nxt(), kind, kind, detail=st_detail,
                                              src=(path, line_no, line_no), stage=stage_now(ts),
                                              blk=text_blocks.get("thinking" if kind == "think" else "text", 0)))
    for tuid, (uts, name, inp, ucwd, use_line, stage, blk) in pend.items():
        # 没等到结果的调用可能已经产生副作用:指针、tool_use_id、提及都保留,标 unfinished
        detail = _basic_detail(name, inp if isinstance(inp, dict) else {})
        detail["unfinished"] = True
        if isinstance(inp, dict):
            possible, more = _file_ops(name, inp, "", None, ucwd, scripts, ts=uts, update_scripts=False)
            paths = {o.path for o in possible if o.op != "read"} | set(more.get("conditional") or [])
            if paths:
                detail["touched"] = sorted(paths)
                detail["unresolved"] = "调用未完成,效应未知"
            im, it = _input_text_mentions(name, inp, ucwd, uts, audit=detail)
            if im:
                detail["mentions"] = im
            if it:
                detail["mentions_truncated"] = it
        if name in ("Bash", "PowerShell") and isinstance(inp, dict):
            mentions, trunc = _path_mentions(str(inp.get("command") or ""), scripts, ucwd, uts, audit=detail)
            if mentions:
                detail["mentions"] = mentions
            if trunc:
                detail["mentions_truncated"] = trunc
        rec.actions.append(Action(uts, nxt(), name, "other", ok=None, detail=detail,
                                  src=(path, use_line, use_line), tuid=tuid, stage=stage, blk=blk))
    rec.result = last_text
    return rec


def collect_cc(main_jsonl: str, seq: list[int],
               stage_intervals: list[dict[str, Any]] | None = None,
               scripts: ScriptTable | None = None) -> dict[str, AgentRec]:
    """CC 会话(主线 + subagents/)→ {agent_id: AgentRec}。seq 跨会话共用,保证全局可排序。
    stage_intervals = run 级阶段区间(stage_intervals_from_marks),给没有归属戳的会话按时间落阶段。"""
    sid8 = os.path.basename(main_jsonl)[:8]
    sub = os.path.splitext(main_jsonl)[0] + "/subagents"
    sub_files = sorted(glob.glob(os.path.join(sub, "*.jsonl"))) if os.path.isdir(sub) else []
    # 脚本表先扫全池(带写入时刻),再走转录:谁先走谁后走都不该影响「跑的时候脚本长什么样」
    if scripts is None:
        scripts = _prescan_scripts([main_jsonl, *sub_files])
    main_id = f"__main__:{sid8}"
    agents = {main_id: _walk(main_jsonl, main_id, sid8, seq, scripts, stage_intervals)}
    for fn in sub_files:
        stem = os.path.splitext(os.path.basename(fn))[0]
        # 时间兜底只给根会话:子 agent 没戳时由 build_ledger 继承派发那一笔的阶段(戳是 skill 粒度,
        # run 级区间是 stage 粒度 —— 直接按时间落会把 execute 期间派的 visual-verify 子代理误成 execute)
        agents[stem] = _walk(fn, stem, sid8, seq, scripts)
    return agents


def collect_cc_pool(roots: list[str], seq: list[int],
                    stage_intervals: list[dict[str, Any]] | None = None) -> dict[str, AgentRec]:
    """跨会话池共用同一份只读脚本历史,不是每个根会话从空表重来。"""
    paths = list(dict.fromkeys(p for root in roots for p in
                              [root, *sorted(glob.glob(os.path.splitext(root)[0] + "/subagents/*.jsonl"))]))
    scripts = _prescan_scripts(paths)
    agents: dict[str, AgentRec] = {}
    for root in roots:
        agents.update(collect_cc(root, seq, stage_intervals, scripts=scripts))
    return agents


def _input_text_mentions(name: str, inp: dict[str, Any], cwd: object, ts: str,
                         audit: dict[str, Any] | None = None) -> tuple[list[tuple[str, str, str | None, str, str]], int]:
    """非命令类调用的输入里提到的路径:派发词(Agent / Task 的 prompt)→ dispatch;发消息 → message;
    Write / Edit / MultiEdit 的正文 → content(写别的文件时清单里列了它)。Read / Grep / Glob 的路径参数已是读,不重复。"""
    if name in ("Agent", "Task"):
        return _path_mentions(str(inp.get("prompt") or ""), {}, cwd, ts, where="dispatch", cls="dispatch", audit=audit)
    if name == "SendMessage":
        return _path_mentions(str(inp.get("message") or inp.get("content") or ""), {}, cwd, ts,
                              where="message", cls="message", audit=audit)
    if name == "Write":
        return _path_mentions(str(inp.get("content") or ""), {}, cwd, ts, where="content", cls="content", audit=audit)
    if name in ("Edit", "MultiEdit"):
        edits = inp.get("edits") if name == "MultiEdit" else [inp]
        body = "\n".join(str(e.get("new_string") or "") + "\n" + str(e.get("old_string") or "")
                         for e in (edits or []) if isinstance(e, dict))
        return _path_mentions(body, {}, cwd, ts, where="content", cls="content", audit=audit)
    return [], 0


def _prescan_scripts(paths: list[str]) -> ScriptTable:
    """全池脚本效应按发起时刻回放,正文按完成时刻可用。未知覆盖/删除/失败/未完成也入表,
    但只写未知墓碑;正式收集不能再修改这份表。行级预筛降低解 JSON 的量。"""
    events: list[tuple[str, int, str, dict[str, Any], Any, str, bool]] = []
    order = 0
    for p in paths:
        if not os.path.isfile(p):
            continue
        pending: dict[str, tuple[str, str, dict[str, Any], Any]] = {}
        with open(p, encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                if '"tool_result"' in line:
                    if not pending or not any(t in line for t in pending):
                        continue
                elif not (_SCRIPT_EXT_HINT.search(line) and '"tool_use"' in line):
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                m = r.get("message")
                blocks = m.get("content") if isinstance(m, dict) else None
                if not isinstance(blocks, list):
                    continue
                ts = ts_norm(str(r.get("timestamp") or ""))
                for b in blocks:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "tool_use":
                        name, inp = str(b.get("name")), b.get("input")
                        if not isinstance(inp, dict):
                            continue
                        target = str(inp.get("file_path") or "")
                        cmd = str(inp.get("command") or "")
                        if ((name in ("Write", "Edit", "MultiEdit") and _SCRIPT_RUN.search(target))
                                or (name in ("Bash", "PowerShell") and _SCRIPT_EXT_HINT.search(cmd))):
                            pending[str(b.get("id"))] = (ts, name, inp, r.get("cwd"))
                    elif b.get("type") == "tool_result" and str(b.get("tool_use_id")) in pending:
                        ev = pending.pop(str(b.get("tool_use_id")))
                        order += 1
                        events.append((ev[0], order, ev[1], ev[2], ev[3], ts, not b.get("is_error", False)))
        for ev in pending.values():
            order += 1
            events.append((ev[0], order, ev[1], ev[2], ev[3], ev[0], False))
    table = ScriptTable()
    for ts, _o, name, inp, cwd, done, ok in sorted(events, key=lambda e: (e[0], e[1])):
        ops, detail = _file_ops(name, inp, "", None, cwd, table, ts=ts, update_scripts=False)
        ops += [FileOp("write", p, conditional=True) for p in detail.get("conditional", [])]
        if not ok:
            for op in ops:
                op.conditional = True                  # 失败/未完成也可能已部分覆写,不能继续借用旧正文
        _update_scripts(table, ops, ts, done)
    table.frozen = True
    return table


# ═══════════════ codex 侧:与 CC 同一套语义 ═══════════════
#
# rollout 记录 = {type, timestamp, payload}。exec 的输入是内嵌 JS(tools.exec_command /
# tools.apply_patch),输出是 "Script completed|failed … Output:\n" + JSON 块({exit_code, output});
# spawn_agent / send_message / wait_agent 是 collaboration 命名空间的 function_call。
# 子 rollout 用 spawn_agent(fork_turns=all)把父的对话整段复制进来 —— 记录 id 相同,按 id 去重。

_ENCRYPTED = re.compile(r"^gAAAA[A-Za-z0-9_\-]{40,}$")


def _json_args(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.lstrip().startswith("{"):
        try:
            j = json.loads(raw)
            return j if isinstance(j, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _codex_stdout(out_text: str) -> tuple[bool, str]:
    """exec 外壳 → (成败, 真正的 stdout)。"""
    ok = not out_text.lstrip().startswith("Script failed")
    idx = out_text.find("Output:\n")
    body = out_text[idx + len("Output:\n"):] if idx >= 0 else out_text
    body = body.lstrip("\n")
    if body.startswith("{"):
        try:
            j = json.loads(body)
            if isinstance(j, dict) and "output" in j:
                if isinstance(j.get("exit_code"), int) and j["exit_code"] != 0:
                    ok = False
                return ok, str(j.get("output") or "")
        except json.JSONDecodeError:
            pass
    return ok, body


def _patch_ops(patch: str, cwd: object) -> list[FileOp]:
    """apply_patch(V4A)→ 文件读写:Add File = 全文写,Update File 每个 hunk = edit(与 Edit 工具同档),
    Delete File = 删除;无上下文的纯追加锚不住,降级为内容未知的写。"""
    from migloop.adapters import codex

    header = re.compile(r"^\*\*\* (Add|Update|Delete) File:\s*(.+?)\s*$", re.M)
    matches = list(header.finditer(patch or ""))
    ops: list[FileOp] = []
    for pos, match in enumerate(matches):
        body_end = matches[pos + 1].start() if pos + 1 < len(matches) else len(patch)
        body = patch[match.end():body_end]
        action, raw_path = match.group(1), match.group(2).strip()
        # 不走 codex._resolve_path:它用 os.path.abspath,在 Windows 上会给 posix 路径补盘符
        p = _resolve(raw_path, _resolve(cwd, None))
        if not p:
            continue
        if action == "Add":
            content = "\n".join(line[1:] for line in codex._patch_body_lines(body) if line.startswith("+"))
            ops.append(FileOp("write", p, "tool", content=content + "\n"))
        elif action == "Delete":
            ops.append(FileOp("delete", p, "tool"))
        else:
            for hunk in codex._patch_chunks(body):
                old_lines: list[str] = []
                new_lines: list[str] = []
                for kind, lines in hunk:
                    if kind in ("ctx", "del"):
                        old_lines += lines
                    if kind in ("ctx", "add"):
                        new_lines += lines
                if not old_lines:
                    ops.append(FileOp("write", p, "tool"))
                    continue
                ops.append(FileOp("edit", p, "tool", old="\n".join(old_lines), new="\n".join(new_lines)))
    return ops


def _codex_exec_ops(raw_arg: Any, out_text: str, cwd: object,
                    scripts: dict[str, Any], *, completed: bool = True,
                    ts: str | None = None) -> tuple[list[FileOp], dict[str, Any], bool]:
    """一次 exec:解 JS → shell 命令(复用 CC 的解析 + stdout 对账)+ apply_patch。返回 (ops, detail, ok)。"""
    from migloop.adapters import codex

    if isinstance(raw_arg, str) and raw_arg.lstrip().startswith("{"):
        js = str(codex._decode_arguments(raw_arg).get("input") or raw_arg)
    else:
        js = str(raw_arg or "")
    ok, stdout = _codex_stdout(out_text) if completed else (False, "")
    detail: dict[str, Any] = {}
    ops: list[FileOp] = []
    shell_calls = codex._extract_shell_calls(js, str(cwd) if cwd else None)
    for sc in shell_calls:
        cmd = str(sc.get("command") or "")
        wdir = sc.get("workdir") or cwd
        detail.setdefault("cmd", " ".join(cmd.split())[:200])
        # 单条 shell 调用时 stdout 就是它的:目录 grep / 多文件 head 按 stdout 反证(与 CC 的 Bash 同一套)
        single = len(shell_calls) == 1 and ok
        sub_ops, capable, undetermined, touched, hints = _shell_analyze(cmd, wdir, scripts, stdout if single else "",
                                                                       success=single, ts=ts)
        if capable:
            detail["write_capable"] = True
        if single and not any(not op.conditional for op in sub_ops):
            why = _unresolved_reason(cmd)
            if why:
                detail["unresolved"] = why      # 不许静默(与 CC 同一条规矩)
        if hints.get("unknown_scripts"):
            # 与 CC 一样:其他已解析效应不能覆盖执行脚本的未知效应;跨 shell 调用合并线索。
            detail["unknown_scripts"] = list(dict.fromkeys((detail.get("unknown_scripts") or []) + hints["unknown_scripts"]))
            unknown = "脚本执行效应未解析(静态解析未关联到执行用的脚本正文)"
            if unknown not in (detail.get("unresolved") or ""):
                detail["unresolved"] = (detail["unresolved"] + "；" if detail.get("unresolved") else "") + unknown
        if undetermined and "unresolved" not in detail:
            detail["unresolved"] = "脚本字面量方向不明"
        _note_touched(detail, touched, sub_ops)
        for key in ("script_mentions", "unsupported_execution"):
            if hints.get(key):
                detail[key] = list(dict.fromkeys((detail.get(key) or []) + hints[key]))
        for key in ("probed", "out_dirs"):
            if hints[key]:
                detail[key] = list(dict.fromkeys((detail.get(key) or []) + hints[key]))
        if len(shell_calls) == 1 and ok:
            tgt = _clean_single_cat(cmd)
            if tgt and stdout.strip() and not stdout.lower().startswith(_ERRISH):
                _attach_single_cat(tgt, stdout, sub_ops, wdir, cmd)
            else:
                _attach_stdout(cmd, _strip_heredocs(cmd.replace("\\\n", " "))[0], stdout, sub_ops)
        conditional = {o.path for o in sub_ops if o.conditional and o.op != "read"}
        conditional_reads = {o.path for o in sub_ops if o.conditional and o.op == "read"}
        for key, paths in (("conditional", conditional), ("conditional_reads", conditional_reads)):
            if paths:
                detail[key] = sorted(set(detail.get(key) or []) | paths)
        _admit_ops([o for o in sub_ops if o.conditional], detail, succeeded=ok)
        ops += [o for o in sub_ops if not (o.conditional and (o.op != "read" or o.path in conditional_reads))]
    for patch in codex._extract_apply_patches(js):
        detail.setdefault("cmd", "apply_patch")
        ops += _patch_ops(patch, cwd)
    if not ok:
        detail["touched"] = sorted(set(detail.get("touched") or []) | {o.path for o in ops if o.op != "read"})
        detail["unresolved"] = "调用失败,效应未知(可能已部分执行)" if completed else "调用未完成,效应未知"
    ops = _admit_ops(ops, detail, succeeded=ok) if ok else ops  # retain failed operation kind; caller admits no files
    return ops, detail, ok


def _walk_codex(path: str, agent_id: str, session: str, seq: list[int], scripts: dict[str, Any],
                seen_ids: set[str]) -> AgentRec:
    rec = AgentRec(id=agent_id, session=session)
    is_sub = not agent_id.startswith("__main__")
    pend: dict[str, tuple[str, str, Any, Any, int]] = {}   # call_id -> (ts, name, raw_arg, cwd, 行号)
    cwd: Any = None
    last_text: str | None = None

    def nxt() -> int:
        seq[0] += 1
        return seq[0]

    def text_action(ts: str, line_no: int, text: str, kind: str, detail: dict[str, Any]) -> None:
        mentions, trunc = _path_mentions(text, {}, cwd, ts, where="text", cls="text", audit=detail)
        if mentions:
            detail["mentions"] = mentions
        if trunc:
            detail["mentions_truncated"] = trunc
        # 原始消息 id 不是 tool_use_id;作者只做来源标签,不制造 sender agent/读写边。
        rec.actions.append(Action(ts, nxt(), kind, kind, detail=detail, src=(path, line_no, line_no)))

    with open(path, encoding="utf-8", errors="ignore") as stream:
        for line_no, line in enumerate(stream):
            try:
                r = json.loads(line)
            except Exception:
                continue
            pl = r.get("payload") if isinstance(r.get("payload"), dict) else {}
            ts = str(r.get("timestamp") or "")
            if r.get("type") in ("session_meta", "turn_context") and pl.get("cwd"):
                cwd = pl.get("cwd")
            pid = pl.get("id")
            if r.get("type") == "session_meta":
                base = pl.get("base_instructions")
                base_text = base.get("text") if isinstance(base, dict) else None
                base_id = f"base_instructions:{pid}" if isinstance(pid, str) and pid else None
                if isinstance(base_text, str) and base_text.strip() and (base_id is None or base_id not in seen_ids):
                    if base_id:
                        seen_ids.add(base_id)
                    text_action(ts, line_no, base_text, "system", {
                        "from": "session_meta.base_instructions", "text": base_text, "summary": None,
                        "source_event_type": "base_instructions", "source_event_id": pid if isinstance(pid, str) and pid else None})
            # event_msg 是运行时镜像,不能重复进账或抢占 canonical response_item 的消息 id。
            if r.get("type") != "response_item":
                continue
            if isinstance(pid, str) and pid:
                if pid in seen_ids:
                    continue                          # fork 复制来的父记录:不是这个 agent 的动作
                seen_ids.add(pid)
            t = pl.get("type")
            if t in ("message", "agent_message"):
                content = pl.get("content")
                text = _text_of([content] if isinstance(content, dict) else content)
                role = pl.get("role")
                if not text.strip() or (t == "message" and role not in ("user", "assistant", "developer", "system")):
                    continue
                kind = ("say" if role == "assistant" else "system" if role in ("developer", "system") else "inbox") if t == "message" else "inbox"
                detail: dict[str, Any] = {"text": text, "summary": None, "source_event_type": t,
                                          "source_event_id": pid if isinstance(pid, str) and pid else None}
                if t == "agent_message":
                    detail.update({"from": pl.get("author"), "recipient": pl.get("recipient"),
                                   "claim_note": "发送者消息主张,未独立核验;不证明实际修改、读取或派发"})
                elif role == "user":
                    detail["from"] = "parent" if is_sub else "user"
                    if is_sub and rec.prompt is None:
                        rec.prompt = text
                elif role == "assistant":
                    last_text = text.strip()
                else:
                    detail["from"] = role
                text_action(ts, line_no, text, kind, detail)
            elif t in ("function_call", "custom_tool_call"):
                raw_arg = pl.get("arguments") if pl.get("arguments") is not None else pl.get("input")
                pend[str(pl.get("call_id"))] = (ts, str(pl.get("name")), raw_arg, cwd, line_no)
            elif t in ("function_call_output", "custom_tool_call_output") and str(pl.get("call_id")) in pend:
                cid = str(pl.get("call_id"))
                uts, name, raw_arg, ucwd, use_line = pend.pop(cid)
                out_text = _text_of(pl.get("output"))
                ops: list[FileOp] = []
                detail: dict[str, Any] = {}
                ok: bool = True
                kind = "other"
                if name == "exec":
                    full_ops, detail, ok = _codex_exec_ops(raw_arg, out_text, ucwd, scripts)
                    kind = _kind_of("exec", full_ops)
                    mentions, trunc = _path_mentions(raw_arg if isinstance(raw_arg, str)
                                                     else json.dumps(raw_arg, ensure_ascii=False), scripts, ucwd, uts, audit=detail)
                    if mentions:
                        detail["mentions"] = mentions
                    if trunc:
                        detail["mentions_truncated"] = trunc
                    ops = full_ops if ok else []
                elif name == "spawn_agent":
                    args = _json_args(raw_arg)
                    try:
                        out = json.loads(out_text) if out_text.strip().startswith("{") else {}
                    except json.JSONDecodeError:
                        out = {}
                    msg = str(args.get("message") or "")
                    detail = {"name": args.get("task_name"), "subagent_type": args.get("agent_type"),
                              "description": args.get("task_name"), "model": None,
                              "prompt": None if _ENCRYPTED.match(msg) else (msg or None),
                              "prompt_encrypted": bool(_ENCRYPTED.match(msg)),
                              "task_path": out.get("task_name") if isinstance(out, dict) else None}
                    kind = "dispatch"
                elif name == "send_message":
                    args = _json_args(raw_arg)
                    msg = str(args.get("message") or "")
                    detail = {"to": args.get("agent") or args.get("nickname") or args.get("to"),
                              "summary": None, "text": None if _ENCRYPTED.match(msg) else msg}
                    kind = "message"
                else:
                    arg_text = raw_arg if isinstance(raw_arg, str) else json.dumps(raw_arg, ensure_ascii=False)
                    detail = {"args": arg_text[:200]}
                act = Action(uts, nxt(), name, kind, ok=ok, detail=detail,
                             src=(path, use_line, line_no), tuid=cid, done_ts=ts)
                for op in ops:
                    ev = _to_ev(op, agent_id, ts if op.op == "read" else uts, nxt(), use_ts=uts, done_ts=ts)
                    act.files.append(FileRef("read" if op.op == "read" else
                                             "delete" if op.op == "delete" else "write", op.path, ev))
                rec.actions.append(act)
    for cid, (uts, name, raw_arg, ucwd, use_line) in pend.items():
        arg_text = raw_arg if isinstance(raw_arg, str) else json.dumps(raw_arg, ensure_ascii=False)
        detail = {"unfinished": True, "args": arg_text[:200]}
        if name == "exec":
            # 仅静态提取候选目标;没有结果就不立正式读写,也不把输入脚本认作成功落盘。
            _possible, hints, _ok = _codex_exec_ops(raw_arg, "", ucwd, scripts, completed=False, ts=uts)
            detail.update(hints)
            detail["touched"] = sorted(set(detail.get("touched") or []) | set(detail.get("conditional") or []))
            mentions, trunc = _path_mentions(arg_text, scripts, ucwd, uts, audit=detail)
            if mentions:
                detail["mentions"] = mentions
            if trunc:
                detail["mentions_truncated"] = trunc
        rec.actions.append(Action(uts, nxt(), name, "other", ok=None, detail=detail,
                                  src=(path, use_line, use_line), tuid=cid))
    rec.result = last_text
    return rec


def collect_codex(root_jsonl: str, seq: list[int],
                  sessions_root: str | None = None) -> dict[str, AgentRec]:
    """codex 会话(主 rollout + 子代理 rollout 树)→ {agent_id: AgentRec},派发边按
    spawn_agent 输出的 task_name ↔ 子 rollout 的 agent_path 对齐。"""
    from migloop.adapters import codex

    tree = codex.discover_rollout_tree(root_jsonl, sessions_root)
    scripts: dict[str, Any] = {}
    seen_ids: set[str] = set()
    agents: dict[str, AgentRec] = {}
    by_rid: dict[str, str] = {}
    by_task: dict[str, str] = {}
    sid8 = ""
    for i, item in enumerate(tree):
        rid = str((item.get("meta") or {}).get("id") or os.path.basename(str(item.get("path"))))
        if i == 0:
            sid8 = rid[:8]
        who = ("__main__:" + rid[:8]) if i == 0 else "agent-" + rid[:12]
        rec = _walk_codex(str(item.get("path")), who, sid8, seq, scripts, seen_ids)
        rec.name = item.get("nickname") or (item.get("agent_path") or "").rsplit("/", 1)[-1] or None
        rec.kind = item.get("agent_role")
        rec.description = item.get("agent_path")
        agents[who] = rec
        by_rid[rid] = who
        if item.get("agent_path"):
            by_task[str(item["agent_path"])] = who
        if item.get("parent") and str(item["parent"]) in by_rid:
            rec.parent = by_rid[str(item["parent"])]
    for a in agents.values():
        for act in a.actions:
            if act.kind == "dispatch":
                child = by_task.get(str(act.detail.get("task_path") or ""))
                if child:
                    act.detail["child"] = child
                    agents[child].parent = agents[child].parent or a.id
            elif act.kind == "message" and act.detail.get("to") in by_task:
                act.detail["to_id"] = by_task[str(act.detail["to"])]
    # 阶段:codex 记录没有归属戳,主线每笔动作按适配器的阶段区间(读 SKILL.md 的边界 + 去噪)
    # 回填;子 rollout 与 CC 子代理同一规矩 —— 由 build_ledger 继承派发时的阶段
    main = agents.get("__main__:" + sid8)
    if main is not None:
        stages = codex.stage_intervals(root_jsonl, sessions_root)
        for act in main.actions:
            act.stage = codex.stage_at(stages, act.ts)
    return agents


def agents_from_events(events: list[Ev], session: str) -> dict[str, AgentRec]:
    """只有事件流(codex 收集器)时的兜底:每条事件一个动作,没有派发/收件箱。"""
    agents: dict[str, AgentRec] = {}
    for e in events:
        a = agents.setdefault(e.agent, AgentRec(id=e.agent, session=session))
        op = "read" if e.kind == "read" else "delete" if e.kind == "delete" else "write"
        a.actions.append(Action(e.ts, e.seq, "event", op, files=[FileRef(op, e.path, e)]))
    return agents
