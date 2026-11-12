#!/bin/sh
set -eu
package_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
build_root=${NATIVE_BUILD_ROOT:-/private/tmp/photoutilities-apple-native-build}
mkdir -p "$build_root"
export CLANG_MODULE_CACHE_PATH="$build_root/clang-cache"
export SWIFTPM_MODULECACHE_OVERRIDE="$build_root/module-cache"
swift build -c release --disable-sandbox --package-path "$package_dir" \
  --scratch-path "$build_root/scratch" --cache-path "$build_root/cache" \
  --config-path "$build_root/config" --security-path "$build_root/security"
swift build -c release --disable-sandbox --package-path "$package_dir" \
  --scratch-path "$build_root/scratch" --cache-path "$build_root/cache" \
  --config-path "$build_root/config" --security-path "$build_root/security" --show-bin-path
