"""Compact audit observations from actual calls, before UI summaries truncate them.

This is an observation vocabulary, not a general shell interpreter. Unknown
wrappers remain unknown; echoes, log reads and dependency installs are not builds.
"""
import hashlib
import json
import re
import shlex


SHELLS = {"bash", "powershell", "exec", "exec_command", "shell", "shell_command"}


def phase(name):
    name = str(name or "").lower().split(":")[-1]
    if name.endswith("-zh"):
        name = name[:-3]
    aliases = {"a2h-spec": "spec", "a2h-plan": "plan", "a2h-execute": "execute",
               "a2h-build": "build", "a2h-verify": "verify", "arkts-visual-verify": "verify",
               "a2h-retrospect": "retrospect", "ecat-refine": "verify"}
    return aliases.get(name)


def segments(command):
    lexer = shlex.shlex(command, posix=False, punctuation_chars=";&|\n")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    lexer.commenters = "#"
    current = []
    try:
        for token in lexer:
            if token and all(c in ";&|\n" for c in token):
                if current:
                    yield current
                current = []
            else:
                current.append(token.strip("\"'"))
        if current:
            yield current
    except ValueError:
        return  # Unbalanced/opaque command: do not infer an action.


def capabilities(name, inp):
    key = str(name or "").lower().split("__")[-1]
    direct = {"build_project": {"build"}, "start_app": {"device"}, "startapp": {"device"},
              "hdc_log": {"device"}, "hdclog": {"device"}, "install_hap": {"device", "install"},
              "take_screenshot": {"device", "screenshot"}}
    if key in direct:
        return sorted(direct[key])
    if key not in SHELLS or not isinstance(inp, dict):
        return []
    command = inp.get("command", inp.get("cmd", ""))
    if not isinstance(command, str):
        return []
    low = command.lower()
    # 下面认的可执行名(hvigor* / hdc / adb / bm)一个都不出现,分词也认不出能力 —— 省掉 shlex
    if not any(word in low for word in ("hvigor", "hdc", "adb", "bm")):
        return []
    found = set()
    for tokens in segments(command):
        if not tokens:
            continue
        words = [t.lower() for t in tokens]
        exe = words[0].replace("\\", "/").rsplit("/", 1)[-1]
        if exe in ("node", "node.exe") and len(words) > 1:
            exe = words[1].replace("\\", "/").rsplit("/", 1)[-1]
        if any(w in ("--help", "-h", "--version") for w in words):
            continue
        if exe in ("hvigor", "hvigorw", "hvigorw.bat", "hvigorw.js"):
            if any(w in ("assemblehap", "assembleapp") for w in words):
                found.add("build")
            if any(w in ("install-hap", "installhap") for w in words):
                found.add("install")
        # 设备工具常放进 shell 变量调:`HDC=…/hdc; "$HDC" install …`、`"$BM" install -p …`
        # (hmigbot-plus 9bf4d4be、c70d9154)。引号在分词时已剥掉,$X / ${X} 两种写法同款。
        if exe in ("hdc", "hdc.exe", "$hdc", "${hdc}", "adb", "adb.exe"):
            found.add("device")
            if "install" in words or "install-multiple" in words:
                found.add("install")
            if any(w in ("screencap", "snapshot_display", "screenshot") for w in words):
                found.add("screenshot")
        if exe in ("bm", "bm.exe", "$bm", "${bm}") and "install" in words:
            found.add("install")
    return sorted(found)


def text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(str(v.get("text", "")) for v in value if isinstance(v, dict))
    return ""


def receipt(output=None, ok=None):
    """回执只决定 outcome 与 build_success(输入哈希、能力在调用时就定了,不必重算)。"""
    body = text(output)
    # Shell transport success is weaker than subcommand success, but an explicit
    # failing exit receipt must never erase a failed-attempt observation.
    if re.search(r"(?:exit code[: =]+|process exited with code\s+)[1-9]\d*\b|BUILD FAILED", body, re.I):
        ok = False
    return {"outcome": "failed" if ok is False else ("returned" if ok is True else "unknown"),
            "build_success": bool(re.search(r"\bBUILD SUCCESSFUL\b", body)) and ok is not False}


def observation(name, inp, output=None, ok=None, *, call=None, idx=None, ts=None):
    inp = inp if isinstance(inp, dict) else {}
    return {"call": call, "idx": idx, "ts": ts, "name": name,
            "kind": "skill" if str(name).lower() == "skill" else ("shell" if str(name).lower() in SHELLS else "tool"),
            "target": str(inp.get("skill") or inp.get("name") or "") if str(name).lower() == "skill" else "",
            "input_hash": hashlib.sha256(json.dumps(inp, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
            "capabilities": capabilities(name, inp),
            **receipt(output, ok)}


class ClaudeCalls:
    """One pass alongside the existing Claude parser; retain no command bodies."""
    def __init__(self, source):
        self.source, self.calls, self.inputs = source, {}, {}

    def observe(self, record, idx):
        blocks = (record.get("message") or {}).get("content")
        # 调用只认 assistant 行、回执只认 user 行,同一 id 只收一次(请求体快照等副本不算)。
        # 没有 type 的手造记录(单测、旧导出)照旧按块读
        rtype = record.get("type")
        if not isinstance(blocks, list) or rtype not in ("assistant", "user", None):
            return
        for b in blocks:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use" and rtype in ("assistant", None):
                cid = b.get("id")
                if cid is not None and cid in self.calls:
                    continue
                self.inputs[cid] = b.get("input")
                self.calls[cid] = observation(b.get("name"), b.get("input"), call=cid, idx=idx, ts=record.get("timestamp"))
                self.calls[cid]["line"] = record.get("_source_line", idx + 1)
            elif b.get("type") == "tool_result" and rtype in ("user", None) and b.get("tool_use_id") in self.calls:
                cid = b["tool_use_id"]
                self.inputs.pop(cid, None)
                self.calls[cid] = {**self.calls[cid], **receipt(b.get("content"), not b.get("is_error", False))}

    def finish(self):
        return [{**v, "source": self.source} for v in self.calls.values()]


def scoped(rows, owner, stage=None, segment=None):
    return [{**r, "owner": owner, "stage": r.get("stage") or stage,
             "segment": r.get("segment") or segment} for r in rows]


def collect(trace):
    meta = trace.get("meta") or {}
    sid = meta.get("session_id") or meta.get("source_file") or "unknown"
    observations = scoped(trace.get("audit_tools", []), sid)
    for agent in trace.get("agents", []):
        if not agent.get("snapshot_of_main"):
            observations.extend(scoped(agent.get("audit_tools", []), agent.get("agent_id"), agent.get("stage"), agent.get("seg")))
    return observations
