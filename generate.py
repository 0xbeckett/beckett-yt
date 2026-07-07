#!/usr/bin/env python3
"""Generate a POST-MORTEM faceless YouTube video from a markdown script.

Pipeline: markdown narration -> local TTS voiceover -> timed captions/callouts -> ffmpeg MP4.
No cloud APIs or manual editing required.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import select
import shutil
import subprocess
import sys
import textwrap
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_OUT = ROOT / "renders"
DEFAULT_WORK = ROOT / "build"
BACKGROUND_IMAGE = ROOT / "assets" / "banner.png"
FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
ASS_FONT = "DejaVu Sans"
ASS_MONO_FONT = "DejaVu Sans Mono"
BACKGROUND_CARD_COUNT = 8
CHARCOAL = "0x0E0F12"
SLATE = "0x16181D"
AMBER = "0xF5A623"
BONE = "0xF2F0EB"
ASH = "0x8A8F98"
RED = "0xE5484D"
# Output video is full HD. ASS overlays intentionally use a 1280x720
# design canvas; libass scales them cleanly to the 1920x1080 render.
WIDTH = 1920
HEIGHT = 1080
ASS_WIDTH = 1280
ASS_HEIGHT = 720
FFMPEG_TIMEOUT_SECONDS = 90
SEGMENT_TARGET_SECONDS = 35.0
SEGMENT_MAX_SECONDS = 45.0
SEGMENT_CARD_COUNT = 3


@dataclass
class Chunk:
    text: str
    chapter: str
    cues: list[str] = field(default_factory=list)
    wav: Path | None = None
    start: float = 0.0
    speech_duration: float = 0.0
    end: float = 0.0


@dataclass
class ParsedScript:
    title: str
    subtitle: str
    chunks: list[Chunk]


@dataclass
class RenderSegment:
    index: int
    start: float
    end: float
    chunks: list[Chunk]

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


def run(cmd: list[str], *, quiet: bool = False, timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    if timeout is None and Path(cmd[0]).name == "ffmpeg":
        timeout = FFMPEG_TIMEOUT_SECONDS
    if not quiet:
        printable = " ".join(str(c) for c in cmd)
        if timeout:
            printable += f"  # timeout={timeout:.0f}s"
        print("$", printable)
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=timeout)


def check_or_install_tools(auto_install: bool) -> None:
    missing = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
    if shutil.which("espeak-ng") is None and shutil.which("espeak") is None:
        missing.append("espeak-ng")
    if not missing:
        return

    if auto_install and shutil.which("apt-get") and shutil.which("sudo"):
        print(f"Missing tools: {', '.join(missing)}. Attempting non-interactive apt install...")
        env = os.environ.copy()
        env["DEBIAN_FRONTEND"] = "noninteractive"
        subprocess.run(["sudo", "-n", "apt-get", "update"], check=True, env=env)
        packages = ["ffmpeg" if tool in ("ffmpeg", "ffprobe") else "espeak-ng" for tool in missing]
        # Preserve order while de-duping.
        packages = list(dict.fromkeys(packages))
        subprocess.run(["sudo", "-n", "apt-get", "install", "-y", *packages], check=True, env=env)
        if all(shutil.which(tool) for tool in ("ffmpeg", "ffprobe")) and (shutil.which("espeak-ng") or shutil.which("espeak")):
            return

    raise SystemExit(
        "Missing required tools: "
        + ", ".join(missing)
        + ". Install ffmpeg and espeak-ng, or rerun with auto-install enabled."
    )


def slugify(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return text[:80] or "post-mortem-video"


def clean_markdown(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", text)
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"(?<!\w)[*_](.*?)[*_](?!\w)", r"\1", text)
    text = text.replace("`", "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def cue_summary(cue: str) -> str:
    cue = clean_markdown(cue)
    cue = re.sub(r"^(tone|voice|music):\s*", "", cue, flags=re.I)
    cue = cue.replace("…", "...")
    cue = re.sub(r"\s+", " ", cue).strip(" .")
    if not cue:
        return ""
    return textwrap.shorten(cue.upper(), width=68, placeholder="...")


def parse_script(path: Path) -> ParsedScript:
    raw = path.read_text(encoding="utf-8")
    title = "POST-MORTEM"
    subtitle = "The anatomy of how things fall apart."
    for line in raw.splitlines():
        if line.startswith("## "):
            title = clean_markdown(line[3:].strip())
            break
    first_h1 = next((clean_markdown(l[2:].strip()) for l in raw.splitlines() if l.startswith("# ")), "POST-MORTEM")
    if first_h1 and first_h1 != title:
        subtitle = first_h1

    chunks: list[Chunk] = []
    current_chapter = "INTRO"
    pending_cues: list[str] = []
    quote_buffer: list[str] = []

    def flush_quote() -> None:
        nonlocal quote_buffer, pending_cues
        if not quote_buffer:
            return
        paragraph = " ".join(part.strip() for part in quote_buffer).strip()
        quote_buffer = []
        if not paragraph:
            return
        cues = [cue_summary(c) for c in re.findall(r"\[([^\]]+)\]", paragraph)]
        cues = [c for c in cues if c]
        spoken = clean_markdown(re.sub(r"\[[^\]]+\]", " ", paragraph))
        if spoken:
            chunks.append(Chunk(text=spoken, chapter=current_chapter, cues=[*pending_cues, *cues]))
            pending_cues = []
        elif cues:
            pending_cues.extend(cues)

    for line in raw.splitlines():
        if line.startswith("### "):
            flush_quote()
            heading = clean_markdown(line[4:].strip())
            # Keep the useful part before the decorative runtime separator.
            current_chapter = re.split(r"\s+[·-]\s+\d", heading, maxsplit=1)[0].strip() or heading
            continue
        if line.startswith(">"):
            quoted = line[1:].strip()
            # A blank blockquote line is a real narration/cue boundary in SCRIPT.md.
            # Preserve that boundary so video renders can be chunked per line/scene
            # instead of per whole chapter.
            if quoted:
                quote_buffer.append(quoted)
            else:
                flush_quote()
        else:
            flush_quote()
    flush_quote()

    if not chunks:
        raise SystemExit(f"No blockquoted narration was found in {path}")
    return ParsedScript(title=title, subtitle=subtitle, chunks=chunks)


def ffprobe_duration(path: Path) -> float:
    result = run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        quiet=True,
    )
    return float(result.stdout.strip())


def synthesize_voice(parsed: ParsedScript, work: Path, *, speed: int, voice: str, pause: float) -> tuple[Path, float]:
    chunks_dir = work / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    tts = shutil.which("espeak-ng") or shutil.which("espeak")
    assert tts

    current = 0.0
    concat_lines: list[str] = []
    for i, chunk in enumerate(parsed.chunks):
        wav = chunks_dir / f"chunk_{i:04d}.wav"
        text_file = chunks_dir / f"chunk_{i:04d}.txt"
        text_file.write_text(chunk.text, encoding="utf-8")
        cmd = [tts, "-w", str(wav), "-s", str(speed), "-v", voice, "-f", str(text_file)]
        # espeak (older) may not support -f with the same behavior on every distro; fall back to argv text.
        try:
            run(cmd, quiet=True)
        except subprocess.CalledProcessError:
            run([tts, "-w", str(wav), "-s", str(speed), "-v", voice, chunk.text], quiet=True)
        chunk.wav = wav
        chunk.start = current
        chunk.speech_duration = ffprobe_duration(wav)
        chunk.end = current + chunk.speech_duration
        concat_lines.append(f"file '{wav.resolve().as_posix()}'")
        current = chunk.end
        if i != len(parsed.chunks) - 1:
            silence = chunks_dir / f"silence_{i:04d}.wav"
            run(
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "anullsrc=r=22050:cl=mono",
                    "-t",
                    f"{pause:.3f}",
                    str(silence),
                ],
                quiet=True,
            )
            concat_lines.append(f"file '{silence.resolve().as_posix()}'")
            current += pause

    concat_file = work / "voiceover.concat.txt"
    concat_file.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")
    voiceover = work / "voiceover.wav"
    run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-ar",
            "48000",
            "-ac",
            "2",
            "-filter:a",
            "loudnorm=I=-16:TP=-1.5:LRA=11",
            str(voiceover),
        ]
    )
    return voiceover, ffprobe_duration(voiceover)


def ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs == 100:
        s += 1
        cs = 0
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def ass_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "").replace("}", "").replace("\n", r"\N")


def wrap_ass(text: str, width: int, max_lines: int = 2) -> str:
    lines = textwrap.wrap(text, width=width, break_long_words=False, break_on_hyphens=False)
    if len(lines) > max_lines:
        kept = lines[: max_lines]
        kept[-1] = textwrap.shorten(" ".join(lines[max_lines - 1 :]), width=width, placeholder="...")
        lines = kept
    return r"\N".join(ass_escape(line) for line in lines)


def split_caption_groups(text: str, max_chars: int = 58, max_words: int = 10) -> list[str]:
    words = text.split()
    groups: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join([*current, word])
        if current and (len(candidate) > max_chars or len(current) >= max_words):
            groups.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        groups.append(" ".join(current))
    return groups


def write_ass_file(
    parsed: ParsedScript,
    work: Path,
    duration: float,
    *,
    window_start: float = 0.0,
    window_end: float | None = None,
    name: str = "visuals.ass",
) -> Path:
    """Write a clipped ASS file for captions + brand cards.

    Segment renders get local subtitle timestamps (window_start is subtracted)
    so libass never has to evaluate a full-episode timeline inside each short
    ffmpeg pass. Fonts are pinned to DejaVu and the subtitles filter is pointed
    at the matching TTF directory so punctuation in titles (dollars, em dashes,
    apostrophes, commas) renders predictably.
    """
    window_end = duration if window_end is None else min(duration, window_end)
    segment_duration = max(0.0, window_end - window_start)
    ass = work / name
    ass.parent.mkdir(parents=True, exist_ok=True)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {ASS_WIDTH}
PlayResY: {ASS_HEIGHT}
ScaledBorderAndShadow: yes
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Tiny,{ASS_MONO_FONT},18,&H00988F8A,&H000000FF,&HAA000000,&H00000000,0,0,0,0,100,100,1,0,1,2,0,7,34,34,28,1
Style: Title,{ASS_FONT},52,&H00EBF0F2,&H0023A6F5,&HAA000000,&H00000000,-1,0,0,0,100,100,0,0,1,3,1,5,66,66,66,1
Style: Amber,{ASS_FONT},38,&H0023A6F5,&H000000FF,&HAA000000,&H00000000,-1,0,0,0,100,100,1,0,1,2,0,5,66,66,66,1
Style: Callout,{ASS_MONO_FONT},23,&H00988F8A,&H0023A6F5,&HAA000000,&H770E0F12,-1,0,0,0,100,100,1,0,3,2,0,8,86,86,92,1
Style: Caption,{ASS_FONT},38,&H00EBF0F2,&H0023A6F5,&HCC000000,&H99000000,-1,0,0,0,100,100,0,0,1,4,1,2,100,100,48,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events: list[str] = []

    def add_event(layer: int, start: float, end: float, style: str, text: str) -> None:
        clipped_start = max(window_start, start)
        clipped_end = min(window_end, end)
        if clipped_end <= clipped_start:
            return
        events.append(
            f"Dialogue: {layer},{ass_time(clipped_start - window_start)},{ass_time(clipped_end - window_start)},"
            f"{style},,0,0,0,,{text}"
        )

    # Persistent brand/timecode-style labels.
    add_event(
        1,
        window_start,
        window_end,
        "Tiny",
        r"{\an7\pos(34,28)\c&H0023A6F5&\b1}POST-MORTEM{\c&H00988F8A&\b0}  //  AUTOPSY FILE",
    )
    add_event(
        1,
        window_start,
        window_end,
        "Tiny",
        r"{\an9\pos(1196,118)\c&H00988F8A&}VOICEOVER  //  CAPTIONS SYNCED",
    )
    # Opening title, clipped into only the segment(s) that overlap it.
    add_event(4, 0, min(8, duration), "Title", r"{\an5\pos(640,270)\fs58\c&H0023A6F5&}POST-MORTEM")
    add_event(
        4,
        1.2,
        min(9.5, duration),
        "Title",
        r"{\an5\pos(640,346)\fs34\c&H00EBF0F2&}" + wrap_ass(parsed.title, 31, max_lines=2),
    )
    add_event(
        4,
        2.2,
        min(9.5, duration),
        "Amber",
        r"{\an5\pos(640,414)\fs22\c&H00988F8A&}THE ANATOMY OF HOW THINGS FALL APART",
    )

    last_chapter = None
    for chunk in parsed.chunks:
        if chunk.chapter != last_chapter:
            last_chapter = chunk.chapter
            chapter_text = re.sub(r"\s*·.*$", "", chunk.chapter).strip().upper()
            if chunk.start > 0.1:
                add_event(
                    5,
                    chunk.start,
                    min(chunk.start + 5.2, duration),
                    "Amber",
                    r"{\an5\pos(640,246)\fs40\c&H0023A6F5&}" + wrap_ass(chapter_text, 34, max_lines=2),
                )
        # Production-direction callouts become subtle forensic visual cards.
        for cue in chunk.cues[:1]:
            if not cue:
                continue
            start = max(0, chunk.start + 0.15)
            end = min(duration, start + min(4.5, max(2.6, chunk.speech_duration)))
            add_event(
                3,
                start,
                end,
                "Callout",
                r"{\an8\pos(640,112)\fs21\c&H00988F8A&}" + wrap_ass("// " + cue, 56, max_lines=2),
            )

    for chunk in parsed.chunks:
        groups = split_caption_groups(chunk.text)
        total_words = max(1, len(chunk.text.split()))
        t = chunk.start
        for idx, group in enumerate(groups):
            words = len(group.split())
            seg_dur = max(0.75, chunk.speech_duration * words / total_words)
            end = min(chunk.end, t + seg_dur)
            if idx == len(groups) - 1:
                end = chunk.end
            text = wrap_ass(group, 40, max_lines=2)
            add_event(10, t, end, "Caption", text)
            t = end

    if segment_duration <= 0:
        raise SystemExit(f"Invalid subtitle segment window: {window_start:.3f}-{window_end:.3f}")
    ass.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return ass


def ffmpeg_sub_path(path: Path) -> str:
    # Escape for ffmpeg filter filename arguments.
    s = path.resolve().as_posix()
    return s.replace("\\", "\\\\").replace(":", r"\:").replace("'", r"\'")


def subtitles_filter(path: Path) -> str:
    arg = f"filename='{ffmpeg_sub_path(path)}'"
    if FONT_DIR.exists():
        arg += f":fontsdir='{ffmpeg_sub_path(FONT_DIR)}'"
    return f"subtitles={arg}"


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.removeprefix("0x").removeprefix("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def blend(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return tuple(round(a[i] * (1 - t) + b[i] * t) for i in range(3))  # type: ignore[return-value]


def put_pixel(rows: list[bytearray], x: int, y: int, color: tuple[int, int, int], alpha: float = 1.0) -> None:
    if y < 0 or y >= len(rows) or x < 0 or x * 3 + 2 >= len(rows[y]):
        return
    idx = x * 3
    if alpha >= 1:
        rows[y][idx : idx + 3] = bytes(color)
        return
    rows[y][idx] = round(rows[y][idx] * (1 - alpha) + color[0] * alpha)
    rows[y][idx + 1] = round(rows[y][idx + 1] * (1 - alpha) + color[1] * alpha)
    rows[y][idx + 2] = round(rows[y][idx + 2] * (1 - alpha) + color[2] * alpha)


def draw_line(rows: list[bytearray], p0: tuple[int, int], p1: tuple[int, int], color: tuple[int, int, int], *, width: int = 1, alpha: float = 1.0) -> None:
    x0, y0 = p0
    x1, y1 = p1
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    radius = max(0, width // 2)
    while True:
        for oy in range(-radius, radius + 1):
            for ox in range(-radius, radius + 1):
                put_pixel(rows, x0 + ox, y0 + oy, color, alpha)
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def draw_rect(rows: list[bytearray], x: int, y: int, w: int, h: int, color: tuple[int, int, int], *, alpha: float = 1.0) -> None:
    for yy in range(max(0, y), min(len(rows), y + h)):
        row_width = len(rows[yy]) // 3
        for xx in range(max(0, x), min(row_width, x + w)):
            put_pixel(rows, xx, yy, color, alpha)


def write_background_card(path: Path, idx: int, *, width: int = 1280, height: int = 720) -> None:
    charcoal = hex_to_rgb("0E0F12")
    slate = hex_to_rgb("16181D")
    amber = hex_to_rgb("F5A623")
    ash = hex_to_rgb("8A8F98")
    red = hex_to_rgb("E5484D")
    blue = (42, 78, 116)
    green = (32, 86, 72)
    violet = (63, 49, 92)
    accents = [amber, red, blue, green, violet, amber, red]
    accent = accents[idx % len(accents)]
    bg_b = blend(slate, accent, 0.05 + (idx % 3) * 0.025)

    rows: list[bytearray] = []
    for y in range(height):
        t = y / max(1, height - 1)
        row = bytearray()
        for x in range(width):
            u = x / max(1, width - 1)
            diagonal = ((x + idx * 97) / width + (y / height) * 0.8) % 1.0
            base = blend(charcoal, bg_b, 0.18 + 0.42 * t + 0.10 * u)
            if diagonal < 0.035:
                base = blend(base, accent, 0.10)
            if x < width * 0.26 and y > height * 0.16:
                base = blend(base, accent, 0.035 + idx * 0.004)
            row.extend(base)
        rows.append(row)

    # Blueprint grid and section-specific bars: static inside each card, cheap to encode.
    for x in range((idx * 23) % 80, width, 80):
        draw_line(rows, (x, 0), (x, height - 1), ash, alpha=0.11)
    for y in range((idx * 17) % 72, height, 72):
        draw_line(rows, (0, y), (width - 1, y), ash, alpha=0.10)
    draw_rect(rows, 0, 0, width, round(height * 0.11), (0, 0, 0), alpha=0.20)
    draw_rect(rows, 0, round(height * 0.86), width, round(height * 0.14), (0, 0, 0), alpha=0.22)
    draw_rect(rows, round(width * 0.05), round(height * (0.18 + 0.045 * (idx % 4))), round(width * (0.38 + 0.035 * (idx % 3))), 5, accent, alpha=0.50)
    draw_rect(rows, round(width * (0.68 - 0.035 * (idx % 4))), round(height * 0.18), 5, round(height * 0.58), accent, alpha=0.28)

    # POST-MORTEM motif: EKG line that varies by card.
    y_mid = round(height * (0.55 + (idx % 3 - 1) * 0.035))
    pts = [
        (round(width * 0.08), y_mid),
        (round(width * 0.24), y_mid),
        (round(width * 0.28), y_mid - 28 - idx * 2),
        (round(width * 0.31), y_mid + 42 + idx * 2),
        (round(width * 0.35), y_mid - 14),
        (round(width * 0.44), y_mid),
        (round(width * 0.58), y_mid),
        (round(width * 0.68), y_mid + 70 + idx * 4),
        (round(width * 0.82), y_mid + 70 + idx * 4),
    ]
    for a, b in zip(pts, pts[1:]):
        draw_line(rows, a, b, accent, width=5, alpha=0.62)
    for a, b in zip(pts, pts[1:]):
        draw_line(rows, a, b, amber, width=2, alpha=0.75)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        f.write(f"P6\n{width} {height}\n255\n".encode("ascii"))
        for row in rows:
            f.write(row)


def make_background_cards(work: Path) -> list[Path]:
    cards_dir = work / "backgrounds"
    cards_dir.mkdir(parents=True, exist_ok=True)
    cards: list[Path] = []
    if BACKGROUND_IMAGE.exists():
        cards.append(BACKGROUND_IMAGE)
    for idx in range(BACKGROUND_CARD_COUNT - len(cards)):
        card = cards_dir / f"plate_{idx + 1:02d}.ppm"
        write_background_card(card, idx)
        cards.append(card)
    return cards


def run_ffmpeg_with_progress(cmd: list[str], *, duration: float, timeout: float = FFMPEG_TIMEOUT_SECONDS) -> None:
    """Run ffmpeg while emitting progress and enforcing a hard timeout."""
    print("$", " ".join(str(c) for c in cmd) + f"  # timeout={timeout:.0f}s")
    started = time.monotonic()
    last_emit = 0.0
    out_time = 0.0
    speed = "?"
    tail: deque[str] = deque(maxlen=60)
    proc = subprocess.Popen(
        cmd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
    )
    assert proc.stdout is not None

    def consume(line: str) -> None:
        nonlocal out_time, speed, last_emit
        line = line.strip()
        if not line:
            return
        tail.append(line)
        if line.startswith("out_time_ms=") or line.startswith("out_time_us="):
            try:
                out_time = int(line.split("=", 1)[1]) / 1_000_000
            except ValueError:
                pass
        elif line.startswith("out_time="):
            stamp = line.split("=", 1)[1]
            try:
                h, m, s = stamp.split(":")
                out_time = int(h) * 3600 + int(m) * 60 + float(s)
            except ValueError:
                pass
        elif line.startswith("speed="):
            speed = line.split("=", 1)[1].strip() or speed
        elif line.startswith("progress="):
            now = time.monotonic()
            if line == "progress=end" or now - last_emit >= 9.0:
                pct = min(100.0, out_time / max(duration, 0.001) * 100)
                elapsed = now - started
                print(
                    f"ffmpeg progress: {out_time:6.1f}s / {duration:.1f}s ({pct:5.1f}%), speed={speed}, elapsed={elapsed:.0f}s",
                    flush=True,
                )
                last_emit = now

    try:
        while True:
            if time.monotonic() - started > timeout:
                proc.kill()
                leftover, _ = proc.communicate(timeout=5)
                for line in leftover.splitlines():
                    consume(line)
                raise subprocess.TimeoutExpired(cmd, timeout, output="\n".join(tail))
            ready, _, _ = select.select([proc.stdout], [], [], 1.0)
            if ready:
                raw = proc.stdout.readline()
                if raw:
                    consume(raw)
            rc = proc.poll()
            if rc is not None:
                for raw in proc.stdout:
                    consume(raw)
                if rc != 0:
                    raise subprocess.CalledProcessError(rc, cmd, output="\n".join(tail))
                return
    finally:
        if proc.poll() is None:
            proc.kill()


def plan_render_segments(
    parsed: ParsedScript,
    duration: float,
    *,
    target: float = SEGMENT_TARGET_SECONDS,
    max_seconds: float = SEGMENT_MAX_SECONDS,
) -> list[RenderSegment]:
    """Group narration chunks into short render passes on silence/chunk boundaries."""
    if not parsed.chunks:
        raise SystemExit("No narration chunks available for segment planning")
    segments: list[RenderSegment] = []
    current_chunks: list[Chunk] = []
    current_start = parsed.chunks[0].start

    for idx, chunk in enumerate(parsed.chunks):
        if not current_chunks:
            current_start = chunk.start
        current_chunks.append(chunk)
        boundary = parsed.chunks[idx + 1].start if idx + 1 < len(parsed.chunks) else duration
        segment_duration = boundary - current_start
        should_cut = idx + 1 < len(parsed.chunks) and (segment_duration >= target or segment_duration >= max_seconds)
        if should_cut:
            segments.append(RenderSegment(len(segments), current_start, boundary, current_chunks))
            current_chunks = []

    if current_chunks:
        segments.append(RenderSegment(len(segments), current_start, duration, current_chunks))

    too_long = [seg for seg in segments if seg.duration > max_seconds + 8]
    if too_long:
        details = ", ".join(f"#{seg.index + 1}={seg.duration:.1f}s" for seg in too_long)
        raise SystemExit(f"Render segment(s) too long for the 90s watchdog guard: {details}")
    return segments


def segment_cards(cards: list[Path], segment_index: int) -> list[Path]:
    count = min(SEGMENT_CARD_COUNT, len(cards))
    return [cards[(segment_index + i) % len(cards)] for i in range(count)]


def render_video_segment(
    voiceover: Path,
    visuals_ass: Path,
    output: Path,
    *,
    segment: RenderSegment,
    fps: int,
    cards: list[Path],
) -> None:
    # Each segment repeats the cheap visual recipe: pre-rendered brand stills,
    # slow zoompan Ken-Burns motion, and short xfade transitions. There is no
    # per-frame animated drawbox work in the hot render path.
    if len(cards) < 2:
        raise SystemExit("Need at least two background cards for an evolving visual track")
    duration = segment.duration
    fade = 0.75 if duration >= 10 else 0.35
    fade = min(fade, max(0.1, duration / max(2 * len(cards), 1)))
    clip_duration = (duration + fade * (len(cards) - 1)) / len(cards)
    top_bar = round(HEIGHT * 78 / 720)
    lower_bar = round(HEIGHT * 102 / 720)

    filters: list[str] = []
    for idx in range(len(cards)):
        motion_seed = segment.index * 3 + idx
        # Alternate pan direction per plate so cuts/crossfades are visibly different.
        x_expr = "iw/2-iw/zoom/2+sin(on/170+%d)*64" % motion_seed
        y_expr = "ih/2-ih/zoom/2+cos(on/205+%d)*38" % (motion_seed * 2)
        zoom_expr = "1.06+0.035*sin(on/360+%d)" % motion_seed
        filters.append(
            f"[{idx}:v]scale=2304:1296:force_original_aspect_ratio=increase,crop=2304:1296,"
            f"zoompan=z='{zoom_expr}':"
            f"x='max(0,min(iw-iw/zoom,{x_expr}))':"
            f"y='max(0,min(ih-ih/zoom,{y_expr}))':"
            f"d=1:fps={fps}:s={WIDTH}x{HEIGHT},"
            f"trim=duration={clip_duration:.3f},setpts=PTS-STARTPTS[bg{idx}]"
        )

    current = "bg0"
    for idx in range(1, len(cards)):
        out = f"xf{idx}"
        offset = max(0.0, (clip_duration - fade) * idx)
        filters.append(
            f"[{current}][bg{idx}]xfade=transition=fade:duration={fade:.3f}:offset={offset:.3f},format=yuv420p[{out}]"
        )
        current = out

    filters.append(
        f"[{current}]trim=duration={duration:.3f},setpts=PTS-STARTPTS,"
        f"drawbox=x=0:y=0:w=iw:h={top_bar}:color=black@0.42:t=fill,"
        f"drawbox=x=0:y=ih-{lower_bar}:w=iw:h={lower_bar}:color=black@0.40:t=fill,"
        f"drawbox=x=0:y={round(HEIGHT * 70 / 720)}:w=iw:h=3:color={AMBER}@0.55:t=fill,"
        f"drawbox=x=0:y={round(HEIGHT * 620 / 720)}:w=iw:h=3:color={AMBER}@0.34:t=fill,"
        f"drawbox=x={round(WIDTH * 40 / 1280)}:y={round(HEIGHT * 118 / 720)}:w={round(WIDTH * 1200 / 1280)}:h=2:color={ASH}@0.20:t=fill,"
        f"{subtitles_filter(visuals_ass)}[v]"
    )
    voice_idx = len(cards)
    bed_idx = len(cards) + 1
    filters.append(
        f"[{voice_idx}:a]atrim=0:{duration:.3f},asetpts=PTS-STARTPTS,volume=1.00[vo];"
        f"[{bed_idx}:a]atrim=0:{duration:.3f},asetpts=PTS-STARTPTS,volume=0.025[bed];"
        "[vo][bed]amix=inputs=2:duration=first:dropout_transition=2,alimiter=limit=0.96[a]"
    )
    filter_complex = ";".join(filters)

    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-hide_banner", "-stats_period", "10", "-progress", "pipe:1"]
    for card in cards:
        cmd.extend(["-loop", "1", "-framerate", str(fps), "-t", f"{clip_duration:.3f}", "-i", str(card)])
    cmd.extend(
        [
            "-ss",
            f"{segment.start:.3f}",
            "-t",
            f"{duration:.3f}",
            "-i",
            str(voiceover),
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=54:sample_rate=48000:duration={duration:.3f}",
            "-filter_complex",
            filter_complex,
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "24",
            "-profile:v",
            "high",
            "-level:v",
            "4.1",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(fps),
            "-g",
            str(fps * 2),
            "-keyint_min",
            str(fps * 2),
            "-sc_threshold",
            "0",
            "-c:a",
            "aac",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            "-shortest",
            str(output),
        ]
    )
    run_ffmpeg_with_progress(cmd, duration=duration, timeout=FFMPEG_TIMEOUT_SECONDS)


def rendered_segment_is_valid(path: Path, *, expected_duration: float, fps: int) -> bool:
    """Return True only for complete, ffprobe-readable segment MP4s.

    A watchdog-killed ffmpeg can leave behind a non-zero-size .mp4 with no
    moov atom. Resumes must not trust file size; they only skip chunks that
    ffprobe can read and whose stream parameters match the concat recipe.
    """
    if not path.exists():
        return False
    try:
        video = run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height,r_frame_rate",
                "-of",
                "csv=p=0",
                str(path),
            ],
            quiet=True,
        ).stdout.strip()
        audio = run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=codec_name",
                "-of",
                "csv=p=0",
                str(path),
            ],
            quiet=True,
        ).stdout.strip()
        duration = ffprobe_duration(path)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError):
        return False
    rate = video.split(",")[-1] if video else ""
    return (
        video.startswith(f"{WIDTH},{HEIGHT}")
        and rate == f"{fps}/1"
        and bool(audio)
        and abs(duration - expected_duration) <= 1.25
    )


def concat_segments(segment_files: list[Path], output: Path) -> None:
    concat_file = output.parent / "segments.concat.txt"
    concat_file.write_text("".join(f"file '{path.resolve().as_posix()}'\n" for path in segment_files), encoding="utf-8")
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        str(output),
    ]
    run(cmd, timeout=FFMPEG_TIMEOUT_SECONDS)


def render_video(
    parsed: ParsedScript,
    voiceover: Path,
    work: Path,
    output: Path,
    *,
    duration: float,
    fps: int,
    cards: list[Path],
) -> None:
    segments = plan_render_segments(parsed, duration)
    segment_dir = work / "segments"
    segment_dir.mkdir(parents=True, exist_ok=True)
    segment_files: list[Path] = []
    print(
        f"Chunked render plan: {len(segments)} segments, "
        f"{min(seg.duration for seg in segments):.1f}-{max(seg.duration for seg in segments):.1f}s each, "
        f"timeout={FFMPEG_TIMEOUT_SECONDS}s per ffmpeg call"
    )
    for segment in segments:
        ass = write_ass_file(
            parsed,
            segment_dir,
            duration,
            window_start=segment.start,
            window_end=segment.end,
            name=f"segment_{segment.index:03d}.ass",
        )
        segment_output = segment_dir / f"segment_{segment.index:03d}.mp4"
        cards_for_segment = segment_cards(cards, segment.index)
        if rendered_segment_is_valid(segment_output, expected_duration=segment.duration, fps=fps):
            print(
                f"Skipping valid segment {segment.index + 1}/{len(segments)} "
                f"({segment.start:.1f}-{segment.end:.1f}s, {segment.duration:.1f}s; ffprobe OK)",
                flush=True,
            )
            segment_files.append(segment_output)
            continue
        print(
            f"Rendering segment {segment.index + 1}/{len(segments)} "
            f"({segment.start:.1f}-{segment.end:.1f}s, {segment.duration:.1f}s, {len(segment.chunks)} narration chunks, "
            f"{len(cards_for_segment)} zoompan plates)"
        )
        started = time.monotonic()
        render_video_segment(
            voiceover,
            ass,
            segment_output,
            segment=segment,
            fps=fps,
            cards=cards_for_segment,
        )
        elapsed = time.monotonic() - started
        if not rendered_segment_is_valid(segment_output, expected_duration=segment.duration, fps=fps):
            raise SystemExit(f"Rendered segment failed ffprobe validation: {segment_output}")
        print(f"rendered segment {segment.index + 1}/{len(segments)} in {elapsed:.0f}s", flush=True)
        segment_files.append(segment_output)

    concat_start = time.monotonic()
    print(f"Concatenating {len(segment_files)} chunks with ffmpeg concat demuxer (-c copy)")
    output.parent.mkdir(parents=True, exist_ok=True)
    concat_segments(segment_files, output)
    print(f"concat complete in {time.monotonic() - concat_start:.1f}s", flush=True)


def verify_output(path: Path, *, width: int = WIDTH, height: int = HEIGHT, expected_duration: float | None = None) -> None:
    result = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,r_frame_rate",
            "-of",
            "csv=p=0",
            str(path),
        ],
        quiet=True,
    )
    audio = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_name",
            "-of",
            "csv=p=0",
            str(path),
        ],
        quiet=True,
    ).stdout.strip()
    duration = ffprobe_duration(path)
    info = result.stdout.strip()
    rate = info.split(",")[-1] if info else ""
    duration_ok = expected_duration is None or abs(duration - expected_duration) <= 2.5
    if not info.startswith(f"{width},{height}") or rate != "30/1" or not audio or duration <= 1 or not duration_ok:
        raise SystemExit(
            f"Rendered file failed sanity check: video={info!r} audio={audio!r} "
            f"duration={duration:.2f}s expected={expected_duration}"
        )
    expected = f", expected={expected_duration:.2f}s" if expected_duration is not None else ""
    print(f"OK: {path} ({duration/60:.1f} min, {info}, audio={audio}, duration={duration:.2f}s{expected})")


def trim_for_smoke(parsed: ParsedScript, *, max_words: int = 60) -> ParsedScript:
    """Return a 20-30s-ish cut for validating the full render path quickly."""
    chunks: list[Chunk] = []
    remaining = max_words
    for chunk in parsed.chunks:
        if remaining <= 0:
            break
        words = chunk.text.split()
        if not words:
            continue
        take = min(len(words), remaining)
        text = " ".join(words[:take])
        if take < len(words):
            text = text.rstrip(" .,;:") + "."
        chunks.append(Chunk(text=text, chapter=chunk.chapter, cues=chunk.cues[:1]))
        remaining -= take
    if not chunks:
        raise SystemExit("Smoke render could not create a short narration cut")
    return ParsedScript(title=parsed.title, subtitle=parsed.subtitle, chunks=chunks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a POST-MORTEM faceless MP4 from SCRIPT.md")
    parser.add_argument("script", type=Path, help="Markdown script with blockquoted narration")
    parser.add_argument("-o", "--output", type=Path, help="Output .mp4 path (default: renders/<script-title>.mp4)")
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_WORK, help="Intermediate build directory")
    parser.add_argument("--speed", type=int, default=145, help="TTS speed in words per minute-ish (espeak scale)")
    parser.add_argument("--voice", default="en-us+m3", help="espeak/espeak-ng voice name")
    parser.add_argument("--pause", type=float, default=0.34, help="Seconds of silence between narration paragraphs")
    parser.add_argument("--fps", type=int, default=30, help="Output framerate")
    parser.add_argument("--smoke", action="store_true", help="Render a 20-30 second cut for fast pipeline validation")
    parser.add_argument("--smoke-words", type=int, default=60, help="Narration words to include in --smoke mode")
    parser.add_argument("--no-auto-install", action="store_true", help="Do not attempt apt-get install for missing tools")
    parser.add_argument("--keep-work", action="store_true", help="Keep previous work directory instead of replacing slug subdir")
    args = parser.parse_args(argv)

    script = args.script.resolve()
    if not script.exists():
        raise SystemExit(f"Script not found: {script}")

    check_or_install_tools(auto_install=not args.no_auto_install)
    parsed = parse_script(script)
    if args.smoke:
        parsed = trim_for_smoke(parsed, max_words=args.smoke_words)
    slug = slugify(parsed.title)
    if args.output:
        output = args.output.resolve()
    else:
        suffix = "-smoke" if args.smoke else ""
        output = (DEFAULT_OUT / f"{slug}{suffix}.mp4").resolve()
    work = (args.work_dir / slug).resolve()
    if work.exists() and not args.keep_work:
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)

    mode = "smoke" if args.smoke else "full"
    print(f"Parsed {len(parsed.chunks)} narration chunks from {script.name} ({mode} render, {WIDTH}x{HEIGHT})")
    voiceover, duration = synthesize_voice(parsed, work, speed=args.speed, voice=args.voice, pause=args.pause)
    cards = make_background_cards(work)
    render_video(parsed, voiceover, work, output, duration=duration, fps=args.fps, cards=cards)
    verify_output(output, expected_duration=duration)
    print(f"Reproducible output: {output.relative_to(ROOT) if output.is_relative_to(ROOT) else output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
