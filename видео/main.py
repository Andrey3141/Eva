#!/usr/bin/env python3
"""
Видеоредактор:
  1) извлечь один кадр
  2) обрезать видео по кадрам
  3) соединить 2 видео
  4) извлечь все кадры в папку
  5) собрать видео из кадров
  6) сделать GIF из видео                                # NEW

Требуется: opencv-python, pillow
"""

import cv2
import os
import re
import sys
import argparse
import shutil

from PIL import Image   # NEW — для GIF


# ────────────────────────── инфо о видео ──────────────────────────

def get_video_info(cap):
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration = total / fps if fps > 0 else 0
    return total, fps, width, height, duration


def print_video_info(video_path):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"❌ Не удалось открыть видео: {video_path}")
        sys.exit(1)
    total, fps, w, h, dur = get_video_info(cap)
    cap.release()
    print("=" * 55)
    print(f"📹 Файл:         {video_path}")
    print(f"🎞  Кадров:       {total}")
    print(f"⚡ FPS:          {fps:.2f}")
    print(f"📐 Размер:       {w} x {h}")
    print(f"⏱  Длительность: {dur:.2f} сек")
    print("=" * 55)
    return total, fps, w, h


# ────────────────────────── парсинг кадра ──────────────────────────

def parse_frame_arg(arg, total, side="start"):
    if arg is None:
        return None
    arg = str(arg).strip().lower()

    if arg.startswith("-") and arg[1:].isdigit():
        n = int(arg[1:])
        if n < 1:
            print("❌ Отсчёт с конца начинается с 1")
            return None
        return max(0, total - n)

    if arg.startswith("end:") or arg.startswith("e:"):
        try:
            n = int(arg.split(":", 1)[1])
        except ValueError:
            print(f"❌ Некорректный номер кадра: {arg}")
            return None
        if n < 1:
            print("❌ Отсчёт с конца начинается с 1")
            return None
        return max(0, total - n)

    if arg.isdigit():
        n = int(arg)
        if n >= total:
            print(f"⚠️  Кадр {n} вне диапазона (0..{total-1}). Беру последний.")
            n = total - 1
        return n

    print(f"❌ Не понял номер кадра: {arg}")
    return None


# ────────────────────────── утилиты ──────────────────────────

def ensure_extension(path, ext):
    _, e = os.path.splitext(path)
    if not e:
        return path + ext
    return path


def safe_mkdir(path):
    if os.path.isdir(path):
        if os.listdir(path):
            answer = input(f"⚠️  Папка '{path}' не пуста. Очистить её? [y/N]: ").strip().lower()
            if answer in ("y", "yes", "д", "да"):
                shutil.rmtree(path)
                os.makedirs(path, exist_ok=True)
                print(f"🧹 Папка очищена: {path}")
            else:
                print("ℹ️  Пишем в существующую папку (файлы могут перезаписаться).")
    else:
        os.makedirs(path, exist_ok=True)
        print(f"📁 Создана папка: {path}")


def get_video_writer(path, fps, size, codec="mp4v"):
    fourcc = cv2.VideoWriter_fourcc(*codec)
    writer = cv2.VideoWriter(path, fourcc, fps, size)
    if not writer.isOpened():
        print(f"❌ Не удалось создать VideoWriter: {path}")
        return None
    return writer


# ────────────────────────── 1) извлечь кадр ──────────────────────────

def save_frame(video_path, frame_index, output_path):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"❌ Не удалось открыть видео: {video_path}")
        return False

    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
    ret, frame = cap.read()
    cap.release()

    if not ret:
        cap = cv2.VideoCapture(video_path)
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, frame_index - 1))
        ret, frame = cap.read()
        cap.release()
        if not ret:
            print("❌ Не удалось прочитать кадр")
            return False

    cv2.imwrite(output_path, frame)
    print(f"✅ Кадр {frame_index} сохранён: {output_path}")
    return True


# ────────────────────────── 2) обрезка ──────────────────────────

def trim_video(video_path, start_frame, end_frame, output_path):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"❌ Не удалось открыть видео: {video_path}")
        return False

    total, fps, w, h, _ = get_video_info(cap)
    if fps <= 0:
        fps = 25.0

    if start_frame > end_frame:
        start_frame, end_frame = end_frame, start_frame

    start_frame = max(0, min(start_frame, total - 1))
    end_frame = max(0, min(end_frame, total - 1))

    print(f"✂️  Обрезка: кадры {start_frame}..{end_frame} "
          f"({end_frame - start_frame + 1} кадров)")

    out = get_video_writer(output_path, fps, (w, h))
    if out is None:
        cap.release()
        return False

    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    current = start_frame
    saved = 0

    while current <= end_frame:
        ret, frame = cap.read()
        if not ret:
            break
        out.write(frame)
        saved += 1
        current += 1
        if saved % 30 == 0 or current > end_frame:
            pct = 100 * (current - start_frame) / (end_frame - start_frame + 1)
            print(f"\r  ⏳ {pct:5.1f}% ({saved} кадров)", end="", flush=True)

    print()
    cap.release()
    out.release()
    print(f"✅ Сохранено: {output_path} ({saved} кадров)")
    return True


# ────────────────────────── 3) склейка двух видео ──────────────────────────

def merge_videos(video1, video2, output_path, target_size=None, target_fps=None):
    cap1 = cv2.VideoCapture(video1)
    cap2 = cv2.VideoCapture(video2)

    if not cap1.isOpened():
        print(f"❌ Не удалось открыть: {video1}")
        return False
    if not cap2.isOpened():
        print(f"❌ Не удалось открыть: {video2}")
        cap1.release()
        return False

    t1, fps1, w1, h1, _ = get_video_info(cap1)
    t2, fps2, w2, h2, _ = get_video_info(cap2)

    print(f"🎬 Видео 1: {w1}x{h1} @ {fps1:.2f} FPS, {t1} кадров")
    print(f"🎬 Видео 2: {w2}x{h2} @ {fps2:.2f} FPS, {t2} кадров")

    out_w, out_h = (target_size if target_size else (w1, h1))
    out_fps = target_fps if target_fps else (fps1 if fps1 > 0 else 25.0)

    if (w1, h1) != (w2, h2):
        print(f"⚠️  Разные размеры. Привожу оба к {out_w}x{out_h}")
    if abs(fps1 - fps2) > 0.01:
        print(f"⚠️  Разный FPS. Итоговый FPS: {out_fps:.2f}")

    out = get_video_writer(output_path, out_fps, (out_w, out_h))
    if out is None:
        cap1.release()
        cap2.release()
        return False

    total_frames = t1 + t2
    written = 0

    def pump(cap):
        nonlocal written
        count = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if (frame.shape[1], frame.shape[0]) != (out_w, out_h):
                frame = cv2.resize(frame, (out_w, out_h))
            out.write(frame)
            written += 1
            count += 1
            if written % 30 == 0:
                pct = 100 * written / max(1, total_frames)
                print(f"\r  ⏳ {pct:5.1f}% ({written} кадров)", end="", flush=True)
        return count

    print("📎 Пишу первое видео...")
    c1 = pump(cap1)
    print(f"\n  ✅ {c1} кадров из первого")
    print("📎 Пишу второе видео...")
    c2 = pump(cap2)
    print(f"\n  ✅ {c2} кадров из второго")

    cap1.release()
    cap2.release()
    out.release()

    print(f"✅ Склеено в: {output_path} (всего {written} кадров)")
    return True


# ────────────────────────── 4) все кадры в папку ──────────────────────────

def extract_all_frames(video_path, output_dir, fmt="jpg", quality=95,
                       every_n=1, prefix="frame"):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"❌ Не удалось открыть видео: {video_path}")
        return False

    total, fps, w, h, _ = get_video_info(cap)
    print(f"🎞  Всего кадров: {total}")

    safe_mkdir(output_dir)

    if fmt.lower() in ("jpg", "jpeg"):
        ext = ".jpg"
        params = [cv2.IMWRITE_JPEG_QUALITY, int(quality)]
    elif fmt.lower() == "png":
        ext = ".png"
        params = [cv2.IMWRITE_PNG_COMPRESSION, 3]
    else:
        ext = "." + fmt.lower().lstrip(".")
        params = []

    idx = 0
    saved = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if idx % every_n == 0:
            filename = f"{prefix}_{idx:06d}{ext}"
            cv2.imwrite(os.path.join(output_dir, filename), frame, params)
            saved += 1
            if saved % 25 == 0:
                pct = 100 * idx / max(1, total)
                print(f"\r  ⏳ {pct:5.1f}% ({saved} сохранено)", end="", flush=True)
        idx += 1

    cap.release()
    print(f"\n✅ Сохранено {saved} кадров в: {output_dir}/")
    return True


# ────────────────────────── 5) видео из кадров ──────────────────────────

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp")


def _natural_key(name):
    return [int(t) if t.isdigit() else t.lower()
            for t in re.split(r"(\d+)", name)]


def collect_frame_files(path):
    if os.path.isdir(path):
        files = [os.path.join(path, f) for f in os.listdir(path)
                 if f.lower().endswith(IMAGE_EXTS)]
        files.sort(key=lambda p: _natural_key(os.path.basename(p)))
        return files
    if os.path.isfile(path):
        return [path]
    return []


def frames_to_video(input_path, output_path, fps=30.0,
                    size=None, codec="mp4v",
                    start=None, end=None, every_n=1,
                    pattern=None):
    if pattern and os.path.isdir(input_path):
        rx = re.compile(pattern)
        files = [os.path.join(input_path, f)
                 for f in os.listdir(input_path)
                 if f.lower().endswith(IMAGE_EXTS) and rx.search(f)]
        files.sort(key=lambda p: _natural_key(os.path.basename(p)))
    else:
        files = collect_frame_files(input_path)

    if not files:
        print(f"❌ В '{input_path}' не найдено изображений")
        return False

    total_files = len(files)
    print(f"🖼  Найдено изображений: {total_files}")

    if start is None: start = 0
    if end is None: end = total_files - 1
    if start < 0: start = max(0, total_files + start)
    if end < 0: end = max(0, total_files + end)
    start = max(0, min(start, total_files - 1))
    end = max(0, min(end, total_files - 1))
    if start > end:
        start, end = end, start

    files = files[start:end + 1]
    if every_n > 1:
        files = files[::every_n]

    print(f"🎬 Собираю видео из {len(files)} кадров @ {fps:.2f} FPS")

    first = cv2.imread(files[0])
    if first is None:
        print(f"❌ Не удалось прочитать: {files[0]}")
        return False

    if size is None:
        h0, w0 = first.shape[:2]
        size = (w0, h0)

    out = get_video_writer(output_path, fps, size, codec=codec)
    if out is None:
        return False

    written = 0
    for i, fpath in enumerate(files):
        img = cv2.imread(fpath)
        if img is None:
            print(f"⚠️  Пропуск (не читается): {fpath}")
            continue
        if (img.shape[1], img.shape[0]) != size:
            img = cv2.resize(img, size)
        out.write(img)
        written += 1
        if written % 25 == 0 or i == len(files) - 1:
            pct = 100 * (i + 1) / len(files)
            print(f"\r  ⏳ {pct:5.1f}% ({written} кадров)", end="", flush=True)

    print()
    out.release()
    print(f"✅ Видео сохранено: {output_path} ({written} кадров)")
    return True


# ────────────────────────── 6) GIF из видео ──────────────────────────  # NEW

def video_to_gif(video_path, output_path,
                 start_frame=None, end_frame=None,
                 fps=12.0,            # частота кадров GIF
                 width=None,          # ширина (высота подберётся)
                 scale=1.0,           # или коэффициент
                 every_n=1,           # брать каждый N-й кадр исходника
                 loop=0,              # 0 = бесконечно
                 max_colors=256,
                 optimize=True):
    """
    Создаёт анимированный GIF из видео.
      start_frame / end_frame — диапазон кадров (можно отрицательные: -1 = последний).
      fps        — сколько кадров GIF в секунду (по умолчанию 12, чтобы файл не раздувался).
      width      — ширина кадра GIF (высота пропорционально). Если None — берётся scale.
      scale      — коэффициент уменьшения (например 0.5 = вдвое меньше).
      every_n    — из исходника брать каждый N-й кадр (грубая прореживание до fps).
      loop       — 0 = зациклить бесконечно.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"❌ Не удалось открыть видео: {video_path}")
        return False

    total, src_fps, w, h, _ = get_video_info(cap)
    if total <= 0:
        print("❌ В видео нет кадров")
        cap.release()
        return False

    # диапазон
    if start_frame is None: start_frame = 0
    if end_frame is None:   end_frame = total - 1
    if start_frame < 0: start_frame = max(0, total + start_frame)
    if end_frame < 0:   end_frame = max(0, total + end_frame)
    start_frame = max(0, min(start_frame, total - 1))
    end_frame = max(0, min(end_frame, total - 1))
    if start_frame > end_frame:
        start_frame, end_frame = end_frame, start_frame

    # размер GIF
    if width is None:
        out_w = max(1, int(w * scale))
    else:
        out_w = int(width)
    out_h = max(1, int(h * out_w / w))

    # как часто реально брать кадры из исходника,
    # чтобы итоговый fps был близок к заданному
    if src_fps > 0 and fps > 0:
        step_by_fps = max(1, int(round(src_fps / fps)))
    else:
        step_by_fps = 1
    step = max(1, every_n, step_by_fps)

    # сколько кадров попадёт в GIF (оценка для прогресса)
    est_total = max(1, (end_frame - start_frame) // step + 1)
    real_fps = src_fps / step if src_fps > 0 else fps
    if real_fps <= 0:
        real_fps = fps if fps > 0 else 12.0

    print(f"🎞  Кадров в источнике: {total}")
    print(f"✂️  Диапазон: {start_frame}..{end_frame}")
    print(f"🎯 Размер GIF: {out_w}x{out_h}, fps={real_fps:.2f}, шаг={step}")

    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    frames = []
    idx = start_frame
    while idx <= end_frame:
        ret, frame = cap.read()
        if not ret:
            break
        if (idx - start_frame) % step == 0:
            frame = cv2.resize(frame, (out_w, out_h), interpolation=cv2.INTER_AREA)
            # OpenCV читает BGR → Pillow ждёт RGB
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frames.append(Image.fromarray(rgb))
            if len(frames) % 10 == 0:
                pct = 100 * (idx - start_frame) / max(1, end_frame - start_frame)
                print(f"\r  ⏳ {pct:5.1f}% ({len(frames)} кадров)", end="", flush=True)
        idx += 1

    cap.release()

    if not frames:
        print("\n❌ Не удалось собрать ни одного кадра")
        return False

    print(f"\n💾 Сохраняю GIF из {len(frames)} кадров...")
    duration_ms = int(1000 / real_fps) if real_fps > 0 else 80

    # Конвертируем в палитру (P) — обязательно для GIF
    paletted = []
    for i, im in enumerate(frames):
        paletted.append(
            im.convert("P", palette=Image.ADAPTIVE, colors=max_colors)
        )
        if (i + 1) % 10 == 0 or i == len(frames) - 1:
            pct = 100 * (i + 1) / len(frames)
            print(f"\r  ⏳ {pct:5.1f}%", end="", flush=True)
    print()

    paletted[0].save(
        output_path,
        save_all=True,
        append_images=paletted[1:],
        duration=duration_ms,
        loop=loop,
        optimize=optimize,
        disposal=2,
    )

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"✅ GIF сохранён: {output_path} "
          f"({len(paletted)} кадров, {size_mb:.2f} МБ)")
    return True


# ────────────────────────── интерактивный режим ──────────────────────────

def ask_video(prompt="Введите путь к видео: "):
    path = input(prompt).strip().strip("'\"")
    if not os.path.isfile(path):
        print(f"❌ Файл не найден: {path}")
        return None
    return path


def ask_int(prompt, default=None):
    raw = input(prompt).strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        print(f"⚠️  Не число, беру значение по умолчанию: {default}")
        return default


def ask_float(prompt, default=None):
    raw = input(prompt).strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        print(f"⚠️  Не число, беру значение по умолчанию: {default}")
        return default


def interactive_mode():
    print("\n╔════════════════════════════════════════════════════╗")
    print("║              🎬 ВИДЕОРЕДАКТОР v4                   ║")
    print("╠════════════════════════════════════════════════════╣")
    print("║  1 — Извлечь один кадр                             ║")
    print("║  2 — Обрезать видео (диапазон кадров)              ║")
    print("║  3 — Склеить два видео                             ║")
    print("║  4 — Извлечь все кадры в папку                     ║")
    print("║  5 — Собрать видео из кадров                       ║")
    print("║  6 — Сделать GIF из видео         # NEW            ║")
    print("║  0 — Выход                                         ║")
    print("╚════════════════════════════════════════════════════╝")

    choice = input("Режим [0-6]: ").strip()

    if choice == "0":
        return

    if choice == "1":
        v = ask_video()
        if not v: return
        total, *_ = print_video_info(v)
        raw = input("Номер кадра (100 / -1 / end:50): ").strip()
        idx = parse_frame_arg(raw, total)
        if idx is None: return
        out = input("Куда сохранить (jpg/png, Enter = auto): ").strip() or f"frame_{idx}.jpg"
        save_frame(v, idx, ensure_extension(out, ".jpg"))

    elif choice == "2":
        v = ask_video()
        if not v: return
        total, *_ = print_video_info(v)
        raw_start = input("Начало (0 / -100): ").strip()
        start = parse_frame_arg(raw_start, total)
        if start is None: return
        raw_end = input("Конец (Enter/'end' = последний): ").strip()
        end = total - 1 if raw_end.lower() in ("", "end", "последний") else parse_frame_arg(raw_end, total)
        if end is None: return
        out = input("Куда сохранить (mp4, Enter = trimmed.mp4): ").strip() or "trimmed.mp4"
        trim_video(v, start, end, ensure_extension(out, ".mp4"))

    elif choice == "3":
        v1 = ask_video("Первое видео: ")
        if not v1: return
        v2 = ask_video("Второе видео: ")
        if not v2: return
        out = input("Куда сохранить (Enter = merged.mp4): ").strip() or "merged.mp4"
        merge_videos(v1, v2, ensure_extension(out, ".mp4"))

    elif choice == "4":
        v = ask_video()
        if not v: return
        print_video_info(v)
        out_dir = input("Папка для кадров (Enter = frames): ").strip() or "frames"
        fmt = input("Формат [jpg/png] (Enter = jpg): ").strip().lower() or "jpg"
        every_n = ask_int("Каждый N-й кадр (Enter = каждый): ", 1)
        quality = ask_int("Качество JPEG 0-100 (Enter = 95): ", 95)
        extract_all_frames(v, out_dir, fmt=fmt, quality=quality, every_n=every_n)

    elif choice == "5":
        path = input("Папка с кадрами (или один файл): ").strip().strip("'\"")
        if not (os.path.isdir(path) or os.path.isfile(path)):
            print(f"❌ Не найдено: {path}")
            return
        out = input("Куда сохранить (mp4, Enter = from_frames.mp4): ").strip() or "from_frames.mp4"
        out = ensure_extension(out, ".mp4")
        fps = ask_float("FPS (Enter = 30): ", 30.0)
        every_n = ask_int("Брать каждый N-й кадр (Enter = каждый): ", 1)
        w = ask_int("Ширина (Enter = из первого кадра): ", None)
        h = ask_int("Высота (Enter = из первого кадра): ", None)
        size = (w, h) if (w and h) else None
        start = ask_int("Начать с кадра № (Enter = 0): ", None)
        end = ask_int("Закончить на кадре № (Enter = последний): ", None)
        pattern = input("Regex-фильтр имён (Enter = все): ").strip() or None
        frames_to_video(path, out, fps=fps, size=size,
                        start=start, end=end, every_n=every_n,
                        pattern=pattern)

    elif choice == "6":  # NEW
        v = ask_video()
        if not v: return
        total, *_ = print_video_info(v)

        print("\nДиапазон кадров (Enter = весь файл):")
        raw_start = input("Начало (0 / -100 / Enter): ").strip()
        start = parse_frame_arg(raw_start, total) if raw_start else None

        raw_end = input("Конец (Enter/'end' = последний): ").strip()
        end = total - 1 if raw_end.lower() in ("", "end", "последний") else parse_frame_arg(raw_end, total)

        out = input("Куда сохранить (Enter = out.gif): ").strip() or "out.gif"
        out = ensure_extension(out, ".gif")

        fps = ask_float("FPS GIF (Enter = 12): ", 12.0)

        width_raw = input("Ширина GIF в px (Enter = авто по scale): ").strip()
        width = int(width_raw) if width_raw.isdigit() else None
        scale = ask_float("Масштаб, если ширина не задана (Enter = 0.5): ", 0.5)

        colors = ask_int("Число цветов (Enter = 256): ", 256)

        video_to_gif(v, out,
                     start_frame=start, end_frame=end,
                     fps=fps, width=width, scale=scale,
                     max_colors=colors)

    else:
        print("❌ Неизвестный режим")


# ────────────────────────── CLI ──────────────────────────

def build_parser():
    p = argparse.ArgumentParser(
        description="Видеоредактор: кадр / обрезка / склейка / кадры / из кадров / GIF"
    )
    sub = p.add_subparsers(dest="cmd")

    pf = sub.add_parser("frame", help="Извлечь один кадр")
    pf.add_argument("video")
    pf.add_argument("index")
    pf.add_argument("-o", "--output", default=None)

    pt = sub.add_parser("trim", help="Обрезать видео")
    pt.add_argument("video")
    pt.add_argument("--start", required=True)
    pt.add_argument("--end", default="end")
    pt.add_argument("-o", "--output", default="trimmed.mp4")

    pm = sub.add_parser("merge", help="Склеить два видео")
    pm.add_argument("video1")
    pm.add_argument("video2")
    pm.add_argument("-o", "--output", default="merged.mp4")

    pa = sub.add_parser("all", help="Извлечь все кадры в папку")
    pa.add_argument("video")
    pa.add_argument("-d", "--dir", default="frames")
    pa.add_argument("--fmt", default="jpg", choices=["jpg", "jpeg", "png"])
    pa.add_argument("--every", type=int, default=1)
    pa.add_argument("--quality", type=int, default=95)

    pv = sub.add_parser("from-frames", help="Собрать видео из кадров")
    pv.add_argument("input")
    pv.add_argument("-o", "--output", default="from_frames.mp4")
    pv.add_argument("--fps", type=float, default=30.0)
    pv.add_argument("--size")
    pv.add_argument("--start", type=int, default=None)
    pv.add_argument("--end", type=int, default=None)
    pv.add_argument("--every", type=int, default=1)
    pv.add_argument("--pattern", default=None)

    # NEW
    pg = sub.add_parser("gif", help="Сделать GIF из видео")
    pg.add_argument("video")
    pg.add_argument("-o", "--output", default="out.gif")
    pg.add_argument("--start", default=None, help="Начальный кадр (можно -100)")
    pg.add_argument("--end", default=None, help="Конечный кадр (можно end)")
    pg.add_argument("--fps", type=float, default=12.0, help="FPS GIF (по умолч. 12)")
    pg.add_argument("--width", type=int, default=None, help="Ширина GIF в px")
    pg.add_argument("--scale", type=float, default=0.5,
                    help="Масштаб, если --width не задан (по умолч. 0.5)")
    pg.add_argument("--every", type=int, default=1, help="Брать каждый N-й кадр")
    pg.add_argument("--colors", type=int, default=256, help="Число цветов GIF (2..256)")
    pg.add_argument("--loop", type=int, default=0, help="0 = бесконечно")

    return p


def main():
    if len(sys.argv) == 1:
        interactive_mode()
        return

    parser = build_parser()
    args = parser.parse_args()

    if args.cmd is None:
        interactive_mode()
        return

    if args.cmd == "frame":
        total, *_ = print_video_info(args.video)
        idx = parse_frame_arg(args.index, total)
        if idx is None: sys.exit(1)
        out = args.output or f"frame_{idx}.jpg"
        save_frame(args.video, idx, ensure_extension(out, ".jpg"))

    elif args.cmd == "trim":
        total, *_ = print_video_info(args.video)
        start = parse_frame_arg(args.start, total)
        if start is None: sys.exit(1)
        end = total - 1 if args.end.lower() in ("end", "последний") else parse_frame_arg(args.end, total)
        if end is None: sys.exit(1)
        trim_video(args.video, start, end, ensure_extension(args.output, ".mp4"))

    elif args.cmd == "merge":
        merge_videos(args.video1, args.video2, ensure_extension(args.output, ".mp4"))

    elif args.cmd == "all":
        extract_all_frames(args.video, args.dir, fmt=args.fmt,
                           quality=args.quality, every_n=args.every)

    elif args.cmd == "from-frames":
        size = None
        if args.size:
            try:
                w, h = args.size.lower().split("x")
                size = (int(w), int(h))
            except ValueError:
                print(f"⚠️  Не понял --size '{args.size}', беру из первого кадра")
        frames_to_video(args.input, ensure_extension(args.output, ".mp4"),
                        fps=args.fps, size=size,
                        start=args.start, end=args.end,
                        every_n=args.every, pattern=args.pattern)

    elif args.cmd == "gif":  # NEW
        total, *_ = print_video_info(args.video)
        start = parse_frame_arg(args.start, total) if args.start else None
        if args.end is None or str(args.end).lower() in ("end", "последний"):
            end = total - 1
        else:
            end = parse_frame_arg(args.end, total)
        video_to_gif(args.video, ensure_extension(args.output, ".gif"),
                     start_frame=start, end_frame=end,
                     fps=args.fps, width=args.width, scale=args.scale,
                     every_n=args.every, loop=args.loop,
                     max_colors=args.colors)


if __name__ == "__main__":
    main()
