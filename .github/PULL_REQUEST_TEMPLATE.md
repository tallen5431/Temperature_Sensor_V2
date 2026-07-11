<!-- Thanks for contributing! Keep PRs small and focused. -->

## What & why

<!-- What does this change, and what problem does it solve? -->

## How to test

<!-- Steps for a reviewer to verify, or the hardware path if firmware-related. -->

## Checklist

- [ ] `pytest` passes locally
- [ ] Added/updated tests for the change
- [ ] Updated `CHANGELOG.md` (and `README.md` if user-facing)
- [ ] No secrets exposed via `/api/config` or `/api/diagnostics`
- [ ] Used a module logger instead of `print()`
- [ ] Bumped `FW_VERSION` if firmware behaviour changed
