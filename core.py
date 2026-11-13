"""FFmpeg probing, validation and command construction."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

VIDEO_EXT = {".mp4", ".m4v", ".mov", ".mkv", ".avi", ".webm", ".ts", ".m2ts", ".wmv", ".flv"}
AUDIO_EXT = {".mka", ".aac", ".ac3", ".eac3", ".dts", ".mp3", ".flac", ".opus", ".ogg", ".wav", ".m4a", ".thd"}
SUB_EXT = {".srt", ".ass", ".ssa", ".vtt", ".sup"}

# Language name, Matroska code and filename aliases.
LANGUAGES = [
    ("Undetermined", "und", ""),
    ("English", "eng", "en"),
    ("Arabic", "ara", "ar"),
    ("French", "fre", "fr"),
    ("Spanish", "spa", "es"),
    ("German", "ger", "de"),
    ("Italian", "ita", "it"),
    ("Portuguese", "por", "pt"),
    ("Russian", "rus", "ru"),
    ("Japanese", "jpn", "ja"),
    ("Korean", "kor", "ko"),
    ("Chinese", "chi", "zh"),
    ("Turkish", "tur", "tr"),
    ("Hindi", "hin", "hi"),
    ("Persian", "per", "fa"),
    ("Dutch", "dut", "nl"),
    ("Polish", "pol", "pl"),
    ("Ukrainian", "ukr", "uk"),
    ("Swedish", "swe", "sv"),
    ("Hebrew", "heb", "he"),
    ("Greek", "gre", "el"),
    ("Indonesian", "ind", "id"),
    ("Thai", "tha", "th"),
    ("Vietnamese", "vie", "vi"),
    ("Czech", "cze", "cs"),
]
_ALT_CODES = {"fra": "fre", "deu": "ger", "zho": "chi", "fas": "per", "nld": "dut", "ell": "gre", "ces": "cze"}

NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


class ProbeError(Exception):
    pass


@dataclass
class StreamInfo:
    index: int
    kind: str  # video, audio, subtitle, other
    codec: str
    language: str = "und"
    title: str = ""
    width: int = 0
    height: int = 0


@dataclass
class ProbeResult:
    path: str
    duration: float
    format_name: str
    streams: list[StreamInfo] = field(default_factory=list)

    def of_kind(self, kind: str) -> list[StreamInfo]:
        return [s for s in self.streams if s.kind == kind]


@dataclass
class ExtraTrack:
    kind: str  # "audio" or "subtitle"
    path: str
    language: str = "und"
    title: str = ""
    delay_ms: int = 0
    default: bool = False


@dataclass
class Job:
    video: ProbeResult
    extras: list[ExtraTrack]
    output: str
    keep_audio: bool = True
    keep_subs: bool = True
    title: str = ""


def kind_of(path: str) -> str | None:
    ext = Path(path).suffix.lower()
    if ext in VIDEO_EXT:
        return "video"
    if ext in AUDIO_EXT:
        return "audio"
    if ext in SUB_EXT:
        return "subtitle"
    return None


def guess_language(filename: str) -> str:
    """Guess a language code from a file name such as 'movie.fr.srt' or 'dub_arabic.mka'."""
    tokens = [t for t in re.split(r"[^a-z]+", Path(filename).stem.lower()) if t]
    for i, tok in enumerate(tokens):
        for name, code, two in LANGUAGES[1:]:
            if tok == name.lower() or tok == code:
                return code
            if two and tok == two:
                return code
        if tok in _ALT_CODES:
            return _ALT_CODES[tok]
    return "und"


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def find_tool(name: str, custom_dir: str = "") -> str | None:
    exe = name + (".exe" if sys.platform == "win32" else "")
    folders = [Path(custom_dir)] if custom_dir else []
    folders += [app_dir() / "ffmpeg", app_dir()]
    for folder in folders:
        candidate = folder / exe
        if candidate.is_file():
            return str(candidate)
    return shutil.which(name)


def probe(ffprobe: str, path: str) -> ProbeResult:
    try:
        run = subprocess.run(
            [ffprobe, "-v", "error", "-show_format", "-show_streams", "-of", "json", path],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=60, creationflags=NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProbeError(str(exc)) from exc
    if run.returncode != 0:
        raise ProbeError(run.stderr.strip() or "ffprobe could not read this file.")
    try:
        data = json.loads(run.stdout)
    except json.JSONDecodeError as exc:
        raise ProbeError("ffprobe returned unreadable output.") from exc

    kinds = {"video": "video", "audio": "audio", "subtitle": "subtitle"}
    streams = []
    for s in data.get("streams", []):
        tags = s.get("tags", {}) or {}
        streams.append(StreamInfo(
            index=int(s.get("index", 0)),
            kind=kinds.get(s.get("codec_type", ""), "other"),
            codec=s.get("codec_name", "unknown"),
            language=tags.get("language", "und"),
            title=tags.get("title", ""),
            width=int(s.get("width", 0) or 0),
            height=int(s.get("height", 0) or 0),
        ))
    fmt = data.get("format", {}) or {}
    try:
        duration = float(fmt.get("duration", 0) or 0)
    except ValueError:
        duration = 0.0
    if not streams:
        raise ProbeError("No streams found in this file.")
    return ProbeResult(path, duration, fmt.get("format_name", ""), streams)


def default_output_path(video_path: str) -> str:
    p = Path(video_path)
    if p.suffix.lower() == ".mkv":
        return str(p.with_name(p.stem + " (new).mkv"))
    return str(p.with_suffix(".mkv"))


def validate_job(job: Job) -> list[str]:
    errors = []
    if not Path(job.video.path).is_file():
        errors.append("The video file no longer exists.")
    for extra in job.extras:
        if not Path(extra.path).is_file():
            errors.append(f"Missing file: {Path(extra.path).name}")
    out = Path(job.output)
    if out.suffix.lower() != ".mkv":
        errors.append("The output name must end with .mkv.")

    def same_path(first: str | Path, second: str | Path) -> bool:
        first_path = os.path.normcase(str(Path(first).resolve()))
        second_path = os.path.normcase(str(Path(second).resolve()))
        return first_path == second_path

    if same_path(out, job.video.path):
        errors.append("The output can't overwrite the source video.")
    for extra in job.extras:
        if same_path(out, extra.path):
            errors.append(f"The output can't overwrite an added track: {Path(extra.path).name}")
            break
    if not job.video.of_kind("video"):
        errors.append("The selected file doesn't contain a video stream.")
    if not out.parent.is_dir():
        errors.append("The output folder doesn't exist.")
    return errors


def build_command(ffmpeg: str, job: Job) -> list[str]:
    """Build the FFmpeg command for a stream-copy remux."""
    cmd = [ffmpeg, "-y", "-hide_banner", "-nostdin", "-progress", "pipe:1", "-nostats",
           "-i", job.video.path]
    for extra in job.extras:
        if extra.kind == "audio" and extra.delay_ms:
            cmd += ["-itsoffset", f"{extra.delay_ms / 1000:.3f}"]
        cmd += ["-i", extra.path]

    cmd += ["-map_chapters", "0"]
    for s in job.video.of_kind("video"):
        cmd += ["-map", f"0:{s.index}"]

    kept_audio = job.video.of_kind("audio") if job.keep_audio else []
    kept_subs = job.video.of_kind("subtitle") if job.keep_subs else []
    for s in kept_audio:
        cmd += ["-map", f"0:{s.index}"]
    for n, extra in enumerate(job.extras, start=1):
        if extra.kind == "audio":
            cmd += ["-map", f"{n}:a:0"]
    for s in kept_subs:
        cmd += ["-map", f"0:{s.index}"]
    for n, extra in enumerate(job.extras, start=1):
        if extra.kind == "subtitle":
            cmd += ["-map", f"{n}:s:0"]

    cmd += ["-map", "0:t?"]  # Keep source attachments, including subtitle fonts.

    cmd += ["-c", "copy"]
    for k, s in enumerate(kept_subs):
        if s.codec == "mov_text":  # Matroska requires text subtitles in SRT format.
            cmd += [f"-c:s:{k}", "srt"]

    chosen = {"audio": None, "subtitle": None}
    counters = {"audio": len(kept_audio), "subtitle": len(kept_subs)}
    flag = {"audio": "a", "subtitle": "s"}
    for extra in job.extras:
        k = counters[extra.kind]
        counters[extra.kind] += 1
        f = flag[extra.kind]
        if extra.kind == "subtitle" and Path(extra.path).suffix.lower() == ".vtt":
            cmd += [f"-c:s:{k}", "srt"]
        cmd += [f"-metadata:s:{f}:{k}", f"language={extra.language or 'und'}"]
        if extra.title:
            cmd += [f"-metadata:s:{f}:{k}", f"title={extra.title}"]
        if extra.default and chosen[extra.kind] is None:
            chosen[extra.kind] = k

    for kind, pick in chosen.items():
        if pick is not None:
            for j in range(counters[kind]):
                cmd += [f"-disposition:{flag[kind]}:{j}", "default" if j == pick else "0"]

    if job.title:
        cmd += ["-metadata", f"title={job.title}"]
    cmd += ["-f", "matroska", job.output]
    return cmd


def parse_progress_line(line: str) -> float | None:
    """Return seconds processed from an FFmpeg '-progress' line, or None."""
    key, _, value = line.strip().partition("=")
    if key in ("out_time_us", "out_time_ms"):  # FFmpeg reports microseconds.
        try:
            return max(0, int(value)) / 1_000_000
        except ValueError:
            return None
    return None


def format_duration(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def human_size(num_bytes: float) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"
