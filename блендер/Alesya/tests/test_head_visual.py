# -*- coding: utf-8 -*-
"""
Alesya — визуальная диагностика формы головы.

Публичный API: run_test() -> None.

Техническая проверка топологии:
  * cage: 1 компонент, без loose, без non-manifold, без degenerate,
    без дубликатов faces, boundary edges только на X≈0;
  * mirror: 1 компонент, 0 boundary edges, 0 non-manifold, без loose,
    без degenerate, без дубликатов faces.

Импорт N_ROWS / N_COLS отсутствует: текущая конструкция
topology-first и не является grid-сеткой.
"""

import math
from collections import defaultdict

import bpy

import config as C
from utils import get_or_create_collection
from materials import make_material
from character.head import build_head


RENDER_RESOLUTION = 800
CAM_LENS          = 85.0

CAM_DISTANCE_FRONT   = 0.60
CAM_DISTANCE_PROFILE = 0.60
CAM_DISTANCE_3Q      = 0.62
CAM_DISTANCE_TOP     = 0.60

NEUTRAL_SKIN_COLOR = (0.80, 0.74, 0.70, 1.0)
NEUTRAL_SKIN_ROUGH = 0.55
NEUTRAL_SKIN_SPEC  = 0.20

BOUNDARY_X_EPS = 1e-5


def _output_dir():
    from pathlib import Path
    here = Path(__file__).resolve()
    return here.parent / "test_output"


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
        bg.inputs[1].default_value = 0.8


def _setup_lights():
    coll = get_or_create_collection("Alesya_Head_Visual_Lights")

    for name, energy, size, loc, rot in [
        ("Head_Key",  500, 3.0, (-1.4, -2.0, C.HEAD_CENTER_Z + 0.7),
         (math.radians(55), 0.0, math.radians(-30))),
        ("Head_Fill", 180, 3.0, ( 1.6, -1.8, C.HEAD_CENTER_Z + 0.1),
         (math.radians(75), 0.0, math.radians(35))),
        ("Head_Rim",  150, 2.0, ( 0.6,  2.2, C.HEAD_CENTER_Z + 0.8),
         (math.radians(-55), 0.0, math.radians(160))),
        ("Head_Top",  200, 2.5, ( 0.0,  0.0, C.HEAD_CENTER_Z + 1.4),
         (0.0, 0.0, 0.0)),
    ]:
        ld = bpy.data.lights.new(name, type='AREA')
        ld.energy = energy
        ld.size = size
        ld.color = (1.0, 1.0, 1.0)
        o = bpy.data.objects.new(name, ld)
        o.location = loc
        o.rotation_euler = rot
        coll.objects.link(o)


def _apply_neutral_material(head):
    mat = make_material(
        "Alesya_Head_Visual_Neutral",
        NEUTRAL_SKIN_COLOR,
        roughness=NEUTRAL_SKIN_ROUGH,
        specular=NEUTRAL_SKIN_SPEC,
    )
    if head.data.materials:
        head.data.materials[0] = mat
    else:
        head.data.materials.append(mat)


# ============================================================
# TOPOLOGY METRICS
# ============================================================

def _collect_topology_metrics(mesh):
    n_verts = len(mesh.vertices)
    n_edges = len(mesh.edges)
    n_faces = len(mesh.polygons)

    edge_key_to_index = {}
    for e in mesh.edges:
        key = (min(e.vertices), max(e.vertices))
        edge_key_to_index[key] = e.index

    edge_face_count = {e.index: 0 for e in mesh.edges}
    for poly in mesh.polygons:
        vs = list(poly.vertices)
        n = len(vs)
        for i in range(n):
            a = vs[i]
            b = vs[(i + 1) % n]
            key = (min(a, b), max(a, b))
            e_idx = edge_key_to_index.get(key)
            if e_idx is not None:
                edge_face_count[e_idx] += 1

    boundary_edges = [i for i, c in edge_face_count.items() if c == 1]
    non_manifold_edges = [i for i, c in edge_face_count.items() if c > 2]
    loose_edges = [i for i, c in edge_face_count.items() if c == 0]

    used_verts = set()
    for poly in mesh.polygons:
        for v in poly.vertices:
            used_verts.add(v)
    for e in mesh.edges:
        for v in e.vertices:
            used_verts.add(v)
    loose_verts = [i for i in range(n_verts) if i not in used_verts]

    degenerate_faces = 0
    mesh.update()
    for poly in mesh.polygons:
        vs = list(poly.vertices)
        if len(set(vs)) < len(vs):
            degenerate_faces += 1
            continue
        if poly.area < 1e-9:
            degenerate_faces += 1

    parent = list(range(n_verts))
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
    roots = set(find(i) for i in range(n_verts))
    components = len(roots)

    boundary_on_x0 = []
    boundary_off_x0 = []
    for e_idx in boundary_edges:
        e = mesh.edges[e_idx]
        v0 = mesh.vertices[e.vertices[0]].co
        v1 = mesh.vertices[e.vertices[1]].co
        if abs(v0.x) < BOUNDARY_X_EPS and abs(v1.x) < BOUNDARY_X_EPS:
            boundary_on_x0.append(e_idx)
        else:
            boundary_off_x0.append(e_idx)

    # --- duplicate faces (canonical, независимо от порядка вершин) ---
    canonical = defaultdict(list)
    for poly in mesh.polygons:
        key = tuple(sorted(poly.vertices))
        canonical[key].append(poly.index)
    duplicate_faces = [idxs for idxs in canonical.values() if len(idxs) > 1]

    # --- детали boundary off X=0 ---
    boundary_off_details = []
    for e_idx in boundary_off_x0:
        e = mesh.edges[e_idx]
        i0 = e.vertices[0]
        i1 = e.vertices[1]
        co0 = mesh.vertices[i0].co
        co1 = mesh.vertices[i1].co
        boundary_off_details.append({
            "edge_index": e_idx,
            "v0_index": i0,
            "v1_index": i1,
            "v0_co": (co0.x, co0.y, co0.z),
            "v1_co": (co1.x, co1.y, co1.z),
        })

    return {
        "n_verts": n_verts,
        "n_edges": n_edges,
        "n_faces": n_faces,
        "boundary_edges": boundary_edges,
        "boundary_on_x0": boundary_on_x0,
        "boundary_off_x0": boundary_off_x0,
        "boundary_off_details": boundary_off_details,
        "non_manifold_edges": non_manifold_edges,
        "loose_edges": loose_edges,
        "loose_verts": loose_verts,
        "degenerate_faces": degenerate_faces,
        "components": components,
        "duplicate_faces": duplicate_faces,
    }


def _print_topology_report(label, m):
    print()
    print(f"=== {label} ===")
    print(f"  vertices              : {m['n_verts']}")
    print(f"  edges                 : {m['n_edges']}")
    print(f"  faces                 : {m['n_faces']}")
    print(f"  boundary edges        : {len(m['boundary_edges'])}")
    print(f"    on X=0 plane        : {len(m['boundary_on_x0'])}")
    print(f"    off X=0 plane       : {len(m['boundary_off_x0'])}")
    print(f"  non-manifold edges    : {len(m['non_manifold_edges'])}")
    print(f"  loose edges           : {len(m['loose_edges'])}")
    print(f"  loose vertices        : {len(m['loose_verts'])}")
    print(f"  degenerate faces      : {m['degenerate_faces']}")
    print(f"  connected components  : {m['components']}")
    print(f"  duplicate faces       : {len(m['duplicate_faces'])}")

    if m["boundary_off_details"]:
        print()
        print("  --- boundary edges off X=0 (details) ---")
        for det in m["boundary_off_details"]:
            x0, y0, z0 = det["v0_co"]
            x1, y1, z1 = det["v1_co"]
            print(f"  edge[{det['edge_index']}]: "
                  f"v{det['v0_index']} -> v{det['v1_index']}")
            print(f"    A = ({x0:+.4f}, {y0:+.4f}, {z0:+.4f})")
            print(f"    B = ({x1:+.4f}, {y1:+.4f}, {z1:+.4f})")
        print("  --- end details ---")

    if m["duplicate_faces"]:
        print()
        print("  --- duplicate faces ---")
        for idxs in m["duplicate_faces"]:
            print(f"  duplicate polygon indices: {idxs}")
        print("  --- end duplicate faces ---")

    print(f"=== END {label} ===")
    print()


def _assert_cage(m):
    problems = []
    if m["components"] != 1:
        problems.append(f"components={m['components']}, expected 1")
    if m["loose_verts"]:
        problems.append(f"loose_verts={len(m['loose_verts'])}")
    if m["loose_edges"]:
        problems.append(f"loose_edges={len(m['loose_edges'])}")
    if m["non_manifold_edges"]:
        problems.append(
            f"non_manifold_edges={len(m['non_manifold_edges'])}")
    if m["degenerate_faces"]:
        problems.append(f"degenerate_faces={m['degenerate_faces']}")
    if m["boundary_off_x0"]:
        problems.append(
            f"boundary edges off X=0: {len(m['boundary_off_x0'])} "
            f"(expected all boundary on X=0)"
        )
    if m["duplicate_faces"]:
        problems.append(
            f"duplicate_faces={len(m['duplicate_faces'])}")
    if problems:
        raise AssertionError("CAGE TOPOLOGY FAILURE:\n  - "
                             + "\n  - ".join(problems))


def _assert_mirrored(m):
    problems = []
    if m["components"] != 1:
        problems.append(f"components={m['components']}, expected 1")
    if m["boundary_edges"]:
        problems.append(
            f"boundary_edges={len(m['boundary_edges'])}, expected 0")
    if m["non_manifold_edges"]:
        problems.append(
            f"non_manifold_edges={len(m['non_manifold_edges'])}")
    if m["loose_verts"]:
        problems.append(f"loose_verts={len(m['loose_verts'])}")
    if m["loose_edges"]:
        problems.append(f"loose_edges={len(m['loose_edges'])}")
    if m["degenerate_faces"]:
        problems.append(f"degenerate_faces={m['degenerate_faces']}")
    if m["duplicate_faces"]:
        problems.append(
            f"duplicate_faces={len(m['duplicate_faces'])}")
    if problems:
        raise AssertionError("MIRROR TOPOLOGY FAILURE:\n  - "
                             + "\n  - ".join(problems))


def _evaluate_mirrored_mesh(cage):
    temp = cage.copy()
    temp.data = cage.data.copy()
    temp.name = "Alesya_Head_MirrorEvalTemp"
    bpy.context.scene.collection.objects.link(temp)
    try:
        for mod in list(temp.modifiers):
            if mod.type != 'MIRROR':
                temp.modifiers.remove(mod)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        eval_obj = temp.evaluated_get(depsgraph)
        mesh = eval_obj.to_mesh()
        try:
            metrics = _collect_topology_metrics(mesh)
        finally:
            eval_obj.to_mesh_clear()
        return metrics
    finally:
        for coll in list(temp.users_collection):
            coll.objects.unlink(temp)
        bpy.data.objects.remove(temp, do_unlink=True)


# ============================================================
# КАМЕРЫ
# ============================================================

def _make_camera(name, coll, location, rotation):
    cd = bpy.data.cameras.new(name + "_Data")
    cd.lens = CAM_LENS
    cd.type = 'PERSP'
    cam = bpy.data.objects.new(name, cd)
    cam.location = location
    cam.rotation_euler = rotation
    coll.objects.link(cam)
    return cam


def _build_cameras():
    coll = get_or_create_collection("Alesya_Head_Visual_Cameras")
    h = C.HEAD_CENTER_Z

    cam_front = _make_camera(
        "Alesya_Head_Visual_Cam_Front", coll,
        (0.0, -CAM_DISTANCE_FRONT, h),
        (math.radians(90), 0.0, 0.0))
    cam_profile = _make_camera(
        "Alesya_Head_Visual_Cam_Profile", coll,
        (CAM_DISTANCE_PROFILE, 0.0, h),
        (math.radians(90), 0.0, math.radians(90)))

    ang = math.radians(40)
    cx = -CAM_DISTANCE_3Q * math.sin(ang)
    cy = -CAM_DISTANCE_3Q * math.cos(ang)
    cam_3q = _make_camera(
        "Alesya_Head_Visual_Cam_3Q", coll,
        (cx, cy, h),
        (math.radians(90), 0.0, ang))

    cam_top = _make_camera(
        "Alesya_Head_Visual_Cam_Top", coll,
        (0.0, 0.0, h + CAM_DISTANCE_TOP),
        (0.0, 0.0, 0.0))

    return {
        "front": cam_front,
        "profile": cam_profile,
        "3q": cam_3q,
        "top": cam_top,
    }


def _render_view(cam, filename, output_dir):
    scene = bpy.context.scene
    scene.camera = cam
    output_dir.mkdir(parents=True, exist_ok=True)
    render_path = output_dir / filename
    scene.render.filepath = str(render_path)
    bpy.ops.render.render(write_still=True)
    print(f"Rendered: {render_path}")


# ============================================================
# ПУБЛИЧНЫЙ API
# ============================================================

def run_test() -> None:
    output_dir = _output_dir()

    print("Alesya head visual test: preparing isolated scene...")
    _clear_scene()
    _setup_render()
    _setup_world()
    _setup_lights()

    coll = get_or_create_collection("Alesya_Head_Visual")

    print("Alesya head visual test: building head only...")
    head = build_head(coll)

    if head is None:
        raise AssertionError("build_head returned None")

    cage_metrics = _collect_topology_metrics(head.data)
    _print_topology_report("TOPOLOGY VALIDATION (CAGE)", cage_metrics)
    _assert_cage(cage_metrics)

    mirror_metrics = _evaluate_mirrored_mesh(head)
    _print_topology_report("TOPOLOGY VALIDATION (MIRROR)", mirror_metrics)
    _assert_mirrored(mirror_metrics)

    print("Modifiers on Alesya_Head:")
    for m in head.modifiers:
        print(f"  {m.name}: {m.type}")
    print()

    _apply_neutral_material(head)

    hide_prefixes = (
        "Alesya_Eyes_Root", "Alesya_Eye_", "Alesya_Iris_",
        "Alesya_IrisRing_", "Alesya_Pupil_", "Alesya_Highlight_",
        "Alesya_Eyelid_", "Alesya_EyelidShadow_", "Alesya_Brow_",
        "Alesya_Landmark_", "Alesya_Diag_", "Alesya_Hair_",
        "Alesya_Hat", "Alesya_Ribbon", "Alesya_Flower",
        "Alesya_Neck", "Alesya_Body", "Alesya_Coat",
    )
    for obj in list(bpy.data.objects):
        if obj.name.startswith(hide_prefixes):
            obj.hide_render = True
            obj.hide_viewport = True

    visible_objects = [o for o in bpy.data.objects
                       if not o.hide_render and o.type in ('MESH', 'EMPTY')]
    print("Alesya head visual test: visible objects in scene:")
    for o in visible_objects:
        print(f"  {o.name}")

    bpy.context.view_layer.update()

    cameras = _build_cameras()

    _render_view(cameras["front"],
                 "head_visual_front.png", output_dir)
    _render_view(cameras["profile"],
                 "head_visual_profile.png", output_dir)
    _render_view(cameras["3q"],
                 "head_visual_3q.png", output_dir)
    _render_view(cameras["top"],
                 "head_visual_top.png", output_dir)

    bpy.context.scene.camera = cameras["front"]

    print("Alesya head visual test: done.")
