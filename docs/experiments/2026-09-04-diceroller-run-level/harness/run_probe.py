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


def load_chains(sid: str) -> dict:
    return json.load(open(os.path.join(EXP, f"chains-{sid}.json"), encoding="utf-8"))


TEMPLATE = "prompt_template.md"
RAW_DIR = ""          # 对照组:原始转录目录(给了就不接 MCP,cwd 切到这里)
HYBRID = False        # 超集组:RAW_DIR + MCP 都给
FIX_AFTER = "2026-09-03T16:46:29Z"   # run 级模式:execute 结束时刻(stage-marks)
MAX_CALLS = 120       # run 级:8 个段 × 每段 ~10 次 + 铺开与归并;两组同一上限
N_SESSIONS = 17


SKILL_PATH = ("C:/Users/hongy/projects/migbot-elite/.claude/worktrees/filestory/docs/insight/skills/"
              "migloop-investigate/SKILL.md")


def _skill_body() -> str:
    """技能正文(去掉 frontmatter):工具组的 prompt = 任务一句话 + 技能 + 两组共用的口径。"""
    text = open(SKILL_PATH, encoding="utf-8").read()
    if text.startswith("---"):
        text = text.split("---", 2)[2]
    return text.strip()


def build_prompt(sid: str, c: dict) -> str:
    t = open(os.path.join(EXP, TEMPLATE), encoding="utf-8").read()
    if "{skill}" in t:
        t = t.replace("{skill}", _skill_body())
    if "{common}" in t:       # run 级模板:两组共用的口径 / 纪律 / 输出段从 prompt_run_common.md 拼进来
        t = t.replace("{common}", open(os.path.join(EXP, "prompt_run_common.md"), encoding="utf-8").read())
    fv = c.get("fix_versions") or []
    fill = {
        "{sid}": sid, "{file}": str(c.get("file")),
        "{fix_desc}": str(c.get("fix_desc") or ""), "{fix_id}": str(c.get("fix_id") or ""),
        "{fix_versions}": "/".join(str(v) for v in fv) if isinstance(fv, list) else str(fv),
        "{gen_desc}": str(c.get("gen_desc") or ""), "{gen_id}": str(c.get("gen_id") or ""),
        "{fix_after}": FIX_AFTER, "{max_calls}": str(MAX_CALLS), "{n_sessions}": str(N_SESSIONS),
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
                 ("guide", "sessions", "index", "file", "agent", "blame", "diff", "action")]
    if RAW_DIR and HYBRID:
        # 超集组:migloop 工具 + Read/Grep/Glob/Bash,cwd 在原始转录目录
        cmd = [CLAUDE, "-p", "--model", model, "--mcp-config", os.path.join(EXP, "mcp-migloop.json"),
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
        cmd = [CLAUDE, "-p", "--model", model, "--mcp-config", os.path.join(EXP, "mcp-migloop.json"),
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
    metrics: dict = {
        "label": label, "chain": int(c["i"]), "file": c.get("file"), "rep": rep, "model": model,
        "session_id": res.get("session_id"), "is_error": bool(res.get("is_error")),
        "num_turns": res.get("num_turns"), "duration_ms": res.get("duration_ms"),
        "duration_api_ms": res.get("duration_api_ms"), "wall_s": round(wall, 1),
        "cost_usd": res.get("total_cost_usd"), "usage": res.get("usage"),
        "result_chars": len(str(res.get("result") or "")),
        "verdict": verdict_of(str(res.get("result") or "")),
        "at": dt.datetime.now().isoformat(timespec="seconds"),
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
            "error": metrics["is_error"], "dir": os.path.relpath(run_dir, EXP)}
    with open(os.path.join(EXP, "runs", "summary.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(line, ensure_ascii=False) + "\n")
    print(json.dumps(line, ensure_ascii=False), flush=True)
    return metrics


def main() -> None:
    global TEMPLATE, RAW_DIR, HYBRID, FIX_AFTER, MAX_CALLS, N_SESSIONS
    ap = argparse.ArgumentParser()
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
    args = ap.parse_args()
    TEMPLATE = args.template
    RAW_DIR = args.raw_dir
    HYBRID = args.hybrid
    FIX_AFTER, MAX_CALLS, N_SESSIONS = args.fix_after, args.max_calls, args.n_sessions
    if args.run_level:
        targets = [{"i": 0, "file": "RUN"}]
    else:
        data = load_chains(args.sid)
        by_i = {int(c["i"]): c for c in data["chains"]}
        by_name = {str(c["file"]).rsplit("/", 1)[-1]: c for c in data["chains"]}
        targets = [by_i[int(tok)] if tok.isdigit() else by_name[tok]      # 下标或文件名(链表重算后下标会变)
                   for tok in [x.strip() for x in args.chains.split(",") if x.strip()]]
    if args.dry_run:
        for c in targets:
            print(build_prompt(args.sid, c))
        return
    for c in targets:
        for rep in range(1, args.reps + 1):
            run_one(args.sid, c, args.label, rep, args.model, args.max_turns)


if __name__ == "__main__":
    sys.exit(main())
