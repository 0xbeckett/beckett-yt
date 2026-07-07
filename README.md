# POST-MORTEM

**A faceless, AI-run YouTube channel — designed, branded, and scripted by Beckett.**

> *The anatomy of how things fall apart.*

This repo is the complete concept + asset pack for a faceless YouTube channel that
one AI can run on autopilot: AI voiceover, no face, no live footage, one repeatable
episode formula. It now includes the production engine that turns a script into a
finished faceless MP4 with local TTS, synced captions, branding, and ffmpeg render.

---

## Render pipeline: script → voiceover → MP4

Single-command local render, no cloud API key required:

```bash
python3 generate.py --smoke SCRIPT.md   # 20-30s validation render, finishes quickly
python3 generate.py SCRIPT.md           # full first episode render
```

Outputs go to `renders/` and intermediates go to `build/` (both gitignored). The
full render produces a 1920×1080/30fps MP4 with espeak/espeak-ng narration, synced
burned-in captions, POST-MORTEM branding, subtle grid/scanline motion, audio bed,
AAC audio, and a faststart moov atom. The ffmpeg step prints heartbeat progress about
every 10 seconds and the script runs `ffprobe` at the end to verify duration plus
video/audio streams.

Dependencies: `ffmpeg`, `ffprobe`, and `espeak-ng`/`espeak`. If they are missing on a
sudo + apt system, `generate.py` attempts a non-interactive install; use
`--no-auto-install` to disable that.

## ⚠️ Scope note (read this first)

This repo delivers the concept, brand assets, first script, and local video renderer —
**not a live YouTube upload**. Creating the Google/YouTube account and publishing
videos requires interactive Google login/verification credentials, so account creation
and upload remain out of scope. Everything before the upload button is reproducible
here.

---

## The pick — niche & format

**Niche: forensic breakdowns of famous failures.** Engineering disasters, corporate
collapses, product flops, infrastructure meltdowns, financial blowups. Every episode
takes one real failure and reconstructs *exactly how it happened* and *why*.

**Why this niche:**
1. **Bottomless, evergreen topic well.** History is an endless supply of failures —
   the channel never runs out and old videos never expire. Perfect for autopilot churn.
2. **High RPM.** The audience skews tech / engineering / business / finance — the
   most advertiser-friendly demographics on YouTube. The same view is worth several
   times a gaming or vlog view.
3. **Retention is built into the structure.** A failure is a mystery with a known
   body but an unknown cause. "How did this happen?" is the strongest hook on the
   platform, and it's baked into every single episode.
4. **Genuinely faceless.** No face, no live shooting. Everything is archival-style
   stills, diagrams, schematics, charts, and AI-generated visuals over an AI voice.
5. **Repeatable formula.** Five fixed beats (below). The AI fills in a new failure
   each week — the shape never changes, so production is a template, not a fresh
   creative problem every time.

**Format:** 8–12 minute single-narrator documentary. Cold-open hook → reconstruction →
the moment of collapse → the autopsy (root cause) → the lesson. Amber-on-charcoal
motion graphics, EKG-flatline motif, monospace data callouts.

---

## Name & positioning

- **Channel name:** **POST-MORTEM**
- **Handle:** `@postmortem` (fallbacks: `@postmortemchannel`, `@thepostmortem`)
- **Tagline / positioning:** *The anatomy of how things fall apart.*
- **One-liner (channel description):** "We autopsy history's biggest failures — the
  disasters, collapses, and billion-dollar mistakes — and find the exact moment it
  all went wrong. New body on the table every week."

The name does triple duty: it's a medical autopsy (we dissect a dead thing), a project
retrospective ("post-mortem" is literally what engineers call a failure review), and a
promise of the format (we only show up *after* it's already broken).

---

## Branding

All assets live in [`assets/`](assets/). Palette and rules in
[`BRAND.md`](BRAND.md).

| Asset | File | Use |
|---|---|---|
| Avatar / logo | `assets/avatar.png` | Channel profile picture (1024×1024, square-safe) |
| Banner | `assets/banner.png` | Channel art / header (2560×1440 safe area aware) |
| Thumbnail template | `assets/thumbnail-template.png` | Reference style for every episode thumbnail |

**Core visual identity:** deep charcoal-black (`#0E0F12`) canvas, a single warm amber
accent (`#F5A623`), off-white type, faint blueprint grid, and the signature motif — a
heartbeat **EKG line that flatlines and then breaks into a downward crash**. It reads
"post-mortem" and "collapse" in one mark, and it's simple enough to work at avatar size.

**Thumbnail formula** (see [`BRAND.md`](BRAND.md) for the full spec): big punchy
off-white headline with the single most shocking word in amber, a small "POST-MORTEM"
corner tag, a desaturated dramatic image of the failure on the right third, and the
EKG-crash line along one edge. Consistency across thumbnails is the channel's shelf
recognition.

---

## First video

- Full script, timed and in the channel voice: [`SCRIPT.md`](SCRIPT.md)
- Episode: **"The $370 Million Bug — How One Line of Code Destroyed a Rocket"**
  (the Ariane 5 Flight 501 disaster).

The script is written to be read aloud by an AI voice: short sentences, deliberate
pauses marked, no visual-only jokes, with a parallel beat sheet describing what's on
screen at each moment.

---

## Content plan

First five episodes + the repeatable formula: [`CONTENT-PLAN.md`](CONTENT-PLAN.md).

---

## Files in this repo

```
README.md            ← you are here
generate.py          ← one-command local TTS + captions + ffmpeg MP4 renderer
BRAND.md             ← palette, type, logo rules, thumbnail spec
SCRIPT.md            ← full first-video script (voiceover-ready) + beat sheet
CONTENT-PLAN.md      ← first 5 episodes + the repeatable formula
assets/
  avatar.png         ← channel logo / profile picture
  banner.png         ← channel banner art
  thumbnail-template.png ← thumbnail style reference
```
