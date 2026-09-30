# -*- coding: utf-8 -*-
"""
Орнамент волос (элементы белорусской стилистики).

Создаёт те же объекты, что были в монолитном скрипте-прототипе:
    Alesya_Hair_Ornament_White_1
    Alesya_Hair_Ornament_White_2
    Alesya_Hair_Ornament_Green_1
    Alesya_Hair_Ornament_Green_2
    Alesya_Hair_Ornament_Red_1
"""

import bpy

import config as C
from materials import make_material, assign_material
from utils import link_to_collection


def build_ornament(coll):
    """Геометрические полосы орнамента на чётке волос."""
    mat_white = make_material("Alesya_Hair_White_Mat",
                              C.HAIR_COLOR_WHITE, roughness=0.45)
    mat_green = make_material("Alesya_Hair_Green_Mat",
                              C.HAIR_COLOR_GREEN, roughness=0.45)
    mat_red   = make_material("Alesya_Hair_Red_Mat",
                              C.HAIR_COLOR_RED, roughness=0.45)

    # (имя, x, z, scale_x, scale_z, материал)
    ornament_specs = [
        ("Alesya_Hair_Ornament_White_1",
         -0.10, C.HEAD_CENTER_Z + 0.22, 0.012, 0.18, mat_white),
        ("Alesya_Hair_Ornament_White_2",
          0.10, C.HEAD_CENTER_Z + 0.22, 0.012, 0.18, mat_white),
        ("Alesya_Hair_Ornament_Green_1",
         -0.05, C.HEAD_CENTER_Z + 0.22, 0.012, 0.18, mat_green),
        ("Alesya_Hair_Ornament_Green_2",
          0.05, C.HEAD_CENTER_Z + 0.22, 0.012, 0.18, mat_green),
        ("Alesya_Hair_Ornament_Red_1",
          0.00, C.HEAD_CENTER_Z + 0.22, 0.012, 0.18, mat_red),
    ]

    for name, x, z, sx, sz, mat in ornament_specs:
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x, -0.08, z))
        obj = bpy.context.active_object
        obj.name = name
        obj.scale = (sx, 0.02, sz)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        assign_material(obj, mat)
        link_to_collection(obj, coll)
