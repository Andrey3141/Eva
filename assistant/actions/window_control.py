"""
Адресное управление окнами для close_* действий.

ЗАПРЕЩЕНО использовать pkill/taskkill по имени процесса: это закроет
все окна приложения, включая пользовательские несохранённые документы.

Разрешено только адресное закрытие КОНКРЕТНОГО окна по заголовку.
Если однозначно выбрать окно нельзя — возвращаем "ambiguous" и
ничего не закрываем.

Платформы:
  - Windows: ctypes.windll.user32 (EnumWindows + PostMessageW(WM_CLOSE)).
    Без внешних зависимостей.
  - Linux: wmctrl -c <title> или xdotool (search + getwindowname +
    windowkill).
  - macOS: пока "unsupported".

ВАЖНО: WM_CLOSE / wmctrl -c / xdotool windowkill — это ЗАПРОС
на закрытие окна, а не гарантия его исчезновения. Статус
"close_requested" означает «команда закрытия успешно отправлена
в найденное окно», а не «окно гарантированно исчезло».

Возвращаемые статусы:
  - "close_requested"  — команда отправлена в найденное окно
  - "not_found"        — подходящее окно не найдено
  - "ambiguous"        — найдено несколько равнозначных окон
  - "unsupported"      — платформа/утилита недоступна
  - "error"            — иная ошибка
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CloseResult:
    status: str          # close_requested | not_found | ambiguous | unsupported | error
    message: str = ""
    matched_title: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "close_requested"


def _title_hint(path: str) -> str:
    """Заголовок окна обычно содержит имя файла без расширения."""
    return Path(path).stem


def close_window_for_file(path: str) -> CloseResult:
    """
    Отправляет запрос на закрытие окна, соответствующего открытому
    файлу. Не трогает другие окна того же приложения.
    """
    if not path:
        return CloseResult("not_found", "path не задан")

    title_hint = _title_hint(path)

    if sys.platform.startswith("win"):
        return _close_windows(path, title_hint)
    if sys.platform == "darwin":
        return _close_macos(path, title_hint)
    return _close_linux(path, title_hint)


# ---------------------------------------------------------------------------
# Общая эвристика выбора лучшего окна
# ---------------------------------------------------------------------------

_EDITOR_MARKERS = (
    " - powerpoint", " - word", " - excel",
    " — libreoffice", " - libreoffice",
    " - libreoffice impress", " - libreoffice calc",
    " - libreoffice writer",
)


def _strip_editor_marker(title: str) -> str:
    t = title.lower()
    for marker in _EDITOR_MARKERS:
        idx = t.find(marker)
        if idx >= 0:
            t = t[:idx].strip()
            break
    return t


def _match_score(title: str, stem_full: str) -> tuple[int, int]:
    """
    Возвращает (уровень, -длина_заголовка).
    Уровни:
      3 — точное совпадение со stem после снятия маркера редактора
      2 — начинается со stem
      1 — содержит stem
    При равенстве уровня — короче заголовок выигрывает
    (отрицательная длина в tuple для sort(reverse=True)).
    """
    t = _strip_editor_marker(title)
    if t == stem_full:
        return (3, -len(title))
    if t.startswith(stem_full):
        return (2, -len(title))
    return (1, -len(title))


def _pick_best(
    candidates: list[tuple[int, str]],
    stem_full: str,
) -> tuple[int, str] | None:
    """
    Возвращает лучший (hwnd|wid, title) или None, если неоднозначно.
    Неоднозначно: у top-1 и top-2 одинаковый score — не угадываем.
    """
    if not candidates:
        return None
    scored = [(_match_score(title, stem_full), wid, title)
              for wid, title in candidates]
    scored.sort(key=lambda x: (x[0], ), reverse=True)

    if len(scored) >= 2 and scored[0][0] == scored[1][0]:
        # Два и более окон с одинаковой уверенностью.
        return None

    _score, wid, title = scored[0]
    return (wid, title)


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------

def _close_windows(path: str, title_hint: str) -> CloseResult:
    try:
        import ctypes
        from ctypes import wintypes
    except Exception as e:
        return CloseResult("unsupported", f"ctypes недоступен: {e}")

    try:
        user32 = ctypes.windll.user32
    except Exception as e:
        return CloseResult("unsupported", f"user32 недоступен: {e}")

    WM_CLOSE = 0x0010
    hint_low = title_hint.lower()
    stem_full = Path(path).stem.lower()

    found: list[tuple[int, str]] = []

    def _enum_proc(hwnd, _lparam):
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value or ""
        if hint_low in title.lower():
            found.append((hwnd, title))
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND,
                                     wintypes.LPARAM)
    try:
        user32.EnumWindows(WNDENUMPROC(_enum_proc), 0)
    except Exception as e:
        return CloseResult("error", f"EnumWindows: {e}")

    if not found:
        return CloseResult("not_found",
                           f"окно с «{title_hint}» не найдено")

    best = _pick_best(found, stem_full)
    if best is None:
        titles = ", ".join(repr(t) for _, t in found[:5])
        return CloseResult(
            "ambiguous",
            f"найдено несколько равнозначных окон: {titles}",
        )

    hwnd, matched_title = best

    try:
        user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    except Exception as e:
        return CloseResult("error", f"PostMessageW: {e}")

    return CloseResult(
        "close_requested",
        f"запрос закрытия отправлен в окно {matched_title!r}",
        matched_title=matched_title,
    )


# ---------------------------------------------------------------------------
# Linux
# ---------------------------------------------------------------------------

def _close_linux(path: str, title_hint: str) -> CloseResult:
    if shutil.which("wmctrl"):
        return _close_linux_wmctrl(path, title_hint)

    if shutil.which("xdotool"):
        return _close_linux_xdotool(path, title_hint)

    return CloseResult(
        "unsupported",
        "ни wmctrl, ни xdotool не найдены — адресное закрытие недоступно",
    )


def _close_linux_wmctrl(path: str, title_hint: str) -> CloseResult:
    """
    wmctrl -c по заголовку. Сам wmctrl при нескольких совпадениях
    ведёт себя неоднозначно (может закрыть несколько), поэтому
    сначала получаем список окон (`wmctrl -l`) и выбираем одно
    так же, как в Windows.
    """
    try:
        r = subprocess.run(
            ["wmctrl", "-l"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=3.0,
            text=True,
        )
    except Exception as e:
        return CloseResult("error", f"wmctrl -l: {e}")

    if r.returncode != 0:
        return CloseResult("error",
                           f"wmctrl -l rc={r.returncode}: {r.stderr.strip()}")

    stem_full = Path(path).stem.lower()
    hint_low = title_hint.lower()
    candidates: list[tuple[str, str]] = []  # (wid, title)

    for line in r.stdout.splitlines():
        # Формат: <winid> <desktop> <host> <title>
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        wid, _desktop, _host, title = parts
        if hint_low in title.lower():
            candidates.append((wid, title))

    if not candidates:
        return CloseResult("not_found",
                           f"wmctrl: окно «{title_hint}» не найдено")

    # Используем общую эвристику, но _pick_best ожидает
    # (int|str, title). Для wmctrl wid — строка hex.
    scored = [(_match_score(title, stem_full), wid, title)
              for wid, title in candidates]
    scored.sort(key=lambda x: (x[0], ), reverse=True)

    if len(scored) >= 2 and scored[0][0] == scored[1][0]:
        titles = ", ".join(repr(t) for _, _, t in scored[:5])
        return CloseResult(
            "ambiguous",
            f"wmctrl: несколько равнозначных окон: {titles}",
        )

    _score, wid, title = scored[0]
    try:
        subprocess.run(
            ["wmctrl", "-i", "-c", wid],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=3.0,
        )
    except Exception as e:
        return CloseResult("error", f"wmctrl -c: {e}")

    return CloseResult(
        "close_requested",
        f"wmctrl: запрос закрытия {title!r}",
        matched_title=title,
    )


def _close_linux_xdotool(path: str, title_hint: str) -> CloseResult:
    """
    xdotool search + getwindowname + выбор одного окна + windowkill.
    Не закрываем несколько окон разом.
    """
    try:
        r = subprocess.run(
            ["xdotool", "search", "--name", title_hint],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=3.0,
            text=True,
        )
    except Exception as e:
        return CloseResult("error", f"xdotool search: {e}")

    if r.returncode != 0 or not r.stdout.strip():
        return CloseResult("not_found",
                           f"xdotool: окно «{title_hint}» не найдено")

    ids = [w.strip() for w in r.stdout.strip().splitlines() if w.strip()]
    if not ids:
        return CloseResult("not_found",
                           f"xdotool: окно «{title_hint}» не найдено")

    stem_full = Path(path).stem.lower()
    candidates: list[tuple[str, str]] = []  # (wid, title)

    for wid in ids:
        try:
            rt = subprocess.run(
                ["xdotool", "getwindowname", wid],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=3.0,
                text=True,
            )
        except Exception:
            continue
        if rt.returncode != 0:
            continue
        title = rt.stdout.strip()
        if title:
            candidates.append((wid, title))

    if not candidates:
        return CloseResult("not_found",
                           f"xdotool: не удалось получить заголовки окон")

    scored = [(_match_score(title, stem_full), wid, title)
              for wid, title in candidates]
    scored.sort(key=lambda x: (x[0], ), reverse=True)

    # Неоднозначно: top-1 и top-2 имеют одинаковую уверенность.
    if len(scored) >= 2 and scored[0][0] == scored[1][0]:
        titles = ", ".join(repr(t) for _, _, t in scored[:5])
        return CloseResult(
            "ambiguous",
            f"xdotool: несколько равнозначных окон: {titles}",
        )

    _score, wid, title = scored[0]
    try:
        subprocess.run(
            ["xdotool", "windowkill", wid],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=3.0,
        )
    except Exception as e:
        return CloseResult("error", f"xdotool windowkill: {e}")

    return CloseResult(
        "close_requested",
        f"xdotool: запрос закрытия {title!r}",
        matched_title=title,
    )


# ---------------------------------------------------------------------------
# macOS
# ---------------------------------------------------------------------------

def _close_macos(path: str, title_hint: str) -> CloseResult:
    return CloseResult(
        "unsupported",
        "адресное закрытие окон на macOS пока не поддерживается",
    )
