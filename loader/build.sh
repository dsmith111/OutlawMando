#!/usr/bin/env bash
# Cross-compile the dstorage.dll proxy for Windows x64 from WSL using zig (bundled clang+mingw).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ZIG="/tmp/claude-1000/-home-dsmith111-repos-OutlawMando/a9743d21-b8eb-4ee6-bfe8-c609ae2f5cff/scratchpad/zigvenv/bin/python -m ziglang"
OUT="$HERE/build/dstorage.dll"
mkdir -p "$HERE/build"

$ZIG c++ \
  -target x86_64-windows-gnu \
  -shared -O2 -fno-exceptions \
  -Wno-nullability-completeness -Wno-ignored-attributes \
  -I "$HERE/sdk" \
  -o "$OUT" \
  "$HERE/src/proxy.cpp" \
  -lkernel32 -luser32

echo "built: $OUT ($(stat -c%s "$OUT") bytes)"
echo "--- exports ---"
objdump -p "$OUT" 2>/dev/null | grep -A10 "Ordinal/Name Pointer" | head -12
echo "--- imported DLLs (want only system DLLs) ---"
objdump -p "$OUT" 2>/dev/null | grep "DLL Name" | sort -u
