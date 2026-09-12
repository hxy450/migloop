"""Standalone CLI/MCP for the inquiry engine shared with the session tree page."""

import argparse
import json
import time

from .engine import Engine
from .store import Store, discover, encode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    importing = sub.add_parser("import")
    importing.add_argument("--pool", required=True)
    query = sub.add_parser("query")
    query.add_argument("request", help="JSON object or batch list")
    query.add_argument(
        "--json",
        action="store_true",
        help="complete structured result for developer checks, not model transport",
    )
    page = sub.add_parser("page")
    page.add_argument("result_id")
    page.add_argument("offset", type=int)
    serve = sub.add_parser("serve")
    serve.add_argument("--port", type=int, default=8878)
    sub.add_parser("mcp")
    args = parser.parse_args()
    if args.command == "import":
        started = time.perf_counter()
        store = Store.build(args.db, discover(args.pool))
        print(
            encode(
                {
                    "seconds": time.perf_counter() - started,
                    "sources": store.db.execute(
                        "SELECT COUNT(*) FROM sources"
                    ).fetchone()[0],
                    "records": store.db.execute(
                        "SELECT COUNT(*) FROM records"
                    ).fetchone()[0],
                    "effects": store.db.execute(
                        "SELECT COUNT(*) FROM effects"
                    ).fetchone()[0],
                }
            )
        )
        store.close()
    elif args.command == "serve":
        from .interfaces import make_http

        server = make_http(args.db, args.port)
        print(f"http://127.0.0.1:{server.server_port}/", flush=True)
        try:
            server.serve_forever()
        finally:
            server.server_close()
    elif args.command == "mcp":
        from .interfaces import build_mcp

        build_mcp(args.db).run()
    else:
        store = Store(args.db)
        try:
            engine = Engine(store)
            if args.command == "page":
                print(engine.page(args.result_id, args.offset))
            else:
                request = json.loads(args.request)
                if args.json:
                    print(encode(engine.query(request)))
                else:
                    print(
                        engine.investigate(
                            request if isinstance(request, list) else [request]
                        )
                    )
        finally:
            store.close()


if __name__ == "__main__":
    main()
