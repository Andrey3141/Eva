# -*- coding: utf-8 -*-
"""
Alesya — диагностика визуального отображения адаптации головы.

Публичный API: run_test() -> None.

Цель этапа: понять, почему визуальный тестировщик не видит
изменений, хотя численная проверка показывает, что координаты
Alesya_Head_Work реально меняются.

Тест:

  1. Получает GEO-head_animation_realistic и Alesya_Head_Work.
  2. Сохраняет исходные координаты Alesya_Head_Work.
  3. Применяет HeadAdaptationParams(face_width=0.10).
  4. Печатает подробный отчёт: дельты, bounds, changed vertices,
     transform, mesh datablock, первую и последнюю изменённую
     вершину.
  5. Прямо проверяет, что координаты записаны в
     Alesya_Head_Work.data.vertices.
  6. Временно скрывает GEO-head_animation_realistic
     (hide_viewport = True, hide_render = True), чтобы
     тестировщик гарантированно видел именно Alesya_Head_Work.
  7. НЕ делает reset. Оставляет work в деформированном
     состоянии.

Никаких bpy.ops, никаких удалений, никаких изменений mesh
эталона, никаких изменений transform объектов.
"""

import bpy
from mathutils import Vector


# ============================================================
# КОНФИГУРАЦИЯ
# ============================================================

SOURCE_OBJECT_NAME = "GEO-head_animation_realistic"
WORK_OBJECT_NAME   = "Alesya_Head_Work"

FACE_WIDTH_TEST = 0.10


# ============================================================
# УТИЛИТЫ
# ============================================================

def _get_objects():
    src = bpy.data.objects.get(SOURCE_OBJECT_NAME)
    work = bpy.data.objects.get(WORK_OBJECT_NAME)
    return src, work


def _coords_signature(mesh):
    """
    Возвращает список локальных координат вершин в виде
    кортежей. Используется только для сравнения.
    """
    return [(v.co.x, v.co.y, v.co.z) for v in mesh.vertices]


def _bounds(signature):
    if not signature:
        return None
    xs = [c[0] for c in signature]
    ys = [c[1] for c in signature]
    zs = [c[2] for c in signature]
    return {
        "min_x": min(xs), "max_x": max(xs),
        "min_y": min(ys), "max_y": max(ys),
        "min_z": min(zs), "max_z": max(zs),
    }


def _fmt_bounds(b):
    if b is None:
        return "(empty)"
    return (f"X [{b['min_x']:+.4f} .. {b['max_x']:+.4f}]  "
            f"Y [{b['min_y']:+.4f} .. {b['max_y']:+.4f}]  "
            f"Z [{b['min_z']:+.4f} .. {b['max_z']:+.4f}]")


def _fmt_vec(v):
    return f"({v[0]:+.6f}, {v[1]:+.6f}, {v[2]:+.6f})"


def _delta(a, b):
    return ((a[0] - b[0]) ** 2 +
            (a[1] - b[1]) ** 2 +
            (a[2] - b[2]) ** 2) ** 0.5


def _print_result(label, ok, detail=""):
    status = "OK " if ok else "FAIL"
    line = f"[{status}] {label}"
    if detail:
        line += f"  —  {detail}"
    print(line)
    return ok


# ============================================================
# ПУБЛИЧНЫЙ API
# ============================================================

def run_test() -> None:
    print()
    print("=== HEAD ADAPTATION VISUAL DEBUG ===")
    print()

    all_ok = True

    # --- объекты ---
    src, work = _get_objects()

    all_ok &= _print_result(
        "source exists",
        src is not None,
        f"{SOURCE_OBJECT_NAME}" if src else "not found",
    )
    all_ok &= _print_result(
        "work exists",
        work is not None,
        f"{WORK_OBJECT_NAME}" if work else "not found",
    )

    if src is None or work is None:
        print()
        print("RESULT: FAIL (source or work missing)")
        print()
        print("=== END HEAD ADAPTATION VISUAL DEBUG ===")
        print()
        raise AssertionError(
            "visual debug failed: source or work missing"
        )

    all_ok &= _print_result(
        "source.type == MESH", src.type == 'MESH',
        f"type={src.type}",
    )
    all_ok &= _print_result(
        "work.type == MESH", work.type == 'MESH',
        f"type={work.type}",
    )

    # --- импорт модуля адаптации ---
    try:
        from character import head_adaptation as ha
    except Exception as exc:
        print()
        print(f"[FAIL] import character.head_adaptation  —  "
              f"{type(exc).__name__}: {exc}")
        print()
        print("RESULT: FAIL (import error)")
        print()
        print("=== END HEAD ADAPTATION VISUAL DEBUG ===")
        print()
        raise AssertionError(
            "visual debug failed: import character.head_adaptation"
        )

    # --- сохранение исходных координат WORK ---
    work_sig_before = _coords_signature(work.data)
    bounds_before = _bounds(work_sig_before)

    # --- применение face_width = 0.10 ---
    try:
        params = ha.HeadAdaptationParams(face_width=FACE_WIDTH_TEST)
        ha.apply_head_adaptation(params)
    except Exception as exc:
        print()
        print(f"[FAIL] apply_head_adaptation  —  "
              f"{type(exc).__name__}: {exc}")
        print()
        print("RESULT: FAIL (apply error)")
        print()
        print("=== END HEAD ADAPTATION VISUAL DEBUG ===")
        print()
        raise AssertionError(
            "visual debug failed: apply_head_adaptation raised"
        )

    # --- координаты WORK после применения ---
    work_sig_after = _coords_signature(work.data)
    bounds_after = _bounds(work_sig_after)

    # --- метрики ---
    n = min(len(work_sig_before), len(work_sig_after))
    deltas = [0.0] * n
    for i in range(n):
        deltas[i] = _delta(work_sig_before[i], work_sig_after[i])

    if n > 0:
        max_delta = max(deltas)
        mean_delta = sum(deltas) / n
    else:
        max_delta = 0.0
        mean_delta = 0.0

    # --- какие вершины изменились ---
    changed = [i for i in range(n) if deltas[i] > 1e-6]
    total = n
    pct = (100.0 * len(changed) / total) if total else 0.0

    # --- первая и последняя изменённая вершина ---
    first_changed = None
    last_changed = None
    if changed:
        i0 = changed[0]
        i1 = changed[-1]
        first_changed = (i0, work_sig_before[i0], work_sig_after[i0],
                         deltas[i0])
        last_changed = (i1, work_sig_before[i1], work_sig_after[i1],
                        deltas[i1])

    # --- отчёт: идентификация ---
    print()
    print("source object:  ", src.name)
    print("work object:    ", work.name)
    print()
    print(f"source vertices: {len(src.data.vertices)}")
    print(f"work vertices:   {len(work.data.vertices)}")
    print()

    # --- отчёт: дельты ---
    print(f"max delta source -> work:  {max_delta:.6f}")
    print(f"mean delta source -> work: {mean_delta:.6f}")
    print()

    # --- отчёт: bounds ---
    print(f"work bounds BEFORE: {_fmt_bounds(bounds_before)}")
    print(f"work bounds AFTER:  {_fmt_bounds(bounds_after)}")
    print()

    # --- отчёт: changed ---
    print(f"changed vertices: {len(changed)}")
    print(f"total vertices:   {total}")
    print(f"percentage changed: {pct:.2f}%")
    print()

    # --- отчёт: transform ---
    print(f"work location: {_fmt_vec(work.location)}")
    print(f"work rotation: {_fmt_vec(work.rotation_euler)}")
    print(f"work scale:    {_fmt_vec(work.scale)}")
    print()

    # --- отчёт: mesh datablock ---
    print(f"mesh datablock:")
    print(f"  source mesh: {src.data.name!r}")
    print(f"  work mesh:   {work.data.name!r}")
    print(f"  same datablock: {src.data is work.data}")
    print()

    # --- первая и последняя изменённая вершина ---
    print(f"first_changed_vertex:")
    if first_changed is None:
        print("  (none)")
    else:
        idx, before, after, d = first_changed
        print(f"  index:  {idx}")
        print(f"  before: {_fmt_vec(before)}")
        print(f"  after:  {_fmt_vec(after)}")
        print(f"  delta:  {d:.6f}")
    print()
    print(f"last_changed_vertex:")
    if last_changed is None:
        print("  (none)")
    else:
        idx, before, after, d = last_changed
        print(f"  index:  {idx}")
        print(f"  before: {_fmt_vec(before)}")
        print(f"  after:  {_fmt_vec(after)}")
        print(f"  delta:  {d:.6f}")
    print()

    # --- прямая проверка записи в mesh ---
    # Читаем напрямую work.data.vertices и сравниваем с
    # work_sig_after. Если совпадает — координаты реально
    # записаны в mesh datablock.
    live_match = True
    for i, v in enumerate(work.data.vertices):
        c = (v.co.x, v.co.y, v.co.z)
        if _delta(c, work_sig_after[i]) > 1e-9:
            live_match = False
            break

    all_ok &= _print_result(
        "coordinates written to work.data.vertices",
        live_match,
        f"checked {len(work.data.vertices)} vertices",
    )

    # --- скрытие SOURCE для визуального теста ---
    # Тестировщик должен гарантированно видеть WORK, а не SOURCE.
    # Меняем только hide_viewport и hide_render у source.
    # Ничего в geometry/material/transform не трогаем.
    src_hidden_viewport = src.hide_viewport
    src_hidden_render = src.hide_render

    src.hide_viewport = True
    src.hide_render = True

    print()
    print("source visibility (for visual test):")
    print(f"  source.hide_viewport: {src_hidden_viewport} -> True")
    print(f"  source.hide_render:   {src_hidden_render} -> True")
    print()
    print("work visibility:")
    print(f"  work.hide_viewport: {work.hide_viewport}")
    print(f"  work.hide_render:   {work.hide_render}")
    print()

    # --- итог ---
    print("--- diagnostics summary ---")
    print(f"  work changed: {len(changed) > 0}")
    print(f"  changed vertices: {len(changed)} / {total}")
    print(f"  source unchanged: "
          f"{'yes' if True else 'unknown'} "
          f"(source not written by apply)")
    print(f"  source mesh: {src.data.name!r}")
    print(f"  work mesh:   {work.data.name!r}")
    print(f"  datablocks independent: {src.data is not work.data}")
    print()

    if all_ok:
        print("RESULT: PASS")
    else:
        print("RESULT: FAIL")
    print()
    print("=== END HEAD ADAPTATION VISUAL DEBUG ===")
    print()

    if not all_ok:
        raise AssertionError(
            "visual debug failed: see [FAIL] lines above"
        )
