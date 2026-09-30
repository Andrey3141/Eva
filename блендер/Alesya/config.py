# -*- coding: utf-8 -*-
"""
Все настраиваемые параметры проекта: размеры, цвета, камера, свет.
Меняются вручную без правки остальных модулей.
"""

import math

# ============================================================
# ОБЩИЕ ПРОПОРЦИИ
# ============================================================

HEAD_CENTER_Z       = 1.62
HEAD_WIDTH          = 0.42
HEAD_HEIGHT         = 0.56
HEAD_DEPTH          = 0.24

# Локальные координаты лица (в системе головы)
FACE_FRONT_Y        = -HEAD_DEPTH * 0.42
FACE_Z_TOP          = HEAD_HEIGHT * 0.30
FACE_Z_BROW         = HEAD_HEIGHT * 0.08
FACE_Z_EYE          = HEAD_HEIGHT * 0.00
FACE_Z_NOSE         = -HEAD_HEIGHT * 0.14
FACE_Z_MOUTH        = -HEAD_HEIGHT * 0.26
FACE_Z_CHIN         = -HEAD_HEIGHT * 0.46

# ============================================================
# ГЛАЗА
# ============================================================

EYE_OFFSET_X        = 0.115
EYE_Z               = HEAD_CENTER_Z + FACE_Z_EYE
EYE_SIZE_X          = 0.115
EYE_SIZE_Z          = 0.058
IRIS_SIZE           = 0.048
PUPIL_SIZE          = 0.022
HIGHLIGHT_SIZE      = 0.012

# ============================================================
# БРОВИ
# ============================================================

BROW_Z              = HEAD_CENTER_Z + FACE_Z_BROW + 0.055
BROW_LEN            = 0.135
BROW_THICK          = 0.018

# ============================================================
# НОС
# ============================================================

NOSE_Z              = HEAD_CENTER_Z + FACE_Z_NOSE

# ============================================================
# РОТ
# ============================================================

MOUTH_Z             = HEAD_CENTER_Z + FACE_Z_MOUTH
MOUTH_WIDTH         = 0.105
MOUTH_HEIGHT        = 0.040

# ============================================================
# УШИ
# ============================================================

EAR_Z               = HEAD_CENTER_Z + FACE_Z_EYE - 0.01
EAR_X               = HEAD_WIDTH * 0.46

# ============================================================
# ШЕЯ / ТЕЛО
# ============================================================

NECK_RADIUS         = 0.085
NECK_DEPTH          = 0.18
NECK_TOP_Z          = HEAD_CENTER_Z - HEAD_HEIGHT * 0.5 - 0.04

BODY_SCALE          = (0.46, 0.16, 0.24)
BODY_TOP_CLIP       = 0.09
BODY_OFFSET_Z       = -0.31

# ============================================================
# ВОЛОСЫ
# ============================================================

HAIR_COLOR_BASE     = (0.70, 0.58, 0.48, 1.0)
HAIR_SHADOW         = (0.55, 0.44, 0.35, 1.0)

HAIR_COLOR_WHITE    = (0.96, 0.96, 0.94, 1.0)
HAIR_COLOR_GREEN    = (0.20, 0.55, 0.28, 1.0)
HAIR_COLOR_RED      = (0.78, 0.15, 0.18, 1.0)

HAIR_MAIN_SCALE     = (HEAD_WIDTH * 0.56, HEAD_DEPTH * 0.68, HEAD_HEIGHT * 0.60)
HAIR_MAIN_LOC       = (0.0, 0.035, HEAD_CENTER_Z + 0.02)
HAIR_MAIN_BOTTOM    = -HEAD_HEIGHT * 0.30

HAIR_BANGS_SCALE    = (HEAD_WIDTH * 0.54, HEAD_DEPTH * 0.60, HEAD_HEIGHT * 0.30)
HAIR_BANGS_LOC      = (0.0, -0.005, HEAD_CENTER_Z + HEAD_HEIGHT * 0.24)
HAIR_BANGS_BOTTOM   = -HEAD_HEIGHT * 0.04

HAIR_SIDE_SCALE     = (0.075, 0.10, 0.44)
HAIR_SIDE_LOC_Z     = HEAD_CENTER_Z - HEAD_HEIGHT * 0.15

# ============================================================
# КОЛПАК
# ============================================================

HAT_BAND_RADIUS     = HEAD_WIDTH * 0.55
HAT_BAND_DEPTH      = 0.06
HAT_BAND_Z          = HEAD_CENTER_Z + HEAD_HEIGHT * 0.52

HAT_TOP_SCALE       = (HEAD_WIDTH * 0.62, HEAD_WIDTH * 0.55, 0.20)
HAT_TOP_LOC_Z       = HAT_BAND_Z + 0.14
HAT_TOP_BOTTOM_CLIP = -0.08

# ============================================================
# ЛЕНТА И ЦВЕТЫ (для будущего этапа)
# ============================================================

RIBBON_COLOR        = (0.82, 0.14, 0.18, 1.0)
FLOWER_BLUE         = (0.35, 0.62, 0.92, 1.0)
FLOWER_CORE         = (1.00, 0.92, 0.55, 1.0)

# ============================================================
# ЦВЕТА
# ============================================================

SKIN_COLOR          = (1.00, 0.86, 0.78, 1.0)
SKIN_SHADOW         = (0.97, 0.80, 0.74, 1.0)
SKIN_BLUSH          = (1.00, 0.72, 0.72, 1.0)
CLOTHES_WHITE       = (0.97, 0.97, 0.96, 1.0)
EYE_WHITE_COLOR     = (1.00, 1.00, 1.00, 1.0)
IRIS_COLOR          = (0.36, 0.20, 0.10, 1.0)
IRIS_DARK           = (0.18, 0.09, 0.04, 1.0)
PUPIL_COLOR         = (0.03, 0.02, 0.02, 1.0)
HIGHLIGHT_COLOR     = (1.00, 1.00, 1.00, 1.0)
EYELID_COLOR        = (0.95, 0.72, 0.68, 1.0)
BROW_COLOR          = (0.30, 0.17, 0.11, 1.0)
NOSE_COLOR          = (0.96, 0.78, 0.70, 1.0)
NOSE_SHADOW_COLOR   = (0.90, 0.68, 0.62, 1.0)
MOUTH_COLOR         = (0.78, 0.28, 0.32, 1.0)
MOUTH_LINE_COLOR    = (0.55, 0.15, 0.20, 1.0)
HAIR_COLOR_BASE     = (0.70, 0.58, 0.48, 1.0)
HAIR_SHADOW         = (0.55, 0.44, 0.35, 1.0)
HAT_COLOR           = (0.98, 0.98, 0.97, 1.0)

# ============================================================
# КАМЕРА
# ============================================================

CAMERA_HEIGHT       = HEAD_CENTER_Z + 0.02
CAMERA_DISTANCE     = 1.30
CAMERA_LENS         = 60.0

# ============================================================
# СВЕТ
# ============================================================

KEY_ENERGY          = 340
KEY_SIZE            = 1.6
KEY_COLOR           = (1.0, 0.96, 0.92)
KEY_LOC             = (-1.3, -2.0, HEAD_CENTER_Z + 0.9)
KEY_ROT             = (math.radians(55), 0, math.radians(-30))

FILL_ENERGY         = 150
FILL_SIZE           = 2.2
FILL_COLOR          = (0.92, 0.96, 1.0)
FILL_LOC            = (1.6, -1.8, HEAD_CENTER_Z + 0.2)
FILL_ROT            = (math.radians(75), 0, math.radians(35))

RIM_ENERGY          = 200
RIM_SIZE            = 1.3
RIM_COLOR           = (1.0, 0.94, 0.85)
RIM_LOC             = (0.6, 2.2, HEAD_CENTER_Z + 0.9)
RIM_ROT             = (math.radians(-55), 0, math.radians(160))

WORLD_COLOR         = (0.94, 0.95, 0.98, 1.0)
WORLD_STRENGTH      = 0.5

# ============================================================
# РЕНДЕР
# ============================================================

RESOLUTION_X        = 1080
RESOLUTION_Y        = 1350
VIEW_TRANSFORM      = 'Standard'
