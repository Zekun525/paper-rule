# Release checklist

- Run unit tests and lint.
- Inspect `git status`, tracked files, staged diff, and all commit history.
- Scan for secrets and private material; verify examples are synthetic.
- Confirm the remote is a new public repository owned by the intended account.
- Confirm CI and release status from GitHub before reporting success.

GitHub CLI and npm were unavailable in the development environment at initial inspection. Do not report publication as complete without verifying it.
