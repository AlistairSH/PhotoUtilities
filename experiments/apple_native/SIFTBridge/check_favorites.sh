#!/bin/sh
set -eu
package_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
check_dir=$(mktemp -d "${TMPDIR:-/tmp}/framewise-favorite-checks.XXXXXX")
trap 'rm -rf "$check_dir"' EXIT
CLANG_MODULE_CACHE_PATH="$check_dir/module-cache" swiftc \
    "$package_dir/Sources/Framewise/FavoriteContainer.swift" \
    "$package_dir/Sources/Framewise/FileFavorite.swift" "$package_dir/Checks/Favorites/main.swift" \
    -o "$check_dir/favorite-checks"
"$check_dir/favorite-checks" "$@"
