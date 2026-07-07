# POST-MORTEM — Episode 001 (Script)

## The $370 Million Bug — How One Line of Code Destroyed a Rocket

**Runtime target:** ~9:30 · **Format:** single AI narrator · **Subject:** Ariane 5,
Flight 501 (4 June 1996)

**How to read this file:** the left column is what the voice says — read it verbatim.
`[beats in brackets]` are direction: pauses, tone, and what's on screen. Timestamps are
cumulative and approximate; they're for pacing the edit, not hard cuts.

---

### COLD OPEN — HOOK · 0:00–0:45

> On the fourth of June, 1996, a rocket left the ground in French Guiana.
>
> `[held black. faint launch-pad rumble.]`
>
> Thirty-seven seconds later, it tore itself apart in the sky.
>
> `[amber EKG line draws across… flatlines… then the crash spike. beat.]`
>
> No one was hurt. There was no sabotage. No storm. No faulty wire, no cracked weld,
> no engine that failed.
>
> The rocket worked perfectly. Every bolt, every valve, every gram of fuel did
> exactly what it was built to do.
>
> `[pause]`
>
> It was destroyed by a number. A single number, in a piece of software that wasn't
> even supposed to be running — code that had already done its job, copied over from
> an older rocket because it had never once failed.
>
> This is how a decade of work and three hundred and seventy million dollars came
> apart in less time than it takes to read this sentence.
>
> `[intro sting: wordmark snaps in]` This is **POST-MORTEM**.

---

### CHAPTER 1 — THE SETUP · 0:45–2:45

> Ariane 5 was Europe's bet on the future.
>
> `[archival-style stills: ESA, the assembled launcher, blueprint overlays]`
>
> Its predecessor, Ariane 4, was one of the most reliable rockets ever flown —
> Europe's workhorse, a machine that put more than half the world's commercial
> satellites into orbit. But it was getting old, and it wasn't big enough for what
> was coming next.
>
> So the European Space Agency spent nearly ten years and around seven billion
> dollars building its successor. Ariane 5 was taller, heavier, and far more
> powerful — a rocket designed to carry the biggest payloads of the coming century.
>
> `[stat cards, monospace: ~10 YEARS · ~$7 BILLION · maiden flight 04·06·1996]`
>
> Flight 501 was its very first launch. The maiden voyage. On board sat four
> scientific satellites called Cluster — a mission years in the making, built to
> study the Earth's magnetic field. Irreplaceable.
>
> `[beat]`
>
> Now — a rocket is only as smart as the computer flying it. And that computer needs
> to know one thing above all else: which way is up. How is it tilted, how fast is it
> turning, where is it pointed. That job belongs to a component called the Inertial
> Reference System.
>
> `[simple diagram: the SRI feeding orientation data to the main computer]`
>
> Ariane 5 carried two of them — a main unit and a backup — constantly measuring the
> rocket's motion and feeding it to the flight computer, so the engines could steer.
>
> Here's the decision that matters. When the engineers wrote the software for that
> system, they didn't start from scratch. Why would they? Ariane 4's version had
> flown for years without a single fault. It was trusted. It was proven.
>
> So they reused it.
>
> `[on screen, mono: "REUSED FROM ARIANE 4 — 0 FAILURES". amber underline.]`
>
> And that decision — the safe one, the sensible one — is what killed the rocket.

---

### CHAPTER 2 — THE CRACKS · 2:45–4:45

> To understand why, you need one small piece of how computers hold numbers. I'll keep
> it painless.
>
> `[clean animated explainer, charcoal + amber]`
>
> Inside that navigation software was a value tracking the rocket's sideways speed —
> its horizontal velocity. The program stored it in a large, roomy format: a
> sixty-four-bit number, able to hold a huge range of values.
>
> But at one point, the code needed to hand that value to another part of the system
> that expected something smaller — a sixteen-bit number. A far smaller box.
>
> `[visual: a big amber number being poured into a small box that can't hold it]`
>
> And here is the entire disaster, in one idea: on Ariane 4, the sideways speed never
> got big enough to overflow that little box. The rocket was slower off the pad. The
> number always fit.
>
> Ariane 5 was a different animal. More powerful. It built up horizontal speed far
> faster than its predecessor ever could.
>
> `[side-by-side: Ariane 4 gentle curve vs Ariane 5 steep curve; the amber value climbs past a red line]`
>
> Thirty-seven seconds into the flight, that sideways speed climbed past the largest
> value the small box could hold.
>
> The number didn't fit.
>
> `[the value hits the ceiling. mono error text flickers: OPERAND ERROR.]`
>
> In that instant, the software did what it was written to do when it hit an
> impossible conversion. It flagged an error — and it shut the whole navigation unit
> down.
>
> The backup unit? It was running the exact same code, reading the exact same
> too-large number. It had failed a fraction of a second earlier, for exactly the
> same reason.
>
> `[two units on screen; both go dark, one after the other. beat.]`
>
> Two independent systems. One shared flaw. Both gone. And the rocket was now flying
> blind.

---

### CHAPTER 3 — THE COLLAPSE · 4:45–6:15

> `[tone drops. this is the moment.]`
>
> With both navigation units offline, the failed system did one last thing before it
> died. Instead of sending flight data, it sent a diagnostic error code — raw
> numbers, meant for engineers on the ground, never meant for the flight computer.
>
> But the flight computer didn't know that. It was still waiting for orientation
> data, and it took those error numbers and read them as if they were real — as if
> the rocket were violently off course.
>
> `[garbage data flooding into the flight computer; the horizon indicator lurches]`
>
> So it did its job. It tried to correct. It swung the engine nozzles hard over to
> fix a problem that did not exist.
>
> `[the nozzles slam to full deflection]`
>
> The rocket obeyed. It pitched sharply, at full power, into an angle it was never
> built to survive. The aerodynamic forces hit it like a wall.
>
> `[Signal Red enters for the first time]`
>
> The boosters began to tear away from the main stage. And the moment the rocket
> sensed itself breaking apart, its automatic self-destruct did the only thing left
> to do — it detonated the vehicle, high over the launch site, before the wreckage
> could reach the ground.
>
> `[the explosion. then cut to silence. held black.]`
>
> Thirty-seven seconds. That's all it took.
>
> `[mono, slow count-up: T+00:37 · ~$370,000,000 LOST]`
>
> Ten years of work. Around three hundred and seventy million dollars of rocket and
> satellites. Gone — over a number that was too big for its box.

---

### CHAPTER 4 — THE AUTOPSY · 6:15–8:15

> `[amber chapter card: "THE AUTOPSY". shift from what happened to why.]`
>
> An inquiry board took the failure apart. And the uncomfortable truth is that no
> part of this was bad luck. Every link in the chain was a decision.
>
> `[the findings appear one by one, mono list, amber ticks]`
>
> One. The navigation code was reused from Ariane 4 without being re-tested against
> Ariane 5's actual flight profile. It was trusted because it had never failed — but
> it had never flown *this* rocket.
>
> Two. The specific calculation that overflowed wasn't even needed after liftoff. It
> was a leftover, a routine that only mattered on the launch pad, left running into
> flight for a rocket where it served no purpose at all. Dead code, still armed.
>
> Three. That conversion had no protection on it — no check to catch a number that
> was too large, no safe fallback. Some values in the system were protected. This one
> was deliberately left unprotected, to save processing power, based on an assumption
> that the number could never get that big. On Ariane 4, that assumption was true. On
> Ariane 5, no one re-checked it.
>
> Four. Both the main and backup units ran identical software. So the redundancy —
> the whole point of having two — was an illusion. A backup only helps if it can fail
> in a different way. This one was guaranteed to fail in exactly the same way, at
> exactly the same instant.
>
> `[beat. tone steadies.]`
>
> Put those together and the shape of it is clear. This wasn't the story of a bad
> programmer. It was the story of a good assumption that quietly stopped being true —
> and a system with no one left to notice.
>
> The code wasn't wrong for Ariane 4. It was wrong for the rocket it was actually
> bolted to. And nobody had asked the question, because it had never needed asking.

---

### CHAPTER 5 — THE LESSON + OUTRO · 8:15–9:30

> `[return to calm. charcoal. the EKG line, steady now.]`
>
> Here's what Flight 501 leaves on the table.
>
> Reliability is not a property a thing *has*. It's a property of a thing *in a
> situation*. Move it somewhere new — a faster rocket, a bigger load, a different
> world — and "it's never failed before" stops being a promise. It becomes a
> question you haven't asked yet.
>
> The most dangerous code in any system isn't the part everyone's watching. It's the
> part everyone trusts. The proven part. The part nobody re-reads, because it worked
> last time.
>
> `[pause]`
>
> Ariane 5 went on to become one of the most successful rockets in history — it flew
> for another twenty-seven years. They found the bug. They fixed the redundancy. They
> asked the questions.
>
> But the first one paid for that lesson in thirty-seven seconds and three hundred and
> seventy million dollars.
>
> `[beat]`
>
> Every disaster starts as a decision that made sense at the time. That's the whole
> job of this channel — to go back and find the exact moment the sense ran out.
>
> `[wordmark]`
>
> I'm going to keep putting failures on this table. If you want to be here when I do —
> subscribe, and I'll see you at the next one.
>
> `[amber EKG line flatlines… crash spike… cut to black.]`

---

### PRODUCTION NOTES (for the voiceover + edit step)

- **Voice:** measured, low, unhurried. Think coroner reading a report, not a
  YouTuber. Let the pauses breathe — the calm is the brand.
- **Read speed:** ~150 words/min. This script runs ~9–10 minutes at that pace.
- **Music:** low charcoal drone throughout; drop it out entirely on the two "held
  black" beats (the flatline hook and the explosion) for silence-as-punctuation.
- **Signal Red** appears exactly once (the collapse). Don't spend it early.
- **Fact-check note:** figures and sequence follow the ESA Flight 501 inquiry board
  findings (overflow on a 64-bit→16-bit conversion of horizontal bias/velocity in
  the SRI; ~$370M loss). Keep a source line in the description for credibility.
