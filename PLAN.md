# PLAN.md — Build the `recipe-scaler` Skill

## Goal
Build a single, narrowly-scoped Claude skill that scales recipes up or down to a target serving count or pan size, performing exact fraction math and unit conversions in a Python script. Deliver the skill folder, `SKILL.md`, the script, three test cases, and a top-level `README.md`.

This skill is for a graduate course assignment. The grader will run it in Claude Code and judge it on: clear activation, load-bearing script, correct behavior on three test prompts, and a clean walkthrough.

---

## Folder structure to create

```
.claude/
└── skills/
    └── recipe-scaler/
        ├── SKILL.md
        ├── scripts/
        │   └── scale_recipe.py
        ├── references/
        │   └── unit_conversions.md
        └── tests/
            ├── test_normal.txt
            ├── test_edge.txt
            └── test_cautious.txt

README.md   ← top-level, in repo root (not inside the skill)
```

Do not create `assets/`. We don't need it.

---

## Build order (pause points marked)

1. Create the folder structure above with empty placeholder files.
2. **PAUSE — let me review the structure.**
3. Write `scripts/scale_recipe.py` (the load-bearing piece — build this before SKILL.md so SKILL.md can describe it accurately).
4. Write `SKILL.md`.
5. Write `references/unit_conversions.md`.
6. Write the three test files in `tests/`.
7. Write the top-level `README.md`.
8. **PAUSE — I'll record the demo video and add the link to README.md myself.**

---

## What the skill does (one paragraph for SKILL.md description)

Scales a recipe to a target serving count, scale factor, or new pan size. Uses exact fraction arithmetic, promotes/demotes units to keep amounts cookable (e.g., 6 tsp → 2 tbsp), and emits warnings for ingredients that don't scale linearly (leavening, salt, yeast, eggs at fractional values). Use when a user pastes a recipe and asks to halve it, double it, fit it into a different pan, or hit a specific serving count.

---

## Script spec — `scripts/scale_recipe.py`

### CLI

```bash
python scale_recipe.py --input <path-to-json> --output <path-to-json>
```

The model writes a JSON input file, runs the script, and reads the JSON output file. No interactive prompts. No stdout parsing. JSON in, JSON out.

### Input JSON schema

```json
{
  "ingredients": [
    {"name": "all-purpose flour", "amount": "2 1/4", "unit": "cup"},
    {"name": "baking soda",       "amount": "1",     "unit": "tsp"},
    {"name": "large eggs",        "amount": "2",     "unit": null}
  ],
  "base_servings": 24,
  "scale": {
    "mode": "servings",          // one of: "servings" | "factor" | "pan"
    "target_servings": 36,       // required if mode == "servings"
    "factor": 1.5,               // required if mode == "factor"
    "from_pan": [9, 13],         // required if mode == "pan" (inches)
    "to_pan":   [8, 8]           // required if mode == "pan" (inches)
  }
}
```

Accepted `unit` values (case-insensitive, plural OK): `tsp`, `tbsp`, `cup`, `fl oz`, `oz`, `lb`, `g`, `kg`, `ml`, `l`, or `null` for countable items (eggs, cloves, lemons).

`amount` accepts: integers (`"2"`), decimals (`"1.5"`), simple fractions (`"3/4"`), or mixed numbers (`"2 1/4"`). Parse with `fractions.Fraction` for exact math.

### Output JSON schema

```json
{
  "scale_factor": "1.5",
  "scaled_ingredients": [
    {"name": "all-purpose flour", "display": "3 3/8 cup",  "amount_raw": "27/8", "unit": "cup"},
    {"name": "baking soda",       "display": "1 1/2 tsp",  "amount_raw": "3/2",  "unit": "tsp"},
    {"name": "large eggs",        "display": "3",          "amount_raw": "3",    "unit": null,
     "note": "Rounded from 3 to nearest whole egg."}
  ],
  "warnings": [
    "Leavening (baking soda) was scaled linearly. For scale factors above 2x, consider reducing leavening by ~25% of the scaled amount.",
    "Egg count rounded to a whole number; adjust other liquids slightly if texture matters."
  ],
  "notes": []
}
```

### Deterministic rules the script must implement

1. **Compute scale factor.**
   - `servings` mode: `factor = target_servings / base_servings`
   - `factor` mode: use as given
   - `pan` mode: `factor = (from_pan[0] * from_pan[1]) / (to_pan[0] * to_pan[1])` — note this gives the factor to convert *from* the original recipe *to* the new pan. Double-check the direction: a 9×13 (117 sq in) recipe poured into an 8×8 (64 sq in) needs `factor = 64/117 ≈ 0.547`.
   - Store `factor` as `Fraction` from the start (e.g., `Fraction(target_servings, base_servings)`).

2. **Scale each ingredient amount** by exact `Fraction` multiplication.

3. **Promote/demote units** when the result crosses a clean threshold. Conversion table (use these exact equivalencies):
   - `3 tsp = 1 tbsp`
   - `16 tbsp = 1 cup`
   - `1 cup = 8 fl oz`
   - `16 oz = 1 lb`
   - `1000 g = 1 kg`
   - `1000 ml = 1 l`

   Promotion rule: if scaled amount in source unit ≥ next unit's threshold *and* converts cleanly to a value with denominator ≤ 8, promote. Demote symmetrically when a scaled amount falls below 1 in the source unit and demoting yields a denominator ≤ 8.

4. **Format `display` as a human-readable cooking measurement.** Round to the nearest 1/8 for volumes < 1 cup, nearest 1/4 for ≥ 1 cup, nearest whole for counts. Render mixed numbers (`"3 3/8 cup"`, not `"27/8 cup"`). Always keep `amount_raw` as the unrounded `Fraction` as a string for auditability.

5. **Countable items (`unit: null`):** round to nearest whole integer. If the unrounded value differs from the rounded value by ≥ 0.15, add a `note` to that ingredient.

6. **Warning rules** (append to `warnings` array, not per-ingredient):
   - If `factor > 2.0` and any ingredient name matches `/baking soda|baking powder|yeast/i` → leavening warning.
   - If `factor > 2.5` and any ingredient name matches `/salt/i` → salt non-linearity warning.
   - If any countable ingredient was rounded (see rule 5) → egg/count rounding warning.
   - If `mode == "pan"` → always add a note that bake time will need adjustment (script does not compute new bake time).

7. **Refuse-to-scale guard:** if `factor > 5` or `factor < 0.2`, still compute the result but add a prominent warning that scaling beyond 5x or below 0.2x is unreliable, especially for baking. Do not error out.

### Implementation notes

- Use `from fractions import Fraction` exclusively for math. Never `float`.
- Single file, no external dependencies. Standard library only.
- Type hints required.
- Include a docstring at the top and on each function.
- Add an `if __name__ == "__main__":` guard that uses `argparse`.
- Validate input JSON shape and raise a clear `ValueError` with the offending field if malformed.

---

## SKILL.md spec

### Frontmatter (YAML)

```yaml
---
name: recipe-scaler
description: Scales a recipe to a target serving count, scale factor, or different pan size. Performs exact fraction math, promotes/demotes units (tsp↔tbsp↔cup, oz↔lb, g↔kg), and warns about ingredients that don't scale linearly (leavening, salt, yeast) or that need rounding (eggs). Use when a user pastes a recipe and asks to halve it, double it, fit it into a different pan, or hit a specific serving count.
---
```

### Body sections (in order)

1. **When to use this skill** — bullet list of trigger phrases ("scale this recipe," "halve this," "convert to an 8×8 pan," "I need this to feed 12").
2. **When NOT to use this skill** — explicit non-goals: don't suggest ingredient substitutions, don't rewrite cooking instructions, don't compute new bake times, don't adjust for altitude, don't claim the scaled recipe will taste identical.
3. **Inputs the skill expects** — the recipe (pasted text or structured), `base_servings`, and the target (servings | factor | pan).
4. **Step-by-step instructions for the model:**
   - Parse the user's recipe into the input JSON schema. If ambiguous (missing units, missing servings), ask one clarifying question before running the script.
   - Write the input JSON to a temp file.
   - Invoke `python scripts/scale_recipe.py --input <tmp_in> --output <tmp_out>`.
   - Read the output JSON and present it to the user as a clean ingredient list followed by any warnings.
   - Never do the scaling math yourself in prose. Always call the script.
5. **Expected output format for the user** — show an example: rescaled ingredient list as a table or clean list, then a "Notes" section with any warnings.
6. **Limitations** — explicit list: linear scaling assumption, baking is finicky, no bake-time adjustment, no substitution logic, max reliable range is 0.2x to 5x.

---

## `references/unit_conversions.md`

A short reference the model can pull in if it needs to remind itself of the conversion table. Keep under 30 lines. Just the equivalencies and a one-line note that the script handles all conversions automatically — the file exists so a human reader (the grader) can verify the math the script does.

---

## Three test prompts (write to `tests/`)

Each test file should contain: the user prompt, the expected behavior summary, and what to look for in the output.

### `test_normal.txt` — Normal case
**Prompt:** "Scale this chocolate chip cookie recipe from 24 to 36 cookies: 2¼ cups flour, 1 tsp baking soda, 1 tsp salt, 1 cup butter, ¾ cup sugar, ¾ cup brown sugar, 2 eggs, 2 tsp vanilla, 2 cups chocolate chips."
**Expected:** Factor = 1.5. Clean fractional output. Egg count → 3 (rounded from 3.0, no rounding note needed). No leavening warning (factor ≤ 2.0). No salt warning (factor ≤ 2.5).

### `test_edge.txt` — Edge case
**Prompt:** "Convert this 9×13 brownie recipe to fit an 8×8 pan: 2 cups sugar, 1 cup butter, 4 eggs, 1 cup cocoa, 1½ cups flour, 1 tsp baking powder, ½ tsp salt, 2 tsp vanilla."
**Expected:** Factor ≈ 0.547. Pan-area math correct. Egg count rounds 4 × 0.547 ≈ 2.19 → 2 eggs *with* rounding note (delta ≥ 0.15). Bake-time adjustment note present.

### `test_cautious.txt` — Cautious case
**Prompt:** "Scale this sourdough loaf recipe 5x: 500g bread flour, 350g water, 100g starter, 10g salt."
**Expected:** Factor = 5.0. Script runs, but warnings include the >5x is unreliable note (or hits exactly 5, edge of range — either way, a strong baking caveat). Salt warning fires (factor > 2.5). Leavening warning fires (yeast pattern matches "starter"? — no, "starter" doesn't match the regex. This is intentional: the test reveals the model should *additionally* warn the user in prose that sourdough hydration and fermentation time don't scale linearly, regardless of what the script says). The model should be cautious in its prose response and recommend batching instead of one giant loaf.

---

## Top-level `README.md` spec

Sections (in order):

1. **What this skill does** — 2–3 sentences.
2. **Why I chose this task** — 1 paragraph: code is load-bearing because of fraction arithmetic, unit cascading, pan-area ratios, and non-linear warning rules; an LLM doing this in prose drifts on digits and breaks measurements.
3. **How to use it** — show the folder location, a one-line example prompt, and what the user sees back.
4. **What the script does** — bullet summary of the seven deterministic rules, in plain English.
5. **What worked well** — leave a placeholder paragraph for me to fill in after testing.
6. **Limitations** — copy from SKILL.md's limitations section.
7. **Walkthrough video** — placeholder line: `Video: [link to be added]`.

Keep README under ~120 lines. It's documentation, not a tutorial.

---

## Out of scope (do not build)

- Ingredient substitution suggestions.
- Bake-time recalculation.
- Altitude adjustment.
- Nutritional recalculation.
- A web UI, a Streamlit app, or anything beyond the CLI script.
- Unit tests with `pytest` — the three test prompts in `tests/*.txt` are the test suite for this assignment.
- Any dependencies beyond the Python standard library.

---

## Acceptance checklist (Claude Code: verify before declaring done)

- [ ] Folder structure matches the tree above exactly.
- [ ] `SKILL.md` has YAML frontmatter with `name` and `description`.
- [ ] `description` mentions trigger conditions clearly enough that an agent could route to it.
- [ ] `scripts/scale_recipe.py` uses `Fraction` (no `float` for amounts), has type hints, has a docstring, runs from CLI with `--input` and `--output`.
- [ ] All seven deterministic rules from the script spec are implemented.
- [ ] Three test files exist in `tests/` with prompt + expected behavior.
- [ ] Top-level `README.md` exists with all seven sections.
- [ ] No files created outside the structure above.
- [ ] No external dependencies.
