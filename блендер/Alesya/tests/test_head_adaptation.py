# -*- coding: utf-8 -*-
"""
Alesya — read-only технический тест параметрической адаптации.

Публичный API: run_test() -> None.

Тест работает с существующими объектами:

    GEO-head_animation_realistic   (BASE, никогда не меняется)
    Alesya_Head_Work               (рабочая копия)

Тест НЕ создаёт объекты и НЕ удаляет сцену.

Тест проверяет:

  1. Оба объекта существуют, оба — MESH.
  2. Нейтральные параметры (все = 0.0):
       * topology сохраняется;
       * координаты Alesya_Head_Work совпадают с BASE
         (в пределах численной погрешности).
  3. После небольшой деформации (face_width ≠ 0):
       * Alesya_Head_Work изменился;
       * GEO-head_animation_realistic НЕ изменился;
       * топология Alesya_Head_Work не изменилась.
  4. reset_head() возвращает Alesya_Head_Work к BASE.

При провале любой проверки бросается AssertionError — тот же
механизм, что используют остальные тесты проекта.
"""

import bpy


# ============================================================
# КОНФИГУРАЦИЯ
# ============================================================

SOURCE_OBJECT_NAME = "GEO-head_animation_realistic"
WORK_OBJECT_NAME   = "Alesya_Head_Work"

COORD_EPS = 1e-6


# ============================================================
# УТИЛИТЫ
# ============================================================

def _print_result(label, ok, detail=""):
    status = "OK " if ok else "FAIL"
    line = f"[{status}] {label}"
    if detail:
        line += f"  —  {detail}"
    print(line)
    return ok


def _mesh_signature(mesh):
    """
    Простая сигнатура: список координат вершин в локальных
    координатах. Используется только для сравнения.
    """
    return [(v.co.x, v.co.y, v.co.z) for v in mesh.vertices]


def _max_coord_delta(sig_a, sig_b):
    if len(sig_a) != len(sig_b):
        return float("inf")
    m = 0.0
    for a, b in zip(sig_a, sig_b):
        for i in range(3):
            d = abs(a[i] - b[i])
            if d > m:
                m = d
    return m


def _counts(mesh):
    return (
        len(mesh.vertices),
        len(mesh.edges),
        len(mesh.polygons),
    )


# ============================================================
# ПУБЛИЧНЫЙ API
# ============================================================

def run_test() -> None:
    print()
    print("=== HEAD ADAPTATION TEST ===")
    print()

    all_ok = True

    # --- импорт адаптации ---
    try:
        from character import head_adaptation as ha
    except Exception as exc:
        all_ok &= _print_result(
            "import character.head_adaptation",
            False,
            f"{type(exc).__name__}: {exc}",
        )
        print()
        print("RESULT: FAIL")
        print()
        print("=== END HEAD ADAPTATION TEST ===")
        print()
        raise AssertionError(
            "head adaptation test failed: import error"
        )

    # --- объекты ---
    src = bpy.data.objects.get(SOURCE_OBJECT_NAME)
    work = bpy.data.objects.get(WORK_OBJECT_NAME)

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
        print("RESULT: FAIL")
        print()
        print("=== END HEAD ADAPTATION TEST ===")
        print()
        raise AssertionError(
            "head adaptation test failed: source or work missing"
        )

    all_ok &= _print_result(
        "source.type == MESH", src.type == 'MESH',
        f"type={src.type}",
    )
    all_ok &= _print_result(
        "work.type == MESH", work.type == 'MESH',
        f"type={work.type}",
    )

    # --- базовые сигнатуры ---
    src_counts_before = _counts(src.data)
    work_counts_before = _counts(work.data)

    src_sig_before = _mesh_signature(src.data)

    # =========================================================
    # 1. Нейтральные параметры
    # =========================================================
    print()
    print("--- neutral parameters (all = 0.0) ---")

    try:
        params_neutral = ha.HeadAdaptationParams()
        ha.apply_head_adaptation(params_neutral)
    except Exception as exc:
        all_ok &= _print_result(
            "apply_head_adaptation (neutral)",
            False,
            f"{type(exc).__name__}: {exc}",
        )
        print()
        print("RESULT: FAIL")
        print()
        print("=== END HEAD ADAPTATION TEST ===")
        print()
        raise AssertionError(
            "head adaptation test failed: neutral apply error"
        )

    work_counts_after_neutral = _counts(work.data)
    all_ok &= _print_result(
        "topology unchanged after neutral apply",
        work_counts_before == work_counts_after_neutral,
        f"before={work_counts_before}  after={work_counts_after_neutral}",
    )

    work_sig_neutral = _mesh_signature(work.data)
    delta = _max_coord_delta(src_sig_before, work_sig_neutral)
    all_ok &= _print_result(
        "work == base after neutral apply",
        delta <= COORD_EPS,
        f"max_delta={delta:.9f}",
    )

    # =========================================================
    # 2. Тестовая деформация
    # =========================================================
    print()
    print("--- test deformation (face_width = 0.08) ---")

    src_sig_reference = _mesh_signature(src.data)

    try:
        params_test = ha.HeadAdaptationParams(face_width=0.08)
        ha.apply_head_adaptation(params_test)
    except Exception as exc:
        all_ok &= _print_result(
            "apply_head_adaptation (face_width=0.08)",
            False,
            f"{type(exc).__name__}: {exc}",
        )
        print()
        print("RESULT: FAIL")
        print()
        print("=== END HEAD ADAPTATION TEST ===")
        print()
        raise AssertionError(
            "head adaptation test failed: test apply error"
        )

    work_sig_deformed = _mesh_signature(work.data)
    delta_deformed = _max_coord_delta(src_sig_before, work_sig_deformed)
    all_ok &= _print_result(
        "work changed after face_width=0.08",
        delta_deformed > COORD_EPS,
        f"max_delta_vs_base={delta_deformed:.6f}",
    )

    src_sig_after = _mesh_signature(src.data)
    delta_src = _max_coord_delta(src_sig_reference, src_sig_after)
    all_ok &= _print_result(
        "source unchanged after apply",
        delta_src <= COORD_EPS,
        f"max_delta={delta_src:.9f}",
    )

    work_counts_deformed = _counts(work.data)
    all_ok &= _print_result(
        "topology unchanged after deformation",
        work_counts_before == work_counts_deformed,
        f"before={work_counts_before}  after={work_counts_deformed}",
    )

    # =========================================================
    # 3. reset_head
    # =========================================================
    print()
    print("--- reset_head() ---")

    try:
        ha.reset_head()
    except Exception as exc:
        all_ok &= _print_result(
            "reset_head()",
            False,
            f"{type(exc).__name__}: {exc}",
        )
        print()
        print("RESULT: FAIL")
        print()
        print("=== END HEAD ADAPTATION TEST ===")
        print()
        raise AssertionError(
            "head adaptation test failed: reset error"
        )

    work_sig_reset = _mesh_signature(work.data)
    delta_reset = _max_coord_delta(src_sig_before, work_sig_reset)
    all_ok &= _print_result(
        "work == base after reset",
        delta_reset <= COORD_EPS,
        f"max_delta={delta_reset:.9f}",
    )

    work_counts_reset = _counts(work.data)
    all_ok &= _print_result(
        "topology unchanged after reset",
        work_counts_before == work_counts_reset,
        f"before={work_counts_before}  after={work_counts_reset}",
    )

    # =========================================================
    # Итог
    # =========================================================
    print()
    if all_ok:
        print("RESULT: PASS")
    else:
        print("RESULT: FAIL")
    print()
    print("=== END HEAD ADAPTATION TEST ===")
    print()

    if not all_ok:
        raise AssertionError(
            "head adaptation test failed: see [FAIL] lines above"
        )
