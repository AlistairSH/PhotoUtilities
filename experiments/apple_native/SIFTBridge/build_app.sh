#!/bin/sh
# Build a local, ad-hoc signed Framewise app. Full Xcode is not required.
set -eu
photos_delete=0
if [ "${1:-}" = "--enable-photos-delete" ]; then
    photos_delete=1
    shift
fi
store_candidate=0
if [ "${1:-}" = "--store-candidate" ]; then
    store_candidate=1
    photos_delete=1
    shift
fi
[ "$#" -eq 1 ] || { echo 'usage: build_app.sh [--enable-photos-delete | --store-candidate] /absolute/path/Framewise.app' >&2; exit 2; }
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
cp -RX "$package_dir/Licenses" "$app_path/Contents/Resources/Licenses"
cp -X "$package_dir/Resources/PrivacyInfo.xcprivacy" "$app_path/Contents/Resources/"
cp -X "$package_dir/Resources/PrivacyPolicy.txt" "$app_path/Contents/Resources/"
cat > "$app_path/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleIdentifier</key><string>local.photoutilities.review</string>
<key>CFBundleName</key><string>Framewise</string>
<key>CFBundleDisplayName</key><string>Framewise</string>
<key>CFBundleExecutable</key><string>Framewise</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>0.5.17</string>
<key>CFBundleVersion</key><string>23</string>
<key>CFBundleIconFile</key><string>AppIcon.icns</string>
<key>CFBundleDevelopmentRegion</key><string>en</string>
<key>LSMinimumSystemVersion</key><string>27.0</string>
<key>NSHighResolutionCapable</key><true/>
<key>NSLocalNetworkUsageDescription</key><string>Framewise looks for scanners available on your local network.</string>
<key>NSDownloadsFolderUsageDescription</key><string>Framewise saves sheet masters and extracted photos to Downloads by default.</string>
</dict></plist>
PLIST
if [ -n "${FRAMEWISE_PRIVACY_POLICY_URL:-}" ]; then
    case "$FRAMEWISE_PRIVACY_POLICY_URL" in
        https://?*) ;;
        *) echo 'FRAMEWISE_PRIVACY_POLICY_URL must be an HTTPS URL' >&2; exit 2 ;;
    esac
    /usr/bin/plutil -insert FramewisePrivacyPolicyURL -string "$FRAMEWISE_PRIVACY_POLICY_URL" "$app_path/Contents/Info.plist"
fi
if [ "$store_candidate" -eq 0 ]; then
    /usr/bin/plutil -insert FramewiseExternalSANE -bool YES "$app_path/Contents/Info.plist"
fi
# Generated bundles under synced Documents may inherit Finder/resource-fork attributes.
/usr/bin/xattr -cr "$app_path"
if [ "$photos_delete" -eq 1 ]; then
    /usr/libexec/PlistBuddy -c 'Add :NSPhotoLibraryUsageDescription string Framewise uses Photos access to read and change Favorites and genre keywords, save rotations you choose, and move photos you choose to delete to Recently Deleted.' "$app_path/Contents/Info.plist"
    /usr/libexec/PlistBuddy -c 'Add :NSPhotoLibraryAddUsageDescription string Framewise adds the original files you choose to save to Photos.' "$app_path/Contents/Info.plist"
    entitlements="$scratch/entitlements.plist"
    cat > "$entitlements" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>com.apple.security.personal-information.photos-library</key><true/>
</dict></plist>
PLIST
    if [ "$store_candidate" -eq 1 ]; then
        /usr/libexec/PlistBuddy -c 'Add :com.apple.security.device.usb bool true' "$entitlements"
        /usr/libexec/PlistBuddy -c 'Add :com.apple.security.network.client bool true' "$entitlements"
        /usr/libexec/PlistBuddy -c 'Add :com.apple.security.files.downloads.read-write bool true' "$entitlements"
        /usr/libexec/PlistBuddy -c 'Add :com.apple.security.app-sandbox bool true' "$entitlements"
        /usr/libexec/PlistBuddy -c 'Add :com.apple.security.files.user-selected.read-write bool true' "$entitlements"
    fi
    /usr/bin/codesign --force --options runtime --entitlements "$entitlements" --sign - "$app_path"
else
    /usr/bin/codesign --force --sign - "$app_path"
fi
/usr/bin/codesign --verify --strict "$app_path"
echo "$app_path"
