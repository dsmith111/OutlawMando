#!/usr/bin/env bash
# Restore the vanilla DirectStorage runtime (remove the proxy).
set -euo pipefail
GAME="/mnt/g/SteamLibrary/steamapps/common/Star Wars Outlaws"
if [ -f "$GAME/dstorage_real.dll" ]; then
  cp "$GAME/dstorage_real.dll" "$GAME/dstorage.dll"
  echo "restored vanilla dstorage.dll (proxy removed)"
  echo "(dstorage_real.dll backup left in place; safe to keep)"
else
  echo "no dstorage_real.dll backup found — nothing to restore"
fi
# Remove the core DLL we added, restoring the game's shipped (DirectStorage-off) state.
if [ -f "$GAME/dstoragecore.dll" ]; then
  rm -f "$GAME/dstoragecore.dll"
  echo "removed dstoragecore.dll (DirectStorage back to shipped/disabled state)"
fi
