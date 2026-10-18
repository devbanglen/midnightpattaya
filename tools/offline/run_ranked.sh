#!/usr/bin/env bash
# Offline checks for ranked circuit racing (docs/RANKED_SYSTEM.md "Offline checks"). Not a playtest.
# Needs the luau CLI (https://github.com/luau-lang/luau/releases), which is not in the repo.
# usage: bash tools/offline/run_ranked.sh /path/to/luau[.exe]
# It wraps the real module sources between a mock "head" and a test "tail" (the luau CLI has no file I/O, so a
# module cannot be loaded with mocked requires any other way) and runs them in a temporary folder.
set -euo pipefail
LUAU="${1:?usage: run_ranked.sh <path to luau>}"
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/../../roblox/src/ServerStorage"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
tr -d '\r' < "$SRC/RankedRating.luau" > "$WORK/RankedRating.luau"
tr -d '\r' < "$SRC/RankedRatingTest.luau" > "$WORK/RankedRatingTest.luau"
echo 'print(require("./RankedRatingTest")(require("./RankedRating")))' > "$WORK/unit.luau"
{ cat "$HERE/ranked_session_head.luau"; tr -d '\r' < "$SRC/RaceSessionService.luau"; cat "$HERE/ranked_session_tail.luau"; } > "$WORK/session.luau"
{ cat "$HERE/ranked_board_head.luau"; tr -d '\r' < "$SRC/LeaderboardService.luau"; cat "$HERE/ranked_board_tail.luau"; } > "$WORK/board.luau"
cd "$WORK"
echo "== RankedRatingTest"; "$LUAU" unit.luau
echo "== RaceSessionService.Ranked (mocked)"; "$LUAU" session.luau
echo "== LeaderboardService ranked board (mocked)"; "$LUAU" board.luau
