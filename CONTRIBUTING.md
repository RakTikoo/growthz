# Contributing

Thanks for looking. growthz is a small, single-purpose tool; these
house rules keep changes easy to review.

> **Research and educational tool only. Not a medical device.**
> Arithmetic against published CDC tables only — no diagnosis,
> interpretation or recommendation.

## Run the tests

```console
$ python3 run_tests.py
```

All tests must pass before a change is considered. Add tests in `tests/`
for any new behaviour. New oracle cases must be computed by hand from
published LMS rows, with the arithmetic shown in the test comments —
never values produced by the tool itself.

## House rules

- Keep the tool single-purpose and dependency-free (standard library
  only).
- The bundled tables in `growthz/data/` are verbatim copies of the
  CDC's published files. Never edit them; if a table needs replacing,
  replace the whole file from the CDC source and update
  `growthz/data/SOURCES.md`.
- No diagnosis, assessment, categories or advice — numbers only, by
  design. Pull requests adding interpretation will not be accepted.
- Do not mix references: CDC and WHO tables, rules and flags stay
  separate, each named in the output it produced.
- The README's Honest limits section is a promise. If a change alters
  a documented limit or behaviour, update the README in the same pull
  request — and SKILL.md too if the CLI, its flags or its exit codes
  changed.
- Plain words in docs and messages. No marketing language.

## Claiming an issue

Comment on the issue saying you are taking it, then open a pull request
that mentions the issue number.
