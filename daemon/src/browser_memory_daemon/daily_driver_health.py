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
import subprocess
import time
from typing import Any, Callable
import urllib.error
import urllib.request

from .config import RuntimeConfig

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

    loopback = _loopback_health(selected_base_url, selected_urlopen)
    windows_loopback = _windows_loopback_health(config.port, selected_runner, include_windows_loopback=include_windows_loopback, powershell=powershell)
    systemd = _systemd_status(selected_runner)
    journals = _journal_status(selected_runner, since=journal_since)
    database = _database_status(config)
    storage = _storage_status(config, selected_extension_dir)
    extension = _extension_status(selected_extension_dir, expected_policy_mode=config.policy_mode)

    errors: list[str] = []
    warnings: list[str] = []
    _score_loopback(loopback, errors)
    _score_windows_loopback(windows_loopback, errors, warnings)
    _score_systemd(systemd, errors, warnings)
    _score_journals(journals, errors, warnings)
    _score_database(database, errors, warnings)
    _score_storage(storage, warnings)
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
        "health": _select_keys(payload, ("ok", "capture_enabled", "policy_mode", "storage_root", "version")),
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
        output["health"] = _select_keys(payload, ("ok", "capture_enabled", "policy_mode", "storage_root", "version"))
    if parse_error:
        output["error"] = parse_error
    elif result.exit_code != 0:
        output["error"] = _sanitize_journal_message(result.stderr or result.stdout or "windows loopback check failed")
    return output


def _systemd_status(runner: CommandRunner) -> dict[str, Any]:
    units: dict[str, Any] = {}
    available = True
    for unit in DAILY_DRIVER_UNITS:
        show = runner(
            [
                "systemctl",
                "--user",
                "show",
                unit,
                "--property=Id,LoadState,ActiveState,SubState,NRestarts,ExecMainStatus,ExecMainStartTimestamp,StateChangeTimestamp",
                "--no-pager",
            ],
            10,
        )
        enabled = runner(["systemctl", "--user", "is-enabled", unit], 10)
        active = runner(["systemctl", "--user", "is-active", unit], 10)
        if show.exit_code == 127 or enabled.exit_code == 127 or active.exit_code == 127:
            available = False
        props = _parse_systemctl_show(show.stdout)
        units[unit] = {
            "ok": show.exit_code == 0 and props.get("LoadState") == "loaded" and props.get("ActiveState") == "active" and active.stdout == "active",
            "load_state": props.get("LoadState"),
            "active_state": props.get("ActiveState"),
            "sub_state": props.get("SubState"),
            "is_active": active.stdout or active.stderr,
            "is_enabled": enabled.stdout or enabled.stderr,
            "n_restarts": _safe_int(props.get("NRestarts")),
            "exec_main_status": _safe_int(props.get("ExecMainStatus")),
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
    return {
        "artifact_status_counts": _group_counts(conn, "media_artifacts", "capture_status"),
        "task_status_counts": _group_counts(conn, "media_fetch_tasks", "status"),
        "due_pending_or_retrying": _safe_scalar(
            conn,
            """
            SELECT COUNT(*) FROM media_fetch_tasks
            WHERE status IN ('pending','retrying')
              AND (next_attempt_at IS NULL OR next_attempt_at <= CURRENT_TIMESTAMP)
            """,
        ),
        "stale_leases": _safe_scalar(
            conn,
            """
            SELECT COUNT(*) FROM media_fetch_tasks
            WHERE lease_until IS NOT NULL
              AND lease_until < CURRENT_TIMESTAMP
              AND status IN ('fetching','uploading','leased')
            """,
        ),
    }


def _storage_status(config: RuntimeConfig, extension_dir: Path | None) -> dict[str, Any]:
    paths = {
        "config_root": config.config_root,
        "data_root": config.data_root,
        "state_root": config.state_root,
        "clean_text_root": config.clean_text_root,
        "media_root": config.media_root,
    }
    if extension_dir is not None:
        paths["extension_dir"] = extension_dir
    return {name: _disk_usage(path) for name, path in paths.items()}


def _extension_status(extension_dir: Path | None, *, expected_policy_mode: str) -> dict[str, Any]:
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
    token_files = {rel: _extension_file_state(extension_dir / rel, expected_policy_mode=expected_policy_mode) for rel in _EXTENSION_TOKEN_FILES}
    files = {
        "manifest.json": {"exists": manifest_path.exists(), "bytes": _file_size(manifest_path)},
        **{rel: {"exists": (extension_dir / rel).exists(), "bytes": _file_size(extension_dir / rel)} for rel in _EXTENSION_TOKEN_FILES},
    }
    token_configured = all(state.get("api_token_configured") for state in token_files.values())
    policy_modes = {rel: state.get("policy_mode_default") for rel, state in token_files.items()}
    policy_matches = all(mode == expected_policy_mode for mode in policy_modes.values() if mode)
    ok = extension_dir.exists() and manifest_path.exists() and not manifest_error and token_configured and policy_matches
    output: dict[str, Any] = {
        "ok": ok,
        "path": str(extension_dir),
        "exists": extension_dir.exists(),
        "manifest": _select_keys(manifest, ("manifest_version", "name", "version")) if manifest else {},
        "files": files,
        "api_token_configured": token_configured,
        "policy_mode_defaults": policy_modes,
        "expected_policy_mode": expected_policy_mode,
    }
    if manifest_error:
        output["error"] = manifest_error
    missing = [rel for rel, state in files.items() if not state["exists"]]
    if missing:
        output["missing_files"] = missing
    return output


def _extension_file_state(path: Path, *, expected_policy_mode: str) -> dict[str, Any]:
    state: dict[str, Any] = {"exists": path.exists()}
    if not path.exists():
        return state
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        state["error"] = _safe_error(exc)
        return state
    token_matches = re.findall(r"apiToken:\s*(['\"])(.*?)\1", text)
    state["api_token_configured"] = any(value for _quote, value in token_matches)
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
    return {
        "path": str(path),
        "checked_path": str(target),
        "exists": path.exists(),
        "ok": True,
        "total_bytes": usage.total,
        "used_bytes": used,
        "free_bytes": usage.free,
        "used_percent": round((used / usage.total) * 100, 2) if usage.total else None,
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
        restarts = state.get("n_restarts")
        if isinstance(restarts, int) and restarts > 0:
            warnings.append(f"{unit} reports NRestarts={restarts}")


def _score_journals(journals: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    for unit, state in journals.get("units", {}).items():
        if not state.get("ok"):
            warnings.append(f"journalctl check failed for {unit}")
            continue
        if state.get("error_or_higher_count", 0) > 0:
            errors.append(f"{unit} has {state['error_or_higher_count']} journal error-or-higher entries in window")
        elif state.get("warning_or_higher_count", 0) > 0:
            warnings.append(f"{unit} has {state['warning_or_higher_count']} journal warning entries in window")


def _score_database(database: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    if not database.get("ok"):
        errors.append("database integrity/FTS check is not OK")
    media_queue = database.get("media_queue") or {}
    if media_queue.get("stale_leases", 0) > 0:
        errors.append(f"media queue has {media_queue['stale_leases']} stale leases")
    if media_queue.get("due_pending_or_retrying", 0) > 0:
        warnings.append(f"media queue has {media_queue['due_pending_or_retrying']} due pending/retrying tasks")


def _score_storage(storage: dict[str, Any], warnings: list[str]) -> None:
    for name, state in storage.items():
        if not state.get("ok"):
            warnings.append(f"storage path {name} could not be checked")
            continue
        if state.get("free_bytes", 0) < 1_000_000_000:
            warnings.append(f"storage path {name} has less than 1GB free")
        used_percent = state.get("used_percent")
        if isinstance(used_percent, (int, float)) and used_percent >= 95:
            warnings.append(f"storage path {name} is {used_percent}% used")


def _score_extension(extension: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    if not extension.get("exists"):
        errors.append("Windows extension artifact directory is missing")
        return
    if not extension.get("manifest"):
        errors.append("Windows extension manifest is missing or invalid")
    if not extension.get("api_token_configured"):
        errors.append("Windows extension artifact does not have a configured API token default")
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
