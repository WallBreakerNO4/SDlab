# pyright: basic, reportMissingImports=false

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.other.backfill_run_style_items import (
    BackfillError,
    DbRun,
    RunBackfillPlan,
    _to_repo_relative_path,
    backfill_run,
    build_backfill_plans,
    main,
    parse_style_keys_by_y_index,
    resolve_y_asset_content,
)


def _yaml_bytes(
    indexes: list[int],
    *,
    schema: str,
    collection_id: str | None = None,
    with_info_type: bool = False,
) -> bytes:
    payload: dict[str, object] = {"schema": schema}
    if collection_id is not None:
        payload["collection_id"] = collection_id
    items: list[dict[str, object]] = []
    for index in indexes:
        info: dict[str, object] = {"index": index}
        if with_info_type:
            # v2 资产的 info.type 字段；最小解析应直接忽略
            info["type"] = "artists"
        items.append(
            {
                "tags": [{"text": f"artist {index}", "weight": 1.0}],
                "info": info,
            }
        )
    payload["items"] = items
    return yaml.dump(payload, allow_unicode=True, sort_keys=False).encode("utf-8")


def _metadata_records(y_indexes: list[int]) -> list[dict[str, object]]:
    return [
        {
            "status": "success",
            "x_index": 0,
            "y_index": y_index,
            "y_value": f"label-{y_index}",
        }
        for y_index in y_indexes
    ]


def _write_run_dir(
    run_root: Path,
    run_dir: str,
    *,
    y_indexes: list[int],
    metadata_records: list[dict[str, object]],
    y_json_path: str,
    y_json_sha256: str,
) -> Path:
    run_path = run_root / run_dir
    run_path.mkdir(parents=True)
    run_json = {
        "run_id": run_dir,
        "run_dir": run_dir,
        "y_json_path": y_json_path,
        "y_json_sha256": y_json_sha256,
        "selection": {"x_indexes": [0], "y_indexes": y_indexes},
    }
    (run_path / "run.json").write_text(
        json.dumps(run_json, ensure_ascii=False), encoding="utf-8"
    )
    lines = [json.dumps(record, ensure_ascii=False) for record in metadata_records]
    (run_path / "metadata.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return run_path


def _write_y_asset(repo_root: Path, rel_path: Path, content: bytes) -> None:
    asset_path = repo_root / rel_path
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    asset_path.write_bytes(content)


def _stub_git_log(commits: list[str]) -> Callable[[Path, str], list[str]]:
    def _fn(repo_root: Path, rel_path: str) -> list[str]:
        return list(commits)

    return _fn


def _stub_git_show(
    contents: dict[str, bytes],
) -> Callable[[Path, str, str], bytes | None]:
    def _fn(repo_root: Path, commit: str, rel_path: str) -> bytes | None:
        return contents.get(commit)

    return _fn


def _fail_git_log(repo_root: Path, rel_path: str) -> list[str]:
    raise AssertionError("当前文件 hash 匹配时不应查询 git 历史")


class _FakeResponse:
    def __init__(self, data: object) -> None:
        self.data = data


class _FakeSupabaseClient:
    """只实现本脚本用到的 runs select + run_style_items upsert。"""

    def __init__(self, *, runs: list[dict[str, object]]) -> None:
        self._runs = runs
        self._style_items: dict[tuple[object, object], dict[str, object]] = {}
        self.upsert_calls: list[dict[str, object]] = []

    def table(self, table_name: str) -> "_FakeQuery":
        return _FakeQuery(self, table_name)

    def style_item_rows(self) -> list[dict[str, object]]:
        return [dict(row) for row in self._style_items.values()]


class _FakeQuery:
    def __init__(self, client: _FakeSupabaseClient, table_name: str) -> None:
        self._client = client
        self._table_name = table_name
        self._mode: str | None = None
        self._rows: list[dict[str, object]] = []
        self._on_conflict = ""

    def select(self, columns: str) -> "_FakeQuery":
        self._mode = "select"
        return self

    def upsert(self, json: object, *, on_conflict: str) -> "_FakeQuery":
        self._mode = "upsert"
        rows = json if isinstance(json, list) else [json]
        self._rows = [dict(row) for row in rows]
        self._on_conflict = on_conflict
        return self

    def returning(self, mode: str) -> "_FakeQuery":
        return self

    def execute(self) -> _FakeResponse:
        if self._mode == "select":
            assert self._table_name == "runs"
            return _FakeResponse([dict(row) for row in self._client._runs])
        if self._mode == "upsert":
            assert self._table_name == "run_style_items"
            assert self._on_conflict == "run_id,style_key"
            for row in self._rows:
                key = (row["run_id"], row["style_key"])
                existing = self._client._style_items.get(key)
                merged = {**existing, **row} if existing is not None else dict(row)
                self._client._style_items[key] = merged
                self._client.upsert_calls.append(
                    {
                        "table": self._table_name,
                        "on_conflict": self._on_conflict,
                        "row": dict(row),
                    }
                )
            return _FakeResponse([])
        raise AssertionError("query mode is not set")


def test_to_repo_relative_path_handles_foreign_absolute_paths() -> None:
    repo_root = Path("/home/wall/self-project/SDlab")
    # 老机器绝对路径：按最右侧 data/ 锚点换算
    assert _to_repo_relative_path(
        "/home/wall/SDlab/data/prompts/Y/300_NAI_Styles_Table.yaml",
        repo_root=repo_root,
    ) == Path("data/prompts/Y/300_NAI_Styles_Table.yaml")
    # 当前仓库内的绝对路径
    assert _to_repo_relative_path(
        str(repo_root / "data/prompts/Y/asset.yaml"), repo_root=repo_root
    ) == Path("data/prompts/Y/asset.yaml")
    # 相对路径原样返回
    assert _to_repo_relative_path(
        "data/prompts/Y/asset.yaml", repo_root=repo_root
    ) == Path("data/prompts/Y/asset.yaml")
    # 无法定位的路径
    assert _to_repo_relative_path("/etc/hostname", repo_root=repo_root) is None


def test_resolve_y_asset_content_uses_current_file_when_hash_matches(
    tmp_path: Path,
) -> None:
    content = _yaml_bytes([0], schema="prompt-y-table/v3")
    rel_path = Path("data/prompts/Y/asset.yaml")
    _write_y_asset(tmp_path, rel_path, content)

    result = resolve_y_asset_content(
        repo_root=tmp_path,
        rel_path=rel_path,
        expected_sha256=hashlib.sha256(content).hexdigest(),
        git_log_commits=_fail_git_log,
    )

    assert result == content


def test_resolve_y_asset_content_recovers_matching_version_from_git(
    tmp_path: Path,
) -> None:
    v2_content = _yaml_bytes([0], schema="prompt-y-table/v2", with_info_type=True)
    v3_content = _yaml_bytes([0], schema="prompt-y-table/v3")
    rel_path = Path("data/prompts/Y/asset.yaml")
    _write_y_asset(tmp_path, rel_path, v3_content)

    result = resolve_y_asset_content(
        repo_root=tmp_path,
        rel_path=rel_path,
        expected_sha256=hashlib.sha256(v2_content).hexdigest(),
        git_log_commits=_stub_git_log(["commit-v3", "commit-v2"]),
        git_show_file=_stub_git_show(
            {"commit-v3": v3_content, "commit-v2": v2_content}
        ),
    )

    assert result == v2_content


def test_resolve_y_asset_content_raises_when_no_version_matches(
    tmp_path: Path,
) -> None:
    with pytest.raises(BackfillError, match="sha256"):
        resolve_y_asset_content(
            repo_root=tmp_path,
            rel_path=Path("data/prompts/Y/missing.yaml"),
            expected_sha256="0" * 64,
            git_log_commits=_stub_git_log(["commit-x"]),
            git_show_file=_stub_git_show({"commit-x": b"schema: other\n"}),
        )


def test_parse_style_keys_minimal_parse_supports_v2_assets() -> None:
    # 位置（0-based）≠ info.index：style_key 取 info.index
    content = _yaml_bytes([9, 3, 0], schema="prompt-y-table/v2", with_info_type=True)

    assert parse_style_keys_by_y_index(
        content, source_name="data/prompts/Y/300_NAI_Styles_Table.yaml"
    ) == {
        0: "300-nai-styles-table:9",
        1: "300-nai-styles-table:3",
        2: "300-nai-styles-table:0",
    }


def test_parse_style_keys_prefers_explicit_collection_id() -> None:
    content = _yaml_bytes(
        [1], schema="prompt-y-table/v3", collection_id="My Custom Collection"
    )

    assert parse_style_keys_by_y_index(content, source_name="whatever.yaml") == {
        0: "my-custom-collection:1"
    }


def test_build_backfill_plans_marks_coverage_matrix(tmp_path: Path) -> None:
    run_root = tmp_path / "outputs"
    ok_path = run_root / "run-a"
    ok_path.mkdir(parents=True)
    (ok_path / "run.json").write_text("{}", encoding="utf-8")
    (ok_path / "metadata.jsonl").write_text("", encoding="utf-8")
    # `_old` 目录不参与：没有同名 DB run，精确匹配天然忽略
    (run_root / "run-a_old").mkdir()
    (run_root / "run-b").mkdir()  # 缺 run.json / metadata.jsonl

    plans = build_backfill_plans(
        [
            DbRun(run_id="uuid-a", run_dir="run-a"),
            DbRun(run_id="uuid-b", run_dir="run-b"),
            DbRun(run_id="uuid-c", run_dir="run-c"),
        ],
        run_root=run_root,
    )

    by_dir = {plan.run.run_dir: plan for plan in plans}
    assert by_dir["run-a"].action == "backfill"
    assert by_dir["run-b"].action == "skip"
    assert "run.json" in by_dir["run-b"].reason
    assert by_dir["run-c"].action == "skip"
    assert by_dir["run-c"].reason == "本地无产物目录"


def _make_git_recovered_run(
    tmp_path: Path,
) -> tuple[Path, RunBackfillPlan, bytes, bytes]:
    """构造一个 run：run.json 记录 v2 资产 sha，当前文件已是 v3，需从 git 找回。"""
    repo_root = tmp_path / "repo"
    v2_content = _yaml_bytes(
        [9, 3, 0], schema="prompt-y-table/v2", with_info_type=True
    )
    v3_content = _yaml_bytes([9, 3, 0], schema="prompt-y-table/v3")
    rel_path = Path("data/prompts/Y/300_NAI_Styles_Table.yaml")
    _write_y_asset(repo_root, rel_path, v3_content)

    records = _metadata_records([0, 1, 2])
    # 首个非空 y_value 生效：后续重复行不改变 label
    records.append(
        {"status": "success", "x_index": 1, "y_index": 1, "y_value": "duplicate"}
    )
    run_path = _write_run_dir(
        tmp_path / "outputs",
        "test-run",
        y_indexes=[0, 1, 2],
        metadata_records=records,
        y_json_path="/old-machine/SDlab/data/prompts/Y/300_NAI_Styles_Table.yaml",
        y_json_sha256=hashlib.sha256(v2_content).hexdigest(),
    )
    plan = RunBackfillPlan(
        run=DbRun(run_id="uuid-test-run", run_dir="test-run"),
        run_path=run_path,
        action="backfill",
        reason="",
    )
    return repo_root, plan, v2_content, v3_content


def test_backfill_run_replays_and_upserts_idempotently(tmp_path: Path) -> None:
    repo_root, plan, v2_content, v3_content = _make_git_recovered_run(tmp_path)
    client = _FakeSupabaseClient(runs=[])
    git_log = _stub_git_log(["commit-v3", "commit-v2"])
    git_show = _stub_git_show({"commit-v3": v3_content, "commit-v2": v2_content})

    row_count = backfill_run(
        plan,
        client=client,
        repo_root=repo_root,
        dry_run=False,
        git_log_commits=git_log,
        git_show_file=git_show,
    )

    assert row_count == 3
    expected_rows = [
        {
            "run_id": "uuid-test-run",
            "run_dir": "test-run",
            "style_key": "300-nai-styles-table:9",
            "y_index": 0,
            "label": "label-0",
        },
        {
            "run_id": "uuid-test-run",
            "run_dir": "test-run",
            "style_key": "300-nai-styles-table:3",
            "y_index": 1,
            "label": "label-1",
        },
        {
            "run_id": "uuid-test-run",
            "run_dir": "test-run",
            "style_key": "300-nai-styles-table:0",
            "y_index": 2,
            "label": "label-2",
        },
    ]
    assert sorted(client.style_item_rows(), key=lambda row: row["y_index"]) == (
        expected_rows
    )

    # 幂等：重复执行 upsert 同 key 行，不产生重复
    again = backfill_run(
        plan,
        client=client,
        repo_root=repo_root,
        dry_run=False,
        git_log_commits=git_log,
        git_show_file=git_show,
    )
    assert again == 3
    assert len(client.style_item_rows()) == 3


def test_backfill_run_dry_run_writes_nothing(tmp_path: Path) -> None:
    repo_root, plan, v2_content, v3_content = _make_git_recovered_run(tmp_path)

    row_count = backfill_run(
        plan,
        client=None,
        repo_root=repo_root,
        dry_run=True,
        git_log_commits=_stub_git_log(["commit-v2"]),
        git_show_file=_stub_git_show({"commit-v2": v2_content}),
    )

    assert row_count == 3


def test_backfill_run_skips_when_y_index_set_mismatch(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    content = _yaml_bytes([9, 3, 0], schema="prompt-y-table/v3")
    rel_path = Path("data/prompts/Y/300_NAI_Styles_Table.yaml")
    _write_y_asset(repo_root, rel_path, content)
    # metadata 只覆盖 selection 的子集 → 集合校验失败
    run_path = _write_run_dir(
        tmp_path / "outputs",
        "broken-run",
        y_indexes=[0, 1, 2],
        metadata_records=_metadata_records([0, 1]),
        y_json_path="data/prompts/Y/300_NAI_Styles_Table.yaml",
        y_json_sha256=hashlib.sha256(content).hexdigest(),
    )
    plan = RunBackfillPlan(
        run=DbRun(run_id="uuid-broken", run_dir="broken-run"),
        run_path=run_path,
        action="backfill",
        reason="",
    )
    client = _FakeSupabaseClient(runs=[])

    with pytest.raises(BackfillError, match="集合不一致"):
        backfill_run(plan, client=client, repo_root=repo_root, dry_run=False)
    assert client.upsert_calls == []


def test_main_dry_run_prints_matrix_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
    repo_root = tmp_path / "repo"
    content = _yaml_bytes([9, 3, 0], schema="prompt-y-table/v3")
    rel_path = Path("data/prompts/Y/300_NAI_Styles_Table.yaml")
    _write_y_asset(repo_root, rel_path, content)
    run_root = tmp_path / "outputs"
    _write_run_dir(
        run_root,
        "run-a",
        y_indexes=[0, 1, 2],
        metadata_records=_metadata_records([0, 1, 2]),
        y_json_path="/old-machine/SDlab/data/prompts/Y/300_NAI_Styles_Table.yaml",
        y_json_sha256=hashlib.sha256(content).hexdigest(),
    )
    client = _FakeSupabaseClient(
        runs=[
            {"id": "uuid-a", "run_dir": "run-a"},
            {"id": "uuid-b", "run_dir": "run-b"},
        ]
    )

    exit_code = main(
        ["--run-root", str(run_root), "--dry-run"],
        client_factory=lambda url, key: client,
        repo_root=repo_root,
    )

    assert exit_code == 0
    assert client.upsert_calls == []
    out = capsys.readouterr().out
    assert "run-a: 回填" in out
    assert "run-a: 计划写入 3 行" in out
    assert "run-b: 跳过（本地无产物目录）" in out


def test_main_continues_after_failed_run_and_exit_code_reflects_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
    repo_root = tmp_path / "repo"
    content = _yaml_bytes([9, 3, 0], schema="prompt-y-table/v3")
    rel_path = Path("data/prompts/Y/300_NAI_Styles_Table.yaml")
    _write_y_asset(repo_root, rel_path, content)
    run_root = tmp_path / "outputs"
    _write_run_dir(
        run_root,
        "run-a",
        y_indexes=[0, 1, 2],
        metadata_records=_metadata_records([0, 1, 2]),
        y_json_path="data/prompts/Y/300_NAI_Styles_Table.yaml",
        y_json_sha256=hashlib.sha256(content).hexdigest(),
    )
    # run-b 的 Y 资产 sha 无法解析（tmp repo 不是 git 仓库，git log 必失败）
    _write_run_dir(
        run_root,
        "run-b",
        y_indexes=[0, 1, 2],
        metadata_records=_metadata_records([0, 1, 2]),
        y_json_path="data/prompts/Y/missing.yaml",
        y_json_sha256="0" * 64,
    )
    client = _FakeSupabaseClient(
        runs=[
            {"id": "uuid-a", "run_dir": "run-a"},
            {"id": "uuid-b", "run_dir": "run-b"},
        ]
    )

    exit_code = main(
        ["--run-root", str(run_root)],
        client_factory=lambda url, key: client,
        repo_root=repo_root,
    )

    assert exit_code == 1
    # 单 run 失败不中断：run-a 已写入，run-b 报错跳过
    assert len(client.style_item_rows()) == 3
    out = capsys.readouterr().out
    assert "run-a: 已写入 3 行" in out
    assert "run-b: 失败（Y 资产无法按记录的 sha256 解析）" in out
