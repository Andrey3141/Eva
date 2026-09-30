from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.workbook.workbook import Workbook

from .base import Gradebook, StudentMatch, GradeTarget


# ---------------------------------------------------------------------------
# Нормализация русских фамилий (падежные формы)
# ---------------------------------------------------------------------------

_SURNAME_ENDINGS = [
    "ыми", "ими", "ого", "его", "ому", "ему",
    "ая", "яя", "ое", "ее", "ые", "ие", "ой", "ей", "ый", "ий",
    "ова", "ева", "ина", "ына", "ову", "еву", "ину", "ыну",
    "овым", "евым", "иным", "ыным",
    "овом", "евом", "ином", "ыном",
    "ов", "ев", "ин", "ын",
    "у", "ю", "а", "я", "е", "ы", "и", "о",
]


def _base_surname(token: str) -> str:
    t = token.strip().lower().replace("ё", "е")
    if len(t) <= 4:
        return t
    for end in _SURNAME_ENDINGS:
        if len(t) - len(end) >= 4 and t.endswith(end):
            return t[: -len(end)]
    return t


def _query_key(name: str) -> tuple[str, str]:
    parts = [p for p in name.strip().split() if p]
    if not parts:
        return "", ""
    base = _base_surname(parts[0])
    rest = " ".join(p.lower().replace("ё", "е") for p in parts[1:])
    return base, rest


def _full_name_key(full_name: str) -> tuple[str, str]:
    parts = [p for p in full_name.strip().split() if p]
    if not parts:
        return "", ""
    base = _base_surname(parts[0])
    rest = " ".join(p.lower().replace("ё", "е") for p in parts[1:])
    return base, rest


# ---------------------------------------------------------------------------
# ExcelGradebook
# ---------------------------------------------------------------------------

class ExcelGradebook(Gradebook):
    """
    Прототип журнала под конкретный формат:
      - лист "Электроснабжение" (или первый лист),
      - строка 1: №, ФИО, 10.09, 12.09, 15.09, 17.09, 19.09, ...
      - столбец B: ФИО,
      - ученики: со строки 2,
      - оценка: пересечение строки ученика и колонки даты.
    """

    DEFAULT_SHEET = "Электроснабжение"
    NAME_COL = 2
    HEADER_ROW = 1
    FIRST_STUDENT_ROW = 2

    def __init__(self) -> None:
        self.path: Optional[str] = None
        self.wb: Optional[Workbook] = None
        self.sheet_name: Optional[str] = None
        self._students: list[StudentMatch] = []
        self._row_to_name: dict[str, dict[int, str]] = {}
        self._lesson_columns: dict[str, dict[str, int]] = {}

    # --------------------------------------------------------------
    # load
    # --------------------------------------------------------------
    def load(self, path: str) -> None:
        self.path = path
        self.wb = load_workbook(path, data_only=False)

        if self.DEFAULT_SHEET in self.wb.sheetnames:
            self.sheet_name = self.DEFAULT_SHEET
        else:
            self.sheet_name = self.wb.sheetnames[0]

        self._students = []
        self._row_to_name = {}
        self._lesson_columns = {}

        self._scan_students()
        self._scan_lessons()

    # --------------------------------------------------------------
    # get_students
    # --------------------------------------------------------------
    def get_students(self) -> list[str]:
        return [s.full_name for s in self._students]

    # --------------------------------------------------------------
    # find_student
    # --------------------------------------------------------------
    def find_student(self, name: str) -> list[StudentMatch]:
        if not name:
            return []

        raw = name.strip()
        low = raw.lower().replace("ё", "е")

        exact = [s for s in self._students if s.full_name.lower().replace("ё", "е") == low]
        if exact:
            return exact

        substr = [
            s for s in self._students
            if low in s.full_name.lower().replace("ё", "е")
        ]
        if substr:
            return substr

        q_base, q_rest = _query_key(raw)
        if not q_base:
            return []

        candidates: list[StudentMatch] = []
        for s in self._students:
            f_base, f_rest = _full_name_key(s.full_name)
            if f_base != q_base:
                continue
            if q_rest and not f_rest.startswith(q_rest):
                if not _rest_matches(q_rest, f_rest):
                    continue
            candidates.append(s)

        return candidates

    # --------------------------------------------------------------
    # find_grade_target
    # --------------------------------------------------------------
    def find_grade_target(
        self,
        student: StudentMatch,
        subject: str,
        lesson: str,
    ) -> GradeTarget | None:
        if self.wb is None or self.sheet_name is None:
            return None

        if subject and subject.strip() != self.sheet_name:
            return None

        col_idx = self._lesson_columns.get(self.sheet_name, {}).get(lesson.strip())
        if col_idx is None:
            return None

        row = student.row
        column = get_column_letter(col_idx)
        cell = f"{column}{row}"

        return GradeTarget(
            student=student.full_name,
            sheet=self.sheet_name,
            row=row,
            column=column,
            cell=cell,
        )

    # --------------------------------------------------------------
    # get_grade
    # --------------------------------------------------------------
    def get_grade(self, target: GradeTarget) -> int | None:
        if self.wb is None:
            return None
        ws = self.wb[target.sheet]
        value = ws[target.cell].value
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    # --------------------------------------------------------------
    # set_grade
    # --------------------------------------------------------------
    def set_grade(self, target: GradeTarget, grade: int) -> None:
        if self.wb is None:
            raise RuntimeError("Журнал не загружен.")
        ws = self.wb[target.sheet]
        ws[target.cell] = grade

    # --------------------------------------------------------------
    # save — атомарная замена через временный файл
    # --------------------------------------------------------------
    def save(self) -> None:
        """
        Сохраняет книгу через временный файл в той же директории,
        затем атомарно заменяет оригинал через os.replace().
        До os.replace() оригинал не изменяется.
        """
        if self.wb is None:
            raise RuntimeError("Workbook не загружен.")

        if not self.path:
            raise RuntimeError("Путь к журналу не задан.")

        target = Path(self.path)
        target.parent.mkdir(parents=True, exist_ok=True)

        fd, temp_path = tempfile.mkstemp(
            prefix=f".{target.stem}_",
            suffix=".tmp.xlsx",
            dir=str(target.parent),
        )
        os.close(fd)

        try:
            # 1. Сохраняем во временный файл.
            self.wb.save(temp_path)

            # 2. Проверяем, что временный файл создан и непуст.
            if not os.path.exists(temp_path):
                raise RuntimeError("Временный файл не создан.")
            if os.path.getsize(temp_path) == 0:
                raise RuntimeError("Временный файл пуст.")

            # 3. Атомарная замена оригинала.
            os.replace(temp_path, target)

        except Exception:
            # Удаляем временный файл, если он остался.
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except OSError:
                pass
            raise

    # --------------------------------------------------------------
    # Диагностика
    # --------------------------------------------------------------
    def diagnose(self) -> str:
        if self.wb is None:
            return "Файл не загружен."

        lines: list[str] = []
        lines.append(f"Файл: {self.path}")
        lines.append(f"Активный лист: {self.sheet_name}")
        lines.append("Листы:")
        for name in self.wb.sheetnames:
            ws = self.wb[name]
            lines.append(f"  - {name}  (размер: {ws.max_row}×{ws.max_column})")

        lines.append("")
        lines.append("Ученики:")
        for s in self._students:
            lines.append(f"  строка {s.row}: {s.full_name}")

        lines.append("")
        lines.append("Занятия (заголовки):")
        for lesson, col_idx in sorted(
            self._lesson_columns.get(self.sheet_name or "", {}).items(),
            key=lambda x: x[1],
        ):
            lines.append(f"  {lesson} → колонка {get_column_letter(col_idx)}")

        return "\n".join(lines)

    # --------------------------------------------------------------
    # Внутреннее
    # --------------------------------------------------------------
    def _scan_students(self) -> None:
        assert self.wb is not None and self.sheet_name is not None
        ws = self.wb[self.sheet_name]
        row_map: dict[int, str] = {}

        for row in range(self.FIRST_STUDENT_ROW, ws.max_row + 1):
            name_cell = ws.cell(row=row, column=self.NAME_COL).value
            if name_cell is None:
                continue
            full_name = str(name_cell).strip()
            if not full_name:
                continue
            row_map[row] = full_name
            self._students.append(
                StudentMatch(full_name=full_name, row=row, sheet=self.sheet_name)
            )

        self._row_to_name[self.sheet_name] = row_map

    def _scan_lessons(self) -> None:
        assert self.wb is not None and self.sheet_name is not None
        ws = self.wb[self.sheet_name]
        lesson_cols: dict[str, int] = {}

        for col in range(1, ws.max_column + 1):
            v = ws.cell(row=self.HEADER_ROW, column=col).value
            if v is None:
                continue
            s = str(v).strip()
            if s in ("№", "ФИО", ""):
                continue
            if _looks_like_date(s):
                lesson_cols[s] = col

        self._lesson_columns[self.sheet_name] = lesson_cols


# ---------------------------------------------------------------------------
# Вспомогательные
# ---------------------------------------------------------------------------

def _rest_matches(query_rest: str, full_rest: str) -> bool:
    q_tokens = [t for t in query_rest.replace(".", " ").split() if t]
    f_tokens = [t for t in full_rest.replace(".", " ").split() if t]
    if not q_tokens:
        return True
    if len(q_tokens) > len(f_tokens):
        return False
    for q, f in zip(q_tokens, f_tokens):
        if not f.startswith(q):
            return False
    return True


def _looks_like_date(s: str) -> bool:
    import re
    return bool(re.match(
        r"^\s*\d{1,2}[./\-]\d{1,2}(?:[./\-]\d{2,4})?\s*$",
        s,
    ))
