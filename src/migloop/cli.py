# -*- coding: utf-8 -*-
"""
MigLoop Trace Viewer — 单命令生成 Claude Code / Codex 会话轨迹页面

用法:
  migloop                          列出最近的 session
  migloop <session.jsonl 路径>      指定 transcript 文件
  migloop <session-id 前缀>         在 Claude / Codex session 目录中自动定位
  migloop <项目名片段>              匹配项目目录,取最新 session
  migloop <目标> -o out.html --open

跨平台:Windows `py migloop.pyz ...` / macOS·Linux `python3 migloop.pyz ...`
依赖:Python >= 3.9,无第三方库
"""
import argparse
import os
import sys
import webbrowser

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from . import adapters
from .render import build_html, load_asset, load_template


def projects_root(cli_root=None):
    return cli_root or adapters.get("claude").default_root()


def codex_sessions_root(cli_root=None):
    return cli_root or adapters.get("codex").default_root()


def all_sessions(root, codex_root=None):
    """[(mtime, path, project, size, format, session_id)] 新→旧。"""
    roots = {"claude": root, "codex": codex_root or codex_sessions_root()}
    return [(row.mtime, row.path, row.project, row.size, row.format, row.session_id)
            for row in adapters.discover(roots)]


def short_proj(dirname):
    """C--Users-hongy-projects-transfer-app-arch9 -> transfer-app-arch9"""
    key = "-projects-"
    i = dirname.rfind(key)
    if i >= 0 and i + len(key) < len(dirname):
        return dirname[i + len(key):]
    return dirname[-30:]


def list_sessions(root, codex_root=None, limit=20):
    rows = all_sessions(root, codex_root)
    if not rows:
        print("没有找到 Claude Code 或 Codex session transcript")
        return
    print("最近的 session:\n")
    print("  %-30s %-7s %-10s %8s  %s" % ("项目", "格式", "session", "大小", "修改时间"))
    import datetime
    for mt, p, proj, size, kind, sid in rows[:limit]:
        t = datetime.datetime.fromtimestamp(mt).strftime("%m-%d %H:%M")
        print("  %-30s %-7s %-10s %7.1fM  %s" %
              (short_proj(proj)[:30], kind, sid[:8], size / 1e6, t))
    print("\n用法: migloop <session-id 前缀 | 项目名片段 | jsonl 路径> [-o out.html] [--open]")


def resolve_target(target, root, codex_root=None):
    """把用户输入解析成唯一的 jsonl 路径;歧义/未命中时报错退出。"""
    if os.path.isfile(target):
        return target
    directory_hint = None
    if os.path.isdir(target):
        cands = sorted(glob.glob(os.path.join(target, "*.jsonl")),
                       key=os.path.getmtime, reverse=True)
        if cands:
            return cands[0]
        # A project directory is also a useful lookup key for Codex because
        # rollout files live under ~/.codex/sessions rather than in the repo.
        directory_hint = os.path.basename(os.path.abspath(target))

    rows = all_sessions(root, codex_root)
    lookup = directory_hint or target
    by_sid = [p for _, p, _, _, _, sid in rows if sid.startswith(lookup)]
    if len(by_sid) == 1:
        return by_sid[0]
    if len(by_sid) > 1:
        sys.exit("session-id 前缀不唯一,命中 %d 个,请给更长前缀" % len(by_sid))

    low = lookup.lower()
    by_proj = [(mt, p, proj) for mt, p, proj, _, _, _ in rows if low in proj.lower()]
    if by_proj:
        projs = sorted(set(proj for _, _, proj in by_proj))
        if len(projs) > 1:
            print("匹配到多个项目,取最新 session。其余候选:")
            for pr in projs:
                print("  -", short_proj(pr))
        return by_proj[0][1]

    sys.exit("找不到匹配 %r 的 Claude/Codex session;运行 migloop 不带参数可列出全部" % target)


def session_format(path):
    return adapters.detect(path).FORMAT


def extract_trace(path):
    adapter = adapters.detect(path)
    return adapter.extract(path)


def main():
    ap = argparse.ArgumentParser(prog="migloop", description="Claude Code / Codex 会话轨迹可视化页面生成器")
    ap.add_argument("targets", nargs="*", help="jsonl 路径 | session-id 前缀 | 项目名片段(--compare 时可多个)")
    ap.add_argument("-o", "--out", default=None, help="输出 HTML 路径")
    ap.add_argument("--open", action="store_true", help="生成后在浏览器打开")
    ap.add_argument("--compare", action="store_true", help="多个目标生成跨会话对比页")
    ap.add_argument("--projects-root", default=None, help="覆盖 ~/.claude/projects")
    ap.add_argument("--codex-sessions-root", default=None, help="覆盖 ~/.codex/sessions")
    ap.add_argument("--live", action="store_true",
                    help="增量监控仍在追加的 session，并启动本地自动刷新页面")
    ap.add_argument("--interval", type=float, default=10.0,
                    help="--live 文件变化与页面刷新间隔秒数（默认 10）")
    ap.add_argument("--host", default="127.0.0.1",
                    help="--live 本地服务监听地址（默认 127.0.0.1）")
    ap.add_argument("--port", type=int, default=0,
                    help="--live 端口；0 表示自动选择空闲端口")
    ap.add_argument("--cache-dir", default=None,
                    help="--live 增量 checkpoint 目录（默认 ~/.migloop/cache）")
    ap.add_argument("--reset-live-cache", action="store_true",
                    help="忽略已有增量 checkpoint，从 transcript 起点重放一次")
    ap.add_argument("--no-final", action="store_true",
                    help="--live 停止时不生成最终自包含 HTML")
    ap.add_argument("--chat-provider", default="codex",
                    choices=("codex", "anthropic", "openai-compatible", "off"),
                    help="--live 页面分析助手的模型 provider（默认 codex；off 关闭）")
    ap.add_argument("--chat-model", default=None,
                    help="分析助手模型名；codex 留空时使用本机已配置默认模型")
    ap.add_argument("--chat-api-key-env", default=None,
                    help="API key 所在环境变量名（默认按 provider 选择）")
    ap.add_argument("--chat-base-url", default=None,
                    help="Anthropic endpoint 或 OpenAI-compatible API base URL")
    ap.add_argument("--chat-timeout", type=float, default=180.0,
                    help="单次分析最长等待秒数（默认 180）")
    args = ap.parse_args()

    root = projects_root(args.projects_root)
    codex_root = codex_sessions_root(args.codex_sessions_root)
    if not args.targets:
        list_sessions(root, codex_root)
        return

    if args.live and args.compare:
        sys.exit("--live 不能与 --compare 同时使用")

    if args.compare:
        if len(args.targets) < 2:
            sys.exit("--compare 需要至少 2 个目标")
        from .render import compare as compare_build
        traces = []
        for tgt in args.targets:
            jl = resolve_target(tgt, root, codex_root)
            print("解析 %s ..." % jl)
            traces.append(extract_trace(jl))
        font = compare_build.extract_font_face(load_asset("viewer.html"))
        html = compare_build.build_compare_html(traces, load_asset("compare.html"), font)
        out = args.out or "migloop-compare-%d.html" % len(traces)
        with open(out, "w", encoding="utf-8") as f:
            f.write(html)
        print("对比页(%d 个会话)已生成 -> %s (%.0f KB)" % (
            len(traces), os.path.abspath(out), os.path.getsize(out) / 1024))
        if args.open:
            import pathlib
            webbrowser.open(pathlib.Path(out).resolve().as_uri())
        return

    jsonl = resolve_target(args.targets[0], root, codex_root)
    adapter = adapters.detect(jsonl)
    fmt = adapter.FORMAT
    sub = os.path.join(os.path.splitext(jsonl)[0], "subagents")
    if fmt == "claude" and not os.path.isdir(sub):
        print("提示: 未找到 %s,子代理泳道将为空(分享 session 时请连同同名目录一起拷贝)" % sub)

    if args.live:
        if not adapter.SUPPORTS_LIVE:
            sys.exit("%s session 已支持离线/对比报告；--live 增量监控尚未接入该 adapter" % fmt)
        from .chat import provider as chat_provider
        from .live import monitor as live_session
        cwd_base = os.path.basename(os.path.dirname(jsonl)).replace("C--Users-hongy-projects-", "") or "session"
        out = args.out or "migloop-%s-%s.html" % (
            cwd_base, os.path.splitext(os.path.basename(jsonl))[0][:8])
        template = load_template()

        def build_snapshot_bytes():
            trace = adapter.extract(jsonl)
            return build_html(trace, template).encode("utf-8")

        chat_service = None
        if args.chat_provider != "off":
            try:
                chat_config = chat_provider.ChatConfig(
                    provider=args.chat_provider,
                    model=args.chat_model,
                    api_key_env=args.chat_api_key_env,
                    base_url=args.chat_base_url,
                    timeout=max(10.0, args.chat_timeout),
                )

                def build_chat_context():
                    return chat_provider.build_lineage_context(
                        adapter.extract(jsonl), chat_config.max_context_chars
                    )

                chat_service = chat_provider.ChatService(
                    chat_config, build_chat_context,
                    session=chat_provider.SessionCorpus(jsonl),
                )
                info = chat_service.info()
                print("分析助手    -> %s / %s" % (info["provider"], info["model"]))
            except chat_provider.ChatConfigurationError as exc:
                print("提示: 分析助手未启用: %s" % exc)

        live_session.run_live(
            jsonl=jsonl,
            build_snapshot=build_snapshot_bytes,
            out_path=out,
            host=args.host,
            port=args.port,
            interval=args.interval,
            cache_dir=args.cache_dir,
            reset_cache=args.reset_live_cache,
            open_browser=args.open,
            write_final=not args.no_final,
            chat_service=chat_service,
        )
        return

    print("解析 %s ..." % jsonl)
    trace = extract_trace(jsonl)

    m, t = trace["meta"], trace["totals"]
    cwd_base = os.path.basename((m.get("cwd") or "").rstrip("\\/")) or "session"
    out = args.out or "migloop-%s-%s.html" % (cwd_base, (m["session_id"] or "x")[:8])
    html = build_html(trace, load_template())
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)

    print("  session  %s  (%s %s, %s)" %
          (m["session_id"], m.get("session_format", "claude"), m["cc_version"], m["model"]))
    print("  时长 %.1fh · 工具调用 %d · 子代理 %d · 阶段 %s" % (
        (t["duration_ms"] or 0) / 3600000, t["tool_calls"], t["subagent_transcripts"],
        " → ".join(s["label"] for s in trace["stages"] if s["stage"] != "setup")))
    print("已生成 -> %s (%.0f KB)" % (os.path.abspath(out), os.path.getsize(out) / 1024))

    if args.open:
        import pathlib
        webbrowser.open(pathlib.Path(out).resolve().as_uri())


if __name__ == "__main__":
    main()
