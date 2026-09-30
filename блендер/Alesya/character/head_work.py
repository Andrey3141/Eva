# -*- coding: utf-8 -*-
"""
Alesya — создание рабочей копии головы.

Публичный API:

    create_work_head() -> bpy.types.Object | None

Создаёт независимый объект Alesya_Head_Work в коллекции
Alesya_Character на основе GEO-head_animation_realistic.

Исходный объект НЕ изменяется. Сцена НЕ очищается. Существующие
объекты НЕ удаляются.

Функция идемпотентна: если Alesya_Head_Work уже существует —
возвращает его без пересоздания.

Что копируется:
  * mesh data (полная независимая копия);
  * location, rotation, scale;
  * материалы (ссылки на те же материалы);
  * vertex positions, topology.

Рабочая копия полностью независима: изменения Alesya_Head_Work
не влияют на GEO-head_animation_realistic, и наоборот.
"""

import bpy


# ============================================================
# КОНФИГУРАЦИЯ
# ============================================================

SOURCE_OBJECT_NAME   = "GEO-head_animation_realistic"

WORK_OBJECT_NAME     = "Alesya_Head_Work"
WORK_MESH_NAME       = "Alesya_Head_Work_Mesh"
WORK_COLLECTION_NAME = "Alesya_Character"


# ============================================================
# КОЛЛЕКЦИИ
# ============================================================

def _get_or_create_collection(name):
    coll = bpy.data.collections.get(name)
    if coll is not None:
        return coll
    coll = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(coll)
    return coll


# ============================================================
# СОЗДАНИЕ РАБОЧЕЙ КОПИИ
# ============================================================

def create_work_head():
    """
    Создаёт независимую рабочую копию головы.

    Возвращает объект Alesya_Head_Work или None, если исходный
    объект не найден.
    """
    print()
    print("[head_work] create_work_head() called")
    print()

    src = bpy.data.objects.get(SOURCE_OBJECT_NAME)
    if src is None:
        print(f"[head_work] FAIL: source object not found: "
              f"{SOURCE_OBJECT_NAME}")
        print()
        return None

    if src.type != 'MESH':
        print(f"[head_work] FAIL: source object is not a MESH: "
              f"{src.name} (type={src.type})")
        print()
        return None

    # Идемпотентность: если рабочая копия уже существует — вернуть её.
    existing = bpy.data.objects.get(WORK_OBJECT_NAME)
    if existing is not None:
        print(f"[head_work] INFO: {WORK_OBJECT_NAME} already exists, "
              f"returning existing object")
        coll = _get_or_create_collection(WORK_COLLECTION_NAME)
        if existing.name not in coll.objects:
            for c in list(existing.users_collection):
                c.objects.unlink(existing)
            coll.objects.link(existing)
        print(f"[head_work] OK: work object present "
              f"(data={existing.data.name!r})")
        print()
        return existing

    # --- 1. Независимая копия mesh data ---
    new_mesh = src.data.copy()
    new_mesh.name = WORK_MESH_NAME

    # --- 2. Независимая копия объекта ---
    new_obj = src.copy()
    new_obj.data = new_mesh
    new_obj.name = WORK_OBJECT_NAME
    new_obj.data.name = WORK_MESH_NAME

    # --- 3. Сохраняем исходные transform ---
    new_obj.location = src.location.copy()
    new_obj.rotation_euler = src.rotation_euler.copy()
    new_obj.rotation_mode = src.rotation_mode
    new_obj.scale = src.scale.copy()

    # --- 4. Помещаем в коллекцию Alesya_Character ---
    coll = _get_or_create_collection(WORK_COLLECTION_NAME)

    # Убираем копию из всех коллекций, куда её автоматически
    # добавил src.copy().
    for c in list(new_obj.users_collection):
        c.objects.unlink(new_obj)

    coll.objects.link(new_obj)

    # --- 5. Обнуляем родителя, чтобы не зависеть от чужой иерархии ---
    if new_obj.parent is not None:
        new_obj.parent = None

    print(f"[head_work] OK: created {WORK_OBJECT_NAME}")
    print(f"[head_work]     mesh data: {new_obj.data.name!r}")
    print(f"[head_work]     collection: {[c.name for c in new_obj.users_collection]}")
    print(f"[head_work]     vertices: {len(new_obj.data.vertices)}")
    print()
    return new_obj
