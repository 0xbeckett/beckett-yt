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


def run(cmd: list[str], *, quiet: bool = False) -> subprocess.CompletedProcess[str]:
    if not quiet:
        print("$", " ".join(str(c) for c in cmd))
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)


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
            quote_buffer.append(line[1:].strip())
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


def write_ass_file(parsed: ParsedScript, work: Path, duration: float) -> Path:
    """Write one combined ASS file for captions + brand cards.

    Keeping this to a single libass burn is much faster than stacking separate
    subtitle filters for captions and cards.
    """
    ass = work / "visuals.ass"
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {ASS_WIDTH}
PlayResY: {ASS_HEIGHT}
ScaledBorderAndShadow: yes
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Tiny,Noto Sans Mono,18,&H00988F8A,&H000000FF,&HAA000000,&H00000000,0,0,0,0,100,100,1,0,1,2,0,7,34,34,28,1
Style: Title,Noto Sans,52,&H00EBF0F2,&H0023A6F5,&HAA000000,&H00000000,-1,0,0,0,100,100,0,0,1,3,1,5,66,66,66,1
Style: Amber,Noto Sans,38,&H0023A6F5,&H000000FF,&HAA000000,&H00000000,-1,0,0,0,100,100,1,0,1,2,0,5,66,66,66,1
Style: Callout,Noto Sans Mono,23,&H00988F8A,&H0023A6F5,&HAA000000,&H770E0F12,-1,0,0,0,100,100,1,0,3,2,0,8,86,86,92,1
Style: Caption,Noto Sans,38,&H00EBF0F2,&H0023A6F5,&HCC000000,&H99000000,-1,0,0,0,100,100,0,0,1,4,1,2,100,100,48,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events: list[str] = []
    # Persistent brand/timecode-style labels.
    events.append(
        f"Dialogue: 1,{ass_time(0)},{ass_time(duration)},Tiny,,0,0,0,,"
        + r"{\an7\pos(34,28)\c&H0023A6F5&\b1}POST-MORTEM{\c&H00988F8A&\b0}  //  AUTOPSY FILE"
    )
    events.append(
        f"Dialogue: 1,{ass_time(0)},{ass_time(duration)},Tiny,,0,0,0,,"
        + r"{\an9\pos(1196,118)\c&H00988F8A&}VOICEOVER  //  CAPTIONS SYNCED"
    )
    # Opening title.
    events.append(
        f"Dialogue: 4,{ass_time(0)},{ass_time(min(8, duration))},Title,,0,0,0,,"
        + r"{\an5\pos(640,270)\fs58\c&H0023A6F5&}POST-MORTEM"
    )
    events.append(
        f"Dialogue: 4,{ass_time(1.2)},{ass_time(min(9.5, duration))},Title,,0,0,0,,"
        + r"{\an5\pos(640,346)\fs34\c&H00EBF0F2&}"
        + wrap_ass(parsed.title, 31, max_lines=2)
    )
    events.append(
        f"Dialogue: 4,{ass_time(2.2)},{ass_time(min(9.5, duration))},Amber,,0,0,0,,"
        + r"{\an5\pos(640,414)\fs22\c&H00988F8A&}THE ANATOMY OF HOW THINGS FALL APART"
    )

    last_chapter = None
    for chunk in parsed.chunks:
        if chunk.chapter != last_chapter:
            last_chapter = chunk.chapter
            chapter_text = re.sub(r"\s*·.*$", "", chunk.chapter).strip().upper()
            if chunk.start > 0.1:
                events.append(
                    f"Dialogue: 5,{ass_time(chunk.start)},{ass_time(min(chunk.start + 5.2, duration))},Amber,,0,0,0,,"
                    + r"{\an5\pos(640,246)\fs40\c&H0023A6F5&}"
                    + wrap_ass(chapter_text, 34, max_lines=2)
                )
        # Production-direction callouts become subtle forensic visual cards.
        for cue in chunk.cues[:1]:
            if not cue:
                continue
            start = max(0, chunk.start + 0.15)
            end = min(duration, start + min(4.5, max(2.6, chunk.speech_duration)))
            events.append(
                f"Dialogue: 3,{ass_time(start)},{ass_time(end)},Callout,,0,0,0,,"
                + r"{\an8\pos(640,112)\fs21\c&H00988F8A&}"
                + wrap_ass("// " + cue, 56, max_lines=2)
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
            events.append(f"Dialogue: 10,{ass_time(t)},{ass_time(end)},Caption,,0,0,0,,{text}")
            t = end

    ass.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return ass


def ffmpeg_sub_path(path: Path) -> str:
    # Escape for ffmpeg's subtitles filter filename argument.
    s = path.resolve().as_posix()
    return s.replace("\\", "\\\\").replace(":", r"\:").replace("'", r"\'")


def run_ffmpeg_with_progress(cmd: list[str], *, duration: float) -> None:
    """Run ffmpeg while emitting a heartbeat from -progress output."""
    print("$", " ".join(str(c) for c in cmd))
    started = time.monotonic()
    last_emit = 0.0
    out_time = 0.0
    speed = "?"
    tail: deque[str] = deque(maxlen=40)
    proc = subprocess.Popen(
        cmd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
    )
    assert proc.stdout is not None
    for raw in proc.stdout:
        line = raw.strip()
        if not line:
            continue
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
                print(f"ffmpeg progress: {out_time:6.1f}s / {duration:.1f}s ({pct:5.1f}%), speed={speed}, elapsed={elapsed:.0f}s", flush=True)
                last_emit = now
    rc = proc.wait()
    if rc != 0:
        raise subprocess.CalledProcessError(rc, cmd, output="\n".join(tail))


def render_video(
    voiceover: Path,
    visuals_ass: Path,
    output: Path,
    *,
    duration: float,
    fps: int,
) -> None:
    # Visible motion comes from zoompan on a still brand image, not from animated
    # drawbox expressions over the whole timeline (those stalled 1080p renders).
    if not BACKGROUND_IMAGE.exists():
        raise SystemExit(f"Missing background image: {BACKGROUND_IMAGE}")
    top_bar = round(HEIGHT * 78 / 720)
    lower_bar = round(HEIGHT * 102 / 720)
    filter_complex = (
        f"[0:v]scale=2304:1536,"
        f"zoompan=z='1.12+0.04*sin(on/480)':"
        f"x='max(0,min(iw-iw/zoom,iw/2-iw/zoom/2+sin(on/180)*70))':"
        f"y='max(0,min(ih-ih/zoom,ih/2-ih/zoom/2+cos(on/210)*45))':"
        f"d=1:fps={fps}:s={WIDTH}x{HEIGHT},"
        f"trim=duration={duration:.3f},setpts=PTS-STARTPTS,"
        f"drawbox=x=0:y=0:w=iw:h={top_bar}:color=black@0.42:t=fill,"
        f"drawbox=x=0:y=ih-{lower_bar}:w=iw:h={lower_bar}:color=black@0.40:t=fill,"
        f"drawbox=x=0:y={round(HEIGHT * 70 / 720)}:w=iw:h=3:color={AMBER}@0.55:t=fill,"
        f"drawbox=x=0:y={round(HEIGHT * 620 / 720)}:w=iw:h=3:color={AMBER}@0.34:t=fill,"
        f"drawbox=x={round(WIDTH * 40 / 1280)}:y={round(HEIGHT * 118 / 720)}:w={round(WIDTH * 1200 / 1280)}:h=2:color={ASH}@0.20:t=fill,"
        f"subtitles='{ffmpeg_sub_path(visuals_ass)}'[v];"
        "[1:a]volume=1.00[vo];[2:a]volume=0.025[bed];"
        "[vo][bed]amix=inputs=2:duration=first:dropout_transition=2,alimiter=limit=0.96[a]"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-stats_period",
        "10",
        "-progress",
        "pipe:1",
        "-loop",
        "1",
        "-framerate",
        str(fps),
        "-t",
        f"{duration:.3f}",
        "-i",
        str(BACKGROUND_IMAGE),
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
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(fps),
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-movflags",
        "+faststart",
        "-shortest",
        str(output),
    ]
    run_ffmpeg_with_progress(cmd, duration=duration)


def verify_output(path: Path, *, width: int = WIDTH, height: int = HEIGHT) -> None:
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
    if not info.startswith(f"{width},{height}") or not audio or duration <= 1:
        raise SystemExit(f"Rendered file failed sanity check: video={info!r} audio={audio!r} duration={duration:.2f}")
    print(f"OK: {path} ({duration/60:.1f} min, {info}, audio={audio})")


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
    visuals_ass = write_ass_file(parsed, work, duration)
    render_video(voiceover, visuals_ass, output, duration=duration, fps=args.fps)
    verify_output(output)
    print(f"Reproducible output: {output.relative_to(ROOT) if output.is_relative_to(ROOT) else output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
