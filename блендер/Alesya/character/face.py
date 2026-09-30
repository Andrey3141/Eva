# -*- coding: utf-8 -*-
"""Нос и рот (лицевые элементы)."""

import bpy

import config as C
from materials import make_material, assign_material
from utils import link_to_collection, shade_smooth


def build_face(coll):
    """Сборка лицевых элементов: нос + рот."""
    _build_nose(coll)
    _build_mouth(coll)


def _build_nose(coll):
    """Стилизованный нос: переносица, кончик, тень ноздрей."""
    mat_main  = make_material("Alesya_Nose_Mat", C.NOSE_COLOR, roughness=0.55)
    mat_shade = make_material("Alesya_Nose_Shadow_Mat", C.NOSE_SHADOW_COLOR,
                              roughness=0.6)

    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=24, ring_count=16,
        location=(0, C.FACE_FRONT_Y + 0.010, C.NOSE_Z + 0.06),
        radius=1.0)
    bridge = bpy.context.active_object
    bridge.name = "Alesya_Nose_Bridge"
    bridge.scale = (0.014, 0.014, 0.055)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    shade_smooth(bridge)
    assign_material(bridge, mat_main)
    link_to_collection(bridge, coll)

    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=24, ring_count=16,
        location=(0, C.FACE_FRONT_Y - 0.004, C.NOSE_Z),
        radius=1.0)
    tip = bpy.context.active_object
    tip.name = "Alesya_Nose"
    tip.scale = (0.024, 0.018, 0.020)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    shade_smooth(tip)
    assign_material(tip, mat_main)
    link_to_collection(tip, coll)

    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=20, ring_count=12,
        location=(0, C.FACE_FRONT_Y - 0.001, C.NOSE_Z - 0.020),
        radius=1.0)
    nostril = bpy.context.active_object
    nostril.name = "Alesya_Nose_Shadow"
    nostril.scale = (0.020, 0.008, 0.008)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    shade_smooth(nostril)
    assign_material(nostril, mat_shade)
    link_to_collection(nostril, coll)


def _build_mouth(coll):
    """Стилизованные губы с контроллером Alesya_Mouth."""
    mat_lip  = make_material("Alesya_Mouth_Mat", C.MOUTH_COLOR, roughness=0.45)
    mat_line = make_material("Alesya_Mouth_Line_Mat", C.MOUTH_LINE_COLOR,
                             roughness=0.5)

    bpy.ops.object.empty_add(
        type='PLAIN_AXES',
        location=(0, C.FACE_FRONT_Y - 0.005, C.MOUTH_Z))
    ctrl = bpy.context.active_object
    ctrl.name = "Alesya_Mouth"
    ctrl.empty_display_size = 0.05
    link_to_collection(ctrl, coll)

    def make_lip(name, loc, scale, mat):
        bpy.ops.mesh.primitive_uv_sphere_add(
            segments=32, ring_count=16, location=loc, radius=1.0)
        obj = bpy.context.active_object
        obj.name = name
        obj.scale = scale
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        shade_smooth(obj)
        assign_material(obj, mat)
        link_to_collection(obj, coll)
        obj.parent = ctrl
        obj.matrix_parent_inverse = ctrl.matrix_world.inverted()
        return obj

    make_lip("Alesya_Mouth_Upper_L",
             (-C.MOUTH_WIDTH * 0.22, C.FACE_FRONT_Y - 0.010,
              C.MOUTH_Z + 0.011),
             (C.MOUTH_WIDTH * 0.30, 0.010, C.MOUTH_HEIGHT * 0.35),
             mat_lip)
    make_lip("Alesya_Mouth_Upper_R",
             ( C.MOUTH_WIDTH * 0.22, C.FACE_FRONT_Y - 0.010,
              C.MOUTH_Z + 0.011),
             (C.MOUTH_WIDTH * 0.30, 0.010, C.MOUTH_HEIGHT * 0.35),
             mat_lip)
    make_lip("Alesya_Mouth_Lower",
             (0, C.FACE_FRONT_Y - 0.010, C.MOUTH_Z - 0.014),
             (C.MOUTH_WIDTH * 0.42, 0.011, C.MOUTH_HEIGHT * 0.32),
             mat_lip)

    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=24, ring_count=10,
        location=(0, C.FACE_FRONT_Y - 0.013, C.MOUTH_Z - 0.001),
        radius=1.0)
    line = bpy.context.active_object
    line.name = "Alesya_Mouth_Line"
    line.scale = (C.MOUTH_WIDTH * 0.44, 0.006, 0.004)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    shade_smooth(line)
    assign_material(line, mat_line)
    link_to_collection(line, coll)
    line.parent = ctrl
    line.matrix_parent_inverse = ctrl.matrix_world.inverted()

    for side, sx in (("L", -1), ("R", 1)):
        make_lip(f"Alesya_Mouth_Corner_{side}",
                 (sx * C.MOUTH_WIDTH * 0.48,
                  C.FACE_FRONT_Y - 0.011,
                  C.MOUTH_Z - 0.002),
                 (0.008, 0.007, 0.010),
                 mat_lip)
