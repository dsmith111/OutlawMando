# Beskar recolor — material source

The mod overrides the metal-armor materials of the "Play as Boba Fett" mod so they read as clean
Mandalorian beskar. Cloth/leather pieces are left untouched.

## Files
Each tone folder holds the 8 metal-armor pieces + boots (9 `.mmaterial` files total), named at
their game-relative paths (`helix/materials/mat_chr_*_canon_boba_fett_*_metal.mmaterial`):

| Folder | Tone | `L1 Color Overlay` / `L2 Color` |
|--------|------|--------------------------------|
| `main-cool-silver/` | **Main** — bright cool silver | `(0.46, 0.50, 0.58)` / `(0.44, 0.49, 0.60)` |
| `optional-gunmetal/` | Deeper, more contrast | `(0.38, 0.42, 0.50)` / `(0.34, 0.39, 0.50)` |
| `optional-steel/` | Lighter steel | `(0.60, 0.63, 0.68)` / `(...)` |

These are the exact files packaged in the `nexus/` bundles.

## How they were generated
From the **vanilla** raw materials (ripped separately, kept out of this repo) using
[`../tools/make_tone.py`](../tools/make_tone.py), which applies only the **proven-safe** edits:
`float3` color constants + `Paint Roughness BC`, all **same length**. Example:

```sh
python3 ../tools/make_tone.py cool_bright OVL=0.46,0.50,0.58 L2=0.44,0.49,0.60 PR=0.12,0.45
```

## Why it looks the way it does
- The armor's metal read comes from lifting the dark base tint and neutralizing Boba's paint +
  weathering colors to cool silver.
- A true **mirror** shine isn't achievable: base roughness/metalness aren't editable constants,
  enabling the paint layer crashes, and editing weathering scalars crashes. So the ceiling is a
  clean, cool gunmetal-silver — matte-metallic under reflective light. See
  [`../docs/FINDINGS.md`](../docs/FINDINGS.md).
