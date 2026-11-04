#!/bin/sh
# Build a local, ad-hoc signed macOS prototype. Full Xcode is not required.
set -eu
[ "$#" -eq 1 ] || { echo 'usage: build_app.sh NEW_APP_PATH.app' >&2; exit 2; }
package_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
app_path=$1
case "$app_path" in /*.app) ;; *) echo 'Choose an absolute .app path' >&2; exit 2 ;; esac
[ ! -e "$app_path" ] && [ ! -L "$app_path" ] || { echo 'Destination exists; refusing overwrite' >&2; exit 2; }
build_root=${SIFT_BUILD_ROOT:-/private/tmp/photoutilities-sift-bridge}
mkdir -p "$build_root"
if ! "$package_dir/build.sh" > "$build_root/app-build.log" 2>&1; then
    tail -60 "$build_root/app-build.log" >&2
    exit 1
fi
binary_dir=$(tail -1 "$build_root/app-build.log")
# Exclusive directory creation protects an occupied destination, including symlinks.
mkdir -p "$(dirname -- "$app_path")"
mkdir "$app_path"
mkdir -p "$app_path/Contents/MacOS"
cp -X "$binary_dir/photo-review" "$app_path/Contents/MacOS/PhotoReview"
cat > "$app_path/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleIdentifier</key><string>local.photoutilities.review</string>
<key>CFBundleName</key><string>Photo Review</string>
<key>CFBundleDisplayName</key><string>Photo Review</string>
<key>CFBundleExecutable</key><string>PhotoReview</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>0.2</string>
<key>CFBundleVersion</key><string>2</string>
<key>LSMinimumSystemVersion</key><string>15.0</string>
<key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST
# Generated bundles under synced Documents may inherit Finder/resource-fork attributes.
/usr/bin/xattr -cr "$app_path"
/usr/bin/codesign --force --sign - "$app_path"
/usr/bin/codesign --verify --strict "$app_path"
echo "$app_path"
