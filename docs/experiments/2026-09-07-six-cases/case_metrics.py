"""按四个口径挑案例:最多跳 / 生成→修复耗时最长 / 生成期改动最多 / 修复期改动最多,外加每根的 token 估算。
用法: python case_metrics.py <sid>"""
from __future__ import annotations

import json
import sys
from collections import deque
from datetime import datetime

sys.path.insert(0, "C:/Users/hongy/projects/migloop/src")
from migloop import service  # noqa: E402

LEAF = ("external", "generated", "outband")


def ts_s(ts: str) -> float:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()


def usage_by_agent(led):
    """每个 agent 的 (ts, out, ctx) 列表,按 message.id 去重(一次 API 响应会拆成多条记录)。"""
    paths: dict[str, str] = {}
    for a in led.agents.values():
        for act in a.actions:
            if act.src:
                paths[a.id] = act.src[0]
                break
    out: dict[str, list[tuple[str, int, int]]] = {}
    seen_msg: set[str] = set()
    for aid, p in paths.items():
        rows = out.setdefault(aid, [])
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                m = r.get("message") if isinstance(r.get("message"), dict) else None
                if not m or r.get("type") != "assistant" or not isinstance(m.get("usage"), dict):
                    continue
                mid = str(m.get("id") or "")
                if mid in seen_msg:
                    continue
                seen_msg.add(mid)
                u = m["usage"]
                ctx = int(u.get("input_tokens") or 0) + int(u.get("cache_read_input_tokens") or 0) \
                    + int(u.get("cache_creation_input_tokens") or 0)
                rows.append((r.get("timestamp") or "", int(u.get("output_tokens") or 0), ctx))
    return out


def version_tokens(led, usage, path: str, v: int) -> tuple[int, int, int]:
    """写第 v 版的 agent 在「上一效应 → 这一效应」窗口里花的 (输出 token, 上下文 token, 轮数)。"""
    st = led.stories[path]
    ver = st.versions[v - 1]
    a = led.agents.get(ver.by)
    if a is None or ver.by_ver is None:
        return 0, 0, 0
    effects = [x for x in a.actions if x.ver is not None]
    end = next((x.ts for x in effects if x.ver == ver.by_ver), ver.ts)
    start = next((x.ts for x in effects if x.ver == ver.by_ver - 1), "")
    rows = [r for r in usage.get(a.id, []) if start < r[0] <= end]
    return sum(r[1] for r in rows), sum(r[2] for r in rows), len(rows)


def hops(led, path: str, v: int, cap: int = 400) -> tuple[int, int, bool]:
    """从 (path, v) 往上游铺:文件版 → 写者 agent 版 → 它喂养该版的读(主会话只看窗口,子 agent 累计)+ 派发它的父版。
    返回 (最深跳数, 节点数, 是否撞上限)。"""
    seen = set()
    q = deque([(("f", path, v), 0)])
    depth = 0
    while q:
        node, d = q.popleft()
        if node in seen:
            continue
        seen.add(node)
        depth = max(depth, d)
        if len(seen) >= cap:
            return depth, len(seen), True
        if node[0] == "f":
            st = led.stories.get(node[1])
            if st is None or node[2] < 1 or node[2] > len(st.versions):
                continue
            ver = st.versions[node[2] - 1]
            if ver.source in LEAF or ver.by not in led.agents or ver.by_ver is None:
                continue
            q.append((("a", ver.by, ver.by_ver), d + 1))
        else:
            a = led.agents[node[1]]
            k = node[2]
            main = a.id.startswith("__main__")
            for act in a.actions:
                if act.at > k or (main and act.at != k):
                    continue
                for ref in act.files:
                    if ref.op == "read" and ref.v and ref.path != path:
                        q.append((("f", ref.path, ref.v), d + 1))
            if a.parent and a.parent_ver:
                q.append((("a", a.parent, a.parent_ver), d + 1))
    return depth, len(seen), False


def main(sid: str) -> None:
    p = service.locate_session(sid)
    led = service.session_ledger(p)
    pay = service.fixchain_payload(p)
    usage = usage_by_agent(led)
    rows = []
    for c in pay["chains"]:
        st = led.stories.get(c["file_abs"])
        if st is None:
            continue
        fix_vs = c.get("fix_versions") or []
        gen_n = sum(1 for ver in st.versions if ver.v not in fix_vs and ver.source not in LEAF)
        first_fix = fix_vs[0] if fix_vs else len(st.versions)
        d, n, capped = hops(led, c["file_abs"], first_fix)
        elapsed = (ts_s(c["fix_at"]) - ts_s(c["gen_at"])) / 3600 if c.get("gen_at") and c.get("fix_at") else None
        g_out = g_ctx = g_turns = f_out = f_ctx = f_turns = 0
        for ver in st.versions:
            o, cx, t = version_tokens(led, usage, c["file_abs"], ver.v)
            if ver.v in fix_vs:
                f_out += o; f_ctx += cx; f_turns += t
            else:
                g_out += o; g_ctx += cx; g_turns += t
        rows.append({"file": c["file"], "kind": c["kind"], "hops": d, "nodes": n, "capped": capped,
                     "elapsed_h": elapsed, "gen_n": gen_n, "fix_n": len(fix_vs),
                     "gen_out": g_out, "gen_ctx": g_ctx, "gen_turns": g_turns,
                     "fix_out": f_out, "fix_ctx": f_ctx, "fix_turns": f_turns})
    print(f"# {sid}: {len(rows)} 根;fix_after={led.fix_after}")
    for key, label, rev in (("hops", "最多跳(上游树最深跳数;节点数;撞上限)", True),
                            ("elapsed_h", "生成→修复耗时最长(小时)", True),
                            ("gen_n", "生成期改动次数最多(agent 写的版本数)", True),
                            ("fix_n", "修复期改动次数最多", True),
                            ("fix_ctx", "修复期最耗上下文 token(修复方窗口内每轮上下文之和)", True),
                            ("gen_ctx", "生成期最耗上下文 token", True)):
        print(f"\n## {label}")
        for r in sorted([r for r in rows if r[key] is not None], key=lambda r: r[key], reverse=rev)[:4]:
            print(f"- {r['file']} [{r['kind']}] 跳 {r['hops']}/节点 {r['nodes']}{'(撞上限)' if r['capped'] else ''} · "
                  f"耗时 {r['elapsed_h'] and round(r['elapsed_h'], 1)}h · 生成改 {r['gen_n']} · 修复改 {r['fix_n']} · "
                  f"生成 token 出 {r['gen_out']}/上下文 {r['gen_ctx']}/{r['gen_turns']} 轮 · "
                  f"修复 token 出 {r['fix_out']}/上下文 {r['fix_ctx']}/{r['fix_turns']} 轮")
    # 不是链根的工程文件,生成期改动最多的
    print("\n## 生成期改动最多的工程代码文件(含非链根)")
    allrows = []
    roots = {c["file_abs"] for c in pay["chains"]}
    for path, st in led.stories.items():
        if not path.endswith((".ets", ".ts", ".json5")) or "/spec/" in path or "/node_modules/" in path:
            continue
        n = sum(1 for ver in st.versions if ver.source not in LEAF
                and (led.fix_after is None or ver.ts < led.fix_after))
        if n:
            allrows.append((n, path.rsplit("/", 1)[-1], path in roots))
    for n, f, is_root in sorted(allrows, reverse=True)[:6]:
        print(f"- {f}: 生成期 {n} 版{'(链根)' if is_root else '(修复期没被改,无链)'}")


if __name__ == "__main__":
    main(sys.argv[1])
