# Contributing to GPSMCPMMS

Thanks for your interest in improving GPSMCPMMS! Contributions of all kinds —
bug reports, fixes, documentation, translations and features — are welcome.

## Reporting issues

Please open a [GitHub issue](https://github.com/saiedt/gpsmcpmms/issues) with:

- what you expected and what actually happened,
- steps to reproduce (a minimal `register_params(...)` snippet helps a lot),
- your Python version and operating system.

## Development setup

```bash
git clone https://github.com/saiedt/gpsmcpmms
cd gpsmcpmms
python -m venv .venv && . .venv/bin/activate    # optional
pip install -r requirements.txt                 # Flask; needs Python 3.10+
```

Launch the editor with the small demo from the README's *Quick start* and verify
your change in the browser. The example modules under `test_app/` show how a
module declares its parameters.

## Making changes

- Keep pull requests focused — one logical change per PR.
- Match the existing code style (4-space indentation and the formatting used in
  `config.py` / `cvv_tree.py`; no external formatter is enforced).
- Update `README.md` and the guides under `docs/` when behaviour changes.
- For translations, use the CSV round-trip described in
  `docs/translation-guide.*` rather than editing `ui/lang/*.json` by hand.
- Fork the repo, create a topic branch, commit with a clear message, and open a
  pull request against `main`.

## License of contributions

GPSMCPMMS is licensed under the Apache License, Version 2.0. By submitting a
contribution you agree that it is provided under that same license (see
section 5 of the [LICENSE](LICENSE)). A `Signed-off-by` line (`git commit -s`)
is appreciated but not required.
