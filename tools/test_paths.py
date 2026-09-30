"""
Тесты assistant.paths — фактический контракт.

Запуск через pytest:
    pytest -v tools/test_paths.py
Прямой запуск:
    python -m tools.test_paths

Тесты не требуют сети, TTS, микрофона, GUI.
"""
import os
import sys
from pathlib import Path

from assistant import paths


# ---------------------------------------------------------------------------
# base_dir / project_root / runtime
# ---------------------------------------------------------------------------

def test_base_dir_returns_existing_directory():
    bd = paths.base_dir()
    assert isinstance(bd, Path)
    assert bd.exists()
    assert bd.is_dir()


def test_base_dir_does_not_depend_on_cwd(tmp_path, monkeypatch):
    before = paths.base_dir()
    monkeypatch.chdir(tmp_path)
    after = paths.base_dir()
    assert before == after, f"{before} != {after}"


def test_runtime_kind_is_source_here():
    # Тесты запускаются из исходников, значит runtime_kind == "source".
    assert paths.runtime_kind() == "source"
    assert paths.is_frozen() is False


def test_project_root_is_directory():
    pr = paths.project_root()
    assert isinstance(pr, Path)
    assert pr.exists()
    assert pr.is_dir()


# ---------------------------------------------------------------------------
# env_path
# ---------------------------------------------------------------------------

def test_env_path_relative_resolves_against_base_dir(monkeypatch):
    monkeypatch.setenv("EVA_TEST_REL", "some/sub/path")
    p = paths.env_path("EVA_TEST_REL", "ignored_default")
    assert p.is_absolute()
    assert p == paths.base_dir() / "some/sub/path"


def test_env_path_absolute_stays_absolute(monkeypatch, tmp_path):
    abs_path = tmp_path / "custom" / "file.txt"
    monkeypatch.setenv("EVA_TEST_ABS", str(abs_path))
    p = paths.env_path("EVA_TEST_ABS", "ignored_default")
    assert p.is_absolute()
    assert p == abs_path


def test_env_path_empty_uses_default(monkeypatch):
    monkeypatch.setenv("EVA_TEST_EMPTY", "")
    p = paths.env_path("EVA_TEST_EMPTY", "fallback/thing")
    assert p == paths.base_dir() / "fallback/thing"


def test_env_path_missing_uses_default(monkeypatch):
    monkeypatch.delenv("EVA_TEST_MISSING", raising=False)
    p = paths.env_path("EVA_TEST_MISSING", "fallback/missing")
    assert p == paths.base_dir() / "fallback/missing"


def test_env_path_whitespace_only_uses_default(monkeypatch):
    monkeypatch.setenv("EVA_TEST_WS", "   ")
    p = paths.env_path("EVA_TEST_WS", "fallback/ws")
    assert p == paths.base_dir() / "fallback/ws"


# ---------------------------------------------------------------------------
# user_data_dir / temp_dir
# ---------------------------------------------------------------------------

def test_user_data_dir_is_path():
    d = paths.user_data_dir()
    assert isinstance(d, Path)


def test_temp_dir_exists():
    d = paths.temp_dir()
    assert isinstance(d, Path)
    assert d.exists()
    assert d.is_dir()


# ---------------------------------------------------------------------------
# env_file_path
# ---------------------------------------------------------------------------

def test_env_file_path_returns_path_or_none():
    p = paths.env_file_path()
    assert p is None or isinstance(p, Path)


def test_env_file_path_ignores_cwd(tmp_path, monkeypatch):
    """
    .env в cwd не должен подхватываться, потому что env_file_path
    ищет в user_data_dir и base_dir.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("X=1\n", encoding="utf-8")
    p = paths.env_file_path()
    # Если base_dir реально содержит .env — вернётся он, но не тот, что в tmp_path.
    if p is not None:
        assert p != tmp_path / ".env"


# ---------------------------------------------------------------------------
# silero_model_path / avatar_dir / gradebook_path
# ---------------------------------------------------------------------------

def test_silero_model_path_is_path():
    p = paths.silero_model_path()
    assert isinstance(p, Path)
    assert p.is_absolute()


def test_avatar_dir_is_path():
    p = paths.avatar_dir()
    assert isinstance(p, Path)
    assert p.is_absolute()


def test_gradebook_path_is_path():
    p = paths.gradebook_path()
    assert isinstance(p, Path)
    assert p.is_absolute()


def test_silero_model_path_override(monkeypatch, tmp_path):
    custom = tmp_path / "my_silero.pt"
    monkeypatch.setenv("SILERO_MODEL_PATH", str(custom))
    p = paths.silero_model_path()
    assert p == custom


def test_avatar_dir_override(monkeypatch, tmp_path):
    custom = tmp_path / "my_avatar"
    monkeypatch.setenv("AVATAR_DIR", str(custom))
    p = paths.avatar_dir()
    assert p == custom


def test_gradebook_path_override(monkeypatch, tmp_path):
    custom = tmp_path / "my_journal.xlsx"
    monkeypatch.setenv("GRADEBOOK_PATH", str(custom))
    p = paths.gradebook_path()
    assert p == custom


def test_relative_override_resolves_against_base_dir(monkeypatch):
    monkeypatch.setenv("GRADEBOOK_PATH", "relative/journal.xlsx")
    p = paths.gradebook_path()
    assert p.is_absolute()
    assert p == paths.base_dir() / "relative/journal.xlsx"


# ---------------------------------------------------------------------------
# logs_dir / whisper_cache_dir
# ---------------------------------------------------------------------------

def test_logs_dir_creates_directory(monkeypatch, tmp_path):
    custom = tmp_path / "custom_logs"
    monkeypatch.setenv("EVA_LOG_DIR", str(custom))
    d = paths.logs_dir()
    assert d == custom
    assert d.exists()
    assert d.is_dir()


def test_whisper_cache_dir_creates_directory(monkeypatch, tmp_path):
    custom = tmp_path / "custom_whisper"
    monkeypatch.setenv("WHISPER_CACHE_DIR", str(custom))
    d = paths.whisper_cache_dir()
    assert d == custom
    assert d.exists()
    assert d.is_dir()


def test_describe_contains_no_playwright_line():
    text = paths.describe()
    assert "playwright" not in text.lower()
    assert "Playwright" not in text
    assert "ещё не подключён" not in text


# ---------------------------------------------------------------------------
# Прямой запуск
# ---------------------------------------------------------------------------

def _run_all():
    tests = [
        test_base_dir_returns_existing_directory,
        test_runtime_kind_is_source_here,
        test_project_root_is_directory,
        test_user_data_dir_is_path,
        test_temp_dir_exists,
        test_env_file_path_returns_path_or_none,
        test_silero_model_path_is_path,
        test_avatar_dir_is_path,
        test_gradebook_path_is_path,
        test_describe_contains_no_playwright_line,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"[OK] {t.__name__}", flush=True)
        except AssertionError as e:
            failed += 1
            print(f"[FAIL] {t.__name__}: {e}", flush=True)
        except Exception as e:
            failed += 1
            print(f"[ERROR] {t.__name__}: {type(e).__name__}: {e}", flush=True)
    print(flush=True)
    print(f"=== {len(tests) - failed}/{len(tests)} PATH TESTS PASSED (direct) ===", flush=True)
    return failed


def main():
    if not os.path.exists("assistant"):
        print("Запускать из корня проекта.", flush=True)
        sys.exit(2)
    sys.exit(1 if _run_all() else 0)


if __name__ == "__main__":
    main()
