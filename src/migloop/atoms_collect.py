"""CC 会话实录 → 两原子账本的动作流(atoms.AgentRec)。

与 filestory_collect 的差别就是 0723 普查钉出来的几条:
- 相对路径按「记录 cwd + 命令内 cd 链」解析;cd 到变量之后的相对路径解析不了就丢,不猜
- 工具调用先等结果:is_error 的不落账、不占版本号
- 脚本落盘/脚本读:heredoc 体、会话内落盘的脚本体、python -c 里的文件字面量(via=script)
- rm / git rm / Remove-Item → 删除版本;git checkout/restore <path> → 内容未知的写
- Grep 工具 content 模式的命中行 → 带行段的读
- Agent 派发 / SendMessage 是效应;收件箱从自己实录里的 teammate-message 读

agent 身份:主线 = ``__main__:<sid8>``,子代理 = 其 transcript 文件 stem(自带会话 hash)。
"""

from __future__ import annotations

import ast
import glob
import json
import os
import posixpath
import re
from dataclasses import dataclass
from typing import Any

from migloop.atoms import Action, AgentRec, FileRef
from migloop.audit import stage_order
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


# ═══════════════ 路径 ═══════════════

def _norm_abs(p: str) -> str:
    q = p.replace("\\", "/")
    if len(q) > 1 and q[1] == ":":
        return q[:2] + posixpath.normpath(q[2:] or "/")
    return posixpath.normpath(q)


_BAD_PATH_CHARS = frozenset(" \t\n;|\"'<>=")


def _resolve(p: object, base: str | None) -> str | None:
    # 带空白/引号/分隔符的 token 是分词失衡的残渣,不是路径 —— 宁可漏
    if not isinstance(p, str) or not p or any(c in _BAD_PATH_CHARS for c in p):
        return None
    q = p.replace("\\", "/")
    if q.startswith("/") or (len(q) > 1 and q[1] == ":"):
        return _norm_abs(q)
    if base is None:
        return None
    return _norm_abs(base.rstrip("/") + "/" + q)


# ═══════════════ 脚本字面量 ═══════════════

#: 全文倾向兜底只对小脚本生效:一张 24 条 .ets 路径的数据表在只写脚本里曾全被当成写目标
#: (0723 vv-static-B 的 gen_static.py,凭空造出 34 条返修链里的 19 条);字面量多于这个数就不猜方向
_TENDENCY_MAX_LITERALS = 3


def _py_script_ops(code: str, base: str | None) -> list[FileOp]:
    """python 正文里规整的读改写按 ast 解成确定的读写,解不出的形状不猜(交给字面量层当「碰过」):
    s = open(p).read() → 读;s = s.replace(old, new[, n]) 后 open(p,'w').write(s) → edit;
    open(p,'w').write(常量) / Path(p).write_text(常量) / with open(p,'w') as f: f.write(常量) → 全文写;
    写回的是算出来的东西(re.sub、拼接)→ 内容未知的写(盲写),不是黑盒。"""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    consts: dict[str, str] = {}
    read_path: dict[str, str] = {}                     # 变量 → 它是哪个文件读出来的内容
    edits: dict[str, list[tuple[str, str, bool]]] = {}  # 变量 → 累计的 replace
    dirty: set[str] = set()                            # 变量被解不出的运算改过:写回只能算内容未知
    ops: list[FileOp] = []

    def cs(node: ast.AST | None) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            return consts.get(node.id)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            a, b = cs(node.left), cs(node.right)
            return a + b if a is not None and b is not None else None
        return None

    def opened(call: ast.AST) -> tuple[str | None, str]:
        """open(P[, mode]) / Path(P) / pathlib.Path(P) → (路径, 模式)"""
        if not isinstance(call, ast.Call):
            return None, ""
        f = call.func
        name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
        if name not in ("open", "Path") or not call.args:
            return None, ""
        mode = cs(call.args[1]) if name == "open" and len(call.args) > 1 else ""
        for kw in call.keywords:
            if kw.arg == "mode":
                mode = cs(kw.value) or ""
        return cs(call.args[0]), mode or ""

    def emit_write(p: str | None, arg: ast.AST) -> None:
        rp = _resolve(p, base) if p else None
        if not rp:
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
            if old is not None and new is not None:
                for o2, n2, a2 in edits.pop(arg.func.value.id, []):
                    ops.append(FileOp("edit", rp, "script", old=o2, new=n2, replace_all=a2))
                ops.append(FileOp("edit", rp, "script", old=old, new=new, replace_all=len(arg.args) < 3))
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
            s = cs(val)
            if s is not None:
                consts[name] = s
                return
            if isinstance(val, ast.Call) and isinstance(val.func, ast.Attribute):
                if val.func.attr in ("read", "read_text"):
                    p, _mode = opened(val.func.value)
                    rp = _resolve(p, base) if p else None
                    if rp:
                        read_path[name] = rp
                        dirty.discard(name)
                        ops.append(FileOp("read", rp, "script", dep=True))
                    return
                if (val.func.attr == "replace" and isinstance(val.func.value, ast.Name)
                        and val.func.value.id == name and name in read_path and len(val.args) >= 2):
                    old, new = cs(val.args[0]), cs(val.args[1])
                    if old is not None and new is not None:
                        edits.setdefault(name, []).append((old, new, len(val.args) < 3))
                        return
            if name in read_path:
                dirty.add(name)           # s = re.sub(...) / s + x:写回内容算不出
            return
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call) and isinstance(stmt.value.func, ast.Attribute):
            call = stmt.value
            if call.func.attr in ("write", "write_text") and call.args:
                p, _mode = opened(call.func.value)
                if p:
                    emit_write(p, call.args[0])
            return
        if isinstance(stmt, ast.With) and len(stmt.items) == 1:
            item = stmt.items[0]
            p, _mode = opened(item.context_expr)
            var = item.optional_vars.id if isinstance(item.optional_vars, ast.Name) else None
            if p and var:
                for inner in stmt.body:
                    if (isinstance(inner, ast.Expr) and isinstance(inner.value, ast.Call)
                            and isinstance(inner.value.func, ast.Attribute) and inner.value.func.attr == "write"
                            and isinstance(inner.value.func.value, ast.Name) and inner.value.func.value.id == var
                            and inner.value.args):
                        emit_write(p, inner.value.args[0])
                    elif (isinstance(inner, ast.Assign) and len(inner.targets) == 1 and isinstance(inner.targets[0], ast.Name)
                          and isinstance(inner.value, ast.Call) and isinstance(inner.value.func, ast.Attribute)
                          and inner.value.func.attr == "read" and isinstance(inner.value.func.value, ast.Name)
                          and inner.value.func.value.id == var):
                        rp = _resolve(p, base)
                        if rp:
                            read_path[inner.targets[0].id] = rp
                            ops.append(FileOp("read", rp, "script", dep=True))
            return

    for stmt in tree.body:
        handle(stmt)
    return ops


def _literal_ops(code: str, base: str | None) -> tuple[list[FileOp], int, list[str]]:
    """脚本正文里的文件字面量 → 读/写。按紧邻的调用形态判方向;判不出的只在小脚本里按
    全文倾向(只写/只读)兜底,其余放弃并计数 —— 宁可漏,但要能报出自己。
    返回 (ops, 放弃的字面量数, 放弃的那些路径):放弃的不猜方向,记成「碰过」,让 file / sessions 能把指针摆出来。"""
    body_w, body_r = bool(_WRITEISH.search(code)), bool(_READISH.search(code))
    lits = list(_LIT.finditer(code))
    tendency_ok = len(lits) <= _TENDENCY_MAX_LITERALS
    ops: list[FileOp] = []
    undetermined = 0
    touched: list[str] = []
    for m in lits:
        after = code[m.end():m.end() + 40]
        before = code[max(0, m.start() - 40):m.start()]
        # 紧跟在 : 后面的是映射的值("hmos_page_map": {"MainActivity": "…/Index.ets"}),不是文件操作的
        # 目标:DiceRoller 0903 主会话初始化 progress.json 的 heredoc 曾借倾向兜底给 Index.ets 造出一版假修复
        if re.search(r":\s*$", before):
            undetermined += 1
            continue
        # open(p, 'w') / 'a' / 'wb' / 'w+':模式串必须是完整的短 token,后面紧跟 , 或 ) ——
        # 只看引号后一个字母会把数据表里紧跟的 'wired' 之类字段当成写模式
        if re.match(r"\s*,\s*['\"][wa][bt+]{0,2}['\"]\s*[,)]", after) or re.match(r"\s*\)\s*\.write", after):
            op = "write"
        elif re.match(r"\s*\)\s*\.(?:read|open|exists|is_file|iterdir|glob)", after) \
                or re.search(r"(?:json\.load|read_text|readFile|Get-Content)\s*\(?\s*(?:open\()?$",
                             before) \
                or (re.search(r"open\(\s*$", before) and re.match(r"\s*\)", after)):
            op = "read"
        elif tendency_ok and body_w and not body_r:
            op = "write"
        elif tendency_ok and body_r and not body_w:
            op = "read"
        else:
            undetermined += 1
            tp = _resolve(m.group(1), base)
            if tp and tp not in touched:
                touched.append(tp)
            continue
        p = _resolve(m.group(1), base)
        if p:
            ops.append(FileOp(op, p, "script"))
    return ops, undetermined, touched


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


def _shell_analyze(cmd: str, cwd: object, scripts: dict[str, str],
                   out: str = "") -> tuple[list[FileOp], bool, int, list[str], dict[str, list[str]]]:
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

    for seg in _split_segments(text):
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
            py_ops = _py_script_ops(code, base)
            ops += py_ops
            lit_ops, und, tch = _literal_ops(code, base)
            lit_ops = [o for o in lit_ops if o.path not in {o.path for o in py_ops}]
            ops += lit_ops
            undetermined += und
            touched += tch
            capable = capable or bool(_WRITEISH.search(code))
            out_dirs += _dir_hints(code, base)
        if head in _RUNNERS:
            run = next((w for w in args if _SCRIPT_RUN.search(w) and not w.startswith("-")), None)
            if run:
                ran_script = True
                body = scripts.get(os.path.basename(run)) or scripts.get(_resolve(run, base) or "")
                if body is None:
                    capable = True                # 会话外脚本:目标不可知
                else:
                    lit_ops, und, tch = _literal_ops(body, base)
                    ops += lit_ops
                    undetermined += und
                    touched += tch
                    capable = capable or bool(_WRITEISH.search(body))
                    out_dirs += _dir_hints(body, base)
    if out and grep_ctx:
        gb, has_n, names_only = grep_ctx[-1]
        ops += _grep_stdout_reads(out, gb, has_n, names_only, ops, listing)
    if out and "==> " in out and any(_head_word([t[0] for t in _tokenize(s) if t[2] == ""])[0]
                                       in ("head", "tail") for s in _split_segments(text)):
        ops += _head_header_reads(out, base, ops)
    if out and _FOR_LOOP.search(cmd or ""):
        _attach_loop_sections((cmd or "").replace("\\\n", " "), out, ops)
    for body in bodies:
        if hd_target is not None:
            for op in ops:
                if op.op == "write" and op.path == hd_target:
                    op.content, op.via = body, "shell"
            continue
        py_ops = _py_script_ops(body, base)
        ops += py_ops
        lit_ops, und, tch = _literal_ops(body, base)
        solved = {o.path for o in py_ops}
        ops += [o for o in lit_ops if o.path not in solved]
        # ast 解出了读写的路径,字面量层不再对它「放弃」计数(否则动作仍标黑盒)
        tch = [p for p in tch if p not in solved]
        undetermined += sum(1 for p in tch) if py_ops else und
        touched += tch
        capable = capable or bool(_WRITEISH.search(body))
        out_dirs += _dir_hints(body, base)
    if ran_script or capable:
        out_dirs += mk_dirs
    return ops, capable, undetermined, touched, {"probed": probe_hits, "out_dirs": list(dict.fromkeys(out_dirs))}


def shell_file_ops(cmd: str, cwd: object, scripts: dict[str, str], out: str = "") -> list[FileOp]:
    return _shell_analyze(cmd, cwd, scripts, out)[0]


def _note_touched(detail: dict[str, Any], touched: list[str], ops: list[FileOp]) -> None:
    """脚本里出现了路径但方向不明的,记成「碰过」:不立版本、不猜读写,file / sessions 把指针摆出来让人展开。
    0723 修复方用 python heredoc 读改写 F012ViewModel.ets,既读又写就放弃了,文件那边看不见有人碰过它。"""
    seen = {o.path for o in ops}
    tch = sorted({p for p in touched if p not in seen})
    if tch:
        detail["touched"] = tch


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
    tail = "/" + tgt.replace("\\", "/").lstrip("./")
    reads = [o for o in ops if o.op == "read" and not o.dep
             and (o.path == tgt or o.path.endswith(tail))]
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
              scripts: dict[str, str]) -> tuple[list[FileOp], dict[str, Any]]:
    """成功的调用 → 文件读写 + 附加细节。"""
    detail: dict[str, Any] = _basic_detail(name, inp)
    ops: list[FileOp] = []
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
            # 调查员只能说"无法确认读过"。没给 offset/limit 就是整份读(Read 默认从头读到底)
            numbered = _numbered_lines(out)
            p = _resolve(inp.get("file_path"), _resolve(cwd, None))
            if p and numbered:
                start = numbered[0][0]
                full = start == 1 and not inp.get("offset") and not inp.get("limit")
                ops.append(FileOp("read", p, "tool", content="\n".join(t for _, t in numbered),
                                  full=full, start=start, n=len(numbered)))
    elif name == "Write":
        p = _resolve(inp.get("file_path"), _resolve(cwd, None))
        if p:
            content = str(inp.get("content") or "")
            ops.append(FileOp("write", p, "tool", content=content,
                              created="created successfully" in (out or "").lower()))
            if _SCRIPT_RUN.search(p):
                scripts[os.path.basename(p)] = content
                scripts[p] = content
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
        ops, capable, undetermined, touched, hints = _shell_analyze(cmd, cwd, scripts, out)
        if capable:
            detail["write_capable"] = True
        if not ops:
            why = _unresolved_reason(cmd)
            if why:
                detail["unresolved"] = why      # 不许静默:解析不了的读写要能报出自己
        if undetermined and "unresolved" not in detail:
            detail["unresolved"] = "脚本字面量方向不明"
        _note_touched(detail, touched, ops)
        if hints["probed"]:
            detail["probed"] = hints["probed"]
        if hints["out_dirs"]:
            detail["out_dirs"] = hints["out_dirs"]
        for op in ops:
            # heredoc 落盘的 .py/.sh 也进脚本表:之后 python3 它时按脚本内容推断读写,不再当黑盒
            if op.op == "write" and op.content is not None and _SCRIPT_RUN.search(op.path):
                scripts[os.path.basename(op.path)] = op.content
                scripts[op.path] = op.content
        tgt = _clean_single_cat(cmd)
        if tgt and out.strip() and not out.lower().startswith(_ERRISH):
            _attach_single_cat(tgt, out, ops, cwd, cmd)
        else:
            _attach_stdout(cmd, _strip_heredocs(cmd.replace("\\\n", " "))[0], out, ops)
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


def _to_ev(op: FileOp, agent: str, ts: str, seq: int, stage: str | None = None) -> Ev:
    kind = {"read": "read", "delete": "delete", "edit": "edit",
            "write": "wfull" if op.content is not None else ("wconcat" if op.sources else "wopaque")}[op.op]
    return Ev(ts, seq, kind, op.path, agent, content=op.content, old=op.old, new=op.new,
              replace_all=op.replace_all, start=op.start, n=op.n, full=op.full, dep=op.dep,
              via=op.via, seen=op.seen, stage=stage, created=op.created, sources=op.sources)


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
          scripts: dict[str, str], stage_intervals: list[dict[str, Any]] | None = None) -> AgentRec:
    rec = AgentRec(id=agent_id, session=session)
    pend: dict[str, tuple[str, str, Any, Any, int, str | None]] = {}   # id -> (ts, name, inp, cwd, 行号, 阶段)

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
            for b in blocks:
                if not isinstance(b, dict):
                    continue
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
                                               stage_now(ts))
                elif b.get("type") == "tool_result" and str(b.get("tool_use_id")) in pend:
                    tuid = str(b.get("tool_use_id"))
                    uts, name, inp, ucwd, use_line, stage = pend.pop(tuid)
                    ok = not b.get("is_error", False)
                    ops: list[FileOp] = []
                    detail: dict[str, Any] = _basic_detail(name, inp)
                    if ok:
                        ops, detail = _file_ops(name, inp, _text_of(b.get("content")),
                                                r.get("toolUseResult"), ucwd, scripts)
                    act = Action(uts, nxt(), name, _kind_of(name, ops), ok=ok, detail=detail,
                                 src=(path, use_line, line_no), tuid=tuid, stage=stage)
                    for op in ops:
                        # 写在调用时刻发生,读的内容在结果时刻进上下文
                        ev = _to_ev(op, agent_id, ts if op.op == "read" else uts, nxt(), stage)
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
                    rec.actions.append(Action(ts, nxt(), "inbox", "inbox", detail={
                        "from": tm.group(1) if tm else "dispatcher",
                        "summary": tm.group(2) if tm else None, "text": text},
                        src=(path, line_no, line_no), stage=stage_now(ts)))
                    if rec.prompt is None and is_sub:
                        rec.prompt = text
                else:
                    ukind, udetail, uop = _classify_user_text(raw, cwd)
                    if ukind:
                        uact = Action(ts, nxt(), ukind, ukind, detail=udetail,
                                      src=(path, line_no, line_no), stage=stage_now(ts))
                        if uop is not None:
                            uact.files.append(FileRef("read", uop.path,
                                                      _to_ev(uop, agent_id, ts, nxt(), stage_now(ts))))
                        rec.actions.append(uact)
            # agent 自己说的话 / 想的话:一条记录一条索引,喂养下一版;全文按指针展开
            for kind, texts in (("say", said), ("think", thought)):
                if texts:
                    rec.actions.append(Action(ts, nxt(), kind, kind, detail={"text": _head("\n".join(texts))},
                                              src=(path, line_no, line_no), stage=stage_now(ts)))
    for uts, name, _inp, _cwd, _line, _stage in pend.values():
        rec.actions.append(Action(uts, nxt(), name, "other", ok=None))
    rec.result = last_text
    return rec


def collect_cc(main_jsonl: str, seq: list[int],
               stage_intervals: list[dict[str, Any]] | None = None) -> dict[str, AgentRec]:
    """CC 会话(主线 + subagents/)→ {agent_id: AgentRec}。seq 跨会话共用,保证全局可排序。
    stage_intervals = run 级阶段区间(stage_intervals_from_marks),给没有归属戳的会话按时间落阶段。"""
    sid8 = os.path.basename(main_jsonl)[:8]
    scripts: dict[str, str] = {}
    main_id = f"__main__:{sid8}"
    agents = {main_id: _walk(main_jsonl, main_id, sid8, seq, scripts, stage_intervals)}
    sub = os.path.splitext(main_jsonl)[0] + "/subagents"
    if os.path.isdir(sub):
        for fn in sorted(glob.glob(os.path.join(sub, "*.jsonl"))):
            stem = os.path.splitext(os.path.basename(fn))[0]
            # 时间兜底只给根会话:子 agent 没戳时由 build_ledger 继承派发那一笔的阶段(戳是 skill 粒度,
            # run 级区间是 stage 粒度 —— 直接按时间落会把 execute 期间派的 visual-verify 子代理误成 execute)
            agents[stem] = _walk(fn, stem, sid8, seq, scripts)
    return agents


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
                    scripts: dict[str, str]) -> tuple[list[FileOp], dict[str, Any], bool]:
    """一次 exec:解 JS → shell 命令(复用 CC 的解析 + stdout 对账)+ apply_patch。返回 (ops, detail, ok)。"""
    from migloop.adapters import codex

    if isinstance(raw_arg, str) and raw_arg.lstrip().startswith("{"):
        js = str(codex._decode_arguments(raw_arg).get("input") or raw_arg)
    else:
        js = str(raw_arg or "")
    ok, stdout = _codex_stdout(out_text)
    detail: dict[str, Any] = {}
    ops: list[FileOp] = []
    shell_calls = codex._extract_shell_calls(js, str(cwd) if cwd else None)
    for sc in shell_calls:
        cmd = str(sc.get("command") or "")
        wdir = sc.get("workdir") or cwd
        detail.setdefault("cmd", " ".join(cmd.split())[:200])
        # 单条 shell 调用时 stdout 就是它的:目录 grep / 多文件 head 按 stdout 反证(与 CC 的 Bash 同一套)
        single = len(shell_calls) == 1 and ok
        sub_ops, capable, undetermined, touched, hints = _shell_analyze(cmd, wdir, scripts, stdout if single else "")
        if capable:
            detail["write_capable"] = True
        if single and not sub_ops:
            why = _unresolved_reason(cmd)
            if why:
                detail["unresolved"] = why      # 不许静默(与 CC 同一条规矩)
        if undetermined and "unresolved" not in detail:
            detail["unresolved"] = "脚本字面量方向不明"
        _note_touched(detail, touched, sub_ops)
        for key in ("probed", "out_dirs"):
            if hints[key]:
                detail[key] = list(dict.fromkeys((detail.get(key) or []) + hints[key]))
        if len(shell_calls) == 1 and ok:
            tgt = _clean_single_cat(cmd)
            if tgt and stdout.strip() and not stdout.lower().startswith(_ERRISH):
                _attach_single_cat(tgt, stdout, sub_ops, wdir, cmd)
            else:
                _attach_stdout(cmd, _strip_heredocs(cmd.replace("\\\n", " "))[0], stdout, sub_ops)
        ops += sub_ops
    for patch in codex._extract_apply_patches(js):
        detail.setdefault("cmd", "apply_patch")
        ops += _patch_ops(patch, cwd)
    return ops, detail, ok


def _walk_codex(path: str, agent_id: str, session: str, seq: list[int], scripts: dict[str, str],
                seen_ids: set[str]) -> AgentRec:
    rec = AgentRec(id=agent_id, session=session)
    is_sub = not agent_id.startswith("__main__")
    pend: dict[str, tuple[str, str, Any, Any, int]] = {}   # call_id -> (ts, name, raw_arg, cwd, 行号)
    cwd: Any = None
    last_text: str | None = None

    def nxt() -> int:
        seq[0] += 1
        return seq[0]

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
            if isinstance(pid, str):
                if pid in seen_ids:
                    continue                          # fork 复制来的父记录:不是这个 agent 的动作
                seen_ids.add(pid)
            t = pl.get("type")
            if t == "message":
                text = _text_of(pl.get("content"))
                role = pl.get("role")
                if role == "user" and text.strip():
                    rec.actions.append(Action(ts, nxt(), "inbox", "inbox",
                                              detail={"from": "parent" if is_sub else "user",
                                                      "summary": None, "text": text}))
                    if is_sub and rec.prompt is None:
                        rec.prompt = text
                elif role == "assistant" and text.strip():
                    last_text = text.strip()
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
                             src=(path, use_line, line_no), tuid=cid)
                for op in ops:
                    ev = _to_ev(op, agent_id, ts if op.op == "read" else uts, nxt())
                    act.files.append(FileRef("read" if op.op == "read" else
                                             "delete" if op.op == "delete" else "write", op.path, ev))
                rec.actions.append(act)
    for uts, name, _a, _c, _l in pend.values():
        rec.actions.append(Action(uts, nxt(), name, "other", ok=None))
    rec.result = last_text
    return rec


def collect_codex(root_jsonl: str, seq: list[int],
                  sessions_root: str | None = None) -> dict[str, AgentRec]:
    """codex 会话(主 rollout + 子代理 rollout 树)→ {agent_id: AgentRec},派发边按
    spawn_agent 输出的 task_name ↔ 子 rollout 的 agent_path 对齐。"""
    from migloop.adapters import codex

    tree = codex.discover_rollout_tree(root_jsonl, sessions_root)
    scripts: dict[str, str] = {}
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
