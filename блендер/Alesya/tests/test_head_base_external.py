# -*- coding: utf-8 -*-
"""
Alesya — read-only топологический аудит внешней base mesh головы.

Публичный API: run_test() -> None.

Работает с уже импортированным объектом:

    GEO-head_animation_realistic

в коллекции Alesya_Head_Base_Experiment.

Дополнительно печатает статистику по отдельным глазным мешам:

    GEO-head_animation_realistic.sclera.L
    GEO-head_animation_realistic.sclera.R
    GEO-head_animation_realistic.iris.L
    GEO-head_animation_realistic.iris.R

Тест строго read-only:
  * не удаляет объекты;
  * не переименовывает;
  * не меняет mesh;
  * не применяет модификаторы;
  * не использует bpy.ops;
  * не меняет сцену;
  * не меняет bpy.data.

Симметрия проверяется относительно ЦЕНТРАЛЬНОЙ X-плоскости
самой головы:

    center_x = (min_x + max_x) / 2
    mirror_x = 2 * center_x - x

Поиск зеркальной вершины идёт через пространственную сетку
с ячейкой SEARCH_CELL_SIZE, а не через точное совпадение
округлённых координат. Это устойчиво к небольшим численным
различиям между L и R половинами.
"""

import math
from collections import defaultdict

import bpy
from mathutils import Vector


# ============================================================
# КОНФИГУРАЦИЯ
# ============================================================

MAIN_HEAD_NAME   = "GEO-head_animation_realistic"

EYE_MESH_NAMES = [
    "GEO-head_animation_realistic.sclera.L",
    "GEO-head_animation_realistic.sclera.R",
    "GEO-head_animation_realistic.iris.L",
    "GEO-head_animation_realistic.iris.R",
]

# Размер ячейки пространственной сетки для поиска ближайшей
# зеркальной вершины. Голова имеет размеры порядка 0.27 м по X,
# поэтому ячейка 0.001 м даёт ~270 ячеек по X, этого достаточно
# для быстрого поиска ближайших кандидатов без полного перебора.
SEARCH_CELL_SIZE = 0.001

# Допустимое расстояние между вершиной и найденной зеркальной
# парой. Голова имеет масштаб ~0.27 м, поэтому 2 мм — это
# разумная tolerance для стилизованной/сканированной модели.
# Не подбираем значение ради 100% match.
SYMMETRY_MATCH_TOLERANCE = 0.002

# Оставлен для служебных точных сравнений (например, если
# потребуется точное совпадение в других местах). В проверке
# симметрии больше НЕ используется как условие совпадения.
SYMMETRY_LOOKUP_EPS = 1e-4

DEGENERATE_AREA_EPS = 1e-9


# ============================================================
# УТИЛИТЫ
# ============================================================

def _find_object(name):
    return bpy.data.objects.get(name)


def _print_not_found(name):
    print()
    print("=== EXTERNAL HEAD TOPOLOGY ===")
    print()
    print(f"{name} not found")
    print()
    print("To proceed, import a human head base mesh and give it")
    print(f"the exact object name:")
    print(f"    {name}")
    print()
    print("=== END EXTERNAL HEAD TOPOLOGY ===")
    print()


# ============================================================
# TOPOLOGY METRICS
# ============================================================

def _face_classification(mesh):
    tri = 0
    quad = 0
    ngon = 0
    other = 0
    for poly in mesh.polygons:
        n = len(poly.vertices)
        if n == 3:
            tri += 1
        elif n == 4:
            quad += 1
        elif n > 4:
            ngon += 1
        else:
            other += 1
    return tri, quad, ngon, other


def _edge_face_counts(mesh):
    edge_key_to_index = {}
    for e in mesh.edges:
        key = (min(e.vertices), max(e.vertices))
        edge_key_to_index[key] = e.index

    counts = {e.index: 0 for e in mesh.edges}
    for poly in mesh.polygons:
        vs = list(poly.vertices)
        n = len(vs)
        for i in range(n):
            a = vs[i]
            b = vs[(i + 1) % n]
            key = (min(a, b), max(a, b))
            e_idx = edge_key_to_index.get(key)
            if e_idx is not None:
                counts[e_idx] += 1
    return counts


def _connected_components(mesh):
    n = len(mesh.vertices)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for e in mesh.edges:
        union(e.vertices[0], e.vertices[1])

    return len(set(find(i) for i in range(n)))


def _loose_geometry(mesh):
    used_by_face = set()
    for poly in mesh.polygons:
        for v in poly.vertices:
            used_by_face.add(v)

    used_by_edge = set()
    for e in mesh.edges:
        used_by_edge.add(e.vertices[0])
        used_by_edge.add(e.vertices[1])

    loose_verts = [
        i for i in range(len(mesh.vertices))
        if i not in used_by_face and i not in used_by_edge
    ]

    counts = _edge_face_counts(mesh)
    loose_edges = [i for i, c in counts.items() if c == 0]
    return loose_verts, loose_edges


def _degenerate_faces(mesh):
    mesh.update()
    deg = 0
    for poly in mesh.polygons:
        vs = list(poly.vertices)
        if len(set(vs)) < len(vs):
            deg += 1
            continue
        if poly.area < DEGENERATE_AREA_EPS:
            deg += 1
    return deg


def _aabb(mesh, obj):
    mw = obj.matrix_world
    coords = [mw @ v.co for v in mesh.vertices]
    if not coords:
        return None
    xs = [c.x for c in coords]
    ys = [c.y for c in coords]
    zs = [c.z for c in coords]
    return {
        "min_x": min(xs), "max_x": max(xs),
        "min_y": min(ys), "max_y": max(ys),
        "min_z": min(zs), "max_z": max(zs),
    }


# ============================================================
# SYMMETRY (через пространственную сетку и ближайшую вершину)
# ============================================================

def _cell_key_of(v, cell_size):
    return (
        int(math.floor(v.x / cell_size)),
        int(math.floor(v.y / cell_size)),
        int(math.floor(v.z / cell_size)),
    )


def _symmetry_check(mesh, obj, center_x,
                    cell_size=SEARCH_CELL_SIZE,
                    match_tol=SYMMETRY_MATCH_TOLERANCE):
    """
    Для каждой вершины (x, y, z) ищет ближайшую вершину к
    зеркальной точке (2*center_x - x, y, z) через
    пространственную сетку с ячейкой cell_size.

    Возвращает словарь с метриками.
    """
    mw = obj.matrix_world
    coords = [mw @ v.co for v in mesh.vertices]
    n = len(coords)

    if n == 0:
        return {
            "center_x": center_x,
            "match_tolerance": match_tol,
            "cell_size": cell_size,
            "checked": 0,
            "error_max": 0.0,
            "error_mean": 0.0,
            "unmatched": 0,
            "total": 0,
        }

    # Пространственная сетка: ячейка -> список индексов вершин.
    grid = defaultdict(list)
    for i, c in enumerate(coords):
        grid[_cell_key_of(c, cell_size)].append(i)

    # Диапазон соседних ячеек для поиска.
    # Ищем в ±2 ячейках, чтобы покрыть match_tol.
    # 2 * cell_size должно быть >= match_tol.
    neighbor_radius = max(1, int(math.ceil(match_tol / cell_size)) + 1)

    checked = 0
    unmatched = 0
    error_max = 0.0
    error_sum = 0.0

    for i, c in enumerate(coords):
        mirror_x = 2.0 * center_x - c.x
        target = Vector((mirror_x, c.y, c.z))

        cx, cy, cz = _cell_key_of(target, cell_size)

        best_d = float("inf")
        best_j = -1
        for dx in range(-neighbor_radius, neighbor_radius + 1):
            for dy in range(-neighbor_radius, neighbor_radius + 1):
                for dz in range(-neighbor_radius, neighbor_radius + 1):
                    key = (cx + dx, cy + dy, cz + dz)
                    for j in grid.get(key, ()):
                        d = (coords[j] - target).length
                        if d < best_d:
                            best_d = d
                            best_j = j

        if best_j < 0 or best_d > match_tol:
            unmatched += 1
            continue

        checked += 1
        error_sum += best_d
        if best_d > error_max:
            error_max = best_d

    error_mean = (error_sum / checked) if checked > 0 else 0.0

    return {
        "center_x": center_x,
        "match_tolerance": match_tol,
        "cell_size": cell_size,
        "checked": checked,
        "error_max": error_max,
        "error_mean": error_mean,
        "unmatched": unmatched,
        "total": n,
    }


# ============================================================
# EYE / MOUTH LOOP DETECTION
# ============================================================

def _facial_loop_estimate(mesh):
    return {
        "eye_loop": "NEED_VISUAL_CHECK",
        "mouth_loop": "NEED_VISUAL_CHECK",
    }


# ============================================================
# ОТЧЁТ
# ============================================================

def _report_main_head(obj):
    mesh = obj.data
    n_verts = len(mesh.vertices)
    n_edges = len(mesh.edges)
    n_faces = len(mesh.polygons)

    tri, quad, ngon, other = _face_classification(mesh)

    edge_counts = _edge_face_counts(mesh)
    boundary_edges = [i for i, c in edge_counts.items() if c == 1]
    non_manifold_edges = [i for i, c in edge_counts.items() if c > 2]

    components = _connected_components(mesh)
    loose_verts, loose_edges = _loose_geometry(mesh)
    degenerate = _degenerate_faces(mesh)

    aabb = _aabb(mesh, obj)

    if aabb is not None:
        center_x = (aabb["min_x"] + aabb["max_x"]) * 0.5
    else:
        center_x = 0.0

    sym = _symmetry_check(mesh, obj, center_x)
    facial = _facial_loop_estimate(mesh)

    print()
    print("=== EXTERNAL HEAD TOPOLOGY ===")
    print()
    print(f"object:                {obj.name}")
    print(f"mesh:                  {mesh.name}")
    print(f"collections:           "
          f"{', '.join(c.name for c in obj.users_collection) or '-'}")
    print()
    print(f"vertices:              {n_verts}")
    print(f"edges:                 {n_edges}")
    print(f"faces:                 {n_faces}")
    print()
    print(f"connected_components:  {components}")
    print(f"boundary_edges:        {len(boundary_edges)}")
    print(f"non_manifold_edges:    {len(non_manifold_edges)}")
    print(f"loose_vertices:        {len(loose_verts)}")
    print(f"loose_edges:           {len(loose_edges)}")
    print(f"degenerate_faces:      {degenerate}")
    print()
    print(f"triangles:             {tri}")
    print(f"quads:                 {quad}")
    print(f"ngons:                 {ngon}")
    if other:
        print(f"other_faces:           {other}")
    print()
    if aabb is not None:
        print(f"min_x:                 {aabb['min_x']:+.4f}")
        print(f"max_x:                 {aabb['max_x']:+.4f}")
        print(f"min_y:                 {aabb['min_y']:+.4f}")
        print(f"max_y:                 {aabb['max_y']:+.4f}")
        print(f"min_z:                 {aabb['min_z']:+.4f}")
        print(f"max_z:                 {aabb['max_z']:+.4f}")
    print()
    print(f"symmetry:")
    print(f"  symmetry_match_tolerance: {sym['match_tolerance']:.6f}")
    print(f"  symmetry_center_x:        {sym['center_x']:+.4f}")
    print(f"  symmetry_checked:         {sym['checked']} / {sym['total']}")
    print(f"  symmetry_error_max:       {sym['error_max']:.6f}")
    print(f"  symmetry_error_mean:      {sym['error_mean']:.6f}")
    print(f"  symmetry_unmatched:       {sym['unmatched']}")
    print()
    print(f"eye_loop:              {facial['eye_loop']}")
    print(f"mouth_loop:            {facial['mouth_loop']}")
    print()
    print("=== END EXTERNAL HEAD TOPOLOGY ===")
    print()


def _report_eye_mesh(obj):
    mesh = obj.data
    n_verts = len(mesh.vertices)
    n_edges = len(mesh.edges)
    n_faces = len(mesh.polygons)
    tri, quad, ngon, other = _face_classification(mesh)

    aabb = _aabb(mesh, obj)

    print(f"  {obj.name}")
    print(f"    vertices:  {n_verts}")
    print(f"    edges:     {n_edges}")
    print(f"    polygons:  {n_faces}")
    print(f"    triangles: {tri}")
    print(f"    quads:     {quad}")
    print(f"    ngons:     {ngon}")
    if aabb is not None:
        print(f"    AABB X: {aabb['min_x']:+.4f} .. {aabb['max_x']:+.4f}")
        print(f"    AABB Y: {aabb['min_y']:+.4f} .. {aabb['max_y']:+.4f}")
        print(f"    AABB Z: {aabb['min_z']:+.4f} .. {aabb['max_z']:+.4f}")
    print()


def _report_eye_meshes():
    print()
    print("=== EYE MESH STATS ===")
    print()
    found_any = False
    for name in EYE_MESH_NAMES:
        obj = bpy.data.objects.get(name)
        if obj is None:
            print(f"  {name}: NOT FOUND")
            print()
            continue
        found_any = True
        _report_eye_mesh(obj)
    if not found_any:
        print("  No eye meshes found.")
    print("=== END EYE MESH STATS ===")
    print()


# ============================================================
# ПУБЛИЧНЫЙ API
# ============================================================

def run_test() -> None:
    obj = _find_object(MAIN_HEAD_NAME)
    if obj is None:
        _print_not_found(MAIN_HEAD_NAME)
        return

    if obj.type != 'MESH':
        print()
        print("=== EXTERNAL HEAD TOPOLOGY ===")
        print()
        print(f"object {obj.name} is not a MESH (type={obj.type})")
        print()
        print("=== END EXTERNAL HEAD TOPOLOGY ===")
        print()
        return

    _report_main_head(obj)
    _report_eye_meshes()
