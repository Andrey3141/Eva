# -*- coding: utf-8 -*-
"""Камера Alesya_Camera."""

import bpy
import math

import config as C
from utils import get_or_create_collection


def build_camera():
    coll = get_or_create_collection("Alesya_Camera")

    cam_data = bpy.data.cameras.new("Alesya_Camera_Data")
    cam_data.lens = C.CAMERA_LENS
    cam_data.type = 'PERSP'

    cam = bpy.data.objects.new("Alesya_Camera", cam_data)
    coll.objects.link(cam)

    cam.location = (0, -C.CAMERA_DISTANCE, C.CAMERA_HEIGHT)
    cam.rotation_euler = (math.radians(90), 0, 0)

    bpy.context.scene.camera = cam
    return cam
