# Volume science: what the targets are based on

This is the evidence behind `MUSCLE_TARGETS`, `SECONDARY_WEIGHT` and `MUSCLE_REGIONS` in
[app/exercises.py](../app/exercises.py), and the rules that follow from it. Read it before
changing a target, adding a muscle group, or subdividing one — several plausible-sounding
changes are ruled out below, with reasons.

It is deliberately separate from ARCHITECTURE.md: that file says how the app is shaped,
this one says what we believe about training and how confident we are.

---

## 1. What the literature establishes

**Weekly sets per muscle group drive hypertrophy, with diminishing returns.** The best
current synthesis is [Pelland et al., *Sports Medicine* (2025)](https://link.springer.com/article/10.1007/s40279-025-02344-w)
([PubMed](https://pubmed.ncbi.nlm.nih.gov/41343037/)) — Bayesian meta-regressions over 67
studies and 2,058 participants:

- Posterior probability that more volume produces more growth: **100%**. It keeps rising
  past 40 sets/week, but ever more slowly.
- Roughly **4 sets/week** is the floor at which a muscle reliably responds at all.
- Most of the achievable weekly gain arrives in the **first 5–10 sets**.
- **Frequency is essentially irrelevant to hypertrophy** once weekly volume is matched.
  It matters for strength. This is why Body Shop aggregates by week and does not care how
  many sessions the sets came from.

[Schoenfeld and Krieger's earlier meta-regression](https://www.semanticscholar.org/paper/Dose-response-relationship-between-weekly-training-Schoenfeld-Ogborn/0d34206f962394983054451cddd8a3b91818f732)
put a threshold near **10 sets/week** for near-maximal growth. Most reviews land on a
responsive band in the low tens of sets for trained lifters.

### The finding the codebase depends on

Pelland tested three ways of counting sets where the muscle is not the target: **total**
(count an indirect set as 1.0), **fractional** (0.5), and **direct** (0.0). The
**fractional method fit the data best.**

`PRIMARY_WEIGHT = 1.0` / `SECONDARY_WEIGHT = 0.5` is therefore not a convenience — it is
the best-supported way to count a set, and it is the single most defensible thing in the
app. Do not replace it with a flat count, and do not "improve" it with invented
per-exercise coefficients without evidence to point at.

### Do different muscles need different amounts?

Weakly supported. Direct comparisons mostly find no muscle-specific optimum; the
recurring exception is triceps, which keeps responding at higher volumes — plausibly
because it is a secondary mover whose real volume is undercounted, which the fractional
method partly fixes anyway.

So `MUSCLE_TARGETS` (20 large / 10 small) is a **defensible convention, not a finding.**
Practitioner frameworks such as [RP's volume landmarks](https://rpstrength.com/blogs/articles/training-volume-landmarks-muscle-growth)
do differentiate per muscle, and are expert opinion rather than dose-response data. Treat
the numbers as calibration you may tune, not as results you must preserve.

---

## 2. Regions and heads: real, but not measured

The plan to track upper/mid/lower chest and the three deltoid heads runs into one hard
fact:

> **No study has ever established a weekly set target for a muscle head or region.**
> Nobody has run the experiment. Not for delt heads, not for pec regions, not for
> anything.

What *is* established is that growth within a muscle is **non-uniform, and follows
exercise selection and muscle length** — a different claim, and a weaker one to build a
number on:

| Subdivision | Confidence | Evidence |
| --- | --- | --- |
| Triceps long vs. lateral/medial | **Strong** | [Maeo 2023](https://onlinelibrary.wiley.com/doi/10.1080/17461391.2022.2100279): overhead extensions grew every head substantially more than pushdowns, long head most ([discussion](https://www.strongerbyscience.com/research-spotlight-triceps/)) |
| Deltoid front / side / rear | **Strong** | Distinct activation per movement class; [systematic review of the three portions](https://www.sciencedirect.com/science/article/abs/pii/S1360859222001607). The deltoid subdivides into ~7 regions by moment arm, so exercise variety matters more than volume per head |
| Hamstrings knee-flexion vs. hip-extension | **Strong** | Maeo: the seated leg curl (hip flexed, hamstrings long) produced ~55% more growth than lying, across three of the four heads |
| Chest clavicular (upper) vs. sternal | **Moderate–good** | [Chaves 2020](https://pubmed.ncbi.nlm.nih.gov/32922646/): the incline-only group grew upper pec markedly more than flat or combined |
| Lats vs. mid-back; gastrocnemius vs. soleus | **Moderate** | Vertical vs. horizontal pulling; knee angle changing which plantarflexor is loaded |
| Quad heads, glute max vs. medius, traps regions | **Moderate** | ROM and joint-angle studies; mapping exercises to regions is muddier |
| Biceps long vs. short head, "upper vs. lower abs" | **Weak** | Largely EMG, little hypertrophy data. Not tracked |

General principle from the reviews ([NSCA](https://www.nsca.com/education/articles/ptq/building-a-balanced-and-symmetrical-physique/),
[muscle-length meta-analysis](https://sportrxiv.org/index.php/server/preprint/view/464)):
regional growth tracks the region most loaded by the exercise, effects are modest, and
results are inconsistent between studies.

---

## 3. Rules that follow

These are binding on the code.

### 3.1 Regions get no targets

A region reports **sets, share of its parent's volume, and whether it was neglected.** It
has no target, no `state`, no `intensity`, and never colours the body map. There is no
evidence to grade it against, and inventing one would put a fabricated number in front of
a user who cannot tell it apart from the sourced ones.

### 3.2 Targets partition; they never multiply

If chest is 20 and you give upper, middle and lower chest 10 each, you have silently set a
30-set chest target and every user reads as under-trained. Should a future phase ever give
regions targets, they must **sum to the parent's**, and that phase must say why the
literature suddenly permits it.

### 3.3 Attribution is partial on purpose

Only movements whose region emphasis is defensible appear in `EXERCISE_REGIONS`. A
deadlift trains the back without saying anything about lats vs. mid-back, so it is
attributed to neither, and the payload reports how much of the parent's volume was
region-attributed. **Partial coverage stated honestly beats full coverage invented.**

Two deliberate asymmetries:

- **Pressing counts toward front delts** (it is where most front-delt volume comes from,
  and the point of the readout is to show that), but
- **pressing does not count toward triceps regions** — the long-head evidence is about
  isolation patterns and elbow position, so only direct triceps work is attributed.

### 3.4 The neglect threshold is a judgement, and is named as one

`REGION_NEGLECT_SHARE` (0.15) and `REGION_NEGLECT_MIN_PARENT_SETS` (4.0, the literature's
approximate floor for a muscle responding at all) are the only invented numbers in the
region feature. They are constants with docstrings, not magic literals, so a future
session can see exactly what is opinion.

---

## 4. Product voice

Body Shop is not a hypertrophy calculator and must not read like one.

- **Never show a range as advice.** No "aim for 10–20 sets", no "4–12 sets for rear
  delts". A range is a research finding, not an instruction, and printing one invites the
  user to treat the widest number as the goal. One target per group; the colour ramp says
  the rest.
- **The purpose is coverage, not maximisation.** What the app is *for* is keeping every
  muscle — and every region of the ones we can subdivide — inside a productive range: no
  gaps that leave weak links, and no runaway volume on one group while its neighbours are
  untrained. That framing is what the red overshoot scale and the region readout are both
  in service of.
- **Say "balanced", "covered", "productive range"** — not "optimal", "maximal", or
  anything implying a dose the app can compute for a specific person.
- **Do not give medical or injury advice.** The honest claim is about *balance* and
  *avoiding overwork*, which is a training claim. "This will prevent injury" is not.

---

## 5. If you revisit this

Worth doing, roughly in order of value:

1. **Recalibrate `MUSCLE_TARGETS`** against the dose-response curve rather than the
   20/10 convention — it is the least evidenced number in the app.
2. **Extend `EXERCISE_REGIONS`** past the curated set. free-exercise-db carries no
   sub-muscular data at all, so this is hand work or a job for the AI classification in
   Phase 8 — which must emit into the vocabulary in `MUSCLE_REGIONS`, not invent its own.
3. **Add quads, glutes and traps regions** if the exercise-to-region mapping can be made
   as clean as the six that shipped.
4. **Per-exercise secondary weights** instead of a flat 0.5, if evidence appears. The
   fractional method is currently the best-supported option, so this needs a real source.
