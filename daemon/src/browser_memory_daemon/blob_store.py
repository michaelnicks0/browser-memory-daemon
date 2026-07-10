from __future__ import annotations

import hashlib
import os
import uuid
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, cast

from .storage_paths import StoragePathResolution, contained_child_path, resolve_db_path_under


def prefer_relative_locator(relative_locator: str | None, legacy_path: str | None) -> str | None:
    return relative_locator if relative_locator not in {None, ""} else legacy_path


class BlobStoreError(RuntimeError):
    """Raised when a contained blob operation cannot be completed safely."""


@dataclass(frozen=True)
class StagedBlob:
    path: Path
    root: Path
    byte_size: int
    sha256: str


@dataclass(frozen=True)
class BlobDeleteResult:
    status: str
    path: Path | None = None

    @property
    def deleted(self) -> bool:
        return self.status == "deleted"


def _chunks(source: bytes | bytearray | memoryview | BinaryIO | Iterable[bytes]) -> Iterator[bytes]:
    if isinstance(source, (bytes, bytearray, memoryview)):
        yield bytes(source)
        return
    read = getattr(source, "read", None)
    if callable(read):
        while True:
            chunk = read(1024 * 1024)
            if not chunk:
                return
            if not isinstance(chunk, (bytes, bytearray, memoryview)):
                raise BlobStoreError("blob stream must yield bytes")
            yield bytes(chunk)
    else:
        for chunk in source:
            if not isinstance(chunk, (bytes, bytearray, memoryview)):
                raise BlobStoreError("blob stream must yield bytes")
            yield bytes(chunk)


class BlobStore:
    """Contained filesystem boundary for one configured blob root."""

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve(strict=False)

    def path(self, *parts: str, create_root: bool = False) -> Path:
        return contained_child_path(self.root, *parts, create_root=create_root)

    def resolve(self, locator: str | Path | None, *, require_file: bool = False) -> StoragePathResolution:
        return resolve_db_path_under(self.root, locator, require_file=require_file)

    def relative_locator(self, locator: str | Path) -> str:
        path = self._required_path(locator)
        relative = path.relative_to(self.root)
        if not relative.parts:
            raise BlobStoreError("blob locator cannot name the storage root")
        return relative.as_posix()

    def _required_path(self, locator: str | Path, *, require_file: bool = False) -> Path:
        resolution = self.resolve(locator, require_file=require_file)
        if resolution.status != "ok" or resolution.path is None:
            raise BlobStoreError(f"blob locator is not usable: {resolution.status}")
        return resolution.path

    def stage(
        self,
        source: bytes | bytearray | memoryview | BinaryIO | Iterable[bytes],
        *,
        expected_size: int | None = None,
        expected_sha256: str | None = None,
    ) -> StagedBlob:
        if expected_size is not None and expected_size < 0:
            raise ValueError("expected_size must be >= 0")
        expected_hash = str(expected_sha256 or "").strip().lower() or None
        if expected_hash is not None and (len(expected_hash) != 64 or any(char not in "0123456789abcdef" for char in expected_hash)):
            raise ValueError("expected_sha256 must be lowercase hexadecimal SHA-256")
        staging_dir = self.path(".staging", create_root=True)
        staging_dir.mkdir(parents=True, exist_ok=True)
        stage_path = self.path(".staging", f"stage_{uuid.uuid4().hex}.tmp")
        digest = hashlib.sha256()
        byte_size = 0
        try:
            with stage_path.open("xb") as handle:
                for chunk in _chunks(source):
                    handle.write(chunk)
                    digest.update(chunk)
                    byte_size += len(chunk)
                handle.flush()
                os.fsync(handle.fileno())
            actual_hash = digest.hexdigest()
            if expected_size is not None and byte_size != expected_size:
                raise BlobStoreError(f"staged blob size mismatch: expected {expected_size}, got {byte_size}")
            if expected_hash is not None and actual_hash != expected_hash:
                raise BlobStoreError("staged blob SHA-256 mismatch")
            return StagedBlob(stage_path, self.root, byte_size, actual_hash)
        except Exception:
            try:
                stage_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    def abort(self, staged: StagedBlob) -> None:
        stage_path = self._validated_stage(staged)
        try:
            stage_path.unlink(missing_ok=True)
        except OSError as exc:
            raise BlobStoreError(f"failed to remove staged blob: {exc}") from exc

    def _validated_stage(self, staged: StagedBlob) -> Path:
        if staged.root != self.root:
            raise BlobStoreError("staged blob belongs to a different root")
        resolution = self.resolve(staged.path, require_file=True)
        stage_path = resolution.path
        if resolution.status != "ok" or stage_path is None:
            raise BlobStoreError(f"staged blob is not usable: {resolution.status}")
        staging_root = self.path(".staging")
        try:
            stage_path.relative_to(staging_root)
        except ValueError as exc:
            raise BlobStoreError("staged blob is outside the staging directory") from exc
        return stage_path

    def commit(self, staged: StagedBlob, locator: str | Path) -> Path:
        stage_path = self._validated_stage(staged)
        target = self._required_path(locator)
        target.parent.mkdir(parents=True, exist_ok=True)
        target_parent = target.parent.resolve(strict=False)
        try:
            target_parent.relative_to(self.root)
        except ValueError as exc:
            raise BlobStoreError("blob target parent escapes configured root") from exc
        try:
            os.replace(stage_path, target)
            directory_fd = os.open(target_parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError as exc:
            raise BlobStoreError(f"failed to commit staged blob: {exc}") from exc
        return target

    def write(
        self,
        locator: str | Path,
        source: bytes | bytearray | memoryview | BinaryIO | Iterable[bytes],
        *,
        expected_size: int | None = None,
        expected_sha256: str | None = None,
    ) -> Path:
        staged = self.stage(source, expected_size=expected_size, expected_sha256=expected_sha256)
        try:
            return self.commit(staged, locator)
        except Exception:
            try:
                self.abort(staged)
            except BlobStoreError:
                pass
            raise

    def write_bytes(
        self,
        locator: str | Path,
        content: bytes,
        *,
        expected_sha256: str | None = None,
    ) -> Path:
        return self.write(locator, content, expected_size=len(content), expected_sha256=expected_sha256)

    def write_text(self, locator: str | Path, text: str, *, encoding: str = "utf-8") -> Path:
        return self.write_bytes(locator, text.encode(encoding))

    def open(self, locator: str | Path, mode: str = "rb") -> BinaryIO:
        if mode != "rb":
            raise ValueError("BlobStore.open supports binary read-only mode")
        path = self._required_path(locator, require_file=True)
        return cast(BinaryIO, path.open(mode))

    def read_bytes(self, locator: str | Path) -> bytes:
        with self.open(locator, "rb") as handle:
            return handle.read()

    def read_text(self, locator: str | Path, *, encoding: str = "utf-8", errors: str = "strict") -> str:
        return self.read_bytes(locator).decode(encoding, errors=errors)

    def stat(self, locator: str | Path) -> os.stat_result:
        path = self._required_path(locator, require_file=True)
        try:
            return path.stat()
        except OSError as exc:
            raise BlobStoreError(f"failed to stat blob: {exc}") from exc

    def delete(self, locator: str | Path | None) -> BlobDeleteResult:
        resolution = self.resolve(locator, require_file=False)
        path = resolution.path
        if resolution.status in {"empty", "invalid", "outside-root"} or path is None:
            return BlobDeleteResult(resolution.status, path)
        try:
            if not path.exists():
                return BlobDeleteResult("missing", path)
            if not path.is_file():
                return BlobDeleteResult("not-file", path)
            path.unlink()
            return BlobDeleteResult("deleted", path)
        except OSError:
            return BlobDeleteResult("error", path)

    def exists(self, locator: str | Path | None) -> bool:
        return self.resolve(locator, require_file=True).status == "ok"

    def staged_paths(self) -> list[Path]:
        staging = self.path(".staging")
        if not staging.is_dir():
            return []
        return sorted(path for path in staging.iterdir() if path.is_file())
