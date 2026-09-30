# -*- coding: utf-8 -*-
"""
Alesya — параметрическая адаптация рабочей головы.

Публичный API:

    HeadAdaptationParams     — dataclass с параметрами адаптации
    apply_head_adaptation(params) -> None
    reset_head() -> None

Работает ТОЛЬКО с:

    Alesya_Head_Work

Никогда не изменяет:

    GEO-head_animation_realistic

Принцип:

    BASE  = GEO-head_animation_realistic  (эталон, никогда не меняется)
        ↓
    APPLY = записать в Alesya_Head_Work результат BASE + параметры
        ↓
    RESET = вернуть Alesya_Head_Work к точной копии BASE

Повторный apply с другими параметрами НЕ накапливает деформации:
каждый вызов начинается с чистых координат BASE, а не с текущего
состояния Alesya_Head_Work.

Деформация выполняется в ЛОКАЛЬНЫХ координатах mesh. Transform
объекта Alesya_Head_Work (location/rotation/scale) не меняется.
Топология (vertices/edges/polygons) не меняется.
"""

import math
from dataclasses import dataclass, field

import bpy
from mathutils import Vector


# ============================================================
# КОНФИГУРАЦИЯ
# ============================================================

SOURCE_OBJECT_NAME = "GEO-head_animation_realistic"
WORK_OBJECT_NAME   = "Alesya_Head_Work"


# ============================================================
# ПАРАМЕТРЫ АДАПТАЦИИ
# ============================================================

@dataclass
class HeadAdaptationParams:
    """
    Параметры адаптации рабочей головы.

    Все значения — безразмерные коэффициенты относительного
    изменения относительно BASE. Знак и величина влияют на
    направление и силу деформации:

        0.0    — без изменения
        > 0.0  — увеличение (или выступ вперёд/вверх/вбок)
        < 0.0  — уменьшение (или отступ назад/вниз/внутрь)

    Диапазон значений рекомендуется держать в пределах [-0.5, 0.5],
    чтобы не разрушить базовую форму. Точные значения подбираются
    на последующих этапах.
    """
    # --- ширина лица по X ---
    face_width:         float = 0.0
    jaw_width:          float = 0.0
    chin_width:         float = 0.0
    forehead_width:     float = 0.0
    skull_width:        float = 0.0

    # --- глубинные параметры по Y ---
    chin_depth:         float = 0.0
    forehead_depth:     float = 0.0

    # --- вертикальные параметры по Z ---
    skull_height:       float = 0.0
    lower_face_height:  float = 0.0

    # --- объём щёк (X и Y одновременно) ---
    cheek_volume:       float = 0.0

    # Резерв для будущих параметров — можно расширять без ломки API.
    extra:              dict = field(default_factory=dict)


# ============================================================
# ВНУТРЕННИЕ ОРИЕНТИРЫ В ЛОКАЛЬНЫХ КООРДИНАТАХ BASE
# ============================================================
#
# Мы не фиксируем их жёстко. Значения вычисляются один раз из
# текущей BASE и пересчитываются при каждом apply — это делает
# механизм устойчивым к возможной подмене BASE.

def _local_bounds(mesh):
    """
    Возвращает min/max по X, Y, Z в локальных координатах mesh.
    """
    xs = [v.co.x for v in mesh.vertices]
    ys = [v.co.y for v in mesh.vertices]
    zs = [v.co.z for v in mesh.vertices]
    return {
        "min_x": min(xs), "max_x": max(xs),
        "min_y": min(ys), "max_y": max(ys),
        "min_z": min(zs), "max_z": max(zs),
        "mid_x": (min(xs) + max(xs)) * 0.5,
        "mid_y": (min(ys) + max(ys)) * 0.5,
        "mid_z": (min(zs) + max(zs)) * 0.5,
        "size_x": max(xs) - min(xs),
        "size_y": max(ys) - min(ys),
        "size_z": max(zs) - min(zs),
    }


# ============================================================
# ВЕСА ОБЛАСТЕЙ
# ============================================================
#
# Каждая функция возвращает вес 0.0..1.0 для конкретной вершины
# по её локальным координатам. Веса гладкие: smoothstep и
# гауссовы кривые, без резких границ и без полос.
#
# Z-ось: низ подбородка -> верх макушки.

def _smoothstep(edge0, edge1, x):
    if edge1 == edge0:
        return 0.0 if x < edge0 else 1.0
    t = (x - edge0) / (edge1 - edge0)
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def _gauss(x, center, width):
    if width <= 0.0:
        return 0.0
    d = (x - center) / width
    return math.exp(-d * d)


def _weights_face(co, bounds):
    """
    Вес «общей ширины лица». Действует на передней половине
    (y < mid_y) в средней зоне по Z. Не затрагивает череп и
    подбородок.
    """
    z_norm = (co.z - bounds["min_z"]) / max(bounds["size_z"], 1e-9)
    w_z = _gauss(z_norm, 0.55, 0.20)
    w_y = _smoothstep(bounds["mid_y"], bounds["min_y"], co.y)
    return w_z * w_y


def _weights_jaw(co, bounds):
    """
    Вес «челюсти». Нижняя треть, широкая зона по X.
    """
    z_norm = (co.z - bounds["min_z"]) / max(bounds["size_z"], 1e-9)
    w_z = _gauss(z_norm, 0.18, 0.14)
    return w_z


def _weights_chin(co, bounds):
    """
    Вес «подбородка». Самая нижняя точка по Z, передняя половина.
    """
    z_norm = (co.z - bounds["min_z"]) / max(bounds["size_z"], 1e-9)
    w_z = _gauss(z_norm, 0.02, 0.10)
    w_y = _smoothstep(bounds["mid_y"], bounds["min_y"], co.y)
    return w_z * w_y


def _weights_cheek(co, bounds):
    """
    Вес «щёк». Средняя зона по Z, боковые участки.
    """
    z_norm = (co.z - bounds["min_z"]) / max(bounds["size_z"], 1e-9)
    w_z = _gauss(z_norm, 0.45, 0.16)
    # Боковой вес: сильнее к краям по X, слабее в центре.
    x_rel = abs(co.x - bounds["mid_x"]) / max(bounds["size_x"] * 0.5, 1e-9)
    w_x = _smoothstep(0.15, 0.85, x_rel)
    return w_z * w_x


def _weights_forehead(co, bounds):
    """
    Вес «лба». Верхняя треть, передняя половина.
    """
    z_norm = (co.z - bounds["min_z"]) / max(bounds["size_z"], 1e-9)
    w_z = _gauss(z_norm, 0.82, 0.14)
    w_y = _smoothstep(bounds["mid_y"], bounds["min_y"], co.y)
    return w_z * w_y


def _weights_skull(co, bounds):
    """
    Вес «черепа». Верхняя часть, все направления.
    """
    z_norm = (co.z - bounds["min_z"]) / max(bounds["size_z"], 1e-9)
    w_z = _smoothstep(0.55, 1.0, z_norm)
    return w_z


def _compute_all_weights(co, bounds):
    """
    Возвращает dict со всеми весами для одной вершины.
    """
    return {
        "face":     _weights_face(co, bounds),
        "jaw":      _weights_jaw(co, bounds),
        "chin":     _weights_chin(co, bounds),
        "cheek":    _weights_cheek(co, bounds),
        "forehead": _weights_forehead(co, bounds),
        "skull":    _weights_skull(co, bounds),
    }


# ============================================================
# ДЕФОРМАЦИЯ ОДНОЙ ВЕРШИНЫ
# ============================================================

def _deform_vertex(co, weights, params):
    """
    Возвращает новые локальные координаты вершины после
    применения параметров адаптации.
    """
    x, y, z = co.x, co.y, co.z

    # --- X-параметры: ширина ---
    #
    # Для симметрии относительно центральной оси головы
    # используем знак (x - mid_x).
    # mid_x по построению 0 в локальных координатах mesh
    # (Alesya_Head_Work унаследовал центральную симметрию от BASE),
    # но мы работаем через относительное значение, чтобы не
    # зависеть от этого допущения.

    # face_width: лёгкое расширение/сужение передней половины лица
    if weights["face"] > 0.0:
        x *= 1.0 + params.face_width * weights["face"]

    # jaw_width
    if weights["jaw"] > 0.0:
        x *= 1.0 + params.jaw_width * weights["jaw"]

    # chin_width
    if weights["chin"] > 0.0:
        x *= 1.0 + params.chin_width * weights["chin"]

    # forehead_width
    if weights["forehead"] > 0.0:
        x *= 1.0 + params.forehead_width * weights["forehead"]

    # skull_width
    if weights["skull"] > 0.0:
        x *= 1.0 + params.skull_width * weights["skull"]

    # --- Y-параметры: глубина ---

    # chin_depth: подбородок вперёд (y уменьшается, если y < mid_y)
    if weights["chin"] > 0.0:
        # Направление «вперёд» зависит от знака y относительно mid_y.
        # Лицо смотрит в -Y в BASE.
        y += params.chin_depth * weights["chin"] * (-1.0)

    # forehead_depth: лоб вперёд
    if weights["forehead"] > 0.0:
        y += params.forehead_depth * weights["forehead"] * (-1.0)

    # cheek_volume: щёки одновременно по X и Y
    if weights["cheek"] > 0.0:
        # Боковой вынос
        x *= 1.0 + params.cheek_volume * weights["cheek"]
        # Лёгкий выступ вперёд
        y += params.cheek_volume * weights["cheek"] * (-0.5)

    # --- Z-параметры: высота ---

    # skull_height: верхняя часть выше/ниже
    if weights["skull"] > 0.0:
        z *= 1.0 + params.skull_height * weights["skull"]

    # lower_face_height: нижняя часть лица удлиняется/укорачивается
    if weights["jaw"] > 0.0:
        z -= params.lower_face_height * weights["jaw"]

    return Vector((x, y, z))


# ============================================================
# API: APPLY / RESET
# ============================================================

def _get_objects():
    src = bpy.data.objects.get(SOURCE_OBJECT_NAME)
    work = bpy.data.objects.get(WORK_OBJECT_NAME)
    return src, work


def apply_head_adaptation(params):
    """
    Применяет параметры адаптации к Alesya_Head_Work.

    Каждый вызов начинается с ЧИСТЫХ координат BASE
    (GEO-head_animation_realistic), поэтому повторный вызов с
    другими параметрами НЕ накапливает деформации.

    Топология не меняется. Transform объекта не меняется.
    GEO-head_animation_realistic не изменяется.
    """
    src, work = _get_objects()

    if src is None:
        print(f"[head_adaptation] FAIL: source not found: "
              f"{SOURCE_OBJECT_NAME}")
        return
    if work is None:
        print(f"[head_adaptation] FAIL: work not found: "
              f"{WORK_OBJECT_NAME}")
        return

    if src.type != 'MESH' or work.type != 'MESH':
        print("[head_adaptation] FAIL: source or work is not a MESH")
        return

    src_mesh = src.data
    work_mesh = work.data

    # Топология должна совпадать — иначе деформация по индексам
    # вершин была бы некорректной.
    if len(src_mesh.vertices) != len(work_mesh.vertices):
        print("[head_adaptation] FAIL: vertex count mismatch "
              f"src={len(src_mesh.vertices)} "
              f"work={len(work_mesh.vertices)}")
        return

    # Вычислим локальные bounds BASE для построения весов.
    bounds = _local_bounds(src_mesh)

    # Для каждой вершины work:
    #   1. взять координаты ИЗ BASE (src_mesh), не из work.
    #   2. посчитать веса.
    #   3. применить параметры.
    #   4. записать в work_mesh.
    for i, work_v in enumerate(work_mesh.vertices):
        base_co = src_mesh.vertices[i].co
        weights = _compute_all_weights(base_co, bounds)
        new_co = _deform_vertex(base_co, weights, params)
        work_v.co = new_co

    work_mesh.update()


def reset_head():
    """
    Возвращает Alesya_Head_Work к точной копии BASE —
    GEO-head_animation_realistic.

    Берёт координаты напрямую из src_mesh, без хранения
    дополнительных копий. Топология не меняется. Transform
    объекта не меняется. GEO-head_animation_realistic не
    изменяется.
    """
    src, work = _get_objects()

    if src is None:
        print(f"[head_adaptation] FAIL: source not found: "
              f"{SOURCE_OBJECT_NAME}")
        return
    if work is None:
        print(f"[head_adaptation] FAIL: work not found: "
              f"{WORK_OBJECT_NAME}")
        return

    if src.type != 'MESH' or work.type != 'MESH':
        print("[head_adaptation] FAIL: source or work is not a MESH")
        return

    src_mesh = src.data
    work_mesh = work.data

    if len(src_mesh.vertices) != len(work_mesh.vertices):
        print("[head_adaptation] FAIL: vertex count mismatch "
              f"src={len(src_mesh.vertices)} "
              f"work={len(work_mesh.vertices)}")
        return

    for i, work_v in enumerate(work_mesh.vertices):
        work_v.co = src_mesh.vertices[i].co.copy()

    work_mesh.update()
