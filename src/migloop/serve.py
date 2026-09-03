"""``migloop <目标> --serve``:本机 stdlib HTTP,把报告页、返修链路页与两原子端点挂在
hmigbot 同名路径上(fixchain.html / viewer.html 的默认相对地址就是这些),零第三方依赖。

    /                                        → 302 到目标会话的报告页
    /api/insight1/report/<sid>  /insight1/report/<sid>
    /api/insight1/fixchain/<sid>             返修链路页(首屏轻,链由页面异步拉)
    /api/insight1/fixchain-data/<sid>        {chains, cross, t0}
    /api/insight1/atom/<sid>/<tool>          index | file | agent | blame | action(JSON)
    /api/insight1/atom/<sid>/text/<tool>     guide | sessions | index | file | agent | blame | diff | action(文本)
    /api/insight1/filediff/<sid>?file=&v=
"""

from __future__ import annotations

import json
import re
import sys
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from . import service

_RE_REPORT = re.compile(r"^/(?:api/)?insight1/report/([^/]+)/?$")
_RE_FIXCHAIN = re.compile(r"^/api/insight1/fixchain/([^/]+)/?$")
_RE_FIXDATA = re.compile(r"^/api/insight1/fixchain-data/([^/]+)/?$")
_RE_ATOM_TEXT = re.compile(r"^/api/insight1/atom/([^/]+)/text/([a-z]+)/?$")
_RE_ATOM = re.compile(r"^/api/insight1/atom/([^/]+)/([a-z]+)/?$")
_RE_FILEDIFF = re.compile(r"^/api/insight1/filediff/([^/]+)/?$")


class _Handler(BaseHTTPRequestHandler):
    default_sid: str = ""
    roots: dict[str, str] = {}

    def log_message(self, fmt: str, *args: Any) -> None:   # 安静;错误走 JSON 体
        pass

    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, obj: Any) -> None:
        self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _html(self, html: str) -> None:
        self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")

    def _text(self, status: int, text: str) -> None:
        self._send(status, text.encode("utf-8"), "text/plain; charset=utf-8")

    def _path_of(self, sid: str) -> str:
        return service.locate_session(urllib.parse.unquote(sid), self.roots)

    def do_GET(self) -> None:  # noqa: N802 - stdlib 命名
        url = urllib.parse.urlsplit(self.path)
        route = url.path
        args = {k: v[-1] for k, v in urllib.parse.parse_qs(url.query, keep_blank_values=True).items()}
        try:
            if route in ("/", "/index.html"):
                self.send_response(302)
                self.send_header("Location", f"/api/insight1/report/{self.default_sid}")
                self.end_headers()
                return
            m = _RE_REPORT.match(route)
            if m:
                self._html(service.report_html(self._path_of(m.group(1))))
                return
            m = _RE_FIXCHAIN.match(route)
            if m:
                self._html(service.fixchain_html(self._path_of(m.group(1))))
                return
            m = _RE_FIXDATA.match(route)
            if m:
                self._json(200, service.fixchain_payload(self._path_of(m.group(1))))
                return
            m = _RE_ATOM_TEXT.match(route)
            if m:
                self._text(200, service.atom_text(self._path_of(m.group(1)), m.group(2), args))
                return
            m = _RE_ATOM.match(route)
            if m:
                payload = service.atom_json(self._path_of(m.group(1)), m.group(2), args)
                if payload is None:
                    self._json(404, {"error": "账本里没有: " + json.dumps(args, ensure_ascii=False)})
                    return
                self._json(200, payload)
                return
            m = _RE_FILEDIFF.match(route)
            if m:
                if not args.get("file") or args.get("v") is None:
                    self._json(400, {"error": "需要 file= 与 v="})
                    return
                payload = service.file_diff(self._path_of(m.group(1)), str(args["file"]), int(args["v"]))
                if payload is None:
                    self._json(404, {"error": f"没有该版本: {args['file']}@{args['v']}"})
                    return
                self._json(200, payload)
                return
            self._json(404, {"error": "no such route", "path": route})
        except service.SessionLookupError as err:
            self._json(404, {"error": str(err)})
        except ValueError as err:
            self._json(400, {"error": f"参数错误: {err}"})
        except Exception as err:  # noqa: BLE001 - 服务不能因为一个请求崩
            self._json(500, {"error": f"构建失败: {err}"})


def make_server(default_sid: str, host: str = "127.0.0.1", port: int = 0,
                roots: dict[str, str] | None = None) -> ThreadingHTTPServer:
    handler = type("MigLoopHandler", (_Handler,), {"default_sid": default_sid, "roots": roots or {}})
    return ThreadingHTTPServer((host, port), handler)


def serve(target: str, host: str = "127.0.0.1", port: int = 0, open_browser: bool = False,
          roots: dict[str, str] | None = None) -> None:
    """阻塞运行;Ctrl+C 退出。首次打开会建账(大会话几十秒),之后走缓存。"""
    path = service.locate_session(target, roots)
    fmt = service._fmt_of(service.extract_trace(path))
    sid = service.root_sid8(fmt, path)
    srv = make_server(sid, host, port, roots)
    base = f"http://{host}:{srv.server_address[1]}"
    print(f"migloop serve · {path}")
    print(f"  报告页     {base}/api/insight1/report/{sid}")
    print(f"  返修链路   {base}/api/insight1/fixchain/{sid}")
    print(f"  两原子文本 {base}/api/insight1/atom/{sid}/text/guide")
    print("Ctrl+C 停止")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(f"{base}/api/insight1/report/{sid}")).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye", file=sys.stderr)
    finally:
        srv.server_close()
