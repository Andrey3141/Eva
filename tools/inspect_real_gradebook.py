# tools/inspect_real_gradebook.py
"""
Диагностика: какой журнал реально загружается и как выглядит его структура.

Запуск:
    python -m tools.inspect_real_gradebook
"""
import os
import sys
from pathlib import Path

from openpyxl import load_workbook

from config import Config
from assistant import paths


def main():
    print("=== GRADEBOOK DIAGNOSTIC ===")
    print(f"[config] Config.GRADEBOOK_PATH = {Config.GRADEBOOK_PATH}")
    print(f"[paths]  paths.gradebook_path() = {paths.gradebook_path()}")
    print(f"[env]    GRADEBOOK_PATH = {os.environ.get('GRADEBOOK_PATH', '<unset>')}")

    path = Path(Config.GRADEBOOK_PATH)
    print(f"[file]   absolute = {path.resolve()}")
    print(f"[file]   exists   = {path.is_file()}")

    if not path.is_file():
        print("[file]   НЕ НАЙДЕН. Создайте файл или задайте GRADEBOOK_PATH в .env.")
        return 1

    wb = load_workbook(path, data_only=False)
    print(f"[wb]     sheets = {wb.sheetnames}")

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        print(f"\n[sheet]  {sheet_name!r}")
        print(f"[sheet]  dimensions = {ws.max_row} rows × {ws.max_column} cols")

        # Заголовки (строка 1) и первые несколько строк.
        print("[sheet]  --- первые 5 строк ---")
        for r in range(1, min(ws.max_row, 5) + 1):
            row_vals = []
            for c in range(1, min(ws.max_column, 12) + 1):
                cell = ws.cell(row=r, column=c)
                v = cell.value
                # Показать тип значения: str / int / datetime / None.
                t = type(v).__name__ if v is not None else "None"
                row_vals.append(f"{cell.coordinate}={v!r}({t})")
            print(f"[sheet]  row {r}: " + " | ".join(row_vals))

        # Специально — ищем в первой строке заголовки, похожие на даты.
        print("[sheet]  --- заголовки, похожие на даты ---")
        date_like = []
        from openpyxl.utils import get_column_letter
        import datetime as _dt
        for c in range(1, ws.max_column + 1):
            v = ws.cell(row=1, column=c).value
            if v is None:
                continue
            if isinstance(v, _dt.datetime) or isinstance(v, _dt.date):
                date_like.append((get_column_letter(c), v, type(v).__name__))
            elif isinstance(v, str) and any(ch.isdigit() for ch in v):
                # "29.09", "29.09.2026", "29/09", "17.09" и т.п.
                import re
                if re.match(r"^\s*\d{1,2}[./\-]\d{1,2}(?:[./\-]\d{2,4})?\s*$", v):
                    date_like.append((get_column_letter(c), v, "str"))

        for col, v, t in date_like:
            print(f"[sheet]  col {col}: {v!r} ({t})")

        if not date_like:
            print("[sheet]  <дат в заголовке не найдено>")

    return 0


if __name__ == "__main__":
    sys.exit(main())
