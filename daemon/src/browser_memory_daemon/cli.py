from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request

from .app import make_server
from .config import load_config


def _request(method: str, url: str, *, token: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="memory")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--token", default=None)
    parser.add_argument("--runtime-root", default=None)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("serve")
    sub.add_parser("health")
    search = sub.add_parser("search")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=10)
    forget = sub.add_parser("forget")
    forget.add_argument("--domain")
    forget.add_argument("--url")
    cap = sub.add_parser("capture-fixture")
    cap.add_argument("--url", required=True)
    cap.add_argument("--title", default="Fixture")
    cap.add_argument("--text", required=True)
    args = parser.parse_args(argv)

    cfg = load_config(host=args.host, port=args.port, token=args.token, runtime_root=args.runtime_root, test_mode=False)
    base = f"http://{cfg.host}:{cfg.port}"
    if args.command == "serve":
        server = make_server(cfg)
        print(f"browser-memory-daemon listening on http://{cfg.host}:{cfg.port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            return 130
        return 0
    if args.command == "health":
        with urllib.request.urlopen(f"{base}/health", timeout=10) as response:
            print(response.read().decode("utf-8"))
        return 0
    if args.command == "search":
        q = urllib.parse.urlencode({"q": args.query, "limit": str(args.limit)})
        print(json.dumps(_request("GET", f"{base}/search?{q}", token=cfg.api_token), indent=2))
        return 0
    if args.command == "forget":
        print(json.dumps(_request("POST", f"{base}/forget", token=cfg.api_token, body={"domain": args.domain, "url": args.url}), indent=2))
        return 0
    if args.command == "capture-fixture":
        print(json.dumps(_request("POST", f"{base}/capture", token=cfg.api_token, body={"url": args.url, "title": args.title, "text": args.text}), indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
