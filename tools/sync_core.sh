#!/bin/sh
# Point every component's core/ submodule at the root core/ HEAD (make sync-core) and refresh
# the Arduino library's copy of the transmitter sources.
#   sync_core.sh [ROOT]      ROOT: the umbrella checkout (default: the parent of this directory)
# Stops with a non-zero status at the first component that cannot be synced.
ROOT=${1:-$(cd "$(dirname "$0")/.." && pwd)}
COMPONENTS="arduino zephyr-module ios android unoq"
die() { echo "sync-core: $*" >&2; exit 1; }

# a directory without its own .git makes `git -C` act on the repository that contains it
[ -e "$ROOT/core/.git" ] || die "core is not an initialised submodule (make setup)"
# Only commits travel: an uncommitted edit in core/ would stay behind while every component
# reports the old HEAD as synced.
dirty=$(git -C "$ROOT/core" status --porcelain --untracked-files=no) || die "core: git status failed"
[ -z "$dirty" ] || { echo "$dirty" >&2; die "core has uncommitted changes to tracked files: commit them, then sync"; }
rev=$(git -C "$ROOT/core" rev-parse HEAD) || die "core: no HEAD"

for d in $COMPONENTS; do
    c="$ROOT/$d/core"
    [ -e "$c/.git" ] || die "$d/core is not an initialised submodule (make setup)"
    git -C "$c" fetch -q "$ROOT/core" || die "$d/core: fetch from core failed"
    git -C "$c" checkout -q "$rev" || die "$d/core: checkout of $rev failed"
    # a checkout keeps local edits that do not conflict: the tree is then not the one of $rev
    [ -z "$(git -C "$c" status --porcelain --untracked-files=no)" ] || echo "warning: $d/core has local changes on top of $rev" >&2
    echo "$d/core -> $rev"
done

# The Arduino library tracks its own copy of the transmitter sources (the Arduino IDE builds
# libraries/Blinko alone, without the submodule). arduino/build.sh refreshes it at every build;
# doing it here too keeps the tracked copy from being committed at the previous core.
# Same files as in arduino/build.sh.
lib="$ROOT/arduino/libraries/Blinko/src/core"
if [ -d "$lib" ]; then
    for f in rs_proto.h rs_tx.h rs_tx.c rs_pack.h rs_pack.c; do
        cp "$ROOT/arduino/core/$f" "$lib/" || die "arduino: cannot refresh libraries/Blinko/src/core/$f"
    done
    echo "arduino/libraries/Blinko/src/core refreshed"
fi

# The components' pointers name a commit of blinko-core: pushed before core itself, they point
# at a commit nobody else can fetch. Checked against the local origin/main (no network).
if ! git -C "$ROOT/core" rev-parse -q --verify origin/main >/dev/null 2>&1; then
    echo "warning: core has no origin/main to compare with" >&2
elif ! git -C "$ROOT/core" merge-base --is-ancestor "$rev" origin/main; then
    echo "warning: core $rev is not in origin/main: push core before pushing the component pointers" >&2
fi
