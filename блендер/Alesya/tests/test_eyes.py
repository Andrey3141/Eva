# -*- coding: utf-8 -*-
"""
Alesya — диагностика посадки глаз.

Проверки:

  1. Отчёт обо всех объектах глаз.
  2. Симметрия L ↔ R по мировым координатам.
  3. Абсолютная проверка положения бровей.
  4. HEAD ↔ EYES POSITION TEST (диагностический режим).
  5. EYE VISIBILITY / PLACEMENT — проверка, что фактическая
     геометрия глаз выступает перед поверхностью лица.
  6. HEAD LOCAL/WORLD Z CHECK.
  7. HEAD Z ORIGIN DIAGNOSTIC.
"""

import math
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

import config as C
from utils import get_or_create_collection
from character.head import build_head
from character.eyes import build_eyes


EPSILON = 1e-4

SYMMETRY_PAIRS = [
    ("Alesya_Eye_L",          "Alesya_Eye_R"),
    ("Alesya_Iris_L",         "Alesya_Iris_R"),
    ("Alesya_Pupil_L",        "Alesya_Pupil_R"),
    ("Alesya_Highlight_L",    "Alesya_Highlight_R"),
    ("Alesya_Eyelid_L",       "Alesya_Eyelid_R"),
    ("Alesya_Eyelid_Lower_L", "Alesya_Eyelid_Lower_R"),
    ("Alesya_Brow_L",         "Alesya_Brow_R"),
]

# Ожидаемые мировые координаты бровей.
# Y вычисляется по коду eyes.py:
#     center_y = EYE_Y_FRONT - EYE_DEPTH * 0.20
#              = -0.1630 - 0.034 * 0.20
#              = -0.1698
EXPECTED_BROW_POSITIONS = {
    "Alesya_Brow_L": (-0.072, -0.1698, 1.690),
    "Alesya_Brow_R": (+0.072, -0.1698, 1.690),
}

EYE_HEAD_MAX_DISTANCE = 0.30

PROTRUSION_MIN = 0.001


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
        bg.inputs[1].default_value = 0.9


def _setup_lights():
    coll = get_or_create_collection("Alesya_Eyes_Test_Lights")
    for name, energy, size, loc, rot in [
        ("Eyes_Key",  400, 2.5, (-1.5, -2.2, C.HEAD_CENTER_Z + 0.6),
         (1.05, 0.0, -0.55)),
        ("Eyes_Fill",  90, 2.5, ( 1.8, -1.8, C.HEAD_CENTER_Z + 0.1),
         (1.25, 0.0,  0.90)),
        ("Eyes_Rim",  120, 1.8, ( 0.0,  2.4, C.HEAD_CENTER_Z + 0.7),
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
    coll = get_or_create_collection("Alesya_Eyes_Test_Camera")
    cd = bpy.data.cameras.new("Eyes_Test_Camera_Data")
    cd.lens = 80.0
    cd.type = 'PERSP'
    cam = bpy.data.objects.new("Eyes_Test_Camera", cd)
    cam.location = (0.0, -0.55, C.HEAD_CENTER_Z + 0.02)
    cam.rotation_euler = (math.radians(90), 0.0, 0.0)
    coll.objects.link(cam)
    return cam


def _print_object_report():
    names = [
        "Alesya_Eyes_Root",
        "Alesya_Eye_L", "Alesya_Eye_R",
        "Alesya_Iris_L", "Alesya_Iris_R",
        "Alesya_Pupil_L", "Alesya_Pupil_R",
        "Alesya_Highlight_L", "Alesya_Highlight_R",
        "Alesya_Eyelid_L", "Alesya_Eyelid_R",
        "Alesya_Eyelid_Lower_L", "Alesya_Eyelid_Lower_R",
        "Alesya_Brow_L", "Alesya_Brow_R",
    ]
    print()
    print("=== EYES OBJECT REPORT ===")
    for name in names:
        obj = bpy.data.objects.get(name)
        if obj is None:
            print(f"[MISSING] {name}")
            continue
        loc = obj.matrix_world.translation
        parent = obj.parent.name if obj.parent else "-"
        print(f"[OK]      {name:<26} "
              f"loc=({loc.x:+.4f}, {loc.y:+.4f}, {loc.z:+.4f})  "
              f"parent={parent}")
    print("=== END EYES OBJECT REPORT ===")
    print()


def _world_location(obj):
    return obj.matrix_world.translation


def _check_symmetry() -> bool:
    print()
    print("=== EYES SYMMETRY TEST ===")

    failed_pairs = []
    for left_name, right_name in SYMMETRY_PAIRS:
        label = f"{left_name.replace('Alesya_', '')} ↔ " \
                f"{right_name.replace('Alesya_', '')}"

        left = bpy.data.objects.get(left_name)
        right = bpy.data.objects.get(right_name)

        if left is None or right is None:
            missing = []
            if left is None:
                missing.append(left_name)
            if right is None:
                missing.append(right_name)
            print(f"[FAIL] {label}  — missing: {', '.join(missing)}")
            failed_pairs.append(label)
            continue

        lp = _world_location(left)
        rp = _world_location(right)

        dx = abs(lp.x + rp.x)
        dy = abs(lp.y - rp.y)
        dz = abs(lp.z - rp.z)

        ok = (dx < EPSILON and dy < EPSILON and dz < EPSILON)

        if ok:
            print(f"[PASS] {label}")
        else:
            print(f"[FAIL] {label}  — "
                  f"dx={dx:.6f}  dy={dy:.6f}  dz={dz:.6f}  "
                  f"(left=({lp.x:+.4f}, {lp.y:+.4f}, {lp.z:+.4f}), "
                  f"right=({rp.x:+.4f}, {rp.y:+.4f}, {rp.z:+.4f}))")
            failed_pairs.append(label)

    print("=== END EYES SYMMETRY TEST ===")
    print()

    if failed_pairs:
        raise AssertionError(
            f"Eyes symmetry check failed for: {', '.join(failed_pairs)}"
        )
    return True


def _check_brow_positions():
    print()
    print("=== BROW POSITION TEST ===")

    for name, expected in EXPECTED_BROW_POSITIONS.items():
        obj = bpy.data.objects.get(name)

        if obj is None:
            raise AssertionError(f"Missing object: {name}")

        actual = obj.matrix_world.translation

        dx = abs(actual.x - expected[0])
        dy = abs(actual.y - expected[1])
        dz = abs(actual.z - expected[2])

        if dx >= EPSILON or dy >= EPSILON or dz >= EPSILON:
            print(
                f"[FAIL] {name} — "
                f"actual=({actual.x:+.4f}, {actual.y:+.4f}, {actual.z:+.4f}), "
                f"expected=({expected[0]:+.4f}, "
                f"{expected[1]:+.4f}, {expected[2]:+.4f})"
            )
            raise AssertionError(
                f"{name} has incorrect world position"
            )

        print(f"[PASS] {name}")

    print("=== END BROW POSITION TEST ===")
    print()


def _build_head_bvh():
    head = bpy.data.objects.get("Alesya_Head")
    if head is None:
        raise AssertionError("Missing object: Alesya_Head")

    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = head.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()

    try:
        matrix = evaluated.matrix_world
        world_verts = [matrix @ v.co for v in mesh.vertices]
        polygons = [list(poly.vertices) for poly in mesh.polygons]

        if world_verts:
            xs = [v.x for v in world_verts]
            ys = [v.y for v in world_verts]
            zs = [v.z for v in world_verts]
            print()
            print("=== HEAD WORLD BOUNDS ===")
            print(f"X: min {min(xs):+.4f}  max {max(xs):+.4f}")
            print(f"Y: min {min(ys):+.4f}  max {max(ys):+.4f}")
            print(f"Z: min {min(zs):+.4f}  max {max(zs):+.4f}")
            print("=== END HEAD WORLD BOUNDS ===")
            print()

        return BVHTree.FromPolygons(world_verts, polygons)
    finally:
        evaluated.to_mesh_clear()


def _check_eye_head_positions():
    print()
    print("=== HEAD ↔ EYES POSITION TEST (diagnostic) ===")

    bvh = _build_head_bvh()

    directions = [
        ("+Y", Vector((0.0,  1.0, 0.0))),
        ("-Y", Vector((0.0, -1.0, 0.0))),
    ]

    for name in ("Alesya_Eye_L", "Alesya_Eye_R"):
        eye = bpy.data.objects.get(name)
        if eye is None:
            raise AssertionError(f"Missing object: {name}")

        origin = eye.matrix_world.translation.copy()

        for label, direction in directions:
            location, normal, index, distance = bvh.ray_cast(
                origin, direction, EYE_HEAD_MAX_DISTANCE)

            print(f"[{label}] {name}")
            print(f"    origin=({origin.x:+.4f}, "
                  f"{origin.y:+.4f}, {origin.z:+.4f})")

            if location is None:
                print(f"    NO HIT within {EYE_HEAD_MAX_DISTANCE:.3f}")
            else:
                print(f"    hit=({location.x:+.4f}, "
                      f"{location.y:+.4f}, {location.z:+.4f})")
                print(f"    distance={distance:.4f}")

    print("=== END HEAD ↔ EYES POSITION TEST ===")
    print()


def _world_bounds_of(obj):
    mw = obj.matrix_world
    coords = [mw @ v.co for v in obj.data.vertices]
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
    }


def _head_front_y_at(bvh, x, z, y_start=-0.05, max_dist=0.30):
    origin = Vector((x, y_start, z))
    direction = Vector((0.0, -1.0, 0.0))
    location, normal, index, distance = bvh.ray_cast(
        origin, direction, max_dist)
    if location is None:
        return None
    return location.y


def _check_eye_visibility():
    print()
    print("=== EYE VISIBILITY / PLACEMENT ===")

    bvh = _build_head_bvh()

    failed = []

    for name in ("Alesya_Eye_L", "Alesya_Eye_R"):
        eye = bpy.data.objects.get(name)
        if eye is None:
            raise AssertionError(f"Missing object: {name}")

        wb = _world_bounds_of(eye)
        if wb is None:
            raise AssertionError(f"{name} has no geometry")

        center = wb["center"]
        eye_front_y = wb["min"].y

        head_front_y = _head_front_y_at(
            bvh, x=center.x, z=center.z)

        print(f"{name.replace('Alesya_', '').upper()}:")
        print(f"  center       = ({center.x:+.4f}, "
              f"{center.y:+.4f}, {center.z:+.4f})")
        print(f"  world_min    = ({wb['min'].x:+.4f}, "
              f"{wb['min'].y:+.4f}, {wb['min'].z:+.4f})")
        print(f"  world_max    = ({wb['max'].x:+.4f}, "
              f"{wb['max'].y:+.4f}, {wb['max'].z:+.4f})")

        if head_front_y is None:
            print(f"  head_front_at_eye = NOT FOUND")
            print(f"  protrusion        = N/A")
            failed.append(name)
            print()
            continue

        protrusion = head_front_y - eye_front_y

        print(f"  head_front_at_eye = ({center.x:+.4f}, "
              f"{head_front_y:+.4f}, {center.z:+.4f})")
        print(f"  protrusion        = {protrusion:+.4f}")

        if protrusion < PROTRUSION_MIN:
            print(f"  [FAIL] eye is not in front of head surface")
            failed.append(name)
        else:
            print(f"  [PASS]")
        print()

    print("=== END EYE VISIBILITY / PLACEMENT ===")
    print()

    if failed:
        raise AssertionError(
            "Eye visibility check failed for: " + ", ".join(failed)
        )
    else:
        print("[PASS] eyes are positioned in front of head surface")


def _check_head_local_world_z():
    print()
    print("=== HEAD LOCAL/WORLD Z CHECK ===")

    head = bpy.data.objects.get("Alesya_Head")
    if head is None:
        raise AssertionError("Missing object: Alesya_Head")

    local_zs = [v.co.z for v in head.data.vertices]
    if not local_zs:
        raise AssertionError("Alesya_Head mesh has no vertices")

    local_min = min(local_zs)
    local_max = max(local_zs)

    mw = head.matrix_world
    world_zs = [(mw @ v.co).z for v in head.data.vertices]
    world_min = min(world_zs)
    world_max = max(world_zs)

    expected_world_min = C.HEAD_CENTER_Z + local_min
    expected_world_max = C.HEAD_CENTER_Z + local_max

    print(f"local_z_min = {local_min:+.6f}")
    print(f"local_z_max = {local_max:+.6f}")
    print(f"world_z_min = {world_min:+.6f}")
    print(f"world_z_max = {world_max:+.6f}")
    print(f"expected_world_z_min = {expected_world_min:+.6f}")
    print(f"expected_world_z_max = {expected_world_max:+.6f}")

    ok = (abs(world_min - expected_world_min) < EPSILON and
          abs(world_max - expected_world_max) < EPSILON)

    if not ok:
        raise AssertionError(
            "world_z != HEAD_CENTER_Z + local_z. "
            "Возможно, HEAD_CENTER_Z применяется дважды."
        )

    print("[PASS] world_z == C.HEAD_CENTER_Z + local_z")
    print("=== END HEAD LOCAL/WORLD Z CHECK ===")
    print()


def _head_z_origin_diagnostic():
    print()
    print("=== HEAD Z ORIGIN DIAGNOSTIC ===")
    print()
    print(f"C.HEAD_CENTER_Z = {C.HEAD_CENTER_Z!r}")
    print("=== END HEAD Z ORIGIN DIAGNOSTIC ===")
    print()


def run_test() -> None:
    output_dir = _output_dir()

    print("Alesya eyes test: preparing scene...")
    _clear_scene()
    _setup_render()
    _setup_world()
    _setup_lights()

    coll = get_or_create_collection("Alesya_Eyes_Test")

    print("Alesya eyes test: building head...")
    build_head(coll)

    print("Alesya eyes test: building eyes...")
    build_eyes(coll)

    _print_object_report()
    _check_symmetry()
    _check_brow_positions()
    _check_eye_head_positions()
    _check_eye_visibility()
    _check_head_local_world_z()
    _head_z_origin_diagnostic()

    cam = _build_camera()
    bpy.context.scene.camera = cam

    output_dir.mkdir(parents=True, exist_ok=True)
    render_path = output_dir / "eyes_test_front.png"
    bpy.context.scene.render.filepath = str(render_path)
    bpy.ops.render.render(write_still=True)
    print(f"Rendered: {render_path}")

    print("Alesya eyes test: done.")
