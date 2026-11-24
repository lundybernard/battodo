#!/bin/sh
# Usage: scripts/check-install.sh [<rev>]
#
# The script installs <rev> (default HEAD) of this repository as a
# non-editable `pixi global` tool, as a user does. It then runs the unit
# tests that the installed package ships, the integration and cli suites
# of <rev>, and the btodo and btd entry points against that install. The
# check reads the commit, not the uncommitted changes.
#
# The install, its global manifest, and the test files go to a temporary
# directory, which the script removes on exit and on HUP, INT, or TERM.
# The caller's global tools and global manifest stay as they are. The
# install uses the caller's pixi and uv caches.
set -eu

rev=$(git rev-parse --verify "${1:-HEAD}^{commit}")
repo=$(git rev-parse --show-toplevel)
if [ -n "$(git --no-optional-locks status --porcelain)" ]; then
	echo "note: the check installs $rev and skips uncommitted changes" >&2
fi
# The tools inherit TMPDIR and run from other directories, so a relative
# TMPDIR becomes absolute here. An unset or empty TMPDIR stays as it is.
case ${TMPDIR:-/} in /*) ;; *) export TMPDIR="$PWD/$TMPDIR" ;; esac
# git archive reads its paths relative to the working directory.
cd "$repo"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
# dash does not run the EXIT trap on a signal, so each signal trap exits.
# The status is 128 plus the signal number, as for a killed process.
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
PIXI_HOME="$work/pixi-home"
export PIXI_HOME
# pixi uses the first global manifest that exists: the one in PIXI_HOME,
# then the one in the user config directory. This empty manifest keeps
# the install out of the caller's manifest.
mkdir -p "$PIXI_HOME/manifests"
: >"$PIXI_HOME/manifests/pixi-global.toml"

echo "== Install battodo at $rev"
# pixi installs a --path source as editable, so the check installs from
# the git source.
pixi global install --git "file://$repo" --rev "$rev" \
	--expose btodo --expose btd battodo

python="$PIXI_HOME/envs/battodo/bin/python"
site=$("$python" -I -c \
	'import sysconfig; print(sysconfig.get_path("purelib"))')
git archive --output="$work/tree.tar" "$rev" pyproject.toml tests
mkdir "$work/tree"
tar -xf "$work/tree.tar" -C "$work/tree"

echo "== Check the install in $site"
for hook in "$site"/_editable_impl_*.pth; do
	if [ -e "$hook" ]; then
		echo "error: editable install: $hook" >&2
		exit 1
	fi
done
# The pin is the version in the file name of the batconf wheel.
pin=$(sed -n 's|.*/batconf-\([^-]*\)-.*\.whl.*|\1|p' \
	"$work/tree/pyproject.toml")
batconf=$("$python" -I -c \
	'from importlib.metadata import version; print(version("batconf"))')
if [ "$batconf" != "$pin" ]; then
	echo "error: batconf $batconf installed, pin: ${pin:-none}" >&2
	exit 1
fi
echo "batconf $batconf matches the pin"

# -I and a working directory outside the checkout keep the checkout's
# sources off sys.path.
cd "$work"
module=$("$python" -I -c 'import battodo; print(battodo.__file__)')
echo "battodo loads from $module"
case "$module" in
"$site"/*) ;;
*)
	echo "error: battodo loads from outside $site" >&2
	exit 1
	;;
esac

echo "== The unit tests of the installed package"
"$python" -I -m unittest discover --start-directory "$site/battodo" \
	--top-level-directory "$site" --pattern '*_test.py'

cd "$work/tree"
for layer in integration cli; do
	echo "== The $layer suite of $rev"
	"$python" -I -m unittest discover --top-level-directory . \
		--start-directory "tests/$layer" --pattern '*_test.py'
done

echo "== The entry points"
# An environment with only HOME keeps the caller's PYTHONPATH and
# battodo configuration out of the run. When HOME is unset, the user
# config path falls back to the caller's home directory.
env -i HOME="$work" "$PIXI_HOME/bin/btodo" skill >/dev/null
env -i HOME="$work" "$PIXI_HOME/bin/btd" --help
