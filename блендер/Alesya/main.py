# -*- coding: utf-8 -*-
"""
Alesya 2.5D Avatar — точка входа.

Открыть в Blender 4.3.2:
    Scripting -> Open -> Alesya/main.py -> Run Script (Alt+P)

Задачи main.py:
  1. определить корень проекта относительно открытого .blend;
  2. перезагрузить модули проекта;
  3. вызвать build_alesya();
  4. больше ничего.

Все настройки подсистем живут в своих модулях.
main.py не редактируется под конкретные тесты.
"""

import sys
import importlib
from pathlib import Path

import bpy


# ============================================================
# 1. Определение корня проекта
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
        f"    Blender/Alesya/main.py"
    )

if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))


# ============================================================
# 2. Принудительная перезагрузка модулей проекта
# ============================================================

PROJECT_MODULES = [
    "config",
    "materials",
    "utils",
    "character",
    "character.head",
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


def _force_reload_project_modules():
    importlib.invalidate_caches()
    for name in list(sys.modules.keys()):
        if name in PROJECT_MODULES:
            del sys.modules[name]
        elif (name.startswith("character.")
              or name.startswith("accessories.")
              or name.startswith("scene.")
              or name.startswith("animation.")):
            del sys.modules[name]
    for name in PROJECT_MODULES:
        importlib.import_module(name)


_force_reload_project_modules()


# ============================================================
# 3. Импорт точки сборки
# ============================================================

from build import build_alesya  # noqa: E402


# ============================================================
# 4. Запуск
# ============================================================

def main():
    build_alesya()


if __name__ == "__main__":
    main()
