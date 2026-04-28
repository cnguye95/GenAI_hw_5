# recipe-scaler

A Claude skill that scales recipes by exact fractional arithmetic.

## Walkthrough video

Video: https://youtu.be/wq8lUhXBWjQ

## What this skill does

Given a recipe and a target — a new serving count, a scale factor, or a new
pan size — the skill produces a rescaled ingredient list with cooking-friendly
fractions, automatic unit promotion (e.g., 6 tsp → 2 tbsp), and warnings for
ingredients that don't scale linearly (leavening, salt, eggs).

## Why I chose this task

Recipe scaling looks trivial, but the math is precisely the kind of thing an
LLM gets subtly wrong in prose: 2¼ × 1.5 is 27/8 (= 3 3/8), not 3.4; 6 tsp is
2 tbsp, not "about 2 tbsp"; a 9×13 pan poured into an 8×8 pan needs a factor
of 64/117 ≈ 0.547, not "a little more than half." Pushing the math out to a
Python script with `fractions.Fraction` keeps the digits exact, makes unit
cascading deterministic, and prevents the model from confidently muddling
half-tablespoons. The non-linear warning rules (don't blindly 5x the salt,
fractional eggs need rounding) are exactly the kind of structured, finicky
logic that belongs in code rather than prose.

## How to use it

The skill lives in `.claude/skills/recipe-scaler/`. Once it's available,
ask Claude things like:

- "Halve this banana bread recipe: ..."
- "Scale this cookie recipe from 24 to 36 servings: ..."
- "Convert this brownie recipe from a 9×13 to an 8×8 pan: ..."
- "I need this for 8 people, it's written for 4: ..."

Claude will parse your recipe into structured form, run the script, and
return a clean ingredient list followed by any warnings.

Example one-liner:

> **You:** *"Scale this from 24 to 36 cookies: 2¼ cups flour, 1 tsp baking soda, 2 tsp vanilla, 2 eggs, 2 cups chocolate chips."*
>
> **Claude:** *(invokes script)* "Here's the scaled recipe (factor 1.5):
> flour 3 3/8 cup, baking soda 1 1/2 tsp, vanilla 1 tbsp, eggs 3, chocolate
> chips 3 cup. No warnings."

## What the script does

The load-bearing piece is `scripts/scale_recipe.py`. It reads JSON, writes
JSON, and implements seven deterministic rules:

1. **Computes the scale factor** as a `Fraction` — from servings, an explicit
   factor, or the ratio of pan areas (`to_area / from_area`).
2. **Multiplies each ingredient amount** by exact fraction arithmetic. No
   floats touch the amounts.
3. **Promotes/demotes units** along the cascade tsp ↔ tbsp ↔ cup, oz ↔ lb,
   g ↔ kg, ml ↔ l — but only when the result has a denominator ≤ 8 (so the
   measurement stays cookable).
4. **Formats the display** as a mixed-number string ("3 3/8 cup", not
   "27/8 cup"), rounded to 1/8 for volumes and 1/4 for imperial weights.
5. **Rounds countable items** (eggs, lemons, cloves) to whole numbers, and
   adds a per-ingredient note if the unrounded value differed by ≥ 0.15.
6. **Emits warnings** for non-linear scaling cases: leavening above 2x, salt
   above 2.5x, any rounded count, and any pan-size change (always adds a
   bake-time note).
7. **Flags out-of-range factors** (above 5x or below 0.2x) with a strong
   reliability caveat — but still computes the result.

All amount math uses `fractions.Fraction`. No external dependencies.

## What worked well

The script executes cleanly and quickly. The JSON conversions work to show that the model is behaving as expected.
Also, the JSON output shows some reasoning in edge cases like with eggs (cannot be rounded).


## Limitations

- **Linear scaling assumption.** The script multiplies every amount by the
  same factor; real recipes don't always behave that way.
- **Baking is finicky.** Outside ~0.5x to ~2x, baked-good ratios drift.
- **Reliable range: 0.2x to 5x.** The script computes outside this range but
  flags it strongly. For sourdough or bread at 5x, prefer multiple batches.
- **No bake-time adjustment.** Pan changes especially change bake time.
- **No substitutions, altitude, or nutrition.** Out of scope.
- **Eggs are integers.** A 0.547x scale of 4 eggs becomes 2, not 2.19.


