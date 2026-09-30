# -*- coding: utf-8 -*-
"""
Alesya — визуальная диагностика производственных глаз.

Публичный API: run_test() -> None.

Строит настоящие голову и глаза и печатает:

  * EYE DEPTH ORDER — по world-bounds передних границ
    объектов: Eye / Iris / Pupil / Highlight / Eyelid / LowerEyelid.
  * EYE VISUAL DIAGNOSTIC — полный отчёт world-bounds.

Рендерит eyes_visual_diagnostic.png.
"""

import math
import bpy
from mathutils import Vector

import config as C
from utils import get_or_create_collection
from character.head import build_head
from character.eyes import build_eyes


RENDER_RESOLUTION    = 800
CAMERA_DISTANCE      = 0.55
CAMERA_LENS          = 90.0


# ============================================================
# УТИЛИТЫ
# ============================================================

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
    coll = get_or_create_collection("Alesya_Eyes_Visual_Lights")
    for name, energy, size, loc, rot in [
        ("Vis_Key",  500, 3.0, (-1.4, -2.0, C.HEAD_CENTER_Z + 0.6),
         (1.05, 0.0, -0.55)),
        ("Vis_Fill", 200, 3.0, ( 1.6, -1.8, C.HEAD_CENTER_Z + 0.1),
         (1.25, 0.0,  0.90)),
        ("Vis_Rim",  150, 2.0, ( 0.0,  2.4, C.HEAD_CENTER_Z + 0.7),
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
    coll = get_or_create_collection("Alesya_Eyes_Visual_Camera")
    cd = bpy.data.cameras.new("Eyes_Visual_Camera_Data")
    cd.lens = CAMERA_LENS
    cd.type = 'PERSP'
    cam = bpy.data.objects.new("Eyes_Visual_Camera", cd)
    cam.location = (0.0, -CAMERA_DISTANCE, C.HEAD_CENTER_Z + 0.01)
    cam.rotation_euler = (math.radians(90), 0.0, 0.0)
    coll.objects.link(cam)
    return cam


def _world_bounds(obj):
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


def _fmt(v):
    return f"({v.x:+.4f}, {v.y:+.4f}, {v.z:+.4f})"


def _front_y(obj):
    wb = _world_bounds(obj)
    if wb is None:
        return None
    return wb["min"].y


def _print_depth_order():
    print()
    print("=== EYE DEPTH ORDER ===")
    print()

    def fy(name):
        obj = bpy.data.objects.get(name)
        if obj is None:
            return None
        return _front_y(obj)

    eye_l  = fy("Alesya_Eye_L")
    iris_l = fy("Alesya_Iris_L")
    pup_l  = fy("Alesya_Pupil_L")
    hl_l   = fy("Alesya_Highlight_L")
    up_l   = fy("Alesya_Eyelid_L")
    lo_l   = fy("Alesya_Eyelid_Lower_L")

    def show(label, value):
        if value is None:
            print(f"{label}: MISSING")
        else:
            print(f"{label}: {value:+.4f}")

    print("LEFT EYE:")
    show("  Eye front      ", eye_l)
    show("  Iris front     ", iris_l)
    show("  Pupil front    ", pup_l)
    show("  Highlight front", hl_l)
    show("  Upper eyelid   ", up_l)
    show("  Lower eyelid   ", lo_l)
    print()

    eye_r  = fy("Alesya_Eye_R")
    iris_r = fy("Alesya_Iris_R")
    pup_r  = fy("Alesya_Pupil_R")
    hl_r   = fy("Alesya_Highlight_R")
    up_r   = fy("Alesya_Eyelid_R")
    lo_r   = fy("Alesya_Eyelid_Lower_R")

    print("RIGHT EYE:")
    show("  Eye front      ", eye_r)
    show("  Iris front     ", iris_r)
    show("  Pupil front    ", pup_r)
    show("  Highlight front", hl_r)
    show("  Upper eyelid   ", up_r)
    show("  Lower eyelid   ", lo_r)
    print()

    print("=== END EYE DEPTH ORDER ===")
    print()

    # --- Проверки глубины и наличия поверхности ---
    def chk(label, cond):
        print(f"[{'PASS' if cond else 'FAIL'}] {label}")

    if iris_l is not None and pup_l is not None:
        chk("pupil is in front of iris (L)", pup_l < iris_l)
    if iris_r is not None and pup_r is not None:
        chk("pupil is in front of iris (R)", pup_r < iris_r)

    if iris_l is not None and hl_l is not None:
        chk("highlight is in front of iris (L)", hl_l < iris_l)
    if iris_r is not None and hl_r is not None:
        chk("highlight is in front of iris (R)", hl_r < iris_r)

    upper_ok = all(v is not None for v in (up_l, up_r))
    lower_ok = all(v is not None for v in (lo_l, lo_r))
    chk("upper eyelid has finite surface", upper_ok)
    chk("lower eyelid has finite surface", lower_ok)
    print()


def _print_visual_diagnostic():
    print()
    print("=== EYE VISUAL DIAGNOSTIC ===")
    print()

    for name in (
        "Alesya_Eye_L", "Alesya_Eye_R",
        "Alesya_Iris_L", "Alesya_Iris_R",
        "Alesya_IrisRing_L", "Alesya_IrisRing_R",
        "Alesya_Pupil_L", "Alesya_Pupil_R",
        "Alesya_Highlight_L", "Alesya_Highlight_R",
        "Alesya_Eyelid_L", "Alesya_Eyelid_R",
        "Alesya_Eyelid_Lower_L", "Alesya_Eyelid_Lower_R",
    ):
        obj = bpy.data.objects.get(name)
        if obj is None:
            print(f"[MISSING] {name}")
            continue
        wb = _world_bounds(obj)
        if wb is None:
            print(f"[EMPTY]   {name}")
            continue
        print(f"{name}:")
        print(f"  world_min = {_fmt(wb['min'])}")
        print(f"  world_max = {_fmt(wb['max'])}")
        print(f"  center    = {_fmt(wb['center'])}")
        print(f"  y_front   = {wb['min'].y:+.4f}")
        print()

    print("=== END EYE VISUAL DIAGNOSTIC ===")
    print()


# ============================================================
# ПУБЛИЧНЫЙ API
# ============================================================

def run_test() -> None:
    output_dir = _output_dir()

    print("Alesya eyes visual test: preparing scene...")
    _clear_scene()
    _setup_render()
    _setup_world()
    _setup_lights()

    coll = get_or_create_collection("Alesya_Eyes_Visual")

    print("Alesya eyes visual test: building head...")
    build_head(coll)

    print("Alesya eyes visual test: building production eyes...")
    build_eyes(coll)

    bpy.context.view_layer.update()

    _print_depth_order()
    _print_visual_diagnostic()

    cam = _build_camera()
    bpy.context.scene.camera = cam

    output_dir.mkdir(parents=True, exist_ok=True)
    render_path = output_dir / "eyes_visual_diagnostic.png"
    bpy.context.scene.render.filepath = str(render_path)
    bpy.ops.render.render(write_still=True)
    print(f"Rendered: {render_path}")

    print("Alesya eyes visual test: done.")
