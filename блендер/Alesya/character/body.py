# -*- coding: utf-8 -*-
"""Шея и тело."""

import bpy

import config as C
from materials import make_material, assign_material
from utils import link_to_collection, shade_smooth


def build_body(coll):
    mat_skin = make_material("Alesya_Skin_Neck", C.SKIN_SHADOW, roughness=0.55)

    bpy.ops.mesh.primitive_cylinder_add(
        vertices=32, radius=C.NECK_RADIUS, depth=C.NECK_DEPTH,
        location=(0, 0, C.NECK_TOP_Z))
    neck = bpy.context.active_object
    neck.name = "Alesya_Neck"
    shade_smooth(neck)
    assign_material(neck, mat_skin)
    link_to_collection(neck, coll)

    # Тело будет переопределено в clothes.py (там же и материал)
    return neck
