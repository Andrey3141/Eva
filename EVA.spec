# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec для EVA.
Собирает onedir-приложение: EVA/EVA(.exe) + _internal/ + assets/.

Сборка:
    pyinstaller --clean EVA.spec

Результат:
    dist/EVA/EVA.exe          (Windows)
    dist/EVA/EVA              (Linux)
    dist/EVA/_internal/...
    dist/EVA/assets/silero/v4_ru.pt
    dist/EVA/assets/avatar/...
"""
from pathlib import Path

project_root = Path(SPECPATH).resolve()
assets_dir = project_root / "assets"
data_dir = project_root / "data"


datas = []

# assets/ → assets/ внутри _MEIPASS (для onedir — рядом с exe)
if assets_dir.exists():
    for path in assets_dir.rglob("*"):
        if path.is_file():
            rel = path.relative_to(project_root)
            datas.append((str(path), str(rel.parent)))

# data/test_gradebook.xlsx → data/
if data_dir.exists():
    for path in data_dir.rglob("*.xlsx"):
        rel = path.relative_to(project_root)
        datas.append((str(path), str(rel.parent)))


a = Analysis(
    ["main.py"],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "assistant.tts.silero_tts",
        "assistant.tts.edge_tts",
        "assistant.tts.fallback_tts",
        "assistant.audio.playback",
        "torch",
        "torchaudio",
        "omegaconf",
        "edge_tts",
        "sounddevice",
        "faster_whisper",
        "openpyxl",
        "pyttsx3",
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "PyQt5", "PyQt6"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="EVA",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,             # UPX может ломать torch DLL — выключено
    console=True,          # для первой сборки — True, потом False
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="EVA",
)
