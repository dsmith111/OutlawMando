#!/usr/bin/env bash
# Rebuild the whole Din staging tree (local/din_swap/staging) from the downloaded model.
# Nothing here touches the game folder; deploy with:  python3 deploy_din.py --redeploy
# Args are passed to the texture builder (e.g. shine=0.4) or, if they name a fit parameter, to build_din.py.
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(cd ../../.. && pwd)"
TEXARGS=(); FITARGS=(); CAPEARGS=()
for a in "$@"; do case "$a" in shine=*|beskar=*|albedo_linear=*) TEXARGS+=("$a");; cape_*=*) CAPEARGS+=("$a");; *=*) FITARGS+=("$a");; esac; done
echo "== round-trip self-test of the .mmb writer against vanilla containers"
python3 test_roundtrip.py "$ROOT/local/mesh_edit/helmet_ORIGINAL.mmb" "$ROOT/local/din_swap/containers/vest.mmb" "$ROOT/local/din_swap/containers/boots.mmb" "$ROOT/local/din_swap/containers/gloves.mmb" | tail -1
echo "== textures (single-level carriers)"
python3 -I build_textures.py "${TEXARGS[@]}" | python3 -c "
import sys, ast
for l in sys.stdin:
    l = l.strip()
    if l.startswith('{'):
        d = ast.literal_eval(l); print('   ' + d['key'] + ':  ' + ' | '.join('_%s %s' % (c, v.split(',')[0]) for c, v in d['containers'].items()))"
echo "== meshes";    python3 -I build_din.py "${FITARGS[@]}" | sed 's/^/   /' | cut -c1-150
echo "== materials"; python3 build_materials.py | grep -c '^mat_' | sed 's/^/   materials written: /'
echo "== cape (borrowed Canto police cape)"; python3 build_cape.py "${CAPEARGS[@]}"
echo "== validate"
python3 validate_all.py
echo "staging tree: $ROOT/local/din_swap/staging   (previews: python3 -I preview_build.py body ; python3 -I pose_test.py)"
