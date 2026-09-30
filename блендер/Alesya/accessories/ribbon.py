# -*- coding: utf-8 -*-
"""Декоративная лента на плече (заготовка этапа 1)."""

import bpy

import config as C
from materials import make_material, assign_material
from utils import link_to_collection, shade_smooth


def build_ribbon(coll):
    """Лента на плече — сохраняем как отдельный объект для будущего этапа."""
    mat = make_material("Alesya_Ribbon_Mat", C.RIBBON_COLOR, roughness=0.5)

    body_z = C.NECK_TOP_Z - 0.09 + C.BODY_OFFSET_Z + 0.22
    ribbon_z = body_z + C.BODY_SCALE[2] * 0.30
    ribbon_x = C.BODY_SCALE[0] * 0.28

    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=32, ring_count=12,
        location=(ribbon_x, -C.BODY_SCALE[1] * 0.4, ribbon_z), radius=1.0)
    ribbon = bpy.context.active_object
    ribbon.name = "Alesya_Ribbon"
    ribbon.scale = (0.10, 0.03, 0.055)
    ribbon.rotation_euler[1] = 0  # без наклона — сохраняем поведение
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    shade_smooth(ribbon)
    assign_material(ribbon, mat)
    link_to_collection(ribbon, coll)
