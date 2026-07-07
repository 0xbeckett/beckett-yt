# POST-MORTEM — Brand Guide

The whole point of a faceless channel is that the *brand* is the face. These rules keep
every thumbnail, intro, and lower-third recognizably POST-MORTEM so the channel builds
shelf recognition even though there's no host.

---

## Positioning

- **Name:** POST-MORTEM (always uppercase in the wordmark)
- **Tagline:** *The anatomy of how things fall apart.*
- **Voice:** calm, precise, forensic. A coroner, not a hype man. We never gloat over a
  disaster — we respect it and dissect it. Dry wit is allowed; sensationalism is not.

---

## Color palette

| Role | Name | Hex | Use |
|---|---|---|---|
| Base | Charcoal Black | `#0E0F12` | Backgrounds, canvas |
| Base 2 | Slate | `#16181D` | Panels, gradient partner |
| Accent | Autopsy Amber | `#F5A623` | The ONE accent — highlights, the EKG line, key word in headlines |
| Ink | Bone White | `#F2F0EB` | Primary type |
| Muted | Ash Grey | `#8A8F98` | Secondary type, captions, dates |
| Alert | Signal Red | `#E5484D` | Rare — only for the literal moment of failure / death toll |

**Rule:** amber is the only color that gets to be bright. Everything else is
charcoal, bone, or ash. One accent = premium, disciplined, instantly recognizable.
Signal red is a scalpel, not a highlighter — used at most once per video.

---

## Typography

- **Display / wordmark:** a heavy geometric or grotesk sans — e.g. **Archivo Black**,
  **Anton**, or **Neue Haas Grotesk Black**. Tight tracking, uppercase.
- **Body / lower-thirds:** a clean humanist sans — **Inter** or **Söhne**.
- **Data callouts:** a monospace — **JetBrains Mono** or **IBM Plex Mono**. All
  numbers, timestamps, error codes, and "coroner's report" stat cards use mono. The
  monospace is a deliberate signal: this is technical, evidentiary, factual.

---

## The logo / avatar

- The mark is a **heartbeat EKG line that runs flat, then breaks into a sharp
  downward crash spike** — one gesture that reads both "flatline / death" and
  "collapse / crash."
- Amber line on charcoal, inside a subtle concentric ring badge.
- Must survive being shrunk to a 24px avatar: no fine text in the mark itself.
- File: `assets/avatar.png`

## The banner

- Charcoal gradient, faint blueprint grid, the EKG-crash line across the middle, the
  **POST-MORTEM** wordmark and tagline centered-left with lots of negative space.
- Keep the wordmark and tagline inside YouTube's central safe area (1546×423 in the
  2560×1440 canvas) so they survive TV/desktop/mobile cropping.
- File: `assets/banner.png`

---

## Thumbnail template

Every thumbnail follows the same skeleton so the channel is recognizable in a
sidebar of competitors. Reference: `assets/thumbnail-template.png`.

**Layout (1280×720):**
1. **Background:** charcoal + faint blueprint grid.
2. **Corner tag (top-left):** small amber pill/label reading `POST-MORTEM` — the
   channel signature, same spot every time.
3. **Headline (left two-thirds):** 3–6 words, heavy uppercase Bone White, with the
   single most shocking word in **Autopsy Amber**. e.g. THE $460 MILLION **BUG**.
4. **Subject image (right third):** one desaturated, high-drama image of the failure
   (the explosion, the wreck, the empty HQ). Slightly darkened so text stays king.
5. **Signature motif:** the amber EKG-flatline-to-crash line along the bottom edge.

**Do:** one idea per thumbnail, huge readable type, consistent amber word-highlight.
**Don't:** clickbait faces, red arrows, multiple bright colors, more than ~6 words.

---

## Motion / editing signatures (for the edit step)

- **Intro sting (~3s):** silent charcoal, the amber EKG line draws across, flatlines,
  crashes down on the beat — wordmark snaps in. Same every episode.
- **Stat cards:** monospace numbers counting up on a charcoal card with an amber
  underline. Used for costs, dates, death tolls, timelines.
- **"The Autopsy" chapter card:** amber section title on black, signals the shift from
  *what happened* to *why it happened*.
- **Pacing:** slow, deliberate, lots of held black frames. The calm is the brand.
