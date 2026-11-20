#!/usr/bin/env bash
# Fetches the Baxter COLLADA meshes referenced by sim/baxter_isaac.urdf from the
# upstream RethinkRobotics/baxter_common repository, pinned to an exact commit
# and verified by SHA-256. Run once before importing the URDF into Isaac Sim:
#   bash sim/tools/fetch_meshes.sh
# Meshes are BSD 3-Clause (c) 2013-2015 Rethink Robotics; see
# sim/LICENSE.baxter_description. They are fetched instead of vendored because
# of their size; the pinned commit and hashes below make the set reproducible.
set -euo pipefail

PINNED_COMMIT="6c4b0f375fe4e356a3b12df26ef7c0d5e58df86e"
BASE="https://raw.githubusercontent.com/RethinkRobotics/baxter_common/${PINNED_COMMIT}/baxter_description"
DEST="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/meshes"
mkdir -p "$DEST"

fail=0
while read -r sha file upstream_path; do
  out="$DEST/$file"
  if [ -f "$out" ] && echo "$sha  $out" | sha256sum -c - >/dev/null 2>&1; then
    echo "ok (cached)  $file"
    continue
  fi
  echo "fetching     $file"
  curl -fsSL "$BASE/$upstream_path" -o "$out"
  if echo "$sha  $out" | sha256sum -c - >/dev/null 2>&1; then
    echo "ok           $file"
  else
    echo "HASH MISMATCH $file - deleting" >&2
    rm -f "$out"
    fail=1
  fi
done <<'MESHES'
5f26641362fba070757907374cf59cf3052dc4d9b133090552c2f83b6cf46705  E0.DAE  meshes/upper_elbow/E0.DAE
3e1b3868d8c43baf307e1cca7e700c8be75c6cd983dace1d76ee2c3b563243e2  E1.DAE  meshes/lower_elbow/E1.DAE
95f8bc9e80eea217afb4e7b271fa71ce52a7054bbe4b20868c1b889e6bc66f65  H0.DAE  meshes/head/H0.DAE
dcb09dfdd019b803a0761c367f8acf6f331a0c4984952cc424ecb5a174087422  H1.DAE  meshes/head/H1.DAE
6b0a44b95452421196cccdc1347fbb3f6da6df7a32c5929ba92ae7441b5b1d60  PEDESTAL.DAE  meshes/base/PEDESTAL.DAE
97ce864d405db2de44ddd73689fe8e60eec16cc307daf67ee2d6bb886eb9b161  S0.DAE  meshes/upper_shoulder/S0.DAE
50231b610a1f01a5f22394942e324ea3e4b62c5762a5201b16bab2a2c0ac5bdb  S1.DAE  meshes/lower_shoulder/S1.DAE
f32b0aa2010f8b021bd649166207eb86250d19cee8c1ea25dbf8cf8ee41eecf7  W0.DAE  meshes/upper_forearm/W0.DAE
9df525029abbdab8c7ce566d57b6067bcfb804da5a27a6ce43dc59cd2e63ffd4  W1.DAE  meshes/lower_forearm/W1.DAE
8a6cc33e009acc6f3f408008839f5a7e208cfb6caa87e8234425279cc726b109  W2.DAE  meshes/wrist/W2.DAE
5067ef42e5575227ff0c2235215c9e1bea804dd62dc87c024a714e03a9d7220e  base_link.DAE  meshes/torso/base_link.DAE
f0303ca3d47d90cc70969e540a234356a551c5e9d62cbccec35d3bd39c11ad50  base_link_collision.DAE  meshes/torso/base_link_collision.DAE
0b7361cb274df9005294234680b7006aebd4c0067f1515b7a936028cba4c65df  pedestal_link_collision.DAE  meshes/base/pedestal_link_collision.DAE
MESHES

if [ "$fail" -ne 0 ]; then
  echo "One or more meshes failed integrity verification." >&2
  exit 1
fi
echo "All 13 meshes present and verified in $DEST"
