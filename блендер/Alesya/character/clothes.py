# -*- coding: utf-8 -*-
"""Одежда (текущая поварская верхняя часть)."""

import bpy

import config as C
from materials import make_material, assign_material
from utils import link_to_collection, shade_smooth


def build_clothes(coll):
    """Верхняя часть поварской одежды (тело-сфера)."""
    mat_cloth = make_material("Alesya_Coat", C.CLOTHES_WHITE, roughness=0.7)

    body_z = C.NECK_TOP_Z - 0.09 + C.BODY_OFFSET_Z + 0.22
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=48, ring_count=24,
        location=(0, 0, body_z), radius=1.0)
    body = bpy.context.active_object
    body.name = "Alesya_Body"
    body.scale = C.BODY_SCALE
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    for v in body.data.vertices:
        if v.co.z > C.BODY_TOP_CLIP:
            v.co.z = C.BODY_TOP_CLIP
    shade_smooth(body)
    assign_material(body, mat_cloth)
    link_to_collection(body, coll)
