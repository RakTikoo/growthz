# growthz — independent adversarial review

Reviewer: independent review agent (did not build the tool).
Date: 2026-11-17. Scope: the gauntlet was run locally; at review time nothing had been published or pushed.
Design decisions left untouched, as specified: CDC only in v1 (WHO is
future work); implausible-value flags are data-quality flags only,
never a judgement about the child.

## Verdict

Sound tool, correct arithmetic, honest README. Three real defects
found (one high, two medium) plus two low-severity robustness issues —
all fixed, with regression tests. Original suite: **30 tests, all
passing**. Final suite: **36 tests, all passing**.

## (b) Independent oracle verification — PASS

Computed independently from the raw bundled CSV rows (own LMS
arithmetic + `math.erf` normal CDF in the review script; the tool's
code was not used to produce the expected values):

| Case | Table row (L, M, S) | Independent Z / pct | Tool |
|---|---|---|---|
| **CDC worked example: M, 9 mo, 9.7 kg wt-age** | wtageinf 9.5: −0.1600954, 9.476500305, 0.11218624 | **Z = 0.2074 → 0.207, 58.2%** | 0.207, 58.2 ✓ (CDC publishes Z = 0.207, 58th pct) |
| F, 12.5 mo, 11.0 kg wt-age | wtageinf ♀12.5: −0.15640945, 9.666089185, 0.106834517 | 1.198, 88.5% | ✓ |
| M, 12.5 mo, 76.0 cm length-age | lenageinf ♂12.5: −0.753908107, 76.11837536, 0.038703461 | −0.040, 48.4% | ✓ |
| F, 6.5 mo, 44.0 cm head-circ | hcageinf ♀6.5: −1.046582628, 42.71033603, 0.029974303 | 0.977, 83.6% | ✓ |
| F, 60.5 mo, 112.0 cm stature | statage ♀60.5: −0.057729947, 107.9566031, 0.044276588 | 0.830, 79.7% | ✓ |
| M, 120.5 mo, BMI 18.5 | bmiagerev ♂120.5: −2.765648008, 16.64613844, 0.120112464 | 0.762, 77.7% | ✓ |
| M, 120.5 mo, 32.0 kg wt-age (older table) | wtage ♂120.5 | −0.015, 49.4% | ✓ |
| M, length 85.5 cm, 12.5 kg wt-for-length | wtleninf ♂85.5 | 0.512, 69.6% | ✓ |
| F, height 100.5 cm, 16.0 kg wt-for-stature | wtstat ♀100.5 | 0.306, 62.0% | ✓ |
| Interpolation midpoint M, 9.0 mo, 9.7 kg | mean of 8.5/9.5 rows | 0.393, 65.3% | ✓ |

Bundled-table provenance: all 8 LMS files were re-downloaded from
`cdc.gov/growthcharts/data/zscore/` during this review and are
**byte-for-byte identical** to the bundled copies. `growthz check`
passes.

## (a) Adversarial probes — what was tried

Boundaries (all correct): exact grid points (0, 0.5, 9.5, 35.5, 36,
45 cm, 77 cm, 103.5 cm, 121.5 cm, 240, 240.5); just outside every grid
(35.75 length-age, 36 head-circ, 44.9/103.6 wt-for-length, 121.6
wt-for-stature, age 300, age −1 via API) → blank + explanatory note,
no extrapolation, no crash. Non-uniform end intervals (0→0.5,
35.5→36) interpolate correctly. Infant→older wt-age switch at
36 / 36.0001 is continuous (−0.210 vs −0.210). Half-month policy:
age 9.0 interpolates between the 8.5/9.5 rows (documented; differs
from a floor(age)+0.5 system by design, README says so plainly).
L = 0 branch (synthetic): ln formula correct; tiny L (1e-12) sane;
median → Z = 0, 50.0%. Zero/negative measurements and negative age
rejected per row. Missing sex/age values, unrecognised sex, `1.0` as
sex, comma decimals, non-numeric age → per-row notes, batch survives.
Short rows, blank lines, duplicate header mid-file, quoted fields,
CRLF+BOM, whitespace/case sex variants, scientific notation → all
handled. BMI is never computed from recumbent length; an explicit
`bmi` wins over weight+height. Extreme-but-finite values (30 kg at
9.5 mo → Z 9.38; 0.5 kg → Z −33.5; head-circ 200 cm → Z 150.8) are
computed and carry the WHO-range data-quality flag, as designed.

## Findings and fixes

1. **HIGH — one extreme row aborted the whole batch.**
   `M,0,1e200` (L ≈ +1.82 at birth) raised a raw
   `OverflowError: (34, 'Numerical result out of range')` out of
   `compute_row`; the convert died with exit 2, no output file, and
   every other row was lost — contradicting the README's "bad rows do
   not abort the run". Fixed: `lms_zscore` catches `OverflowError`
   and returns a signed infinity (the mathematically correct limit;
   percentile 100/0, plausibility flag fires), and the CLI now also
   converts any `GrowthzError`/`ArithmeticError`/`ValueError` from
   `compute_row` into a per-row problem note.
2. **MEDIUM — non-finite values produced silent garbage.**
   `float()` parses `nan`/`inf`/`1e999`, and the CLI accepted them:
   a `nan` weight yielded z = `nan`, percentile = `nan`, counted as
   "computed", with no flag or note; an `inf` weight yielded a
   fabricated Z = 55.678; `nan`/`inf` ages produced misleading
   "outside grid range" notes (and a NaN age still got a
   weight-for-length result). Fixed: `_parse_float` rejects
   non-finite values as bad rows; `lms_zscore` and `compute_row`
   raise `GrowthzError` on non-finite inputs for API users too.
3. **MEDIUM — surplus CSV fields aborted the run.**
   A row with more fields than the header died at write time:
   `error: could not write output file ...: dict contains fields not
   in fieldnames: None` (exit 2, no output). Fixed: surplus fields
   are ignored with a printed warning; the row's named columns are
   processed normally.
4. **LOW — `compute_row(sex=3)` raised a raw `KeyError`.**
   Fixed: sex and finiteness are validated up front, raising
   `GrowthzError` with a clear message.
5. **LOW — summary line over-counted.** "computed z-scores for N
   rows" counted rows with no measurements at all (nothing was
   computed for them). Fixed: a row counts only when at least one
   z-score was produced. README demo output is unchanged (all 5 demo
   rows produce z-scores).

Six regression tests were added (`TestAdversarialReviewRegressions`)
pinning each fix; the README test count and bad-row description were
updated to match.

Not fixed (observed, acceptable): a 1 cm height yields BMI 200000
and stature Z = −121 — both flagged as data-quality problems, which
is the flag system working as designed; duplicate column names in a
header are not specially handled.

## (c) Fresh-install + demo — PASS

`python3 -m venv` (system Python 3.12.3) worked — creating a venv
from the astro-tools venv's Python did not complete cleanly, so the
system interpreter was used; no `--target` fallback was needed.
`pip install <local tree>` in the fresh venv succeeded (stdlib only),
`growthz check` → PASS, and the README demo reproduced **exactly**:
console output matches the README verbatim and the output CSV is
byte-identical to the bundled `examples/measurements_growthz.csv`.
Re-verified again after the fixes, in a second fresh venv.

## (e) README check — PASS

States "Research and educational tool only. Not a medical device"
up top; states CDC-only v1 with WHO as future work in three places;
"Honest limits" section is complete and accurate (interpolation is a
policy, no extrapolation, no gestational-age correction, extreme
z-scores unmodified, reference-population caveat). Grep for
diagnosis/interpretation language finds only negations ("does not
diagnose, interpret, or recommend", "No diagnosis..."). Flags are
described throughout as statements about the data, never the child.
