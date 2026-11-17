# Data sources

All LMS tables in this directory are the official CDC percentile data
files, downloaded **verbatim** (byte-for-byte, including the CDC's own
percentile columns) on **2026-11-17** from the CDC page
"Growth Charts — Percentile Data Files with LMS Values":
https://www.cdc.gov/growthcharts/cdc-data-files.htm

Base URL for every file below:
`https://www.cdc.gov/growthcharts/data/zscore/<file>`

| File | CDC chart | Grid | Range in file |
|---|---|---|---|
| `wtageinf.csv` | Weight-for-age, birth to 36 months | Agemos | 0–36 months |
| `lenageinf.csv` | Length-for-age, birth to 36 months | Agemos | 0–35.5 months |
| `wtleninf.csv` | Weight-for-recumbent length, birth to 36 months | Length (cm) | 45–103.5 cm |
| `hcageinf.csv` | Head circumference-for-age, birth to 36 months | Agemos | 0–36 months |
| `wtage.csv` | Weight-for-age, 2 to 20 years | Agemos | 24–240 months |
| `statage.csv` | Stature-for-age, 2 to 20 years | Agemos | 24–240 months |
| `bmiagerev.csv` | BMI-for-age, 2 to 20 years | Agemos | 24–240.5 months |
| `wtstat.csv` | Weight-for-stature | Height (cm) | 77–121.5 cm |

Sex coding in the files is the CDC's: 1 = male, 2 = female. The CDC
states the data "remain unchanged from the initial release on May 30,
2000 of the growth charts". The files are US Government public data,
redistributed here unchanged so the tool works fully offline and every
number it uses can be inspected.

Reference for the method: Kuczmarski RJ et al. *2000 CDC Growth Charts
for the United States: Methods and Development.* Vital Health Stat
11(246), 2002; and Flegal KM, Cole TJ. *Construction of LMS parameters
for the Centers for Disease Control and Prevention 2000 growth chart.*
Natl Health Stat Report 63, 2013.
