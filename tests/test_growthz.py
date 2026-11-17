"""Tests for growthz.

The expected values are NOT produced by growthz itself. Each oracle
case below was computed by hand arithmetic (shown in the comments)
from the L, M, S values published in the CDC's own data files, and the
headline case is the CDC's own published worked example, verbatim.
A second, independent oracle is built into the tables themselves: the
CDC files carry smoothed percentile columns (P3, P5, ..., P97) next to
the LMS values, so feeding a published percentile value back through
the LMS formula must return that percentile's z-score.
"""

import csv
import io
import math
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from growthz import core
from growthz.cli import main

DATA_DIR = ROOT / "growthz" / "data"


def oracle_z(x, l_value, m_value, s_value):
    """The CDC LMS formula, written out again here as the test oracle."""
    if l_value != 0:
        return ((x / m_value) ** l_value - 1.0) / (l_value * s_value)
    return math.log(x / m_value) / s_value


class TestCdcWorkedExample(unittest.TestCase):
    """CDC data-files page, worked example, verbatim.

    "To obtain the weight-for-age z-score of a 9-month-old male who
    weighs 9.7 kg, we would look up the L, M and S values from the
    WTAGEINF table, which are L=-0.1600954, M=9.476500305, and
    S=0.11218624" -- CDC publishes the result as Z = 0.207, the
    58th percentile.

    Hand arithmetic: 9.7 / 9.476500305 = 1.023585...;
    1.023585 ** -0.1600954 = 0.996277... (so (X/M)^L - 1 = -0.003723);
    L * S = -0.1600954 * 0.11218624 = -0.017960...;
    Z = -0.003723 / -0.017960 = 0.2074 -> 0.207.
    Percentile = 100 * Phi(0.2074) = 58.2 -> the 58th percentile.
    """

    L, M, S = -0.1600954, 9.476500305, 0.11218624

    def test_formula_against_published_values(self):
        z = core.lms_zscore(9.7, self.L, self.M, self.S)
        self.assertAlmostEqual(z, 0.207, places=3)
        self.assertAlmostEqual(core.z_to_percentile(z), 58.2, places=1)

    def test_bundled_table_row_is_the_published_row(self):
        lms = core.table("weight_for_age_infant").lookup(1, 9.5)
        self.assertEqual(lms, (self.L, self.M, self.S))

    def test_full_pipeline_reproduces_example(self):
        z, pct = core.run_known_case()
        self.assertAlmostEqual(z, 0.207, places=3)
        self.assertAlmostEqual(pct, 58.2, places=1)

    def test_check_subcommand_passes(self):
        out = io.StringIO()
        with redirect_stdout(out):
            rc = main(["check"])
        self.assertEqual(rc, 0)
        self.assertIn("PASS", out.getvalue())


class TestOracleCases(unittest.TestCase):
    """More cases computed independently from published LMS rows.

    Each comment block shows the published row and the arithmetic;
    the asserted numbers come from that arithmetic (via oracle_z in
    this file), never from growthz's output.
    """

    def assert_case(self, sex, age, measure_kwargs, key, expected_z,
                    expected_pct):
        result = core.compute_row(sex, age, **measure_kwargs)
        self.assertAlmostEqual(result[f"{key}_z"], expected_z, places=3)
        self.assertAlmostEqual(result[f"{key}_percentile"], expected_pct,
                               places=1)

    def test_female_weight_for_age_infant(self):
        # wtageinf, sex 2, Agemos 12.5: L=-0.15640945, M=9.666089185,
        # S=0.106834517. X=11.0 kg.
        # (11/9.666089185)^-0.15640945 - 1 = -0.019581...;
        # L*S = -0.016710...; Z = 1.1979 -> 1.198; Phi -> 88.5th.
        self.assert_case(2, 12.5, {"weight_kg": 11.0}, "weight_for_age",
                         1.198, 88.5)

    def test_male_length_for_age(self):
        # lenageinf, sex 1, Agemos 12.5: L=-0.753908107, M=76.11837536,
        # S=0.038703461. X=76.0 cm -> Z=-0.040, percentile 48.4.
        self.assert_case(1, 12.5, {"length_cm": 76.0}, "length_for_age",
                         -0.040, 48.4)

    def test_female_head_circ_for_age(self):
        # hcageinf, sex 2, Agemos 6.5: L=-1.046582628, M=42.71033603,
        # S=0.029974303. X=44.0 cm -> Z=0.977, percentile 83.6.
        self.assert_case(2, 6.5, {"head_circ_cm": 44.0},
                         "head_circ_for_age", 0.977, 83.6)

    def test_female_stature_for_age(self):
        # statage, sex 2, Agemos 60.5: L=-0.057729947, M=107.9566031,
        # S=0.044276588. X=112.0 cm -> Z=0.830, percentile 79.7.
        self.assert_case(2, 60.5, {"height_cm": 112.0}, "stature_for_age",
                         0.830, 79.7)

    def test_male_bmi_for_age(self):
        # bmiagerev, sex 1, Agemos 120.5: L=-2.765648008, M=16.64613844,
        # S=0.120112464. X=18.5 -> Z=0.762, percentile 77.7.
        self.assert_case(1, 120.5, {"bmi": 18.5}, "bmi_for_age",
                         0.762, 77.7)

    def test_male_weight_for_age_older(self):
        # wtage, sex 1, Agemos 120.5: L=-1.206688407, M=32.08799062,
        # S=0.17892874. X=32.0 kg -> Z=-0.015, percentile 49.4.
        self.assert_case(1, 120.5, {"weight_kg": 32.0}, "weight_for_age",
                         -0.015, 49.4)

    def test_male_weight_for_length(self):
        # wtleninf, sex 1, Length 85.5: L=-0.81214646, M=12.01610828,
        # S=0.075868383. X=12.5 kg -> Z=0.512, percentile 69.6.
        result = core.compute_row(1, 20.0, weight_kg=12.5, length_cm=85.5)
        self.assertAlmostEqual(result["weight_for_length_z"], 0.512,
                               places=3)
        self.assertAlmostEqual(result["weight_for_length_percentile"],
                               69.6, places=1)

    def test_female_weight_for_stature(self):
        # wtstat, sex 2, Height 100.5: L=-2.563140425, M=15.5737634,
        # S=0.085322654. X=16.0 kg -> Z=0.306, percentile 62.0.
        result = core.compute_row(2, 54.0, weight_kg=16.0, height_cm=100.5)
        self.assertAlmostEqual(result["weight_for_stature_z"], 0.306,
                               places=3)
        self.assertAlmostEqual(result["weight_for_stature_percentile"],
                               62.0, places=1)

    def test_bmi_computed_from_weight_and_height(self):
        # Female, 60.5 months, 20.0 kg, 112.0 cm:
        # BMI = 20 / 1.12^2 = 15.943878...
        # bmiagerev sex 2 Agemos 60.5: L=-3.35007771, M=15.15188405,
        # S=0.084300139 -> Z=0.556, percentile 71.1.
        result = core.compute_row(2, 60.5, weight_kg=20.0, height_cm=112.0)
        self.assertAlmostEqual(result["bmi_kg_m2"], 15.94, places=2)
        self.assertAlmostEqual(result["bmi_for_age_z"], 0.556, places=3)
        self.assertAlmostEqual(result["bmi_for_age_percentile"], 71.1,
                               places=1)


class TestInterpolation(unittest.TestCase):
    """Documented policy: linear interpolation of L, M, S between rows.

    Male weight-for-age at exactly 9.0 months sits halfway between the
    published Agemos 8.5 row (L=-0.1334091, M=9.081119817,
    S=0.113217163) and the 9.5 row (L=-0.1600954, M=9.476500305,
    S=0.11218624). Interpolated: L=-0.14675225, M=9.278810061,
    S=0.1127017015. For X=9.7: Z=0.393, percentile 65.3 (hand
    arithmetic via the same LMS formula on the interpolated values).
    """

    def test_midpoint_interpolation(self):
        lms = core.table("weight_for_age_infant").lookup(1, 9.0)
        self.assertAlmostEqual(lms[0], -0.14675225, places=8)
        self.assertAlmostEqual(lms[1], 9.278810061, places=8)
        self.assertAlmostEqual(lms[2], 0.1127017015, places=9)
        result = core.compute_row(1, 9.0, weight_kg=9.7)
        self.assertAlmostEqual(result["weight_for_age_z"], 0.393, places=3)
        self.assertAlmostEqual(result["weight_for_age_percentile"], 65.3,
                               places=1)

    def test_no_extrapolation(self):
        tbl = core.table("weight_for_age_infant")
        self.assertIsNone(tbl.lookup(1, -0.5))
        self.assertIsNone(tbl.lookup(1, 36.5))
        self.assertIsNotNone(tbl.lookup(1, 36.0))


class TestFormulaBranches(unittest.TestCase):
    def test_l_zero_branch(self):
        # No CDC row has L exactly 0, so the ln branch is tested with
        # synthetic parameters: ln(11/10)/0.1 = 0.953102, Phi -> 83.0.
        z = core.lms_zscore(11.0, 0.0, 10.0, 0.1)
        self.assertAlmostEqual(z, 0.953102, places=6)
        self.assertAlmostEqual(core.z_to_percentile(z), 83.0, places=1)

    def test_median_gives_zero(self):
        result = core.compute_row(1, 9.5, weight_kg=9.476500305)
        self.assertAlmostEqual(result["weight_for_age_z"], 0.0, places=9)
        self.assertAlmostEqual(result["weight_for_age_percentile"], 50.0,
                               places=9)

    def test_nonpositive_measurement_rejected(self):
        with self.assertRaises(core.GrowthzError):
            core.lms_zscore(0.0, 1.0, 10.0, 0.1)
        with self.assertRaises(core.GrowthzError):
            core.lms_zscore(-1.0, 1.0, 10.0, 0.1)


class TestBundledTablesAgainstCdcPercentileColumns(unittest.TestCase):
    """Independent oracle: the CDC's own smoothed percentile columns.

    For sampled rows of every bundled table, feeding the published P5
    value through the LMS formula must give z ~= -1.645, P50 z ~= 0,
    and P97 z ~= +1.881 (tolerance covers the files' rounding).
    """

    EXPECTED_ROWS = {
        "wtageinf.csv": 76, "lenageinf.csv": 74, "wtleninf.csv": 120,
        "hcageinf.csv": 76, "wtage.csv": 436, "statage.csv": 436,
        "bmiagerev.csv": 438, "wtstat.csv": 92,
    }

    def test_row_counts(self):
        for filename, expected in self.EXPECTED_ROWS.items():
            with open(DATA_DIR / filename, newline="",
                      encoding="utf-8-sig") as handle:
                rows = [r for r in csv.DictReader(handle)
                        if r["Sex"] in ("1", "2")]
            self.assertEqual(len(rows), expected, filename)

    def test_percentile_columns_agree_with_lms(self):
        for filename in self.EXPECTED_ROWS:
            with open(DATA_DIR / filename, newline="",
                      encoding="utf-8-sig") as handle:
                rows = [r for r in csv.DictReader(handle)
                        if r["Sex"] in ("1", "2")]
            for row in rows[::17]:  # sample across sexes and grid
                l_v, m_v, s_v = (float(row["L"]), float(row["M"]),
                                 float(row["S"]))
                self.assertAlmostEqual(
                    oracle_z(float(row["P50"]), l_v, m_v, s_v), 0.0,
                    places=6, msg=filename)
                self.assertAlmostEqual(
                    oracle_z(float(row["P5"]), l_v, m_v, s_v), -1.645,
                    delta=0.01, msg=filename)
                self.assertAlmostEqual(
                    oracle_z(float(row["P97"]), l_v, m_v, s_v), 1.881,
                    delta=0.01, msg=filename)


class TestFlagsAndRanges(unittest.TestCase):
    def test_extreme_value_flagged_as_data_quality(self):
        # Male, 9.5 months, 30 kg: Z = 9.38 (hand arithmetic on the
        # published row), outside the WHO plausibility range -6..+5.
        result = core.compute_row(1, 9.5, weight_kg=30.0)
        self.assertAlmostEqual(result["weight_for_age_z"], 9.380, places=2)
        self.assertTrue(any("weight_for_age" in f
                            for f in result["data_quality_flags"]))

    def test_normal_row_has_no_flags(self):
        result = core.compute_row(1, 9.5, weight_kg=9.7)
        self.assertEqual(result["data_quality_flags"], [])

    def test_out_of_range_age_gives_note_not_crash(self):
        result = core.compute_row(1, 300.0, weight_kg=80.0)
        self.assertNotIn("weight_for_age_z", result)
        self.assertTrue(any("weight_for_age" in n
                            for n in result["notes"]))

    def test_sex_parsing(self):
        for text in ("M", "m", "male", "Male", "1"):
            self.assertEqual(core.parse_sex(text), 1)
        for text in ("F", "f", "female", "Female", "2"):
            self.assertEqual(core.parse_sex(text), 2)
        with self.assertRaises(core.GrowthzError):
            core.parse_sex("X")


class TestCli(unittest.TestCase):
    def run_cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = main(argv)
        return rc, out.getvalue(), err.getvalue()

    def write_csv(self, directory, name, text):
        path = Path(directory) / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_convert_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = self.write_csv(
                tmp, "in.csv",
                "id,sex,age_months,weight_kg,length_cm,head_circ_cm\n"
                "a1,M,9.5,9.7,72.0,45.0\n"
                "a2,F,12.5,11.0,,44.5\n")
            out_path = Path(tmp) / "out.csv"
            rc, out, _ = self.run_cli(
                ["convert", str(src), "--out", str(out_path)])
            self.assertEqual(rc, 0)
            self.assertIn("processed 2 rows", out)
            with open(out_path, newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["weight_for_age_z"], "0.207")
            self.assertEqual(rows[0]["weight_for_age_percentile"], "58.2")
            self.assertEqual(rows[0]["id"], "a1")  # columns carried through
            self.assertEqual(rows[1]["weight_for_age_z"], "1.198")

    def test_bad_row_is_noted_not_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = self.write_csv(
                tmp, "in.csv",
                "sex,age_months,weight_kg\n"
                "M,9.5,9.7\n"
                "X,9.5,9.7\n"
                "F,notanumber,9.0\n")
            out_path = Path(tmp) / "out.csv"
            rc, out, _ = self.run_cli(
                ["convert", str(src), "--out", str(out_path)])
            self.assertEqual(rc, 0)
            self.assertIn("computed z-scores for 1 rows", out)
            with open(out_path, newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertIn("unrecognised sex", rows[1]["notes"])
            self.assertIn("not a number", rows[2]["notes"])

    def test_missing_required_column_is_clean_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = self.write_csv(tmp, "in.csv", "sex,weight_kg\nM,9.7\n")
            rc, _, err = self.run_cli(["convert", str(src)])
            self.assertEqual(rc, 2)
            self.assertIn("age_months", err)
            self.assertNotIn("Traceback", err)

    def test_missing_and_empty_files_are_clean_errors(self):
        rc, _, err = self.run_cli(["convert", "/nonexistent/nope.csv"])
        self.assertEqual(rc, 2)
        self.assertIn("not found", err)
        with tempfile.TemporaryDirectory() as tmp:
            src = self.write_csv(tmp, "empty.csv", "")
            rc, _, err = self.run_cli(["convert", str(src)])
            self.assertEqual(rc, 2)
            self.assertNotIn("Traceback", err)

    def test_no_subcommand_prints_help(self):
        rc, _, _ = self.run_cli([])
        self.assertEqual(rc, 2)

    def test_module_invocation(self):
        proc = subprocess.run(
            [sys.executable, "-m", "growthz", "check"],
            cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("PASS", proc.stdout)


class TestAdversarialReviewRegressions(unittest.TestCase):
    """Regressions from the independent adversarial review (REVIEW.md).

    Each test pins a defect the review actually reproduced against the
    pre-fix code: non-finite values flowing into z-scores, one extreme
    row aborting a whole batch via OverflowError, and surplus CSV
    fields aborting the run at write time.
    """

    def run_cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = main(argv)
        return rc, out.getvalue(), err.getvalue()

    def write_csv(self, directory, name, text):
        path = Path(directory) / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_lms_zscore_rejects_nonfinite(self):
        for bad in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(core.GrowthzError):
                core.lms_zscore(bad, 1.0, 10.0, 0.1)

    def test_lms_zscore_overflow_is_signed_inf_not_crash(self):
        # (1e200 / 3.53) ** 1.815 overflows a float; the true z is
        # beyond range in the + direction (L > 0). Used to raise a raw
        # OverflowError out of compute_row.
        z = core.lms_zscore(1e200, 1.815151075, 3.530203168, 0.152385273)
        self.assertEqual(z, math.inf)
        self.assertEqual(core.z_to_percentile(z), 100.0)

    def test_compute_row_rejects_bad_sex_and_nonfinite(self):
        with self.assertRaises(core.GrowthzError):
            core.compute_row(3, 9.5, weight_kg=9.7)
        with self.assertRaises(core.GrowthzError):
            core.compute_row(1, float("nan"), weight_kg=9.7)
        with self.assertRaises(core.GrowthzError):
            core.compute_row(1, 9.5, weight_kg=float("inf"))

    def test_nonfinite_csv_values_are_bad_rows_not_nan_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = self.write_csv(
                tmp, "in.csv",
                "sex,age_months,weight_kg\n"
                "M,9.5,nan\n"
                "M,inf,9.7\n"
                "F,12.5,11.0\n")
            out_path = Path(tmp) / "out.csv"
            rc, out, _ = self.run_cli(
                ["convert", str(src), "--out", str(out_path)])
            self.assertEqual(rc, 0)
            self.assertIn("computed z-scores for 1 rows", out)
            with open(out_path, newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertIn("not a finite number", rows[0]["notes"])
            self.assertIn("not a finite number", rows[1]["notes"])
            self.assertEqual(rows[2]["weight_for_age_z"], "1.198")
            self.assertNotIn("nan", rows[0]["weight_for_age_z"])

    def test_extreme_row_does_not_abort_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = self.write_csv(
                tmp, "in.csv",
                "sex,age_months,weight_kg\n"
                "M,0,1e200\n"
                "F,9.5,9.0\n")
            out_path = Path(tmp) / "out.csv"
            rc, out, _ = self.run_cli(
                ["convert", str(src), "--out", str(out_path)])
            self.assertEqual(rc, 0)
            with open(out_path, newline="") as handle:
                rows = list(csv.DictReader(handle))
            # Extreme row: flagged as a data-quality problem, not fatal.
            self.assertIn("weight_for_age", rows[0]["data_quality_flags"])
            # The ordinary row behind it is still computed.
            self.assertEqual(rows[1]["weight_for_age_z"], "0.316")

    def test_extra_fields_beyond_header_are_ignored_with_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = self.write_csv(
                tmp, "in.csv",
                "sex,age_months,weight_kg\n"
                "M,9.5,9.7,EXTRA\n")
            out_path = Path(tmp) / "out.csv"
            rc, out, _ = self.run_cli(
                ["convert", str(src), "--out", str(out_path)])
            self.assertEqual(rc, 0)
            self.assertIn("extra field(s)", out)
            with open(out_path, newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["weight_for_age_z"], "0.207")


if __name__ == "__main__":
    unittest.main()
