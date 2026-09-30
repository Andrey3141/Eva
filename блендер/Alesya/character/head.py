# -*- coding: utf-8 -*-
"""
Голова Алеси — topology-first анатомическая base mesh (седьмая конструкция).

ПРИНЦИП:

  * сначала проектируются АНАТОМИЧЕСКИЕ EDGE LOOPS;
  * затем между петлями задаются явные quad faces;
  * координаты вершин назначаются ПОСЛЕ topology;
  * строится половина X >= 0, затем Mirror по X;
  * поверх — Subdivision Surface.

Строгая проверка topology проверяет:
  * каждая грань — 3 или 4 уникальные вершины;
  * каждое внутреннее ребро используется ровно 2 гранями;
  * рёбра на X = 0 — ровно 1 гранью;
  * нет дубликатов faces;
  * нет ссылок на несуществующие вершины.

Публичный API: build_head(coll) -> head_object.
C.HEAD_CENTER_Z применяется ровно один раз через obj.location.z.
"""

import bpy
import math
from collections import defaultdict

import config as C
from materials import make_material, assign_material
from utils import link_to_collection, shade_smooth


# ============================================================
# PARAMETERS
# ============================================================

HEAD_WIDTH      = 0.420
HEAD_HEIGHT     = 0.580
HEAD_DEPTH      = 0.280

SUBDIV_LEVELS   = 2


# ============================================================
# АНАТОМИЧЕСКИЕ EDGE LOOPS
# ============================================================

CROWN_LOOP = [
    "C_crown",
    "CR_1", "CR_2", "CR_3", "CR_4",
    "C_crown_back",
]

FOREHEAD_LOOP = [
    "C_forehead_mid",
    "FH_1", "FH_2", "FH_3", "FH_4",
    "C_forehead_back_mid",
]

BROW_LOOP = [
    "C_brow_mid",
    "BR_1", "BR_2", "BR_3",
    "C_brow_side",
    "BR_3_back", "BR_2_back", "BR_1_back",
    "C_brow_back_mid",
]

ORBIT_LOOP = [
    "C_orbit_inner",
    "OR_inner_top", "OR_top", "OR_outer_top",
    "OR_outer", "OR_outer_bottom", "OR_bottom",
    "OR_inner_bottom",
    "C_orbit_inner",
]

CHEEKBONE_LOOP = [
    "C_cheekbone_mid",
    "CB_1", "CB_2", "CB_3",
    "C_cheekbone_side",
    "CB_3_back", "CB_2_back", "CB_1_back",
    "C_cheekbone_back_mid",
]

CHEEK_LOOP = [
    "C_cheek_mid",
    "CH_1", "CH_2", "CH_3",
    "C_cheek_side",
    "CH_3_back", "CH_2_back", "CH_1_back",
    "C_cheek_back_mid",
]

MOUTH_LOOP = [
    "C_mouth_mid",
    "MO_1", "MO_2", "MO_3",
    "C_mouth_side",
    "MO_3_back", "MO_2_back", "MO_1_back",
    "C_mouth_back_mid",
]

JAW_LOOP = [
    "C_jaw_mid",
    "JW_1", "JW_2", "JW_3", "JW_4",
    "C_jaw_back_mid",
]

CHIN_LOOP = [
    "C_chin_mid",
    "CN_1", "CN_2", "CN_3",
    "C_chin_bottom_mid",
    "CN_3_back", "CN_2_back", "CN_1_back",
    "C_chin_back_mid",
]


# ============================================================
# КООРДИНАТЫ ВЕРШИН
# ============================================================

VERTEX_COORDS = {
    # --- центральная линия ---
    "C_crown":              (0.000,  0.000,  +0.290),
    "C_crown_back":         (0.000, +0.105,  +0.270),
    "C_forehead_mid":       (0.000, -0.098,  +0.150),
    "C_forehead_back_mid":  (0.000, +0.135,  +0.150),
    "C_brow_mid":           (0.000, -0.118,  +0.092),
    "C_brow_side":          (0.000, -0.108,  +0.090),
    "C_brow_back_mid":      (0.000, +0.140,  +0.090),
    "C_orbit_inner":        (0.000, -0.100,  +0.055),
    "C_cheekbone_mid":      (0.000, -0.108,  -0.010),
    "C_cheekbone_side":     (0.000, -0.100,  -0.010),
    "C_cheekbone_back_mid": (0.000, +0.140,  -0.010),
    "C_cheek_mid":          (0.000, -0.095,  -0.070),
    "C_cheek_side":         (0.000, -0.088,  -0.070),
    "C_cheek_back_mid":     (0.000, +0.130,  -0.070),
    "C_mouth_mid":          (0.000, -0.100,  -0.135),
    "C_mouth_side":         (0.000, -0.096,  -0.135),
    "C_mouth_back_mid":     (0.000, +0.120,  -0.135),
    "C_jaw_mid":            (0.000, -0.092,  -0.200),
    "C_jaw_back_mid":       (0.000, +0.100,  -0.200),
    "C_chin_mid":           (0.000, -0.108,  -0.240),
    "C_chin_bottom_mid":    (0.000, -0.106,  -0.290),
    "C_chin_back_mid":      (0.000, +0.040,  -0.260),

    # --- CROWN loop ---
    "CR_1": (0.045,  0.000, +0.288),
    "CR_2": (0.075, +0.030, +0.278),
    "CR_3": (0.080, +0.070, +0.250),
    "CR_4": (0.060, +0.095, +0.230),

    # --- FOREHEAD loop ---
    "FH_1": (0.055, -0.100, +0.150),
    "FH_2": (0.110, -0.092, +0.150),
    "FH_3": (0.155, -0.070, +0.150),
    "FH_4": (0.170, +0.020, +0.150),

    # --- BROW loop ---
    "BR_1": (0.045, -0.120, +0.092),
    "BR_2": (0.095, -0.115, +0.090),
    "BR_3": (0.155, -0.090, +0.090),
    "BR_3_back": (0.170, +0.020, +0.090),
    "BR_2_back": (0.150, +0.080, +0.090),
    "BR_1_back": (0.060, +0.130, +0.090),

    # --- ORBIT loop ---
    "OR_inner_top":    (0.045, -0.104, +0.060),
    "OR_top":          (0.090, -0.108, +0.062),
    "OR_outer_top":    (0.140, -0.100, +0.058),
    "OR_outer":        (0.160, -0.090, +0.040),
    "OR_outer_bottom": (0.140, -0.090, +0.020),
    "OR_bottom":       (0.090, -0.098, +0.018),
    "OR_inner_bottom": (0.045, -0.100, +0.030),

    # --- CHEEKBONE loop ---
    "CB_1": (0.050, -0.110, -0.010),
    "CB_2": (0.115, -0.108, -0.008),
    "CB_3": (0.185, -0.090, -0.010),
    "CB_3_back": (0.180, +0.030, -0.010),
    "CB_2_back": (0.150, +0.100, -0.010),
    "CB_1_back": (0.060, +0.135, -0.010),

    # --- CHEEK loop ---
    "CH_1": (0.045, -0.096, -0.070),
    "CH_2": (0.105, -0.090, -0.070),
    "CH_3": (0.160, -0.070, -0.070),
    "CH_3_back": (0.160, +0.030, -0.070),
    "CH_2_back": (0.135, +0.090, -0.070),
    "CH_1_back": (0.055, +0.120, -0.070),

    # --- MOUTH loop ---
    "MO_1": (0.040, -0.100, -0.135),
    "MO_2": (0.085, -0.098, -0.135),
    "MO_3": (0.120, -0.085, -0.135),
    "MO_3_back": (0.120, +0.030, -0.135),
    "MO_2_back": (0.100, +0.080, -0.135),
    "MO_1_back": (0.045, +0.110, -0.135),

    # --- JAW loop ---
    "JW_1": (0.040, -0.095, -0.200),
    "JW_2": (0.090, -0.090, -0.200),
    "JW_3": (0.135, -0.070, -0.200),
    "JW_4": (0.145, +0.020, -0.200),

    # --- CHIN loop ---
    "CN_1": (0.040, -0.108, -0.240),
    "CN_2": (0.075, -0.106, -0.245),
    "CN_3": (0.100, -0.090, -0.270),
    "CN_3_back": (0.095, +0.010, -0.270),
    "CN_2_back": (0.070, +0.030, -0.260),
    "CN_1_back": (0.035, +0.038, -0.255),
}


# ============================================================
# FACES — пересобраны как единая непрерывная поверхность
# ============================================================
#
# Ключевые правила:
#   * каждое внутреннее ребро принадлежит ровно двум faces;
#   * ребро на X = 0 принадлежит ровно одной face (в половине);
#   * никаких «патчей», наложенных друг на друга.
#
# Полосы (loops-стрипы), сшиваемые между последовательными
# петлями:
#   1. CROWN      ↔ FOREHEAD
#   2. FOREHEAD   ↔ BROW
#   3. BROW       ↔ ORBIT (с опорой C_brow_side)
#   4. ORBIT      ↔ CHEEKBONE (через CB_*)
#   5. CHEEKBONE  ↔ CHEEK
#   6. CHEEK      ↔ MOUTH
#   7. MOUTH      ↔ JAW
#   8. JAW        ↔ CHIN
#   9. CHIN вниз  → C_chin_bottom_mid
#
# Задняя сторона сшивается через *_back-вершины и C_*_back_mid.

FACES = [
    # ========================================================
    # 1. CROWN ↔ FOREHEAD
    # ========================================================
    ("C_crown",       "CR_1",   "FH_1",   "C_forehead_mid"),
    ("CR_1",          "CR_2",   "FH_2",   "FH_1"),
    ("CR_2",          "CR_3",   "FH_3",   "FH_2"),
    ("CR_3",          "CR_4",   "FH_4",   "FH_3"),
    ("CR_4",          "C_crown_back", "C_forehead_back_mid", "FH_4"),

    # ========================================================
    # 2. FOREHEAD ↔ BROW
    # ========================================================
    ("C_forehead_mid", "FH_1", "BR_1", "C_brow_mid"),
    ("FH_1",           "FH_2", "BR_2", "BR_1"),
    ("FH_2",           "FH_3", "BR_3", "BR_2"),
    ("FH_3",           "FH_4", "BR_3_back", "BR_3"),
    ("FH_4",           "C_forehead_back_mid", "C_brow_back_mid", "BR_3_back"),

    # Задняя часть brow-полосы
    ("C_brow_mid",     "BR_1", "BR_1_back", "C_brow_back_mid"),
    ("BR_1",           "BR_2", "BR_2_back", "BR_1_back"),
    ("BR_2",           "BR_3", "BR_3_back", "BR_2_back"),

    # ========================================================
    # 3. BROW ↔ ORBIT
    # ========================================================
    # Внутренняя (медиальная) часть надбровья переходит в орбиту
    ("C_brow_mid",     "BR_1", "OR_inner_top", "C_orbit_inner"),
    ("BR_1",           "BR_2", "OR_top", "OR_inner_top"),
    ("BR_2",           "BR_3", "OR_outer_top", "OR_top"),

    # Переход к C_brow_side (центр на X=0 между BR_3 и BR_3_back)
    ("BR_3",           "C_brow_side", "OR_outer", "OR_outer_top"),

    # Задняя полоса переходит в боковой край орбиты
    ("C_brow_back_mid", "BR_3_back", "OR_outer", "C_brow_side"),
    ("BR_3",           "BR_3_back", "OR_outer", "C_brow_side"),

    # ========================================================
    # 4. ORBIT (замкнутая рамка)
    # ========================================================
    ("OR_inner_top",    "OR_top",          "OR_outer_top",  "OR_outer"),
    ("OR_outer",        "OR_outer_bottom", "OR_bottom",     "OR_inner_bottom"),
    ("OR_inner_bottom", "OR_bottom",       "OR_inner_top",  "C_orbit_inner"),

    # ========================================================
    # 5. ORBIT ↔ CHEEKBONE
    # ========================================================
    ("C_orbit_inner",   "OR_inner_bottom", "CB_1", "C_cheekbone_mid"),
    ("OR_inner_bottom", "OR_bottom",       "CB_2", "CB_1"),
    ("OR_bottom",       "OR_outer_bottom", "CB_3", "CB_2"),
    ("OR_outer_bottom", "OR_outer",        "CB_3_back", "CB_3"),
    ("OR_outer",        "BR_3_back",       "CB_2_back", "CB_3_back"),
    ("BR_3_back",       "C_brow_back_mid", "C_cheekbone_back_mid", "CB_2_back"),
    ("CB_2_back",       "CB_1_back",       "C_cheekbone_back_mid", "C_cheekbone_mid"),

    # ========================================================
    # 6. CHEEKBONE ↔ CHEEK
    # ========================================================
    ("C_cheekbone_mid", "CB_1", "CH_1", "C_cheek_mid"),
    ("CB_1",            "CB_2", "CH_2", "CH_1"),
    ("CB_2",            "CB_3", "CH_3", "CH_2"),
    ("CB_3",            "CB_3_back", "CH_3_back", "CH_3"),
    ("CB_3_back",       "CB_2_back", "CH_2_back", "CH_3_back"),
    ("CB_2_back",       "CB_1_back", "CH_1_back", "CH_2_back"),
    ("CB_1_back",       "C_cheekbone_back_mid", "C_cheek_back_mid", "CH_1_back"),

    # ========================================================
    # 7. CHEEK ↔ MOUTH
    # ========================================================
    ("C_cheek_mid", "CH_1", "MO_1", "C_mouth_mid"),
    ("CH_1",        "CH_2", "MO_2", "MO_1"),
    ("CH_2",        "CH_3", "MO_3", "MO_2"),
    ("CH_3",        "CH_3_back", "MO_3_back", "MO_3"),
    ("CH_3_back",   "CH_2_back", "MO_2_back", "MO_3_back"),
    ("CH_2_back",   "CH_1_back", "MO_1_back", "MO_2_back"),
    ("CH_1_back",   "C_cheek_back_mid", "C_mouth_back_mid", "MO_1_back"),

    # ========================================================
    # 8. MOUTH ↔ JAW
    # ========================================================
    ("C_mouth_mid", "MO_1",       "JW_1", "C_jaw_mid"),
    ("MO_1",        "MO_2",       "JW_2", "JW_1"),
    ("MO_2",        "MO_3",       "JW_3", "JW_2"),
    ("MO_3",        "MO_3_back",  "JW_4", "JW_3"),
    ("MO_3_back",   "MO_2_back",  "JW_4", "JW_3"),
    ("MO_2_back",   "MO_1_back",  "C_jaw_back_mid", "JW_4"),
    ("MO_1_back",   "C_mouth_back_mid", "C_jaw_back_mid", "MO_2_back"),
    ("C_mouth_back_mid", "MO_1_back", "C_jaw_back_mid", "C_jaw_mid"),

    # ========================================================
    # 9. JAW ↔ CHIN
    # ========================================================
    ("C_jaw_mid", "JW_1", "CN_1", "C_chin_mid"),
    ("JW_1",      "JW_2", "CN_2", "CN_1"),
    ("JW_2",      "JW_3", "CN_3", "CN_2"),
    ("JW_3",      "JW_4", "CN_3_back", "CN_3"),
    ("JW_4",      "C_jaw_back_mid", "C_chin_back_mid", "CN_3_back"),

    # ========================================================
    # 10. CHIN — замыкание нижнего контура
    # ========================================================
    ("C_chin_mid",        "CN_1", "CN_1_back", "C_chin_bottom_mid"),
    ("CN_1",              "CN_2", "CN_2_back", "CN_1_back"),
    ("CN_2",              "CN_3", "CN_3_back", "CN_2_back"),
    ("CN_3",              "CN_3_back", "C_chin_back_mid", "C_chin_mid"),
    ("C_chin_bottom_mid", "CN_3_back", "C_chin_back_mid", "C_chin_mid"),
]


# ============================================================
# СТРОГАЯ ТОПОЛОГИЧЕСКАЯ ПРОВЕРКА
# ============================================================

def _face_edges(face):
    n = len(face)
    edges = []
    for i in range(n):
        a = face[i]
        b = face[(i + 1) % n]
        edges.append((min(a, b), max(a, b)))
    return edges


def _strict_topology_check(faces, vertex_names):
    coords = {name: VERTEX_COORDS[name] for name in vertex_names}

    problems = []

    for fi, f in enumerate(faces):
        if len(f) < 3 or len(f) > 4:
            problems.append(f"face[{fi}] has invalid size {len(f)}: {f}")
            continue
        if len(set(f)) < len(f):
            problems.append(f"face[{fi}] has duplicate vertex: {f}")
        missing = [n for n in f if n not in coords]
        if missing:
            problems.append(
                f"face[{fi}] references unknown landmarks: {missing}")

    edge_use = defaultdict(list)
    for fi, f in enumerate(faces):
        for e in _face_edges(f):
            edge_use[e].append(fi)

    non_manifold = []
    boundary_off_center = []
    boundary_on_center = []

    for e, fis in edge_use.items():
        n = len(fis)
        if n > 2:
            non_manifold.append((e, fis))
        elif n == 1:
            a, b = e
            ax, ay, az = coords[a]
            bx, by, bz = coords[b]
            if abs(ax) < 1e-6 and abs(bx) < 1e-6:
                boundary_on_center.append((e, fis))
            else:
                boundary_off_center.append((e, fis))

    canonical_to_indices = defaultdict(list)
    for fi, f in enumerate(faces):
        canonical = tuple(sorted(f))
        canonical_to_indices[canonical].append(fi)

    duplicate_faces = [
        (canon, idxs) for canon, idxs in canonical_to_indices.items()
        if len(idxs) > 1
    ]

    if non_manifold:
        print()
        print("=== NON-MANIFOLD EDGES ===")
        for e, fis in non_manifold:
            a, b = e
            print(f"  edge ({a}, {b}) -> used by {len(fis)} faces {fis}")
        print("=== END NON-MANIFOLD EDGES ===")

    if boundary_off_center:
        print()
        print("=== BOUNDARY EDGES OFF X=0 ===")
        for e, fis in boundary_off_center:
            a, b = e
            print(f"  edge ({a}, {b}) -> used by {len(fis)} faces {fis}")
        print("=== END BOUNDARY EDGES OFF X=0 ===")

    if duplicate_faces:
        print()
        print("=== DUPLICATE FACES ===")
        for canon, idxs in duplicate_faces:
            print(f"  duplicate face {canon} -> indices {idxs}")
        print("=== END DUPLICATE FACES ===")

    if problems:
        print()
        print("=== FACE PROBLEMS ===")
        for p in problems:
            print(f"  {p}")
        print("=== END FACE PROBLEMS ===")

    if problems or non_manifold or boundary_off_center or duplicate_faces:
        raise AssertionError(
            "STRICT TOPOLOGY FAILURE: "
            f"problems={len(problems)}, "
            f"non_manifold={len(non_manifold)}, "
            f"boundary_off_center={len(boundary_off_center)}, "
            f"duplicate_faces={len(duplicate_faces)}"
        )

    print("STRICT TOPOLOGY PASS")


# ============================================================
# MESH GENERATION
# ============================================================

def _build_mesh_object(coll):
    names = list(VERTEX_COORDS.keys())
    idx = {name: i for i, name in enumerate(names)}
    verts = [VERTEX_COORDS[name] for name in names]

    _strict_topology_check(FACES, names)

    face_indices = [tuple(idx[n] for n in f) for f in FACES]

    mesh = bpy.data.meshes.new("Alesya_Head_Cage_Mesh")
    mesh.from_pydata(verts, [], face_indices)
    mesh.update()

    before = (len(mesh.vertices), len(mesh.edges), len(mesh.polygons))
    mesh.validate(verbose=False)
    after = (len(mesh.vertices), len(mesh.edges), len(mesh.polygons))
    if before != after:
        raise AssertionError(
            f"mesh.validate() changed topology: {before} → {after}"
        )

    obj = bpy.data.objects.new("Alesya_Head", mesh)
    coll.objects.link(obj)
    return obj


def build_head(coll):
    mat_skin = make_material("Alesya_Skin", C.SKIN_COLOR,
                             roughness=0.55, specular=0.25)

    cage = _build_mesh_object(coll)

    mirror = cage.modifiers.new(name="Mirror", type='MIRROR')
    mirror.use_axis[0] = True
    mirror.use_clip = True
    mirror.merge_threshold = 1e-4

    subdiv = cage.modifiers.new(name="Subdivision", type='SUBSURF')
    subdiv.levels = SUBDIV_LEVELS
    subdiv.render_levels = SUBDIV_LEVELS
    subdiv.use_limit_surface = True

    if cage.data.materials:
        cage.data.materials[0] = mat_skin
    else:
        cage.data.materials.append(mat_skin)

    for poly in cage.data.polygons:
        poly.use_smooth = True

    cage.location = (0.0, 0.0, C.HEAD_CENTER_Z)

    return cage


# ============================================================
# ДИАГНОСТИЧЕСКИЙ API
# ============================================================

DEBUG_Z_SAMPLES = [
    +1.00, +0.90, +0.75, +0.60, +0.45, +0.30, +0.15, +0.00,
    -0.15, -0.30, -0.45, -0.55, -0.70, -0.84, -0.90,
]


def _approx_width(z_norm):
    z = z_norm * (HEAD_HEIGHT * 0.5)
    best = 0.0
    for (_, (x, _, vz)) in VERTEX_COORDS.items():
        if abs(vz - z) < 0.05:
            best = max(best, abs(x))
    return 2.0 * best if best > 0 else HEAD_WIDTH * 0.5


def _approx_depth(z_norm):
    z = z_norm * (HEAD_HEIGHT * 0.5)
    ys = [y for (_, (_, y, vz)) in VERTEX_COORDS.items()
          if abs(vz - z) < 0.05]
    if not ys:
        return HEAD_DEPTH * 0.5
    return max(ys) - min(ys)


def _approx_front(z_norm):
    z = z_norm * (HEAD_HEIGHT * 0.5)
    ys = [y for (_, (_, y, vz)) in VERTEX_COORDS.items()
          if abs(vz - z) < 0.05]
    if not ys:
        return 0.0
    return min(ys)


def debug_profile_mapping():
    results = []
    print()
    print("=== BASE PROFILE (pure functions) ===")
    print(f"{'z_norm':>8}{'width':>10}{'depth':>10}{'front':>10}")
    for z in DEBUG_Z_SAMPLES:
        w = _approx_width(z)
        d = _approx_depth(z)
        f = _approx_front(z)
        print(f"{z:>+8.2f}{w:>10.4f}{d:>10.4f}{f:>+10.4f}")
        results.append({"z_norm": z, "width": w, "depth": d, "front": f})
    print("=== END BASE PROFILE ===")
    print()
    return results


def debug_profile_sphere_base():
    print()
    print("=== PROFILE → SURFACE → WIDTH ===")
    for z in DEBUG_Z_SAMPLES:
        w = _approx_width(z)
        print(f"{z:>+8.2f}{w:>10.4f}{w:>10.4f}{1.0:>10.4f}")
    print("=== END PROFILE → SURFACE → WIDTH ===")
    print()


def debug_ring_math():
    print()
    print("=== RING MATH ===")
    for z in DEBUG_Z_SAMPLES:
        print(f"{z:>+8.2f}{_approx_width(z):>10.4f}"
              f"{_approx_depth(z):>10.4f}{_approx_front(z):>+10.4f}")
    print("=== END RING MATH ===")
    print()


def debug_normalized_profile_mapping():
    print()
    print("=== NORMALIZED WIDTH ===")
    for z in DEBUG_Z_SAMPLES:
        print(f"{z:>+8.2f}{_approx_width(z):>10.4f}")
    print("=== END NORMALIZED WIDTH ===")
    print()


def debug_max_width_position():
    print()
    print("=== MAX WIDTH POSITION ===")
    max_w = 0.0
    max_z = 0.0
    for i in range(201):
        z = 1.0 - 2.0 * i / 200.0
        w = _approx_width(z)
        if w > max_w:
            max_w = w
            max_z = z
    print(f"MAX width = {max_w:.4f} at z_norm = {max_z:+.3f}")
    print("=== END MAX WIDTH ===")
    print()


def debug_stage_contributions():
    print()
    print("=== ANATOMICAL ZONES ===")
    for z in DEBUG_Z_SAMPLES:
        print(f"{z:>+8.2f}{_approx_width(z):>10.4f}")
    print("=== END ANATOMICAL ZONES ===")
    print()


def debug_slice_widths():
    print()
    print("=== SLICE WIDTHS (t = 0.30 .. 0.65) ===")
    for i in range(40):
        t = 0.30 + 0.35 * i / 39
        z = 1.0 - 2.0 * t
        print(f"{t:>6.3f}{_approx_width(z):>10.4f}")
    print("=== END SLICE WIDTHS ===")
    print()
