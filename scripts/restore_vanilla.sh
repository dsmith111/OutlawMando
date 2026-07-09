#!/usr/bin/env bash
# Remove the beskar ARMOR overrides (game falls back to vanilla in the archives)
# and restore the mod's original boots material from its backup.
set -euo pipefail
DST="/mnt/g/SteamLibrary/steamapps/common/Star Wars Outlaws/helix/materials"

echo "Removing beskar armor overrides from: $DST"
for f in /home/dsmith111/repos/OutlawMando/deliver/beskar_armor/*.mmaterial; do
  b="$(basename "$f")"
  if [[ -f "$DST/$b" ]]; then rm -f "$DST/$b"; echo "  - $b"; fi
done

BOOTS="$DST/mat_chr_botm_5_canon_boba_fett_boots_metal.mmaterial"
if [[ -f "$BOOTS.bak" ]]; then
  cp "$BOOTS.bak" "$BOOTS"
  echo "  ~ boots restored from .bak (mod's original)"
fi
echo "Done. Armor is back to vanilla Boba; boots back to the mod's original."
