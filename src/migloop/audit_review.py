"""Migration-wide, evidence-bounded audit. No absence-to-failure inference."""
from datetime import datetime

from .audit_events import collect, observation, phase


def instant(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.timestamp() if parsed.tzinfo is not None else None
    except (TypeError, AttributeError, ValueError, OverflowError):
        return None


def run(traces, *, material_gaps=False):
    unique, owners, stages, unavailable = {}, set(), [], []
    for trace in traces:
        meta = trace.get("meta") or {}
        sid = meta.get("session_id") or meta.get("source_file") or "unknown"
        owners.add(sid)
        stages.extend((sid, s) for s in trace.get("stages", []))
        for agent in trace.get("agents", []):
            owners.add(agent.get("agent_id"))
            if not agent.get("snapshot_of_main") and "audit_tools" not in agent:
                unavailable.append(agent.get("agent_id"))
        rows = collect(trace)
        if "audit_tools" not in trace:
            unavailable.append(sid)
            # Older trace inputs remain usable, but cannot certify full coverage.
            rows += [{**observation(t.get("name"), t.get("_inp") or {"command": t.get("brief", ""), "skill": t.get("skill", t.get("brief", ""))},
                                  t.get("result"), t.get("ok"), call=t.get("tuid") or "legacy-" + str(i), idx=t.get("idx", i), ts=t.get("ts")),
                      "owner": sid, "stage": t.get("stage"), "segment": t.get("seg"), "source": meta.get("source_file")}
                     for i, t in enumerate(trace.get("tools", []))]
        for row in rows:
            key = (row.get("owner"), row.get("call") or row.get("idx"), row.get("ts"), row.get("input_hash"))
            if key not in unique or (not unique[key].get("stage") and row.get("stage")):
                unique[key] = row
    rows = sorted(unique.values(), key=lambda r: instant(r.get("ts")) or 0)
    findings, checks = [], []

    def finding(rule, level, title, detail, evidence):
        first = evidence[0] if evidence else {}
        findings.append({"rule": rule, "level": level, "title": title, "detail": detail,
                         "agents": sorted({str(r.get("owner")) for r in evidence}), "paths": [],
                         "anchor": {"stage": first.get("stage"), "segment": first.get("segment"), "ts": first.get("ts"), "owner": first.get("owner")},
                         "evidence": [{k: r.get(k) for k in ("owner", "call", "source", "line", "ts", "outcome")} for r in evidence[:12]]})

    # Count actual failed calls across all agents. A retry is only recognized for
    # the same owner, tool and arguments; unrelated successes cannot clear it.
    for kind, rule in (("skill", "skill-fail"), ("shell", "script-fail")):
        failures = [r for r in rows if r["kind"] == kind and r["outcome"] == "failed"]
        unresolved, recovered = [], []
        for row in failures:
            retry = any(r.get("owner") == row.get("owner") and r["name"] == row["name"]
                        and r["input_hash"] == row["input_hash"] and r["outcome"] == "returned"
                        and instant(r.get("ts")) is not None and instant(row.get("ts")) is not None
                        and instant(r["ts"]) > instant(row["ts"]) for r in rows)
            (recovered if retry else unresolved).append(row)
        state = "failed" if unresolved else ("recovered" if recovered else "unknown" if material_gaps or unavailable or not rows else "observed")
        checks.append({"rule": rule, "status": state, "failed_calls": len(failures), "recovered_calls": len(recovered)})
        if failures:
            targets = "、".join(sorted({r["target"] for r in failures if r.get("target")}))
            finding(rule, "warn" if unresolved else "info", "工具调用失败记录" + (" · 已见同参重试成功" if not unresolved else ""),
                    (targets + "：" if targets else "") +
                    f"全会话观测到 {len(failures)} 次失败，其中 {len(recovered)} 次随后同参调用返回成功。"
                    "这是调用结果，不据此断言迁移产物无效；未恢复项也可能由其他方案解决。", failures)

    kinds = {phase(s.get("stage")) for _, s in stages}
    # Native workflow role is useful when custom stage names have no a2h alias.
    verify_names = {a.get("stage") for t in traces for a in t.get("agents", []) if str(a.get("type", "")).lower() == "verify"}
    has_verify = "verify" in kinds or bool(verify_names)
    requirements = [("build", "execute-no-build", "构建", bool(kinds & {"execute", "build"})),
                    ("device", "verify-no-emulator", "设备操作", has_verify),
                    ("install", "verify-no-install", "安装", has_verify),
                    ("screenshot", "verify-no-screenshot", "设备截图", has_verify)]
    for capability, rule, label, applicable in requirements:
        candidates = [r for r in rows if capability in r["capabilities"]]
        # Installation/build may be prepared earlier and reused. Other actions
        # outside a known verify phase are shown as context, not proof of verify.
        relevant = [r for r in candidates if capability in ("build", "install") or
                    phase(r.get("stage")) == "verify" or r.get("stage") in verify_names]
        returned = [r for r in relevant if r["outcome"] == "returned"]
        failed = [r for r in relevant if r["outcome"] == "failed"]
        status = ("observed" if returned else "not_applicable" if not applicable else
                  "failed" if failed else "unknown")
        checks.append({"rule": rule, "status": status, "observed_calls": len(returned),
                       "failed_calls": len(failed), "context_calls": len(candidates),
                       "build_success_receipts": sum(bool(r.get("build_success")) for r in returned)})
        if applicable and status != "observed":
            finding(rule, "warn" if failed else "info", label + ("调用有失败回执" if failed else "证据不足"),
                    "已检查同次迁移的主会话及子代理。" +
                    ("尚未观测到相应调用返回成功。" if failed else "未找到可识别的相关调用回执，脚本封装或材料缺口也可能导致未识别。") +
                    "不等同于没执行；设备可复用已启动的实例，安装和构建也可能在更早的阶段完成。", relevant)
            if not relevant:
                wanted = {"execute", "build"} if capability == "build" else {"verify"}
                anchor = next((s for _, s in stages if phase(s.get("stage")) in wanted or s.get("stage") in verify_names), {})
                findings[-1]["anchor"] = {"stage": anchor.get("stage")}
    # Explicit interruption only; absent end markers are not interruptions, and
    # emitted tokens cannot be labelled wasted without checking reused outputs.
    seen_agents = set()
    for trace in traces:
        for agent in trace.get("agents", []):
            aid = agent.get("agent_id")
            if aid in seen_agents or agent.get("snapshot_of_main"):
                continue
            seen_agents.add(aid)
            if agent.get("abort_explicit"):
                finding("aborted-agent", "warn", "代理有明确中断记录", "需核查后续是否续跑或接管；已写出的内容可能继续被复用，不将全部输出 token 视为浪费。",
                        [{"owner": aid, "stage": agent.get("stage"), "ts": agent.get("end_ts")}])
    checks.extend([{"rule": "spec-no-analyzer", "status": "not_applicable", "reason": "代理名称不是源码分析能力的证据"},
                   {"rule": "spec-main-write", "status": "not_applicable", "reason": "由谁写规格是流水线策略，不是通用缺陷"}])
    return {"findings": findings, "assessments": checks,
            "coverage": {"owners": len(owners), "calls": len(rows), "material_gaps": bool(material_gaps),
                         "hint_stages": sum(s.get("signal") == "skill-load-hint" for _, s in stages),
                         "unavailable_owners": sorted(set(str(x) for x in unavailable)),
                         "scope": "provided migration roots and their descendants"}}
