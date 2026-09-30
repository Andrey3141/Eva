# -*- coding: utf-8 -*-
"""Поварской колпак."""

import bpy

import config as C
from materials import make_material, assign_material
from utils import link_to_collection, shade_smooth


def build_hat(coll):
    mat = make_material("Alesya_Hat_Mat", C.HAT_COLOR, roughness=0.65)

    bpy.ops.mesh.primitive_cylinder_add(
        vertices=48, radius=C.HAT_BAND_RADIUS, depth=C.HAT_BAND_DEPTH,
        location=(0, 0, C.HAT_BAND_Z))
    band = bpy.context.active_object
    band.name = "Alesya_Hat_Band"
    shade_smooth(band)
    assign_material(band, mat)
    link_to_collection(band, coll)

    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=48, ring_count=32,
        location=(0, 0, C.HAT_TOP_LOC_Z), radius=1.0)
    top = bpy.context.active_object
    top.name = "Alesya_Hat"
    top.scale = C.HAT_TOP_SCALE
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    for v in top.data.vertices:
        if v.co.z < C.HAT_TOP_BOTTOM_CLIP:
            v.co.z = C.HAT_TOP_BOTTOM_CLIP
    shade_smooth(top)
    assign_material(top, mat)
    link_to_collection(top, coll)
