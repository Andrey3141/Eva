# -*- coding: utf-8 -*-
"""
Alesya — read-only диагностика объектов сцены.

Публичный API: run_test() -> None.

Задача: показать РЕАЛЬНУЮ структуру объектов в текущем .blend,
включая Empty-иерархии вроде «Head (Animation) - Realistic» и
вложенные в них mesh-объекты.

Тест строго read-only:
  * не удаляет объекты;
  * не меняет объекты;
  * не применяет модификаторы;
  * не меняет сцену;
  * не трогает bpy.data.

Корректно работает с любым типом bpy.data.objects:
Mesh, Camera, Light, Armature, Empty, Curve, Surface, Meta,
Font, GreasePencil, Lattice, Volume, PointCloud и т.п.
Тип data определяется через isinstance, а не через data.type,
потому что у bpy.types.Mesh нет свойства .type.
"""

import bpy


# ============================================================
# КОНФИГУРАЦИЯ
# ============================================================

# Для отдельного блока «интересных» объектов.
KEYWORDS = ("Head", "head", "Animation", "Realistic", "Alesya")


# ============================================================
# ОПРЕДЕЛЕНИЕ ТИПА DATA (безопасное для Blender 4.3.2)
# ============================================================

def _data_type_label(data):
    """
    Возвращает строковую метку типа data через isinstance.
    Никогда не падает, даже если у data нет .type.
    """
    if data is None:
        return "-"
    if isinstance(data, bpy.types.Mesh):
        return "MESH"
    if isinstance(data, bpy.types.Camera):
        return "CAMERA"
    if isinstance(data, bpy.types.Light):
        return "LIGHT"
    if isinstance(data, bpy.types.Armature):
        return "ARMATURE"
    if isinstance(data, bpy.types.Curve):
        return "CURVE"
    if isinstance(data, bpy.types.SurfaceCurve):
        return "SURFACE"
    if isinstance(data, bpy.types.MetaBall):
        return "META"
    if isinstance(data, bpy.types.Font):
        return "FONT"
    if isinstance(data, bpy.types.Lattice):
        return "LATTICE"
    if isinstance(data, bpy.types.Volume):
        return "VOLUME"
    if isinstance(data, bpy.types.PointCloud):
        return "POINTCLOUD"
    if isinstance(data, bpy.types.GreasePencil):
        return "GREASEPENCIL"
    # fallback
    return f"UNKNOWN({type(data).__name__})"


# ============================================================
# СБОР ИНФОРМАЦИИ ОБ ОБЪЕКТЕ
# ============================================================

def _object_collections(obj):
    names = [c.name for c in obj.users_collection]
    if not names:
        return "(none)"
    return ", ".join(names)


def _object_parent_name(obj):
    if obj.parent is None:
        return "-"
    return obj.parent.name


def _object_children_names(obj):
    return [c.name for c in obj.children]


def _mesh_counts(data):
    """
    Возвращает (vertices, edges, polygons) для Mesh data.
    Для не-Mesh возвращает (None, None, None).
    """
    if isinstance(data, bpy.types.Mesh):
        try:
            return len(data.vertices), len(data.edges), len(data.polygons)
        except Exception:
            return None, None, None
    return None, None, None


# ============================================================
# ПЕЧАТЬ ОБЪЕКТА
# ============================================================

def _print_object_block(obj, header=None):
    if header is not None:
        print(header)

    data = obj.data
    data_name = data.name if data is not None else "-"
    data_type = _data_type_label(data)
    verts, edges, polys = _mesh_counts(data)

    print(f"  name:          {obj.name}")
    print(f"  type:          {obj.type}")
    print(f"  parent:        {_object_parent_name(obj)}")
    print(f"  collection(s): {_object_collections(obj)}")
    print(f"  data.name:     {data_name}")
    print(f"  data.type:     {data_type}")
    if verts is None:
        print(f"  vertices:      -")
        print(f"  edges:         -")
        print(f"  polygons:      -")
    else:
        print(f"  vertices:      {verts}")
        print(f"  edges:         {edges}")
        print(f"  polygons:      {polys}")
    print()


def _matches_keyword(name):
    for k in KEYWORDS:
        if k in name:
            return True
    return False


# ============================================================
# ПУБЛИЧНЫЙ API
# ============================================================

def run_test() -> None:
    print()
    print("=== EXTERNAL OBJECTS DIAGNOSTIC ===")
    print()

    all_objects = list(bpy.data.objects)
    scene_objects = list(bpy.context.scene.objects)

    # --------------------------------------------------------
    # 1. Все объекты в текущей сцене — полный список
    # --------------------------------------------------------
    print(f"--- OBJECTS IN CURRENT SCENE "
          f"({len(scene_objects)} total, full list) ---")
    print()
    for obj in scene_objects:
        _print_object_block(obj)

    # --------------------------------------------------------
    # 2. Все объекты в bpy.data.objects — полный список
    # --------------------------------------------------------
    print(f"--- ALL bpy.data.objects "
          f"({len(all_objects)} total, full list) ---")
    print()
    for obj in all_objects:
        _print_object_block(obj)

    # --------------------------------------------------------
    # 3. Отдельный блок — «интересные» объекты по ключевым словам
    # --------------------------------------------------------
    matched = [o for o in all_objects if _matches_keyword(o.name)]
    print(f"--- MATCHED BY KEYWORDS {KEYWORDS} "
          f"({len(matched)} found) ---")
    print()
    for obj in matched:
        _print_object_block(obj, header="[MATCH]")

    # --------------------------------------------------------
    # 4. Иерархия «Head (Animation) - Realistic»
    # --------------------------------------------------------
    print("--- HIERARCHY OF HEAD-LIKE OBJECTS ---")
    print()

    def _walk(obj, depth=0):
        indent = "  " * depth
        data = obj.data
        data_type = _data_type_label(data)
        extra = ""
        if isinstance(data, bpy.types.Mesh):
            extra = f" verts={len(data.vertices)} polys={len(data.polygons)}"
        print(f"{indent}{obj.name} "
              f"[type={obj.type}, data={data_type}]{extra}")
        for child in obj.children:
            _walk(child, depth + 1)

    roots_with_children = [
        o for o in all_objects
        if ("Head" in o.name or "Realistic" in o.name) and o.parent is None
    ]
    if not roots_with_children:
        print("  (no root-level objects with 'Head' or 'Realistic' in name)")
    for r in roots_with_children:
        _walk(r, 0)
    print()

    # --------------------------------------------------------
    # 5. Дети конкретно объекта "Head (Animation) - Realistic"
    # --------------------------------------------------------
    print("--- CHILDREN OF 'Head (Animation) - Realistic' ---")
    print()
    parent_obj = bpy.data.objects.get("Head (Animation) - Realistic")
    if parent_obj is None:
        print("  Object 'Head (Animation) - Realistic' not found")
        print("  (possible variants in scene:)")
        for o in all_objects:
            if "Head" in o.name or "Realistic" in o.name:
                print(f"    - {o.name!r}")
    else:
        print(f"  parent object type: {parent_obj.type}")
        data = parent_obj.data
        print(f"  parent data.type:   {_data_type_label(data)}")
        print(f"  parent collection(s): {_object_collections(parent_obj)}")
        print(f"  children ({len(parent_obj.children)}):")
        for child in parent_obj.children:
            _print_object_block(child, header=f"  [CHILD]")

    # --------------------------------------------------------
    # 6. Проверка целевого имени
    # --------------------------------------------------------
    print("--- TARGET OBJECT LOOKUP ---")
    print()
    target = bpy.data.objects.get("Alesya_Head_Base_Experiment")
    if target is None:
        print("Alesya_Head_Base_Experiment: NOT FOUND in bpy.data.objects")
        print("Suggested: rename the actual mesh object to "
              "Alesya_Head_Base_Experiment,")
        print("or update test_head_base_external.py to look up the real "
              "name.")
    else:
        print("Alesya_Head_Base_Experiment: FOUND")
        _print_object_block(target)

    print("=== END EXTERNAL OBJECTS DIAGNOSTIC ===")
    print()
