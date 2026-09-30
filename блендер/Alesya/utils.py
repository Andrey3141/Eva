# -*- coding: utf-8 -*-
"""Общие вспомогательные функции."""

import bpy


def clear_scene():
    """Полностью очищает сцену от объектов и данных."""
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.cameras,
                  bpy.data.lights, bpy.data.curves, bpy.data.images):
        for item in list(block):
            try:
                block.remove(item)
            except Exception:
                pass


def get_or_create_collection(name, parent=None):
    """Возвращает существующую коллекцию или создаёт новую."""
    if name in bpy.data.collections:
        return bpy.data.collections[name]
    coll = bpy.data.collections.new(name)
    if parent:
        parent.children.link(coll)
    else:
        bpy.context.scene.collection.children.link(coll)
    return coll


def link_to_collection(obj, collection):
    """Переносит объект в указанную коллекцию."""
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    collection.objects.link(obj)


def apply_transforms(obj):
    """Применяет масштаб/поворот/позицию к объекту."""
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.select_set(False)


def shade_smooth(obj):
    """Включает сглаживание полигонов."""
    bpy.context.view_layer.objects.active = obj
    for p in obj.data.polygons:
        p.use_smooth = True


def parent_to(child, parent):
    """Привязывает child к parent с сохранением мировой позиции."""
    child.parent = parent
    child.matrix_parent_inverse = parent.matrix_world.inverted()
