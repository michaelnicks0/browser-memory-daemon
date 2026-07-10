from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request

from .app import make_server
from .blob_migration import migrate_blob_root
from .config import load_config
from .daily_driver_health import daily_driver_health_snapshot
from .db import connect, init_db
from .media import purge_media_cache
from .media_worker import run_loop as run_media_worker_loop, run_once as run_media_worker_once


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
    parser.add_argument("--blob-root", default=None)
    parser.add_argument("--policy-mode", choices=["all", "recall", "balanced", "strict"], default=None)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("serve")
    sub.add_parser("health")
    doctor_cmd = sub.add_parser("doctor")
    doctor_cmd.add_argument("--storage-census", action="store_true", help="walk clean-text/media roots for exact file counts; default uses DB-derived counts")
    daily_health = sub.add_parser("daily-driver-health")
    daily_health.add_argument("--journal-since", default="24 hours ago")
    daily_health.add_argument("--extension-dir")
    daily_health.add_argument("--powershell")
    daily_health.add_argument("--skip-windows-loopback", action="store_true")
    daily_health.add_argument("--no-fail", action="store_true")
    recent = sub.add_parser("recent")
    recent.add_argument("--limit", type=int, default=25)
    timeline = sub.add_parser("timeline")
    timeline.add_argument("--date")
    timeline.add_argument("--after")
    timeline.add_argument("--before")
    timeline.add_argument("--limit", type=int, default=100)
    document = sub.add_parser("document")
    document.add_argument("document_id")
    snapshot = sub.add_parser("snapshot")
    snapshot.add_argument("snapshot_id")
    search = sub.add_parser("search")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=10)
    policy = sub.add_parser("policy-rules")
    policy.add_argument("--block-domain")
    policy.add_argument("--block-url-prefix")
    forget = sub.add_parser("forget")
    forget.add_argument("--domain")
    forget.add_argument("--url")
    cap = sub.add_parser("capture-fixture")
    cap.add_argument("--url", required=True)
    cap.add_argument("--title", default="Fixture")
    cap.add_argument("--text", required=True)
    worker = sub.add_parser("media-worker")
    worker.add_argument("--once", action="store_true")
    worker.add_argument("--loop", action="store_true")
    worker.add_argument("--interval", type=float, default=30.0)
    worker.add_argument("--limit", type=int, default=25)
    cache = sub.add_parser("media-cache")
    cache_sub = cache.add_subparsers(dest="cache_command", required=True)
    purge = cache_sub.add_parser("purge")
    purge.add_argument("--domain")
    purge.add_argument("--document-id")
    purge.add_argument("--snapshot-id")
    purge.add_argument("--older-than")
    purge.add_argument("--max-bytes-to-purge", type=int)
    purge.add_argument("--dry-run", action="store_true")
    purge.add_argument("--execute", action="store_true")
    purge.add_argument("--rehydrate", action="store_true")
    rehydrate = cache_sub.add_parser("rehydrate")
    rehydrate.add_argument("--domain")
    rehydrate.add_argument("--document-id")
    rehydrate.add_argument("--snapshot-id")
    rehydrate.add_argument("--limit", type=int, default=100)
    blob = sub.add_parser("blob-root")
    blob_sub = blob.add_subparsers(dest="blob_command", required=True)
    migrate = blob_sub.add_parser("migrate")
    migrate.add_argument("--from-root", default=None)
    migrate.add_argument("--execute", action="store_true")
    migrate.add_argument("--remove-source", action="store_true")
    args = parser.parse_args(argv)

    cfg = load_config(
        host=args.host,
        port=args.port,
        token=args.token,
        policy_mode=args.policy_mode,
        runtime_root=args.runtime_root,
        blob_root=args.blob_root,
        test_mode=False,
    )
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
    if args.command == "recent":
        q = urllib.parse.urlencode({"limit": str(args.limit)})
        print(json.dumps(_request("GET", f"{base}/recent?{q}", token=cfg.api_token), indent=2))
        return 0
    if args.command == "timeline":
        params = {"limit": str(args.limit)}
        if args.date:
            params["date"] = args.date
        if args.after:
            params["after"] = args.after
        if args.before:
            params["before"] = args.before
        q = urllib.parse.urlencode(params)
        print(json.dumps(_request("GET", f"{base}/timeline?{q}", token=cfg.api_token), indent=2))
        return 0
    if args.command == "document":
        document_id = urllib.parse.quote(args.document_id, safe="")
        print(json.dumps(_request("GET", f"{base}/documents/{document_id}", token=cfg.api_token), indent=2))
        return 0
    if args.command == "snapshot":
        snapshot_id = urllib.parse.quote(args.snapshot_id, safe="")
        print(json.dumps(_request("GET", f"{base}/snapshots/{snapshot_id}", token=cfg.api_token), indent=2))
        return 0
    if args.command == "doctor":
        q = "?storage_census=full" if args.storage_census else ""
        print(json.dumps(_request("GET", f"{base}/doctor{q}", token=cfg.api_token), indent=2))
        return 0
    if args.command == "daily-driver-health":
        result = daily_driver_health_snapshot(
            cfg,
            extension_dir=args.extension_dir,
            journal_since=args.journal_since,
            include_windows_loopback=not args.skip_windows_loopback,
            powershell=args.powershell,
        )
        print(json.dumps(result, indent=2))
        return 0 if (args.no_fail or result.get("ok")) else 1
    if args.command == "policy-rules":
        if args.block_domain and args.block_url_prefix:
            parser.error("policy-rules accepts only one of --block-domain or --block-url-prefix")
        if args.block_domain or args.block_url_prefix:
            body = {
                "rule_type": "url-prefix" if args.block_url_prefix else "domain",
                "pattern": args.block_url_prefix or args.block_domain,
                "action": "block",
            }
            print(json.dumps(_request("POST", f"{base}/policy/rules", token=cfg.api_token, body=body), indent=2))
        else:
            print(json.dumps(_request("GET", f"{base}/policy/rules", token=cfg.api_token), indent=2))
        return 0
    if args.command == "forget":
        has_domain = args.domain is not None and str(args.domain).strip() != ""
        has_url = args.url is not None and str(args.url).strip() != ""
        if has_domain == has_url:
            parser.error("forget accepts exactly one of --domain or --url")
        print(json.dumps(_request("POST", f"{base}/forget", token=cfg.api_token, body={"domain": args.domain, "url": args.url}), indent=2))
        return 0
    if args.command == "media-worker":
        init_db(cfg)
        if args.loop and not args.once:
            run_media_worker_loop(cfg, interval_seconds=args.interval, limit=args.limit)
            return 0
        with connect(cfg.db_path) as conn:
            print(json.dumps(run_media_worker_once(conn, cfg, limit=args.limit), indent=2))
        return 0
    if args.command == "media-cache":
        init_db(cfg)
        if args.cache_command == "purge":
            body = {
                "domain": args.domain,
                "document_id": args.document_id,
                "snapshot_id": args.snapshot_id,
                "older_than": args.older_than,
                "max_bytes_to_purge": args.max_bytes_to_purge,
                "dry_run": not args.execute,
                "rehydrate": args.rehydrate,
            }
            with connect(cfg.db_path) as conn:
                print(json.dumps(purge_media_cache(conn, cfg, body), indent=2))
            return 0
        if args.cache_command == "rehydrate":
            body = {"domain": args.domain, "document_id": args.document_id, "snapshot_id": args.snapshot_id, "dry_run": False, "rehydrate": True, "rehydrate_only": True}
            with connect(cfg.db_path) as conn:
                purge_media_cache(conn, cfg, body)
                print(json.dumps(run_media_worker_once(conn, cfg, limit=args.limit), indent=2))
            return 0
    if args.command == "blob-root":
        init_db(cfg)
        if args.blob_command == "migrate":
            with connect(cfg.db_path) as conn:
                print(json.dumps(migrate_blob_root(conn, cfg, source_root=args.from_root, execute=args.execute, remove_source=args.remove_source), indent=2))
            return 0
    if args.command == "capture-fixture":
        print(json.dumps(_request("POST", f"{base}/capture", token=cfg.api_token, body={"url": args.url, "title": args.title, "text": args.text}), indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
