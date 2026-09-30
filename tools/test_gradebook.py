"""
Проверка ExcelGradebook.
Запуск через pytest:
    pytest -v tools/test_gradebook.py
Прямой запуск:
    python -m tools.test_gradebook
"""
import os
import sys

from assistant import paths
from assistant.gradebook import ExcelGradebook


PATH = str(paths.gradebook_path())
SUBJECT = "Электроснабжение"
LESSON = "17.09"


def _require_file():
    if not os.path.exists(PATH):
        raise RuntimeError(
            f"Файл не найден: {PATH}. "
            "Создайте его: python -m tools.make_test_gradebook"
        )


def test_gradebook_loads():
    _require_file()
    gb = ExcelGradebook()
    gb.load(PATH)
    assert gb.sheet_name == SUBJECT, gb.sheet_name


def test_find_student_ivanov():
    _require_file()
    gb = ExcelGradebook()
    gb.load(PATH)
    m = gb.find_student("Иванов")
    assert len(m) == 1, f"Иванов: найдено {len(m)}"
    assert m[0].full_name.startswith("Иванов")


def test_find_student_sidorov():
    _require_file()
    gb = ExcelGradebook()
    gb.load(PATH)
    m = gb.find_student("Сидоров")
    assert len(m) == 1, f"Сидоров: найдено {len(m)}"
    assert m[0].full_name.startswith("Сидоров")


def test_find_student_missing():
    _require_file()
    gb = ExcelGradebook()
    gb.load(PATH)
    m = gb.find_student("Гарри Поттер")
    assert len(m) == 0


def test_lesson_column():
    _require_file()
    gb = ExcelGradebook()
    gb.load(PATH)
    m = gb.find_student("Иванов")
    assert len(m) == 1
    t = gb.find_grade_target(m[0], SUBJECT, LESSON)
    assert t is not None, f"Занятие {LESSON} не найдено"
    assert t.column == "F", t.column


def test_grade_empty_and_filled():
    _require_file()
    gb = ExcelGradebook()
    gb.load(PATH)

    # Иванов на 17.09 — пусто
    m = gb.find_student("Иванов")
    t = gb.find_grade_target(m[0], SUBJECT, LESSON)
    assert t is not None
    assert gb.get_grade(t) is None

    # Сидоров на 17.09 — 5
    ms = gb.find_student("Сидоров")
    ts = gb.find_grade_target(ms[0], SUBJECT, LESSON)
    assert ts is not None
    assert gb.get_grade(ts) == 5


def main():
    print("=== GRADEBOOK TEST ===", flush=True)
    print(f"Файл: {PATH}", flush=True)
    print(f"Предмет: {SUBJECT}", flush=True)
    print(f"Занятие: {LESSON}", flush=True)
    print(flush=True)

    if not os.path.exists(PATH):
        print(f"[FAIL] Файл не найден: {PATH}", flush=True)
        print("Создайте его: python -m tools.make_test_gradebook", flush=True)
        sys.exit(1)

    test_gradebook_loads()
    print("[OK] Файл загружен", flush=True)
    test_find_student_ivanov()
    print("[OK] Найден Иванов", flush=True)
    test_find_student_sidorov()
    print("[OK] Найден Сидоров", flush=True)
    test_find_student_missing()
    print("[OK] Несуществующий ученик — 0 совпадений", flush=True)
    test_lesson_column()
    print(f"[OK] Занятие {LESSON} → колонка F", flush=True)
    test_grade_empty_and_filled()
    print("[OK] Пустая и заполненная ячейка проверены", flush=True)

    print(flush=True)
    print("=== ALL TESTS PASSED ===", flush=True)


if __name__ == "__main__":
    main()
