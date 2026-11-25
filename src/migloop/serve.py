"""``migloop <目标> --serve``:本机 stdlib HTTP,把报告页与会话总览挂在 hmigbot 同名路径上
(viewer.html / chain.html 的默认相对地址就是这些),零第三方依赖。

    /                                        → 302 到目标会话的报告页
    /api/insight1/report/<sid>  /insight1/report/<sid>
    /api/insight1/chain/<sid>                会话总览页:同工程全部会话 + ECAT 各轮(chain.py)
    /api/insight1/chain-data/<sid>           会话总览数据(JSON)
<sid> 也可以是 URL 编码后的 transcript 路径(ECAT 角色会话不在会话发现的根里)。

返修链路页、两原子端点与调查页已移到 fuxi-ailabs/a2h-memory 的 ``fixchain/``:那边的服务继承
``_Handler``,在 ``route_get`` 前面加自己的路由,经 ``make_server(..., handler=...)`` 起服。
"""

from __future__ import annotations

import json
import re
import sys
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, ClassVar

from . import service

_RE_REPORT = re.compile(r"^/(?:api/)?insight1/report/([^/]+)/?$")
_RE_CHAIN = re.compile(r"^/(?:api/)?insight1/chain/([^/]+)/?$")
_RE_CHAIN_DATA = re.compile(r"^/api/insight1/chain-data/([^/]+)/?$")


class _Handler(BaseHTTPRequestHandler):
    default_sid: str = ""
    roots: ClassVar[dict[str, str]] = {}

    def log_message(self, fmt: str, *args: Any) -> None:   # 安静;错误走 JSON 体
        pass

    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, obj: Any) -> None:
        self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _html(self, html: str) -> None:
        self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")

    def _path_of(self, sid: str) -> str:
        return service.locate_session(urllib.parse.unquote(sid), self.roots)

    def route_get(self, route: str, args: dict[str, str]) -> bool:
        """处理一条 GET 路由,认不出返回 False(子类先试自己的路由,再交给这里)。"""
        m = _RE_REPORT.match(route)
        if m:
            self._html(service.report_html(self._path_of(m.group(1))))
            return True
        m = _RE_CHAIN.match(route)
        if m:
            from .render import load_asset
            ident = json.dumps(urllib.parse.unquote(m.group(1)), ensure_ascii=False).replace("</", "<\\/")
            self._html(load_asset("chain.html").replace("__CHAIN_ID__", ident))
            return True
        m = _RE_CHAIN_DATA.match(route)
        if m:
            from . import chain
            self._json(200, chain.build_chain(self._path_of(m.group(1)), service.extract_trace))
            return True
        return False

    def do_GET(self) -> None:
        url = urllib.parse.urlsplit(self.path)
        route = url.path
        args = {k: v[-1] for k, v in urllib.parse.parse_qs(url.query, keep_blank_values=True).items()}
        try:
            if route in ("/", "/index.html"):
                self.send_response(302)
                self.send_header("Location", f"/api/insight1/report/{self.default_sid}")
                self.end_headers()
                return
            if not self.route_get(route, args):
                self._json(404, {"error": "no such route", "path": route})
        except service.SessionLookupError as err:
            self._json(404, {"error": str(err)})
        except ValueError as err:
            self._json(400, {"error": f"参数错误: {err}"})
        except Exception as err:  # 服务不能因为一个请求崩
            self._json(500, {"error": f"构建失败: {err}"})


def make_server(default_sid: str, host: str = "127.0.0.1", port: int = 0,
                roots: dict[str, str] | None = None,
                handler: type[_Handler] | None = None) -> ThreadingHTTPServer:
    cls = type("MigLoopHandler", (handler or _Handler,), {"default_sid": default_sid, "roots": roots or {}})
    return ThreadingHTTPServer((host, port), cls)


def serve(target: str, host: str = "127.0.0.1", port: int = 0, open_browser: bool = False,
          roots: dict[str, str] | None = None) -> None:
    """阻塞运行;Ctrl+C 退出。"""
    path = service.locate_session(target, roots)
    fmt = service._fmt_of(service.extract_trace(path))
    sid = service.root_sid8(fmt, path)
    srv = make_server(sid, host, port, roots)
    base = f"http://{host}:{srv.server_address[1]}"
    print(f"migloop serve · {path}")
    print(f"  报告页     {base}/api/insight1/report/{sid}")
    print(f"  会话总览   {base}/api/insight1/chain/{sid}")
    print("Ctrl+C 停止")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(f"{base}/api/insight1/report/{sid}")).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye", file=sys.stderr)
    finally:
        srv.server_close()
