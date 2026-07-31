# Volume science: what the targets are based on

This is the evidence behind `MUSCLE_TARGETS`, `SECONDARY_WEIGHT` and `MUSCLE_REGIONS` in
[app/exercises.py](../app/exercises.py) and the scaling in
[app/training.py](../app/training.py), and the rules that follow from it. Read it before
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

### Does one target fit every lifter?

No, and Phase 6 says so — but the honest version of "no" is smaller than it looks.

The dose-response curve in Pelland rises for **everyone**. What differs between a
beginner and an advanced lifter is not the shape of the curve but how much volume they
can recover from and hold to week after week, and there is no dose-response study that
resolves that into per-level numbers. So `app/training.py` scales the *whole* baseline by
one multiplier per level (0.6 / 1.0 / 1.3) and preserves the 2:1 large-to-small split
untouched, because that split is the part §1 actually supports.

**Those three multipliers are convention.** Tune them; do not defend them as findings.
The same goes for `SESSION_OVERHEAD_MINUTES`, which is a claim about gyms, not muscles.

Two things in that module are *not* convention:

- **`MIN_GROUP_TARGET = 4`** is §1's floor — roughly the volume below which a muscle does
  not reliably respond at all. It is the reason no combination of a short week and a
  beginner setting can produce a target of 2.
- **The `min` rule.** Experience and available time are not independent inputs. Training
  three short sessions *is* how a lower training age shows up in the log, so multiplying
  the two factors charges the same lifter twice for one fact — the first implementation
  did exactly that and pushed every group onto the floor. The target is the smaller of
  what the level asks for and what the week can hold, which also means **a roomier week
  never raises a target**. Having time available is not evidence that more volume is
  wanted; it is only ever a ceiling.

The old constraint still binds: the frequency finding in §1 is why the session plan enters
as *total weekly minutes* and not as a per-session prescription. Body Shop still does not
care how many sessions the sets came from, only that they fit.

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

### 3.4 The trainer setup scales, it never prescribes

The setup on `/summary` resolves to **one integer per group**, exactly as the fixed
targets did. It may not become a range, a per-session plan, or a recommendation about
which experience level to pick. Three specific things it must not do:

- **Never print a range.** "Beginners: 8–14 sets" is the §4 violation this feature is
  most exposed to, because it now has a plausible-looking reason to show two numbers.
- **Never tell someone what level they are.** The control asks; it does not assess.
  Nothing in the app has the information to place a lifter, and the levels are
  calibration rather than a diagnosis.
- **Say which input is binding, not what to do about it.** `limited_by` exists so the
  page can report that the week — rather than the level — is what is holding the targets
  down. That is a statement about arithmetic the user can check. "Train more" is not.

### 3.5 A personal best is your own, and always shows its working

Phase 6.7 put an estimated one-rep max on `/progress`. It is the app's first
strength-relative mark, and it stays inside the same discipline as everything above.

- **It is your log, not a population.** Epley on a set the user typed in is arithmetic
  on their own data. A strength *standard* — what someone of a given bodyweight
  "should" lift — needs a bodyweight the app does not store and a comparison it does
  not make. That remains out, and it is a product decision rather than a missing
  feature.
- **An estimate is labelled as one and names its source.** The panel reads
  `Est. 1RM 117kg — from 100kg × 5 on Jul 24`, never a bare number. A logged single is
  not dressed up as an estimate, because it is the lift.
- **Refusing is the default.** No weight, no reps, or a set past `MAX_ESTIMATE_REPS`
  (12) means no estimate — every rep-max formula drifts badly past ten, and Epley on a
  20-rep set reports a single 67% above the bar. The movement then draws as a **hollow
  ring, never a small node**: sizing an unmeasured lift at zero states that it is light,
  which is false rather than merely unknown.
- **Nothing here is prescriptive.** The graph reports what was lifted. It does not say
  what should be lifted next, and Phase 8's auto-progression is where that argument
  belongs.

### 3.6 The neglect threshold is a judgement, and is named as one

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

  **The exception, and why it is one:** a routine's `4 × 6-8` is a rep prescription
  *inside a session someone else wrote*, labelled as a suggestion and shown next to that
  session. It is not a claim about how much weekly volume a muscle needs, which is the
  object this rule is about — and it is what every routine anywhere is written in. What
  a routine may still never do is print a weekly set target, or a range of one.
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
   20/10 convention — it is the least evidenced number in the app. Note this now moves
   every trainer level at once, since they are multipliers on it.
1b. **Revisit the level multipliers** (0.6 / 1.0 / 1.3) if evidence on training-age and
   recoverable volume appears. Same status as the targets: calibration, not results.
2. **Extend `EXERCISE_REGIONS`** past the curated set. free-exercise-db carries no
   sub-muscular data at all, so this is hand work or a job for the AI classification in
   Phase 8 — which must emit into the vocabulary in `MUSCLE_REGIONS`, not invent its own.
3. **Add quads, glutes and traps regions** if the exercise-to-region mapping can be made
   as clean as the six that shipped.
4. **Per-exercise secondary weights** instead of a flat 0.5, if evidence appears. The
   fractional method is currently the best-supported option, so this needs a real source.
