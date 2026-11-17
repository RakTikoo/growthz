"""Core LMS z-score logic for growthz.

The method is the CDC's published LMS method (CDC 2000 growth charts,
National Center for Health Statistics):

    Z = ((X / M) ** L - 1) / (L * S)      for L != 0
    Z = ln(X / M) / S                     for L == 0

where X is the measurement and L, M, S are the CDC table values for the
child's sex and age (or, for weight-for-length / weight-for-stature, for
the child's length / height). The percentile is the standard normal CDF
of Z, computed with the standard library's math.erf -- no third-party
dependencies anywhere in this tool.

Age / grid handling (documented policy, following the CDC data-files
page): the CDC tables list age at the half-month point for the whole
month (row 9.5 covers 9.0-9.99 months), and the CDC states that "to
obtain L, M and S values at finer age or length/stature intervals
interpolation could be used". growthz therefore LINEARLY INTERPOLATES
L, M and S between the two surrounding table rows for the requested
age (or length/height). At an exact table grid point the table values
are used verbatim, so CDC's own published worked example reproduces
exactly (see `growthz check`). There is NO extrapolation: a value
outside a table's grid range yields no z-score for that measure, and
the row's notes column says why.

Table choice in the 24-36 month overlap: weight-for-age and
head-circumference-for-age use the birth-to-36-months infant tables up
to and including 36 months and the 2-to-20-years weight table above
36 months. Length-for-age is recumbent length (infant table, to
35.5 months); stature-for-age is standing height (2-to-20-years table,
from 24 months). They are separate input columns on purpose: length
and stature are not interchangeable measurements.

Plausibility flags: when a computed z-score falls outside the range
WHO uses to flag biologically implausible values in survey data
cleaning (weight-for-age -6..+5, length/height-for-age -6..+6,
weight-for-length/height -5..+5, BMI-for-age -5..+5,
head-circumference-for-age -5..+5), the row gets a data-quality flag.
A flag means "check the measurement or the data entry" -- it is a
statement about the data, never a judgement about the child, and this
tool makes no diagnosis or interpretation of any kind.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"


class GrowthzError(Exception):
    """A user-facing error: print the message, exit non-zero, no traceback."""


# ---------------------------------------------------------------------------
# LMS mathematics
# ---------------------------------------------------------------------------

def lms_zscore(x, l_value, m_value, s_value):
    """Z-score of measurement x under LMS parameters (CDC formula)."""
    if not math.isfinite(x):
        raise GrowthzError(f"measurement must be finite, got {x}")
    if x <= 0:
        raise GrowthzError(f"measurement must be positive, got {x}")
    if m_value <= 0 or s_value <= 0:
        raise GrowthzError("table M and S values must be positive")
    try:
        if l_value != 0:
            return ((x / m_value) ** l_value - 1.0) / (l_value * s_value)
        return math.log(x / m_value) / s_value
    except OverflowError:
        # (x/M)**L overflowed the float range: the true z-score is
        # beyond float range in the direction of sign(L) (S > 0).
        # Return a signed infinity instead of crashing -- callers flag
        # it as outside every plausibility range, like any other
        # extreme value. (Review fix: a single extreme row previously
        # aborted a whole batch convert with a raw OverflowError.)
        return math.copysign(math.inf, l_value)


def z_to_percentile(z):
    """Percentile (0-100) of a z-score, via the standard normal CDF."""
    return 100.0 * 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


# ---------------------------------------------------------------------------
# CDC LMS tables (bundled verbatim; see data/SOURCES.md)
# ---------------------------------------------------------------------------

class LMSTable:
    """One CDC LMS table: rows keyed by sex, on an age/length/height grid."""

    def __init__(self, filename, grid_column):
        self.filename = filename
        self.grid_column = grid_column
        self.rows = {1: [], 2: []}  # sex -> sorted [(grid, L, M, S), ...]
        path = DATA_DIR / filename
        with open(path, newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                sex = (row.get("Sex") or "").strip()
                if sex not in ("1", "2"):
                    # The CDC files repeat their header row between the
                    # male and female blocks in some tables; skip anything
                    # that is not a data row.
                    continue
                self.rows[int(sex)].append((
                    float(row[grid_column]),
                    float(row["L"]), float(row["M"]), float(row["S"])))
        for sex in self.rows:
            self.rows[sex].sort()
            if not self.rows[sex]:
                raise GrowthzError(f"CDC table {filename} has no rows "
                                   f"for sex {sex}")

    def grid_range(self, sex):
        rows = self.rows[sex]
        return rows[0][0], rows[-1][0]

    def lookup(self, sex, grid_value):
        """(L, M, S) at grid_value, linearly interpolated between rows.

        Returns None when grid_value is outside the table's grid range
        (no extrapolation, ever).
        """
        rows = self.rows[sex]
        lo, hi = rows[0][0], rows[-1][0]
        if grid_value < lo or grid_value > hi:
            return None
        for i, (grid, l_v, m_v, s_v) in enumerate(rows):
            if grid_value == grid:
                return (l_v, m_v, s_v)
            if grid_value < grid:
                g0, l0, m0, s0 = rows[i - 1]
                frac = (grid_value - g0) / (grid - g0)
                return (l0 + frac * (l_v - l0),
                        m0 + frac * (m_v - m0),
                        s0 + frac * (s_v - s0))
        return None  # unreachable given the range check


_TABLES = {}


def table(name):
    if name not in _TABLES:
        filename, grid_column = TABLE_FILES[name]
        _TABLES[name] = LMSTable(filename, grid_column)
    return _TABLES[name]


TABLE_FILES = {
    "weight_for_age_infant": ("wtageinf.csv", "Agemos"),   # birth-36 mo
    "weight_for_age": ("wtage.csv", "Agemos"),             # 2-20 y
    "length_for_age": ("lenageinf.csv", "Agemos"),         # birth-35.5 mo
    "stature_for_age": ("statage.csv", "Agemos"),          # 2-20 y
    "head_circ_for_age": ("hcageinf.csv", "Agemos"),       # birth-36 mo
    "bmi_for_age": ("bmiagerev.csv", "Agemos"),            # 2-20 y
    "weight_for_length": ("wtleninf.csv", "Length"),       # by length, cm
    "weight_for_stature": ("wtstat.csv", "Height"),        # by height, cm
}

# WHO biologically-implausible-value ranges, used ONLY as data-quality
# flags: (lower, upper) z-score bounds per measure.
PLAUSIBILITY_RANGES = {
    "weight_for_age": (-6.0, 5.0),
    "length_for_age": (-6.0, 6.0),
    "stature_for_age": (-6.0, 6.0),
    "weight_for_length": (-5.0, 5.0),
    "weight_for_stature": (-5.0, 5.0),
    "head_circ_for_age": (-5.0, 5.0),
    "bmi_for_age": (-5.0, 5.0),
}


def parse_sex(text):
    """Parse a sex value: M/male/1 -> 1, F/female/2 -> 2 (CDC coding)."""
    value = str(text).strip().lower()
    if value in ("1", "m", "male"):
        return 1
    if value in ("2", "f", "female"):
        return 2
    raise GrowthzError(f"unrecognised sex value {text!r}: use M/F, "
                       "male/female, or the CDC codes 1/2")


# ---------------------------------------------------------------------------
# Per-row computation
# ---------------------------------------------------------------------------

MEASURES = (
    # (output prefix, table name or chooser, grid source, value source)
    "weight_for_age", "length_for_age", "stature_for_age",
    "head_circ_for_age", "bmi_for_age", "weight_for_length",
    "weight_for_stature",
)


def _add_result(out, flags, measure, table_name, grid_value, x, grid_label):
    """Compute one z-score/percentile pair into `out`, or record why not."""
    if x is None or grid_value is None:
        return
    lms = table(table_name).lookup(out["_sex"], grid_value)
    if lms is None:
        lo, hi = table(table_name).grid_range(out["_sex"])
        out["_notes"].append(
            f"{measure} not computed: {grid_label} {grid_value:g} is "
            f"outside the CDC {table_name} grid range {lo:g}-{hi:g}")
        return
    z = lms_zscore(x, *lms)
    out[f"{measure}_z"] = z
    out[f"{measure}_percentile"] = z_to_percentile(z)
    lo_z, hi_z = PLAUSIBILITY_RANGES[measure]
    if z < lo_z or z > hi_z:
        flags.append(
            f"{measure}_z_outside_plausibility_range({lo_z:g}..{hi_z:g})")


def compute_row(sex, age_months, weight_kg=None, length_cm=None,
                height_cm=None, head_circ_cm=None, bmi=None):
    """Compute every applicable z-score for one child.

    Returns a dict with one `<measure>_z` and `<measure>_percentile`
    entry per computed measure, plus `bmi_kg_m2` when BMI was computed
    from weight and standing height, `data_quality_flags` (a list --
    data-quality statements only), and `notes` (a list of reasons any
    requested measure was not computed).
    """
    if sex not in (1, 2):
        raise GrowthzError(f"sex must be 1 (male) or 2 (female), "
                           f"got {sex!r}")
    for name, value in (("age_months", age_months),
                        ("weight_kg", weight_kg), ("length_cm", length_cm),
                        ("height_cm", height_cm),
                        ("head_circ_cm", head_circ_cm), ("bmi", bmi)):
        if value is not None and not math.isfinite(value):
            raise GrowthzError(f"{name} must be finite, got {value}")
    out = {"_sex": sex, "_notes": []}
    flags = []

    # BMI: an explicit bmi value wins; otherwise compute it from weight
    # and standing height only (CDC BMI-for-age starts at 24 months and
    # is defined on stature, not recumbent length).
    bmi_value = bmi
    if bmi_value is None and weight_kg is not None and height_cm is not None:
        bmi_value = weight_kg / (height_cm / 100.0) ** 2
        out["bmi_kg_m2"] = bmi_value

    # Weight-for-age: infant table to 36 months inclusive, older table
    # above 36 months (documented overlap policy, see module docstring).
    if weight_kg is not None and age_months is not None:
        wfa_table = ("weight_for_age_infant" if age_months <= 36
                     else "weight_for_age")
        _add_result(out, flags, "weight_for_age", wfa_table, age_months,
                    weight_kg, "age_months")
    if length_cm is not None and age_months is not None:
        _add_result(out, flags, "length_for_age", "length_for_age",
                    age_months, length_cm, "age_months")
    if height_cm is not None and age_months is not None:
        _add_result(out, flags, "stature_for_age", "stature_for_age",
                    age_months, height_cm, "age_months")
    if head_circ_cm is not None and age_months is not None:
        _add_result(out, flags, "head_circ_for_age", "head_circ_for_age",
                    age_months, head_circ_cm, "age_months")
    if bmi_value is not None and age_months is not None:
        _add_result(out, flags, "bmi_for_age", "bmi_for_age", age_months,
                    bmi_value, "age_months")
    if weight_kg is not None and length_cm is not None:
        _add_result(out, flags, "weight_for_length", "weight_for_length",
                    length_cm, weight_kg, "length_cm")
    if weight_kg is not None and height_cm is not None:
        _add_result(out, flags, "weight_for_stature", "weight_for_stature",
                    height_cm, weight_kg, "height_cm")

    out["data_quality_flags"] = flags
    out["notes"] = out.pop("_notes")
    del out["_sex"]
    return out


# ---------------------------------------------------------------------------
# Built-in reference case (CDC's own published worked example)
# ---------------------------------------------------------------------------
# CDC data-files page, worked example: a 9-month-old male weighing
# 9.7 kg. CDC looks up the WTAGEINF row at Agemos 9.5 (the half-month
# point for the whole 9th month): L = -0.1600954, M = 9.476500305,
# S = 0.11218624, and publishes Z = 0.207, the 58th percentile.
# Independent arithmetic: (9.7/9.476500305)^-0.1600954 = 1.003723...;
# (1.003723 - 1)/(-0.1600954 * 0.11218624) = 0.2074 -> Z = 0.207,
# percentile = 100 * Phi(0.2074) = 58.2 -> the 58th percentile.
KNOWN_SEX = 1
KNOWN_AGE_MONTHS = 9.5
KNOWN_WEIGHT_KG = 9.7
KNOWN_Z = 0.207
KNOWN_PERCENTILE = 58.2


def run_known_case():
    """Return (computed_z, computed_percentile) for the CDC example."""
    result = compute_row(KNOWN_SEX, KNOWN_AGE_MONTHS,
                         weight_kg=KNOWN_WEIGHT_KG)
    return result["weight_for_age_z"], result["weight_for_age_percentile"]
