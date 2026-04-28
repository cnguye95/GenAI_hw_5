"""scale_recipe.py — Scale a recipe with exact fraction arithmetic.

Reads a JSON recipe spec, scales every ingredient amount by an exact
fractional factor (computed from a target serving count, an explicit factor,
or a pan-size change), promotes/demotes units to keep results cookable,
and emits warnings for ingredients that don't scale linearly.

Usage:
    python scale_recipe.py --input <path-to-input.json> --output <path-to-output.json>

Standard library only. All amount math uses fractions.Fraction; floats are
never used for ingredient amounts.
"""

from __future__ import annotations

import argparse
import json
import re
from fractions import Fraction
from pathlib import Path
from typing import Any


PROMOTE_TABLE: dict[str, tuple[str, Fraction]] = {
    "tsp":   ("tbsp", Fraction(3)),
    "tbsp":  ("cup",  Fraction(16)),
    "fl oz": ("cup",  Fraction(8)),
    "oz":    ("lb",   Fraction(16)),
    "g":     ("kg",   Fraction(1000)),
    "ml":    ("l",    Fraction(1000)),
}

DEMOTE_TABLE: dict[str, tuple[str, Fraction]] = {
    "tbsp": ("tsp",  Fraction(3)),
    "cup":  ("tbsp", Fraction(16)),
    "lb":   ("oz",   Fraction(16)),
    "kg":   ("g",    Fraction(1000)),
    "l":    ("ml",   Fraction(1000)),
}

VALID_UNITS: set[str] = {"tsp", "tbsp", "cup", "fl oz", "oz", "lb", "g", "kg", "ml", "l"}

UNIT_ALIASES: dict[str, str] = {
    "teaspoon": "tsp", "teaspoons": "tsp", "tsp.": "tsp",
    "tablespoon": "tbsp", "tablespoons": "tbsp", "tbsp.": "tbsp", "tbs": "tbsp",
    "cups": "cup", "c": "cup",
    "fluid ounce": "fl oz", "fluid ounces": "fl oz", "fl. oz.": "fl oz", "floz": "fl oz",
    "ounce": "oz", "ounces": "oz", "oz.": "oz",
    "pound": "lb", "pounds": "lb", "lbs": "lb", "lb.": "lb",
    "gram": "g", "grams": "g",
    "kilogram": "kg", "kilograms": "kg",
    "milliliter": "ml", "milliliters": "ml", "millilitre": "ml", "millilitres": "ml",
    "liter": "l", "liters": "l", "litre": "l", "litres": "l",
}

LEAVENING_RE = re.compile(r"baking soda|baking powder|yeast", re.IGNORECASE)
SALT_RE = re.compile(r"salt", re.IGNORECASE)


def parse_amount(value: Any) -> Fraction:
    """Parse an amount into an exact Fraction.

    Accepts integers, floats (via decimal-string conversion), and strings of the
    form '2', '1.5', '3/4', or '2 1/4'.
    """
    if isinstance(value, bool):
        raise ValueError(f"amount must not be a boolean: {value!r}")
    if isinstance(value, int):
        return Fraction(value)
    if isinstance(value, float):
        return Fraction(str(value))
    if not isinstance(value, str):
        raise ValueError(f"amount must be string, int, or float; got {type(value).__name__}")
    text = value.strip()
    if not text:
        raise ValueError("amount string is empty")
    if " " in text:
        whole_part, frac_part = text.split(None, 1)
        try:
            whole = Fraction(whole_part)
            frac = Fraction(frac_part)
        except (ValueError, ZeroDivisionError) as exc:
            raise ValueError(f"could not parse mixed number {value!r}: {exc}") from exc
        return whole + frac
    try:
        return Fraction(text)
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError(f"could not parse amount {value!r}: {exc}") from exc


def normalize_unit(unit: Any) -> str | None:
    """Normalize a unit to canonical form, or None for countable items."""
    if unit is None:
        return None
    if not isinstance(unit, str):
        raise ValueError(f"unit must be a string or null; got {type(unit).__name__}")
    key = unit.strip().lower()
    if key == "":
        return None
    if key in VALID_UNITS:
        return key
    if key in UNIT_ALIASES:
        return UNIT_ALIASES[key]
    if key.endswith("s") and key[:-1] in VALID_UNITS:
        return key[:-1]
    raise ValueError(
        f"unknown unit {unit!r}; valid units: {sorted(VALID_UNITS)} or null"
    )


def fraction_str(f: Fraction) -> str:
    """Stringify a Fraction as 'a/b' or 'a' if it's a whole number."""
    if f.denominator == 1:
        return str(f.numerator)
    return f"{f.numerator}/{f.denominator}"


def fraction_to_display(f: Fraction) -> str:
    """Render a non-negative Fraction as a mixed number ('3 3/8', '1/2', '5')."""
    if f.denominator == 1:
        return str(f.numerator)
    if f.numerator < f.denominator:
        return f"{f.numerator}/{f.denominator}"
    whole, rem = divmod(f.numerator, f.denominator)
    return f"{whole} {rem}/{f.denominator}"


def scale_factor_str(f: Fraction) -> str:
    """Render a scale factor: terminating decimal if exact, else fraction with approx."""
    if f.denominator == 1:
        return str(f.numerator)
    d = f.denominator
    while d % 2 == 0:
        d //= 2
    while d % 5 == 0:
        d //= 5
    if d == 1:
        return str(float(f))
    return f"{f.numerator}/{f.denominator} (~{float(f):.4f})"


def round_to(amount: Fraction, denom: int) -> Fraction:
    """Round a non-negative Fraction to the nearest 1/denom (half up)."""
    scaled = amount * denom + Fraction(1, 2)
    return Fraction(int(scaled), denom)


def round_half_up_int(amount: Fraction) -> int:
    """Round a non-negative Fraction to the nearest integer (half up)."""
    return int(amount + Fraction(1, 2))


def round_for_display(amount: Fraction, unit: str | None) -> Fraction:
    """Apply per-unit display rounding rules.

    Volumes (tsp/tbsp/cup/fl oz) round to nearest 1/8 — the finest precision
    a cook actually measures and the precision shown in PLAN.md's example
    output ('3 3/8 cup'). Imperial weights (oz/lb) and large metric (kg/l)
    round to 1/4. Small metric (g/ml) rounds to the nearest whole unit.
    Counts round to the nearest whole.
    """
    if unit is None:
        return Fraction(round_half_up_int(amount))
    if unit in ("tsp", "tbsp", "fl oz", "cup"):
        return round_to(amount, 8)
    if unit in ("oz", "lb"):
        return round_to(amount, 4)
    if unit in ("g", "ml"):
        return Fraction(round_half_up_int(amount))
    if unit in ("kg", "l"):
        return round_to(amount, 4)
    return amount


def try_promote(amount: Fraction, unit: str) -> tuple[Fraction, str]:
    """Promote toward larger units while threshold is met and denominator <= 8."""
    while unit in PROMOTE_TABLE:
        target_unit, ratio = PROMOTE_TABLE[unit]
        if amount < ratio:
            break
        new_amount = amount / ratio
        if new_amount.denominator > 8:
            break
        amount, unit = new_amount, target_unit
    return amount, unit


def try_demote(amount: Fraction, unit: str) -> tuple[Fraction, str]:
    """Demote toward smaller units while amount < 1 and result has denominator <= 8."""
    while unit in DEMOTE_TABLE and amount < 1:
        target_unit, ratio = DEMOTE_TABLE[unit]
        new_amount = amount * ratio
        if new_amount.denominator > 8:
            break
        amount, unit = new_amount, target_unit
    return amount, unit


def scale_ingredient(
    name: str, amount: Fraction, unit: str | None, factor: Fraction
) -> tuple[dict[str, Any], bool]:
    """Scale a single ingredient. Returns (output_dict, was_count_rounded_flag)."""
    scaled = amount * factor

    if unit is None:
        rounded_int = round_half_up_int(scaled)
        delta = scaled - rounded_int
        abs_delta = -delta if delta < 0 else delta
        out: dict[str, Any] = {
            "name": name,
            "display": str(rounded_int),
            "amount_raw": fraction_str(scaled),
            "unit": None,
        }
        was_rounded = abs_delta >= Fraction(15, 100)
        if was_rounded:
            out["note"] = (
                f"Rounded from {fraction_to_display(scaled)} to nearest whole "
                f"({rounded_int})."
            )
        return out, was_rounded

    final_amount, final_unit = try_promote(scaled, unit)
    final_amount, final_unit = try_demote(final_amount, final_unit)
    display_amount = round_for_display(final_amount, final_unit)
    return (
        {
            "name": name,
            "display": f"{fraction_to_display(display_amount)} {final_unit}",
            "amount_raw": fraction_str(final_amount),
            "unit": final_unit,
        },
        False,
    )


def compute_scale_factor(
    spec: dict[str, Any], base_servings: int | None
) -> tuple[Fraction, str]:
    """Compute scale factor and return (factor, mode)."""
    if not isinstance(spec, dict):
        raise ValueError("'scale' must be an object")
    mode = spec.get("mode")
    if mode == "servings":
        target = spec.get("target_servings")
        if not isinstance(target, int) or isinstance(target, bool) or target <= 0:
            raise ValueError("'scale.target_servings' must be a positive integer")
        if not isinstance(base_servings, int) or base_servings <= 0:
            raise ValueError(
                "'base_servings' must be a positive integer when scale.mode == 'servings'"
            )
        return Fraction(target, base_servings), mode
    if mode == "factor":
        raw = spec.get("factor")
        if raw is None:
            raise ValueError("'scale.factor' is required when scale.mode == 'factor'")
        try:
            frac = parse_amount(raw)
        except ValueError as exc:
            raise ValueError(f"'scale.factor' could not be parsed: {exc}") from exc
        if frac <= 0:
            raise ValueError("'scale.factor' must be positive")
        return frac, mode
    if mode == "pan":
        from_pan = spec.get("from_pan")
        to_pan = spec.get("to_pan")
        if not (isinstance(from_pan, list) and isinstance(to_pan, list)):
            raise ValueError("'scale.from_pan' and 'scale.to_pan' must be lists")
        if len(from_pan) != 2 or len(to_pan) != 2:
            raise ValueError("'scale.from_pan' and 'scale.to_pan' must each have 2 numbers")
        try:
            from_area = parse_amount(from_pan[0]) * parse_amount(from_pan[1])
            to_area = parse_amount(to_pan[0]) * parse_amount(to_pan[1])
        except ValueError as exc:
            raise ValueError(f"pan dimensions must be numeric: {exc}") from exc
        if from_area <= 0 or to_area <= 0:
            raise ValueError("pan dimensions must be positive")
        return to_area / from_area, mode
    raise ValueError(
        f"'scale.mode' must be 'servings', 'factor', or 'pan'; got {mode!r}"
    )


def parse_input(data: Any) -> tuple[list[dict[str, Any]], int | None, dict[str, Any]]:
    """Validate and parse the input JSON."""
    if not isinstance(data, dict):
        raise ValueError("input JSON must be an object")
    if "ingredients" not in data:
        raise ValueError("input JSON missing required field 'ingredients'")
    raw_ingredients = data["ingredients"]
    if not isinstance(raw_ingredients, list) or not raw_ingredients:
        raise ValueError("'ingredients' must be a non-empty list")
    parsed: list[dict[str, Any]] = []
    for i, ing in enumerate(raw_ingredients):
        if not isinstance(ing, dict):
            raise ValueError(f"'ingredients[{i}]' must be an object")
        for key in ("name", "amount"):
            if key not in ing:
                raise ValueError(f"'ingredients[{i}]' missing required field {key!r}")
        try:
            amount = parse_amount(ing["amount"])
        except ValueError as exc:
            raise ValueError(f"'ingredients[{i}].amount': {exc}") from exc
        try:
            unit = normalize_unit(ing.get("unit"))
        except ValueError as exc:
            raise ValueError(f"'ingredients[{i}].unit': {exc}") from exc
        if amount < 0:
            raise ValueError(f"'ingredients[{i}].amount' must be non-negative")
        parsed.append({"name": str(ing["name"]), "amount": amount, "unit": unit})
    base_servings = data.get("base_servings")
    if base_servings is not None:
        if not isinstance(base_servings, int) or isinstance(base_servings, bool) or base_servings <= 0:
            raise ValueError("'base_servings' must be a positive integer if provided")
    if "scale" not in data:
        raise ValueError("input JSON missing required field 'scale'")
    return parsed, base_servings, data["scale"]


def build_warnings(
    factor: Fraction,
    ingredients: list[dict[str, Any]],
    rounded_count_flags: list[bool],
    mode: str,
) -> list[str]:
    """Build the warnings list per the seven deterministic rules."""
    warnings: list[str] = []
    if factor > 5 or factor < Fraction(1, 5):
        warnings.append(
            "Scale factor is outside the reliable range (0.2x to 5x). "
            "Results may be unreliable, especially for baked goods. "
            "Consider preparing the recipe in multiple separate batches instead "
            "of one giant or one tiny batch."
        )
    if factor > 2 and any(LEAVENING_RE.search(ing["name"]) for ing in ingredients):
        warnings.append(
            "Leavening agents (baking soda / baking powder / yeast) were scaled "
            "linearly. For scale factors above 2x, consider reducing the leavening "
            "by roughly 25% of the scaled amount — leavening does not scale linearly."
        )
    if factor > Fraction(5, 2) and any(SALT_RE.search(ing["name"]) for ing in ingredients):
        warnings.append(
            "Salt was scaled linearly. For scale factors above 2.5x, consider "
            "reducing salt slightly — salt perception is non-linear in large batches."
        )
    if any(rounded_count_flags):
        warnings.append(
            "One or more countable ingredients (e.g., eggs) were rounded to a whole "
            "number. If texture matters, adjust other liquids slightly to compensate."
        )
    if mode == "pan":
        warnings.append(
            "Pan size changed: bake time will need adjustment. A smaller, deeper pan "
            "typically takes longer; a larger, shallower pan typically takes less. "
            "This script does not compute the new bake time."
        )
    return warnings


def scale_recipe(data: dict[str, Any]) -> dict[str, Any]:
    """Top-level scaling routine. Returns the output dict."""
    ingredients, base_servings, scale_spec = parse_input(data)
    factor, mode = compute_scale_factor(scale_spec, base_servings)

    scaled_ingredients: list[dict[str, Any]] = []
    rounded_flags: list[bool] = []
    for ing in ingredients:
        out, was_rounded = scale_ingredient(ing["name"], ing["amount"], ing["unit"], factor)
        scaled_ingredients.append(out)
        rounded_flags.append(was_rounded)

    warnings = build_warnings(
        factor,
        [{"name": i["name"]} for i in ingredients],
        rounded_flags,
        mode,
    )

    return {
        "scale_factor": scale_factor_str(factor),
        "scaled_ingredients": scaled_ingredients,
        "warnings": warnings,
        "notes": [],
    }


def main(input_path: Path, output_path: Path) -> None:
    """CLI entry point: read input JSON, scale, write output JSON."""
    with input_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    result = scale_recipe(data)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
        f.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scale a recipe with exact fraction arithmetic."
    )
    parser.add_argument("--input", required=True, type=Path, help="Path to input JSON file")
    parser.add_argument("--output", required=True, type=Path, help="Path to output JSON file")
    args = parser.parse_args()
    main(args.input, args.output)
