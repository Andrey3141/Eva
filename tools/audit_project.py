"""
Аудит проекта EVA. Не удаляет и не меняет ничего.
Собирает:
  - список всех файлов (Python/не Python);
  - импорты внутри проекта;
  - ссылки на модули;
  - зависимости из requirements.txt;
  - использование каждого файла из assistant/, tools/, корня.
Печатает результат в stdout и пишет в logs/audit_<timestamp>.txt.

Запуск:
    python -m tools.audit_project
"""
from __future__ import annotations

import ast
import os
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules",
             ".local-browsers", "logs", "data", "assets"}


def iter_files() -> list[Path]:
    out = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            p = Path(dirpath) / fn
            if p.suffix in (".pyc",):
                continue
            out.append(p)
    return out


def extract_imports(path: Path) -> set[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(text)
    except Exception:
        return set()

    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                mods.add(n.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mods.add(node.module.split(".")[0])
    return mods


def module_name(path: Path) -> str | None:
    try:
        rel = path.relative_to(ROOT)
    except ValueError:
        return None
    if rel.suffix != ".py":
        return None
    parts = list(rel.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts else None


def main() -> int:
    files = iter_files()
    py_files = [p for p in files if p.suffix == ".py"]

    # 1. Все модули проекта
    modules = {}
    for p in py_files:
        mn = module_name(p)
        if mn:
            modules[mn] = p

    # 2. Импорты в каждом файле
    imports_per_file: dict[Path, set[str]] = {}
    for p in py_files:
        imports_per_file[p] = extract_imports(p)

    # 3. Обратные ссылки: кто импортирует модуль X
    referrers: dict[str, set[str]] = {m: set() for m in modules}
    for p, mods in imports_per_file.items():
        mn = module_name(p)
        for m in mods:
            # Ищем первый модуль, который начинается с этого имени.
            for candidate in modules:
                if candidate == m or candidate.startswith(m + "."):
                    if mn != candidate:
                        referrers.setdefault(candidate, set()).add(mn or str(p))

    # 4. requirements.txt
    reqs: list[str] = []
    req_path = ROOT / "requirements.txt"
    if req_path.is_file():
        for line in req_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                reqs.append(line)

    # 5. Ссылки на имена файлов из корня (main.py, config.py)
    root_files = [p for p in files if p.parent == ROOT]
    root_refs: dict[str, set[str]] = {p.name: set() for p in root_files}
    for p in py_files:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for name in root_refs:
            stem = Path(name).stem
            if re.search(rf"\b{re.escape(stem)}\b", text) and p.name != name:
                root_refs[name].add(str(p.relative_to(ROOT)))

    # 6. Формируем отчёт
    lines: list[str] = []
    lines.append(f"EVA PROJECT AUDIT — {datetime.now().isoformat()}")
    lines.append(f"Root: {ROOT}")
    lines.append(f"Files total: {len(files)}")
    lines.append(f"Python files: {len(py_files)}")
    lines.append("")

    lines.append("=== ROOT FILES ===")
    for p in root_files:
        lines.append(f"  {p.name}")
        for ref in sorted(root_refs.get(p.name, ())):
            lines.append(f"      referenced by: {ref}")
    lines.append("")

    lines.append("=== PYTHON MODULES (assistant/, tools/, root) ===")
    for mn in sorted(modules):
        p = modules[mn]
        refs = sorted(referrers.get(mn, ()))
        lines.append(f"  {mn}  ->  {p.relative_to(ROOT)}")
        if refs:
            lines.append(f"      imported by: {', '.join(refs)}")
        else:
            lines.append(f"      imported by: <none>")
    lines.append("")

    lines.append("=== REQUIREMENTS.TXT ===")
    for r in reqs:
        lines.append(f"  {r}")
    lines.append("")

    lines.append("=== TOOLS ===")
    for p in sorted((ROOT / "tools").glob("*.py")):
        mn = module_name(p)
        refs = sorted(referrers.get(mn or "", ()))
        lines.append(f"  {p.relative_to(ROOT)}  (module={mn})")
        lines.append(f"      imported by: {', '.join(refs) or '<none>'}")

    report = "\n".join(lines)
    print(report, flush=True)

    out_dir = ROOT / "logs"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / f"audit_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt"
    out_file.write_text(report, encoding="utf-8")
    print(f"\n[audit] written to {out_file}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
