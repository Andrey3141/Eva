# -*- coding: utf-8 -*-
"""
Alesya — read-only проверка рабочей копии головы.

Публичный API: run_test() -> None.

Тест НЕ создаёт копию сам. Копирование выполняет
character.head_work.create_work_head().

Тест ТОЛЬКО ЧИТАЕТ и печатает результат. При провале любой
проверки бросает AssertionError — тот же механизм, который
используют остальные тесты проекта, чтобы tests/main.py
пометил тест как [FAIL].
"""

import bpy


# ============================================================
# КОНФИГУРАЦИЯ
# ============================================================

SOURCE_OBJECT_NAME   = "GEO-head_animation_realistic"
WORK_OBJECT_NAME     = "Alesya_Head_Work"
WORK_COLLECTION_NAME = "Alesya_Character"

TRANSFORM_EPS = 1e-6


# ============================================================
# УТИЛИТЫ
# ============================================================

def _vec_equal(a, b, eps=TRANSFORM_EPS):
    return all(abs(a[i] - b[i]) <= eps for i in range(3))


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
    print("=== HEAD WORK COPY TEST ===")
    print()

    src = bpy.data.objects.get(SOURCE_OBJECT_NAME)
    work = bpy.data.objects.get(WORK_OBJECT_NAME)

    all_ok = True

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

    # Если чего-то нет — сразу финализируем.
    if src is None or work is None:
        print()
        if all_ok:
            print("RESULT: PASS")
        else:
            print("RESULT: FAIL")
        print()
        print("=== END HEAD WORK COPY TEST ===")
        print()
        if not all_ok:
            raise AssertionError(
                "head work copy check failed: "
                "source or work object missing"
            )
        return

    all_ok &= _print_result(
        "source.type == MESH",
        src.type == 'MESH',
        f"type={src.type}",
    )

    all_ok &= _print_result(
        "work.type == MESH",
        work.type == 'MESH',
        f"type={work.type}",
    )

    data_independent = (src.data is not work.data)
    all_ok &= _print_result(
        "source.data is not work.data",
        data_independent,
        f"src.data={src.data.name!r}  work.data={work.data.name!r}",
    )

    src_v = len(src.data.vertices)
    work_v = len(work.data.vertices)
    all_ok &= _print_result(
        "vertex_count same",
        src_v == work_v,
        f"source={src_v}  work={work_v}",
    )

    src_e = len(src.data.edges)
    work_e = len(work.data.edges)
    all_ok &= _print_result(
        "edge_count same",
        src_e == work_e,
        f"source={src_e}  work={work_e}",
    )

    src_p = len(src.data.polygons)
    work_p = len(work.data.polygons)
    all_ok &= _print_result(
        "polygon_count same",
        src_p == work_p,
        f"source={src_p}  work={work_p}",
    )

    loc_ok = _vec_equal(src.location, work.location)
    rot_ok = _vec_equal(src.rotation_euler, work.rotation_euler)
    scl_ok = _vec_equal(src.scale, work.scale)

    all_ok &= _print_result(
        "location same",
        loc_ok,
        f"source={tuple(round(v, 6) for v in src.location)}  "
        f"work={tuple(round(v, 6) for v in work.location)}",
    )
    all_ok &= _print_result(
        "rotation same",
        rot_ok,
        f"source={tuple(round(v, 6) for v in src.rotation_euler)}  "
        f"work={tuple(round(v, 6) for v in work.rotation_euler)}",
    )
    all_ok &= _print_result(
        "scale same",
        scl_ok,
        f"source={tuple(round(v, 6) for v in src.scale)}  "
        f"work={tuple(round(v, 6) for v in work.scale)}",
    )

    work_colls = [c.name for c in work.users_collection]
    in_target_coll = WORK_COLLECTION_NAME in work_colls
    all_ok &= _print_result(
        f"work in collection {WORK_COLLECTION_NAME!r}",
        in_target_coll,
        f"collections={work_colls}",
    )

    all_ok &= _print_result(
        "material slots match (count)",
        len(src.data.materials) == len(work.data.materials),
        f"source={len(src.data.materials)}  work={len(work.data.materials)}",
    )

    print()
    if all_ok:
        print("RESULT: PASS")
    else:
        print("RESULT: FAIL")
    print()
    print("=== END HEAD WORK COPY TEST ===")
    print()

    if not all_ok:
        raise AssertionError(
            "head work copy check failed: see [FAIL] lines above"
        )
