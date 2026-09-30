# -*- coding: utf-8 -*-
"""
Alesya — единая точка входа тестовой системы.

Запуск в Blender 4.3.2:
    Scripting -> Open -> Alesya/tests/main.py -> Run Script (Alt+P)

Режимы работы:

  1. RUN_EXTERNAL_HEAD_ONLY = True
        Запускается ТОЛЬКО read-only тест EXTERNAL_HEAD_TEST.
        Сцена не очищается, объекты не удаляются, ничего из
        bpy.data не стирается.

        Если EXTERNAL_HEAD_TEST == "tests.test_head_work_copy",
        перед запуском автоматически вызывается
        character.head_work.create_work_head(), чтобы гарантировать
        наличие объекта Alesya_Head_Work. Создание копии не изменяет
        исходный GEO-head_animation_realistic и не очищает сцену.

  2. RUN_EXTERNAL_HEAD_ONLY = False
        Полный обычный набор тестов.
"""

import sys
import importlib
import traceback
from pathlib import Path

import bpy


# ============================================================
# РЕЖИМ ЗАПУСКА
# ============================================================

RUN_EXTERNAL_HEAD_ONLY = True


# ============================================================
# 1. Корень проекта
# ============================================================

def _resolve_project_dir() -> Path:
    blend_path = bpy.data.filepath
    if not blend_path:
        raise RuntimeError(
            "Файл .blend не сохранён. Сохраните сцену рядом с папкой Alesya/."
        )
    return Path(blend_path).resolve().parent / "Alesya"


PROJECT_DIR = _resolve_project_dir()
if not PROJECT_DIR.exists():
    raise RuntimeError(
        f"Не найдена папка проекта: {PROJECT_DIR}\n"
        f"Ожидается структура:\n"
        f"    Blender/Alesya.blend\n"
        f"    Blender/Alesya/tests/main.py"
    )
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))


# ============================================================
# 2. Реестр тестов
# ============================================================

EXTERNAL_HEAD_TEST = "tests.test_head_adaptation_visual_debug"

TESTS_READONLY = [
    EXTERNAL_HEAD_TEST,
]

TESTS_DESTRUCTIVE = [
    "tests.test_head",
    "tests.test_eyes",
    "tests.test_eyes_visual",
    "tests.test_face_anthropometry",
    "tests.test_head_visual",
]


# ============================================================
# 3. Перезагрузка production-модулей
# ============================================================

PRODUCTION_MODULES = [
    "config",
    "materials",
    "utils",
    "character",
    "character.head",
    "character.head_work",
    "character.face",
    "character.eyes",
    "character.hair",
    "character.body",
    "character.clothes",
    "accessories",
    "accessories.hat",
    "accessories.ribbon",
    "accessories.flowers",
    "accessories.ornament",
    "scene",
    "scene.camera",
    "scene.lighting",
    "animation",
    "animation.eyes",
    "animation.mouth",
    "animation.face",
    "animation.idle",
]


def _force_reload_modules():
    importlib.invalidate_caches()

    for name in list(sys.modules.keys()):
        if name in PRODUCTION_MODULES:
            del sys.modules[name]
        elif name.startswith("tests."):
            del sys.modules[name]
        elif name == "tests":
            del sys.modules[name]
        elif (name.startswith("character.")
              or name.startswith("accessories.")
              or name.startswith("scene.")
              or name.startswith("animation.")):
            del sys.modules[name]

    for name in PRODUCTION_MODULES:
        importlib.import_module(name)


_force_reload_modules()


# ============================================================
# 4. ANSI
# ============================================================

ANSI_GREEN = "\033[92m"
ANSI_CYAN  = "\033[96m"
ANSI_RED   = "\033[91m"
ANSI_YEL   = "\033[93m"
ANSI_RESET = "\033[0m"


def _ansi_supported() -> bool:
    import os
    if os.environ.get("NO_COLOR"):
        return False
    stream = sys.stdout
    if stream is None:
        return False
    try:
        return bool(stream.isatty())
    except Exception:
        return False


_USE_ANSI = _ansi_supported()


def ansi(text: str, color: str) -> str:
    if _USE_ANSI:
        return f"{color}{text}{ANSI_RESET}"
    return text


def print_suite_start(mode_label: str):
    lines = [
        "=" * 60,
        "ALESYA TEST SUITE — START",
        f"MODE: {mode_label}",
        "=" * 60,
    ]
    print(ansi("\n".join(lines), ANSI_GREEN))
    print()


def print_suite_finish(passed: int, failed: int):
    lines = [
        "=" * 60,
        "ALESYA TEST SUITE — FINISHED",
        f"PASSED: {passed}",
        f"FAILED: {failed}",
        "=" * 60,
    ]
    color = ANSI_RED if failed > 0 else ANSI_CYAN
    print(ansi("\n".join(lines), color))
    if failed > 0:
        print(ansi("TEST FAILED", ANSI_RED))
    print()


def print_test_header(name: str):
    print(ansi(f"[TEST] {name}", ANSI_YEL))
    print("-" * 40)


def print_test_pass(name: str):
    print("-" * 40)
    print(ansi(f"[PASS] {name}", ANSI_GREEN))
    print()


def print_test_fail(name: str):
    print("-" * 40)
    print(ansi(f"[FAIL] {name}", ANSI_RED))
    print()


def print_group_header(label: str):
    print(ansi(f"--- {label} ---", ANSI_CYAN))


# ============================================================
# 5. Запуск одного теста
# ============================================================

def _run_single_test(module_name: str) -> bool:
    print_test_header(module_name)

    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        traceback.print_exc()
        print(f"[FAIL] {module_name} — import error: "
              f"{type(exc).__name__}: {exc}")
        print_test_fail(module_name)
        return False

    if not hasattr(module, "run_test"):
        msg = f"Module {module_name} does not expose run_test()."
        print(f"[FAIL] {module_name} — {msg}")
        print_test_fail(module_name)
        return False

    try:
        module.run_test()
    except Exception as exc:
        traceback.print_exc()
        print(f"[FAIL] {module_name} — {type(exc).__name__}: {exc}")
        print_test_fail(module_name)
        return False

    print_test_pass(module_name)
    return True


# ============================================================
# 6. MAIN
# ============================================================

def _run_group(label, module_names):
    print_group_header(label)
    passed = 0
    failed = 0
    for module_name in module_names:
        if _run_single_test(module_name):
            passed += 1
        else:
            failed += 1
    return passed, failed


def _ensure_work_head_if_needed():
    """
    Если в external-режиме запускается test_head_work_copy,
    заранее создаём рабочую копию головы через
    character.head_work.create_work_head().

    Функция идемпотентна: если копия уже есть, ничего не
    пересоздаётся. Исходный GEO-head_animation_realistic
    не изменяется, сцена не очищается.
    """
    if EXTERNAL_HEAD_TEST != "tests.test_head_work_copy":
        return
    try:
        from character.head_work import create_work_head
    except Exception as exc:
        print(f"[main] WARNING: cannot import character.head_work: "
              f"{type(exc).__name__}: {exc}")
        return
    create_work_head()


def main():
    if RUN_EXTERNAL_HEAD_ONLY:
        print_suite_start("EXTERNAL HEAD — READ-ONLY")

        _ensure_work_head_if_needed()

        passed, failed = _run_group(
            "EXTERNAL HEAD TOPOLOGY (read-only, scene preserved)",
            [EXTERNAL_HEAD_TEST],
        )

        print_suite_finish(passed, failed)

        if failed > 0:
            raise RuntimeError(f"{failed} test(s) failed.")
        return

    print_suite_start("FULL TEST SUITE")

    total_passed = 0
    total_failed = 0

    p, f = _run_group("READ-ONLY TESTS (scene is not modified)",
                      TESTS_READONLY)
    total_passed += p
    total_failed += f

    p, f = _run_group("DESTRUCTIVE TESTS (scene is rebuilt)",
                      TESTS_DESTRUCTIVE)
    total_passed += p
    total_failed += f

    print_suite_finish(total_passed, total_failed)

    if total_failed > 0:
        raise RuntimeError(f"{total_failed} test(s) failed.")


if __name__ == "__main__":
    main()
