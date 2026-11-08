# Framewise

Framewise is a native macOS app for reviewing a batch of photos before you edit
or organize them. Choose images from Finder or the Photos library. Framewise
groups related shots and suggests **Top Pick**, **Keep & Review**, or **Possible
Cull** so you can compare alternatives and decide which photos to keep, edit,
or remove.

Framewise runs its analysis locally using Swift, Apple Vision, and OpenCV SIFT.
It needs no Python environment or network service at runtime. Photos may download
selected images from iCloud if they aren’t stored on your Mac.

## Review photos

1. Use **Choose Files…** or **Choose from Photos…** to select up to 500 JPEG,
   HEIC/HEIF, PNG, or single-image TIFF images. Set **Auto-rotate** before
   selecting if you want to change how Framewise orients its previews.
2. Scanning starts automatically. **Stop Scan** cancels loading or analysis,
   and **Scan Again** reruns the selection. **Processing time** in the sidebar
   shows the duration of each analysis phase after a scan.
3. Open a related set or **Ungrouped** in the sidebar. Use **Subject boxes**,
   focus notes, and **Zoom…** to inspect a photo at full resolution. **Show in
   Finder** reveals a selected file on disk.
4. To remove a photo, click **Delete…** and confirm. Files go to the Mac Trash.
   In the Photos-enabled build below, library items go to **Recently Deleted**
   after macOS grants Photos access. Tier suggestions never remove photos.

Review results are held for the current app session. Open **Help → Framewise
Help** to search for topics, or **Window → Show Framewise** to bring back the
review window.

## Build and run

Framewise requires macOS 15 or later. The local build uses Apple Command Line
Tools and the pinned OpenCV 4.11.0 static libraries. Follow the [OpenCV build
instructions](experiments/apple_native/SIFTBridge/README.md#pin-and-build-the-macos-dependency)
to prepare the dependency. Then run from the repository root:

```sh
OPENCV_ROOT=/absolute/path/to/opencv/install \
  experiments/apple_native/SIFTBridge/build_app.sh --enable-photos-delete \
  "/absolute/path/to/Framewise.app"
open "/absolute/path/to/Framewise.app"
```

Choose a new destination outside the repository. The script builds and
ad-hoc signs a local development bundle. Omit `--enable-photos-delete` for a
bundle that can review Photos selections and move files on disk to Trash.

See the [Framewise app notes](experiments/apple_native/UI.md) for packaging and
validation, the [native analysis guide](experiments/apple_native/README.md) for
developer checks, and [PROJECT.md](PROJECT.md) for implementation status.

## Companion tools

- [PhotoUtilities CLI](CLI.md) covers scanner capture, sheet splitting, batch
  reports, Polaroid TIFF processing, SQLite history, and ZIP archive/restore.
- [RestorationLab](RestorationLab/README.md) is a separate film-restoration tool.
