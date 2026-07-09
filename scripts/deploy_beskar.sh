#!/usr/bin/env bash
# Deploy the beskar silver ARMOR overrides (+ optional boots) into the game.
# Usage:  bash deploy_beskar.sh [bootsVariant]
#   bootsVariant (optional): C | D | E | A | B   (default: C = glossy)
set -euo pipefail
REPO="/home/dsmith111/repos/OutlawMando/deliver"
DST="/mnt/g/SteamLibrary/steamapps/common/Star Wars Outlaws/helix/materials"

echo "Deploying beskar armor to: $DST"
for f in "$REPO"/beskar_armor/*.mmaterial; do
  cp "$f" "$DST/"
  echo "  + $(basename "$f")"
done

BOOTS="${1:-A}"   # default A = SAME-LENGTH tint (safe). C/D/E change file length -> known crash risk.
declare -A BV=( [A]=boots_silver_A_neutral090 [B]=boots_silver_B_bright097 \
                [C]=boots_C_dirtyglossy [D]=boots_D_cleanglossy [E]=boots_E_dirtyglossy_bright )
if [[ "$BOOTS" =~ ^[CDE]$ ]]; then
  echo "  ! WARNING: boots variant $BOOTS changes the material file length; this currently"
  echo "    corrupts the header and can CRASH the game. Use A/B until the repoint is fixed."
fi
if [[ -n "${BV[$BOOTS]:-}" ]]; then
  cp "$REPO/${BV[$BOOTS]}.mmaterial" "$DST/mat_chr_botm_5_canon_boba_fett_boots_metal.mmaterial"
  echo "  + boots variant $BOOTS (${BV[$BOOTS]})"
fi
echo "Done. Launch the game and inspect Kay/Boba. Screenshot the armor."
