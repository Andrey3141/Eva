# -*- coding: utf-8 -*-
"""Голубые цветы возле плеча (заготовка этапа 1)."""

import bpy
import math

import config as C
from materials import make_material, assign_material
from utils import link_to_collection, shade_smooth


def build_flowers(coll):
    mat_blue = make_material("Alesya_Flower_Blue_Mat", C.FLOWER_BLUE, roughness=0.5)
    mat_core = make_material("Alesya_Flower_Core_Mat", C.FLOWER_CORE, roughness=0.5)

    body_z = C.NECK_TOP_Z - 0.09 + C.BODY_OFFSET_Z + 0.22
    flower_z = body_z + C.BODY_SCALE[2] * 0.42

    positions = [
        ("Alesya_Flower_L", -C.BODY_SCALE[0] * 0.33, flower_z),
        ("Alesya_Flower_R",  C.BODY_SCALE[0] * 0.33, flower_z + 0.02),
    ]

    for name, x, z in positions:
        for i in range(5):
            ang = math.radians(72 * i)
            px = x + math.cos(ang) * 0.028
            pz = z + math.sin(ang) * 0.028
            bpy.ops.mesh.primitive_uv_sphere_add(
                segments=16, ring_count=8,
                location=(px, -C.BODY_SCALE[1] * 0.5, pz), radius=1.0)
            petal = bpy.context.active_object
            petal.name = f"{name}_Petal_{i}"
            petal.scale = (0.022, 0.008, 0.022)
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
            shade_smooth(petal)
            assign_material(petal, mat_blue)
            link_to_collection(petal, coll)

        bpy.ops.mesh.primitive_uv_sphere_add(
            segments=16, ring_count=8,
            location=(x, -C.BODY_SCALE[1] * 0.5 - 0.004, z), radius=1.0)
        core = bpy.context.active_object
        core.name = f"{name}_Core"
        core.scale = (0.012, 0.006, 0.012)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        shade_smooth(core)
        assign_material(core, mat_core)
        link_to_collection(core, coll)

        bpy.ops.object.empty_add(type='PLAIN_AXES',
                                 location=(x, -C.BODY_SCALE[1] * 0.5, z))
        ctrl = bpy.context.active_object
        ctrl.name = name
        ctrl.empty_display_size = 0.03
        link_to_collection(ctrl, coll)
