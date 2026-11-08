#!/bin/sh
# Build a local, ad-hoc signed Framewise app. Full Xcode is not required.
set -eu
photos_delete=0
if [ "${1:-}" = "--enable-photos-delete" ]; then
    photos_delete=1
    shift
fi
[ "$#" -eq 1 ] || { echo 'usage: build_app.sh [--enable-photos-delete] /absolute/path/Framewise.app' >&2; exit 2; }
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
scratch=$(mktemp -d "$build_root/app-resources.XXXXXX")
trap 'rm -rf "$scratch"' EXIT
iconset="$scratch/AppIcon.iconset"
mkdir "$iconset"
for size in 16 32 128 256 512; do
    retina=$((size * 2))
    /usr/bin/sips -z "$size" "$size" "$package_dir/Resources/AppIcon.png" \
        --out "$iconset/icon_${size}x${size}.png" >/dev/null
    /usr/bin/sips -z "$retina" "$retina" "$package_dir/Resources/AppIcon.png" \
        --out "$iconset/icon_${size}x${size}@2x.png" >/dev/null
done
/usr/bin/iconutil -c icns "$iconset" -o "$scratch/AppIcon.icns"
# Exclusive directory creation protects an occupied destination, including symlinks.
mkdir -p "$(dirname -- "$app_path")"
mkdir "$app_path"
mkdir -p "$app_path/Contents/MacOS" "$app_path/Contents/Resources"
cp -X "$binary_dir/Framewise" "$app_path/Contents/MacOS/Framewise"
cp -X "$scratch/AppIcon.icns" "$app_path/Contents/Resources/AppIcon.icns"
cat > "$app_path/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleIdentifier</key><string>local.photoutilities.review</string>
<key>CFBundleName</key><string>Framewise</string>
<key>CFBundleDisplayName</key><string>Framewise</string>
<key>CFBundleExecutable</key><string>Framewise</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>0.5.12</string>
<key>CFBundleVersion</key><string>18</string>
<key>CFBundleIconFile</key><string>AppIcon.icns</string>
<key>CFBundleDevelopmentRegion</key><string>en</string>
<key>LSMinimumSystemVersion</key><string>15.0</string>
<key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST
# Generated bundles under synced Documents may inherit Finder/resource-fork attributes.
/usr/bin/xattr -cr "$app_path"
if [ "$photos_delete" -eq 1 ]; then
    /usr/libexec/PlistBuddy -c 'Add :NSPhotoLibraryUsageDescription string Framewise uses Photos access to move a photo you choose to delete to Recently Deleted.' "$app_path/Contents/Info.plist"
    entitlements="$scratch/entitlements.plist"
    cat > "$entitlements" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>com.apple.security.personal-information.photos-library</key><true/>
</dict></plist>
PLIST
    /usr/bin/codesign --force --options runtime --entitlements "$entitlements" --sign - "$app_path"
else
    /usr/bin/codesign --force --sign - "$app_path"
fi
/usr/bin/codesign --verify --strict "$app_path"
echo "$app_path"
