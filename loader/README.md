# `dstorage.dll` proxy — DirectStorage interception for Snowdrop/Outlaws

Experimental research tooling. This is **not** part of the shipped color mod, and it comes with
a real caveat (see below). Full context: [`../docs/HELMET-RESIZE.md`](../docs/HELMET-RESIZE.md).

## What it does
A proxy `dstorage.dll` that the game loads in place of the real one. It:
- forwards the 4 real DirectStorage exports to the renamed real runtime (`dstorage_real.dll`),
- wraps `IDStorageFactory → IDStorageQueue → EnqueueRequest` to **log** (and, at a marked hook,
  **substitute**) streamed reads,
- coexists with the `version.dll` modloader (different proxy target — no conflict).

The ABI in `src/proxy.cpp` is mirrored from DirectStorage 1.2.3 and `static_assert`-verified.
Exports exactly the 4 real entry points; depends only on Windows system DLLs.

## Build (from Linux, no MSVC/sudo)
```sh
python3 -m venv .venv && .venv/bin/pip install ziglang   # one-time
# edit build.sh: point ZIG at your .venv, then:
bash build.sh                                            # -> build/dstorage.dll
```
`build.sh` cross-compiles with `zig c++ -target x86_64-windows-gnu`. Headers in `sdk/` are
Microsoft's DirectStorage headers (MIT).

## Run (requires binaries you must obtain yourself — NOT in this repo)
Put these next to the scripts (a `redist/` folder) or edit the script paths:
- `dstoragecore.dll` — the DirectStorage **implementation** (from the DirectStorage redist / NuGet
  `Microsoft.Direct3D.DirectStorage`). The stock 1.2.x core works with the game's 2305 stub.
- `oo2core_8_win64.dll` — real **Oodle**, only needed if you re-encode replacement blocks
  (ships with various games; the `ooz` decompressor can decode without it).

Then:
```sh
bash scripts/install_proxy.sh      # backs up real dstorage.dll, installs proxy (+ enables DS)
#   ... launch the game, reproduce ...
python3 scripts/analyze_log.py "<game>/dstorage_proxy.log"
bash scripts/uninstall_proxy.sh    # restores stock state
```
The scripts have **example, machine-specific paths** (a WSL `/mnt/g/...` game dir). Edit them
for your install.

## ⚠️ Caveat
Enabling DirectStorage (installing `dstoragecore.dll`) makes the game stream **materials**
through DirectStorage too, which **bypasses `version.dll` and disables loose-material mods**
(your color mod will revert). Only enable this if the proxy also serves your material reads.
`uninstall_proxy.sh` fully reverts to the stock (DirectStorage-disabled) state.
