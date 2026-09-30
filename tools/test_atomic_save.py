"""
Тесты атомарного сохранения ExcelGradebook.
Работают в системной temp-директории, исходный журнал не трогают.

Запуск:
    python -m tools.test_atomic_save
"""
import os
import shutil
from pathlib import Path

from assistant import paths
from assistant.gradebook import ExcelGradebook
from assistant.gradebook.base import GradeTarget


SOURCE_PATH = str(paths.gradebook_path())
TMP_DIR = str(paths.temp_dir() / "eva_atomic_test")
SUBJECT = "Электроснабжение"


def _fresh_copy(tag: str) -> str:
    if not os.path.exists(SOURCE_PATH):
        raise RuntimeError(
            f"Нет исходного журнала {SOURCE_PATH}. "
            "Сначала выполните: python -m tools.make_test_gradebook"
        )
    os.makedirs(TMP_DIR, exist_ok=True)
    dst = os.path.join(TMP_DIR, f"gradebook_{tag}.xlsx")
    shutil.copyfile(SOURCE_PATH, dst)
    return dst


def _cleanup():
    if os.path.isdir(TMP_DIR):
        shutil.rmtree(TMP_DIR, ignore_errors=True)


def _temp_files_near(path: str) -> list[str]:
    p = Path(path)
    return [
        str(f) for f in p.parent.iterdir()
        if f.name.startswith(f".{p.stem}_") and f.name.endswith(".tmp.xlsx")
    ]


def _read_cell(path: str, cell: str, sheet: str = SUBJECT):
    gb = ExcelGradebook()
    gb.load(path)
    return gb.wb[sheet][cell].value


def test_a():
    print("\nA. Обычное сохранение", flush=True)
    path = _fresh_copy("a")

    gb = ExcelGradebook()
    gb.load(path)

    matches = gb.find_student("Иванов")
    assert len(matches) == 1, f"Иванов: {len(matches)} совпадений"
    target = gb.find_grade_target(matches[0], SUBJECT, "17.09")
    assert target is not None, "target не найден"
    assert gb.get_grade(target) is None, "F2 должен быть пуст"

    gb.set_grade(target, 4)
    gb.save()

    verify = ExcelGradebook()
    verify.load(path)
    vm = verify.find_student("Иванов")
    vt = verify.find_grade_target(vm[0], SUBJECT, "17.09")
    assert verify.get_grade(vt) == 4, f"F2 = {verify.get_grade(vt)}, ожидалось 4"

    leftovers = _temp_files_near(path)
    assert not leftovers, f"Остались временные файлы: {leftovers}"

    print("[OK]", flush=True)


def test_b():
    print("\nB. Ошибка сохранения временного файла", flush=True)
    path = _fresh_copy("b")

    gb = ExcelGradebook()
    gb.load(path)
    matches = gb.find_student("Иванов")
    target = gb.find_grade_target(matches[0], SUBJECT, "17.09")
    assert target is not None
    assert gb.get_grade(target) is None

    original_wb_save = gb.wb.save

    def broken_save(_path):
        raise RuntimeError("disk full")

    gb.wb.save = broken_save

    raised = False
    try:
        gb.set_grade(target, 4)
        try:
            gb.save()
        except RuntimeError:
            raised = True
    finally:
        gb.wb.save = original_wb_save

    assert raised, "Ожидалось RuntimeError"

    verify = ExcelGradebook()
    verify.load(path)
    vm = verify.find_student("Иванов")
    vt = verify.find_grade_target(vm[0], SUBJECT, "17.09")
    assert verify.get_grade(vt) is None, \
        f"F2 должен остаться пустым, получено {verify.get_grade(vt)}"

    leftovers = _temp_files_near(path)
    assert not leftovers, f"Остались временные файлы: {leftovers}"

    print("[OK]", flush=True)


def test_c():
    print("\nC. Ошибка атомарной замены", flush=True)
    path = _fresh_copy("c")

    gb = ExcelGradebook()
    gb.load(path)
    matches = gb.find_student("Иванов")
    target = gb.find_grade_target(matches[0], SUBJECT, "17.09")
    assert target is not None
    assert gb.get_grade(target) is None

    original_replace = os.replace

    def broken_replace(src, dst):
        raise OSError("replace failed")

    os.replace = broken_replace

    raised = False
    try:
        gb.set_grade(target, 4)
        try:
            gb.save()
        except OSError:
            raised = True
    finally:
        os.replace = original_replace

    assert raised, "Ожидалось OSError"

    verify = ExcelGradebook()
    verify.load(path)
    vm = verify.find_student("Иванов")
    vt = verify.find_grade_target(vm[0], SUBJECT, "17.09")
    assert verify.get_grade(vt) is None, \
        f"F2 должен остаться пустым, получено {verify.get_grade(vt)}"

    leftovers = _temp_files_near(path)
    assert not leftovers, f"Остались временные файлы: {leftovers}"

    print("[OK]", flush=True)


def test_d():
    print("\nD. Проверка повторной загрузкой", flush=True)
    path = _fresh_copy("d")

    gb = ExcelGradebook()
    gb.load(path)
    matches = gb.find_student("Сидоров")
    target = gb.find_grade_target(matches[0], SUBJECT, "17.09")
    assert target is not None
    assert gb.get_grade(target) == 5

    gb.set_grade(target, 3)
    gb.save()

    verify = ExcelGradebook()
    verify.load(path)
    vm = verify.find_student("Сидоров")
    vt = verify.find_grade_target(vm[0], SUBJECT, "17.09")
    assert verify.get_grade(vt) == 3, \
        f"F3 = {verify.get_grade(vt)}, ожидалось 3"

    assert gb.get_grade(target) == 3

    leftovers = _temp_files_near(path)
    assert not leftovers, f"Остались временные файлы: {leftovers}"

    print("[OK]", flush=True)


def main():
    if not os.path.exists(SOURCE_PATH):
        print("Сначала создайте журнал: python -m tools.make_test_gradebook", flush=True)
        return

    print("=== ATOMIC SAVE TEST ===", flush=True)
    try:
        test_a()
        test_b()
        test_c()
        test_d()
    finally:
        _cleanup()

    print("\n=== ALL ATOMIC SAVE TESTS PASSED ===", flush=True)


if __name__ == "__main__":
    main()
