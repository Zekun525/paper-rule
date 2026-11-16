# Testing

Run `pytest -q` for offline governance, scope filtering, and API smoke tests. Tests use temporary directories and synthetic content. Install optional lint tools via `python -m pip install -e ".[dev]"`, then run `python -m ruff check src tests`. Browser E2E, real model evaluation, privacy-history scanning, and installation-on-clean-machine tests are still outstanding.
