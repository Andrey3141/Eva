"""
Создаёт тестовый .xlsx для отладки пайплайна.
Путь берётся из assistant.paths.gradebook_path() — работает и в source,
и в PyInstaller, и на Linux/Windows.

Запуск: python -m tools.make_test_gradebook
"""
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font

from assistant import paths


HEADERS = ["№", "ФИО", "10.09", "12.09", "15.09", "17.09", "19.09"]

ROWS = [
    (1, "Иванов Пётр Сергеевич",      5, 4, 5, None, None),
    (2, "Сидоров Алексей Дмитриевич", 4, 3, None, 5, None),
    (3, "Петров Максим Андреевич",    3, 4, 4, None, None),
    (4, "Смирнов Артём Олегович",     5, 5, None, None, 4),
    (5, "Кузнецов Дмитрий Игоревич",  4, None, 5, 4, None),
    (6, "Морозов Никита Владимирович", None, 5, 4, None, 5),
    (7, "Волкова Анна Сергеевна",     5, 5, 5, 5, 5),
]


def main():
    out_path = paths.gradebook_path()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "Электроснабжение"

    for col, header in enumerate(HEADERS, start=1):
        c = ws.cell(row=1, column=col, value=header)
        c.font = Font(bold=True)
        c.alignment = Alignment(horizontal="center")

    for r_idx, row in enumerate(ROWS, start=2):
        for c_idx, value in enumerate(row, start=1):
            ws.cell(row=r_idx, column=c_idx, value=value)

    ws.column_dimensions["A"].width = 5
    ws.column_dimensions["B"].width = 32
    for col in ("C", "D", "E", "F", "G"):
        ws.column_dimensions[col].width = 8

    wb.save(str(out_path))
    print(f"[OK] Создан: {out_path}", flush=True)
    print(f"     Лист: {ws.title}", flush=True)
    print(f"     Строк с учениками: {len(ROWS)}", flush=True)


if __name__ == "__main__":
    main()
