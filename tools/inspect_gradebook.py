"""
Диагностика структуры .xlsx-журнала.
Путь передаётся аргументом; никаких встроенных относительных путей.

Запуск:
    python -m tools.inspect_gradebook path/to/journal.xlsx
"""
import sys

from assistant.gradebook import ExcelGradebook


def main():
    if len(sys.argv) < 2:
        print("Использование: python -m tools.inspect_gradebook <path.xlsx>", flush=True)
        sys.exit(1)

    gb = ExcelGradebook()
    gb.load(sys.argv[1])
    print(gb.diagnose(), flush=True)


if __name__ == "__main__":
    main()
