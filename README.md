# growthz

> **Research and educational tool only. Not a medical device.**
> growthz does arithmetic against published CDC tables. It does not
> diagnose, interpret, or recommend anything, and its output must be
> verified before any clinical use.

**Batch-compute CDC growth z-scores and percentiles for a whole CSV of
child measurements at once — offline, with the CDC's own LMS tables.**

Growth z-scores are how growth-chart data is actually analysed in
research and survey work, but the tooling is awkward: the WHO/CDC
reference programs are desktop or R/Stata affairs, and the one Python
attempt is abandoned and accuracy-disclaimed. `growthz` is the file-level
tool: give it a CSV with a sex, an age in months, and whatever
measurements you have (weight, length, height, head circumference, BMI),
and it writes the same CSV back with a z-score and percentile for every
measure it can compute — using the CDC LMS method and the CDC's own
published LMS tables, bundled verbatim so everything runs offline and
every number can be checked against the source file it came from.

**v1 is CDC only** (the CDC 2000 growth charts for the United States).
The WHO Child Growth Standards are future work.

## Demo

```console
$ growthz convert examples/measurements.csv --out examples/measurements_growthz.csv
processed 5 rows from examples/measurements.csv
  computed z-scores for 5 rows; 0 rows carry a data-quality flag (see README)
  reference : CDC 2000 growth charts (LMS), CDC only in v1
  output    : examples/measurements_growthz.csv
```

Input (`examples/measurements.csv`):

```csv
id,sex,age_months,weight_kg,length_cm,height_cm,head_circ_cm
ex1,M,9.5,9.7,72.0,,45.0
ex2,F,12.5,11.0,79.0,,44.5
ex3,F,60.5,20.0,,112.0,
ex4,M,120.5,32.0,,138.0,
ex5,M,9.0,9.7,71.0,,44.0
```

The output keeps every input column and appends one z-score and
percentile per measure. A few of the appended columns:

```csv
id,...,weight_for_age_z,weight_for_age_percentile,length_for_age_z,length_for_age_percentile,bmi_for_age_z,bmi_for_age_percentile,weight_for_length_z,weight_for_length_percentile
ex1,...,0.207,58.2,-0.125,45.0,,,1.018,84.6
ex2,...,1.198,88.5,1.597,94.5,,,0.726,76.6
ex3,...,0.690,75.5,,,,0.556,71.1,,
ex5,...,0.393,65.3,-0.237,40.6,,,1.316,90.6
```

(The full output, including stature, head-circumference and
weight-for-stature columns plus `data_quality_flags` and `notes`, is in
`examples/measurements_growthz.csv`. Empty cells mean that measure was
not computable for that row — the `notes` column says why when an input
was present but out of range.)

The first row is the CDC's own published worked example — a 9-month-old
male at 9.7 kg — and the tool reproduces the CDC's published answer
exactly (see *Verify your install*).

## Install

```console
$ pip install git+https://github.com/RakTikoo/growthz
```

Requires Python ≥ 3.10. **No third-party dependencies** — standard
library only — and everything runs **offline**: the CDC tables are
bundled in `growthz/data/` (verbatim copies; see
`growthz/data/SOURCES.md` for the source page, download date, and
file-by-file provenance).

## Usage

```
growthz convert FILE [--out FILE]
growthz check
```

Input CSV columns:

- `sex` — **required**: `M`/`F`, `male`/`female`, or the CDC codes
  `1`/`2`.
- `age_months` — **required**: age in months; decimals are fine (see
  *Age handling* below).
- `weight_kg`, `length_cm` (recumbent length), `height_cm` (standing
  stature), `head_circ_cm`, `bmi` — optional measurements. Each measure
  with enough inputs gets a z-score and a percentile.
- Any other columns are carried through untouched.

Measures computed, and the CDC table behind each:

| Output | Inputs | CDC table | Grid range |
|---|---|---|---|
| `weight_for_age` | weight, age | wtageinf / wtage | 0–36 mo / 24–240 mo |
| `length_for_age` | recumbent length, age | lenageinf | 0–35.5 mo |
| `stature_for_age` | standing height, age | statage | 24–240 mo |
| `head_circ_for_age` | head circumference, age | hcageinf | 0–36 mo |
| `bmi_for_age` | bmi, or weight + standing height, age | bmiagerev | 24–240.5 mo |
| `weight_for_length` | weight, recumbent length | wtleninf | length 45–103.5 cm |
| `weight_for_stature` | weight, standing height | wtstat | height 77–121.5 cm |

Length and stature are separate columns on purpose: recumbent length
and standing height are different measurements with different tables,
and silently mixing them is a classic source of wrong z-scores.

If `bmi` is not given but both `weight_kg` and `height_cm` are, BMI is
computed as kg/m² and reported in the `bmi_kg_m2` column. BMI is never
computed from recumbent length: CDC BMI-for-age starts at 24 months and
is defined on stature.

Rows with a bad value (an unrecognised sex, a non-numeric or
non-finite age, a non-positive or non-finite measurement) do not
abort the run: the row is written out
with the problem described in its `notes` column and a warning on the
console. A structurally broken file (missing `sex`/`age_months`
columns, empty file) is an error with a clean message, never a
traceback.

### Verify your install

```
$ growthz check
growthz check -- CDC published worked example
  input   : 9-month-old male, weight 9.7 kg (CDC WTAGEINF row Agemos 9.5: L=-0.1600954, M=9.476500305, S=0.11218624)
  computed: Z 0.207, percentile 58.2
  expected: Z 0.207, percentile 58.2 (CDC data-files page: Z = 0.207, 58th percentile)
  result  : PASS
```

This is the worked example published on the CDC's data-files page,
verbatim: for a 9-month-old male weighing 9.7 kg, the CDC looks up
L = −0.1600954, M = 9.476500305, S = 0.11218624 in the WTAGEINF table
and publishes Z = 0.207, the 58th percentile. The test suite pins this
example, nine further cases computed by hand from published LMS rows
(arithmetic shown in the test comments), and a cross-check of every
bundled table against the CDC's own smoothed percentile columns printed
in the same files.

## Method

The CDC LMS method. For a measurement X and the table values L
(Box-Cox power), M (median) and S (generalised coefficient of
variation) for the child's sex and age (or length/height, for the
weight-for-length/stature tables):

```
Z = ((X/M)^L − 1) / (L·S)    for L ≠ 0
Z = ln(X/M) / S              for L = 0
```

The percentile is the standard normal CDF of Z, computed with
`math.erf` from the standard library.

### Age handling

The CDC tables list age at the **half-month point for the whole
month**: the row at Agemos 9.5 covers children aged 9.0–9.99 months,
which is why the CDC's worked example for a "9-month-old" uses the 9.5
row. The CDC also states that "to obtain L, M and S values at finer
age or length/stature intervals interpolation could be used".

growthz follows that directly: **L, M and S are linearly interpolated
between the two surrounding table rows** for the requested age (or
length/height). Consequences, stated plainly:

- At an exact table grid point (…, 8.5, 9.5, 10.5, …) the published
  table values are used verbatim — that is how `growthz check`
  reproduces the CDC example exactly.
- Between grid points the result is an interpolation, not a published
  CDC number. It is smooth and close to either neighbour, but if you
  need to match a system that instead uses the whole-month row
  (floor(age) + 0.5), your results will differ slightly between grid
  points.
- **No extrapolation, ever.** Outside a table's grid range the measure
  is left blank and the row's `notes` column says so.

In the 24–36 month overlap where both the infant (birth–36 mo) and the
older-children (2–20 y) charts exist, weight-for-age and
head-circumference use the infant tables up to and including 36
months, and the older weight table above 36 months.

### Data-quality flags (WHO plausibility ranges)

When a computed z-score falls outside the range the WHO uses to flag
biologically implausible values during survey data cleaning —
weight-for-age −6…+5, length/height-for-age −6…+6,
weight-for-length/height −5…+5, BMI-for-age −5…+5,
head-circumference-for-age −5…+5 — the row's `data_quality_flags`
column names the measure, e.g.
`weight_for_age_z_outside_plausibility_range(-6..+5)`.

A flag is a statement about the **data** — "check this measurement or
its data entry" — in the spirit of the WHO flagging practice it is
borrowed from. It is **not a judgement about the child**, and growthz
attaches no interpretation, category, or recommendation to any z-score,
flagged or not.

## Honest limits

- **CDC only in v1.** These are the CDC 2000 charts for the United
  States. The WHO Child Growth Standards (0–5 y) and WHO 2007
  reference (5–19 y) are a different reference with different tables
  and extra rules (the modified z-score for |Z| > 3, the 0.7 cm
  length/height adjustment); they are **not** in v1 and are future
  work. Do not mix references.
- **Numbers only, by design.** No diagnosis, no growth assessment, no
  categories, no advice. A z-score is reported; what it means for a
  child is a clinical judgement this tool does not make.
- **Age is taken as given.** You supply `age_months`; growthz does not
  compute age from birth/visit dates, does not correct for gestational
  age or prematurity, and does not apply the WHO length-vs-height
  0.7 cm adjustment. Garbage age in, garbage z-score out.
- **Interpolation is a policy, not a CDC-published value** (see *Age
  handling*). Between grid points, other CDC-based systems may differ
  slightly depending on their own policy.
- **Extreme z-scores are the plain LMS formula's.** Unlike the WHO
  method, the CDC LMS calculation here is not modified beyond ±3 SD,
  so very extreme measurements produce very extreme z-scores; that is
  exactly what the plausibility flags are for.
- **The reference is a reference.** CDC 2000 describes the US reference
  population the charts were built from; a percentile is a position in
  that population, nothing more.

## Tests

```console
$ python3 run_tests.py
```

36 tests (stdlib `unittest`): the CDC published worked example
verbatim (formula level, table level, full pipeline, and the `check`
subcommand), nine more oracle cases hand-computed from published LMS
rows, the interpolation policy, the L = 0 formula branch, every bundled
table cross-checked against the CDC's own percentile columns and row
counts, plausibility-flag behaviour, out-of-range handling, and CLI
end-to-end/adversarial cases (bad rows noted rather than fatal, missing
columns, empty and missing files — all clean errors, no tracebacks),
plus the adversarial-review regressions in `REVIEW.md` (non-finite
values rejected per row, an extreme row that overflowed the LMS
formula no longer aborts the batch, surplus CSV fields ignored with
a warning).

## License

MIT. Free and open source, for science. The bundled CDC data files are
US Government public data, redistributed unchanged.
