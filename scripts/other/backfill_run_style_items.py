# pyright: basic, reportPrivateUsage=false

"""历史 run 的 run_style_items 一次性回填脚本（确定性重放）。

按 run.json 记录的 y_json_path / y_json_sha256 解析当时版本的 Y 资产
（当前文件 hash 不符时从 git 历史找回），重建 y_index → style_key 映射并
幂等 upsert 到 Supabase。参考任务文档：tasks/spec-style-favorites.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

import yaml

if __package__ in {None, ""}:
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

from scripts.r2_upload.postgrest_http import _PostgrestHTTPClient  # noqa: E402
from scripts.r2_upload.supabase_env import (  # noqa: E402
    MissingRequiredEnvError,
    require_env,
)
from scripts.r2_upload.supabase_normalize import extract_rows_from_data  # noqa: E402
from scripts.r2_upload.upload_runtime import (  # noqa: E402
    _autoload_dotenv,
    _resolve_default_run_root,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_STYLE_ITEMS_TABLE = "run_style_items"
UPSERT_BATCH_SIZE = 500
_MISSING_ENV_MESSAGE = "missing required Supabase configuration"


class BackfillError(RuntimeError):
    """单个 run 回填失败；message 只含可公开的固定短原因。"""


class SupabaseResponseLike(Protocol):
    data: object


class SupabaseQueryLike(Protocol):
    def upsert(self, json: object, *, on_conflict: str) -> "SupabaseQueryLike": ...
    def select(self, columns: str) -> "SupabaseQueryLike": ...
    def returning(self, mode: str) -> "SupabaseQueryLike": ...
    def execute(self) -> SupabaseResponseLike: ...


class SupabaseClientLike(Protocol):
    def table(self, table_name: str) -> SupabaseQueryLike: ...


ClientFactory = Callable[[str, str], SupabaseClientLike]
GitLogCommitsFn = Callable[[Path, str], list[str]]
GitShowFileFn = Callable[[Path, str, str], "bytes | None"]


@dataclass(frozen=True, slots=True)
class DbRun:
    run_id: str
    run_dir: str


@dataclass(frozen=True, slots=True)
class RunBackfillPlan:
    run: DbRun
    run_path: Path | None
    action: str  # "backfill" | "skip"
    reason: str


@dataclass(frozen=True, slots=True)
class RunArtifacts:
    y_rel_path: Path
    y_sha256: str
    selection_y_indexes: list[int]
    labels: dict[int, str]
    metadata_y_indexes: set[int]


def _normalize_collection_id(value: str) -> str:
    # 复刻 scripts/generation/prompt_grid.py:_normalize_collection_id
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return normalized.strip("-")


def _resolve_collection_id(payload: Mapping[str, object], source_name: str) -> str:
    # 复刻 scripts/generation/prompt_grid.py:_y_collection_id：
    # 顶层 collection_id 缺失时回退为规范化文件名 stem
    raw_collection_id = payload.get("collection_id")
    if isinstance(raw_collection_id, str):
        normalized = _normalize_collection_id(raw_collection_id)
        if normalized:
            return normalized
    stem = Path(source_name).stem
    return _normalize_collection_id(stem) or "y-prompts"


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _to_repo_relative_path(raw_path: str, *, repo_root: Path) -> Path | None:
    """run.json 记录的是生图机器上的路径；换算为 repo-relative 路径。"""
    path = Path(raw_path)
    if not path.is_absolute():
        return path
    try:
        return path.relative_to(repo_root)
    except ValueError:
        pass
    # 老机器的绝对路径：取最右侧 data/ 锚点及之后的部分
    parts = path.parts
    for index in range(len(parts) - 1, -1, -1):
        if parts[index] == "data":
            return Path(*parts[index:])
    return None


def _git_log_commits(repo_root: Path, rel_path: str) -> list[str]:
    proc = subprocess.run(
        ["git", "log", "--all", "--format=%H", "--", rel_path],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return []
    return [
        line.strip()
        for line in proc.stdout.decode("utf-8").splitlines()
        if line.strip()
    ]


def _git_show_file(repo_root: Path, commit: str, rel_path: str) -> bytes | None:
    proc = subprocess.run(
        ["git", "show", f"{commit}:{rel_path}"],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout


def resolve_y_asset_content(
    *,
    repo_root: Path,
    rel_path: Path,
    expected_sha256: str,
    git_log_commits: GitLogCommitsFn | None = None,
    git_show_file: GitShowFileFn | None = None,
) -> bytes:
    """按 sha256 解析 Y 资产内容：先看当前文件，不符则从 git 历史逐版本找回。"""
    log_fn = git_log_commits or _git_log_commits
    show_fn = git_show_file or _git_show_file

    current_path = repo_root / rel_path
    if current_path.is_file():
        content = current_path.read_bytes()
        if _sha256_bytes(content) == expected_sha256:
            return content

    for commit in log_fn(repo_root, rel_path.as_posix()):
        content = show_fn(repo_root, commit, rel_path.as_posix())
        if content is not None and _sha256_bytes(content) == expected_sha256:
            return content

    raise BackfillError("Y 资产无法按记录的 sha256 解析")


def parse_style_keys_by_y_index(content: bytes, *, source_name: str) -> dict[int, str]:
    """最小解析 Y 资产：items 位置（0-based）→ style_key。

    故意不用 read_y_rows：它硬校验 prompt-y-table/v3，而历史资产是 v2。
    """
    try:
        payload_obj = cast(object, yaml.safe_load(content.decode("utf-8")))
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise BackfillError("Y 资产解析失败") from exc
    if not isinstance(payload_obj, dict):
        raise BackfillError("Y 资产形态错误")
    payload = cast(dict[str, object], payload_obj)

    collection_id = _resolve_collection_id(payload, source_name)
    items_obj = payload.get("items")
    if not isinstance(items_obj, list):
        raise BackfillError("Y 资产形态错误")

    style_keys: dict[int, str] = {}
    for position, item_obj in enumerate(cast(list[object], items_obj)):
        if not isinstance(item_obj, dict):
            continue
        info_obj = cast(dict[str, object], item_obj).get("info")
        if not isinstance(info_obj, dict):
            continue
        item_index = cast(dict[str, object], info_obj).get("index")
        if isinstance(item_index, bool) or not isinstance(item_index, int):
            continue
        style_keys[position] = f"{collection_id}:{item_index}"
    return style_keys


def _require_str_field(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise BackfillError(f"run.json 字段缺失: {key}")
    return value


def _parse_selection_y_indexes(payload: Mapping[str, object]) -> list[int]:
    selection_obj = payload.get("selection")
    if not isinstance(selection_obj, dict):
        raise BackfillError("run.json 字段缺失: selection.y_indexes")
    raw = cast(dict[str, object], selection_obj).get("y_indexes")
    if not isinstance(raw, list):
        raise BackfillError("run.json 字段缺失: selection.y_indexes")
    result: list[int] = []
    for item in cast(list[object], raw):
        if isinstance(item, bool) or not isinstance(item, int):
            raise BackfillError("run.json 字段类型错误: selection.y_indexes")
        result.append(item)
    return result


def _load_metadata_labels(
    metadata_path: Path,
) -> tuple[dict[int, str], set[int]]:
    """读取 metadata.jsonl：y_index 全集 + 每个 y_index 首个非空 y_value。"""
    labels: dict[int, str] = {}
    y_indexes: set[int] = set()
    try:
        raw_lines = metadata_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise BackfillError("metadata.jsonl 读取失败") from exc
    for raw_line in raw_lines:
        line = raw_line.strip()
        if not line:
            continue
        try:
            record_obj = cast(object, json.loads(line))
        except json.JSONDecodeError:
            continue
        if not isinstance(record_obj, dict):
            continue
        record = cast(dict[str, object], record_obj)
        y_index = record.get("y_index")
        if isinstance(y_index, bool) or not isinstance(y_index, int):
            continue
        y_indexes.add(y_index)
        y_value = record.get("y_value")
        if y_index not in labels and isinstance(y_value, str) and y_value.strip():
            labels[y_index] = y_value
    return labels, y_indexes


def load_run_artifacts(run_path: Path, *, repo_root: Path) -> RunArtifacts:
    run_json_path = run_path / "run.json"
    try:
        payload_obj = cast(
            object, json.loads(run_json_path.read_text(encoding="utf-8"))
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise BackfillError("run.json 读取失败") from exc
    if not isinstance(payload_obj, dict):
        raise BackfillError("run.json 形态错误")
    payload = cast(dict[str, object], payload_obj)

    y_json_path = _require_str_field(payload, "y_json_path")
    y_sha256 = _require_str_field(payload, "y_json_sha256")
    selection_y_indexes = _parse_selection_y_indexes(payload)

    y_rel_path = _to_repo_relative_path(y_json_path, repo_root=repo_root)
    if y_rel_path is None:
        raise BackfillError("run.json 的 y_json_path 无法定位")

    labels, metadata_y_indexes = _load_metadata_labels(run_path / "metadata.jsonl")
    return RunArtifacts(
        y_rel_path=y_rel_path,
        y_sha256=y_sha256,
        selection_y_indexes=selection_y_indexes,
        labels=labels,
        metadata_y_indexes=metadata_y_indexes,
    )


def build_style_item_rows(
    *,
    run: DbRun,
    style_keys: Mapping[int, str],
    artifacts: RunArtifacts,
) -> list[dict[str, object]]:
    if artifacts.metadata_y_indexes != set(artifacts.selection_y_indexes):
        raise BackfillError("metadata 与 selection 的 y_index 集合不一致")
    rows: list[dict[str, object]] = []
    for y_index in artifacts.selection_y_indexes:
        style_key = style_keys.get(y_index)
        if style_key is None:
            raise BackfillError("Y 资产条目缺少 info.index")
        label = artifacts.labels.get(y_index)
        if label is None:
            raise BackfillError("metadata 缺少 y_value")
        rows.append(
            {
                "run_id": run.run_id,
                "run_dir": run.run_dir,
                "style_key": style_key,
                "y_index": y_index,
                "label": label,
            }
        )
    return rows


def list_db_runs(client: SupabaseClientLike) -> list[DbRun]:
    data = client.table("runs").select("id,run_dir").execute().data
    runs: list[DbRun] = []
    for row in extract_rows_from_data(data):
        run_id = row.get("id")
        run_dir = row.get("run_dir")
        if not isinstance(run_id, str) or not run_id.strip():
            continue
        if not isinstance(run_dir, str) or not run_dir.strip():
            continue
        runs.append(DbRun(run_id=run_id, run_dir=run_dir))
    runs.sort(key=lambda run: run.run_dir)
    return runs


def upsert_run_style_items(
    client: SupabaseClientLike, rows: list[dict[str, object]]
) -> None:
    for start in range(0, len(rows), UPSERT_BATCH_SIZE):
        chunk = rows[start : start + UPSERT_BATCH_SIZE]
        _ = (
            client.table(RUN_STYLE_ITEMS_TABLE)
            .upsert(chunk, on_conflict="run_id,style_key")
            .returning("minimal")
            .execute()
        )


def build_backfill_plans(
    db_runs: Sequence[DbRun], *, run_root: Path
) -> list[RunBackfillPlan]:
    """pre-flight 覆盖矩阵：DB run × 本地 outputs 精确匹配（`_old` 目录不参与）。"""
    plans: list[RunBackfillPlan] = []
    for run in db_runs:
        run_path = run_root / run.run_dir
        if not run_path.is_dir():
            plans.append(
                RunBackfillPlan(
                    run=run,
                    run_path=None,
                    action="skip",
                    reason="本地无产物目录",
                )
            )
            continue
        if not (run_path / "run.json").is_file() or not (
            run_path / "metadata.jsonl"
        ).is_file():
            plans.append(
                RunBackfillPlan(
                    run=run,
                    run_path=run_path,
                    action="skip",
                    reason="产物缺少 run.json 或 metadata.jsonl",
                )
            )
            continue
        plans.append(
            RunBackfillPlan(run=run, run_path=run_path, action="backfill", reason="")
        )
    return plans


def backfill_run(
    plan: RunBackfillPlan,
    *,
    client: SupabaseClientLike | None,
    repo_root: Path,
    dry_run: bool,
    git_log_commits: GitLogCommitsFn | None = None,
    git_show_file: GitShowFileFn | None = None,
) -> int:
    """回填单个 run，返回写入（或计划写入）行数。"""
    if plan.run_path is None:
        raise BackfillError("本地无产物目录")
    artifacts = load_run_artifacts(plan.run_path, repo_root=repo_root)
    content = resolve_y_asset_content(
        repo_root=repo_root,
        rel_path=artifacts.y_rel_path,
        expected_sha256=artifacts.y_sha256,
        git_log_commits=git_log_commits,
        git_show_file=git_show_file,
    )
    style_keys = parse_style_keys_by_y_index(
        content, source_name=artifacts.y_rel_path.as_posix()
    )
    rows = build_style_item_rows(
        run=plan.run, style_keys=style_keys, artifacts=artifacts
    )
    if not dry_run:
        if client is None:
            raise BackfillError("supabase client is not initialized")
        try:
            upsert_run_style_items(client, rows)
        except Exception as exc:
            raise BackfillError("run_style_items 写入失败") from exc
    return len(rows)


def _default_client_factory(
    supabase_url: str, service_role_key: str
) -> SupabaseClientLike:
    client = _PostgrestHTTPClient(supabase_url, service_role_key)
    return cast(SupabaseClientLike, cast(object, client))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="历史 run 的 run_style_items 确定性回填。"
    )
    _ = parser.add_argument(
        "--run-root",
        default=_resolve_default_run_root(),
        help="Root directory containing run folders.",
    )
    _ = parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印计划，不写库。",
    )
    return parser


def main(
    argv: list[str] | None = None,
    *,
    client_factory: ClientFactory | None = None,
    repo_root: Path | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    _autoload_dotenv()
    resolved_repo_root = repo_root or REPO_ROOT

    try:
        supabase_url = require_env("SUPABASE_URL")
        service_role_key = require_env("SUPABASE_SERVICE_ROLE_KEY")
    except MissingRequiredEnvError:
        print(_MISSING_ENV_MESSAGE, file=sys.stderr)
        return 1
    factory = client_factory or _default_client_factory
    try:
        client = factory(supabase_url, service_role_key)
    except Exception:
        print("failed to initialize supabase client", file=sys.stderr)
        return 1

    try:
        db_runs = list_db_runs(client)
    except Exception:
        print("failed to list runs", file=sys.stderr)
        return 1

    run_root = Path(cast(str, args.run_root))
    plans = build_backfill_plans(db_runs, run_root=run_root)

    backfill_count = sum(1 for plan in plans if plan.action == "backfill")
    print(f"DB runs: {len(plans)}，可回填: {backfill_count}")
    for plan in plans:
        if plan.action == "backfill":
            print(f"  {plan.run.run_dir}: 回填")
        else:
            print(f"  {plan.run.run_dir}: 跳过（{plan.reason}）")

    failed = 0
    for plan in plans:
        if plan.action != "backfill":
            continue
        try:
            row_count = backfill_run(
                plan,
                client=client,
                repo_root=resolved_repo_root,
                dry_run=bool(args.dry_run),
            )
        except BackfillError as exc:
            failed += 1
            print(f"  {plan.run.run_dir}: 失败（{exc}）")
        except Exception:
            failed += 1
            print(f"  {plan.run.run_dir}: 失败（未预期错误）")
        else:
            verb = "计划写入" if args.dry_run else "已写入"
            print(f"  {plan.run.run_dir}: {verb} {row_count} 行")

    if failed:
        print(f"完成，{failed} 个 run 失败")
        return 1
    print("完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
