# -*- coding: utf-8 -*-
"""Освещение и World."""

import bpy

import config as C
from utils import get_or_create_collection


def build_lighting():
    coll = get_or_create_collection("Alesya_Lights")

    # --- Key ---
    key_data = bpy.data.lights.new("Alesya_Key", type='AREA')
    key_data.energy = C.KEY_ENERGY
    key_data.size = C.KEY_SIZE
    key_data.color = C.KEY_COLOR
    key = bpy.data.objects.new("Alesya_Key", key_data)
    key.location = C.KEY_LOC
    key.rotation_euler = C.KEY_ROT
    coll.objects.link(key)

    # --- Fill ---
    fill_data = bpy.data.lights.new("Alesya_Fill", type='AREA')
    fill_data.energy = C.FILL_ENERGY
    fill_data.size = C.FILL_SIZE
    fill_data.color = C.FILL_COLOR
    fill = bpy.data.objects.new("Alesya_Fill", fill_data)
    fill.location = C.FILL_LOC
    fill.rotation_euler = C.FILL_ROT
    coll.objects.link(fill)

    # --- Rim ---
    rim_data = bpy.data.lights.new("Alesya_Rim", type='AREA')
    rim_data.energy = C.RIM_ENERGY
    rim_data.size = C.RIM_SIZE
    rim_data.color = C.RIM_COLOR
    rim = bpy.data.objects.new("Alesya_Rim", rim_data)
    rim.location = C.RIM_LOC
    rim.rotation_euler = C.RIM_ROT
    coll.objects.link(rim)

    # --- World ---
    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = C.WORLD_COLOR
        bg.inputs[1].default_value = C.WORLD_STRENGTH
