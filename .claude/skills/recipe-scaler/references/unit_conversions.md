# Unit conversions reference

The script (`scripts/scale_recipe.py`) handles all conversions automatically;
this file exists for human verification.

## Volume

| Equivalence       |
|-------------------|
| 3 tsp = 1 tbsp    |
| 16 tbsp = 1 cup   |
| 1 cup = 8 fl oz   |

## Weight

| Equivalence       |
|-------------------|
| 16 oz = 1 lb      |

## Metric

| Equivalence       |
|-------------------|
| 1000 g = 1 kg     |
| 1000 ml = 1 l     |

## Promotion / demotion behavior

The script promotes a smaller unit to the next larger unit when:

1. The scaled amount is greater than or equal to the threshold (e.g., 3 tsp), AND
2. The result in the larger unit has a denominator ≤ 8 (i.e., it's a clean
   cooking measurement like 1/2, 3/4, 1/8, etc.).

Demotion happens symmetrically when the scaled amount in the source unit
falls below 1 and demoting yields a denominator ≤ 8.

This keeps results readable: 6 tsp becomes 2 tbsp, but 7 tsp stays as 7 tsp
(promoting to tbsp would give 7/3, which has denominator 3 — fine — except
it's not a standard measure; the rule's denominator-≤-8 check passes here,
so it would actually promote to 2 1/3 tbsp, which is awkward but legal).
Use judgment in prose to suggest a cleaner equivalent if useful.
