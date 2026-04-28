# Project Conventions

- Python 3.11+, standard library only. Ask before adding any dependency.
- All scripts use type hints and a top-of-file docstring.
- Skills live in `.claude/skills/<skill-name>/`.
- Use `fractions.Fraction` for any exact arithmetic — never `float` for amounts.
- When in doubt about scope, re-read `PLAN.md` and ask before expanding.
- Pause at any explicit "PAUSE" marker in `PLAN.md` and wait for confirmation.