import difflib
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .base import BaseAction, ActionResult, ActionContext
from .window_control import close_window_for_file


# ---------------------------------------------------------------------------
# grade_student
# ---------------------------------------------------------------------------

class GradeStudentAction(BaseAction):
    name = "grade_student"

    def run(
        self,
        params: dict,
        context: ActionContext,
        target: dict | None = None,
        current_grade: int | None = None,
    ) -> ActionResult:
        student = params.get("student", "?")
        grade = params.get("grade", "?")
        target = target or {}

        print(
            f"[ACTION] grade_student: student={student!r}, grade={grade}, "
            f"target={target!r}, current_grade={current_grade}, "
            f"dry_run={context.dry_run}",
            flush=True,
        )

        subject = context.current_subject or "?"
        lesson = context.current_lesson or "?"
        cell = target.get("cell", "?")
        sheet = target.get("sheet", "?")

        if not target:
            return ActionResult(
                executed=False,
                needs_confirmation=True,
                dry_run=True,
                message=(
                    f"Я собираюсь поставить {student} оценку {grade}. "
                    f"Ячейка пока не определена. Выполнить?"
                ),
                details={"current_grade": current_grade, "target": {}},
            )

        if current_grade is None:
            message = (
                f"Я собираюсь поставить {student} оценку {grade} "
                f"в журнале «{subject}», занятие {lesson}, ячейка {cell} "
                f"(лист {sheet}). Выполнить?"
            )
        else:
            message = (
                f"У {student} на занятии {lesson} уже стоит оценка "
                f"{current_grade}. Заменить её на {grade}?"
            )

        return ActionResult(
            executed=False,
            needs_confirmation=True,
            dry_run=True,
            message=message,
            details={"current_grade": current_grade, "target": target},
        )


# ---------------------------------------------------------------------------
# open_file — тестовое действие
# ---------------------------------------------------------------------------

class OpenFileAction(BaseAction):
    name = "open_file"

    def run(self, params, context, target=None, current_grade=None) -> ActionResult:
        target_name = (params.get("target") or "").strip()
        print(f"[ACTION] open_file: target={target_name!r}", flush=True)
        return ActionResult(
            True,
            f"Открываю: {target_name or 'файл'}. (тест)",
            details={"target": target_name},
        )


# ---------------------------------------------------------------------------
# Общие хелперы поиска файлов
# ---------------------------------------------------------------------------

_PUNCT_RE = re.compile(r"[^\w\s\-]+", re.UNICODE)
_WS_RE = re.compile(r"\s+")


def _normalize(s: str) -> str:
    s = (s or "").strip().lower().replace("ё", "е")
    s = _PUNCT_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    return s


_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e",
    "ё": "e", "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k",
    "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "",
    "э": "e", "ю": "yu", "я": "ya",
}


def _translit(s: str) -> str:
    return "".join(_TRANSLIT.get(ch, ch) for ch in s)


def _normalize_for_compare(s: str) -> str:
    return _translit(_normalize(s))


def _token_match_ratio(a: str, b: str) -> float:
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    a_digit = a.isdigit()
    b_digit = b.isdigit()
    if a_digit or b_digit:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


_TOKEN_MATCH_MIN = 0.70
_EXTRA_TOLERANCE_SINGLE = 1
_PENALTY_PER_EXTRA_SINGLE = 0.18
_EXTRA_TOLERANCE_MULTI = 3
_PENALTY_PER_EXTRA_MULTI = 0.06
_MIN_PENALTY = 0.35
_UNMATCHED_PENALTY = 0.25

_DEFAULT_MATCH_THRESHOLD = 0.70
_DEFAULT_AMBIGUITY_MARGIN = 0.05


_STEM_UNMATCHED_IGNORE = {
    "класс", "класса", "классе", "классов", "классы",
    "лекция", "лекции", "лекцию", "лекций",
    "тема", "темы", "тему", "тем",
    "занятие", "занятия", "занятий", "занятии",
    "урок", "урока", "уроков",
    "год", "года", "году", "годов",
    "курс", "курса", "курсе", "курсов",
    "часть", "части", "частей",
    "версия", "версии", "версий",
    "для", "по", "на", "с", "со", "в", "во",
    "и", "а", "но", "или",
}


def _is_meaningful_stem_token(s: str) -> bool:
    if not s:
        return False
    if s.isdigit():
        return False
    if s in _STEM_UNMATCHED_IGNORE:
        return False
    return True


def _similarity(topic_norm: str, stem_norm: str) -> float:
    if not topic_norm or not stem_norm:
        return 0.0
    if topic_norm == stem_norm:
        return 1.0

    topic_tokens = topic_norm.split()
    stem_tokens = stem_norm.split()
    if not topic_tokens or not stem_tokens:
        return 0.0

    matched_topic = 0
    topic_score_sum = 0.0
    for t in topic_tokens:
        best = max((_token_match_ratio(t, s) for s in stem_tokens), default=0.0)
        topic_score_sum += best
        if best >= _TOKEN_MATCH_MIN:
            matched_topic += 1
    topic_coverage = topic_score_sum / len(topic_tokens)

    stem_score_sum = 0.0
    for s in stem_tokens:
        best = max((_token_match_ratio(s, t) for t in topic_tokens), default=0.0)
        stem_score_sum += best
    stem_coverage = stem_score_sum / len(stem_tokens)

    base = max(topic_coverage, stem_coverage)

    meaningful_stem_tokens = [
        s for s in stem_tokens if _is_meaningful_stem_token(s)
    ]
    meaningful_matched = 0
    for s in meaningful_stem_tokens:
        best = max((_token_match_ratio(s, t) for t in topic_tokens), default=0.0)
        if best >= _TOKEN_MATCH_MIN:
            meaningful_matched += 1

    extra_tokens = max(0, len(meaningful_stem_tokens) - meaningful_matched)

    if len(topic_tokens) >= 2:
        tolerance = _EXTRA_TOLERANCE_MULTI
        penalty_per_extra = _PENALTY_PER_EXTRA_MULTI
    else:
        tolerance = _EXTRA_TOLERANCE_SINGLE
        penalty_per_extra = _PENALTY_PER_EXTRA_SINGLE

    if extra_tokens <= tolerance:
        penalty = 1.0
    else:
        overflow = extra_tokens - tolerance
        penalty = max(_MIN_PENALTY, 1.0 - overflow * penalty_per_extra)

    score = base * penalty

    stem_unmatched = 0
    for s in meaningful_stem_tokens:
        best = max((_token_match_ratio(s, t) for t in topic_tokens), default=0.0)
        if best < _TOKEN_MATCH_MIN:
            stem_unmatched += 1

    if stem_unmatched:
        unmatched_penalty = max(
            _MIN_PENALTY,
            1.0 - stem_unmatched * _UNMATCHED_PENALTY,
        )
        score *= unmatched_penalty

    return score


@dataclass
class _Candidate:
    score: float
    path: Path
    is_exact: bool


def _collect_candidates(
    directory: Path,
    topic: str,
    allowed_ext: tuple[str, ...],
) -> list[_Candidate]:
    topic_norm = _normalize_for_compare(topic)
    if not topic_norm:
        return []

    try:
        files = [
            f for f in directory.iterdir()
            if f.is_file() and f.suffix.lower() in allowed_ext
        ]
    except OSError:
        return []

    out: list[_Candidate] = []
    for f in files:
        stem_norm = _normalize_for_compare(f.stem)
        is_exact = (stem_norm == topic_norm)
        score = _similarity(topic_norm, stem_norm)
        out.append(_Candidate(score=score, path=f, is_exact=is_exact))

    out.sort(key=lambda c: (-c.score, c.path.name.lower()))
    return out


def _open_file(path: Path) -> bool:
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
            return True
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
            return True
        subprocess.Popen(["xdg-open", str(path)])
        return True
    except Exception as e:
        print(f"[ACTION] open file error: {e}", flush=True)
        return False


def _format_candidates(cands: list[_Candidate], limit: int = 5) -> str:
    parts = [
        f"{c.path.name} ({int(round(c.score * 100))}%)"
        for c in cands[:limit]
    ]
    if len(cands) > limit:
        parts.append(f"… и ещё {len(cands) - limit}")
    return ", ".join(parts)


_APP_BY_EXT = {
    ".pptx": "powerpoint", ".ppt": "powerpoint", ".odp": "libreoffice",
    ".pdf": "pdf_viewer",
    ".mp4": "vlc", ".webm": "vlc", ".mkv": "vlc", ".mov": "vlc", ".avi": "vlc",
    ".xlsx": "excel", ".xls": "excel", ".xlsm": "excel",
}


def _app_for_path(path: str) -> str | None:
    return _APP_BY_EXT.get(Path(path).suffix.lower())


def _update_last_opened(context, kind: str, path: str) -> None:
    """Сохраняет runtime-состояние последнего открытого файла."""
    context.last_opened_type = kind
    context.last_opened_path = str(path)
    context.last_opened_app = _app_for_path(str(path))


def _clear_last_opened(context) -> None:
    context.last_opened_type = None
    context.last_opened_path = None
    context.last_opened_app = None


# ---------------------------------------------------------------------------
# open_presentation
# ---------------------------------------------------------------------------

_SUPPORTED_PRESENTATION_EXT = (".pptx", ".ppt", ".pdf", ".odp")


class OpenPresentationAction(BaseAction):
    name = "open_presentation"

    def run(self, params, context, target=None, current_grade=None) -> ActionResult:
        topic = (params.get("topic") or "").strip()
        dir_str = getattr(context, "presentations_dir", None)
        threshold = float(getattr(context, "presentation_match_threshold",
                                  _DEFAULT_MATCH_THRESHOLD))
        margin = float(getattr(context, "presentation_ambiguity_margin",
                               _DEFAULT_AMBIGUITY_MARGIN))

        if not dir_str:
            print(f"[ACTION] open_presentation: topic={topic!r} reason=no_dir",
                  flush=True)
            return ActionResult(
                executed=False,
                message="Папка с презентациями не настроена. "
                        "Выберите её в настройках.",
                details={"topic": topic, "reason": "no_dir"},
            )

        directory = Path(dir_str)
        if not directory.is_dir():
            print(f"[ACTION] open_presentation: topic={topic!r} "
                  f"reason=dir_missing dir={directory}", flush=True)
            return ActionResult(
                executed=False,
                message=f"Папка с презентациями не найдена: {directory}. "
                        f"Проверьте настройки.",
                details={"topic": topic, "reason": "dir_missing",
                         "dir": str(directory)},
            )

        if not topic:
            print(f"[ACTION] open_presentation: topic='' reason=no_topic",
                  flush=True)
            return ActionResult(
                executed=False,
                message="Какую презентацию открыть? Уточните тему.",
                details={"topic": "", "reason": "no_topic",
                         "dir": str(directory)},
            )

        candidates = _collect_candidates(
            directory, topic, _SUPPORTED_PRESENTATION_EXT,
        )
        if not candidates:
            print(f"[ACTION] open_presentation: topic={topic!r} "
                  f"reason=not_found candidates=0", flush=True)
            return ActionResult(
                executed=False,
                message=f"Презентация по теме «{topic}» не найдена "
                        f"в папке {directory.name}.",
                details={"topic": topic, "reason": "not_found",
                         "dir": str(directory)},
            )

        exact_candidates = [c for c in candidates if c.is_exact]

        if len(exact_candidates) == 1:
            c = exact_candidates[0]
            print(f"[ACTION] open_presentation: topic={topic!r} "
                  f"chosen={c.path.name!r} score={c.score:.3f} reason=exact",
                  flush=True)
            return self._open_and_report(c.path, topic, c.score,
                                         "exact", context)

        if len(exact_candidates) > 1:
            names = _format_candidates(exact_candidates)
            print(f"[ACTION] open_presentation: topic={topic!r} "
                  f"exact_count={len(exact_candidates)} "
                  f"reason=ambiguous_exact", flush=True)
            return ActionResult(
                executed=False,
                message=(
                    f"Нашла несколько точных совпадений по теме «{topic}»: "
                    f"{names}. Какой файл открыть?"
                ),
                details={"topic": topic, "reason": "ambiguous",
                         "ambiguous_kind": "exact",
                         "dir": str(directory),
                         "candidates": [
                             {"path": str(c.path), "score": c.score,
                              "exact": True}
                             for c in exact_candidates
                         ]},
            )

        top = candidates[0]

        if top.score < threshold:
            print(f"[ACTION] open_presentation: topic={topic!r} "
                  f"top={top.path.name!r} score={top.score:.3f} "
                  f"reason=below_threshold", flush=True)
            return ActionResult(
                executed=False,
                message=(
                    f"Подходящая презентация по теме «{topic}» не найдена. "
                    f"Ближайшее: «{top.path.stem}» "
                    f"({int(round(top.score * 100))}% совпадения)."
                ),
                details={"topic": topic, "reason": "below_threshold",
                         "top_path": str(top.path),
                         "top_score": top.score,
                         "dir": str(directory)},
            )

        if len(candidates) >= 2:
            second = candidates[1]
            if (second.score >= threshold
                    and (top.score - second.score) < margin):
                names = _format_candidates(candidates)
                print(f"[ACTION] open_presentation: topic={topic!r} "
                      f"top={top.path.name!r} score={top.score:.3f} "
                      f"second={second.path.name!r} score={second.score:.3f} "
                      f"reason=ambiguous", flush=True)
                return ActionResult(
                    executed=False,
                    message=(
                        f"Нашла несколько похожих презентаций по теме "
                        f"«{topic}»: {names}. Уточните, пожалуйста, название."
                    ),
                    details={"topic": topic, "reason": "ambiguous",
                             "ambiguous_kind": "fuzzy",
                             "dir": str(directory),
                             "candidates": [
                                 {"path": str(c.path), "score": c.score,
                                  "exact": c.is_exact}
                                 for c in candidates
                             ]},
                )

        print(f"[ACTION] open_presentation: topic={topic!r} "
              f"chosen={top.path.name!r} score={top.score:.3f} "
              f"reason=fuzzy_auto_open", flush=True)
        return self._open_and_report(top.path, topic, top.score,
                                     "fuzzy_auto_open", context)

    @staticmethod
    def _open_and_report(found, topic, score, reason, context=None):
        ok = _open_file(found)
        if not ok:
            return ActionResult(
                executed=False,
                message=f"Нашла «{found.name}», но не удалось открыть файл. "
                        f"Проверьте, что установлено приложение для "
                        f"{found.suffix}.",
                details={"topic": topic, "reason": "open_failed",
                         "path": str(found), "score": score},
            )
        if context is not None:
            _update_last_opened(context, "presentation", str(found))
        return ActionResult(
            executed=True,
            message=f"Открываю презентацию «{found.stem}».",
            details={"topic": topic, "path": str(found),
                     "score": score, "reason": reason},
        )


# ---------------------------------------------------------------------------
# open_video
# ---------------------------------------------------------------------------

_SUPPORTED_VIDEO_EXT = (".mp4", ".webm", ".mkv", ".mov", ".avi")


class OpenVideoAction(BaseAction):
    name = "open_video"

    def run(self, params, context, target=None, current_grade=None) -> ActionResult:
        topic = (params.get("topic") or "").strip()
        dir_str = getattr(context, "presentations_dir", None)
        threshold = float(getattr(context, "presentation_match_threshold",
                                  _DEFAULT_MATCH_THRESHOLD))
        margin = float(getattr(context, "presentation_ambiguity_margin",
                               _DEFAULT_AMBIGUITY_MARGIN))

        if not dir_str:
            print(f"[ACTION] open_video: topic={topic!r} reason=no_dir",
                  flush=True)
            return ActionResult(
                executed=False,
                message="Папка с видео не настроена. Выберите её в настройках.",
                details={"topic": topic, "reason": "no_dir"},
            )

        directory = Path(dir_str)
        if not directory.is_dir():
            print(f"[ACTION] open_video: topic={topic!r} "
                  f"reason=dir_missing dir={directory}", flush=True)
            return ActionResult(
                executed=False,
                message=f"Папка с видео не найдена: {directory}. "
                        f"Проверьте настройки.",
                details={"topic": topic, "reason": "dir_missing",
                         "dir": str(directory)},
            )

        if not topic:
            print(f"[ACTION] open_video: topic='' reason=no_topic", flush=True)
            return ActionResult(
                executed=False,
                message="Какое видео включить? Уточните тему.",
                details={"topic": "", "reason": "no_topic",
                         "dir": str(directory)},
            )

        candidates = _collect_candidates(
            directory, topic, _SUPPORTED_VIDEO_EXT,
        )
        if not candidates:
            print(f"[ACTION] open_video: topic={topic!r} "
                  f"reason=not_found candidates=0", flush=True)
            return ActionResult(
                executed=False,
                message=f"Видео по теме «{topic}» не найдено "
                        f"в папке {directory.name}.",
                details={"topic": topic, "reason": "not_found",
                         "dir": str(directory)},
            )

        exact_candidates = [c for c in candidates if c.is_exact]

        if len(exact_candidates) == 1:
            c = exact_candidates[0]
            print(f"[ACTION] open_video: topic={topic!r} "
                  f"chosen={c.path.name!r} score={c.score:.3f} reason=exact",
                  flush=True)
            return self._open_and_report(c.path, topic, c.score,
                                         "exact", context)

        if len(exact_candidates) > 1:
            names = _format_candidates(exact_candidates)
            print(f"[ACTION] open_video: topic={topic!r} "
                  f"exact_count={len(exact_candidates)} "
                  f"reason=ambiguous_exact", flush=True)
            return ActionResult(
                executed=False,
                message=(
                    f"Нашла несколько точных совпадений по теме «{topic}»: "
                    f"{names}. Какой файл открыть?"
                ),
                details={"topic": topic, "reason": "ambiguous",
                         "ambiguous_kind": "exact",
                         "dir": str(directory),
                         "candidates": [
                             {"path": str(c.path), "score": c.score,
                              "exact": True}
                             for c in exact_candidates
                         ]},
            )

        top = candidates[0]

        if top.score < threshold:
            print(f"[ACTION] open_video: topic={topic!r} "
                  f"top={top.path.name!r} score={top.score:.3f} "
                  f"reason=below_threshold", flush=True)
            return ActionResult(
                executed=False,
                message=(
                    f"Подходящее видео по теме «{topic}» не найдено. "
                    f"Ближайшее: «{top.path.stem}» "
                    f"({int(round(top.score * 100))}% совпадения)."
                ),
                details={"topic": topic, "reason": "below_threshold",
                         "top_path": str(top.path),
                         "top_score": top.score,
                         "dir": str(directory)},
            )

        if len(candidates) >= 2:
            second = candidates[1]
            if (second.score >= threshold
                    and (top.score - second.score) < margin):
                names = _format_candidates(candidates)
                print(f"[ACTION] open_video: topic={topic!r} "
                      f"top={top.path.name!r} score={top.score:.3f} "
                      f"second={second.path.name!r} score={second.score:.3f} "
                      f"reason=ambiguous", flush=True)
                return ActionResult(
                    executed=False,
                    message=(
                        f"Нашла несколько похожих видео по теме "
                        f"«{topic}»: {names}. Уточните, пожалуйста, название."
                    ),
                    details={"topic": topic, "reason": "ambiguous",
                             "ambiguous_kind": "fuzzy",
                             "dir": str(directory),
                             "candidates": [
                                 {"path": str(c.path), "score": c.score,
                                  "exact": c.is_exact}
                                 for c in candidates
                             ]},
                )

        print(f"[ACTION] open_video: topic={topic!r} "
              f"chosen={top.path.name!r} score={top.score:.3f} "
              f"reason=fuzzy_auto_open", flush=True)
        return self._open_and_report(top.path, topic, top.score,
                                     "fuzzy_auto_open", context)

    @staticmethod
    def _open_and_report(found, topic, score, reason, context=None):
        ok = _open_file(found)
        if not ok:
            return ActionResult(
                executed=False,
                message=f"Нашла «{found.name}», но не удалось открыть файл. "
                        f"Проверьте, что установлено приложение для "
                        f"{found.suffix}.",
                details={"topic": topic, "reason": "open_failed",
                         "path": str(found), "score": score},
            )
        if context is not None:
            _update_last_opened(context, "video", str(found))
        return ActionResult(
            executed=True,
            message=f"Включаю видео «{found.stem}».",
            details={"topic": topic, "path": str(found),
                     "score": score, "reason": reason},
        )


# ---------------------------------------------------------------------------
# open_excel
# ---------------------------------------------------------------------------

_SUPPORTED_EXCEL_EXT = (".xlsx", ".xls", ".xlsm")


class OpenExcelAction(BaseAction):
    name = "open_excel"

    def run(self, params, context, target=None, current_grade=None) -> ActionResult:
        topic = (params.get("topic") or "").strip()
        dir_str = getattr(context, "presentations_dir", None)
        threshold = float(getattr(context, "presentation_match_threshold",
                                  _DEFAULT_MATCH_THRESHOLD))
        margin = float(getattr(context, "presentation_ambiguity_margin",
                               _DEFAULT_AMBIGUITY_MARGIN))

        if not dir_str:
            print(f"[ACTION] open_excel: topic={topic!r} reason=no_dir",
                  flush=True)
            return ActionResult(
                executed=False,
                message="Папка с Excel-файлами не настроена.",
                details={"topic": topic, "reason": "no_dir"},
            )
        directory = Path(dir_str)
        if not directory.is_dir():
            return ActionResult(
                executed=False,
                message=f"Папка не найдена: {directory}.",
                details={"topic": topic, "reason": "dir_missing"},
            )
        if not topic:
            return ActionResult(
                executed=False,
                message="Какой Excel-файл открыть? Уточните тему.",
                details={"topic": "", "reason": "no_topic"},
            )

        candidates = _collect_candidates(directory, topic, _SUPPORTED_EXCEL_EXT)
        if not candidates:
            return ActionResult(
                executed=False,
                message=f"Excel-файл по теме «{topic}» не найден.",
                details={"topic": topic, "reason": "not_found"},
            )

        exact_candidates = [c for c in candidates if c.is_exact]
        if len(exact_candidates) == 1:
            c = exact_candidates[0]
            print(f"[ACTION] open_excel: topic={topic!r} "
                  f"chosen={c.path.name!r} score={c.score:.3f} reason=exact",
                  flush=True)
            return self._open_and_report(c.path, topic, c.score, context)
        if len(exact_candidates) > 1:
            names = _format_candidates(exact_candidates)
            return ActionResult(
                executed=False,
                message=f"Нашла несколько точных совпадений: {names}. Какой открыть?",
                details={"topic": topic, "reason": "ambiguous",
                         "ambiguous_kind": "exact"},
            )

        top = candidates[0]
        if top.score < threshold:
            return ActionResult(
                executed=False,
                message=f"Подходящий Excel-файл не найден. "
                        f"Ближайшее: «{top.path.stem}» "
                        f"({int(round(top.score * 100))}%).",
                details={"topic": topic, "reason": "below_threshold",
                         "top_score": top.score},
            )

        if len(candidates) >= 2:
            second = candidates[1]
            if (second.score >= threshold
                    and (top.score - second.score) < margin):
                names = _format_candidates(candidates)
                return ActionResult(
                    executed=False,
                    message=f"Нашла несколько похожих: {names}. Уточните.",
                    details={"topic": topic, "reason": "ambiguous",
                             "ambiguous_kind": "fuzzy"},
                )

        print(f"[ACTION] open_excel: topic={topic!r} "
              f"chosen={top.path.name!r} score={top.score:.3f} "
              f"reason=fuzzy_auto_open", flush=True)
        return self._open_and_report(top.path, topic, top.score, context)

    @staticmethod
    def _open_and_report(found, topic, score, context=None):
        ok = _open_file(found)
        if not ok:
            return ActionResult(
                executed=False,
                message=f"Не удалось открыть «{found.name}».",
                details={"topic": topic, "reason": "open_failed"},
            )
        if context is not None:
            _update_last_opened(context, "excel", str(found))
        return ActionResult(
            executed=True,
            message=f"Открываю Excel-файл «{found.stem}».",
            details={"topic": topic, "path": str(found), "score": score},
        )


# ---------------------------------------------------------------------------
# close_*
# ---------------------------------------------------------------------------

def _close_last_opened(
    context,
    required_kind: str | None,
    not_open_message: str,
) -> ActionResult:
    """
    Адресное закрытие последнего открытого EVA файла.

    Статус "close_requested" означает: команда закрытия ОТПРАВЛЕНА
    в найденное окно. Это НЕ подтверждение, что окно исчезло.

    last_opened_* очищается только при "close_requested" как единственном
    сигнале «мы отправили запрос именно в нужное окно». При
    not_found/ambiguous/unsupported/error состояние НЕ трогаем.
    """
    path = context.last_opened_path
    kind = context.last_opened_type

    if not path or not kind:
        return ActionResult(
            executed=False,
            message=not_open_message,
            details={"reason": "no_last_opened"},
        )

    if required_kind is not None and kind != required_kind:
        return ActionResult(
            executed=False,
            message=not_open_message,
            details={"reason": "no_last_opened", "kind": kind},
        )

    result = close_window_for_file(path)
    print(
        f"[ACTION] close: kind={kind!r} path={path!r} "
        f"status={result.status!r} msg={result.message!r}",
        flush=True,
    )

    if result.status == "close_requested":
        _clear_last_opened(context)
        return ActionResult(
            executed=True,
            message=f"Отправляю запрос на закрытие «{Path(path).name}».",
            details={"path": path, "kind": kind,
                     "status": "close_requested",
                     "matched_title": result.matched_title},
        )
    if result.status == "not_found":
        return ActionResult(
            executed=False,
            message=f"Окно с «{Path(path).name}» не найдено.",
            details={"path": path, "kind": kind, "status": "not_found"},
        )
    if result.status == "ambiguous":
        return ActionResult(
            executed=False,
            message=(
                f"Нашла несколько окон, подходящих под "
                f"«{Path(path).name}». Уточните, какое закрыть."
            ),
            details={"path": path, "kind": kind, "status": "ambiguous",
                     "reason": result.message},
        )
    if result.status == "unsupported":
        return ActionResult(
            executed=False,
            message=(
                f"Адресное закрытие файла не поддерживается на этой системе. "
                f"Закройте «{Path(path).name}» вручную."
            ),
            details={"path": path, "kind": kind,
                     "status": "unsupported",
                     "reason": result.message},
        )
    return ActionResult(
        executed=False,
        message=f"Не удалось закрыть «{Path(path).name}»: {result.message}",
        details={"path": path, "kind": kind,
                 "status": "error", "reason": result.message},
    )


class CloseFileAction(BaseAction):
    name = "close_file"

    def run(self, params, context, target=None, current_grade=None) -> ActionResult:
        return _close_last_opened(
            context,
            required_kind=None,
            not_open_message="Нечего закрывать: я пока ничего не открывала.",
        )


class ClosePresentationAction(BaseAction):
    name = "close_presentation"

    def run(self, params, context, target=None, current_grade=None) -> ActionResult:
        return _close_last_opened(
            context,
            required_kind="presentation",
            not_open_message="Сейчас презентация не открыта.",
        )


class CloseVideoAction(BaseAction):
    name = "close_video"

    def run(self, params, context, target=None, current_grade=None) -> ActionResult:
        return _close_last_opened(
            context,
            required_kind="video",
            not_open_message="Сейчас видео не запущено.",
        )


class CloseExcelAction(BaseAction):
    name = "close_excel"

    def run(self, params, context, target=None, current_grade=None) -> ActionResult:
        return _close_last_opened(
            context,
            required_kind="excel",
            not_open_message="Сейчас Excel-файл не открыт.",
        )


# ---------------------------------------------------------------------------
# restart_*
# ---------------------------------------------------------------------------

def _restart_last_opened(
    context,
    required_kind: str,
    not_open_message: str,
) -> ActionResult:
    """
    Переоткрывает последний открытый файл: закрывает окно и открывает
    заново.

    Логика по статусу закрытия:
      - "close_requested" — команда отправлена, пробуем открыть заново.
      - "not_found"       — окно не найдено, но файл существует;
                            открываем заново.
      - "ambiguous"       — несколько равнозначных окон; НЕ открываем
                            заново.
      - "unsupported"     — НЕ открываем заново (избегаем дубликата).
      - "error"           — НЕ открываем заново.
    """
    path = context.last_opened_path
    kind = context.last_opened_type

    if not path or kind != required_kind:
        return ActionResult(
            executed=False,
            message=not_open_message,
            details={"reason": "no_last_opened"},
        )

    if not os.path.exists(path):
        print(f"[ACTION] restart: reason=path_missing path={path!r}",
              flush=True)
        return ActionResult(
            executed=False,
            message=f"Файл «{Path(path).name}» больше не существует.",
            details={"reason": "path_missing", "path": path},
        )

    close_res = close_window_for_file(path)
    print(
        f"[ACTION] restart: close status={close_res.status!r} "
        f"msg={close_res.message!r}",
        flush=True,
    )

    if close_res.status == "unsupported":
        return ActionResult(
            executed=False,
            message=(
                f"Переоткрытие не поддерживается на этой системе. "
                f"Закройте «{Path(path).name}» вручную."
            ),
            details={"reason": "unsupported", "path": path},
        )
    if close_res.status == "ambiguous":
        return ActionResult(
            executed=False,
            message=(
                f"Нашла несколько окон, подходящих под "
                f"«{Path(path).name}». Не могу однозначно переоткрыть."
            ),
            details={"reason": "ambiguous", "path": path},
        )
    if close_res.status == "error":
        return ActionResult(
            executed=False,
            message=(
                f"Не удалось отправить запрос на закрытие "
                f"«{Path(path).name}»: {close_res.message}"
            ),
            details={"reason": "close_error", "path": path},
        )

    # close_res.status in ("close_requested", "not_found"):
    ok = _open_file(Path(path))
    if not ok:
        return ActionResult(
            executed=False,
            message=f"Не удалось переоткрыть «{Path(path).name}».",
            details={"reason": "open_failed", "path": path},
        )
    _update_last_opened(context, required_kind, path)
    return ActionResult(
        executed=True,
        message=f"Переоткрываю «{Path(path).name}».",
        details={"path": path, "kind": required_kind,
                 "close_status": close_res.status},
    )


class RestartPresentationAction(BaseAction):
    name = "restart_presentation"

    def run(self, params, context, target=None, current_grade=None) -> ActionResult:
        return _restart_last_opened(
            context,
            required_kind="presentation",
            not_open_message="Нечего переоткрывать: презентация не открыта.",
        )


class RestartExcelAction(BaseAction):
    name = "restart_excel"

    def run(self, params, context, target=None, current_grade=None) -> ActionResult:
        return _restart_last_opened(
            context,
            required_kind="excel",
            not_open_message="Нечего переоткрывать: Excel-файл не открыт.",
        )


# ---------------------------------------------------------------------------
# next_slide
# ---------------------------------------------------------------------------

class NextSlideAction(BaseAction):
    name = "next_slide"

    def run(self, params, context, target=None, current_grade=None) -> ActionResult:
        print("[ACTION] next_slide", flush=True)
        return ActionResult(True, "Следующий слайд. (тест)")
