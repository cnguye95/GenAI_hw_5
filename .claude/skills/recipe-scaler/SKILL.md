---
name: recipe-scaler
description: Scales a recipe to a target serving count, scale factor, or different pan size. Performs exact fraction math, promotes/demotes units (tsp↔tbsp↔cup, oz↔lb, g↔kg), and warns about ingredients that don't scale linearly (leavening, salt, yeast) or that need rounding (eggs). Use when a user pastes a recipe and asks to halve it, double it, fit it into a different pan, or hit a specific serving count.
---

# recipe-scaler

A skill for scaling recipes by exact fraction arithmetic. The math lives in
`scripts/scale_recipe.py` — never compute scaled amounts in prose.

## When to use this skill

Activate when a user is scaling a recipe and the request matches any of:

- "scale this recipe to N servings / N cookies / N portions"
- "halve this", "double this", "1.5x this", "third this recipe"
- "convert this to an 8×8 pan" (or any pan-size change)
- "I need this to feed 12 people"
- "make this for 4 instead of 6"
- The user pastes a recipe and asks for a different yield

## When NOT to use this skill

Do not activate (or stop and decline) if the user is asking for:

- Ingredient substitutions (gluten-free swaps, dairy-free, etc.)
- Rewriting cooking instructions or method
- New bake time, oven temperature, or altitude adjustment
- Nutritional recalculation
- A claim that the scaled recipe will taste identical
- Anything other than scaling amounts up or down

If the user wants both a scale and a substitution, scale first, then say
substitutions are out of scope for this skill.

## Inputs the skill expects

To call the script, the model needs:

1. **The recipe** as a list of ingredients with name, amount, and unit. Pasted
   text is fine — parse it into the structured form below.
2. **`base_servings`** — the original yield, if the user is scaling by serving
   count. Skip if the user is scaling by factor or pan size.
3. **The scale target**, one of:
   - `servings` mode: a target serving count
   - `factor` mode: an explicit multiplier (e.g., `0.5`, `2`, `1.5`)
   - `pan` mode: from-pan and to-pan dimensions in inches

If the recipe is missing units or `base_servings` is unclear, ask **one**
clarifying question before running the script. Do not guess.

## Step-by-step instructions

1. **Parse** the user's recipe into the input JSON schema below. Use `null`
   for the unit on countable items (eggs, lemons, cloves of garlic).

2. **Write** the JSON to a temp file (e.g., via the `Write` tool to a path like
   `/tmp/recipe_in.json` or the OS-appropriate temp dir).

3. **Invoke** the script:
   ```
   python .claude/skills/recipe-scaler/scripts/scale_recipe.py \
     --input <tmp_in.json> --output <tmp_out.json>
   ```

4. **Read** the output JSON.

5. **Present** the result to the user as a clean, readable ingredient list,
   followed by any warnings. Use the `display` field for each ingredient — that
   is the human-readable form. Then list the contents of the `warnings` array
   under a "Notes" heading. Add a brief prose caveat of your own only if the
   situation calls for one (e.g., 5x sourdough — see Limitations).

**Never** do the scaling math yourself in prose. The whole point of the skill
is that fraction math, unit cascades, and pan-area ratios are easy to get
wrong in language. Always call the script.

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
    "mode": "servings",
    "target_servings": 36
  }
}
```

For `factor` mode, replace `scale` with `{"mode": "factor", "factor": "1.5"}`.
For `pan` mode, replace it with
`{"mode": "pan", "from_pan": [9, 13], "to_pan": [8, 8]}` (inches).

`amount` accepts integers (`"2"`), decimals (`"1.5"`), simple fractions
(`"3/4"`), and mixed numbers (`"2 1/4"`).

Accepted units (case-insensitive, plurals OK): `tsp`, `tbsp`, `cup`, `fl oz`,
`oz`, `lb`, `g`, `kg`, `ml`, `l`, or `null` for countable items.

### Output JSON schema

```json
{
  "scale_factor": "1.5",
  "scaled_ingredients": [
    {"name": "all-purpose flour", "display": "3 3/8 cup", "amount_raw": "27/8", "unit": "cup"},
    {"name": "large eggs",        "display": "3",         "amount_raw": "3",    "unit": null}
  ],
  "warnings": [...],
  "notes": []
}
```

`display` is the cooking-ready string. `amount_raw` is the unrounded exact
fraction in the final unit (for auditability). `warnings` is a list of strings
the model should surface to the user verbatim.

## Expected output format for the user

Render the result as:

> **Scaled recipe (factor: 1.5)**
>
> | Ingredient | Amount |
> |---|---|
> | all-purpose flour | 3 3/8 cup |
> | baking soda | 1 1/2 tsp |
> | large eggs | 3 |
>
> **Notes**
> - (warnings here, one per line)

A bullet list is also fine. The key is: clean ingredient list first,
then warnings. Do not embed warnings inside the ingredient list.

## Limitations

- **Linear scaling assumption.** The script multiplies every amount by the
  same factor. Real recipes don't always behave this way — leavening, salt,
  spice, and hydration ratios are non-linear in subtle ways.
- **Baking is finicky.** Below ~0.5x or above ~2x, baked-good ratios start to
  drift. The script flags this but does not correct it.
- **Reliable range: 0.2x to 5x.** Outside this range the script still computes
  a result but adds a strong warning. For sourdough or bread at 5x, also tell
  the user in prose to consider multiple smaller batches — fermentation and
  hydration don't scale.
- **No bake-time adjustment.** Pan changes especially change bake time. The
  script tells the user this but does not compute new times.
- **No substitutions.** The skill never suggests ingredient swaps.
- **No altitude or humidity adjustments.**
- **Eggs are integers.** A 0.547x scale of 4 eggs becomes 2 eggs with a note;
  it does not become 2.19 eggs.
