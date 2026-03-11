import pytest
import scripts.generation.comfyui_part1_generate as comfy_gen
import scripts.cli.menu as cli_menu
import scripts.r2_upload.upload_images_to_r2 as r2_upload
import scripts.r2_upload.supabase_writer as supabase_writer


def test_comfyui_part1_generate_exports():
    exports = [
        "build_parser",
        "main",
        "run",
        "run_retry",
        "_append_negative_prompt",
        "comfy_submit_prompt",
        "comfy_wait_prompt_done_with_fallback",
        "comfy_get_history_item",
        "comfy_download_image_to_path",
    ]
    for name in exports:
        assert hasattr(comfy_gen, name), f"Missing export: {name}"
        assert callable(getattr(comfy_gen, name)), f"Export {name} is not callable"


def test_cli_menu_exports():
    assert hasattr(cli_menu, "run_menu"), "Missing export: run_menu"
    assert callable(cli_menu.run_menu), "Export run_menu is not callable"


def test_r2_upload_exports():
    callables = ["build_parser", "main"]
    for name in callables:
        assert hasattr(r2_upload, name), f"Missing export: {name}"
        assert callable(getattr(r2_upload, name)), f"Export {name} is not callable"

    assert hasattr(r2_upload, "_EXIT_CODES_BY_CATEGORY"), (
        "Missing export: _EXIT_CODES_BY_CATEGORY"
    )
    try:
        _ = r2_upload._EXIT_CODES_BY_CATEGORY
    except Exception as e:
        pytest.fail(f"Export _EXIT_CODES_BY_CATEGORY is not accessible: {e}")


def test_supabase_writer_exports():
    callables = [
        "SupabaseWriter",
        "SupabaseConfigError",
        "SupabaseArgumentError",
        "SupabaseRemoteError",
        "_default_client_factory",
        "_normalize_rows_for_postgrest",
    ]
    for name in callables:
        assert hasattr(supabase_writer, name), f"Missing export: {name}"
        assert callable(getattr(supabase_writer, name)), (
            f"Export {name} is not callable/instantiable"
        )
