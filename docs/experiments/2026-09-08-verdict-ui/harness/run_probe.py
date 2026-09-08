"""调查 agent 对照实验 harness:一条链一次 `claude -p`(Opus 5 + migloop MCP),记录 token / 工具调用 / 结论。

用法:
    python run_probe.py --sid 9b3105a2 --chains 0,3,7 --label baseline [--reps 1] [--max-turns 40] [--model opus]

每次运行落在 runs/<label>/chain<NN>-<file>/rep<k>/:prompt.md、result.json(claude -p 的 JSON)、
transcript.jsonl(调查 agent 自己的会话记录,拷一份)、metrics.json;并向 runs/summary.jsonl 追加一行。
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time

EXP = os.path.dirname(os.path.abspath(__file__))
CLAUDE = shutil.which("claude") or "claude"
MIGLOOP_SRC = "C:/Users/hongy/projects/migloop/src"
if MIGLOOP_SRC not in sys.path:
    sys.path.insert(0, MIGLOOP_SRC)
NO_REPAIR = False       # --no-repair:结论块坏了也不做 schema 修复重试
_IDENTITY: dict[str, str] = {}


def ledger_identity_of(sid: str) -> str | None:
    """harness 自己算账本身份(工具代码版本 + 数据池清单摘要),不让模型猜;同一 sid 只建一次账。"""
    if sid in _IDENTITY:
        return _IDENTITY[sid]
    try:
        from migloop import atoms, service
        ident = atoms.ledger_identity(service.session_ledger(service.locate_session(sid)))
    except Exception as e:  # noqa: BLE001 — 身份算不出来只记 None,不拦实验
        print(f"  ledger identity unavailable: {e}", flush=True)
        ident = None
    _IDENTITY[sid] = ident
    return ident


def collect_verdict(sid: str, res: dict, run_dir: str, model: str, cmd_base: list[str], work_cwd: str) -> dict:
    """报告末尾的结构化结论块 → verdict.json。抽不到 / 校验失败且允许时做一次修复重试(--resume 同一会话,
    只让它重发结论块),两次结果与新增费用都留下;不在服务端补证据、猜节点。"""
    from migloop import verdict as _verdict
    text0 = str(res.get("result") or "")
    lb = _verdict.load_block(text0)
    vj: dict = {"attempts": [{"found": lb["found"], "kind": lb["kind"], "raw": lb["raw"], "errors": lb["errors"]}],
                "repaired": False, "repair": None}
    final = lb
    if (not lb["found"] or lb["errors"]) and not NO_REPAIR and res.get("session_id") and not RAW_DIR:
        prompt = _verdict.repair_prompt(lb)
        open(os.path.join(run_dir, "repair_prompt.md"), "w", encoding="utf-8").write(prompt)
        cmd = [CLAUDE, "-p", "--resume", str(res["session_id"]), "--model", model, *cmd_base,
               "--max-turns", "3", "--output-format", "json"]
        t0 = time.time()
        proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8",
                              cwd=work_cwd, timeout=1800)
        try:
            res2 = json.loads(proc.stdout)
        except json.JSONDecodeError:
            res2 = {"is_error": True, "result": proc.stdout[-2000:], "rc": proc.returncode, "stderr": (proc.stderr or "")[-2000:]}
        json.dump(res2, open(os.path.join(run_dir, "result_repair.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        lb2 = _verdict.load_block(str(res2.get("result") or ""))
        vj["attempts"].append({"found": lb2["found"], "kind": lb2["kind"], "raw": lb2["raw"], "errors": lb2["errors"]})
        vj["repaired"] = True
        vj["repair"] = {"cost_usd": res2.get("total_cost_usd"), "num_turns": res2.get("num_turns"),
                        "wall_s": round(time.time() - t0, 1), "is_error": bool(res2.get("is_error"))}
        if lb2["found"] and (not lb2["errors"] or not lb["found"]):
            final = lb2
    vj.update({"found": final["found"], "kind": final["kind"], "raw": final["raw"], "data": final["data"],
               "errors": final["errors"], "harness_identity": ledger_identity_of(sid),
               "schema": "migloop-verdict/1"})
    json.dump(vj, open(os.path.join(run_dir, "verdict.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return vj


def load_chains(sid: str) -> dict:
    return json.load(open(os.path.join(EXP, f"chains-{sid}.json"), encoding="utf-8"))


TEMPLATE = "prompt_template.md"
RAW_DIR = ""          # 对照组:原始转录目录(给了就不接 MCP,cwd 切到这里)
HYBRID = False        # 超集组:RAW_DIR + MCP 都给
FIX_AFTER = "2026-09-03T16:46:29Z"   # run 级模式:execute 结束时刻(stage-marks)
MAX_CALLS = 120       # run 级:8 个段 × 每段 ~10 次 + 铺开与归并;两组同一上限
N_SESSIONS = 17
MCP_CONFIG = "mcp-migloop.json"      # --mcp-config 可换成 legacy 分支的配置
TASK_FILE = ""        # 模板里 {task} 的来源(exp/ 下的文件名)


SKILL_PATH = ("C:/Users/hongy/projects/migbot-elite/.claude/worktrees/filestory/docs/insight/skills/"
              "migloop-investigate/SKILL.md")


def _skill_body() -> str:
    """技能正文(去掉 frontmatter):工具组的 prompt = 任务一句话 + 技能 + 两组共用的口径。"""
    text = open(SKILL_PATH, encoding="utf-8").read()
    if text.startswith("---"):
        text = text.split("---", 2)[2]
    return text.strip()


def _fix_transcript(fix_id: str) -> str:
    """原始组要的是转录位置,不是账本 id:子代理 = <会话>/subagents/<id>.jsonl,主会话 = <sid8>-*.jsonl。"""
    if fix_id.startswith("__main__:"):
        return f"主会话 {fix_id.split(':', 1)[1]}-*.jsonl 自己"
    return f"某个主会话目录下的 subagents/{fix_id}.jsonl"


def build_prompt(sid: str, c: dict) -> str:
    t = open(os.path.join(EXP, TEMPLATE), encoding="utf-8").read()
    if "{skill}" in t:
        t = t.replace("{skill}", _skill_body())
    if "{common}" in t:       # run 级模板:两组共用的口径 / 纪律 / 输出段从 prompt_run_common.md 拼进来
        t = t.replace("{common}", open(os.path.join(EXP, "prompt_run_common.md"), encoding="utf-8").read())
    if "{task}" in t and TASK_FILE:   # 任务段单独一个文件,两组一字不差
        t = t.replace("{task}", open(os.path.join(EXP, TASK_FILE), encoding="utf-8").read().strip())
    fv = c.get("fix_versions") or []
    fill = {
        "{sid}": sid, "{file}": str(c.get("file")),
        "{fix_desc}": str(c.get("fix_desc") or ""), "{fix_id}": str(c.get("fix_id") or ""),
        "{fix_versions}": "/".join(str(v) for v in fv) if isinstance(fv, list) else str(fv),
        "{gen_desc}": str(c.get("gen_desc") or ""), "{gen_id}": str(c.get("gen_id") or ""),
        "{fix_after}": FIX_AFTER, "{max_calls}": str(MAX_CALLS), "{n_sessions}": str(N_SESSIONS),
        "{fix_at}": str(c.get("fix_at") or ""), "{kind}": str(c.get("kind") or "rework"),
        "{fix_transcript}": _fix_transcript(str(c.get("fix_id") or "")),
    }
    for k, v in fill.items():
        t = t.replace(k, v)
    return t


def _text_len(content) -> int:
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        return sum(len(str(b.get("text") or "")) if isinstance(b, dict) else len(str(b)) for b in content)
    return len(str(content or ""))


def parse_transcript(path: str) -> dict:
    usage = {"input": 0, "cache_create": 0, "cache_read": 0, "output": 0}
    turns: list[dict] = []
    calls: dict[str, dict] = {}
    seq: list[dict] = []
    seen_msg: set[str] = set()
    with open(path, encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            m = r.get("message") if isinstance(r.get("message"), dict) else {}
            if r.get("type") == "assistant":
                u = m.get("usage") or {}
                mid = str(m.get("id") or r.get("uuid"))
                if mid not in seen_msg and u:          # 同一消息分多条记录落盘时只记一次
                    seen_msg.add(mid)
                    t = {"input": int(u.get("input_tokens") or 0),
                         "cache_create": int(u.get("cache_creation_input_tokens") or 0),
                         "cache_read": int(u.get("cache_read_input_tokens") or 0),
                         "output": int(u.get("output_tokens") or 0)}
                    turns.append(t)
                    for k in usage:
                        usage[k] += t[k]
                for b in m.get("content") or []:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        name = str(b.get("name") or "")
                        short = name.replace("mcp__migloop__", "")
                        inp = b.get("input") or {}
                        brief = {k: v for k, v in inp.items() if k != "sid"}
                        rec = {"tool": short, "input": brief, "chars": 0, "ts": r.get("timestamp")}
                        calls[str(b.get("id"))] = rec
                        seq.append(rec)
            elif r.get("type") == "user":
                for b in m.get("content") or []:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        rec = calls.get(str(b.get("tool_use_id")))
                        if rec is not None:
                            rec["chars"] = _text_len(b.get("content"))
                            rec["is_error"] = bool(b.get("is_error"))
    per_tool: dict[str, dict] = {}
    for rec in seq:
        p = per_tool.setdefault(rec["tool"], {"n": 0, "chars": 0})
        p["n"] += 1
        p["chars"] += rec["chars"]
    return {"usage": usage, "turns": len(turns), "tool_calls": len(seq), "per_tool": per_tool,
            "tool_chars": sum(r["chars"] for r in seq), "seq": seq}


def find_transcript(session_id: str, tries: int = 10) -> str | None:
    pat = os.path.join(os.path.expanduser("~"), ".claude", "projects", "*", f"{session_id}.jsonl")
    for _ in range(tries):
        hits = glob.glob(pat)
        if hits:
            return hits[0]
        time.sleep(1)
    return None


def verdict_of(text: str) -> str:
    m = re.search(r"定性[::]\s*(.+)", text or "")
    return m.group(1).strip() if m else ""


def run_one(sid: str, c: dict, label: str, rep: int, model: str, max_turns: int) -> dict:
    fname = re.sub(r"[^A-Za-z0-9_.-]", "_", str(c.get("file")).rsplit("/", 1)[-1])[:40]
    run_dir = os.path.join(EXP, "runs", label, f"chain{int(c['i']):02d}-{fname}", f"rep{rep}")
    os.makedirs(run_dir, exist_ok=True)
    prompt = build_prompt(sid, c)
    open(os.path.join(run_dir, "prompt.md"), "w", encoding="utf-8").write(prompt)
    mcp_tools = [f"mcp__migloop__{t}" for t in
                 ("guide", "sessions", "index", "file", "agent", "search", "blame", "diff", "action")]
    if RAW_DIR and HYBRID:
        # 超集组:migloop 工具 + Read/Grep/Glob/Bash,cwd 在原始转录目录
        cmd = [CLAUDE, "-p", "--model", model, "--mcp-config", os.path.join(EXP, MCP_CONFIG),
               "--allowedTools", *mcp_tools, "Read", "Grep", "Glob", "Bash",
               "--max-turns", str(max_turns), "--output-format", "json"]
        work_cwd = RAW_DIR
    elif RAW_DIR:
        # 对照组:没有 migloop 工具,只给 Read/Grep/Glob/Bash 在原始转录目录里自己找
        tools = ["Read", "Grep", "Glob", "Bash"]
        cmd = [CLAUDE, "-p", "--model", model, "--allowedTools", *tools,
               "--max-turns", str(max_turns), "--output-format", "json"]
        work_cwd = RAW_DIR
    else:
        cmd = [CLAUDE, "-p", "--model", model, "--mcp-config", os.path.join(EXP, MCP_CONFIG),
               "--allowedTools", *mcp_tools, "--max-turns", str(max_turns), "--output-format", "json"]
        work_cwd = run_dir
    t0 = time.time()
    attempts = 0
    while True:
        attempts += 1
        proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8",
                              cwd=work_cwd, timeout=3600)
        open(os.path.join(run_dir, "stderr.txt"), "w", encoding="utf-8").write(proc.stderr or "")
        try:
            res = json.loads(proc.stdout)
        except json.JSONDecodeError:
            open(os.path.join(run_dir, "stdout.txt"), "w", encoding="utf-8").write(proc.stdout or "")
            res = {"is_error": True, "result": proc.stdout[-2000:], "rc": proc.returncode}
        # Anthropic 侧 500 / 529(过载)是首轮就死的瞬时错,不算实验结果,等一会重来
        transient = res.get("is_error") and ("API Error" in str(res.get("result") or "")
                                             or res.get("terminal_reason") == "api_error")
        if not transient or attempts >= 4:
            break
        print(f"  transient api error on attempt {attempts}, retrying in 90s", flush=True)
        time.sleep(90)
    wall = time.time() - t0
    res["attempts"] = attempts
    json.dump(res, open(os.path.join(run_dir, "result.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    base_flags = cmd[cmd.index("--model") + 2:cmd.index("--max-turns")]
    vj = collect_verdict(sid, res, run_dir, model, base_flags, work_cwd)
    metrics: dict = {
        "label": label, "chain": int(c["i"]), "file": c.get("file"), "rep": rep, "model": model,
        "session_id": res.get("session_id"), "is_error": bool(res.get("is_error")),
        "num_turns": res.get("num_turns"), "duration_ms": res.get("duration_ms"),
        "duration_api_ms": res.get("duration_api_ms"), "wall_s": round(wall, 1),
        "cost_usd": res.get("total_cost_usd"), "usage": res.get("usage"),
        "result_chars": len(str(res.get("result") or "")),
        "verdict": verdict_of(str(res.get("result") or "")),
        "at": dt.datetime.now().isoformat(timespec="seconds"),
        "verdict_ok": bool(vj.get("data")), "verdict_errors": vj.get("errors"), "repair": vj.get("repair"),
        "cost_usd_total": (res.get("total_cost_usd") or 0) + ((vj.get("repair") or {}).get("cost_usd") or 0),
        "harness_identity": vj.get("harness_identity"),
    }
    tp = find_transcript(str(res.get("session_id") or "")) if res.get("session_id") else None
    if tp:
        shutil.copyfile(tp, os.path.join(run_dir, "transcript.jsonl"))
        metrics["transcript"] = parse_transcript(tp)
    json.dump(metrics, open(os.path.join(run_dir, "metrics.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    tr = metrics.get("transcript") or {}
    u = tr.get("usage") or {}
    line = {"label": label, "chain": metrics["chain"], "file": str(c.get("file")).rsplit("/", 1)[-1],
            "rep": rep, "turns": metrics["num_turns"], "calls": tr.get("tool_calls"),
            "tool_chars": tr.get("tool_chars"), "in": u.get("input"), "cache_read": u.get("cache_read"),
            "cache_create": u.get("cache_create"), "out": u.get("output"),
            "cost": metrics["cost_usd"], "wall_s": metrics["wall_s"], "verdict": metrics["verdict"],
            "error": metrics["is_error"], "dir": os.path.relpath(run_dir, EXP),
            "verdict_ok": metrics["verdict_ok"], "repair_cost": ((vj.get("repair") or {}).get("cost_usd"))}
    with open(os.path.join(EXP, "runs", "summary.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(line, ensure_ascii=False) + "\n")
    print(json.dumps(line, ensure_ascii=False), flush=True)
    return metrics


def main() -> None:
    global TEMPLATE, RAW_DIR, HYBRID, FIX_AFTER, MAX_CALLS, N_SESSIONS, MCP_CONFIG, TASK_FILE, NO_REPAIR
    ap = argparse.ArgumentParser()
    ap.add_argument("--task-file", default="", help="模板 {task} 段的文件名(exp/ 下)")
    ap.add_argument("--sid", default="9b3105a2")
    ap.add_argument("--chains", default="", help="链下标或文件名,逗号分隔(见 chains-<sid>.json);run 级模式不用")
    ap.add_argument("--label", required=True)
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--max-turns", type=int, default=40)
    ap.add_argument("--model", default="opus")
    ap.add_argument("--template", default="prompt_template.md", help="提示词模板文件名(变体用)")
    ap.add_argument("--raw-dir", default="", help="对照组:原始转录目录,不接 MCP 只给 Read/Grep/Glob/Bash")
    ap.add_argument("--hybrid", action="store_true", help="超集组:--raw-dir 之上再接 MCP 工具")
    ap.add_argument("--run-level", action="store_true",
                    help="整个 run 一次调查(全部修复段),不给链坐标;结果落在 chain00-RUN/")
    ap.add_argument("--fix-after", default=FIX_AFTER)
    ap.add_argument("--max-calls", type=int, default=MAX_CALLS)
    ap.add_argument("--n-sessions", type=int, default=N_SESSIONS)
    ap.add_argument("--dry-run", action="store_true", help="只打印拼好的 prompt,不跑模型")
    ap.add_argument("--mcp-config", default=MCP_CONFIG, help="MCP 配置文件名(exp/ 下),legacy 用 mcp-legacy.json")
    ap.add_argument("--no-repair", action="store_true", help="结论块坏了也不做 schema 修复重试")
    args = ap.parse_args()
    TEMPLATE = args.template
    MCP_CONFIG = args.mcp_config
    TASK_FILE = args.task_file
    NO_REPAIR = args.no_repair
    RAW_DIR = args.raw_dir
    HYBRID = args.hybrid
    FIX_AFTER, MAX_CALLS, N_SESSIONS = args.fix_after, args.max_calls, args.n_sessions
    if args.run_level:
        targets = [{"i": 0, "file": "RUN"}]
    else:
        data = load_chains(args.sid)
        by_i = {int(c["i"]): c for c in data["chains"]}
        by_name = {str(c["file"]).rsplit("/", 1)[-1]: c for c in data["chains"]}
        targets = []
        for k, tok in enumerate([x.strip() for x in args.chains.split(",") if x.strip()]):
            if tok.isdigit():
                targets.append(by_i[int(tok)])
            elif tok in by_name:                                          # 文件名(链表重算后下标会变)
                targets.append(by_name[tok])
            else:                                                         # 不是链根的文件(如生成期反复改写、修复期没动的)
                targets.append({"i": 90 + k, "file": tok})
    if args.dry_run:
        for c in targets:
            print(build_prompt(args.sid, c))
        return
    for c in targets:
        for rep in range(1, args.reps + 1):
            run_one(args.sid, c, args.label, rep, args.model, args.max_turns)


if __name__ == "__main__":
    sys.exit(main())
