# -*- coding: utf-8 -*-
"""
MigLoop PoC — Claude Code session JSONL -> structured trace JSON

用法:
  python -m migloop.adapters.claude <path-to-session.jsonl> [--out out.json]

产出 schema v0.1:
  meta / totals / stages[] / tools[] / agents[] / prompts[] / markers[]

阶段切分规则(确定性优先):
  - 主信号:记录的 attributionSkill 归属戳发生管线 skill 切换 = 阶段边界
    (a2h-spec/plan/execute/verify/retrospect, mig-arch);Skill 工具调用退为兜底
  - 首个管线阶段之前 = setup 段
  - 非管线 skill(deveco-cli / grill-with-docs 等)记为当前阶段内的 helper 标记
"""
import glob
import json
import os
import sys
import argparse
import difflib
from collections import Counter
from datetime import datetime, timedelta

from .base import SessionCandidate


FORMAT = "claude"
SUPPORTS_LIVE = True


def default_root():
    return os.path.join(os.path.expanduser("~"), ".claude", "projects")


def is_session(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as stream:
            for line in stream:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                return (record.get("type") != "session_meta" and
                        any(key in record for key in ("sessionId", "message", "uuid", "type")))
    except OSError:
        pass
    return False


def iter_sessions(root):
    if not root or not os.path.isdir(root):
        return
    for path in glob.glob(os.path.join(root, "*", "*.jsonl")):
        try:
            stat = os.stat(path)
        except OSError:
            continue
        yield SessionCandidate(
            mtime=stat.st_mtime,
            path=path,
            project=os.path.basename(os.path.dirname(path)),
            size=stat.st_size,
            format=FORMAT,
            session_id=os.path.basename(path).split(".")[0],
        )

PIPELINE_SKILLS = ["a2h-run", "a2h-run-zh", "a2h-init-zh", "a2h-build-zh",
                   "mig-arch", "a2h-arch-scaffold", "a2h-spec", "a2h-plan",
                   "a2h-execute", "a2h-verify", "a2h-retrospect"]

STAGE_LABELS = {
    "setup": "Setup",
    "a2h-run": "Run",
    "a2h-run-zh": "Run",
    "a2h-init-zh": "Init",
    "a2h-build-zh": "Build",
    "mig-arch": "Arch (mig-arch)",
    "a2h-arch-scaffold": "Scaffold",
    "a2h-spec": "Spec",
    "a2h-plan": "Plan",
    "a2h-execute": "Execute",
    "a2h-verify": "Verify",
    "a2h-retrospect": "Retrospect",
    "session": "Session",
}


def parse_ts(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def ms_between(a, b):
    da, db = parse_ts(a), parse_ts(b)
    if da and db:
        return int((db - da).total_seconds() * 1000)
    return None


def brief_tool_target(name, inp):
    """一行摘要:这个工具调用作用在什么对象上。"""
    if not isinstance(inp, dict):
        return ""
    for key in ("file_path", "path", "pattern", "skill", "command", "description",
                "prompt", "query", "url", "notebook_path"):
        v = inp.get(key)
        if isinstance(v, str) and v.strip():
            v = " ".join(v.split())
            return v[:300]
    return ""


def result_snippet(block, tur, limit=220):
    """从 tool_result block / toolUseResult 提取结果文本摘要。"""
    txt = ""
    c = block.get("content")
    if isinstance(c, str):
        txt = c
    elif isinstance(c, list):
        txt = "\n".join(x.get("text", "") for x in c if isinstance(x, dict) and x.get("text"))
    if not txt.strip() and isinstance(tur, dict):
        for k in ("stdout", "stderr"):
            v = tur.get(k)
            if isinstance(v, str) and v.strip():
                txt = v
                break
        if not txt.strip():
            cc = tur.get("content")
            if isinstance(cc, str):
                txt = cc
            elif isinstance(cc, list):
                txt = "\n".join(x.get("text", "") for x in cc if isinstance(x, dict) and x.get("text"))
    txt = txt.strip()
    return txt[:limit] if txt else ""


def result_text(block, tur):
    """提取完整工具结果文本。

    可见性统计只认最终进入 agent 上下文的 tool_result；命令内部读过、但没有
    输出的文件不算可见。
    """
    chunks = []
    content = block.get("content")
    if isinstance(content, str):
        chunks.append(content)
    elif isinstance(content, list):
        chunks.extend(
            x.get("text", "")
            for x in content
            if isinstance(x, dict) and isinstance(x.get("text"), str)
        )
    if not any(x.strip() for x in chunks) and isinstance(tur, dict):
        for key in ("stdout", "stderr"):
            value = tur.get(key)
            if isinstance(value, str) and value:
                chunks.append(value)
        if not any(x.strip() for x in chunks):
            content = tur.get("content")
            if isinstance(content, str):
                chunks.append(content)
            elif isinstance(content, list):
                chunks.extend(
                    x.get("text", "")
                    for x in content
                    if isinstance(x, dict) and isinstance(x.get("text"), str)
                )
    return "\n".join(x for x in chunks if x)


def load_main_session(path):
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


import re

_PAGE_RE = re.compile(r"page_\d{4}_[A-Za-z0-9]+")
_FEAT_RE = re.compile(r"\bF0\d\d(?:-[A-Za-z0-9-]+)?")

# lineage 归属：几乎每个 agent 都读的跨切面文件，不能当 owning spec（否则它们会"生产"几乎所有文件）
_SHARED_SPEC_MARKERS = (
    "decision-ledger", "placeholder-registry", "feature-plan", "ui-plan",
    "ui-manifest", "feature-base", "cross-module-contracts", "module-dep-graph",
    "coverage-matrix", "resource-mapping", "api-inventory",
)


def _rel(path, cwd):
    """把绝对路径相对化到工程根，正斜杠归一。cwd 为空则原样。"""
    p = (path or "").replace("\\", "/")
    if cwd:
        c = cwd.replace("\\", "/").rstrip("/")
        if p.lower().startswith(c.lower() + "/"):
            return p[len(c) + 1:]
    # 工程外但落在某个 spec/ 目录下(如 migbot 把 spec 建在安卓工程里):归一到 spec/...
    # 否则同一文件"写入用绝对路径、读取用相对路径"会被当成两个实体,作者链就断了
    i = p.lower().rfind("/spec/")
    if i >= 0:
        return p[i + 1:]
    return p


def _spec_kind(rel):
    """rel 是相对路径。返回契约/分析文档细类，或 None(普通工程文件)。

    Canonical a2h 流水线使用 ``spec/``；通用 Workflow 常把同样承担实现契约
    作用的产物放在 ``.migration/analysis/``。两者都必须进入血缘的 Spec 列，
    否则会出现“分析 agent 明明写了文档、实现 agent 也读了，图上却是 0”的
    假断链。这里只认明确的迁移目录，不把工程内任意 Markdown 都当 Spec。
    """
    low = rel.lower()
    if low.startswith(".migration/analysis/") and low.endswith(".md"):
        return "analysis"
    if low.startswith(".migration/") and low.endswith(".md"):
        return "shared"
    if not low.startswith("spec/"):
        return None
    if "/handoffs/" in low or low.endswith("_handoff.md"):
        return "handoff"
    if "/ui/page_" in low and low.endswith(".md"):
        return "page"
    if "/features/" in low and low.endswith(".md"):
        return "feature"
    if low.endswith("feature-base.md"):
        return "base"
    if low.endswith(("/ui-plan.md", "/feature-plan.md")):
        return "plan"
    if any(m in low for m in _SHARED_SPEC_MARKERS):
        return "shared"
    return "other"


def _is_hmos(rel):
    """鸿蒙产物文件判定(跨工程通用：认 ArkTS 源 + 资源)。返回 ets/res/cfg 或 None。"""
    low = rel.lower()
    if low.startswith("spec/"):
        return None
    # 任何 .ets 都算鸿蒙代码——模块根的 Index.ets(桶文件)不在 src/main/ets/ 下,
    # 早先按目录判定会把它们整批漏掉
    if low.endswith(".ets"):
        return "ets"
    if "/src/main/ets/" in low and low.endswith(".ts"):
        return "ets"
    if "/resources/" in low and "/src/main/" in low:
        return "res"
    if low.endswith(("module.json5", "oh-package.json5", "build-profile.json5")) \
            or low.startswith("appscope/"):
        return "cfg"
    return None


_ANDROID_EXT = (".java", ".kt", ".kts", ".xml", ".gradle", ".aidl", ".pro",
                ".properties", ".toml", ".yaml", ".yml")
# 纯逻辑代码口径:布局 xml / gradle 脚本的阅读成本远低于逻辑代码,混在一起会高估
# "理解深度"。两套口径同时产出,分子分母各自对齐,读数时不会串味。
_CODE_EXT = (".java", ".kt", ".kts")
_EXTERNAL_EXCLUDE = ("migbot", "/skills/", "/.claude/", "/scratchpad/", "/temp/claude/")


def _is_code(path):
    return path.lower().endswith(_CODE_EXT)


def _is_abs(p):
    """_rel 相对化失败(不在工程内)后仍是绝对路径 → 外部文件。"""
    return p.startswith("/") or (len(p) > 2 and p[1] == ":")


def _union_lines(ivs):
    """读取区间 [(start, n)...] 的并集总行数——精确去重(分页/重读不重复计)。"""
    spans = sorted((s, s + n) for s, n in ivs if n > 0)
    total, cs, ce = 0, None, None
    for s, e in spans:
        if cs is None:
            cs, ce = s, e
        elif s <= ce:
            ce = max(ce, e)
        else:
            total += ce - cs
            cs, ce = s, e
    if cs is not None:
        total += ce - cs
    return total


_SOURCE_SUFFIX = r"(?:java|kt|kts|xml|gradle|aidl|pro|properties|toml|yaml|yml)"
_QUOTED_SOURCE_PATH_RE = re.compile(
    rf"""(?P<quote>["'])(?P<path>[^"'`\r\n]+?\.{_SOURCE_SUFFIX})(?P=quote)""",
    re.IGNORECASE,
)
_BARE_SOURCE_PATH_RE = re.compile(
    rf"""(?P<path>(?:[A-Za-z]:[\\/]|/[A-Za-z0-9_.-]+/|\.{{1,2}}[\\/]|[A-Za-z0-9_.-]+[\\/])
         [^"'`\s;|<>()]+?\.{_SOURCE_SUFFIX})""",
    re.IGNORECASE | re.VERBOSE,
)
_PATH_LINE_RE = re.compile(
    rf"""(?P<path>(?:[A-Za-z]:[\\/]|/|\.{{0,2}}[\\/])?
         [^:\r\n]*?\.{_SOURCE_SUFFIX})[:\-](?P<line>\d+)[:\-](?P<text>.*)$""",
    re.IGNORECASE | re.VERBOSE,
)
_LINE_ONLY_RE = re.compile(r"^\s*(?P<line>\d+)[:\-](?P<text>.*)$")


def _drive_path(path):
    """把 git-bash `/c/Users/...` 归一成宿主机可访问的 `C:/Users/...`。"""
    p = (path or "").strip().strip("\"'").replace("\\", "/")
    m = re.match(r"^/([A-Za-z])/(.*)$", p)
    if m:
        return f"{m.group(1).upper()}:/{m.group(2)}"
    return p


def _source_path_literals(text):
    """抽取命令/结果中明确出现的源码文件路径字面量。"""
    found = []
    seen = set()
    for regex in (_QUOTED_SOURCE_PATH_RE, _BARE_SOURCE_PATH_RE):
        for match in regex.finditer(text or ""):
            value = match.group("path").strip()
            key = value.replace("\\", "/").lower()
            if key not in seen:
                seen.add(key)
                found.append(value)
    return found


def _shell_bases(command, cwd):
    """提取 shell 命令中用于解析相对源码路径的目录。"""
    bases = []
    if cwd:
        bases.append(_drive_path(cwd))
    patterns = (
        r"""(?:^|[;&|]\s*)(?:cd|pushd)\s+(?:"([^"]+)"|'([^']+)'|([^\s;&|]+))""",
        r"""(?:^|[;\r\n]\s*)(?:Set-Location|Push-Location)(?:\s+-LiteralPath|\s+-Path)?\s+
            (?:"([^"]+)"|'([^']+)'|([^\s;]+))""",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, command or "", re.IGNORECASE | re.VERBOSE):
            raw = next((x for x in match.groups() if x), None)
            if raw:
                bases.append(_drive_path(raw))
    return list(dict.fromkeys(os.path.abspath(x) for x in bases if x))


def _resolve_source_path(raw, bases):
    """把工具输入/输出中的路径解析到本机真实文件；不猜不存在的路径。"""
    value = _drive_path(raw)
    if not value or "$" in value or "%" in value:
        return None
    candidates = [value] if os.path.isabs(value) else [
        os.path.join(base, value.replace("/", os.sep)) for base in reversed(bases)
    ]
    for candidate in candidates:
        path = os.path.abspath(candidate)
        if os.path.isfile(path) and path.lower().endswith(_ANDROID_EXT):
            return path.replace("\\", "/")
    return None


def _merge_line_intervals(intervals):
    """[(start, count)] → 去重后的相邻区间，仍使用 start/count。"""
    spans = sorted((int(s), int(s) + int(n) - 1) for s, n in intervals if int(n) > 0)
    merged = []
    for start, end in spans:
        if not merged or start > merged[-1][1] + 1:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return [(start, end - start + 1) for start, end in merged]


_NUMBERED_LINE_RE = re.compile(r"^\s{0,8}(\d+)\t")


def _spans_from_numbered_text(text):
    """从 Read 结果正文的 `N\\t内容` 行号前缀还原精确读取区间 → [(start, count)]。

    workflow 子代理的 transcript 不写 toolUseResult(只有正文)，此时行号前缀是
    唯一的精确来源。旧兜底"数换行、起点当 1"会把分页读整体挪到文件开头，
    与其它 agent 的区间错误合并，去重行数因此虚高。
    """
    nums = []
    for line in (text or "").splitlines():
        m = _NUMBERED_LINE_RE.match(line)
        if m:
            try:
                nums.append(int(m.group(1)))
            except ValueError:
                pass
    if not nums:
        return []
    return _merge_line_intervals([(n, 1) for n in sorted(set(nums))])


def _script_probed_paths(tool_name, inp, cwd):
    """从**命令本身**抠出被脚本碰过的源码文件(不看输出)。

    与 _infer_visible_source_lines 的区别是关键:那个只认真正进入上下文的源码文本,
    这个只说"脚本点到过这个文件"。`python analyze.py`、`wc -l`、`ls`、`find`
    都只让 agent 拿到统计/结构,并没有看到代码——两者必须分开记,
    否则要么把探测当成阅读(虚高),要么让脚本流的会话看着像什么都没做(虚低)。
    """
    if tool_name not in ("Grep", "Bash", "PowerShell") or not isinstance(inp, dict):
        return []
    command = str(inp.get("command") or "")
    if not command:
        return []
    bases = _shell_bases(command, cwd)
    out = []
    for raw in _source_path_literals(command):
        resolved = _resolve_source_path(raw, bases)
        if resolved and resolved not in out:
            out.append(resolved)
    return out


def _infer_visible_source_lines(tool_name, inp, output, cwd):
    """从搜索/命令的最终输出还原真正进入 agent 上下文的源码行。

    这里只认输出中真实出现的源码文本：
    - 命令访问过文件但 stdout 没有源码，不产生事件；
    - `cat file | grep x` 只会匹配最终 grep 输出的行；
    - `grep -l/-c/-q`、存在性检查和路径列表不会被当成源码行。
    """
    if tool_name not in ("Grep", "Bash", "PowerShell") or not (output or "").strip():
        return []
    command = ""
    if isinstance(inp, dict):
        command = str(inp.get("command") or "")
    bases = _shell_bases(command, cwd)
    candidate_paths = []
    raw_paths = []
    if isinstance(inp, dict) and isinstance(inp.get("path"), str):
        raw_paths.append(inp["path"])
    raw_paths.extend(_source_path_literals(command))
    raw_paths.extend(_source_path_literals(output))
    for raw in raw_paths:
        resolved = _resolve_source_path(raw, bases)
        if resolved and resolved not in candidate_paths:
            candidate_paths.append(resolved)
    if not candidate_paths:
        return []

    source_lines = {}
    source_text = {}
    for path in candidate_paths:
        try:
            with open(path, encoding="utf-8", errors="ignore") as stream:
                text = stream.read()
        except OSError:
            continue
        source_text[path] = text.replace("\r\n", "\n").replace("\r", "\n")
        source_lines[path] = source_text[path].splitlines()
    if not source_lines:
        return []

    output_norm = output.replace("\r\n", "\n").replace("\r", "\n")
    output_lines = output_norm.splitlines()
    hits = {path: [] for path in source_lines}

    # 完整文件原文确实出现在结果中，才记为全量可见。命令本身的 cat/open 不作证。
    for path, text in source_text.items():
        if text and text.rstrip("\n") in output_norm:
            hits[path].append((1, len(source_lines[path])))

    # grep/rg/Select-String 常见的 path:line:text / path-line-text。
    for line in output_lines:
        match = _PATH_LINE_RE.search(line)
        if not match:
            continue
        path = _resolve_source_path(match.group("path"), bases)
        lineno = int(match.group("line"))
        if path not in source_lines or not (1 <= lineno <= len(source_lines[path])):
            continue
        shown = match.group("text").strip()
        actual = source_lines[path][lineno - 1].strip()
        if shown and (shown == actual or shown.endswith(actual)):
            hits[path].append((lineno, 1))

    # 搜索显式文件时常省略路径，只返回 `line:text`。多文件 Bash 往往先打印
    # `=== Foo.java ===` 再输出 grep 结果，据此切换当前文件。
    basename_paths = {}
    for path in candidate_paths:
        basename_paths.setdefault(os.path.basename(path).lower(), []).append(path)
    current_path = candidate_paths[0] if len(candidate_paths) == 1 else None
    for line in output_lines:
        low = line.lower()
        if line.lstrip().startswith("==="):
            matched_paths = [
                paths[0]
                for basename, paths in basename_paths.items()
                if len(paths) == 1 and basename in low
            ]
            current_path = matched_paths[0] if len(matched_paths) == 1 else None
            continue
        match = _LINE_ONLY_RE.match(line)
        if not match or current_path not in source_lines:
            continue
        lineno = int(match.group("line"))
        if not (1 <= lineno <= len(source_lines[current_path])):
            continue
        shown = match.group("text").strip()
        actual = source_lines[current_path][lineno - 1].strip()
        if shown and (shown == actual or shown.endswith(actual)):
            hits[current_path].append((lineno, 1))

    # cat/head/sed 或脚本打印通常没有行号。按实际输出与源码的连续文本块匹配；
    # 只收至少两行且有实质字符的块，避免单个 `}`/空行在多文件间误归属。
    for path, lines in source_lines.items():
        if not lines or hits[path] == [(1, len(lines))]:
            continue
        matcher = difflib.SequenceMatcher(
            None,
            [x.rstrip() for x in lines],
            [x.rstrip() for x in output_lines],
            autojunk=False,
        )
        for block in matcher.get_matching_blocks():
            if block.size < 2:
                continue
            meaningful = sum(len(x.strip()) for x in lines[block.a:block.a + block.size])
            if meaningful < 16:
                continue
            hits[path].append((block.a + 1, block.size))

    # 不连续但字面值全局唯一的实质源码行也是真正可见的搜索命中。
    global_line_index = {}
    for path, lines in source_lines.items():
        for lineno, line in enumerate(lines, 1):
            key = line.strip()
            if len(key) >= 8:
                global_line_index.setdefault(key, []).append((path, lineno))
    for line in output_lines:
        key = line.strip()
        locations = global_line_index.get(key) or []
        if len(locations) == 1:
            path, lineno = locations[0]
            hits[path].append((lineno, 1))

    events = []
    for path, intervals in hits.items():
        merged = _merge_line_intervals(intervals)
        if merged:
            events.append({"path": path, "intervals": merged, "via": tool_name})
    return events


def _find_gradle_root(paths):
    """从读到的安卓源码路径反推真正的工程根:逐个向上找 gradle **根**标记
    (settings.gradle / gradlew),取得票最多的那个目录。
    不能用读取路径的公共前缀——只要有一次读取落在工程外(如 .gradle/caches),
    公共前缀就会塌到用户主目录,扫描它等于遍历整台机器。"""
    ROOT_MARKERS = ("settings.gradle", "settings.gradle.kts", "gradlew")
    votes = {}
    for p in paths:
        d = os.path.dirname((p or "").replace("/", os.sep))
        for _ in range(12):                      # 最多上溯 12 层
            if not d or len(d) < 4:
                break
            try:
                if any(os.path.isfile(os.path.join(d, m)) for m in ROOT_MARKERS):
                    votes[d] = votes.get(d, 0) + 1
                    break
            except OSError:
                break
            nd = os.path.dirname(d)
            if nd == d:
                break
            d = nd
    if not votes:
        return None
    return max(votes.items(), key=lambda kv: kv[1])[0]


def _scan_android_total(root, cap_files=20000, cap_dirs=8000):
    """扫描安卓工程根,算出"分母"——工程一共多少源文件/多少行,
    才能把视野换算成覆盖率。工程不在本机就返回 None(视野仍是绝对值,只是没有百分比)。
    注意:本机这份代码可能与当时跑迁移的版本不同,覆盖率是近似值。"""
    if not root or not os.path.isdir(root):
        return None
    skip = ("/build/", "/.git/", "/.gradle/", "/spec/", "/test/", "/androidtest/",
            "/.idea/", "/node_modules/")
    files = lines = ndirs = 0
    code_files = code_lines = 0          # 仅 .kt/.java/.kts —— 纯逻辑代码口径
    inventory = {}                       # 相对路径 -> 行数(全量清单,供"未读文件"呈现)
    for dirpath, dirnames, filenames in os.walk(root):
        ndirs += 1
        if ndirs > cap_dirs:
            return None          # 目录树异常大,放弃(root 可能推断错了)
        low = dirpath.replace(os.sep, "/").lower() + "/"
        if any(s in low for s in skip):
            dirnames[:] = []
            continue
        for fn in filenames:
            if not fn.lower().endswith(_ANDROID_EXT):
                continue
            fp = os.path.join(dirpath, fn)
            rel = os.path.relpath(fp, root).replace(os.sep, "/")
            if "/src/main/" not in fp.replace(os.sep, "/").lower():
                continue
            try:
                with open(fp, encoding="utf-8", errors="ignore") as fh:
                    n = sum(1 for _ in fh)
            except OSError:
                continue
            lines += n
            files += 1
            inventory[rel] = n
            if _is_code(fn):
                code_files += 1
                code_lines += n
            if files > cap_files:
                return None      # 太大,放弃(避免拖慢抽取)
    return {"files": files, "lines": lines,
            "code_files": code_files, "code_lines": code_lines,
            "inventory": inventory,          # 全量文件清单:未被读过的也要能画出来
            "root": root.replace(os.sep, "/")} if files else None


def _abort_reason(last_rec):
    """子代理是否没跑完。正常收尾 = 末条是 stop_reason=end_turn 的 assistant 消息;
    中断则停在 [Request interrupted by user],断连则停在 API Error 文本上。
    返回 'interrupted' / 'api_error' / None(正常)。"""
    if not isinstance(last_rec, dict):
        return None
    msg = last_rec.get("message")
    if not isinstance(msg, dict):
        return "interrupted"
    c = msg.get("content")
    txt = ""
    if isinstance(c, str):
        txt = c
    elif isinstance(c, list):
        txt = " ".join(b.get("text") or "" for b in c
                       if isinstance(b, dict) and b.get("type") == "text")
    low = txt.lower()
    if "request interrupted" in low or "stopped by the user" in low:
        return "interrupted"
    if last_rec.get("type") != "assistant":
        return "interrupted"
    if msg.get("stop_reason") not in (None, "end_turn"):
        return "api_error" if "api error" in low else "interrupted"
    if "api error" in low and "connection" in low:
        return "api_error"
    return None


def build_lineage(agents, main_tools, cwd):
    """从子代理(+主线)的可见源码行与 Write 还原 agent ↔ spec/Android 源 ↔ 鸿蒙文件关系。
    **不做任何归属推断**：每个 spec 文件(含 addendum)、每个 Android 源文件、每个 agent、
    每个鸿蒙文件都是独立实体，边 = 实际进入 agent 上下文的源码行 / Write。跨 session 通用。
    Android 可见行来自 Read 与搜索/命令的最终输出，排除只有路径、计数或重定向的访问。"""
    # 进 spec 列的类别：spec/ 目录下**全部**文件(canonical 的 page/feature/base 之外,
    # handoff/shared/plan/other 同样是 spec 阶段的产出与输入,都要进图)
    SPEC_COL = ("page", "feature", "base", "analysis", "handoff", "shared", "plan", "other")
    la = []            # per-agent：读了哪些 spec/android、写了哪些文件
    spec_read_by = {}  # spec rel -> {kind, read_by:set}   谁实际 Read 了这个 spec 文件
    spec_authors = {}  # spec rel -> {kind, authors:set}   谁写出这个 spec 文件
    file_writers = {}  # hmos rel -> {kind, writers:set}
    android_read_by = {}  # android 绝对路径 -> set(agent_id)
    stage_view = {}    # stage -> 该阶段的安卓源码"视野"(读到哪些文件/去重多少行)
    android_probed_by = {}  # 安卓文件 -> 只用脚本点过它的 agent(内容未必进上下文)
    g_android_iv = {}     # android 绝对路径 -> 全体 agent 的读取区间(全局去重并集用)
    g_android_tot = {}    # android 绝对路径 -> 文件总行数(totalLines)
    g_write_events = []   # (ts, rel_path, kind, val) 全局写事件(终态重放)

    def role_of(wk):
        if wk.get("ets"): return "execute"
        if wk.get("spec"): return "spec"
        if wk.get("plan"): return "plan"
        return "other"

    # 主线程作为合成贡献者。**按阶段拆开**:主线横跨全程,若合成单个 __main__ 则它
    # 没有阶段归属,任何"按阶段筛选"的视图都会整块丢掉主线的读写。
    main_by_stage = {}
    for t in main_tools:
        p = t.get("brief")
        if not p:
            continue
        st = t.get("stage")
        m = main_by_stage.get(st)
        if m is None:
            m = main_by_stage[st] = {
                "agent_id": "__main__" + (":" + st if st else ""),
                "desc": "主会话(编排/直接写盘)" + (" · " + STAGE_LABELS.get(st, st) if st else ""),
                "type": "main-thread", "stage": st,
                "_reads": [], "_writes": [],
                "_read_lines": {}, "_write_lines": {},
                "_read_iv": {}, "_read_total": {}, "_write_events": [],
                "_read_sources": {}, "_probed": [],
            }
        if t["name"] == "Read":
            m["_reads"].append(p)
            m["_read_sources"].setdefault(p, set()).add("Read")
            if t.get("rlines"):
                m["_read_lines"][p] = m["_read_lines"].get(p, 0) + t["rlines"]
                m["_read_iv"].setdefault(p, []).append((t.get("rstart") or 1, t["rlines"]))
                if t.get("rtotal"):
                    m["_read_total"][p] = max(m["_read_total"].get(p, 0), t["rtotal"])
            else:
                for s0, c0 in (t.get("_rspans") or []):
                    m["_read_lines"][p] = m["_read_lines"].get(p, 0) + c0
                    m["_read_iv"].setdefault(p, []).append((s0, c0))
        elif t["name"] in ("Write", "Edit"):
            m["_writes"].append(p)
            if t.get("wlines"):
                m["_write_lines"][p] = m["_write_lines"].get(p, 0) + t["wlines"]
                if t.get("wevent"):
                    m["_write_events"].append((t.get("ts") or "", p, t["wevent"][0], t["wevent"][1]))
        for pp in t.get("_probed_paths") or []:
            m["_probed"].append(pp)
        for event in t.get("_visible_source_lines") or []:
            path = event["path"]
            m["_reads"].append(path)
            m["_read_sources"].setdefault(path, set()).add(event["via"])
            for start, count in event["intervals"]:
                m["_read_iv"].setdefault(path, []).append((start, count))
                m["_read_lines"][path] = m["_read_lines"].get(path, 0) + count
            try:
                with open(path, encoding="utf-8", errors="ignore") as stream:
                    total = sum(1 for _ in stream)
            except OSError:
                total = 0
            if total:
                m["_read_total"][path] = max(m["_read_total"].get(path, 0), total)
    contributors = list(main_by_stage.values()) + agents

    for a in contributors:
        reads_rel = [_rel(p, cwd) for p in a.get("_reads", [])]
        writes_rel = [_rel(p, cwd) for p in a.get("_writes", [])]
        # 行数 map 相对化(同一 rel 多次读/写累加)
        rl_rel, wl_rel, iv_rel, tot_rel, src_rel = {}, {}, {}, {}, {}
        for p, n in (a.get("_read_lines") or {}).items():
            rp = _rel(p, cwd); rl_rel[rp] = rl_rel.get(rp, 0) + n
        for p, n in (a.get("_write_lines") or {}).items():
            wp = _rel(p, cwd); wl_rel[wp] = wl_rel.get(wp, 0) + n
        for p, ivs in (a.get("_read_iv") or {}).items():
            rp = _rel(p, cwd); iv_rel.setdefault(rp, []).extend(ivs)
        for p, n in (a.get("_read_total") or {}).items():
            rp = _rel(p, cwd); tot_rel[rp] = max(tot_rel.get(rp, 0), n)
        for p, names in (a.get("_read_sources") or {}).items():
            rp = _rel(p, cwd)
            src_rel.setdefault(rp, set()).update(names)
        for ev in (a.get("_write_events") or []):
            rp = _rel(ev[1], cwd)
            if _is_hmos(rp) == "ets":
                g_write_events.append((ev[0] or "", rp, ev[2], ev[3],
                                       a.get("stage") or "?"))
        lines_spec = lines_android = lines_ets = android_dedup = 0
        lines_proj = 0
        wk = {}
        # 实质 spec 读取——每个文件独立(含 addendum)；shared/plan 另存供抽屉展示；
        # 工程外源码后缀 = Android 参考读取；工程内相对路径 = 项目自读(review/续写他人产出)
        spec_reads, shared_reads, android_full, proj_reads = [], [], [], []
        for r in sorted(set(reads_rel)):
            k = _spec_kind(r)
            if k:   # spec/ 目录下全算(不再只认 canonical 的 page/feature/base)
                spec_reads.append(r)
                lines_spec += rl_rel.get(r, 0)
                if k in ("shared", "plan"):
                    shared_reads.append(r)   # 子集视图:抽屉里仍单列跨切面 spec
            elif _is_abs(r):
                low = r.lower()
                if any(x in low for x in _EXTERNAL_EXCLUDE):
                    continue
                if low.endswith(_ANDROID_EXT):
                    android_full.append(r)
                    lines_android += rl_rel.get(r, 0)
                    android_dedup += _union_lines(iv_rel.get(r, []))
            else:
                low = r.lower()
                if any(x in low for x in _EXTERNAL_EXCLUDE):
                    continue
                proj_reads.append(r)   # 工程内文件(含读别人的 .ets/配置)
                lines_proj += rl_rel.get(r, 0)
        w_ets, w_spec, w_res, w_other = [], [], [], []
        for w in sorted(set(writes_rel)):
            sk = _spec_kind(w)
            hk = _is_hmos(w)
            if not sk and not hk:
                # 既不是 spec 也不是鸿蒙产物:仍然是这个 agent 的产出(构建脚本、
                # 临时工具等),按"其它产物"收下——不按目录预判它有没有价值。
                # 工程外的工具/缓存文件(.claude、migbot skills 等)不算。
                if not any(x in w.lower() for x in _EXTERNAL_EXCLUDE):
                    w_other.append(w)
                    fw = file_writers.setdefault(w, {"kind": "other", "writers": set(), "lines": 0})
                    fw["writers"].add(a["agent_id"])
                    fw["lines"] += wl_rel.get(w, 0)
                continue
            if hk == "ets":
                wk["ets"] = wk.get("ets", 0) + 1
                w_ets.append(w)
                lines_ets += wl_rel.get(w, 0)
                fw = file_writers.setdefault(w, {"kind": "ets", "writers": set(), "lines": 0})
                fw["writers"].add(a["agent_id"])
                fw["lines"] += wl_rel.get(w, 0)
            elif hk in ("res", "cfg"):
                w_res.append(w)
                fw = file_writers.setdefault(w, {"kind": hk, "writers": set(), "lines": 0})
                fw["writers"].add(a["agent_id"])
                fw["lines"] += wl_rel.get(w, 0)
            elif sk:   # spec/ 目录下全算(handoff/shared/plan/other 也是 spec 产出)
                wk["spec"] = wk.get("spec", 0) + 1
                w_spec.append(w)
                spec_authors.setdefault(w, {"kind": sk, "authors": set()})["authors"].add(a["agent_id"])
                if sk == "plan":
                    wk["plan"] = wk.get("plan", 0) + 1
        # ---- 阶段视野:这个阶段的 agent 一共"看到"了多少安卓源码 ----
        # 与图上口径一致:剔除中断且零产出的白跑分身;分析型 agent(不落盘只返回结论)
        # 的阅读同样算视野——它读过就是看到了。
        n_out_a = len(w_ets) + len(w_spec) + len(w_res) + len(w_other)
        # 脚本探测:命令点到过的源码文件。与"真读"分开记——`python x.py`/`wc -l`/`ls`
        # 只给出统计与结构,代码本身没进上下文,混算会虚高;完全不记又会让脚本流
        # 的会话看着像什么都没做。
        probed_rel = []
        for pp in (a.get("_probed") or []):
            r = _rel(pp, cwd)
            low = r.lower()
            if any(x in low for x in _EXTERNAL_EXCLUDE):
                continue
            if _spec_kind(r) or _is_hmos(r):
                continue
            if low.endswith(_ANDROID_EXT):
                probed_rel.append(r)
        if (android_full or probed_rel) and not (a.get("aborted") and n_out_a == 0):
            sv = stage_view.setdefault(a.get("stage") or "?",
                                       {"iv": {}, "tot": {}, "cum": 0, "agents": set(),
                                        "probed": set()})
            sv.setdefault("probed", set()).update(probed_rel)
            sv["agents"].add(a["agent_id"])
            sv["cum"] += lines_android
            for r in android_full:
                sv["iv"].setdefault(r, []).extend(iv_rel.get(r, []))
                if tot_rel.get(r):
                    sv["tot"][r] = max(sv["tot"].get(r, 0), tot_rel[r])

        # 全局读取桶(spec 列 read_by / android 列与统计)登记**所有有效产出方**。
        # 判据与上面的阶段视野一致:落盘产出(.ets / spec/ 下任意文件)算产出,
        # **把结论作为返回值交回编排方**同样算产出——workflow 模式的理解/审计 agent
        # 读遍全仓却一个文件都不写，按"必须落盘"筛会把整个理解阶段从图上抹掉。
        # 只有【中断且零产出】的白跑分身被排除(它们随后会被重发,留着就是重复计数)。
        if w_ets or w_spec or not (a.get("aborted") and n_out_a == 0):
            for r in spec_reads:
                spec_read_by.setdefault(r, {"kind": _spec_kind(r), "read_by": set()})["read_by"].add(a["agent_id"])
            for r in probed_rel:
                android_probed_by.setdefault(r, set()).add(a["agent_id"])
            for r in android_full:
                android_read_by.setdefault(r, set()).add(a["agent_id"])
                g_android_iv.setdefault(r, []).extend(iv_rel.get(r, []))
                if tot_rel.get(r):
                    g_android_tot[r] = max(g_android_tot.get(r, 0), tot_rel[r])
        # **不做归属推断**：只记该 agent 实际读了哪些 spec/android、实际写了哪些文件
        la.append({
            "agent_id": a["agent_id"], "desc": a.get("desc", ""), "type": a.get("type"),
            "stage": a.get("stage"), "wf_phase": a.get("wf_phase"), "role": role_of(wk),
            "aborted": a.get("aborted"),   # 中断/断连的分身,后续会被重发一次
            "spec_reads": spec_reads,        # 实质 spec 文件(含 addendum)，每个独立
            "shared_reads": shared_reads,    # 跨切面共享 spec(ledger/registry/plan)
            "_android_full": android_full,   # Android 源码绝对路径(下方相对化后剥离)
            "_android_iv": {
                r: _merge_line_intervals(iv_rel.get(r, [])) for r in android_full
            },
            "_android_sources": {
                r: sorted(src_rel.get(r, [])) for r in android_full
            },
            "writes_ets": w_ets, "writes_spec": w_spec, "writes_res": w_res,
            "writes_other": w_other,         # 其它产物(构建脚本/配置等)
            "n_spec_read": len(spec_reads), "n_ets": len(w_ets),
            "n_spec_w": len(w_spec),         # 产出的 spec 文件数(spec/ 下全算)
            "n_out": len(w_spec) + len(w_ets) + len(w_res) + len(w_other),  # 全部产出
            "lines_spec": lines_spec,        # spec 累计读取行
            "lines_android": lines_android,  # Android 源码累计读取行
            "lines_android_dedup": android_dedup,  # 该 agent 安卓读取去重(区间并集)
            "lines_ets": lines_ets,          # .ets 累计写入行(Write 全文 + Edit new_string)
            "n_proj": len(proj_reads),       # 工程内读取(自家产出/配置,非 spec 非安卓)
            "lines_proj": lines_proj,
            # 主线视野要能列出明细;子代理只留计数,防 trace 膨胀
            **({"proj_reads": proj_reads[:800]} if a.get("type") == "main-thread" else {}),
        })

    # ---- Android 根推断：全部外部源码读的**段级公共前缀**(大小写不敏感) ----
    # 单根工程 → 根=工程目录,分组=模块;若跨多个安卓仓,根收敛到公共父目录,分组=各仓名。
    # 注意：同一会话里 git-bash 风格 `/c/Users/...` 与 Windows 风格 `C:/Users/...`
    # 会同时出现,不先归一的话公共前缀直接塌成空串,android_root 失效、相对化全废。
    def _drive_norm(p):
        m = re.match(r"^/([a-zA-Z])/", p)
        return (m.group(1).upper() + ":/" + p[3:]) if m else p

    android_read_by = {_drive_norm(k): v for k, v in android_read_by.items()}
    all_android = sorted(android_read_by)
    android_root = ""
    if all_android:
        seglists = [p.split("/") for p in all_android]
        common = []
        for parts in zip(*seglists):
            if all(x.lower() == parts[0].lower() for x in parts[1:]):
                common.append(parts[0])
            else:
                break
        if len(all_android) == 1:
            common = common[:-1]   # 单文件时根=其所在目录
        android_root = "/".join(common)

    def _a_rel(p):
        p = _drive_norm(p)
        if android_root and p.lower().startswith(android_root.lower()):
            return p[len(android_root):].lstrip("/")
        return p

    android_out = [{"path": _a_rel(p), "readers": sorted(ids)}
                   for p, ids in sorted(android_read_by.items())]
    # 补齐"全工程有、但没有任何 agent 读过"的文件 —— 不补的话图上只剩读过的,
    # 两个 session 的分母不同、盲区不可见(BoxApplication 这类缺读文件会直接消失)。
    # 判重必须回到**扫描根**这一个基准:android_root(读取路径公共前缀)与
    # scan root(gradle 根)未必相同,直接拿 _a_rel 的结果比会漏判成全部未读。
    _scan = _scan_android_total(_find_gradle_root(android_read_by))
    _oos_abs = set()   # 读到但不在扫描清单里的绝对路径(不进覆盖率分子)
    if _scan and _scan.get("inventory"):
        _sr = _scan["root"].replace("\\", "/").rstrip("/")
        _srl = _sr.lower()

        def _scan_rel(abs_p):
            q = _drive_norm(str(abs_p).replace("\\", "/"))
            return q[len(_sr):].lstrip("/").lower() if q.lower().startswith(_srl) else None

        _seen = {r for r in (_scan_rel(p) for p in android_read_by) if r}
        for rel, nlines in sorted(_scan["inventory"].items()):
            if rel.lower() in _seen:
                continue
            android_out.append({"path": _a_rel(_sr + "/" + rel),
                                "readers": [], "unread": True, "lines": nlines})
        # 读到但【不在清单里】的文件(build/ 产物、test/、.idea/、根级 gradle 等)
        # 仍要画进图,但不能进覆盖率分子——否则分子含分母没有的项,百分比会穿 100%。
        _inv = {k.lower() for k in _scan["inventory"]}
        _by_rel = {}
        for p in android_read_by:
            r = _scan_rel(p)
            ok = (r.lower() in _inv) if r else False
            _by_rel[_a_rel(p)] = ok
            if not ok:
                _oos_abs.add(p)
        for x in android_out:
            if not x.get("unread") and not _by_rel.get(x["path"], True):
                x["oos"] = True   # out of scope:清单外
    for x in la:
        android_full = x.pop("_android_full")
        android_iv = x.pop("_android_iv")
        android_sources = x.pop("_android_sources")
        x["android_reads"] = [_a_rel(p) for p in android_full]
        x["android_visible_lines"] = [
            {
                "path": _a_rel(path),
                "spans": [[start, start + count - 1] for start, count in android_iv.get(path, [])],
                "lines": _union_lines(android_iv.get(path, [])),
                "via": android_sources.get(path, []),
            }
            for path in android_full
            if android_iv.get(path)
        ]
        x["n_android"] = len(x["android_reads"])

    # spec 文件全集 = 被读到 ∪ 被写出的**所有** spec/ 下文件(每个独立,含 addendum)
    spec_paths = set(spec_read_by) | set(spec_authors)
    specs_out = []
    for p in sorted(spec_paths):
        kind = (spec_read_by.get(p) or spec_authors.get(p))["kind"]
        specs_out.append({
            "path": p, "kind": kind,
            "read_by": sorted(spec_read_by.get(p, {}).get("read_by", [])),
            "authors": sorted(spec_authors.get(p, {}).get("authors", [])),
        })
    # ---- 终态重放：全局写事件按时间排序，Write 覆盖 / Edit 净增减 → 每 .ets 最终行数 ----
    # 顺带产出:产码进度曲线(工程内 .ets 终态总行数随时间)与每文件"末笔归属阶段"
    g_write_events.sort(key=lambda e: e[0])
    final_lines = {}
    last_writer_stage = {}
    code_timeline = []
    running = 0
    for ts_e, rp, kind, val, st in g_write_events:
        prev = final_lines.get(rp, 0)
        if kind == "set":
            final_lines[rp] = val
        else:
            final_lines[rp] = max(0, prev + val)
        last_writer_stage[rp] = st
        running += final_lines[rp] - prev
        if ts_e:
            code_timeline.append({"ts": ts_e, "lines": running})
    if len(code_timeline) > 1500:   # 降采样,首末保留
        step = len(code_timeline) // 1500 + 1
        code_timeline = code_timeline[::step] + [code_timeline[-1]]

    # ---- 安卓全局去重：跨 agent 区间并集；触达文件体量 = totalLines(缺失用并集兜底) ----
    android_dedup_total = sum(_union_lines(ivs) for ivs in g_android_iv.values())
    android_touched_total = sum(g_android_tot.get(p) or _union_lines(g_android_iv.get(p, []))
                                for p in android_read_by)
    _code_read = [p for p in android_read_by if _is_code(p)]
    android_code_dedup_total = sum(_union_lines(g_android_iv.get(p, [])) for p in _code_read)
    android_code_touched_total = sum(g_android_tot.get(p) or _union_lines(g_android_iv.get(p, []))
                                     for p in _code_read)
    # 与 android_total 同分母的口径:剔除清单外文件(build/、test/、.idea/ 等)
    android_dedup_in_scope = sum(_union_lines(ivs) for p, ivs in g_android_iv.items()
                                 if p not in _oos_abs)
    android_code_dedup_in_scope = sum(_union_lines(g_android_iv.get(p, []))
                                      for p in _code_read if p not in _oos_abs)

    files_out = [{"path": p, "kind": v["kind"], "writers": sorted(v["writers"]), "lines": v.get("lines", 0),
                  "final_lines": final_lines.get(p, 0)}
                 for p, v in sorted(file_writers.items())]

    # ---- 各阶段的安卓源码视野 ----
    # lines_dedup  = 跨 agent 区间并集,同一段代码被多人读只算一次(真实"看过"的量)
    # lines_touched= 被打开过的文件的完整体量,dedup/touched = 这些文件读了多深
    stage_view_out = {}
    for st, sv in stage_view.items():
        # 与全局同口径:清单外文件(build/、test/、.idea/…)不进分子,否则阶段视野条会穿 100%
        sv["iv"] = {p: v for p, v in sv["iv"].items() if _drive_norm(p) not in _oos_abs}
        dedup = sum(_union_lines(ivs) for ivs in sv["iv"].values())
        touched = sum(sv["tot"].get(p) or _union_lines(sv["iv"].get(p, []))
                      for p in sv["iv"])
        code = [p for p in sv["iv"] if _is_code(p)]      # 同一批区间,只留逻辑代码
        # 仅探测 = 脚本点过、但没有任何源码行进入上下文;同样剔除清单外文件
        probe_only = sorted(p for p in sv.get("probed", ())
                            if p not in sv["iv"] and _drive_norm(p) not in _oos_abs)
        stage_view_out[st] = {
            "probe_files": len(probe_only),
            "probe_code_files": sum(1 for p in probe_only if _is_code(p)),
            "files": len(sv["iv"]), "agents": len(sv["agents"]),
            "lines_cum": sv["cum"], "lines_dedup": dedup, "lines_touched": touched,
            "code_files": len(code),
            "code_lines_dedup": sum(_union_lines(sv["iv"][p]) for p in code),
            "code_lines_touched": sum(sv["tot"].get(p) or _union_lines(sv["iv"][p]) for p in code),
        }
    # ---- 各阶段产出:累计写入行(该阶段 agent 的 Write/Edit 总量)与
    #      终态归属行(末笔落在该阶段的文件的最终行数——改谁算谁的)----
    by_stage = {}
    for x in la:
        st = x.get("stage") or "?"
        b = by_stage.setdefault(st, {"lines_ets_written": 0, "ets_files_touched": 0,
                                     "ets_agents": 0, "lines_ets_final_owned": 0})
        b["lines_ets_written"] += x["lines_ets"]
        b["ets_files_touched"] += x["n_ets"]
        if x["n_ets"]:
            b["ets_agents"] += 1
    for rp, st in last_writer_stage.items():
        b = by_stage.setdefault(st, {"lines_ets_written": 0, "ets_files_touched": 0,
                                     "ets_agents": 0, "lines_ets_final_owned": 0})
        b["lines_ets_final_owned"] += final_lines.get(rp, 0)

    kc = Counter(s["kind"] for s in specs_out)
    return {
        "cwd": cwd,
        "agents": la,
        "specs": specs_out,
        "files": files_out,
        "android": android_out,
        "android_root": android_root,
        "code_timeline": code_timeline,
        "by_stage": by_stage,
        # inventory 已展开进 android_out 的 unread 项,不重复落盘
        "android_total": ({k: v for k, v in _scan.items() if k != "inventory"} if _scan else None),
        "stage_view": stage_view_out,
        "stats": {
            "spec_files": len(specs_out),
            "spec_feature": kc.get("feature", 0),
            "spec_page": kc.get("page", 0),
            "spec_base": kc.get("base", 0),
            "spec_handoff": kc.get("handoff", 0),
            "spec_analysis": kc.get("analysis", 0),
            "spec_shared": kc.get("shared", 0),
            "spec_plan": kc.get("plan", 0),
            "spec_other": kc.get("other", 0),
            # 只统计"被读过的"(unread 项是为了画图补进 android_out 的,不进覆盖率分子)
            "android_files": sum(1 for x in android_out if not x.get("unread")),
            "android_code_files": sum(1 for x in android_out
                                      if not x.get("unread") and _is_code(x["path"])),
            "android_unread_files": sum(1 for x in android_out if x.get("unread")),
            # 覆盖率专用分子:读过 ∩ 扫描清单(与 android_total 同分母,不会穿 100%)
            "android_files_in_scope": sum(1 for x in android_out
                                          if not x.get("unread") and not x.get("oos")),
            "android_files_oos": sum(1 for x in android_out if x.get("oos")),
            "lines_android_dedup_in_scope": android_dedup_in_scope,
            "lines_android_code_dedup_in_scope": android_code_dedup_in_scope,
            # 产出方 = 产码(.ets) + 产 spec 两类 agent
            "producing_agents": sum(1 for x in la if x["n_out"] > 0),
            "ets_agents": sum(1 for x in la if x["n_ets"] > 0),
            "spec_agents": sum(1 for x in la if x["n_spec_w"] > 0 and x["n_ets"] == 0),
            "ets_files": sum(1 for f in files_out if f["kind"] == "ets"),
            "read_edges": sum(len(s["read_by"]) for s in specs_out),
            "android_read_edges": sum(len(x["readers"]) for x in android_out),
            "write_edges": sum(len(f["writers"]) for f in files_out if f["kind"] == "ets"),
            # 读行数总量计所有产出方(与图中列一致)——含 spec 阶段 agent 的安卓读取
            "lines_spec_read": sum(x["lines_spec"] for x in la
                                   if x["n_ets"] > 0 or x["n_spec_w"] > 0),
            "lines_android_read": sum(x["lines_android"] for x in la
                                      if x["n_ets"] > 0 or x["n_spec_w"] > 0),
            "lines_android_dedup": android_dedup_total,     # 全局去重:跨 agent 区间并集
            "lines_android_touched": android_touched_total, # 被触达安卓文件的完整体量(totalLines)
            # 纯逻辑代码口径(.kt/.java/.kts):分子分母同时收紧,不被布局 xml / gradle 稀释
            "lines_android_code_dedup": android_code_dedup_total,
            "lines_android_code_touched": android_code_touched_total,
            "lines_ets_written": sum(x["lines_ets"] for x in la),
            "lines_ets_final": sum(final_lines.get(f["path"], 0) for f in files_out if f["kind"] == "ets"),
        },
    }


def load_workflow_runs(session_dir):
    """读取 <session>/workflows/wf_*.json 的编排元数据。

    Workflow 模式下子代理不由 Task 派发，因而没有 toolUseId，也没有描述性 meta；
    编排信息(名字、阶段、每个 agent 的 label)只存在于这里。返回:
      runs   : runId -> {name, task_id, phases, start_ts, status, tokens, tool_calls}
      byagent: agent_id -> {run_id, wf_name, label, phase, model, state, tokens, tool_calls}
    """
    runs, byagent = {}, {}
    wdir = os.path.join(session_dir, "workflows")
    if not os.path.isdir(wdir):
        return runs, byagent
    for fn in sorted(os.listdir(wdir)):
        if not (fn.startswith("wf_") and fn.endswith(".json")):
            continue
        try:
            d = json.load(open(os.path.join(wdir, fn), encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(d, dict):
            continue
        rid = d.get("runId") or fn[:-len(".json")]
        name = d.get("workflowName") or rid
        runs[rid] = {
            "run_id": rid,
            "name": name,
            "task_id": d.get("taskId"),
            "summary": (d.get("summary") or "")[:240],
            "phases": [p.get("title") for p in (d.get("phases") or []) if isinstance(p, dict)],
            "status": d.get("status"),
            "duration_ms": d.get("durationMs"),
            "agent_count": d.get("agentCount"),
            "tokens": d.get("totalTokens"),
            "tool_calls": d.get("totalToolCalls"),
            "script_path": d.get("scriptPath"),
        }
        for e in (d.get("workflowProgress") or []):
            if not isinstance(e, dict) or e.get("type") != "workflow_agent":
                continue
            aid = e.get("agentId")
            if not aid:
                continue
            byagent[aid] = {
                "run_id": rid,
                "wf_name": name,
                "label": e.get("label") or "",
                "phase": e.get("phaseTitle") or "",
                "model": e.get("model"),
                "state": e.get("state"),
                "tokens": e.get("tokens"),
                "tool_calls": e.get("toolCalls"),
                "prompt": (e.get("promptPreview") or "")[:400],
                "result": (e.get("resultPreview") or "")[:400],
            }
    return runs, byagent


def extract(path):
    records = load_main_session(path)
    session_dir = os.path.splitext(path)[0]  # <dir>/<session-id>/
    subagents_dir = os.path.join(session_dir, "subagents")
    wf_runs, wf_byagent = load_workflow_runs(session_dir)

    meta = {
        "source_file": os.path.abspath(path),
        "schema_version": "1.8",
        "session_id": None,
        "cc_version": None,
        "cwd": None,
        "model": None,
        "started_at": None,
        "ended_at": None,
        "record_count": len(records),
    }

    tools = []          # 主线工具调用
    prompts = []        # 用户键入
    markers = []        # compact 边界等
    skill_calls = []    # (idx, ts, skill_name, tool_use_id)
    tool_by_id = {}     # tool_use_id -> tools[] 下标
    usage_by_idx = []   # (idx, usage dict)
    # 同一 assistant 消息在流式写入下会产生多条记录:prompt 侧字段一致,
    # 但 output_tokens 逐步累计——必须取【末条】为最终权威值(取首条会严重低估 output)
    msg_usage = {}      # message.id -> {idx, ts, model, u(最新)}
    context_timeline = []  # 主线每次 LLM 请求的上下文占用采样
    billing = {}        # model -> 计费桶(主线+子代理合并,按 message.id 去重)

    def block_chars(msg):
        """本条记录携带的 content 块的字符量,按 thinking/正文/工具参数三分。
        流式写盘下同一 message.id 分多条记录、每条一个增量块——必须跨记录累加,
        不能取末条(末条只有最后一个块)。"""
        th = tx = tu = 0
        c = msg.get("content")
        if isinstance(c, list):
            for b in c:
                if not isinstance(b, dict):
                    continue
                bt = b.get("type")
                if bt == "thinking":
                    th += len(b.get("thinking") or "")
                elif bt == "redacted_thinking":
                    th += len(b.get("data") or "")
                elif bt == "text":
                    tx += len(b.get("text") or "")
                elif bt == "tool_use":
                    try:
                        tu += len(json.dumps(b.get("input") or {}, ensure_ascii=False))
                    except (TypeError, ValueError):
                        pass
        return th, tx, tu

    def bill(model, u):
        b = billing.setdefault(model, {"req": 0, "inp": 0, "cread": 0,
                                       "cw5": 0, "cw1h": 0, "out": 0})
        b["req"] += 1
        b["inp"] += u.get("input_tokens") or 0
        b["cread"] += u.get("cache_read_input_tokens") or 0
        cc = u.get("cache_creation")
        if isinstance(cc, dict):
            b["cw5"] += cc.get("ephemeral_5m_input_tokens") or 0
            b["cw1h"] += cc.get("ephemeral_1h_input_tokens") or 0
        else:
            b["cw1h"] += u.get("cache_creation_input_tokens") or 0
        b["out"] += u.get("output_tokens") or 0

    prev_ts = None  # 上一条带时间戳记录
    for i, rec in enumerate(records):
        ts = rec.get("timestamp")
        if ts:
            if meta["started_at"] is None:
                meta["started_at"] = ts
            meta["ended_at"] = ts
        if meta["session_id"] is None and rec.get("sessionId"):
            meta["session_id"] = rec["sessionId"]
        if meta["cc_version"] is None and rec.get("version"):
            meta["cc_version"] = rec["version"]
        if meta["cwd"] is None and rec.get("cwd"):
            meta["cwd"] = rec["cwd"]

        rtype = rec.get("type")

        if rtype == "system" and rec.get("subtype") == "compact_boundary":
            markers.append({"idx": i, "ts": ts, "kind": "compact"})

        if rtype == "user":
            if rec.get("promptSource") == "typed":
                content = rec.get("message", {}).get("content")
                if isinstance(content, str) and content.strip():
                    prompts.append({"idx": i, "ts": ts, "wait_ms": 0,
                                    "text": " ".join(content.split())[:400]})
            # tool_result 回填耗时与状态
            msg = rec.get("message")
            if isinstance(msg, dict) and isinstance(msg.get("content"), list):
                for block in msg["content"]:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        tid = block.get("tool_use_id")
                        if tid in tool_by_id:
                            t = tools[tool_by_id[tid]]
                            t["dur_ms"] = ms_between(t["ts"], ts)
                            t["ok"] = not block.get("is_error", False)
                            t["result"] = result_snippet(block, rec.get("toolUseResult"))
                            full_result = result_text(block, rec.get("toolUseResult"))
                            t["_result_rec"] = i
                            tur = rec.get("toolUseResult")
                            if isinstance(tur, dict):
                                t["_tur"] = tur
                                if t["name"] == "Read":
                                    fl = tur.get("file")
                                    if isinstance(fl, dict) and fl.get("numLines"):
                                        t["rlines"] = fl["numLines"]
                                        t["rstart"] = fl.get("startLine") or 1
                                        t["rtotal"] = fl.get("totalLines") or 0
                            if t["name"] == "Read" and not t.get("rlines") and t["ok"]:
                                # 无 toolUseResult 时从正文 `N\t` 行号前缀还原
                                t["_rspans"] = _spans_from_numbered_text(full_result)
                            if t["ok"]:
                                visible = _infer_visible_source_lines(
                                    t["name"], t.get("_inp") or {}, full_result, meta["cwd"]
                                )
                                if visible:
                                    t["_visible_source_lines"] = visible
                                probed = _script_probed_paths(
                                    t["name"], t.get("_inp") or {}, meta["cwd"]
                                )
                                if probed:
                                    t["_probed_paths"] = probed

        msg = rec.get("message")
        if isinstance(msg, dict):
            if meta["model"] is None and msg.get("model") and not msg["model"].startswith("<"):
                meta["model"] = msg["model"]
            usage = msg.get("usage")
            # <synthetic> 是 Claude Code 本地合成的记录(如 API 连接错误),不是真实 LLM 请求
            if isinstance(usage, dict) and msg.get("model") != "<synthetic>":
                mid = msg.get("id")
                slot = msg_usage.get(mid)
                if slot is None:
                    slot = msg_usage[mid] = {"idx": i, "ts": ts,
                                             "model": msg.get("model") or "unknown",
                                             "u": usage, "ch": [0, 0, 0]}
                else:
                    slot["u"] = usage  # 末条为最终权威 usage
                if rtype == "assistant":  # 本条的增量块字符,跨记录累加
                    th, tx, tu = block_chars(msg)
                    slot["ch"][0] += th
                    slot["ch"][1] += tx
                    slot["ch"][2] += tu
            content = msg.get("content")
            if isinstance(content, list):
                for block in content:
                    if not (isinstance(block, dict) and block.get("type") == "tool_use"):
                        continue
                    name = block.get("name")
                    inp = block.get("input", {})
                    entry = {
                        "seq": len(tools),
                        "idx": i,
                        "ts": ts,
                        "name": name,
                        "brief": brief_tool_target(name, inp),
                        "ok": None,
                        "dur_ms": None,
                        "tuid": block.get("id"),
                        "_inp": inp,
                    }
                    if name == "Write":
                        entry["wlines"] = (inp.get("content") or "").count("\n") + 1
                        entry["wevent"] = ["set", entry["wlines"]]
                    elif name == "Edit":
                        entry["wlines"] = (inp.get("new_string") or "").count("\n") + 1
                        entry["wevent"] = ["delta", entry["wlines"] - ((inp.get("old_string") or "").count("\n") + 1)]
                    if name == "Skill":
                        skill = inp.get("skill")
                        entry["skill"] = skill
                        skill_calls.append((i, ts, skill, block.get("id")))
                    if name in ("Agent", "Task"):
                        entry["agent_type"] = inp.get("subagent_type", "general-purpose")
                        entry["agent_desc"] = inp.get("description", "")
                    tools.append(entry)
                    tool_by_id[block.get("id")] = len(tools) - 1

        if ts:
            prev_ts = ts

    # ---- usage 定稿(每条消息取末条记录)----
    # output 构成:按该消息 thinking/正文/工具参数的字符占比,把 output token 摊到三类。
    # 字符≠token,但同一消息内三类的相对占比是可靠的(同一 tokenizer)。
    main_split = {"thinking": 0.0, "text": 0.0, "tool": 0.0}
    for slot in sorted(msg_usage.values(), key=lambda s: s["idx"]):
        u = slot["u"]
        usage_by_idx.append((slot["idx"], u))
        bill(slot["model"], u)
        o = u.get("output_tokens") or 0
        th, tx, tu = slot.get("ch") or (0, 0, 0)
        tot_ch = th + tx + tu
        if tot_ch:
            main_split["thinking"] += o * th / tot_ch
            main_split["text"] += o * tx / tot_ch
            main_split["tool"] += o * tu / tot_ch
        else:
            main_split["text"] += o
        inp = u.get("input_tokens") or 0
        cread = u.get("cache_read_input_tokens") or 0
        cwrite = u.get("cache_creation_input_tokens") or 0
        context_timeline.append({"ts": slot["ts"], "ctx": inp + cread + cwrite,
                                 "out": u.get("output_tokens") or 0,
                                 "inp": inp, "cread": cread, "cwrite": cwrite})

    # ---- 阶段切分 ----
    # 主信号:attributionSkill —— harness 给每条记录盖的确定性 skill 归属戳。
    # 即使某管线阶段没有再触发一次 Skill 工具调用(resume 续跑 / 斜杠命令进入 /
    # 在导出边界之前进入),归属戳仍在,据此切阶段。Skill 工具调用退为兜底。
    # skill 打包为插件后名字带命名空间前缀(如 migbot:a2h-spec),匹配前先归一。
    def norm_skill(name):
        return (name or "").split(":")[-1]

    pipe_boundaries = []
    seen_pipeline = set()
    cur_stage = None
    for i, rec in enumerate(records):
        a = norm_skill(rec.get("attributionSkill"))
        if a in PIPELINE_SKILLS and a != cur_stage:
            pipe_boundaries.append((i, a))
            cur_stage = a
            seen_pipeline.add(a)
    # 兜底:仅有 Skill 工具调用、没有 attributionSkill 归属的管线 skill 也补一个边界
    for idx, ts, skill, _ in skill_calls:
        nskill = norm_skill(skill)
        if nskill in PIPELINE_SKILLS and nskill not in seen_pipeline:
            pipe_boundaries.append((idx, nskill))
            seen_pipeline.add(nskill)
    # Workflow 模式:主线每次 Workflow 调用开一个阶段(阶段名取脚本 meta.name)。
    # 这样"整段一个 Session"会按编排单元自然拆开，与管线 skill 的阶段等价。
    wf_stage_of_run = {}
    if wf_runs:
        by_task = {r["task_id"]: rid for rid, r in wf_runs.items() if r.get("task_id")}
        launched = []
        for t in tools:
            if t["name"] != "Workflow":
                continue
            m = re.search(r"Task ID:\s*(\S+)", t.get("result") or "")
            rid = by_task.get(m.group(1)) if m else None
            launched.append((t["idx"], rid))
        # 没有 Task ID 回填(会话被截断)时按启动顺序对齐 startTime
        if launched and any(r is None for _, r in launched):
            spare = [rid for rid in sorted(wf_runs, key=lambda k: wf_runs[k].get("run_id") or "")
                     if rid not in {r for _, r in launched if r}]
            launched = [(i, r or (spare.pop(0) if spare else None)) for i, r in launched]
        for idx, rid in launched:
            if not rid:
                continue
            key = "wf:" + wf_runs[rid]["name"]
            wf_stage_of_run[rid] = key
            pipe_boundaries.append((idx, key))
    pipe_boundaries.sort()

    # 首个管线边界之前的记录归 setup(若首边界即 idx 0 则无 setup 段)
    boundaries = []
    if not pipe_boundaries or pipe_boundaries[0][0] > 0:
        boundaries.append((0, "setup"))
    boundaries += pipe_boundaries
    boundaries.sort()
    # 同一 idx 去重(保留先出现者),避免退化出空段(end_idx=-1)
    deduped = []
    for bnd in boundaries:
        if deduped and deduped[-1][0] == bnd[0]:
            continue
        deduped.append(bnd)
    boundaries = deduped

    stages = []
    for b, (start_idx, stage_key) in enumerate(boundaries):
        end_idx = boundaries[b + 1][0] - 1 if b + 1 < len(boundaries) else len(records) - 1
        seg_records = records[start_idx:end_idx + 1]
        ts_list = [r.get("timestamp") for r in seg_records if r.get("timestamp")]
        stages.append({
            "id": f"s{b}",
            "stage": stage_key,
            "label": (stage_key[3:] if stage_key.startswith("wf:")
                      else STAGE_LABELS.get(stage_key, stage_key)),
            "start_idx": start_idx,
            "end_idx": end_idx,
            # 取最早/最晚而不是首条/末条:主线 jsonl 的时间戳并非严格按下标递增
            # (并行子代理的完成通知会乱序落盘),按首末取会让相邻阶段的区间互相咬进去
            "start_ts": min(ts_list) if ts_list else None,
            "end_ts": max(ts_list) if ts_list else None,
            "duration_ms": ms_between(min(ts_list), max(ts_list)) if ts_list else None,
            "tool_counts": {},
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "helper_skills": [],
            "artifacts": [],
            "agent_count": 0,
            "prompt_idxs": [],
            "wait_ms": 0,       # 等待用户输入的空转时长
            "active_ms": None,  # 活跃时长 = duration - wait(定稿于阶段归属之后)
        })

    # 无任何管线 Skill 调用的通用会话:整段作为单一 Session 阶段展示
    if len(stages) == 1:
        stages[0]["stage"] = "session"
        stages[0]["label"] = "Session"

    # 同一阶段多次出现(如 verify→execute 回环)时,后续段落编号区分
    seen_stage_keys = {}
    for s in stages:
        seen_stage_keys[s["stage"]] = seen_stage_keys.get(s["stage"], 0) + 1
        if seen_stage_keys[s["stage"]] > 1:
            s["label"] += " ·%d" % seen_stage_keys[s["stage"]]

    def stage_of(idx):
        for s in reversed(stages):
            if idx >= s["start_idx"]:
                return s
        return stages[0]

    for t in tools:
        s = stage_of(t["idx"])
        t["stage"] = s["stage"]
        t["seg"] = s["id"]
        s["tool_counts"][t["name"]] = s["tool_counts"].get(t["name"], 0) + 1
        if t["name"] in ("Write", "Edit"):
            fp = t["brief"]
            if fp and fp not in s["artifacts"]:
                s["artifacts"].append(fp)
        if t["name"] == "Skill" and t.get("skill") and norm_skill(t["skill"]) not in PIPELINE_SKILLS:
            s["helper_skills"].append({"idx": t["idx"], "ts": t["ts"], "skill": t["skill"]})

    for p in prompts:
        s = stage_of(p["idx"])
        p["stage"] = s["stage"]
        p["seg"] = s["id"]
        s["prompt_idxs"].append(p["idx"])

    for idx, usage in usage_by_idx:
        s = stage_of(idx)
        s["output_tokens"] += usage.get("output_tokens") or 0
        s["cache_read_tokens"] += usage.get("cache_read_input_tokens") or 0

    # ---- Subagents ----
    # 两种落盘位置:Task 派发 → subagents/agent-*.jsonl
    #              Workflow 派发 → subagents/workflows/<runId>/agent-*.jsonl
    meta_files = []   # (所在目录, meta 文件名)
    if os.path.isdir(subagents_dir):
        for fn in sorted(os.listdir(subagents_dir)):
            if fn.endswith(".meta.json"):
                meta_files.append((subagents_dir, fn))
        wf_sub = os.path.join(subagents_dir, "workflows")
        if os.path.isdir(wf_sub):
            for rid in sorted(os.listdir(wf_sub)):
                rdir = os.path.join(wf_sub, rid)
                if not os.path.isdir(rdir):
                    continue
                for fn in sorted(os.listdir(rdir)):
                    if fn.endswith(".meta.json"):
                        meta_files.append((rdir, fn))

    agents = []
    if meta_files:
        for adir, fn in meta_files:
            if not fn.endswith(".meta.json"):
                continue
            agent_id = fn[len("agent-"):-len(".meta.json")]
            try:
                m = json.load(open(os.path.join(adir, fn), encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            wfi = wf_byagent.get(agent_id) or {}
            entry = {
                "agent_id": agent_id,
                "type": m.get("agentType"),
                # workflow 子代理的 meta 没有 description，编排 label 才是它的身份
                "desc": (wfi.get("label") or m.get("description") or "")[:240],
                "wf_run": wfi.get("run_id"),
                "wf_name": wfi.get("wf_name"),
                "wf_phase": wfi.get("phase"),
                "tuid": m.get("toolUseId"),
                "stage": None,
                "start_ts": None,
                "end_ts": None,
                "dur_ms": None,
                "output_tokens": 0,
                "tool_uses": 0,
                "tool_counts": {},
                "status": "unknown",
                "aborted": None,  # 'interrupted' / 'api_error' / None(正常收尾)
                "model": None,
                "result": "",
                "skills": {},
                "skill_calls": [],
                "seg": None,
                "_prompt": "",   # 派发 prompt(首条 user 文本)—lineage owning-spec 兜底信号
                "_probed": [],   # 脚本(Bash/Grep)点到过的源码文件——只是探测,未必进上下文
                "_reads": [],    # Read file_path 原始路径
                "_writes": [],   # Write/Edit/MultiEdit file_path 原始路径
                "_read_lines": {},   # path -> 累计读取行数(Read 结果 numLines)
                "_read_iv": {},      # path -> [(startLine, numLines)...] 读取区间(去重并集用)
                "_read_total": {},   # path -> 文件总行数(Read 结果 totalLines, 取 max)
                "_read_sources": {}, # path -> {Read/Grep/Bash/PowerShell} 可见行来源
                "_write_lines": {},  # path -> 累计写入行数(Write content/Edit new_string)
                "_write_events": [], # (ts, path, 'set'|'delta', 行数/净差) 终态重放用
            }
            jl = os.path.join(adir, f"agent-{agent_id}.jsonl")
            if os.path.isfile(jl):
                first_ts = last_ts = None
                last_rec = None
                sub_usage = {}  # message.id -> {m:model, u:最新 usage, ch:[think,text,tool]字符}
                pending_skill = {}  # tool_use_id -> skill_calls 下标(待回填结果)
                pending_read = {}   # tool_use_id -> file_path(待从结果取 numLines)
                pending_visible = {}  # tool_use_id -> (name, input)，从最终输出还原源码行
                with open(jl, encoding="utf-8") as f:
                    for line in f:
                        try:
                            rec = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        ts = rec.get("timestamp")
                        if ts:
                            if first_ts is None:
                                first_ts = ts
                            last_ts = ts
                        # 收尾判定用:正常结束的子代理末条一定是 stop_reason=end_turn 的
                        # assistant 文本;被中断/断连的则停在 [Request interrupted] 或错误上
                        last_rec = rec
                        msg = rec.get("message")
                        if isinstance(msg, dict):
                            mm = msg.get("model")
                            if entry["model"] is None and mm and not mm.startswith("<"):
                                entry["model"] = mm
                            u = msg.get("usage")
                            if isinstance(u, dict) and not (mm or "").startswith("<"):
                                sslot = sub_usage.setdefault(
                                    msg.get("id"),
                                    {"m": msg.get("model") or "unknown", "u": u, "ch": [0, 0, 0]})
                                sslot["u"] = u
                                if rec.get("type") == "assistant":
                                    th, tx, tu = block_chars(msg)
                                    sslot["ch"][0] += th
                                    sslot["ch"][1] += tx
                                    sslot["ch"][2] += tu
                            c = msg.get("content")
                            if not entry["_prompt"] and rec.get("type") == "user":
                                pt = c if isinstance(c, str) else (
                                    " ".join(b.get("text", "") for b in c
                                             if isinstance(b, dict) and b.get("type") == "text")
                                    if isinstance(c, list) else "")
                                if pt and pt.strip():
                                    entry["_prompt"] = pt.strip()[:4000]
                            if isinstance(c, list):
                                for blk in c:
                                    if not isinstance(blk, dict):
                                        continue
                                    if blk.get("type") == "tool_use":
                                        entry["tool_uses"] += 1
                                        n = blk.get("name")
                                        entry["tool_counts"][n] = entry["tool_counts"].get(n, 0) + 1
                                        binp = blk.get("input") or {}
                                        bfp = binp.get("file_path") or binp.get("path")
                                        if n == "Read" and isinstance(bfp, str):
                                            entry["_reads"].append(bfp)
                                            pending_read[blk.get("id")] = bfp
                                        elif n in ("Grep", "Bash", "PowerShell"):
                                            pending_visible[blk.get("id")] = (n, binp)
                                            for pp in _script_probed_paths(n, binp, meta["cwd"]):
                                                entry["_probed"].append(pp)
                                        elif n in ("Write", "Edit", "MultiEdit") and isinstance(bfp, str):
                                            entry["_writes"].append(bfp)
                                            wl = 0
                                            if n == "Write":
                                                wl = (binp.get("content") or "").count("\n") + 1
                                                entry["_write_events"].append((ts, bfp, "set", wl))
                                            elif n == "Edit":
                                                wl = (binp.get("new_string") or "").count("\n") + 1
                                                ol = (binp.get("old_string") or "").count("\n") + 1
                                                entry["_write_events"].append((ts, bfp, "delta", wl - ol))
                                            else:  # MultiEdit
                                                dlt = 0
                                                for e2 in (binp.get("edits") or []):
                                                    if isinstance(e2, dict):
                                                        n2 = (e2.get("new_string") or "").count("\n") + 1
                                                        o2 = (e2.get("old_string") or "").count("\n") + 1
                                                        wl += n2
                                                        dlt += n2 - o2
                                                entry["_write_events"].append((ts, bfp, "delta", dlt))
                                            entry["_write_lines"][bfp] = entry["_write_lines"].get(bfp, 0) + wl
                                        if n == "Skill":
                                            sk = (blk.get("input") or {}).get("skill")
                                            if sk:
                                                entry["skills"][sk] = entry["skills"].get(sk, 0) + 1
                                                entry["skill_calls"].append(
                                                    {"skill": sk, "ts": ts, "ok": None, "dur_ms": None})
                                                pending_skill[blk.get("id")] = len(entry["skill_calls"]) - 1
                                    elif blk.get("type") == "tool_result" and blk.get("tool_use_id") in pending_skill:
                                        sc = entry["skill_calls"][pending_skill.pop(blk["tool_use_id"])]
                                        sc["ok"] = not blk.get("is_error", False)
                                        sc["dur_ms"] = ms_between(sc["ts"], ts)
                                    elif blk.get("type") == "tool_result" and blk.get("tool_use_id") in pending_read:
                                        rp = pending_read.pop(blk["tool_use_id"])
                                        tur = rec.get("toolUseResult")
                                        nl, st, tot = 0, 1, 0
                                        if isinstance(tur, dict):
                                            fl = tur.get("file")
                                            if isinstance(fl, dict):
                                                nl = fl.get("numLines") or 0
                                                st = fl.get("startLine") or 1
                                                tot = fl.get("totalLines") or 0
                                        spans = []
                                        if not nl and not blk.get("is_error"):
                                            # 无 toolUseResult(workflow 子代理)：从正文 `N\t` 前缀取精确区间
                                            body = result_text(blk, rec.get("toolUseResult"))
                                            spans = _spans_from_numbered_text(body)
                                            if not spans and body:  # 无行号(如图片/二进制)才退回数行
                                                nl = body.count("\n") + 1
                                        if spans and not blk.get("is_error"):
                                            entry["_read_sources"].setdefault(rp, set()).add("Read")
                                            for s0, c0 in spans:
                                                entry["_read_iv"].setdefault(rp, []).append((s0, c0))
                                                entry["_read_lines"][rp] = entry["_read_lines"].get(rp, 0) + c0
                                        elif nl and not blk.get("is_error"):
                                            entry["_read_lines"][rp] = entry["_read_lines"].get(rp, 0) + nl
                                            entry["_read_iv"].setdefault(rp, []).append((st, nl))
                                            entry["_read_sources"].setdefault(rp, set()).add("Read")
                                        if tot and not blk.get("is_error"):
                                            entry["_read_total"][rp] = max(entry["_read_total"].get(rp, 0), tot)
                                    elif blk.get("type") == "tool_result" and blk.get("tool_use_id") in pending_visible:
                                        name, vinp = pending_visible.pop(blk["tool_use_id"])
                                        if not blk.get("is_error"):
                                            visible = _infer_visible_source_lines(
                                                name, vinp, result_text(blk, rec.get("toolUseResult")),
                                                meta["cwd"],
                                            )
                                            for event in visible:
                                                rp = event["path"]
                                                entry["_reads"].append(rp)
                                                entry["_read_sources"].setdefault(rp, set()).add(name)
                                                for start, count in event["intervals"]:
                                                    entry["_read_iv"].setdefault(rp, []).append(
                                                        (start, count)
                                                    )
                                                    entry["_read_lines"][rp] = (
                                                        entry["_read_lines"].get(rp, 0) + count
                                                    )
                                                try:
                                                    with open(
                                                        rp, encoding="utf-8", errors="ignore"
                                                    ) as stream:
                                                        total = sum(1 for _ in stream)
                                                except OSError:
                                                    total = 0
                                                if total:
                                                    entry["_read_total"][rp] = max(
                                                        entry["_read_total"].get(rp, 0), total
                                                    )
                                    elif (blk.get("type") == "text" and blk.get("text", "").strip()
                                          and msg.get("role") == "assistant"):
                                        entry["result"] = blk["text"].strip()[:300]
                a_split = {"thinking": 0.0, "text": 0.0, "tool": 0.0}
                for sslot in sub_usage.values():
                    u = sslot["u"]
                    entry["output_tokens"] += u.get("output_tokens") or 0
                    bill(sslot["m"], u)
                    o = u.get("output_tokens") or 0
                    th, tx, tu = sslot["ch"]
                    tot_ch = th + tx + tu
                    if tot_ch:
                        a_split["thinking"] += o * th / tot_ch
                        a_split["text"] += o * tx / tot_ch
                        a_split["tool"] += o * tu / tot_ch
                    else:
                        a_split["text"] += o
                entry["out_split"] = {k: int(round(v)) for k, v in a_split.items()}
                entry["start_ts"] = first_ts
                entry["end_ts"] = last_ts
                entry["dur_ms"] = ms_between(first_ts, last_ts)
                entry["aborted"] = _abort_reason(last_rec)
            # Workflow 子代理没有派发 tool_use,按所属 workflow 归段——
            # 工作流在后台跑，时间窗常越过主线阶段边界，按时间兜底会归错。
            wf_key = wf_stage_of_run.get(entry.get("wf_run") or "")
            if wf_key:
                entry["stage"] = wf_key
                for s in stages:
                    if s["stage"] == wf_key:
                        entry["seg"] = s["id"]
                        break
                # workflow 子代理的 transcript 末条是 StructuredOutput 的 tool_result(user 记录),
                # 不是 assistant/end_turn——收尾启发式会把【全部】判成 interrupted,
                # 于是"白跑分身"过滤把整批真实工作剔出视野统计。编排状态才是权威。
                state = wfi.get("state")
                if state == "done":
                    entry["status"], entry["aborted"] = "completed", None
                elif state:
                    entry["status"] = state
                    entry["aborted"] = entry["aborted"] or "api_error"
            # 通过 toolUseId 回链父会话,定位阶段与最终状态
            elif entry["tuid"] in tool_by_id:
                parent = tools[tool_by_id[entry["tuid"]]]
                entry["stage"] = parent.get("stage")
                entry["seg"] = parent.get("seg")
                tur = parent.get("_tur")
                if isinstance(tur, dict) and tur.get("status"):
                    entry["status"] = tur["status"]
                elif parent.get("ok") is True:
                    entry["status"] = "completed"
            elif entry["start_ts"]:
                # 旧版 cc(如 2.1.195)异步子代理的派发 tool_use 不落盘,
                # 主会话只有完成通知——按子代理起始时间落入的阶段区间兜底归段
                for s in stages:
                    if (s["start_ts"] and s["end_ts"]
                            and s["start_ts"] <= entry["start_ts"] <= s["end_ts"]):
                        entry["stage"] = s["stage"]
                        entry["seg"] = s["id"]
                        break
            agents.append(entry)

    for a in agents:
        if a.get("seg"):
            for s in stages:
                if s["id"] == a["seg"]:
                    s["agent_count"] += 1
                    break

    # ---- 等待/活跃定稿 ----
    # 非活跃 = 会话【真正停摆】:回合已结束(stop_hook_summary/turn_duration 标记)
    # 且直到下一条 assistant/user 记录之间什么都没发生;外加 AskUserQuestion 等待窗口。
    # 回合进行中的长静默(LLM 重试、子代理卡死等)= session 没停,计入活跃。
    # 停摆区间再扣除忙碌覆盖(异步子代理仍在跑 = 没停摆)。
    busy = []
    for t in tools:
        if t.get("dur_ms") and t["name"] != "AskUserQuestion":
            a0 = parse_ts(t["ts"])
            if a0:
                busy.append([a0, a0 + timedelta(milliseconds=t["dur_ms"])])
    for ag in agents:
        a0, b0 = parse_ts(ag.get("start_ts")), parse_ts(ag.get("end_ts"))
        if a0 and b0 and b0 > a0:
            busy.append([a0, b0])
    busy.sort(key=lambda x: x[0])
    merged_busy = []
    for a0, b0 in busy:
        if merged_busy and a0 <= merged_busy[-1][1]:
            if b0 > merged_busy[-1][1]:
                merged_busy[-1][1] = b0
        else:
            merged_busy.append([a0, b0])

    def subtract_busy(p0, p1):
        pieces, cur = [], p0
        for a0, b0 in merged_busy:
            if b0 <= cur or a0 >= p1:
                continue
            if a0 > cur:
                pieces.append((cur, min(a0, p1)))
            cur = max(cur, b0)
        if cur < p1:
            pieces.append((cur, p1))
        return pieces

    # 回合关闭区间:关闭标记 -> 下一条 assistant/user 记录
    stalls = []  # (t0s, t1s, kind, term_idx)  kind: user=以用户动作恢复 / auto / tail
    close_t = None
    for i, rec in enumerate(records):
        ts = rec.get("timestamp")
        if not ts:
            continue
        rt = rec.get("type")
        if rt == "system" and rec.get("subtype") in ("stop_hook_summary", "turn_duration"):
            if close_t is None:
                close_t = ts
        elif rt in ("assistant", "user"):
            if close_t is not None:
                content = (rec.get("message") or {}).get("content")
                is_user_act = (rt == "user" and isinstance(content, str)
                               and not content.lstrip().startswith("<task-notification>"))
                stalls.append((close_t, ts, "user" if is_user_act else "auto", i))
                close_t = None
    if close_t is not None and meta["ended_at"]:
        stalls.append((close_t, meta["ended_at"], "tail", None))
    for t in tools:  # AskUserQuestion = 明确停下等用户点选
        if t["name"] == "AskUserQuestion" and t.get("dur_ms"):
            a0 = parse_ts(t["ts"])
            if a0:
                stalls.append((t["ts"], (a0 + timedelta(milliseconds=t["dur_ms"])).isoformat(),
                               "user", None))

    pieces = []  # (t0, t1, kind, term_idx) 停摆净区间
    for t0s, t1s, kind, tidx in stalls:
        p0, p1 = parse_ts(t0s), parse_ts(t1s)
        if p0 and p1 and p1 > p0:
            for q0, q1 in subtract_busy(p0, p1):
                pieces.append((q0, q1, kind, tidx))

    def overlap_ms(q0, q1, p0, p1):
        lo = q0 if q0 > p0 else p0
        hi = q1 if q1 < p1 else p1
        return max(0.0, (hi - lo).total_seconds() * 1000)

    by_idx = {p["idx"]: p for p in prompts}
    for q0, q1, kind, tidx in pieces:
        if tidx in by_idx:  # 该停摆以这条键入收尾 -> 记为该 prompt 的等待
            by_idx[tidx]["wait_ms"] += int((q1 - q0).total_seconds() * 1000)
    for s in stages:
        if s["duration_ms"] is None:
            continue
        p0, p1 = parse_ts(s["start_ts"]), parse_ts(s["end_ts"])
        stall = wait_u = 0.0
        if p0 and p1:
            for q0, q1, kind, _ in pieces:
                ov = overlap_ms(q0, q1, p0, p1)
                stall += ov
                if kind == "user":
                    wait_u += ov
        stall = min(int(stall), s["duration_ms"])
        s["active_ms"] = s["duration_ms"] - stall
        # 等待用户 = 以用户动作恢复的停摆;其余(tail/auto)= 挂起,前端以差值呈现
        s["wait_ms"] = min(int(wait_u), stall)

    # 清理内部字段
    for t in tools:
        t.pop("_tur", None)
        t.pop("_result_rec", None)

    total_out = sum(s["output_tokens"] for s in stages)
    dur_total = ms_between(meta["started_at"], meta["ended_at"])
    active_total = wait_total = None
    if dur_total is not None:
        w0, w1 = parse_ts(meta["started_at"]), parse_ts(meta["ended_at"])
        stall_t = wait_t = 0.0
        for q0, q1, kind, _ in pieces:
            ov = overlap_ms(q0, q1, w0, w1)
            stall_t += ov
            if kind == "user":
                wait_t += ov
        stall_t = min(int(stall_t), dur_total)
        active_total = dur_total - stall_t
        wait_total = min(int(wait_t), stall_t)
    # output 构成 = 主线 + 全部子代理(思考 / 正文 / 工具参数三分,字符占比摊 token)
    g_split = dict(main_split)
    for a in agents:
        for k, v in (a.get("out_split") or {}).items():
            g_split[k] += v
    totals = {
        "duration_ms": dur_total,
        "user_wait_ms": wait_total,
        "active_ms": active_total,
        "tool_calls": len(tools),
        "agent_calls": sum(1 for t in tools if t["name"] in ("Agent", "Task")),
        "subagent_transcripts": len(agents),
        "main_output_tokens": total_out,
        "subagent_output_tokens": sum(a["output_tokens"] for a in agents),
        # 白烧 = 异常收尾(中断/断连)agent 烧掉的 output——产物多半作废、还要补跑
        "aborted_agents": sum(1 for a in agents if a.get("aborted")),
        "waste_output_tokens": sum(a["output_tokens"] for a in agents if a.get("aborted")),
        "output_split": {k: int(round(v)) for k, v in g_split.items()},
        "user_prompts": len(prompts),
        "files_touched": len({t["brief"] for t in tools if t["name"] in ("Write", "Edit")}),
        "compactions": len(markers),
    }

    # ---- 数据血缘: spec ↔ agent ↔ 鸿蒙文件(在剥离临时字段之前构建)----
    lineage = build_lineage(agents, tools, meta["cwd"])
    for a in agents:  # 剥离仅供 lineage 的临时字段
        a.pop("_prompt", None)
        a.pop("_reads", None)
        a.pop("_writes", None)
        a.pop("_read_lines", None)
        a.pop("_write_lines", None)
        a.pop("_read_iv", None)
        a.pop("_read_total", None)
        a.pop("_read_sources", None)
        a.pop("_write_events", None)
    for tool in tools:
        tool.pop("_inp", None)
        tool.pop("_visible_source_lines", None)
        tool.pop("_probed_paths", None)

    return {"meta": meta, "totals": totals, "stages": stages,
            "tools": tools, "agents": agents, "prompts": prompts, "markers": markers,
            "context_timeline": context_timeline, "billing": billing, "lineage": lineage,
            "workflows": [wf_runs[k] for k in sorted(wf_runs)]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("jsonl")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    data = extract(args.jsonl)
    out = args.out or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   f"trace-{data['meta']['session_id'][:8]}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

    m, t = data["meta"], data["totals"]
    print(f"session   {m['session_id']}  (cc {m['cc_version']}, {m['model']})")
    print(f"time      {m['started_at']} -> {m['ended_at']}  ({(t['duration_ms'] or 0)/3600000:.1f} h)")
    print(f"records   {m['record_count']}  tool_calls {t['tool_calls']}  subagents {t['subagent_transcripts']}")
    print(f"tokens    main-out {t['main_output_tokens']:,}  sub-out {t['subagent_output_tokens']:,}")
    print(f"stages:")
    for s in data["stages"]:
        n_tools = sum(s["tool_counts"].values())
        print(f"  {s['label']:<22} idx {s['start_idx']:>4}-{s['end_idx']:<4} "
              f"{(s['duration_ms'] or 0)/60000:>6.0f} min  tools {n_tools:>3}  "
              f"agents {s['agent_count']:>2}  out-tok {s['output_tokens']:>7,}")
    print(f"\nwritten -> {out}")


if __name__ == "__main__":
    main()
