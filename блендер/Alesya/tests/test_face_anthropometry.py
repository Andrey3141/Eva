# -*- coding: utf-8 -*-
"""
Alesya — антропометрическая диагностика области глаз.

Публичный API: run_test() -> None.

ИТЕРАЦИЯ: РЕКОНСТРУКЦИЯ ГЛАЗНОЙ ЩЕЛИ ПО ВНУТРЕННИМ КРАЯМ ВЕК.

Раньше En/Ex/Ps/Pi брались как внешние экстремумы оболочек век
(max Z верхнего века, min Z нижнего века). Это давало контур
вокруг глаза, а не контур глазной щели.

Сейчас:

  * для верхнего века внутренний край (нижний) — вершины с большим Y
    (глубже, ближе к глазному яблоку), минимум Z по бинам X;
  * для нижнего века внутренний край (верхний) — вершины с большим Y,
    максимум Z по бинам X;
  * En / Ex — крайние бины X, где верхняя граница выше нижней;
  * Ps / Pi — экстремумы в окрестности вертикали зрачка, а не
    глобальные экстремумы;
  * legacy-метод сохранён под именем legacy_shell_aperture для
    сравнения.

Production-код не изменяется.
"""

import math
import bpy
from mathutils import Vector

import config as C
from utils import get_or_create_collection
from character.head import build_head
from character.eyes import build_eyes


# ============================================================
# РЕФЕРЕНСНАЯ БАЗА
# ============================================================

ANTHROPOMETRIC_REFERENCES = {
    "turkish_young_female": {
        "population": "Turkish women, age 18-25",
        "sample": 272,
        "ipd_mm": {"mean": 60.8, "sd": 3.2},
        "intercanthal_mm": {"mean": 30.0, "sd": 2.6},
        "biocular_mm": {"mean": 92.0, "sd": 5.4},
        "pfw_mm": {"mean": 31.0, "sd": 2.4},
        "pfh_mm": {"mean": 10.4, "sd": 1.5},
        "source": ("Bozkir MG, Karakas P, Oguz O. "
                   "Measurements of soft tissue orbits in Turkish "
                   "young adults. Surg Radiol Anat. 2003."),
    },
    "adult_women_20_44": {
        "population": "Adult women, age 20-44",
        "sample": None,
        "ipd_mm": {"mean": 64.20, "sd": 5.06},
        "intercanthal_mm": {"mean": 31.30, "sd": 3.07},
        "biocular_mm": {"mean": 92.98, "sd": 5.85},
        "pfw_mm": {"mean": 29.96, "sd": 1.76},
        "pfh_mm": None,
        "source": ("Anthropometric Analysis of Orbital Region and "
                   "Age-Related Changes in Adult Women. "
                   "(women 20-44 subgroup)"),
    },
}

SCALE_ANCHOR = "ipd_mm"
DEFAULT_REFERENCE_KEY = "turkish_young_female"

SYMMETRY_EPSILON = 1e-4
MIN_POSITIVE_SIZE = 1e-6

# Окрестность вертикали зрачка по X для поиска Ps / Pi.
# Доля от полной ширины щели.
PSPI_PUPIL_WINDOW_FRACTION = 0.35


# ============================================================
# СЦЕНА
# ============================================================

def _clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.cameras,
                  bpy.data.lights, bpy.data.curves, bpy.data.images):
        for item in list(block):
            try:
                block.remove(item)
            except Exception:
                pass


def _setup_render():
    scene = bpy.context.scene
    try:
        scene.render.engine = 'BLENDER_EEVEE_NEXT'
    except Exception:
        scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x = 800
    scene.render.resolution_y = 800
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.view_settings.view_transform = 'Standard'
    scene.render.image_settings.file_format = 'PNG'


def _setup_world():
    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.55, 0.55, 0.58, 1.0)
        bg.inputs[1].default_value = 0.8


def _setup_lights():
    coll = get_or_create_collection("Alesya_Anthropometry_Lights")
    for name, energy, size, loc, rot in [
        ("Anthro_Key",  400, 3.0, (-1.4, -2.0, C.HEAD_CENTER_Z + 0.6),
         (1.05, 0.0, -0.55)),
        ("Anthro_Fill", 150, 3.0, ( 1.6, -1.8, C.HEAD_CENTER_Z + 0.1),
         (1.25, 0.0,  0.90)),
        ("Anthro_Rim",  120, 2.0, ( 0.0,  2.4, C.HEAD_CENTER_Z + 0.7),
         (-1.05, 0.0, 3.14)),
    ]:
        ld = bpy.data.lights.new(name, type='AREA')
        ld.energy = energy
        ld.size = size
        ld.color = (1.0, 1.0, 1.0)
        o = bpy.data.objects.new(name, ld)
        o.location = loc
        o.rotation_euler = rot
        coll.objects.link(o)


def _build_camera():
    coll = get_or_create_collection("Alesya_Anthropometry_Camera")
    cd = bpy.data.cameras.new("Anthro_Camera_Data")
    cd.lens = 90.0
    cd.type = 'PERSP'
    cam = bpy.data.objects.new("Anthro_Camera", cd)
    cam.location = (0.0, -0.55, C.HEAD_CENTER_Z + 0.01)
    cam.rotation_euler = (math.radians(90), 0.0, 0.0)
    coll.objects.link(cam)
    return cam


# ============================================================
# ГЕОМЕТРИЯ
# ============================================================

def _world_coords(obj):
    mw = obj.matrix_world
    return [mw @ v.co for v in obj.data.vertices]


def _world_bounds_from_coords(coords):
    if not coords:
        return None
    xs = [c.x for c in coords]
    ys = [c.y for c in coords]
    zs = [c.z for c in coords]
    return {
        "min": Vector((min(xs), min(ys), min(zs))),
        "max": Vector((max(xs), max(ys), max(zs))),
        "center": Vector(((min(xs) + max(xs)) * 0.5,
                          (min(ys) + max(ys)) * 0.5,
                          (min(zs) + max(zs)) * 0.5)),
        "size": Vector((max(xs) - min(xs),
                        max(ys) - min(ys),
                        max(zs) - min(zs))),
    }


def _require(name):
    obj = bpy.data.objects.get(name)
    if obj is None:
        raise AssertionError(f"Missing required object: {name}")
    return obj


def _finite_positive(value, name):
    if value is None:
        raise AssertionError(f"{name}: missing value")
    if not math.isfinite(value):
        raise AssertionError(f"{name}: non-finite value {value}")
    if value <= MIN_POSITIVE_SIZE:
        raise AssertionError(f"{name}: non-positive value {value}")


# ============================================================
# LEGACY (для сравнения)
# ============================================================

def _legacy_shell_aperture(upper_coords, lower_coords, side_sign):
    """
    Старый метод: En/Ex из крайних бинов по X, Ps = max Z верхнего
    века, Pi = min Z нижнего века. Меряет внешние экстремумы
    оболочек, а не реальную щель.
    """
    if not upper_coords or not lower_coords:
        return None

    xs_all = [c.x for c in upper_coords] + [c.x for c in lower_coords]
    x_min = min(xs_all)
    x_max = max(xs_all)

    if side_sign < 0:
        En = Vector((x_max, 0.0, 0.0))
        Ex = Vector((x_min, 0.0, 0.0))
    else:
        En = Vector((x_min, 0.0, 0.0))
        Ex = Vector((x_max, 0.0, 0.0))

    # Ps / Pi — внешние экстремумы оболочек по Z
    Ps = max(upper_coords, key=lambda c: c.z)
    Pi = min(lower_coords, key=lambda c: c.z)

    return {
        "En": En, "Ex": Ex, "Ps": Ps, "Pi": Pi,
        "PFW": abs(x_max - x_min),
        "PFH": abs(Ps.z - Pi.z),
    }


# ============================================================
# НОВАЯ РЕКОНСТРУКЦИЯ ГЛАЗНОЙ ЩЕЛИ
# ============================================================

def _split_outer_inner(eyelid_coords, eye_coords):
    """
    Разделяет вершины века на внешний и внутренний край по Y.

    Лицо смотрит в -Y:
        внешний край (кожа лица) — меньший Y;
        внутренний край (к яблоку)  — больший Y.

    Порог = медиана Y всех вершин века. Все вершины с Y >= median
    попадают во внутренний край. Если разброс Y мал, возвращаем
    весь набор как внутренний край (это допустимо: оболочка тонкая).
    """
    if not eyelid_coords:
        return [], []

    ys = sorted(c.y for c in eyelid_coords)
    y_min = ys[0]
    y_max = ys[-1]
    span = y_max - y_min

    if span <= 1e-5:
        # Тонкая оболочка — разделение по Y не имеет смысла.
        return [], list(eyelid_coords)

    median_y = ys[len(ys) // 2]
    outer = [c for c in eyelid_coords if c.y < median_y]
    inner = [c for c in eyelid_coords if c.y >= median_y]
    return outer, inner


def _bin_edges(x_min, x_max, n):
    return [x_min + (x_max - x_min) * i / n for i in range(n + 1)]


def _bin_index(x, edges):
    for i in range(len(edges) - 1):
        if edges[i] <= x < edges[i + 1]:
            return i
    return len(edges) - 2


def _reconstruct_aperture(upper_coords, lower_coords, side_sign,
                          pupil_center=None):
    """
    Восстанавливает реальные границы глазной щели.

    Для каждого бина X:
        верхняя граница щели = самая низкая вершина внутреннего края
                               верхнего века (минимум Z);
        нижняя граница щели  = самая высокая вершина внутреннего края
                               нижнего века (максимум Z).

    Щель в бине существует, если верхняя граница строго выше нижней.

    En / Ex — крайние бины X, где щель непустая.
    Ps / Pi — экстремумы в окрестности вертикали зрачка.
    """
    if not upper_coords or not lower_coords:
        return None

    _, upper_inner = _split_outer_inner(upper_coords, None)
    _, lower_inner = _split_outer_inner(lower_coords, None)

    if not upper_inner:
        upper_inner = list(upper_coords)
    if not lower_inner:
        lower_inner = list(lower_coords)

    xs_all = [c.x for c in upper_inner] + [c.x for c in lower_inner]
    x_min = min(xs_all)
    x_max = max(xs_all)
    x_span = x_max - x_min
    if x_span <= MIN_POSITIVE_SIZE:
        return None

    n_bins = 24
    edges = _bin_edges(x_min, x_max, n_bins)

    upper_by_bin = [None] * n_bins
    lower_by_bin = [None] * n_bins

    for i in range(n_bins):
        x0 = edges[i]
        x1 = edges[i + 1]

        up_bin = [c for c in upper_inner
                  if x0 <= c.x < x1 or (i == n_bins - 1 and c.x == x1)]
        lo_bin = [c for c in lower_inner
                  if x0 <= c.x < x1 or (i == n_bins - 1 and c.x == x1)]

        if up_bin:
            # Внутренний край верхнего века — нижняя граница его
            # оболочки, то есть min Z у вершин внутреннего края.
            upper_by_bin[i] = min(up_bin, key=lambda c: c.z)
        if lo_bin:
            # Внутренний край нижнего века — верхняя граница его
            # оболочки, то есть max Z у вершин внутреннего края.
            lower_by_bin[i] = max(lo_bin, key=lambda c: c.z)

    # Только бины, где верхняя граница выше нижней.
    valid_bins = []
    for i in range(n_bins):
        u = upper_by_bin[i]
        l = lower_by_bin[i]
        if u is not None and l is not None and u.z > l.z:
            valid_bins.append(i)

    if len(valid_bins) < 4:
        # Не удалось построить контур — fallback на оболочки.
        return None

    # En / Ex — крайние валидные бины.
    i_first = valid_bins[0]
    i_last = valid_bins[-1]

    if side_sign < 0:
        # Левый глаз: En — медиальный (ближе к центру), это
        # правый край (больший X). Ex — латеральный (меньший X).
        i_en, i_ex = i_last, i_first
    else:
        i_en, i_ex = i_first, i_last

    def _bin_edge_point(i):
        """
        Точка схождения верхнего и нижнего века в данном бине:
        среднее верхней границы (u) и нижней границы (l) по X, Y, Z.
        """
        u = upper_by_bin[i]
        l = lower_by_bin[i]
        pts = [p for p in (u, l) if p is not None]
        sx = sum(p.x for p in pts) / len(pts)
        sy = sum(p.y for p in pts) / len(pts)
        sz = sum(p.z for p in pts) / len(pts)
        return Vector((sx, sy, sz))

    En = _bin_edge_point(i_en)
    Ex = _bin_edge_point(i_ex)

    # --- Ps / Pi в окрестности вертикали зрачка ---
    if pupil_center is not None:
        cx = pupil_center.x
        half_window = x_span * PSPI_PUPIL_WINDOW_FRACTION * 0.5

        window_bins = [i for i in valid_bins
                       if abs(0.5 * (edges[i] + edges[i + 1]) - cx)
                       <= half_window]
        if len(window_bins) < 3:
            window_bins = valid_bins
    else:
        window_bins = valid_bins

    # Ps = самая верхняя точка верхней границы в окрестности.
    # upper_by_bin[i] — это нижняя граница верхнего века.
    # Реальный верх щели = эта же точка, но чуть выше: на самом
    # деле у нашей геометрии щель существует только между
    # нижним краем верхнего века и верхним краем нижнего.
    # Поэтому Ps = max по верхней границе (u.z) — но u — низ
    # верхнего века. Именно он и есть верх щели. Аналогично
    # Pi = min по нижней границе (l.z).
    u_candidates = [upper_by_bin[i] for i in window_bins
                    if upper_by_bin[i] is not None]
    l_candidates = [lower_by_bin[i] for i in window_bins
                    if lower_by_bin[i] is not None]

    if not u_candidates or not l_candidates:
        return None

    Ps = max(u_candidates, key=lambda c: c.z)
    Pi = min(l_candidates, key=lambda c: c.z)

    # Ширина по X (фронтальная проекция)
    width_xz = abs(Ex.x - En.x)
    # Высота по Z
    height_xz = abs(Ps.z - Pi.z)

    return {
        "En": En, "Ex": Ex, "Ps": Ps, "Pi": Pi,
        "width_xz": width_xz,
        "height_xz": height_xz,
        "valid_bins": len(valid_bins),
        "total_bins": n_bins,
    }


# ============================================================
# ЗАГЛУШКИ И ЛИНИИ
# ============================================================

def _landmark_P(pupil_obj):
    coords = _world_coords(pupil_obj)
    bb = _world_bounds_from_coords(coords)
    if bb is None:
        return None
    return bb["center"]


def _create_landmark_empty(name, location, coll):
    bpy.ops.object.empty_add(type='PLAIN_AXES', location=location)
    obj = bpy.context.active_object
    obj.name = name
    obj.empty_display_size = 0.005
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    coll.objects.link(obj)
    return obj


def _create_line_segment(name, p0, p1, coll, color=(1.0, 0.2, 0.2, 1.0)):
    mesh = bpy.data.meshes.new(name + "_Mesh")
    mesh.from_pydata([tuple(p0), tuple(p1)], [(0, 1)], [])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    coll.objects.link(obj)

    mat = bpy.data.materials.get(name + "_Mat")
    if mat is None:
        mat = bpy.data.materials.new(name + "_Mat")
        mat.use_nodes = True
        nt = mat.node_tree
        for n in list(nt.nodes):
            nt.nodes.remove(n)
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        emis = nt.nodes.new("ShaderNodeEmission")
        emis.inputs["Color"].default_value = color
        emis.inputs["Strength"].default_value = 3.0
        nt.links.new(emis.outputs["Emission"], out.inputs["Surface"])
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)

    return obj


# ============================================================
# ИЗМЕРЕНИЯ
# ============================================================

def _measure_all(coll):
    head = _require("Alesya_Head")
    eye_l = _require("Alesya_Eye_L")
    eye_r = _require("Alesya_Eye_R")
    eyelid_u_l = _require("Alesya_Eyelid_L")
    eyelid_u_r = _require("Alesya_Eyelid_R")
    eyelid_d_l = _require("Alesya_Eyelid_Lower_L")
    eyelid_d_r = _require("Alesya_Eyelid_Lower_R")
    pupil_l = _require("Alesya_Pupil_L")
    pupil_r = _require("Alesya_Pupil_R")

    eye_l_coords = _world_coords(eye_l)
    eye_r_coords = _world_coords(eye_r)
    eyelid_u_l_coords = _world_coords(eyelid_u_l)
    eyelid_u_r_coords = _world_coords(eyelid_u_r)
    eyelid_d_l_coords = _world_coords(eyelid_d_l)
    eyelid_d_r_coords = _world_coords(eyelid_d_r)

    if not eye_l_coords or not eye_r_coords:
        raise AssertionError("eye mesh is empty")
    if not eyelid_u_l_coords or not eyelid_d_l_coords:
        raise AssertionError("left eyelids mesh is empty")
    if not eyelid_u_r_coords or not eyelid_d_r_coords:
        raise AssertionError("right eyelids mesh is empty")

    P_L = _landmark_P(pupil_l)
    P_R = _landmark_P(pupil_r)
    if P_L is None or P_R is None:
        raise AssertionError("pupil landmark missing")

    # --- Новая реконструкция ---
    ap_l = _reconstruct_aperture(eyelid_u_l_coords, eyelid_d_l_coords,
                                 side_sign=-1, pupil_center=P_L)
    ap_r = _reconstruct_aperture(eyelid_u_r_coords, eyelid_d_r_coords,
                                 side_sign=+1, pupil_center=P_R)
    if ap_l is None:
        raise AssertionError("left aperture reconstruction failed")
    if ap_r is None:
        raise AssertionError("right aperture reconstruction failed")

    En_L, Ex_L = ap_l["En"], ap_l["Ex"]
    Ps_L, Pi_L = ap_l["Ps"], ap_l["Pi"]
    En_R, Ex_R = ap_r["En"], ap_r["Ex"]
    Ps_R, Pi_R = ap_r["Ps"], ap_r["Pi"]

    # --- Legacy для сравнения ---
    legacy_l = _legacy_shell_aperture(eyelid_u_l_coords,
                                      eyelid_d_l_coords, side_sign=-1)
    legacy_r = _legacy_shell_aperture(eyelid_u_r_coords,
                                      eyelid_d_r_coords, side_sign=+1)

    # --- Landmark empties ---
    landmarks = {
        "Alesya_Landmark_En_L": En_L,
        "Alesya_Landmark_En_R": En_R,
        "Alesya_Landmark_Ex_L": Ex_L,
        "Alesya_Landmark_Ex_R": Ex_R,
        "Alesya_Landmark_P_L":  P_L,
        "Alesya_Landmark_P_R":  P_R,
        "Alesya_Landmark_Ps_L": Ps_L,
        "Alesya_Landmark_Ps_R": Ps_R,
        "Alesya_Landmark_Pi_L": Pi_L,
        "Alesya_Landmark_Pi_R": Pi_R,
    }
    for name, loc in landmarks.items():
        _create_landmark_empty(name, loc, coll)

    # --- Диагностические линии ---
    _create_line_segment("Alesya_Diag_Line_EnEx_L", En_L, Ex_L, coll,
                         color=(1.0, 0.2, 0.2, 1.0))
    _create_line_segment("Alesya_Diag_Line_EnEx_R", En_R, Ex_R, coll,
                         color=(1.0, 0.2, 0.2, 1.0))
    _create_line_segment("Alesya_Diag_Line_PsPi_L", Ps_L, Pi_L, coll,
                         color=(0.2, 0.6, 1.0, 1.0))
    _create_line_segment("Alesya_Diag_Line_PsPi_R", Ps_R, Pi_R, coll,
                         color=(0.2, 0.6, 1.0, 1.0))

    # --- Измерения ---
    PFW_L = (En_L - Ex_L).length
    PFW_R = (En_R - Ex_R).length
    PFW_mean = 0.5 * (PFW_L + PFW_R)

    PFH_L = (Ps_L - Pi_L).length
    PFH_R = (Ps_R - Pi_R).length
    PFH_mean = 0.5 * (PFH_L + PFH_R)

    ICD = (En_L - En_R).length
    IPD = (P_L - P_R).length
    BIC = (Ex_L - Ex_R).length

    for label, value in [
        ("PFW_L", PFW_L), ("PFW_R", PFW_R), ("PFW_mean", PFW_mean),
        ("PFH_L", PFH_L), ("PFH_R", PFH_R), ("PFH_mean", PFH_mean),
        ("ICD", ICD), ("IPD", IPD), ("BIC", BIC),
    ]:
        _finite_positive(value, label)

    # --- Legacy bounding box глаза ---
    eye_l_bb = _world_bounds_from_coords(eye_l_coords)
    eye_r_bb = _world_bounds_from_coords(eye_r_coords)
    eye_obj_w_mean = 0.5 * (eye_l_bb["size"].x + eye_r_bb["size"].x)
    eye_obj_h_mean = 0.5 * (eye_l_bb["size"].z + eye_r_bb["size"].z)

    # --- Head ---
    head_coords = _world_coords(head)
    head_bb = _world_bounds_from_coords(head_coords)

    return {
        "landmarks": landmarks,
        "eye_l_coords": eye_l_coords,
        "eye_r_coords": eye_r_coords,
        "eye_l_bb": eye_l_bb,
        "eye_r_bb": eye_r_bb,
        "head_bb": head_bb,
        "aperture_l": ap_l,
        "aperture_r": ap_r,
        "legacy_l": legacy_l,
        "legacy_r": legacy_r,
        "P_L": P_L, "P_R": P_R,

        "PFW_L": PFW_L, "PFW_R": PFW_R, "PFW_mean": PFW_mean,
        "PFH_L": PFH_L, "PFH_R": PFH_R, "PFH_mean": PFH_mean,
        "ICD": ICD, "IPD": IPD, "BIC": BIC,

        "eye_obj_w_mean": eye_obj_w_mean,
        "eye_obj_h_mean": eye_obj_h_mean,

        "face_width": head_bb["size"].x,
        "face_height": head_bb["size"].z,
        "face_depth": head_bb["size"].y,
    }


# ============================================================
# МАСШТАБИРОВАНИЕ
# ============================================================

def _scale_to_reference(m, ref_key):
    ref = ANTHROPOMETRIC_REFERENCES[ref_key]
    anchor = ref[SCALE_ANCHOR]
    if anchor is None:
        raise AssertionError(
            f"reference {ref_key} has no {SCALE_ANCHOR} to use as anchor")

    anchor_mm = anchor["mean"]
    model_anchor_units = m["IPD"]
    scale_mm_per_unit = anchor_mm / model_anchor_units

    def to_mm(units):
        return units * scale_mm_per_unit

    return {
        "scale_mm_per_unit": scale_mm_per_unit,
        "PFW_mm": to_mm(m["PFW_mean"]),
        "PFH_mm": to_mm(m["PFH_mean"]),
        "ICD_mm": to_mm(m["ICD"]),
        "IPD_mm": to_mm(m["IPD"]),
        "BIC_mm": to_mm(m["BIC"]),
    }


def _compare_to_reference(mm_values, ref_key):
    ref = ANTHROPOMETRIC_REFERENCES[ref_key]
    rows = []
    for key in ("pfw_mm", "pfh_mm", "intercanthal_mm",
                "ipd_mm", "biocular_mm"):
        r = ref.get(key)
        model_key = {
            "pfw_mm": "PFW_mm",
            "pfh_mm": "PFH_mm",
            "intercanthal_mm": "ICD_mm",
            "ipd_mm": "IPD_mm",
            "biocular_mm": "BIC_mm",
        }[key]
        model = mm_values[model_key]
        is_anchor = (key == SCALE_ANCHOR)

        if r is None:
            rows.append({
                "key": key,
                "model": model,
                "reference_mean": None,
                "reference_sd": None,
                "diff": None,
                "z_like": None,
                "is_anchor": is_anchor,
                "status": "REFERENCE: unavailable",
            })
            continue
        diff = model - r["mean"]
        z_like = diff / r["sd"] if r["sd"] and r["sd"] > 0 else None
        status = "anchor (normalized)" if is_anchor else "ok"
        rows.append({
            "key": key,
            "model": model,
            "reference_mean": r["mean"],
            "reference_sd": r["sd"],
            "diff": diff,
            "z_like": z_like,
            "is_anchor": is_anchor,
            "status": status,
        })
    return rows


def _normalized_ratios(m):
    return {
        "PFW_over_BIC": m["PFW_mean"] / m["BIC"],
        "PFH_over_PFW": m["PFH_mean"] / m["PFW_mean"],
        "ICD_over_BIC": m["ICD"] / m["BIC"],
        "IPD_over_BIC": m["IPD"] / m["BIC"],
    }


def _symmetry_report(m):
    pairs = [
        ("PFW_L vs R",   m["PFW_L"], m["PFW_R"], False),
        ("PFH_L vs R",   m["PFH_L"], m["PFH_R"], False),
        ("En_x_L vs -R", m["landmarks"]["Alesya_Landmark_En_L"].x,
                         m["landmarks"]["Alesya_Landmark_En_R"].x, True),
        ("Ex_x_L vs -R", m["landmarks"]["Alesya_Landmark_Ex_L"].x,
                         m["landmarks"]["Alesya_Landmark_Ex_R"].x, True),
        ("P_x_L vs -R",  m["landmarks"]["Alesya_Landmark_P_L"].x,
                         m["landmarks"]["Alesya_Landmark_P_R"].x, True),
    ]
    out = []
    max_err = 0.0
    for label, l, r, is_center in pairs:
        err = abs(l + r) if is_center else abs(l - r)
        out.append((label, err))
        if err > max_err:
            max_err = err
    return out, max_err


# ============================================================
# ОТЧЁТ
# ============================================================

def _fmt(v):
    return f"({v.x:+.4f}, {v.y:+.4f}, {v.z:+.4f})"


def _print_report(m, mm_by_ref, rows_by_ref, ratios, sym_rows, sym_max):
    line = "=" * 60

    print()
    print(line)
    print("EYE ANTHROPOMETRY DIAGNOSTIC")
    print(line)
    print()
    print("REFERENCE BASIS:")
    print("  adult female anthropometric reference values")
    print("  NOT an absolute ideal")
    print("  population-dependent")
    print()

    print("APERTURE RECONSTRUCTION (inner eyelid edges)")
    print(f"  LEFT  : valid_bins={m['aperture_l']['valid_bins']}/"
          f"{m['aperture_l']['total_bins']}  "
          f"width_xz={m['aperture_l']['width_xz']:.4f}  "
          f"height_xz={m['aperture_l']['height_xz']:.4f}")
    print(f"  RIGHT : valid_bins={m['aperture_r']['valid_bins']}/"
          f"{m['aperture_r']['total_bins']}  "
          f"width_xz={m['aperture_r']['width_xz']:.4f}  "
          f"height_xz={m['aperture_r']['height_xz']:.4f}")
    print()

    print("LANDMARKS (world coords)")
    for name in (
        "Alesya_Landmark_En_L", "Alesya_Landmark_En_R",
        "Alesya_Landmark_Ex_L", "Alesya_Landmark_Ex_R",
        "Alesya_Landmark_P_L",  "Alesya_Landmark_P_R",
        "Alesya_Landmark_Ps_L", "Alesya_Landmark_Ps_R",
        "Alesya_Landmark_Pi_L", "Alesya_Landmark_Pi_R",
    ):
        loc = m["landmarks"][name]
        print(f"  {name:<28} {_fmt(loc)}")
    print()

    print("APERTURE VALIDATION")
    print(f"  PFW_L = {m['PFW_L']:.4f}   PFW_R = {m['PFW_R']:.4f}   "
          f"PFW_mean = {m['PFW_mean']:.4f}")
    print(f"  PFH_L = {m['PFH_L']:.4f}   PFH_R = {m['PFH_R']:.4f}   "
          f"PFH_mean = {m['PFH_mean']:.4f}")
    print()

    print("  En / Ex position:")
    print(f"    En_L = {_fmt(m['landmarks']['Alesya_Landmark_En_L'])}")
    print(f"    Ex_L = {_fmt(m['landmarks']['Alesya_Landmark_Ex_L'])}")
    print(f"    En_R = {_fmt(m['landmarks']['Alesya_Landmark_En_R'])}")
    print(f"    Ex_R = {_fmt(m['landmarks']['Alesya_Landmark_Ex_R'])}")
    print()
    print("  Ps / Pi position:")
    print(f"    Ps_L = {_fmt(m['landmarks']['Alesya_Landmark_Ps_L'])}")
    print(f"    Pi_L = {_fmt(m['landmarks']['Alesya_Landmark_Pi_L'])}")
    print(f"    Ps_R = {_fmt(m['landmarks']['Alesya_Landmark_Ps_R'])}")
    print(f"    Pi_R = {_fmt(m['landmarks']['Alesya_Landmark_Pi_R'])}")
    print()

    # Расстояния от Ps / Pi до центра зрачка
    Ps_L = m["landmarks"]["Alesya_Landmark_Ps_L"]
    Pi_L = m["landmarks"]["Alesya_Landmark_Pi_L"]
    Ps_R = m["landmarks"]["Alesya_Landmark_Ps_R"]
    Pi_R = m["landmarks"]["Alesya_Landmark_Pi_R"]
    P_L = m["P_L"]; P_R = m["P_R"]

    def _xz_dist(a, b):
        return math.hypot(a.x - b.x, a.z - b.z)

    print("  Distance from Ps/Pi to pupil center (X-Z projection):")
    print(f"    |Ps_L - P_L|_xz = {_xz_dist(Ps_L, P_L):.4f}")
    print(f"    |Pi_L - P_L|_xz = {_xz_dist(Pi_L, P_L):.4f}")
    print(f"    |Ps_R - P_R|_xz = {_xz_dist(Ps_R, P_R):.4f}")
    print(f"    |Pi_R - P_R|_xz = {_xz_dist(Pi_R, P_R):.4f}")
    print()

    # --- Legacy сравнение ---
    print("LEGACY SHELL APERTURE (external eyelid extremes)")
    leg_l = m["legacy_l"]; leg_r = m["legacy_r"]
    if leg_l is not None:
        print(f"  LEFT  : PFW={leg_l['PFW']:.4f}  PFH={leg_l['PFH']:.4f}")
    if leg_r is not None:
        print(f"  RIGHT : PFW={leg_r['PFW']:.4f}  PFH={leg_r['PFH']:.4f}")
    print(f"  NEW   : PFW={m['PFW_mean']:.4f}  PFH={m['PFH_mean']:.4f}  "
          f"(mean)")
    if leg_l is not None and leg_r is not None:
        leg_pfw_mean = 0.5 * (leg_l['PFW'] + leg_r['PFW'])
        leg_pfh_mean = 0.5 * (leg_l['PFH'] + leg_r['PFH'])
        print(f"  LEGACY vs NEW:")
        print(f"    PFW:  legacy={leg_pfw_mean:.4f}  new={m['PFW_mean']:.4f}  "
              f"diff={m['PFW_mean'] - leg_pfw_mean:+.4f}")
        print(f"    PFH:  legacy={leg_pfh_mean:.4f}  new={m['PFH_mean']:.4f}  "
              f"diff={m['PFH_mean'] - leg_pfh_mean:+.4f}")
    print()

    print("MODEL MEASUREMENTS (blender units)")
    print(f"  PFW (palpebral fissure width)  : {m['PFW_mean']:.4f}")
    print(f"  PFH (palpebral fissure height) : {m['PFH_mean']:.4f}")
    print(f"  ICD (intercanthal)             : {m['ICD']:.4f}")
    print(f"  IPD (interpupillary)           : {m['IPD']:.4f}")
    print(f"  BIC (biocular)                 : {m['BIC']:.4f}")
    print()

    print("LEGACY GEOMETRIC MEASUREMENTS (not anthropological)")
    print(f"  eye_object_width  (mean) : {m['eye_obj_w_mean']:.4f}")
    print(f"  eye_object_height (mean) : {m['eye_obj_h_mean']:.4f}")
    print(f"  face_width               : {m['face_width']:.4f}")
    print(f"  face_height              : {m['face_height']:.4f}")
    print(f"  face_depth               : {m['face_depth']:.4f}")
    print()

    for ref_key in ANTHROPOMETRIC_REFERENCES.keys():
        mm = mm_by_ref[ref_key]
        ref = ANTHROPOMETRIC_REFERENCES[ref_key]
        print(f"REFERENCE: {ref['population']}")
        print(f"  source: {ref['source']}")
        print(f"  scale anchor: {SCALE_ANCHOR} = {ref[SCALE_ANCHOR]['mean']} mm")
        print(f"  scale_mm_per_unit: {mm['scale_mm_per_unit']:.4f}")
        print(f"  Model in mm:")
        print(f"    PFW_mm : {mm['PFW_mm']:.3f}")
        print(f"    PFH_mm : {mm['PFH_mm']:.3f}")
        print(f"    ICD_mm : {mm['ICD_mm']:.3f}")
        print(f"    IPD_mm : {mm['IPD_mm']:.3f}  (anchor)")
        print(f"    BIC_mm : {mm['BIC_mm']:.3f}")
        print()

    for ref_key in ANTHROPOMETRIC_REFERENCES.keys():
        rows = rows_by_ref[ref_key]
        ref = ANTHROPOMETRIC_REFERENCES[ref_key]
        print(f"COMPARISON: {ref['population']}")
        print(f"  {'Parameter':<24}{'Model(mm)':>12}"
              f"{'Ref Mean':>12}{'Ref SD':>10}"
              f"{'Diff':>10}{'Std Diff':>12}  Status")
        print("  " + "-" * 84)
        for row in rows:
            key = row["key"]
            model = row["model"]
            rmean = row["reference_mean"]
            rsd = row["reference_sd"]
            diff = row["diff"]
            zl = row["z_like"]
            status = row["status"]
            if rmean is None:
                print(f"  {key:<24}{model:>12.3f}"
                      f"{'--':>12}{'--':>10}{'--':>10}{'--':>12}  {status}")
            else:
                diff_s = f"{diff:+.3f}"
                zl_s = "--" if zl is None else f"{zl:+.2f}"
                print(f"  {key:<24}{model:>12.3f}"
                      f"{rmean:>12.3f}{rsd:>10.3f}"
                      f"{diff_s:>10}{zl_s:>12}  {status}")
        print()
        print("  Note: 'Std Diff' is standardized difference from the")
        print("  sample mean (model - mean) / SD. It is not a clinical")
        print("  z-score for an individual face.")
        print()

    print("NORMALIZED RATIOS (no target — reference-relative only)")
    print(f"  PFW / BIC : {ratios['PFW_over_BIC']:.4f}")
    print(f"  PFH / PFW : {ratios['PFH_over_PFW']:.4f}")
    print(f"  ICD / BIC : {ratios['ICD_over_BIC']:.4f}")
    print(f"  IPD / BIC : {ratios['IPD_over_BIC']:.4f}")
    print()

    print("SYMMETRY")
    for label, err in sym_rows:
        status = "OK" if err < SYMMETRY_EPSILON else "WARN"
        print(f"  {label:<18} err={err:.6f}  {status}")
    print(f"  MAX asymmetry   : {sym_max:.6f}")
    print()

    print("TECHNICAL RESULT")
    if sym_max < SYMMETRY_EPSILON:
        print("  PASS")
    else:
        print(f"  FAIL — symmetry exceeds {SYMMETRY_EPSILON:.6f}")
    print()
    print("NOTE: anthropometric deviation from reference mean is NOT")
    print("a FAIL condition.")
    print()
    print(line)
    print()


# ============================================================
# РЕНДЕР
# ============================================================

def _render_landmark_overlay(cam, output_dir):
    scene = bpy.context.scene
    scene.camera = cam
    output_dir.mkdir(parents=True, exist_ok=True)
    render_path = output_dir / "face_anthropometry_landmarks.png"
    scene.render.filepath = str(render_path)
    bpy.ops.render.render(write_still=True)
    print(f"Rendered: {render_path}")


# ============================================================
# ПУБЛИЧНЫЙ API
# ============================================================

def run_test() -> None:
    from pathlib import Path
    output_dir = Path(__file__).resolve().parent / "test_output"

    print("Alesya eye anthropometry: preparing scene...")
    _clear_scene()
    _setup_render()
    _setup_world()
    _setup_lights()

    coll = get_or_create_collection("Alesya_Eye_Anthropometry")

    print("Alesya eye anthropometry: building head...")
    build_head(coll)

    print("Alesya eye anthropometry: building eyes...")
    build_eyes(coll)

    bpy.context.view_layer.update()

    print("Alesya eye anthropometry: measuring landmarks and distances...")
    m = _measure_all(coll)

    mm_by_ref = {}
    rows_by_ref = {}
    for ref_key in ANTHROPOMETRIC_REFERENCES.keys():
        mm_by_ref[ref_key] = _scale_to_reference(m, ref_key)
        rows_by_ref[ref_key] = _compare_to_reference(mm_by_ref[ref_key],
                                                     ref_key)

    ratios = _normalized_ratios(m)
    sym_rows, sym_max = _symmetry_report(m)

    _print_report(m, mm_by_ref, rows_by_ref, ratios, sym_rows, sym_max)

    cam = _build_camera()
    _render_landmark_overlay(cam, output_dir)

    if sym_max >= SYMMETRY_EPSILON:
        raise AssertionError(
            f"Symmetry exceeds technical tolerance: {sym_max:.6f} "
            f">= {SYMMETRY_EPSILON:.6f}"
        )

    print("Alesya eye anthropometry: done.")
