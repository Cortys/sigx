"""basedpyright-backed baseline stub generation helpers."""

from __future__ import annotations

from collections.abc import Iterable
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def generate_baseline_stubs(
    *,
    src_root: Path,
    out_root: Path,
    module_targets: Iterable[tuple[str, Path]],
) -> None:
    """Generate baseline stubs using basedpyright.

    Args:
        src_root: Source root to place on ``PYTHONPATH``.
        out_root: Stub output root.
        module_targets: Module names paired with expected stub file paths.

    Raises:
        RuntimeError: If basedpyright is unavailable or generation fails.
    """
    target_stub_paths = {module_name: stub_path for module_name, stub_path in module_targets if module_name}
    if not target_stub_paths:
        return
    required_package_stub_paths = _required_package_stub_paths(
        src_root=src_root,
        out_root=out_root,
        module_names=target_stub_paths,
    )
    expected_stub_paths = {**required_package_stub_paths, **target_stub_paths}

    out_root.mkdir(parents=True, exist_ok=True)

    cache_root = src_root.parent / ".sigx_cache" / "basedpyright"
    cache_state = _load_cache_state(cache_root=cache_root)
    source_hashes: dict[str, str] = {}
    source_paths = _target_source_paths(src_root=src_root, target_names=expected_stub_paths)
    restored_count = _restore_cached_stubs(
        cache_state=cache_state,
        expected_stub_paths=expected_stub_paths,
        source_paths=source_paths,
        source_hashes=source_hashes,
        src_root=src_root,
        out_root=out_root,
        cache_root=cache_root,
    )

    missing_targets = tuple(
        module_name for module_name, stub_path in expected_stub_paths.items() if not stub_path.exists()
    )
    if missing_targets:
        _generate_missing_stubs(
            src_root=src_root,
            out_root=out_root,
            expected_stub_paths=expected_stub_paths,
            missing_targets=missing_targets,
            restored_count=restored_count,
        )

    _verify_expected_stubs(expected_stub_paths=expected_stub_paths)
    _update_cache(
        cache_root=cache_root,
        cache_state=cache_state,
        expected_stub_paths=expected_stub_paths,
        source_paths=source_paths,
        source_hashes=source_hashes,
        src_root=src_root,
        out_root=out_root,
    )


def _generate_missing_stubs(
    *,
    src_root: Path,
    out_root: Path,
    expected_stub_paths: dict[str, Path],
    missing_targets: tuple[str, ...],
    restored_count: int,
) -> None:
    attempted_targets: set[str] = set()

    with tempfile.TemporaryDirectory(prefix="sigx-gen-basedpyright-") as temp_dir:
        project_file = Path(temp_dir) / "pyrightconfig.json"
        _write_project_config(project_file=project_file, src_root=src_root, out_root=out_root)

        if restored_count == 0:
            primary_targets = sorted({module_name.split(".")[0] for module_name in missing_targets})
        else:
            primary_targets = sorted(missing_targets, key=lambda module_name: (module_name.count("."), module_name))

        for target in primary_targets:
            _run_basedpyright_command(
                command=_basedpyright_command(package=target, project_file=project_file),
                source_label=target,
                src_root=src_root,
            )
            attempted_targets.add(target)

        still_missing_targets = sorted(
            module_name
            for module_name, stub_path in expected_stub_paths.items()
            if not stub_path.exists() and module_name not in attempted_targets
        )
        for module_name in still_missing_targets:
            _run_basedpyright_command(
                command=_basedpyright_command(package=module_name, project_file=project_file),
                source_label=module_name,
                src_root=src_root,
            )


def _verify_expected_stubs(*, expected_stub_paths: dict[str, Path]) -> None:
    still_missing = sorted(
        f"{module_name} -> {stub_path}"
        for module_name, stub_path in expected_stub_paths.items()
        if not stub_path.exists()
    )
    if still_missing:
        missing_report = ", ".join(still_missing)
        raise RuntimeError(f"basedpyright did not generate required module stubs: {missing_report}")


def _required_package_stub_paths(
    *,
    src_root: Path,
    out_root: Path,
    module_names: Iterable[str],
) -> dict[str, Path]:
    required: dict[str, Path] = {}
    for module_name in module_names:
        parts = module_name.split(".")
        for index in range(1, len(parts)):
            package_parts = parts[:index]
            package_init = src_root.joinpath(*package_parts, "__init__.py")
            if not package_init.exists():
                continue
            package_name = ".".join(package_parts)
            required[package_name] = out_root.joinpath(*package_parts, "__init__.pyi")
    return required


_CACHE_SCHEMA_VERSION = 1


def _target_source_paths(*, src_root: Path, target_names: Iterable[str]) -> dict[str, Path]:
    source_paths: dict[str, Path] = {}
    for target_name in target_names:
        package_path = src_root.joinpath(*target_name.split("."), "__init__.py")
        module_path = src_root.joinpath(*target_name.split(".")).with_suffix(".py")
        if package_path.exists():
            source_paths[target_name] = package_path
            continue
        if module_path.exists():
            source_paths[target_name] = module_path
    return source_paths


def _load_cache_state(*, cache_root: Path) -> dict[str, object]:
    manifest_path = cache_root / "manifest.json"
    default_state = {
        "environment": _cache_environment(),
        "entries": {},
        "source_hash_index": {},
    }
    state: dict[str, object] = dict(default_state)
    if not manifest_path.exists():
        return state

    try:
        raw_state = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return state

    if not isinstance(raw_state, dict):
        return state
    if raw_state.get("schema_version") != _CACHE_SCHEMA_VERSION:
        return state

    entries = raw_state.get("entries")
    source_hash_index = raw_state.get("source_hash_index")
    if not isinstance(entries, dict) or not isinstance(source_hash_index, dict):
        return state

    current_environment = _cache_environment()
    state["environment"] = current_environment
    state["source_hash_index"] = source_hash_index

    cached_environment = raw_state.get("environment")
    if isinstance(cached_environment, dict) and cached_environment == current_environment:
        state["entries"] = entries

    return state


def _cache_environment() -> dict[str, str]:
    return {
        "basedpyright_version": _basedpyright_version(),
        "python_version": sys.version.split(" ", maxsplit=1)[0],
        "platform": sys.platform,
    }


def _basedpyright_version() -> str:
    try:
        return importlib.metadata.version("basedpyright")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _restore_cached_stubs(
    *,
    cache_state: dict[str, object],
    expected_stub_paths: dict[str, Path],
    source_paths: dict[str, Path],
    source_hashes: dict[str, str],
    src_root: Path,
    out_root: Path,
    cache_root: Path,
) -> int:
    entries = cache_state.get("entries")
    if not isinstance(entries, dict):
        return 0

    restored_count = 0
    for target_name, stub_path in expected_stub_paths.items():
        source_path = source_paths.get(target_name)
        if source_path is None:
            continue
        entry = entries.get(target_name)
        if not isinstance(entry, dict):
            continue
        source_hash = _source_hash(source_path=source_path, src_root=src_root, cache_state=cache_state)
        source_hashes[target_name] = source_hash

        expected_stub_rel = _as_posix(stub_path.relative_to(out_root))
        expected_source_rel = _as_posix(source_path.relative_to(src_root))
        if entry.get("stub_rel_path") != expected_stub_rel:
            continue
        if entry.get("source_rel_path") != expected_source_rel:
            continue
        if entry.get("source_sha256") != source_hash:
            continue

        cached_rel_path_raw = entry.get("cache_stub_rel_path")
        if not isinstance(cached_rel_path_raw, str):
            continue
        cached_rel_path = Path(cached_rel_path_raw)
        if cached_rel_path.is_absolute() or ".." in cached_rel_path.parts:
            continue

        cached_stub_path = cache_root / "stubs" / cached_rel_path
        if not cached_stub_path.exists() or not cached_stub_path.is_file():
            continue

        stub_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cached_stub_path, stub_path)
        restored_count += 1

    return restored_count


def _update_cache(
    *,
    cache_root: Path,
    cache_state: dict[str, object],
    expected_stub_paths: dict[str, Path],
    source_paths: dict[str, Path],
    source_hashes: dict[str, str],
    src_root: Path,
    out_root: Path,
) -> None:
    entries = cache_state.get("entries")
    if not isinstance(entries, dict):
        entries = {}

    stubs_root = cache_root / "stubs"
    stubs_root.mkdir(parents=True, exist_ok=True)

    for target_name, stub_path in expected_stub_paths.items():
        if not stub_path.exists() or not stub_path.is_file():
            continue
        source_path = source_paths.get(target_name)
        if source_path is None:
            continue

        source_hash = source_hashes.get(target_name)
        if source_hash is None:
            source_hash = _source_hash(source_path=source_path, src_root=src_root, cache_state=cache_state)

        stub_rel = stub_path.relative_to(out_root)
        cache_stub_path = stubs_root / stub_rel
        cache_stub_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(stub_path, cache_stub_path)

        entries[target_name] = {
            "stub_rel_path": _as_posix(stub_rel),
            "cache_stub_rel_path": _as_posix(stub_rel),
            "source_rel_path": _as_posix(source_path.relative_to(src_root)),
            "source_sha256": source_hash,
        }

    cache_state["entries"] = entries
    manifest_payload = {
        "schema_version": _CACHE_SCHEMA_VERSION,
        "environment": cache_state.get("environment", _cache_environment()),
        "entries": entries,
        "source_hash_index": cache_state.get("source_hash_index", {}),
    }
    _write_json_atomic(path=cache_root / "manifest.json", data=manifest_payload)


def _source_hash(*, source_path: Path, src_root: Path, cache_state: dict[str, object]) -> str:
    index = cache_state.get("source_hash_index")
    if not isinstance(index, dict):
        index = {}
        cache_state["source_hash_index"] = index

    rel_key = _as_posix(source_path.relative_to(src_root))
    try:
        stat_result = source_path.stat()
    except OSError:
        return ""

    digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
    index[rel_key] = {
        "size": stat_result.st_size,
        "mtime_ns": stat_result.st_mtime_ns,
        "ctime_ns": stat_result.st_ctime_ns,
        "sha256": digest,
    }
    return digest


def _write_json_atomic(*, path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
    temp_path.replace(path)


def _as_posix(path: Path) -> str:
    return path.as_posix()


def _basedpyright_command(*, package: str, project_file: Path) -> list[str]:
    if shutil.which("basedpyright") is not None:
        return ["basedpyright", "--project", str(project_file), "--createstub", package]
    return [sys.executable, "-m", "basedpyright", "--project", str(project_file), "--createstub", package]


def _write_project_config(*, project_file: Path, src_root: Path, out_root: Path) -> None:
    config = {
        "include": [str(src_root)],
        "stubPath": str(out_root),
        "executionEnvironments": [
            {
                "root": str(src_root),
                "extraPaths": [str(src_root)],
            }
        ],
    }
    project_file.write_text(json.dumps(config), encoding="utf-8")


def _run_basedpyright_command(*, command: list[str], source_label: str, src_root: Path) -> None:
    try:
        result = subprocess.run(  # noqa: S603
            command,
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": str(src_root)},
        )
    except FileNotFoundError as exc:
        raise RuntimeError("basedpyright is not installed. Install it with 'pip install basedpyright'.") from exc
    if result.returncode != 0:
        raise RuntimeError(
            f"basedpyright stub generation failed for '{source_label}': {(result.stderr or result.stdout).strip()}"
        )
