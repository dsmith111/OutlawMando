#!/usr/bin/env bash
# Install the dstorage.dll proxy alongside the existing modloader (version.dll).
# Fully reversible: the real runtime is preserved as dstorage_real.dll.
set -euo pipefail
GAME="/mnt/g/SteamLibrary/steamapps/common/Star Wars Outlaws"
PROXY="/home/dsmith111/repos/OutlawMando/loader/build/dstorage.dll"
[ -f "$PROXY" ] || { echo "build first: bash loader/build.sh"; exit 1; }

# Preserve the real DirectStorage runtime exactly once (this is the backup).
if [ ! -f "$GAME/dstorage_real.dll" ]; then
  cp "$GAME/dstorage.dll" "$GAME/dstorage_real.dll"
  echo "backed up real runtime -> dstorage_real.dll"
else
  echo "backup dstorage_real.dll already present (not overwriting it)"
fi

cp "$PROXY" "$GAME/dstorage.dll"
echo "installed proxy -> $GAME/dstorage.dll ($(stat -c%s "$GAME/dstorage.dll") bytes)"

# The game ships the DirectStorage STUB but not its implementation (dstoragecore.dll),
# so DirectStorage returns E_NOTIMPL and the game falls back to plain I/O -> our proxy
# sees nothing. Supplying the core DLL activates DirectStorage (proxy verified S_OK).
CORE="/home/dsmith111/repos/OutlawMando/loader/redist/dstoragecore.dll"
if [ -f "$CORE" ]; then
  cp "$CORE" "$GAME/dstoragecore.dll"
  echo "installed dstoragecore.dll -> enables DirectStorage ($(stat -c%s "$GAME/dstoragecore.dll") bytes)"
else
  echo "WARN: $CORE missing; DirectStorage will stay disabled (proxy sees no traffic)"
fi
echo "log target: $GAME/dstorage_proxy.log"
echo "Coexists with version.dll (modloader). Launch the game; then run analyze_log.py."
