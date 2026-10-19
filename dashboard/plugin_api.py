"""Read-only, metadata-only API for Hermes pending write approvals."""

from __future__ import annotations

import json
import logging
import math
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter()
_log = logging.getLogger(__name__)
_SUBSYSTEMS = ("memory", "skills")
_ALLOWLIST = frozenset({"profile", "subsystem", "id", "action", "origin", "created_at", "age_seconds"})
_MAX_FILE_BYTES = 1_048_576
_MAX_ITEMS = 1_000
_MAX_FIELD_LENGTH = 256
_FIELD_RE = re.compile(r"^[^\x00-\x1f\x7f]*$")


def _default_root() -> Path:
    from hermes_constants import get_default_hermes_root

    return Path(get_default_hermes_root()).resolve()


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _regular_dir(path: Path, root: Path) -> bool:
    try:
        if path.is_symlink() or not stat.S_ISDIR(path.lstat().st_mode):
            return False
        return _inside(path.resolve(), root)
    except OSError:
        return False


def _regular_file(path: Path, profile_home: Path) -> bool:
    try:
        if path.is_symlink() or not stat.S_ISREG(path.lstat().st_mode):
            return False
        return _inside(path.resolve(), profile_home)
    except OSError:
        return False


def _profile_homes(root: Path) -> list[tuple[str, Path]]:
    homes: list[tuple[str, Path]] = [("default", root)]
    profiles = root / "profiles"
    if not _regular_dir(profiles, root):
        return homes
    try:
        with os.scandir(profiles) as scan:
            children = sorted((Path(entry.path) for entry in scan), key=lambda item: item.name)
    except OSError:
        return homes
    for child in children:
        if not _regular_dir(child, root):
            continue
        config = child / "config.yaml"
        if _regular_file(config, child):
            homes.append((child.name, child))
    return homes


def _parse_created_at(value: Any) -> tuple[str, float] | None:
    try:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            timestamp = float(value)
            if not math.isfinite(timestamp):
                return None
            instant = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        elif isinstance(value, str):
            raw = value.strip()
            if not raw:
                return None
            instant = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if instant.tzinfo is None:
                instant = instant.replace(tzinfo=timezone.utc)
            instant = instant.astimezone(timezone.utc)
            timestamp = instant.timestamp()
        else:
            return None
        return instant.isoformat().replace("+00:00", "Z"), timestamp
    except (OverflowError, TypeError, ValueError):
        return None


def _valid_field(value: Any, *, required: bool) -> bool:
    return (
        isinstance(value, str)
        and (bool(value) or not required)
        and len(value) <= _MAX_FIELD_LENGTH
        and _FIELD_RE.fullmatch(value) is not None
    )


def _read_item(path: Path, profile: str, profile_home: Path, subsystem: str, now: float) -> dict[str, Any] | None:
    fd: int | None = None
    try:
        if not _inside(path.parent.resolve(), profile_home):
            return None
        no_follow = getattr(os, "O_NOFOLLOW", None)
        if no_follow is None:
            # Never read pending records on platforms that cannot guarantee the
            # final path component is not a symlink (for example, Windows).
            return None
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | no_follow
        fd = os.open(path, flags)
        file_stat = os.fstat(fd)
        if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_nlink != 1:
            return None
        if file_stat.st_size > _MAX_FILE_BYTES:
            return None
        with os.fdopen(fd, "rb") as stream:
            fd = None
            raw = stream.read(_MAX_FILE_BYTES + 1)
        if len(raw) > _MAX_FILE_BYTES:
            return None
        record = json.loads(raw.decode("utf-8-sig"))
        if not isinstance(record, dict) or not _valid_field(record.get("id"), required=True):
            return None
        if not _valid_field(record.get("action", ""), required=False):
            return None
        if not _valid_field(record.get("origin", ""), required=False):
            return None
        parsed = _parse_created_at(record.get("created_at"))
        if parsed is None:
            return None
        created_at, created_timestamp = parsed
        age_seconds = max(0, int(now - created_timestamp))
        item = {
            "profile": profile,
            "subsystem": subsystem,
            "id": record["id"],
            "action": record.get("action") if isinstance(record.get("action"), str) else "",
            "origin": record.get("origin") if isinstance(record.get("origin"), str) else "",
            "created_at": created_at,
            "age_seconds": age_seconds,
        }
        return {key: item[key] for key in _ALLOWLIST}
    except (OSError, UnicodeError, TypeError, ValueError, json.JSONDecodeError, RecursionError):
        return None
    finally:
        if fd is not None:
            os.close(fd)


def _scan_profile(profile: str, home: Path, now: float, remaining: int) -> tuple[list[dict[str, Any]], int, bool]:
    items: list[dict[str, Any]] = []
    skipped = 0
    truncated = False
    for subsystem in _SUBSYSTEMS:
        directory = home / "pending" / subsystem
        if not _regular_dir(directory, home):
            continue
        try:
            with os.scandir(directory) as scan:
                candidates = sorted((entry for entry in scan), key=lambda entry: entry.name)
                for entry in candidates:
                    path = Path(entry.path)
                    if path.suffix != ".json":
                        continue
                    item = _read_item(path, profile, home, subsystem, now)
                    if item is None:
                        skipped += 1
                    elif len(items) < remaining:
                        items.append(item)
                    else:
                        truncated = True
        except OSError:
            continue
    return items, skipped, truncated


def build_overview(*, root: Path | None = None, now: float | None = None) -> dict[str, Any]:
    resolved_root = (root or _default_root()).resolve()
    timestamp = datetime.now(tz=timezone.utc).timestamp() if now is None else float(now)
    items: list[dict[str, Any]] = []
    skipped = 0
    truncated = False
    profiles: list[dict[str, Any]] = []
    for profile, home in _profile_homes(resolved_root):
        profile_items, profile_skipped, profile_truncated = _scan_profile(
            profile, home, timestamp, max(0, _MAX_ITEMS - len(items))
        )
        items.extend(profile_items)
        skipped += profile_skipped
        truncated = truncated or profile_truncated
        memory_count = sum(item["subsystem"] == "memory" for item in profile_items)
        skills_count = sum(item["subsystem"] == "skills" for item in profile_items)
        ages = [item["age_seconds"] for item in profile_items]
        profiles.append({
            "profile": profile,
            "pending_memory": memory_count,
            "pending_skills": skills_count,
            "total": len(profile_items),
            "oldest_age_seconds": max(ages) if ages else None,
        })
    items.sort(key=lambda item: (item["age_seconds"] * -1, item["profile"], item["id"]))
    ages = [item["age_seconds"] for item in items]
    buckets = (
        ("<1h", lambda age: age < 3600),
        ("1-6h", lambda age: 3600 <= age < 21600),
        ("6-24h", lambda age: 21600 <= age < 86400),
        ("1-7d", lambda age: 86400 <= age < 604800),
        ("7d+", lambda age: age >= 604800),
    )
    return {
        "profiles": profiles,
        "totals": {
            "pending_memory": sum(item["subsystem"] == "memory" for item in items),
            "pending_skills": sum(item["subsystem"] == "skills" for item in items),
            "total": len(items),
            "oldest_age_seconds": max(ages) if ages else None,
        },
        "age_buckets": [{"label": label, "count": sum(test(age) for age in ages)} for label, test in buckets],
        "items": items,
        "skipped": skipped,
        "truncated": truncated,
    }


@router.get("/overview")
def get_overview() -> dict[str, Any]:
    try:
        return build_overview()
    except Exception:
        _log.exception("pending queue monitor scan failed")
        raise HTTPException(status_code=500, detail="Pending queue monitor scan failed")
