from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import subprocess
import time
from typing import Any, Callable
import urllib.error
import urllib.request

from .config import RuntimeConfig, has_non_root_mount_ancestor

DAILY_DRIVER_UNITS = (
    "browser-memory-daemon.service",
    "browser-memory-media-worker.service",
)
PRIORITY_LABELS = {
    "0": "emergency",
    "1": "alert",
    "2": "critical",
    "3": "error",
    "4": "warning",
}
HEADROOM_WARNING_BYTES = int(os.environ.get("BMD_HEALTH_HEADROOM_WARNING_BYTES", "5000000000"))
HEADROOM_ERROR_BYTES = int(os.environ.get("BMD_HEALTH_HEADROOM_ERROR_BYTES", "1000000000"))
HEADROOM_WARNING_USED_PERCENT = float(os.environ.get("BMD_HEALTH_HEADROOM_WARNING_USED_PERCENT", "90"))
HEADROOM_ERROR_USED_PERCENT = float(os.environ.get("BMD_HEALTH_HEADROOM_ERROR_USED_PERCENT", "98"))
SERVICE_RESTART_WARNING_COUNT = int(os.environ.get("BMD_HEALTH_SERVICE_RESTART_WARNING_COUNT", "3"))
SERVICE_RESTART_ERROR_COUNT = int(os.environ.get("BMD_HEALTH_SERVICE_RESTART_ERROR_COUNT", "10"))
SERVICE_START_WARNING_COUNT = int(os.environ.get("BMD_HEALTH_SERVICE_START_WARNING_COUNT", "3"))
SERVICE_START_ERROR_COUNT = int(os.environ.get("BMD_HEALTH_SERVICE_START_ERROR_COUNT", "10"))
_RUNTIME_TABLES = (
    "sources",
    "documents",
    "visits",
    "visit_events",
    "snapshots",
    "chunks",
    "chunks_fts",
    "media_artifacts",
    "media_fetch_tasks",
    "privacy_rules",
    "audit_events",
    "deletion_receipts",
)
_EXTENSION_TOKEN_FILES = (
    "src/service_worker.js",
    "src/options.js",
    "src/popup.js",
)
_DAILY_DRIVER_UNIT_COMMANDS = {
    "browser-memory-daemon.service": "-m browser_memory_daemon --host ${BMD_HOST} --port ${BMD_PORT} serve",
    "browser-memory-media-worker.service": "-m browser_memory_daemon media-worker --loop --interval ${BMD_MEDIA_WORKER_INTERVAL} --limit ${BMD_MEDIA_WORKER_LIMIT}",
}


@dataclass(frozen=True)
class CommandResult:
    args: list[str]
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    elapsed_ms: float = 0.0
    timed_out: bool = False


CommandRunner = Callable[[list[str], int], CommandResult]
UrlOpen = Callable[..., Any]


def _run_command(args: list[str], timeout: int = 10) -> CommandResult:
    started = time.perf_counter()
    try:
        completed = subprocess.run(args, text=True, capture_output=True, timeout=timeout)
        return CommandResult(
            args=args,
            exit_code=completed.returncode,
            stdout=completed.stdout.strip(),
            stderr=completed.stderr.strip(),
            elapsed_ms=round((time.perf_counter() - started) * 1000, 3),
        )
    except FileNotFoundError as exc:
        return CommandResult(args=args, exit_code=127, stderr=str(exc), elapsed_ms=round((time.perf_counter() - started) * 1000, 3))
    except subprocess.TimeoutExpired as exc:
        stdout: str = ""
        if isinstance(exc.stdout, bytes):
            stdout = exc.stdout.decode("utf-8", errors="replace").strip()
        elif exc.stdout is not None:
            stdout = str(exc.stdout).strip()
        return CommandResult(
            args=args,
            exit_code=124,
            stdout=stdout,
            stderr=f"timed out after {timeout}s",
            elapsed_ms=round((time.perf_counter() - started) * 1000, 3),
            timed_out=True,
        )


def default_windows_extension_dir() -> Path | None:
    configured = os.environ.get("BMD_WINDOWS_EXTENSION_DIR")
    if configured:
        return Path(configured).expanduser()
    win_user = os.environ.get("BMD_WINDOWS_USER") or os.environ.get("USER") or os.environ.get("LOGNAME")
    if not win_user:
        return None
    return Path("/mnt/c/Users") / win_user / "AppData" / "Local" / "browser-memory-daemon" / "extension"


def daily_driver_health_snapshot(
    config: RuntimeConfig,
    *,
    base_url: str | None = None,
    extension_dir: str | Path | None = None,
    token_file: str | Path | None = None,
    env_file: str | Path | None = None,
    unit_dir: str | Path | None = None,
    journal_since: str = "24 hours ago",
    include_windows_loopback: bool = True,
    powershell: str | Path | None = None,
    runner: CommandRunner | None = None,
    urlopen: UrlOpen | None = None,
) -> dict[str, Any]:
    """Build a redaction-safe daily-driver health snapshot.

    The snapshot intentionally reports aggregate counts, states, timings, paths,
    and sanitized journal templates only. It never includes captured page text,
    snippets, raw capture URLs, cookies, bearer tokens, or extension API token
    values.
    """

    selected_runner = runner or _run_command
    selected_urlopen = urlopen or urllib.request.urlopen
    selected_base_url = (base_url or f"http://{config.host}:{config.port}").rstrip("/")
    selected_extension_dir = Path(extension_dir).expanduser() if extension_dir else default_windows_extension_dir()
    selected_token_file = Path(token_file).expanduser() if token_file else config.config_root / "token"
    selected_env_file = Path(env_file).expanduser() if env_file else config.config_root / "env"
    selected_unit_dir = Path(unit_dir).expanduser() if unit_dir else Path.home() / ".config" / "systemd" / "user"

    loopback = _loopback_health(selected_base_url, selected_urlopen)
    windows_loopback = _windows_loopback_health(config.port, selected_runner, include_windows_loopback=include_windows_loopback, powershell=powershell)
    systemd = _systemd_status(selected_runner, api_token=config.api_token)
    journals = _journal_status(selected_runner, since=journal_since)
    database = _database_status(config)
    storage = _storage_status(config, selected_extension_dir)
    install = _install_artifact_status(
        config,
        token_file=selected_token_file,
        env_file=selected_env_file,
        unit_dir=selected_unit_dir,
        extension_dir=selected_extension_dir,
    )
    extension = _extension_status(selected_extension_dir, expected_policy_mode=config.policy_mode, expected_api_token=install.get("expected_api_token"))

    errors: list[str] = []
    warnings: list[str] = []
    _score_loopback(loopback, errors)
    _score_windows_loopback(windows_loopback, errors, warnings)
    _score_systemd(systemd, errors, warnings)
    _score_journals(journals, errors, warnings)
    _score_database(database, errors, warnings)
    _score_storage(storage, errors, warnings)
    _score_install_artifacts(install, errors, warnings)
    _score_extension(extension, errors, warnings)

    return {
        "ok": not errors,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "summary": {
            "status": "error" if errors else "warning" if warnings else "ok",
            "errors": errors,
            "warnings": warnings,
        },
        "loopback": loopback,
        "windows_loopback": windows_loopback,
        "systemd": systemd,
        "journals": journals,
        "database": database,
        "storage": storage,
        "install": {key: value for key, value in install.items() if key != "expected_api_token"},
        "extension": extension,
    }


def _loopback_health(base_url: str, urlopen: UrlOpen) -> dict[str, Any]:
    started = time.perf_counter()
    url = f"{base_url}/health"
    try:
        with urlopen(url, timeout=10) as response:
            raw = response.read().decode("utf-8")
            status = getattr(response, "status", None) or response.getcode()
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        return {
            "ok": False,
            "url": url,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
            "error": _safe_error(exc),
        }
    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        return {
            "ok": False,
            "url": url,
            "status_code": status,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
            "error": f"invalid JSON: {exc.msg}",
        }
    return {
        "ok": status == 200 and bool(payload.get("ok")),
        "url": url,
        "status_code": status,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "health": _select_keys(payload, ("ok", "capture_enabled", "policy_mode", "storage_root", "blob_root", "version")),
    }


def _windows_loopback_health(
    port: int,
    runner: CommandRunner,
    *,
    include_windows_loopback: bool,
    powershell: str | Path | None,
) -> dict[str, Any]:
    if not include_windows_loopback:
        return {"ok": None, "skipped": True, "reason": "disabled"}
    ps_path = Path(powershell or os.environ.get("BMD_POWERSHELL") or "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")
    if not ps_path.exists():
        return {"ok": None, "skipped": True, "reason": "powershell-not-found", "path": str(ps_path)}
    script = (
        "try { "
        f"Invoke-RestMethod -Uri 'http://127.0.0.1:{port}/health' -TimeoutSec 5 | ConvertTo-Json -Compress"
        " } catch { Write-Error $_; exit 1 }"
    )
    result = runner([str(ps_path), "-NoProfile", "-Command", script], 15)
    payload: dict[str, Any] | None = None
    parse_error = None
    if result.stdout:
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            parse_error = f"invalid JSON: {exc.msg}"
    ok = result.exit_code == 0 and bool(payload and payload.get("ok"))
    output: dict[str, Any] = {
        "ok": ok,
        "skipped": False,
        "elapsed_ms": result.elapsed_ms,
        "exit_code": result.exit_code,
    }
    if payload is not None:
        output["health"] = _select_keys(payload, ("ok", "capture_enabled", "policy_mode", "storage_root", "blob_root", "version"))
    if parse_error:
        output["error"] = parse_error
    elif result.exit_code != 0:
        output["error"] = _sanitize_journal_message(result.stderr or result.stdout or "windows loopback check failed")
    return output


def _restart_budget(n_restarts: int | None) -> dict[str, Any]:
    count = int(n_restarts or 0)
    status = "error" if count >= SERVICE_RESTART_ERROR_COUNT else "warning" if count >= SERVICE_RESTART_WARNING_COUNT else "ok"
    return {
        "count": count,
        "status": status,
        "warning_threshold": SERVICE_RESTART_WARNING_COUNT,
        "error_threshold": SERVICE_RESTART_ERROR_COUNT,
    }


def _systemd_status(runner: CommandRunner, *, api_token: str) -> dict[str, Any]:
    units: dict[str, Any] = {}
    available = True
    for unit in DAILY_DRIVER_UNITS:
        show = runner(
            [
                "systemctl",
                "--user",
                "show",
                unit,
                "--property=Id,LoadState,ActiveState,SubState,NRestarts,ExecMainStatus,ExecMainStartTimestamp,StateChangeTimestamp,MainPID,FragmentPath",
                "--no-pager",
            ],
            10,
        )
        enabled = runner(["systemctl", "--user", "is-enabled", unit], 10)
        active = runner(["systemctl", "--user", "is-active", unit], 10)
        if show.exit_code == 127 or enabled.exit_code == 127 or active.exit_code == 127:
            available = False
        props = _parse_systemctl_show(show.stdout)
        main_pid = _safe_int(props.get("MainPID"))
        n_restarts = _safe_int(props.get("NRestarts"))
        units[unit] = {
            "ok": show.exit_code == 0 and props.get("LoadState") == "loaded" and props.get("ActiveState") == "active" and active.stdout == "active",
            "fragment_path": props.get("FragmentPath"),
            "load_state": props.get("LoadState"),
            "active_state": props.get("ActiveState"),
            "sub_state": props.get("SubState"),
            "is_active": active.stdout or active.stderr,
            "is_enabled": enabled.stdout or enabled.stderr,
            "n_restarts": n_restarts,
            "restart_budget": _restart_budget(n_restarts),
            "exec_main_status": _safe_int(props.get("ExecMainStatus")),
            "main_pid": main_pid,
            "process_arg_secrecy": _process_arg_secrecy(main_pid, runner, api_token=api_token),
            "exec_main_start_timestamp": props.get("ExecMainStartTimestamp"),
            "state_change_timestamp": props.get("StateChangeTimestamp"),
            "command_exit_codes": {
                "show": show.exit_code,
                "is_enabled": enabled.exit_code,
                "is_active": active.exit_code,
            },
        }
    return {"available": available, "units": units}


def _journal_status(runner: CommandRunner, *, since: str) -> dict[str, Any]:
    units: dict[str, Any] = {}
    for unit in DAILY_DRIVER_UNITS:
        result = runner(
            ["journalctl", "--user", "-u", unit, "--since", since, "-p", "warning..alert", "--no-pager", "--output=json"],
            20,
        )
        parsed = _parse_journal_json_lines(result.stdout)
        priority_counts = Counter(str(row.get("PRIORITY", "unknown")) for row in parsed)
        templates = Counter(_sanitize_journal_message(str(row.get("MESSAGE", ""))) for row in parsed)
        service_start_budget = _service_start_budget(parsed)
        realtime_values = [_safe_int(row.get("__REALTIME_TIMESTAMP")) for row in parsed]
        realtime_values = [value for value in realtime_values if value is not None]
        units[unit] = {
            "ok": result.exit_code == 0,
            "since": since,
            "exit_code": result.exit_code,
            "warning_or_higher_count": len(parsed),
            "priority_counts": dict(sorted(priority_counts.items())),
            "priority_labels": {key: PRIORITY_LABELS.get(key, "unknown") for key in sorted(priority_counts)},
            "error_or_higher_count": sum(count for priority, count in priority_counts.items() if priority.isdigit() and int(priority) <= 3),
            "service_start_budget": service_start_budget,
            "first_realtime_utc": _realtime_us_to_iso(min(realtime_values)) if realtime_values else None,
            "last_realtime_utc": _realtime_us_to_iso(max(realtime_values)) if realtime_values else None,
            "top_sanitized_messages": [
                {"message": message, "count": count}
                for message, count in templates.most_common(5)
                if message
            ],
        }
        if result.exit_code != 0:
            units[unit]["error"] = _sanitize_journal_message(result.stderr or result.stdout or "journalctl failed")
    return {"since": since, "units": units}


def _service_start_budget(rows: list[dict[str, Any]]) -> dict[str, Any]:
    patterns = (
        "failed to start",
        "start request repeated too quickly",
        "failed with result",
        "no space left on device",
        "resources",
    )
    matching = [row for row in rows if any(pattern in str(row.get("MESSAGE", "")).lower() for pattern in patterns)]
    count = len(matching)
    status = "error" if count >= SERVICE_START_ERROR_COUNT else "warning" if count >= SERVICE_START_WARNING_COUNT else "ok"
    return {
        "count": count,
        "status": status,
        "warning_threshold": SERVICE_START_WARNING_COUNT,
        "error_threshold": SERVICE_START_ERROR_COUNT,
    }


def _database_status(config: RuntimeConfig) -> dict[str, Any]:
    db_path = config.db_path
    output: dict[str, Any] = {
        "db_path": str(db_path),
        "exists": db_path.exists(),
        "db_file_bytes": db_path.stat().st_size if db_path.exists() else 0,
        "wal_file_bytes": _file_size(Path(str(db_path) + "-wal")),
    }
    if not db_path.exists():
        output["ok"] = False
        output["error"] = "database file missing"
        return output
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            output["integrity_check"] = conn.execute("PRAGMA integrity_check").fetchone()[0]
            output["page_count"] = conn.execute("PRAGMA page_count").fetchone()[0]
            output["page_size"] = conn.execute("PRAGMA page_size").fetchone()[0]
            output["counts"] = {table: _safe_table_count(conn, table) for table in _RUNTIME_TABLES}
            output["freshness"] = _freshness(conn)
            output["media_queue"] = _media_queue_aggregates(conn)
            output["chunks_missing_fts"] = _safe_scalar(
                conn,
                "SELECT COUNT(*) FROM chunks WHERE id NOT IN (SELECT chunk_id FROM chunks_fts)",
            )
            output["ok"] = output["integrity_check"] == "ok" and output["chunks_missing_fts"] == 0
        finally:
            conn.close()
    except sqlite3.Error as exc:
        output["ok"] = False
        output["error"] = _safe_error(exc)
    return output


def _freshness(conn: sqlite3.Connection) -> dict[str, Any]:
    return {
        "visits": _min_max(conn, "visits", "captured_at"),
        "snapshots": _min_max(conn, "snapshots", "captured_at"),
        "visit_events": _min_max(conn, "visit_events", "event_ended_at"),
        "media_artifacts": _min_max(conn, "media_artifacts", "created_at"),
        "audit_events": _min_max(conn, "audit_events", "created_at"),
    }


def _media_queue_aggregates(conn: sqlite3.Connection) -> dict[str, Any]:
    due_where = """
            status IN ('pending','retrying')
              AND (next_attempt_at IS NULL OR datetime(next_attempt_at) <= CURRENT_TIMESTAMP)
    """
    stale_lease_where = """
            lease_until IS NOT NULL
              AND datetime(lease_until) < CURRENT_TIMESTAMP
              AND status IN ('fetching','uploading','leased')
    """
    return {
        "artifact_status_counts": _group_counts(conn, "media_artifacts", "capture_status"),
        "task_status_counts": _group_counts(conn, "media_fetch_tasks", "status"),
        "due_pending_or_retrying": _safe_scalar(conn, f"SELECT COUNT(*) FROM media_fetch_tasks WHERE {due_where}"),
        "due_by_status": _status_counts_for_where(conn, "media_fetch_tasks", "status", due_where),
        "due_by_artifact_status": _due_by_artifact_status(conn, due_where),
        **_oldest_due_summary(conn, due_where),
        "stale_leases": _safe_scalar(conn, f"SELECT COUNT(*) FROM media_fetch_tasks WHERE {stale_lease_where}"),
        **_oldest_stale_lease_summary(conn, stale_lease_where),
        "latest_worker_run": _latest_media_worker_run(conn),
        "worker_throughput": _media_worker_throughput(conn),
    }


def _status_counts_for_where(conn: sqlite3.Connection, table: str, column: str, where_sql: str) -> dict[str, int]:
    try:
        rows = conn.execute(
            f"SELECT {column} AS value, COUNT(*) AS count FROM {table} WHERE {where_sql} GROUP BY {column} ORDER BY {column}"
        ).fetchall()
        return {str(row["value"]): int(row["count"]) for row in rows}
    except sqlite3.Error:
        return {}


def _due_by_artifact_status(conn: sqlite3.Connection, where_sql: str) -> list[dict[str, Any]]:
    try:
        rows = conn.execute(
            f"""
            SELECT COALESCE(media_artifacts.capture_status, 'unknown') AS capture_status,
                   COALESCE(media_artifacts.media_type, 'unknown') AS media_type,
                   COUNT(*) AS tasks
            FROM media_fetch_tasks
            LEFT JOIN media_artifacts ON media_artifacts.id = media_fetch_tasks.artifact_id
            WHERE {where_sql}
            GROUP BY media_artifacts.capture_status, media_artifacts.media_type
            ORDER BY tasks DESC, capture_status, media_type
            LIMIT 20
            """
        ).fetchall()
        return [
            {"capture_status": str(row["capture_status"]), "media_type": str(row["media_type"]), "tasks": int(row["tasks"])}
            for row in rows
        ]
    except sqlite3.Error:
        return []


def _oldest_due_summary(conn: sqlite3.Connection, where_sql: str) -> dict[str, Any]:
    return _oldest_timestamp_summary(
        conn,
        f"""
        SELECT MIN(datetime(COALESCE(next_attempt_at, created_at))) AS oldest_at,
               CAST(strftime('%s', 'now') - strftime('%s', MIN(datetime(COALESCE(next_attempt_at, created_at)))) AS INTEGER) AS age_seconds
        FROM media_fetch_tasks
        WHERE {where_sql}
        """,
        timestamp_key="oldest_due_at",
        age_key="oldest_due_age_seconds",
    )


def _oldest_stale_lease_summary(conn: sqlite3.Connection, where_sql: str) -> dict[str, Any]:
    return _oldest_timestamp_summary(
        conn,
        f"""
        SELECT MIN(datetime(lease_until)) AS oldest_at,
               CAST(strftime('%s', 'now') - strftime('%s', MIN(datetime(lease_until))) AS INTEGER) AS age_seconds
        FROM media_fetch_tasks
        WHERE {where_sql}
        """,
        timestamp_key="oldest_stale_lease_until",
        age_key="oldest_stale_lease_age_seconds",
    )


def _oldest_timestamp_summary(conn: sqlite3.Connection, sql: str, *, timestamp_key: str, age_key: str) -> dict[str, Any]:
    try:
        row = conn.execute(sql).fetchone()
    except sqlite3.Error:
        return {timestamp_key: None, age_key: None}
    if not row or row["oldest_at"] is None:
        return {timestamp_key: None, age_key: None}
    return {timestamp_key: row["oldest_at"], age_key: max(0, int(row["age_seconds"] or 0))}


def _latest_media_worker_run(conn: sqlite3.Connection) -> dict[str, Any] | None:
    try:
        row = conn.execute(
            """
            SELECT created_at,
                   metadata_json,
                   CAST(strftime('%s', 'now') - strftime('%s', datetime(created_at)) AS INTEGER) AS age_seconds
            FROM audit_events
            WHERE event_type = 'media.worker.run_once'
            ORDER BY datetime(created_at) DESC, created_at DESC
            LIMIT 1
            """
        ).fetchone()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    metadata = _safe_json_dict(row["metadata_json"])
    output: dict[str, Any] = {
        "created_at": row["created_at"],
        "age_seconds": max(0, int(row["age_seconds"] or 0)),
    }
    for key in ("worker_kind", "attempted", "stored", "failed", "skipped", "already_stored"):
        if key in metadata:
            output[key] = metadata[key]
    return output


def _media_worker_throughput(conn: sqlite3.Connection) -> dict[str, dict[str, int]]:
    return {
        "1h": _media_worker_window(conn, "-1 hour"),
        "24h": _media_worker_window(conn, "-24 hours"),
    }


def _media_worker_window(conn: sqlite3.Connection, sqlite_modifier: str) -> dict[str, int]:
    totals = {"runs": 0, "attempted": 0, "stored": 0, "failed": 0, "skipped": 0, "already_stored": 0}
    try:
        rows = conn.execute(
            """
            SELECT metadata_json
            FROM audit_events
            WHERE event_type = 'media.worker.run_once'
              AND datetime(created_at) >= datetime('now', ?)
            """,
            (sqlite_modifier,),
        ).fetchall()
    except sqlite3.Error:
        return totals
    totals["runs"] = len(rows)
    for row in rows:
        metadata = _safe_json_dict(row["metadata_json"])
        for key in ("attempted", "stored", "failed", "skipped", "already_stored"):
            totals[key] += _safe_int(metadata.get(key)) or 0
    return totals


def _safe_json_dict(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, str) or not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _storage_status(config: RuntimeConfig, extension_dir: Path | None) -> dict[str, Any]:
    paths = {
        "config_root": config.config_root,
        "data_root": config.data_root,
        "blob_root": config.blob_root,
        "state_root": config.state_root,
        "clean_text_root": config.clean_text_root,
        "media_root": config.media_root,
    }
    if extension_dir is not None:
        paths["extension_dir"] = extension_dir
    output = {name: _disk_usage(path) for name, path in paths.items()}
    output.setdefault("blob_root", {})["mount_guard"] = {
        "required": config.require_blob_root_mount,
        "ok": (not config.require_blob_root_mount) or has_non_root_mount_ancestor(config.blob_root),
    }
    return output


def _process_arg_secrecy(main_pid: int | None, runner: CommandRunner, *, api_token: str) -> dict[str, Any]:
    if not main_pid or main_pid <= 0:
        return {"checked": False, "reason": "no-main-pid"}
    result = runner(["ps", "-p", str(main_pid), "-o", "args="], 10)
    args_text = result.stdout or ""
    return {
        "checked": result.exit_code == 0,
        "exit_code": result.exit_code,
        "token_literal_present": bool(api_token and api_token in args_text),
        "api_token_assignment_present": "BMD_API_TOKEN=" in args_text,
    }


def _install_artifact_status(
    config: RuntimeConfig,
    *,
    token_file: Path,
    env_file: Path,
    unit_dir: Path,
    extension_dir: Path | None,
) -> dict[str, Any]:
    token_state, expected_api_token = _token_file_state(token_file, runtime_api_token=config.api_token)
    return {
        "expected_api_token": expected_api_token,
        "token_file": token_state,
        "env_file": _env_file_state(env_file, expected_api_token=expected_api_token),
        "unit_dir": str(unit_dir),
        "unit_files": {
            unit: _unit_file_state(unit_dir / unit, unit=unit, expected_api_token=expected_api_token)
            for unit in DAILY_DRIVER_UNITS
        },
        "extension_dir": str(extension_dir) if extension_dir else None,
    }


def _token_file_state(path: Path, *, runtime_api_token: str) -> tuple[dict[str, Any], str | None]:
    state = _basic_file_state(path)
    if not path.exists():
        state.update({"non_empty": False, "owner_only_permissions": False, "matches_runtime_token": False})
        return state, None
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        state.update({"non_empty": False, "owner_only_permissions": False, "matches_runtime_token": False, "error": _safe_error(exc)})
        return state, None
    token = raw.strip()
    state.update(
        {
            "non_empty": bool(token),
            "line_count": len([line for line in raw.splitlines() if line.strip()]),
            "owner_only_permissions": _owner_only_permissions(path),
            "matches_runtime_token": bool(token and token == runtime_api_token),
        }
    )
    return state, token or None


def _env_file_state(path: Path, *, expected_api_token: str | None) -> dict[str, Any]:
    state = _basic_file_state(path)
    if not path.exists():
        state.update({"owner_only_permissions": False, "api_token_assignment_present": False, "matches_token_file": False})
        return state
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        state.update({"owner_only_permissions": False, "api_token_assignment_present": False, "matches_token_file": False, "error": _safe_error(exc)})
        return state
    state.update(
        {
            "owner_only_permissions": _owner_only_permissions(path),
            "api_token_assignment_present": "BMD_API_TOKEN=" in text,
            "policy_mode_assignment_present": "BMD_POLICY_MODE=" in text,
            "blob_root_assignment_present": "BMD_BLOB_ROOT=" in text,
            "require_blob_root_mount_assignment_present": "BMD_REQUIRE_BLOB_ROOT_MOUNT=" in text,
            "pythonpath_assignment_present": "PYTHONPATH=" in text,
            "matches_token_file": bool(expected_api_token and f"BMD_API_TOKEN={expected_api_token}" in text),
        }
    )
    return state


def _unit_file_state(path: Path, *, unit: str, expected_api_token: str | None) -> dict[str, Any]:
    state = _basic_file_state(path)
    expected_command = _DAILY_DRIVER_UNIT_COMMANDS.get(unit, "")
    if not path.exists():
        state.update({"uses_environment_file": False, "expected_execstart_present": False, "token_literal_present": False, "api_token_assignment_present": False})
        return state
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        state.update({"uses_environment_file": False, "expected_execstart_present": False, "token_literal_present": False, "api_token_assignment_present": False, "error": _safe_error(exc)})
        return state
    exec_lines = [line for line in text.splitlines() if line.startswith("ExecStart=")]
    state.update(
        {
            "uses_environment_file": "EnvironmentFile=%h/.config/browser-memory-daemon/env" in text,
            "expected_execstart_present": bool(expected_command and any(expected_command in line for line in exec_lines)),
            "token_literal_present": bool(expected_api_token and expected_api_token in text),
            "api_token_assignment_present": any("BMD_API_TOKEN" in line for line in exec_lines),
        }
    )
    return state


def _basic_file_state(path: Path) -> dict[str, Any]:
    state: dict[str, Any] = {"path": str(path), "exists": path.exists(), "bytes": _file_size(path)}
    try:
        mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else None
    except OSError:
        mode = None
    state["mode_octal"] = f"{mode:04o}" if mode is not None else None
    return state


def _owner_only_permissions(path: Path) -> bool:
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError:
        return False
    return (mode & 0o077) == 0


def _extension_status(extension_dir: Path | None, *, expected_policy_mode: str, expected_api_token: str | None = None) -> dict[str, Any]:
    if extension_dir is None:
        return {"ok": False, "exists": False, "error": "extension directory could not be inferred"}
    manifest_path = extension_dir / "manifest.json"
    manifest: dict[str, Any] = {}
    manifest_error = None
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            manifest_error = _safe_error(exc)
    token_files = {rel: _extension_file_state(extension_dir / rel, expected_policy_mode=expected_policy_mode, expected_api_token=expected_api_token) for rel in _EXTENSION_TOKEN_FILES}
    files = {
        "manifest.json": {"exists": manifest_path.exists(), "bytes": _file_size(manifest_path)},
        **{rel: {"exists": (extension_dir / rel).exists(), "bytes": _file_size(extension_dir / rel)} for rel in _EXTENSION_TOKEN_FILES},
    }
    token_configured = all(state.get("api_token_configured") for state in token_files.values())
    token_matches = all(state.get("api_token_matches_expected") for state in token_files.values()) if expected_api_token else None
    policy_modes = {rel: state.get("policy_mode_default") for rel, state in token_files.items()}
    policy_matches = all(mode == expected_policy_mode for mode in policy_modes.values() if mode)
    ok = extension_dir.exists() and manifest_path.exists() and not manifest_error and token_configured and policy_matches and token_matches is not False
    output: dict[str, Any] = {
        "ok": ok,
        "path": str(extension_dir),
        "exists": extension_dir.exists(),
        "manifest": _select_keys(manifest, ("manifest_version", "name", "version")) if manifest else {},
        "files": files,
        "api_token_configured": token_configured,
        "api_token_matches_token_file": token_matches,
        "policy_mode_defaults": policy_modes,
        "expected_policy_mode": expected_policy_mode,
    }
    if manifest_error:
        output["error"] = manifest_error
    missing = [rel for rel, state in files.items() if not state["exists"]]
    if missing:
        output["missing_files"] = missing
    return output


def _extension_file_state(path: Path, *, expected_policy_mode: str, expected_api_token: str | None) -> dict[str, Any]:
    state: dict[str, Any] = {"exists": path.exists()}
    if not path.exists():
        return state
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        state["error"] = _safe_error(exc)
        return state
    token_matches = re.findall(r"apiToken:\s*(['\"])(.*?)\1", text)
    token_values = [value for _quote, value in token_matches]
    state["api_token_configured"] = any(token_values)
    if expected_api_token is not None:
        state["api_token_matches_expected"] = any(value == expected_api_token for value in token_values)
    policy_match = re.search(r"policyMode:\s*['\"]([^'\"]+)['\"]", text)
    state["policy_mode_default"] = policy_match.group(1) if policy_match else None
    state["policy_mode_matches_expected"] = state["policy_mode_default"] == expected_policy_mode
    return state


def _disk_usage(path: Path) -> dict[str, Any]:
    target = path
    while not target.exists() and target.parent != target:
        target = target.parent
    try:
        usage = shutil.disk_usage(target)
    except OSError as exc:
        return {"path": str(path), "exists": path.exists(), "ok": False, "error": _safe_error(exc)}
    used = usage.total - usage.free
    used_percent = round((used / usage.total) * 100, 2) if usage.total else None
    headroom_status = "ok"
    if usage.free < HEADROOM_ERROR_BYTES or (isinstance(used_percent, (int, float)) and used_percent >= HEADROOM_ERROR_USED_PERCENT):
        headroom_status = "error"
    elif usage.free < HEADROOM_WARNING_BYTES or (isinstance(used_percent, (int, float)) and used_percent >= HEADROOM_WARNING_USED_PERCENT):
        headroom_status = "warning"
    return {
        "path": str(path),
        "checked_path": str(target),
        "exists": path.exists(),
        "ok": True,
        "total_bytes": usage.total,
        "used_bytes": used,
        "free_bytes": usage.free,
        "used_percent": used_percent,
        "headroom": {
            "status": headroom_status,
            "warning_free_bytes": HEADROOM_WARNING_BYTES,
            "error_free_bytes": HEADROOM_ERROR_BYTES,
            "warning_used_percent": HEADROOM_WARNING_USED_PERCENT,
            "error_used_percent": HEADROOM_ERROR_USED_PERCENT,
        },
    }


def _score_loopback(loopback: dict[str, Any], errors: list[str]) -> None:
    if not loopback.get("ok"):
        errors.append("WSL loopback /health is not OK")


def _score_windows_loopback(windows_loopback: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    if windows_loopback.get("skipped"):
        warnings.append(f"Windows loopback check skipped: {windows_loopback.get('reason')}")
    elif not windows_loopback.get("ok"):
        errors.append("Windows loopback /health did not return OK")


def _score_systemd(systemd: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    if not systemd.get("available"):
        warnings.append("systemctl is unavailable or could not inspect user units")
    for unit, state in systemd.get("units", {}).items():
        if not state.get("ok"):
            errors.append(f"{unit} is not active/running")
        if state.get("is_enabled") not in {"enabled", "static"}:
            warnings.append(f"{unit} is not enabled")
        restart_budget = state.get("restart_budget") or {}
        if restart_budget.get("status") == "error":
            errors.append(f"{unit} restart budget exceeded: NRestarts={restart_budget.get('count')}")
        elif restart_budget.get("status") == "warning":
            warnings.append(f"{unit} restart budget warning: NRestarts={restart_budget.get('count')}")
        process = state.get("process_arg_secrecy") or {}
        if process.get("token_literal_present") or process.get("api_token_assignment_present"):
            errors.append(f"{unit} appears to expose token material in process arguments")


def _score_journals(journals: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    for unit, state in journals.get("units", {}).items():
        if not state.get("ok"):
            warnings.append(f"journalctl check failed for {unit}")
            continue
        if state.get("error_or_higher_count", 0) > 0:
            errors.append(f"{unit} has {state['error_or_higher_count']} journal error-or-higher entries in window")
        elif state.get("warning_or_higher_count", 0) > 0:
            warnings.append(f"{unit} has {state['warning_or_higher_count']} journal warning entries in window")
        service_budget = state.get("service_start_budget") or {}
        if service_budget.get("status") == "error":
            errors.append(f"{unit} service-start budget exceeded: {service_budget.get('count')} matching journal entries in window")
        elif service_budget.get("status") == "warning":
            warnings.append(f"{unit} service-start budget warning: {service_budget.get('count')} matching journal entries in window")


def _score_database(database: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    if not database.get("ok"):
        errors.append("database integrity/FTS check is not OK")
    media_queue = database.get("media_queue") or {}
    if media_queue.get("stale_leases", 0) > 0:
        errors.append(f"media queue has {media_queue['stale_leases']} stale leases")
    if media_queue.get("due_pending_or_retrying", 0) > 0:
        warnings.append(f"media queue has {media_queue['due_pending_or_retrying']} due pending/retrying tasks")


def _score_storage(storage: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    for name, state in storage.items():
        if not state.get("ok"):
            warnings.append(f"storage path {name} could not be checked")
            continue
        headroom = state.get("headroom") or {}
        if headroom.get("status") == "error":
            errors.append(f"storage path {name} below hard headroom threshold: {state.get('free_bytes')} bytes free, {state.get('used_percent')}% used")
        elif headroom.get("status") == "warning":
            warnings.append(f"storage path {name} below warning headroom threshold: {state.get('free_bytes')} bytes free, {state.get('used_percent')}% used")
        mount_guard = state.get("mount_guard") or {}
        if mount_guard.get("required") and not mount_guard.get("ok"):
            errors.append(f"storage path {name} is not on a mounted filesystem but BMD_REQUIRE_BLOB_ROOT_MOUNT=1")


def _score_install_artifacts(install: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    token = install.get("token_file") or {}
    if not token.get("exists"):
        errors.append("daily-driver token file is missing")
    elif not token.get("non_empty"):
        errors.append("daily-driver token file is empty")
    elif not token.get("owner_only_permissions"):
        errors.append("daily-driver token file permissions are not owner-only")
    if token.get("line_count", 1) != 1:
        warnings.append("daily-driver token file should contain exactly one non-empty line")
    if token.get("exists") and not token.get("matches_runtime_token"):
        warnings.append("daily-driver token file does not match the token used for this health check")

    env_file = install.get("env_file") or {}
    if not env_file.get("exists"):
        errors.append("daily-driver environment file is missing")
    else:
        if not env_file.get("owner_only_permissions"):
            errors.append("daily-driver environment file permissions are not owner-only")
        if not env_file.get("api_token_assignment_present"):
            errors.append("daily-driver environment file is missing BMD_API_TOKEN")
        if not env_file.get("matches_token_file"):
            errors.append("daily-driver environment token does not match token file")
        if not env_file.get("policy_mode_assignment_present"):
            warnings.append("daily-driver environment file is missing BMD_POLICY_MODE")
        if not env_file.get("blob_root_assignment_present"):
            warnings.append("daily-driver environment file is missing BMD_BLOB_ROOT")
        if not env_file.get("require_blob_root_mount_assignment_present"):
            warnings.append("daily-driver environment file is missing BMD_REQUIRE_BLOB_ROOT_MOUNT")
        if not env_file.get("pythonpath_assignment_present"):
            warnings.append("daily-driver environment file is missing PYTHONPATH")

    for unit, state in (install.get("unit_files") or {}).items():
        if not state.get("exists"):
            errors.append(f"daily-driver unit file is missing: {unit}")
            continue
        if not state.get("uses_environment_file"):
            errors.append(f"{unit} does not use the protected EnvironmentFile")
        if not state.get("expected_execstart_present"):
            errors.append(f"{unit} ExecStart does not match the expected daily-driver command")
        if state.get("token_literal_present") or state.get("api_token_assignment_present"):
            errors.append(f"{unit} contains token material in the unit ExecStart")


def _score_extension(extension: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    if not extension.get("exists"):
        errors.append("Windows extension artifact directory is missing")
        return
    if not extension.get("manifest"):
        errors.append("Windows extension manifest is missing or invalid")
    if not extension.get("api_token_configured"):
        errors.append("Windows extension artifact does not have a configured API token default")
    if extension.get("api_token_matches_token_file") is False:
        errors.append("Windows extension artifact token defaults do not match the WSL token file")
    expected = extension.get("expected_policy_mode")
    for rel, mode in extension.get("policy_mode_defaults", {}).items():
        if mode != expected:
            warnings.append(f"Windows extension {rel} policy default is {mode!r}, expected {expected!r}")


def _parse_systemctl_show(text: str) -> dict[str, str]:
    props: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            props[key] = value
    return props


def _parse_journal_json_lines(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or not stripped.startswith("{"):
            continue
        try:
            rows.append(json.loads(stripped))
        except json.JSONDecodeError:
            continue
    return rows


def _sanitize_journal_message(message: str) -> str:
    safe = message.strip()
    safe = re.sub(r"Bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer <redacted>", safe, flags=re.I)
    safe = re.sub(r"https?://\S+", "<url>", safe)
    safe = re.sub(r"blob:[^\s]+", "<blob-url>", safe)
    safe = re.sub(r"(?<!\w)/(?:[^\s'\"<>]+)", "<path>", safe)
    safe = re.sub(r"\b(?:[a-fA-F0-9]{12,}|[A-Za-z0-9_-]{24,})\b", "<id>", safe)
    safe = re.sub(r"\b\d+(?:\.\d+)?\b", "<n>", safe)
    return safe[:220]


def _safe_error(exc: BaseException) -> str:
    return _sanitize_journal_message(f"{type(exc).__name__}: {exc}")


def _safe_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_scalar(conn: sqlite3.Connection, sql: str) -> int | None:
    try:
        row = conn.execute(sql).fetchone()
        return int(row[0]) if row is not None else None
    except sqlite3.Error:
        return None


def _safe_table_count(conn: sqlite3.Connection, table: str) -> int | None:
    try:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    except sqlite3.Error:
        return None


def _min_max(conn: sqlite3.Connection, table: str, column: str) -> dict[str, Any]:
    try:
        row = conn.execute(f"SELECT MIN({column}) AS min, MAX({column}) AS max FROM {table}").fetchone()
        return {"min": row["min"], "max": row["max"]}
    except sqlite3.Error as exc:
        return {"error": _safe_error(exc)}


def _group_counts(conn: sqlite3.Connection, table: str, column: str) -> dict[str, int]:
    try:
        rows = conn.execute(f"SELECT {column} AS value, COUNT(*) AS count FROM {table} GROUP BY {column} ORDER BY count DESC").fetchall()
        return {str(row["value"]): int(row["count"]) for row in rows}
    except sqlite3.Error:
        return {}


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size if path.exists() else 0
    except OSError:
        return 0


def _realtime_us_to_iso(value: int) -> str:
    return datetime.fromtimestamp(value / 1_000_000, tz=timezone.utc).isoformat(timespec="seconds")


def _select_keys(data: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: data[key] for key in keys if key in data}
