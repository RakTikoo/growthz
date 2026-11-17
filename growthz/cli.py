"""Command-line interface for growthz.

Subcommands:
  growthz convert FILE [--out FILE]  -- append z-scores/percentiles
  growthz check                       -- verify against CDC's worked example

Input CSV columns:
  sex          required: M/F, male/female, or CDC codes 1/2
  age_months   required: age in months (decimal is fine; L, M, S are
               linearly interpolated between CDC table rows -- see
               README "Age handling")
  weight_kg, length_cm (recumbent), height_cm (standing stature),
  head_circ_cm, bmi   -- optional measurements; every measure with
               enough inputs gets a z-score and percentile

All other columns are carried through untouched. Rows with a bad value
do not abort the run: the row is written with a note explaining the
problem. Structural problems (missing required columns, empty file)
are errors.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

from . import core
from .core import GrowthzError

REQUIRED_COLUMNS = ("sex", "age_months")
MEASURE_COLUMNS = ("weight_kg", "length_cm", "height_cm", "head_circ_cm",
                   "bmi")

RESULT_COLUMNS = (
    "bmi_kg_m2",
    "weight_for_age_z", "weight_for_age_percentile",
    "length_for_age_z", "length_for_age_percentile",
    "stature_for_age_z", "stature_for_age_percentile",
    "head_circ_for_age_z", "head_circ_for_age_percentile",
    "bmi_for_age_z", "bmi_for_age_percentile",
    "weight_for_length_z", "weight_for_length_percentile",
    "weight_for_stature_z", "weight_for_stature_percentile",
    "data_quality_flags", "notes",
)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="growthz",
        description="Compute CDC growth z-scores and percentiles for a "
                    "CSV of child measurements (CDC LMS method). Research "
                    "and education only -- not a medical device.")
    sub = parser.add_subparsers(dest="command")

    conv = sub.add_parser(
        "convert", help="append z-scores/percentiles to a measurements CSV")
    conv.add_argument("file", help="input CSV (columns: sex, age_months, "
                                   "and any of weight_kg, length_cm, "
                                   "height_cm, head_circ_cm, bmi)")
    conv.add_argument("--out", default=None,
                      help="output file (default: <input>_growthz.csv)")

    sub.add_parser("check", help="verify the calculator against the CDC's "
                                 "published worked example")
    return parser


def _parse_float(text, column, row_number):
    if text is None or str(text).strip() == "":
        return None
    try:
        value = float(text)
    except ValueError:
        raise GrowthzError(f"row {row_number}: column '{column}' value "
                           f"{text!r} is not a number")
    if not math.isfinite(value):
        # float() happily parses 'nan', 'inf', '1e999' -- none of those
        # is a measurement, and a NaN used to flow through into NaN
        # z-scores that were silently counted as computed.
        raise GrowthzError(f"row {row_number}: column '{column}' value "
                           f"{text!r} is not a finite number")
    return value


def _convert_row(row, row_number):
    """Return (result_dict, problem_or_None) for one input row."""
    try:
        sex = core.parse_sex(row.get("sex", ""))
    except GrowthzError as exc:
        return None, f"row {row_number}: {exc}"
    values = {}
    for column in ("age_months",) + MEASURE_COLUMNS:
        try:
            values[column] = _parse_float(row.get(column), column,
                                          row_number)
        except GrowthzError as exc:
            return None, str(exc)
    if values["age_months"] is None:
        return None, f"row {row_number}: age_months is empty"
    if values["age_months"] < 0:
        return None, f"row {row_number}: age_months is negative"
    for column in MEASURE_COLUMNS:
        if values[column] is not None and values[column] <= 0:
            return None, (f"row {row_number}: {column} must be positive, "
                          f"got {values[column]:g}")
    try:
        result = core.compute_row(
            sex, values["age_months"],
            weight_kg=values["weight_kg"], length_cm=values["length_cm"],
            height_cm=values["height_cm"],
            head_circ_cm=values["head_circ_cm"], bmi=values["bmi"])
    except (GrowthzError, ArithmeticError, ValueError) as exc:
        # A single row's numeric surprise must never abort the batch.
        return None, f"row {row_number}: {exc}"
    return result, None


def _format_result(result):
    formatted = {}
    for column in RESULT_COLUMNS:
        if column == "data_quality_flags":
            formatted[column] = "; ".join(result.get("data_quality_flags",
                                                     []))
        elif column == "notes":
            formatted[column] = "; ".join(result.get("notes", []))
        elif column == "bmi_kg_m2":
            value = result.get(column)
            formatted[column] = "" if value is None else f"{value:.2f}"
        else:
            value = result.get(column)
            if value is None:
                formatted[column] = ""
            elif column.endswith("_percentile"):
                formatted[column] = f"{value:.1f}"
            else:
                formatted[column] = f"{value:.3f}"
    return formatted


def cmd_convert(args):
    path = Path(args.file)
    if not path.is_file():
        raise GrowthzError(f"input file not found: {args.file}")
    if path.stat().st_size == 0:
        raise GrowthzError(f"input file is empty: {args.file}")
    try:
        with open(path, newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames or []
            rows = list(reader)
    except Exception as exc:
        raise GrowthzError(f"could not read {args.file} as CSV: {exc}")
    missing = [c for c in REQUIRED_COLUMNS if c not in fieldnames]
    if missing:
        raise GrowthzError(
            f"{args.file} is missing required column(s): "
            + ", ".join(missing)
            + f". Available columns: {', '.join(fieldnames)}")
    if not rows:
        raise GrowthzError(f"{args.file} contains no data rows: "
                           "nothing to compute.")
    collisions = [c for c in RESULT_COLUMNS if c in fieldnames]
    if collisions:
        raise GrowthzError(
            "the input already has column(s) this tool would write: "
            + ", ".join(collisions)
            + ". Rename or remove them first.")

    out_path = Path(args.out) if args.out else path.with_name(
        path.stem + "_growthz.csv")
    problems = []
    computed = 0
    flagged = 0
    out_rows = []
    for i, row in enumerate(rows, start=2):  # line 1 is the header
        if None in row:
            # DictReader parks fields beyond the header under the None
            # key; they used to abort the whole run at write time with
            # a cryptic DictWriter error. Ignore the surplus, warn.
            problems.append(f"row {i}: extra field(s) beyond the "
                            "header were ignored")
            row = {k: v for k, v in row.items() if k is not None}
        result, problem = _convert_row(row, i)
        new_row = dict(row)
        if problem is not None:
            problems.append(problem)
            formatted = _format_result({})
            formatted["notes"] = problem
            new_row.update(formatted)
        else:
            if any(key.endswith("_z") for key in result):
                computed += 1
            if result.get("data_quality_flags"):
                flagged += 1
            new_row.update(_format_result(result))
        out_rows.append(new_row)
    try:
        with open(out_path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle,
                                    fieldnames=fieldnames + list(RESULT_COLUMNS))
            writer.writeheader()
            writer.writerows(out_rows)
    except Exception as exc:
        raise GrowthzError(f"could not write output file {out_path}: {exc}")

    print(f"processed {len(rows)} rows from {args.file}")
    print(f"  computed z-scores for {computed} rows; "
          f"{flagged} rows carry a data-quality flag (see README)")
    print(f"  reference : CDC 2000 growth charts (LMS), CDC only in v1")
    print(f"  output    : {out_path}")
    for problem in problems:
        print(f"  warning   : {problem}")
    return 0


def cmd_check(_args):
    computed_z, computed_pct = core.run_known_case()
    print("growthz check -- CDC published worked example")
    print("  input   : 9-month-old male, weight 9.7 kg "
          "(CDC WTAGEINF row Agemos 9.5: L=-0.1600954, M=9.476500305, "
          "S=0.11218624)")
    print(f"  computed: Z {computed_z:.3f}, percentile {computed_pct:.1f}")
    print(f"  expected: Z {core.KNOWN_Z:.3f}, percentile "
          f"{core.KNOWN_PERCENTILE:.1f} (CDC data-files page: Z = 0.207, "
          "58th percentile)")
    if (abs(computed_z - core.KNOWN_Z) < 0.0005
            and abs(computed_pct - core.KNOWN_PERCENTILE) < 0.05):
        print("  result  : PASS")
        return 0
    print("  result  : FAIL")
    return 1


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help(sys.stderr)
        return 2
    try:
        if args.command == "convert":
            return cmd_convert(args)
        if args.command == "check":
            return cmd_check(args)
    except GrowthzError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # user errors must never show a traceback
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
