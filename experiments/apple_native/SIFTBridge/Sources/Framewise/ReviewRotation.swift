import CoreImage
import Foundation
import ImageIO
import NativePhotoAnalysis
import Photos

struct ReviewRotation {
    var savedSource: AnalyzedSource?
    var savedTurns = 0
    var pendingTurns: Int

    init(source: AnalyzedSource) {
        pendingTurns = source.rotation.quarter_turns_clockwise
    }

    var totalTurns: Int { (savedTurns + pendingTurns) % 4 }

    mutating func rotateLeft() {
        pendingTurns = (pendingTurns + 3) % 4
    }

    mutating func didSave(_ source: AnalyzedSource) {
        savedSource = source
        savedTurns = totalTurns
        pendingTurns = 0
    }

    // EXIF includes mirrored orientations. Compose the display turn after that transform.
    static func orientation(_ original: Int, turnedClockwise turns: Int) -> Int {
        let cycle = [0, 6, 7, 8, 5, 2, 3, 4, 1]
        return (0..<turns).reduce((1...8).contains(original) ? original : 1) { value, _ in cycle[value] }
    }

    static func saveFile(_ source: AnalyzedSource, turns: Int) throws -> AnalyzedSource {
        let url = source.input.url
        let manager = FileManager.default
        let keys: Set<URLResourceKey> = [.isRegularFileKey, .isSymbolicLinkKey, .fileResourceIdentifierKey]
        let before = try url.resourceValues(forKeys: keys)
        guard before.isRegularFile == true, before.isSymbolicLink == false,
              let identity = before.fileResourceIdentifier, try source.matchesFile() else {
            throw SaveError.sourceChanged
        }
        guard let image = CGImageSourceCreateWithURL(url as CFURL, nil),
              CGImageSourceGetCount(image) == 1,
              let type = CGImageSourceGetType(image) else { throw SaveError.unreadable }

        // Stage on the same volume and publish only after verifying the result and source.
        let directory = try manager.url(for: .itemReplacementDirectory, in: .userDomainMask,
                                        appropriateFor: url, create: true)
        defer { try? manager.removeItem(at: directory) }
        let candidate = directory.appendingPathComponent(url.lastPathComponent)
        guard let destination = CGImageDestinationCreateWithURL(candidate as CFURL, type, 1, nil) else {
            throw SaveError.losslessUnavailable
        }
        let metadata = CGImageSourceCopyPropertiesAtIndex(image, 0, nil) as? [String: Any]
        let original = metadata?[kCGImagePropertyOrientation as String] as? Int ?? 1
        let target = orientation(original, turnedClockwise: turns)
        let options = [kCGImageDestinationOrientation: target] as CFDictionary
        guard CGImageDestinationCopyImageSource(destination, image, options, nil),
              let written = CGImageSourceCreateWithURL(candidate as CFURL, nil),
              let properties = CGImageSourceCopyPropertiesAtIndex(written, 0, nil) as? [String: Any],
              (properties[kCGImagePropertyOrientation as String] as? Int ?? 1) == target else {
            throw SaveError.losslessUnavailable
        }
        let updated = try source.replacingFile(at: url, withBytesAt: candidate)
        let after = try URL(fileURLWithPath: url.path).resourceValues(forKeys: keys)
        guard after.isRegularFile == true, after.isSymbolicLink == false,
              identity.isEqual(after.fileResourceIdentifier), try source.matchesFile() else {
            throw SaveError.sourceChanged
        }
        _ = try manager.replaceItemAt(url, withItemAt: candidate)
        return updated
    }

    static func savePhotos(_ source: AnalyzedSource, identifier: String, turns: Int,
                           loadedAt: Date) async throws -> (AnalyzedSource, PickedPhotoFile) {
        try await ReviewRemoval.authorizePhotosAccess()
        guard let asset = PHAsset.fetchAssets(withLocalIdentifiers: [identifier], options: nil).firstObject,
              asset.mediaType == .image, !asset.mediaSubtypes.contains(.photoLive),
              asset.canPerform(.content) else { throw SaveError.photosUnavailable }
        if let modified = asset.modificationDate, modified > loadedAt { throw SaveError.sourceChanged }

        let input: PHContentEditingInput = try await withCheckedThrowingContinuation { continuation in
            let options = PHContentEditingInputRequestOptions()
            options.isNetworkAccessAllowed = true
            options.canHandleAdjustmentData = { _ in false }
            asset.requestContentEditingInput(with: options) { input, info in
                if let input { continuation.resume(returning: input) }
                else { continuation.resume(throwing: info[PHContentEditingInputErrorKey] as? Error ?? SaveError.photosUnavailable) }
            }
        }
        guard let url = input.fullSizeImageURL else { throw SaveError.unreadable }
        let output = PHContentEditingOutput(contentEditingInput: input)
        let destination = try output.renderedContentURL(for: .jpeg)
        let oriented = orientation(Int(input.fullSizeImageOrientation), turnedClockwise: turns)
        let (updated, copy) = try await Task.detached(priority: .userInitiated) {
            guard let image = CIImage(contentsOf: url, options: [.applyOrientationProperty: false]) else {
                throw SaveError.unreadable
            }
            var properties = image.properties
            properties[kCGImagePropertyOrientation as String] = 1
            var tiff = properties[kCGImagePropertyTIFFDictionary as String] as? [String: Any] ?? [:]
            tiff[kCGImagePropertyTIFFOrientation as String] = 1
            properties[kCGImagePropertyTIFFDictionary as String] = tiff
            let turned = image.oriented(forExifOrientation: Int32(oriented)).settingProperties(properties)
            let quality = CIImageRepresentationOption(rawValue: kCGImageDestinationLossyCompressionQuality as String)
            try CIContext().writeJPEGRepresentation(of: turned, to: destination,
                colorSpace: CGColorSpace(name: CGColorSpace.displayP3)!, options: [quality: 1])
            let copy = try PickedPhotoFile(copying: destination, preferredName: source.input.url.lastPathComponent)
            return (try source.replacingFile(at: copy.url, withBytesAt: copy.url), copy)
        }.value
        guard let current = PHAsset.fetchAssets(withLocalIdentifiers: [identifier], options: nil).firstObject,
              current.modificationDate == asset.modificationDate else { throw SaveError.sourceChanged }
        output.adjustmentData = PHAdjustmentData(formatIdentifier: "local.photoutilities.review.rotation",
            formatVersion: "1", data: Data([UInt8(turns)]))
        try await PHPhotoLibrary.shared().performChanges {
            PHAssetChangeRequest(for: current).contentEditingOutput = output
        }
        return (updated, copy)
    }

    enum SaveError: LocalizedError {
        case sourceChanged, unreadable, losslessUnavailable, photosUnavailable

        var errorDescription: String? {
            switch self {
            case .sourceChanged: "This photo changed since it was loaded. Choose it again before saving a rotation."
            case .unreadable: "Framewise couldn’t read the full-resolution photo."
            case .losslessUnavailable: "Framewise couldn’t update this file’s orientation without rewriting its image data. The file was left intact."
            case .photosUnavailable: "Photos doesn’t allow Framewise to edit this asset. For Live Photos, rotate the photo in Photos."
            }
        }
    }
}
