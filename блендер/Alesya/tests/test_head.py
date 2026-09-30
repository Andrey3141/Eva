# -*- coding: utf-8 -*-
"""
Alesya — аудит геометрии головы.
Публичный API: run_test() -> None.
"""

import math
import bpy
from mathutils import Vector

import config as C
from utils import get_or_create_collection
from character.head import (
    build_head,
    debug_profile_mapping,
    debug_profile_sphere_base,
    debug_ring_math,
    debug_normalized_profile_mapping,
    debug_max_width_position,
    debug_stage_contributions,
    debug_slice_widths,
)


# ============================================================
# 1. КОНФИГУРАЦИЯ ТЕСТА
# ============================================================

TEST_COLLECTION_NAME = "Alesya_Head_Test"
RENDER_RESOLUTION    = 600
CAM_DISTANCE         = 1.10
CAM_HEIGHT           = C.HEAD_CENTER_Z

NUM_SLICES           = 60

THRESH_VERY_CLOSE       = 2.0
THRESH_CLOSE            = 5.0
THRESH_SLIGHTLY_OFF     = 10.0
THRESH_SIGNIFICANTLY    = 20.0

TRANS_VERY_CLOSE_MIN   = 0.90
TRANS_VERY_CLOSE_MAX   = 1.10
TRANS_SLIGHT_WEAK_MIN  = 0.75
TRANS_SLIGHT_STRONG_MAX = 1.25

ELLIPSOID_SIMILARITY_HI = 0.85

W_SILHOUETTE   = 0.25
W_PROFILE      = 0.25
W_CURVATURE    = 0.20
W_TRANSITIONS  = 0.15
W_NONELLIPSOID = 0.15


# ============================================================
# 2. ЭТАЛОН
# ============================================================

REF_HEAD_TOTAL_WIDTH    = 1.00
REF_HEAD_TOTAL_HEIGHT   = 1.35
REF_HEAD_TOTAL_DEPTH    = 0.72

REF_ZONES = [
    (0.00,  0.30,  0.65,  0.35),
    (0.10,  0.55,  0.78,  0.42),
    (0.20,  0.75,  0.88,  0.50),
    (0.30,  0.88,  0.92,  0.55),
    (0.38,  0.95,  0.94,  0.58),
    (0.45,  1.00,  0.95,  0.60),
    (0.55,  0.97,  0.92,  0.58),
    (0.65,  0.88,  0.86,  0.55),
    (0.75,  0.72,  0.78,  0.52),
    (0.85,  0.55,  0.66,  0.52),
    (0.92,  0.38,  0.52,  0.55),
    (1.00,  0.22,  0.38,  0.60),
]

REF_MAX_WIDTH_T          = 0.45
REF_CHEEKBONE_WIDTH      = 1.00
REF_JAW_WIDTH            = 0.72
REF_CHIN_WIDTH           = 0.30
REF_FOREHEAD_WIDTH       = 0.88
REF_CROWN_WIDTH          = 0.40

REF_TRANSITIONS = {
    "crown_to_forehead":   0.30,
    "forehead_to_brow":    0.15,
    "brow_to_cheekbone":   0.18,
    "cheekbone_to_cheek":  0.10,
    "cheek_to_jaw":        0.25,
    "jaw_to_chin":         0.40,
}


# ============================================================
# 3. УТИЛИТЫ
# ============================================================

def _output_dir():
    from pathlib import Path
    here = Path(__file__).resolve()
    return here.parent / "test_output"


def _clamp(v, a, b):
    return max(a, min(b, v))


def _lerp(a, b, t):
    return a + (b - a) * t


def _interp_zones(zones, t, idx):
    if t <= zones[0][0]:
        return zones[0][idx]
    if t >= zones[-1][0]:
        return zones[-1][idx]
    for i in range(len(zones) - 1):
        t0 = zones[i][0]
        t1 = zones[i + 1][0]
        if t0 <= t <= t1:
            k = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
            return _lerp(zones[i][idx], zones[i + 1][idx], k)
    return zones[-1][idx]


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


# ============================================================
# 4. МЕТРИКИ
# ============================================================

def _collect_vertices(head_obj):
    mw = head_obj.matrix_world
    return [mw @ v.co for v in head_obj.data.vertices]


def _bounding_box(verts):
    xs = [v.x for v in verts]
    ys = [v.y for v in verts]
    zs = [v.z for v in verts]
    return (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))


def _measure_slices(verts, num_slices):
    min_x, max_x, min_y, max_y, min_z, max_z = _bounding_box(verts)
    z_range = max(max_z - min_z, 1e-6)

    slices = []
    for i in range(num_slices):
        z_top = max_z - (i / num_slices) * z_range
        z_bot = max_z - ((i + 1) / num_slices) * z_range
        band = [v for v in verts if z_bot <= v.z <= z_top]
        if not band:
            continue
        xs = [v.x for v in band]
        ys = [v.y for v in band]
        width = max(xs) - min(xs)
        depth = max(ys) - min(ys)
        y_center = (max(ys) + min(ys)) * 0.5
        y_front = min(ys)
        y_back = max(ys)
        front_local = y_front - y_center
        slices.append({
            "z": (z_top + z_bot) * 0.5,
            "z_t": (i + 0.5) / num_slices,
            "width": width,
            "depth": depth,
            "x_min": min(xs),
            "x_max": max(xs),
            "y_front": y_front,
            "y_back": y_back,
            "y_center": y_center,
            "front_local": front_local,
        })

    return {
        "slices": slices,
        "min_x": min_x, "max_x": max_x,
        "min_y": min_y, "max_y": max_y,
        "min_z": min_z, "max_z": max_z,
        "width": max_x - min_x,
        "depth": max_y - min_y,
        "height": max_z - min_z,
    }


def _normalize_slices(slices_data):
    w_max = max((s["width"] for s in slices_data["slices"]), default=1e-6)
    d_max = max((s["depth"] for s in slices_data["slices"]), default=1e-6)
    h_total = max(slices_data["height"], 1e-6)

    out = []
    for s in slices_data["slices"]:
        out.append({
            "z_t": s["z_t"],
            "width": s["width"] / w_max,
            "depth": s["depth"] / d_max,
            "front_local": s["front_local"],
            "z_world": s["z"],
            "z_norm": (s["z"] - slices_data["min_z"]) / h_total,
        })
    return out, w_max, d_max


def _reference_slices(num_slices, actual_front_scale):
    ref = []
    for i in range(num_slices):
        t = (i + 0.5) / num_slices
        w = _interp_zones(REF_ZONES, t, 1)
        d = _interp_zones(REF_ZONES, t, 2)
        f = _interp_zones(REF_ZONES, t, 3)
        ref.append({
            "z_t": t,
            "width": w,
            "depth": d,
            "front_local": -f * actual_front_scale,
        })
    return ref


# ============================================================
# 5. КРИВИЗНА
# ============================================================

def _estimate_curvature(verts, head_obj, k_neighbors=8):
    mesh = head_obj.data
    mw = head_obj.matrix_world

    neighbors = [[] for _ in range(len(mesh.vertices))]
    for edge in mesh.edges:
        a, b = edge.vertices
        neighbors[a].append(b)
        neighbors[b].append(a)

    curv = []
    for i, v in enumerate(mesh.vertices):
        p = mw @ v.co
        nb = neighbors[i]
        if not nb:
            curv.append(0.0)
            continue
        nb = nb[:k_neighbors]
        pts = [mw @ mesh.vertices[j].co for j in nb]
        mean = Vector((0.0, 0.0, 0.0))
        for q in pts:
            mean += q
        mean /= len(pts)
        offset = (p - mean).length
        avg_dist = sum((q - p).length for q in pts) / len(pts)
        avg_dist = max(avg_dist, 1e-6)
        curv.append(offset / avg_dist)
    return curv


def _curvature_zone_profile(verts, curv, slices_data):
    min_z = slices_data["min_z"]
    max_z = slices_data["max_z"]
    z_range = max(max_z - min_z, 1e-6)
    bins = [[] for _ in range(10)]
    for v, c in zip(verts, curv):
        t = (max_z - v.z) / z_range
        i = _clamp(int(t * 10), 0, 9)
        bins[i].append(c)
    return [sum(b) / len(b) if b else 0.0 for b in bins]


# ============================================================
# 6. ПЕРЕХОДЫ
# ============================================================

def _transitions_from_profile(norm_slices):
    def width_at(t):
        best = min(norm_slices, key=lambda s: abs(s["z_t"] - t))
        return best["width"]

    pairs = [
        ("crown_to_forehead",   0.05, 0.20),
        ("forehead_to_brow",    0.20, 0.38),
        ("brow_to_cheekbone",   0.38, 0.45),
        ("cheekbone_to_cheek",  0.45, 0.55),
        ("cheek_to_jaw",        0.55, 0.75),
        ("jaw_to_chin",         0.75, 0.95),
    ]
    return {name: abs(width_at(t1) - width_at(t0))
            for name, t0, t1 in pairs}


def _classify_transition(strength, ref_strength):
    ratio = strength / max(ref_strength, 1e-6)
    if TRANS_VERY_CLOSE_MIN <= ratio <= TRANS_VERY_CLOSE_MAX:
        return "VERY CLOSE", ratio
    if TRANS_SLIGHT_WEAK_MIN <= ratio < TRANS_VERY_CLOSE_MIN:
        return "SLIGHTLY WEAK", ratio
    if TRANS_VERY_CLOSE_MAX < ratio <= TRANS_SLIGHT_STRONG_MAX:
        return "SLIGHTLY STRONG", ratio
    if ratio < TRANS_SLIGHT_WEAK_MIN:
        return "WEAK", ratio
    return "STRONG", ratio


# ============================================================
# 7. СРАВНЕНИЕ С ЭТАЛОНОМ
# ============================================================

def _reference_shape_similarity(norm_slices, ref_slices):
    if not norm_slices or not ref_slices:
        return 0.0
    n = min(len(norm_slices), len(ref_slices))
    total_err = 0.0
    for i in range(n):
        total_err += abs(norm_slices[i]["width"] - ref_slices[i]["width"])
        total_err += abs(norm_slices[i]["depth"] - ref_slices[i]["depth"])
    avg_err = total_err / (2 * n)
    return _clamp(1.0 - avg_err, 0.0, 1.0)


def _classify_deviation(actual, reference):
    if reference == 0:
        return "CRITICAL", float('inf')
    pct = (actual - reference) / abs(reference) * 100.0
    a = abs(pct)
    if a <= THRESH_VERY_CLOSE:
        return "VERY CLOSE", pct
    if a <= THRESH_CLOSE:
        return "CLOSE", pct
    if a <= THRESH_SLIGHTLY_OFF:
        return "SLIGHTLY OFF", pct
    if a <= THRESH_SIGNIFICANTLY:
        return "SIGNIFICANTLY OFF", pct
    return "CRITICAL", pct


def _parameter_row(label, actual, reference):
    status, pct = _classify_deviation(actual, reference)
    return {
        "label": label,
        "actual": actual,
        "reference": reference,
        "deviation_pct": pct,
        "status": status,
    }


# ============================================================
# 8. ASCII ГРАФИКИ
# ============================================================

def _ascii_bar(value, max_value, width=24):
    if max_value <= 0:
        return ""
    n = int(round(width * value / max_value))
    n = _clamp(n, 0, width)
    return "█" * n


# ============================================================
# 9. СЦЕНА
# ============================================================

def _setup_render():
    scene = bpy.context.scene
    try:
        scene.render.engine = 'BLENDER_EEVEE_NEXT'
    except Exception:
        scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x = RENDER_RESOLUTION
    scene.render.resolution_y = RENDER_RESOLUTION
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
        bg.inputs[1].default_value = 0.9


def _setup_lights():
    coll = get_or_create_collection("Alesya_Head_Test_Lights")
    for name, energy, size, loc, rot in [
        ("Test_Key",  400, 2.5, (-1.5, -2.2, CAM_HEIGHT + 0.6), (1.05, 0.0, -0.55)),
        ("Test_Fill",  90, 2.5, ( 1.8, -1.8, CAM_HEIGHT + 0.1), (1.25, 0.0,  0.90)),
        ("Test_Rim",  120, 1.8, ( 0.0,  2.4, CAM_HEIGHT + 0.7), (-1.05, 0.0, 3.14)),
    ]:
        ld = bpy.data.lights.new(name, type='AREA')
        ld.energy = energy
        ld.size = size
        ld.color = (1.0, 1.0, 1.0)
        o = bpy.data.objects.new(name, ld)
        o.location = loc
        o.rotation_euler = rot
        coll.objects.link(o)


def _build_cameras():
    coll = get_or_create_collection("Alesya_Head_Test_Cameras")

    def make(name, location, rotation):
        cd = bpy.data.cameras.new(name + "_Data")
        cd.lens = 65.0
        cd.type = 'PERSP'
        o = bpy.data.objects.new(name, cd)
        o.location = location
        o.rotation_euler = rotation
        coll.objects.link(o)
        return o

    d = CAM_DISTANCE
    h = CAM_HEIGHT

    front = make("Alesya_Test_Camera_Front",
                 (0.0, -d, h), (math.radians(90), 0.0, 0.0))
    profile = make("Alesya_Test_Camera_Profile",
                   (d, 0.0, h), (math.radians(90), 0.0, math.radians(90)))

    ang = math.radians(40)
    cx = -d * math.sin(ang)
    cy = -d * math.cos(ang)
    three_q = make("Alesya_Test_Camera_3Q",
                   (cx, cy, h), (math.radians(90), 0.0, ang))

    top = make("Alesya_Test_Camera_Top",
               (0.0, 0.0, h + d), (0.0, 0.0, 0.0))

    return {"front": front, "profile": profile, "3q": three_q, "top": top}


def _render_all(cameras, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    for key, fname in [
        ("front",   "head_test_front.png"),
        ("profile", "head_test_profile.png"),
        ("3q",      "head_test_3q.png"),
        ("top",     "head_test_top.png"),
    ]:
        cam = cameras.get(key)
        if not cam:
            continue
        scene.camera = cam
        scene.render.filepath = str(output_dir / fname)
        bpy.ops.render.render(write_still=True)


# ============================================================
# 10. ПАРАМЕТРЫ И ПЕРЕХОДЫ
# ============================================================

def _build_parameter_table(slices_data, norm_slices):
    rows = []
    w = slices_data["width"]
    h = slices_data["height"]
    d = slices_data["depth"]

    rows.append(_parameter_row("Height / Width", h / max(w, 1e-6),
                               REF_HEAD_TOTAL_HEIGHT))
    rows.append(_parameter_row("Depth / Width", d / max(w, 1e-6),
                               REF_HEAD_TOTAL_DEPTH))

    def width_at(t):
        best = min(norm_slices, key=lambda s: abs(s["z_t"] - t))
        return best["width"]

    rows.append(_parameter_row("Crown width (t=0.05)",
                               width_at(0.05), REF_CROWN_WIDTH))
    rows.append(_parameter_row("Forehead width (t=0.20)",
                               width_at(0.20), REF_FOREHEAD_WIDTH))
    rows.append(_parameter_row("Cheekbone width (t=0.45)",
                               width_at(0.45), REF_CHEEKBONE_WIDTH))
    rows.append(_parameter_row("Jaw width (t=0.75)",
                               width_at(0.75), REF_JAW_WIDTH))
    rows.append(_parameter_row("Chin width (t=0.92)",
                               width_at(0.92), REF_CHIN_WIDTH))

    peak = max(norm_slices, key=lambda s: s["width"])
    rows.append(_parameter_row("Max width position (t)",
                               peak["z_t"], REF_MAX_WIDTH_T))

    cb = width_at(0.45)
    jw = width_at(0.75)
    ch = width_at(0.92)
    fh = width_at(0.20)
    rows.append(_parameter_row("Cheekbone / Jaw",
                               cb / max(jw, 1e-6), 1.0 / 0.72))
    rows.append(_parameter_row("Forehead / Cheekbone",
                               fh / max(cb, 1e-6), 0.88 / 1.00))
    rows.append(_parameter_row("Chin / Jaw",
                               ch / max(jw, 1e-6), 0.30 / 0.72))

    return rows, peak


def _build_anatomical_transitions(norm_slices):
    tr = _transitions_from_profile(norm_slices)
    out = []
    for name, strength in tr.items():
        ref = REF_TRANSITIONS.get(name, 0.25)
        status, ratio = _classify_transition(strength, ref)
        out.append({
            "name": name,
            "strength": strength,
            "reference": ref,
            "ratio": ratio,
            "status": status,
        })
    return out


def _diagnose_problems(param_rows, transitions, curv_zone, shape_sim,
                       slices_data, norm_slices):
    problems = []
    tags = set()

    for row in param_rows:
        if row["status"] in ("SIGNIFICANTLY OFF", "CRITICAL"):
            problems.append(f"{row['label']}: {row['status']} "
                            f"(dev {row['deviation_pct']:+.1f}%)")

    if shape_sim > ELLIPSOID_SIMILARITY_HI:
        problems.append("Surface behaves like a single smooth ellipsoid.")
        tags.update(["ellipsoid-like", "insufficient curvature"])

    if curv_zone:
        cmin = min(curv_zone)
        cmax = max(curv_zone)
        spread = cmax - cmin
        if spread < 0.05:
            problems.append("Local curvature is uniformly low.")
            tags.add("insufficient curvature")
        if cmin > 0.0 and cmax / max(cmin, 1e-6) > 8.0:
            problems.append("Curvature changes abruptly between zones.")
            tags.add("abrupt transitions")

    for t in transitions:
        if t["status"] == "WEAK":
            problems.append(f"Transition {t['name']} is weak "
                            f"(ratio {t['ratio']:.2f}).")
            tags.add("insufficient anatomical regions")
        if t["status"] == "STRONG":
            problems.append(f"Transition {t['name']} is too strong "
                            f"(ratio {t['ratio']:.2f}).")
            tags.add("abrupt transitions")

    ratio_dw = slices_data["depth"] / max(slices_data["width"], 1e-6)
    if ratio_dw < 0.55:
        problems.append("Head is too flat (D/W too small).")
        tags.add("too flat")
    if ratio_dw > 0.90:
        problems.append("Head is too deep (D/W too large).")
        tags.add("too deep")

    def front_at(t):
        best = min(norm_slices, key=lambda s: abs(s["z_t"] - t))
        return best["front_local"]

    if front_at(0.20) > -0.03:
        problems.append("Forehead projection is insufficient.")
        tags.add("forehead problem")
    if front_at(0.45) > -0.025:
        problems.append("Mid-face projection is insufficient.")
        tags.add("cheekbone problem")
    if front_at(0.92) > -0.025:
        problems.append("Chin projection is insufficient.")
        tags.add("chin problem")

    if not problems:
        problems.append("No significant geometric problems detected.")

    return problems, tags


def _compute_construction_adequacy(param_rows, transitions, shape_sim,
                                   curv_zone):
    sil_err = 0.0
    for row in param_rows:
        if "Width" in row["label"] or row["label"].endswith("width"):
            sil_err += abs(row["deviation_pct"])
    sil_score = max(0.0, 100.0 - sil_err * 2.0)

    prof_err = 0.0
    for row in param_rows:
        if "Depth" in row["label"] or "Height" in row["label"]:
            prof_err += abs(row["deviation_pct"])
    prof_score = max(0.0, 100.0 - prof_err * 2.0)

    if curv_zone:
        spread = max(curv_zone) - min(curv_zone)
        curv_score = _clamp(spread * 200.0, 0.0, 100.0)
    else:
        curv_score = 0.0

    if transitions:
        ratios = [t["ratio"] for t in transitions]
        dev = sum(min(abs(r - 1.0), 0.5) for r in ratios) / len(ratios)
        trans_score = max(0.0, 100.0 - dev * 150.0)
    else:
        trans_score = 0.0

    nonell = _clamp((1.0 - shape_sim) * 200.0, 0.0, 100.0)

    total = (sil_score * W_SILHOUETTE
             + prof_score * W_PROFILE
             + curv_score * W_CURVATURE
             + trans_score * W_TRANSITIONS
             + nonell * W_NONELLIPSOID)
    return {
        "silhouette": sil_score,
        "profile": prof_score,
        "curvature": curv_score,
        "transitions": trans_score,
        "non_ellipsoid": nonell,
        "total": _clamp(total, 0.0, 100.0),
    }


# ============================================================
# 11. ОТЧЁТ
# ============================================================

def _build_report_text(slices_data, norm_slices, ref_slices, param_rows,
                       peak, transitions, curv_zone, shape_sim,
                       problems, tags, adequacy):
    lines = []
    line = "=" * 40

    def P(s=""):
        lines.append(s)

    P()
    P(line)
    P("ALESYA ANATOMICAL HEAD AUDIT")
    P(line)
    P()
    P("REFERENCE is an approximate normalized anatomical model")
    P("of an adult female head used for procedural diagnostics,")
    P("not a universal biological standard.")
    P()

    P("--- DIMENSIONS (world units) ---")
    P(f"Width:   {slices_data['width']:.4f}")
    P(f"Height:  {slices_data['height']:.4f}")
    P(f"Depth:   {slices_data['depth']:.4f}")
    P()

    P("--- NORMALIZED RATIOS ---")
    w = max(slices_data["width"], 1e-6)
    P(f"H / W: {slices_data['height'] / w:.3f}  "
      f"(ref {REF_HEAD_TOTAL_HEIGHT:.3f})")
    P(f"D / W: {slices_data['depth'] / w:.3f}  "
      f"(ref {REF_HEAD_TOTAL_DEPTH:.3f})")
    P(f"D / H: {slices_data['depth'] / max(slices_data['height'], 1e-6):.3f}")
    P()

    P("--- PARAMETER COMPARISON ---")
    for row in param_rows:
        P(f"{row['label']}")
        P(f"  Actual:     {row['actual']:.4f}")
        P(f"  Reference:  {row['reference']:.4f}")
        P(f"  Deviation:  {row['deviation_pct']:+.2f}%")
        P(f"  Status:     {row['status']}")
    P()

    w_max_norm = max(s["width"] for s in norm_slices)
    step = max(1, len(norm_slices) // 20)

    P("--- ACTUAL WIDTH PROFILE ---")
    for i in range(0, len(norm_slices), step):
        s = norm_slices[i]
        bar = _ascii_bar(s["width"], w_max_norm)
        P(f"Z={s['z_t']:+.2f}  {bar}")
    P()

    P("--- REFERENCE WIDTH PROFILE ---")
    for i in range(0, len(ref_slices), step):
        s = ref_slices[i]
        bar = _ascii_bar(s["width"], 1.0)
        P(f"Z={s['z_t']:+.2f}  {bar}")
    P()

    d_max_norm = max(abs(s["front_local"]) for s in norm_slices) or 1.0
    P("--- ACTUAL SIDE PROFILE (front offset, world units) ---")
    for i in range(0, len(norm_slices), step):
        s = norm_slices[i]
        f = s["front_local"]
        bar = _ascii_bar(abs(f) / d_max_norm, 1.0, width=24)
        sign = "←" if f < 0 else " "
        P(f"Z={s['z_t']:+.2f}  {sign} {bar}  ({f:+.4f})")
    P()

    P("--- REFERENCE SIDE PROFILE (scaled, world units) ---")
    for i in range(0, len(ref_slices), step):
        s = ref_slices[i]
        f = s["front_local"]
        bar = _ascii_bar(abs(f) / d_max_norm, 1.0, width=24)
        sign = "←" if f < 0 else " "
        P(f"Z={s['z_t']:+.2f}  {sign} {bar}  ({f:+.4f})")
    P()

    P("--- SURFACE COMPLEXITY ---")
    if curv_zone:
        cmin = min(curv_zone)
        cmax = max(curv_zone)
        cmean = sum(curv_zone) / len(curv_zone)
        spread = cmax - cmin
        P(f"Mean curvature:   {cmean:.4f}")
        P(f"Min curvature:    {cmin:.4f}")
        P(f"Max curvature:    {cmax:.4f}")
        P(f"Spread:           {spread:.4f}")
        P(f"Reference shape similarity: {shape_sim:.3f} "
          f"(1.0 = ideal match with reference profile)")
    P()

    P("--- ANATOMICAL TRANSITIONS ---")
    for t in transitions:
        P(f"{t['name']:<24}  {t['status']:<15}  "
          f"strength {t['strength']:.4f}  "
          f"(ref {t['reference']:.4f}, ratio {t['ratio']:.2f})")
    P()

    P(line)
    P("PRIMARY DIAGNOSIS")
    P(line)
    for p in problems:
        P(f"[!] {p}")
    P()
    P("TAGS")
    for tag in sorted(tags):
        P(f"[x] {tag}")
    if not tags:
        P("(none)")
    P()

    P(line)
    P("CONSTRUCTION DIAGNOSIS")
    P(line)
    P(f"Surface complexity:     "
      f"{'LOW' if adequacy['curvature'] < 40 else 'MEDIUM' if adequacy['curvature'] < 75 else 'HIGH'}")
    P(f"Anatomical separation:  "
      f"{'LOW' if adequacy['transitions'] < 40 else 'MEDIUM' if adequacy['transitions'] < 75 else 'HIGH'}")
    P(f"Profile accuracy:       "
      f"{'LOW' if adequacy['profile'] < 40 else 'MEDIUM' if adequacy['profile'] < 75 else 'HIGH'}")
    P(f"Silhouette accuracy:    "
      f"{'LOW' if adequacy['silhouette'] < 40 else 'MEDIUM' if adequacy['silhouette'] < 75 else 'HIGH'}")
    P()

    total = adequacy["total"]
    P(f"CONSTRUCTION ADEQUACY: {total:.1f} / 100")
    if total > 80:
        verdict = "KEEP CURRENT METHOD"
    elif total > 60:
        verdict = "EXTEND CURRENT METHOD"
    elif total > 40:
        verdict = "EXTEND CURRENT METHOD (limited)"
    else:
        verdict = "CHANGE CONSTRUCTION METHOD"
    P(f"VERDICT: {verdict}")
    P()

    P(line)
    P("ALESYA ANATOMICAL HEAD AUDIT — SUMMARY")
    P(line)
    P(f"Overall proportion:     {adequacy['silhouette']:.1f} / 100")
    P(f"Silhouette similarity:  {adequacy['silhouette']:.1f} / 100")
    P(f"Profile similarity:     {adequacy['profile']:.1f} / 100")
    P(f"Surface complexity:     {adequacy['curvature']:.1f} / 100")
    P(f"Anatomical transitions: {adequacy['transitions']:.1f} / 100")
    P(f"Construction adequacy:  {adequacy['total']:.1f} / 100")
    P()
    P("TOP PROBLEMS")
    for i, p in enumerate(problems[:5], 1):
        P(f"  {i}. {p}")
    P()
    P("CONSTRUCTION VERDICT")
    P(f"  {verdict}")
    P()
    P(line)
    P("RECOMMENDED NEXT CHANGES")
    P(line)
    for i, rec in enumerate(_recommendations(tags, adequacy), 1):
        P(f"  {i}. {rec}")
    P()
    P(line)

    return "\n".join(lines)


def _recommendations(tags, adequacy):
    rec = []
    if "ellipsoid-like" in tags or "insufficient curvature" in tags:
        rec.append("Increase local surface curvature by adding "
                   "explicit anatomical bulges (brow ridge, cheekbones, "
                   "temple depressions, jaw corner).")
    if "forehead problem" in tags:
        rec.append("Push forehead forward and create a distinct "
                   "forehead-to-brow transition.")
    if "cheekbone problem" in tags:
        rec.append("Add outward cheekbone volume at t≈0.45 with "
                   "sharp falloff toward cheeks.")
    if "cheek problem" in tags:
        rec.append("Sculpt cheek hollow below the cheekbone to break "
                   "the smooth ellipsoid.")
    if "jaw problem" in tags or "chin problem" in tags:
        rec.append("Define jaw corner and chin projection as separate "
                   "anatomical features.")
    if "abrupt transitions" in tags:
        rec.append("Soften sharp transitions between zones using "
                   "smoothstep blending across a wider vertical band.")
    if "insufficient anatomical regions" in tags:
        rec.append("Introduce at least 4–5 explicit anatomical zones "
                   "instead of one continuous deformation.")
    if "too flat" in tags:
        rec.append("Increase head depth (D/W) toward reference ~0.72.")
    if "too deep" in tags:
        rec.append("Reduce head depth toward reference ~0.72.")
    if adequacy["total"] < 40:
        rec.insert(0, "Current construction is insufficient. Build head "
                      "from explicit anatomical zones: cranium, brow, "
                      "cheekbone, cheek, jaw, chin.")
    if not rec:
        rec.append("No structural changes required; refine proportions.")
    return rec


# ============================================================
# 12. ПУБЛИЧНЫЙ API
# ============================================================

def run_test() -> None:
    output_dir = _output_dir()

    # --- Математическая диагностика ---
    debug_profile_mapping()
    debug_profile_sphere_base()
    debug_ring_math()
    debug_normalized_profile_mapping()
    debug_max_width_position()
    debug_stage_contributions()
    debug_slice_widths()

    print("Alesya head audit: preparing scene...")
    _clear_scene()
    _setup_render()
    _setup_world()
    _setup_lights()

    test_coll = get_or_create_collection(TEST_COLLECTION_NAME)

    print("Alesya head audit: building head from production module...")
    head = build_head(test_coll)

    print("Alesya head audit: collecting geometry...")
    verts = _collect_vertices(head)

    print("Alesya head audit: measuring slices...")
    slices_data = _measure_slices(verts, NUM_SLICES)
    norm_slices, w_max, d_max = _normalize_slices(slices_data)

    actual_front_scale = max(
        (abs(s["front_local"]) for s in norm_slices), default=1.0
    ) or 1.0
    ref_slices = _reference_slices(NUM_SLICES, actual_front_scale)

    print("Alesya head audit: estimating curvature...")
    curv = _estimate_curvature(verts, head)
    curv_zone = _curvature_zone_profile(verts, curv, slices_data)

    print("Alesya head audit: computing metrics...")
    shape_sim = _reference_shape_similarity(norm_slices, ref_slices)
    param_rows, peak = _build_parameter_table(slices_data, norm_slices)
    transitions = _build_anatomical_transitions(norm_slices)

    problems, tags = _diagnose_problems(
        param_rows, transitions, curv_zone, shape_sim,
        slices_data, norm_slices)

    adequacy = _compute_construction_adequacy(
        param_rows, transitions, shape_sim, curv_zone)

    report_text = _build_report_text(
        slices_data, norm_slices, ref_slices, param_rows,
        peak, transitions, curv_zone, shape_sim,
        problems, tags, adequacy)

    print(report_text)

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "head_test_report.txt"
    report_path.write_text(report_text, encoding="utf-8")
    print(f"Report saved to: {report_path}")

    print("Alesya head audit: rendering diagnostic views...")
    cameras = _build_cameras()
    _render_all(cameras, output_dir)
    bpy.context.scene.camera = cameras["front"]

    print("Alesya head audit: done.")
