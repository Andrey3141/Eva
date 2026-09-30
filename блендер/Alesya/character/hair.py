# -*- coding: utf-8 -*-
"""Волосы: основная масса, чёлка, боковые пряди."""

import bpy

import config as C
from materials import make_material, assign_material
from utils import link_to_collection, shade_smooth


def build_hair(coll):
    mat_hair   = make_material("Alesya_Hair_Main_Mat", C.HAIR_COLOR_BASE, roughness=0.45)
    mat_shadow = make_material("Alesya_Hair_Shadow_Mat", C.HAIR_SHADOW, roughness=0.5)

    # --- Основная масса волос ---
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=48, ring_count=32,
        location=C.HAIR_MAIN_LOC, radius=1.0)
    hair_main = bpy.context.active_object
    hair_main.name = "Alesya_Hair_Main"
    hair_main.scale = C.HAIR_MAIN_SCALE
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    for v in hair_main.data.vertices:
        if v.co.z < C.HAIR_MAIN_BOTTOM:
            v.co.z = C.HAIR_MAIN_BOTTOM
    shade_smooth(hair_main)
    assign_material(hair_main, mat_hair)
    link_to_collection(hair_main, coll)

    # --- Чёлка ---
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=48, ring_count=24,
        location=C.HAIR_BANGS_LOC, radius=1.0)
    bangs = bpy.context.active_object
    bangs.name = "Alesya_Hair_Bangs"
    bangs.scale = C.HAIR_BANGS_SCALE
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    for v in bangs.data.vertices:
        if v.co.z < C.HAIR_BANGS_BOTTOM:
            v.co.z = C.HAIR_BANGS_BOTTOM
        if v.co.y < 0:
            v.co.y *= 0.95
    shade_smooth(bangs)
    assign_material(bangs, mat_hair)
    link_to_collection(bangs, coll)

    # --- Боковые пряди ---
    for side, sx in (("L", -1), ("R", 1)):
        bpy.ops.mesh.primitive_uv_sphere_add(
            segments=32, ring_count=24,
            location=(sx * C.HEAD_WIDTH * 0.50, 0.02, C.HAIR_SIDE_LOC_Z),
            radius=1.0)
        strand = bpy.context.active_object
        strand.name = f"Alesya_Hair_{side}"
        strand.scale = C.HAIR_SIDE_SCALE
        for v in strand.data.vertices:
            if v.co.z < 0:
                k = 1.0 + v.co.z / 0.30
                k = max(0.35, k)
                v.co.x *= k
                v.co.y *= k
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        shade_smooth(strand)
        assign_material(strand, mat_hair)
        link_to_collection(strand, coll)

    # --- Тёмная подложка под чёлкой ---
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=32, ring_count=16,
        location=(0, -0.06, C.HEAD_CENTER_Z + C.HEAD_HEIGHT * 0.20),
        radius=1.0)
    under = bpy.context.active_object
    under.name = "Alesya_Hair_Underlay"
    under.scale = (C.HEAD_WIDTH * 0.46, 0.04, C.HEAD_HEIGHT * 0.20)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    shade_smooth(under)
    assign_material(under, mat_shadow)
    link_to_collection(under, coll)
