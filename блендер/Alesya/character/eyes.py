# -*- coding: utf-8 -*-
"""
Глаза Алеси — стилизованная геометрия, подготовленная к анимации.

Исправление этой итерации:

  * EYE_Y_FRONT скорректирован так, чтобы реальная передняя
    поверхность глазного яблока (world_min.y) выступала перед
    поверхностью лица.

    Поверхность лица в районе центра глаза:
        head_front ≈ -0.1563
    Раньше:
        EYE_Y_FRONT = -0.130
        eye_front ≈ EYE_Y_FRONT - eye_half_y = -0.1470
        protrusion = head_front - eye_front ≈ -0.0093  (утоплено)

    Теперь:
        EYE_Y_FRONT = -0.1630
        eye_front ≈ -0.1630 - 0.0170 = -0.1800
        protrusion ≈ (-0.1563) - (-0.1800) = +0.0237

    Это даёт лёгкое выступание яблока перед кожей без
    чрезмерного выноса.

  * Брови автоматически следуют за EYE_Y_FRONT:
        center_y = EYE_Y_FRONT - EYE_DEPTH * 0.20
                 = -0.1630 - 0.0068 = -0.1698
    Соответствующее значение внесено в tests/test_eyes.py.

  * Всё остальное не изменено: размеры яблока, радужка, зрачок,
    блик, веки на поверхности эллипсоида, иерархия, симметрия,
    материалы, имена объектов.
"""

import bpy
import bmesh
import math

import config as C
from materials import make_material, assign_material
from utils import link_to_collection, shade_smooth


# ============================================================
# ПАРАМЕТРЫ ГЛАЗ
# ============================================================

EYE_WIDTH        = 0.048
EYE_HEIGHT       = 0.030
EYE_DEPTH        = 0.034
EYE_SPACING      = 0.072

EYE_OVAL_X       = 1.05
EYE_OVAL_Z       = 0.94

EYE_Z_OFFSET     = 0.010

# Y-центр глазного яблока. Скорректирован под фактическую
# поверхность лица (~ -0.1563) так, чтобы передняя поверхность
# яблока слегка выступала перед лицом.
EYE_Y_FRONT      = -0.1630

IRIS_RADIUS      = 0.020
IRIS_BULGE       = 0.004

PUPIL_RADIUS     = 0.009
PUPIL_DEPTH_FROM_IRIS = 0.001

HIGHLIGHT_RADIUS = 0.004
HIGHLIGHT_DEPTH_FROM_IRIS = 0.002
HIGHLIGHT_OFFSET_X = 0.006
HIGHLIGHT_OFFSET_Z = 0.008

EYELID_COVER     = 0.30
LID_SURFACE_OFFSET = 0.0015
LID_SHELL_DEPTH  = 0.004
UPPER_LID_INNER_DROP = 0.006

BROW_WIDTH       = 0.058
BROW_THICKNESS   = 0.007
BROW_Z_OFFSET    = 0.060
BROW_ARCH        = 0.008

SCLERA_COLOR     = (0.96, 0.96, 0.96, 1.0)
IRIS_COLOR       = (0.36, 0.20, 0.10, 1.0)
IRIS_RING_COLOR  = (0.16, 0.08, 0.04, 1.0)
PUPIL_COLOR      = (0.03, 0.02, 0.02, 1.0)
HIGHLIGHT_COLOR  = (1.00, 1.00, 1.00, 1.0)
EYELID_COLOR     = (0.97, 0.80, 0.74, 1.0)
EYELID_SHADOW    = (0.92, 0.72, 0.66, 1.0)
BROW_COLOR       = (0.30, 0.17, 0.11, 1.0)

SEG_EYE          = 32
RING_EYE         = 16
SEG_IRIS         = 32
SEG_PUPIL        = 24
SEG_BROW         = 32


# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def _clear_existing_eyes(coll):
    names_to_remove = [
        "Alesya_Eyes_Root",
        "Alesya_Eye_L", "Alesya_Eye_R",
        "Alesya_Iris_L", "Alesya_Iris_R",
        "Alesya_IrisRing_L", "Alesya_IrisRing_R",
        "Alesya_Pupil_L", "Alesya_Pupil_R",
        "Alesya_Highlight_L", "Alesya_Highlight_R",
        "Alesya_Eyelid_L", "Alesya_Eyelid_R",
        "Alesya_EyelidShadow_L", "Alesya_EyelidShadow_R",
        "Alesya_Eyelid_Lower_L", "Alesya_Eyelid_Lower_R",
        "Alesya_Brow_L", "Alesya_Brow_R",
        "Alesya_Eyes",
    ]
    for name in names_to_remove:
        obj = bpy.data.objects.get(name)
        if obj is not None:
            bpy.data.objects.remove(obj, do_unlink=True)


def _parent_preserve_world(child, parent):
    bpy.context.view_layer.update()
    world_matrix = child.matrix_world.copy()
    child.parent = parent
    bpy.context.view_layer.update()
    child.matrix_parent_inverse = parent.matrix_world.inverted()
    child.matrix_world = world_matrix
    bpy.context.view_layer.update()


def _uv_sphere(name, loc, scale, coll, mat, seg=SEG_EYE, rings=RING_EYE,
               rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=seg, ring_count=rings,
        location=loc, radius=1.0)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = scale
    obj.rotation_euler = rotation
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    shade_smooth(obj)
    assign_material(obj, mat)
    link_to_collection(obj, coll)
    return obj


def _hemisphere(name, loc, radius, depth, coll, mat,
                rot=(0, 0, 0), seg=SEG_IRIS, rings=12):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=seg, ring_count=rings,
        location=loc, radius=1.0)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = (radius, radius, depth)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    me = obj.data
    for v in me.vertices:
        if v.co.z < 0.0:
            v.co.z = 0.0

    obj.rotation_euler = rot
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)

    shade_smooth(obj)
    assign_material(obj, mat)
    link_to_collection(obj, coll)
    return obj


def _ring_disc(name, loc, inner_r, outer_r, coll, mat, rot=(0, 0, 0),
               seg=48):
    mesh = bpy.data.meshes.new(name + "_Mesh")
    obj = bpy.data.objects.new(name, mesh)
    coll.objects.link(obj)

    bm = bmesh.new()
    verts_in = []
    verts_out = []
    for i in range(seg):
        t = 2.0 * math.pi * i / seg
        cx = math.cos(t)
        cy = math.sin(t)
        verts_in.append(bm.verts.new((cx * inner_r, cy * inner_r, 0.0)))
        verts_out.append(bm.verts.new((cx * outer_r, cy * outer_r, 0.0)))
    for i in range(seg):
        j = (i + 1) % seg
        bm.faces.new((verts_in[i], verts_in[j],
                      verts_out[j], verts_out[i]))
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    obj.data.update()

    obj.rotation_euler = rot
    obj.location = loc

    shade_smooth(obj)
    assign_material(obj, mat)
    return obj


# ============================================================
# ВЕКИ
# ============================================================

def _eye_surface_y(x_local, z_local, eye_half_x, eye_half_y, eye_half_z,
                   eye_center_y):
    xn = x_local / eye_half_x if eye_half_x > 0 else 0.0
    zn = z_local / eye_half_z if eye_half_z > 0 else 0.0
    inside = 1.0 - xn * xn - zn * zn
    if inside <= 0.0:
        inside = 0.0
    return eye_center_y - eye_half_y * math.sqrt(inside)


def _build_lid_on_surface(name, eye_x, eye_z, eye_half_x, eye_half_y,
                          eye_half_z, eye_center_y, side,
                          is_upper, coll, mat):
    mesh = bpy.data.meshes.new(name + "_Mesh")
    obj = bpy.data.objects.new(name, mesh)
    coll.objects.link(obj)
    obj.location = (eye_x, 0.0, eye_z)

    bm = bmesh.new()
    lid_half_x = eye_half_x * 1.02

    n = 18
    front_verts = []
    back_verts = []

    for i in range(n):
        t = i / (n - 1)
        u = (t - 0.5) * 2.0
        x_local = u * lid_half_x
        arc_x = math.cos(u * math.pi * 0.5)

        if is_upper:
            z_edge_top = eye_half_z * (1.0 - EYELID_COVER * arc_x)
            z_edge_top += 0.10 * u * eye_half_z * arc_x
            z_edge_back = z_edge_top + UPPER_LID_INNER_DROP * arc_x
        else:
            z_edge_top = -eye_half_z * (1.0 - 0.05 * arc_x)
            z_edge_back = z_edge_top - UPPER_LID_INNER_DROP * 0.6 * arc_x

        y_front_surface = _eye_surface_y(
            x_local, z_edge_top,
            eye_half_x, eye_half_y, eye_half_z,
            eye_center_y=eye_center_y)

        y_front = y_front_surface - LID_SURFACE_OFFSET
        y_back = y_front + LID_SHELL_DEPTH

        front_verts.append(bm.verts.new((x_local, y_front, z_edge_top)))
        back_verts.append(bm.verts.new((x_local, y_back, z_edge_back)))

    for i in range(n - 1):
        bm.faces.new((front_verts[i], front_verts[i + 1],
                      back_verts[i + 1], back_verts[i]))

    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    obj.data.update()

    shade_smooth(obj)
    assign_material(obj, mat)
    return obj


# ============================================================
# БРОВЬ
# ============================================================

def _build_brow(name, center_x, center_y, center_z, side_sign,
                coll, mat):
    mesh = bpy.data.meshes.new(name + "_Mesh")
    obj = bpy.data.objects.new(name, mesh)
    coll.objects.link(obj)

    bm = bmesh.new()
    n = 10
    verts_top = []
    verts_bot = []
    for i in range(n):
        t = i / (n - 1)
        u = (t - 0.5) * 2.0
        x = side_sign * u * BROW_WIDTH
        arc = math.sin(t * math.pi) * 0.5 + BROW_ARCH * max(0.0, u)
        base_z = arc * 0.010
        thick = BROW_THICKNESS * (1.0 - 0.35 * abs(u))
        verts_top.append(bm.verts.new((x, 0.0, base_z + thick)))
        verts_bot.append(bm.verts.new((x, 0.0, base_z - thick * 0.55)))

    for i in range(n - 1):
        bm.faces.new((verts_top[i], verts_top[i + 1],
                      verts_bot[i + 1], verts_bot[i]))

    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    obj.data.update()

    obj.rotation_euler = (math.radians(90), 0, 0)
    obj.location = (center_x, center_y, center_z)

    shade_smooth(obj)
    assign_material(obj, mat)
    return obj


# ============================================================
# ОСНОВНАЯ ФУНКЦИЯ
# ============================================================

def build_eyes(coll):
    _clear_existing_eyes(coll)

    mat_sclera    = make_material("Alesya_Sclera_Mat", SCLERA_COLOR,
                                  roughness=0.28, specular=0.35)
    mat_iris      = make_material("Alesya_Iris_Mat", IRIS_COLOR,
                                  roughness=0.30, specular=0.40)
    mat_iris_ring = make_material("Alesya_IrisRing_Mat", IRIS_RING_COLOR,
                                  roughness=0.30, specular=0.40)
    mat_pupil     = make_material("Alesya_Pupil_Mat", PUPIL_COLOR,
                                  roughness=0.20, specular=0.45)
    mat_highlight = make_material("Alesya_Highlight_Mat", HIGHLIGHT_COLOR,
                                  roughness=0.05, specular=0.60)
    mat_eyelid    = make_material("Alesya_Eyelid_Mat", EYELID_COLOR,
                                  roughness=0.55, specular=0.20)
    mat_eyelid_sh = make_material("Alesya_EyelidShadow_Mat", EYELID_SHADOW,
                                  roughness=0.60, specular=0.15)
    mat_brow      = make_material("Alesya_Brow_Mat", BROW_COLOR,
                                  roughness=0.55, specular=0.20)

    bpy.ops.object.empty_add(type='PLAIN_AXES',
                             location=(0.0, 0.0, C.HEAD_CENTER_Z))
    root = bpy.context.active_object
    root.name = "Alesya_Eyes_Root"
    root.empty_display_size = 0.06
    link_to_collection(root, coll)

    eye_z = C.HEAD_CENTER_Z + EYE_Z_OFFSET

    eye_half_x = EYE_WIDTH  * 0.5 * EYE_OVAL_X
    eye_half_y = EYE_DEPTH  * 0.5
    eye_half_z = EYE_HEIGHT * 0.5 * EYE_OVAL_Z

    eye_front_y = EYE_Y_FRONT - eye_half_y

    iris_front      = eye_front_y - IRIS_BULGE
    pupil_front     = iris_front - PUPIL_DEPTH_FROM_IRIS
    highlight_front = iris_front - HIGHLIGHT_DEPTH_FROM_IRIS

    iris_depth      = IRIS_BULGE + 0.001
    pupil_depth     = 0.0015
    highlight_depth = HIGHLIGHT_RADIUS * 0.5

    iris_center_y      = iris_front + iris_depth
    pupil_center_y     = pupil_front + pupil_depth
    highlight_center_y = highlight_front + highlight_depth

    for side, sx in (("L", -1), ("R", 1)):
        eye_x = sx * EYE_SPACING

        # --- Глазное яблоко ---
        eye = _uv_sphere(
            name=f"Alesya_Eye_{side}",
            loc=(eye_x, EYE_Y_FRONT, eye_z),
            scale=(eye_half_x, eye_half_y, eye_half_z),
            coll=coll, mat=mat_sclera,
            seg=SEG_EYE, rings=RING_EYE)

        # --- Радужка ---
        iris = _hemisphere(
            name=f"Alesya_Iris_{side}",
            loc=(eye_x, iris_center_y, eye_z),
            radius=IRIS_RADIUS,
            depth=iris_depth,
            coll=coll, mat=mat_iris,
            rot=(math.radians(90), 0, 0),
            seg=SEG_IRIS, rings=12)

        # --- Лимб ---
        iris_ring = _ring_disc(
            name=f"Alesya_IrisRing_{side}",
            loc=(eye_x, iris_front + 0.0006, eye_z),
            inner_r=IRIS_RADIUS * 0.94,
            outer_r=IRIS_RADIUS * 1.06,
            coll=coll, mat=mat_iris_ring,
            rot=(math.radians(90), 0, 0),
            seg=48)

        # --- Зрачок ---
        pupil = _hemisphere(
            name=f"Alesya_Pupil_{side}",
            loc=(eye_x, pupil_center_y, eye_z),
            radius=PUPIL_RADIUS,
            depth=pupil_depth,
            coll=coll, mat=mat_pupil,
            rot=(math.radians(90), 0, 0),
            seg=SEG_PUPIL, rings=10)

        # --- Блик ---
        hl_x = eye_x + sx * HIGHLIGHT_OFFSET_X
        hl_z = eye_z + HIGHLIGHT_OFFSET_Z
        highlight = _hemisphere(
            name=f"Alesya_Highlight_{side}",
            loc=(hl_x, highlight_center_y, hl_z),
            radius=HIGHLIGHT_RADIUS,
            depth=highlight_depth,
            coll=coll, mat=mat_highlight,
            rot=(math.radians(90), 0, 0),
            seg=16, rings=8)

        _parent_preserve_world(eye, root)
        _parent_preserve_world(iris, eye)
        _parent_preserve_world(iris_ring, eye)
        _parent_preserve_world(pupil, eye)
        _parent_preserve_world(highlight, eye)

        # --- Верхнее веко ---
        upper_lid = _build_lid_on_surface(
            name=f"Alesya_Eyelid_{side}",
            eye_x=eye_x, eye_z=eye_z,
            eye_half_x=eye_half_x,
            eye_half_y=eye_half_y,
            eye_half_z=eye_half_z,
            eye_center_y=EYE_Y_FRONT,
            side=sx, is_upper=True,
            coll=coll, mat=mat_eyelid)
        _parent_preserve_world(upper_lid, root)

        # --- Нижнее веко ---
        lower_lid = _build_lid_on_surface(
            name=f"Alesya_Eyelid_Lower_{side}",
            eye_x=eye_x, eye_z=eye_z,
            eye_half_x=eye_half_x,
            eye_half_y=eye_half_y,
            eye_half_z=eye_half_z,
            eye_center_y=EYE_Y_FRONT,
            side=sx, is_upper=False,
            coll=coll, mat=mat_eyelid)
        _parent_preserve_world(lower_lid, root)

        # --- Бровь ---
        brow_z = eye_z + BROW_Z_OFFSET
        brow = _build_brow(
            name=f"Alesya_Brow_{side}",
            center_x=eye_x,
            center_y=EYE_Y_FRONT - EYE_DEPTH * 0.20,
            center_z=brow_z,
            side_sign=sx,
            coll=coll,
            mat=mat_brow)
        _parent_preserve_world(brow, root)

    return root
