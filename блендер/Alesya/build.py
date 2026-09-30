# -*- coding: utf-8 -*-
"""
Единая точка сборки Алеси.

Вызывается из main.py. Собирает сцену, персонажа, аксессуары,
камеру и свет. Настройки рендера тоже применяются здесь.
"""

import bpy

import config as C
from utils import clear_scene, get_or_create_collection
from scene.camera import build_camera
from scene.lighting import build_lighting
from character.head import build_head
from character.body import build_body
from character.hair import build_hair
from character.eyes import build_eyes
from character.face import build_face
from character.clothes import build_clothes
from accessories.hat import build_hat
from accessories.ribbon import build_ribbon
from accessories.flowers import build_flowers
from accessories.ornament import build_ornament


def setup_render():
    scene = bpy.context.scene
    try:
        scene.render.engine = 'BLENDER_EEVEE_NEXT'
    except Exception:
        scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x = C.RESOLUTION_X
    scene.render.resolution_y = C.RESOLUTION_Y
    scene.render.film_transparent = False
    scene.view_settings.view_transform = C.VIEW_TRANSFORM


def build_alesya():
    """Полная сборка сцены с Алесей."""
    clear_scene()
    setup_render()

    alesya_coll = get_or_create_collection("Alesya")
    get_or_create_collection("Alesya_Lights")
    get_or_create_collection("Alesya_Camera")

    build_head(alesya_coll)
    build_body(alesya_coll)
    build_hair(alesya_coll)
    build_eyes(alesya_coll)
    build_face(alesya_coll)
    build_clothes(alesya_coll)

    build_hat(alesya_coll)
    build_ribbon(alesya_coll)
    build_flowers(alesya_coll)
    build_ornament(alesya_coll)

    build_camera()
    build_lighting()

    cam = bpy.data.objects.get("Alesya_Camera")
    if cam:
        bpy.context.view_layer.objects.active = cam
        cam.select_set(True)

    print("Alesya project built successfully.")
