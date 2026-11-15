import Foundation
import NativePhotoAnalysis
import Photos
import os

enum ReviewImport {
    static var photosAddAccessEnabled: Bool {
        Bundle.main.object(forInfoDictionaryKey: "NSPhotoLibraryAddUsageDescription") != nil
    }

    static func saveToPhotos(_ source: AnalyzedSource) async throws -> String? {
        guard photosAddAccessEnabled else { throw ImportError.accessUnavailable }
        var access = PHPhotoLibrary.authorizationStatus(for: .addOnly)
        if access == .notDetermined {
            access = await PHPhotoLibrary.requestAuthorization(for: .addOnly)
        }
        guard access == .authorized else { throw ImportError.accessDenied }

        let original = source.input.url
        let fileKeys: Set<URLResourceKey> = [.isRegularFileKey, .isSymbolicLinkKey]
        let originalValues = try URL(fileURLWithPath: original.path).resourceValues(forKeys: fileKeys)
        guard originalValues.isRegularFile == true, originalValues.isSymbolicLink == false else {
            throw ImportError.fileChanged
        }
        let manager = FileManager.default
        let directory = manager.temporaryDirectory.appendingPathComponent("FramewisePhotos-\(UUID())", isDirectory: true)
        try manager.createDirectory(at: directory, withIntermediateDirectories: false,
                                    attributes: [.posixPermissions: 0o700])
        defer { try? manager.removeItem(at: directory) }

        // PhotoKit reads asynchronously. Stage and check the exact bytes that
        // were reviewed so an external edit cannot swap in a different image.
        let staged = directory.appendingPathComponent(original.lastPathComponent)
        try manager.copyItem(at: original, to: staged)
        let stagedValues = try staged.resourceValues(forKeys: fileKeys)
        guard stagedValues.isRegularFile == true, stagedValues.isSymbolicLink == false else {
            throw ImportError.fileChanged
        }
        let copy = try source.replacingFile(at: staged, withBytesAt: staged)
        guard copy.sha256 == source.sha256 else { throw ImportError.fileChanged }

        let keywords = (try? FileFavorite.writeGenres(adding: [], removing: [],
                            to: staged, expectedDigest: copy.sha256).existing) ?? []
        let genres = Set(SceneGenre.allCases.map(\.rawValue))
        if #available(macOS 27, *), !keywords.isDisjoint(with: genres) {
            do {
                try await ReviewRemoval.authorizePhotosAccess()
            } catch {
                try await importPhoto(staged, original: original)
                return "Photo saved to Photos. Framewise couldn’t verify its genre keywords without Photos read/write access."
            }
            return try await importWithKeywords(staged, original: original, keywords: keywords)
        }
        try await importPhoto(staged, original: original)
        return nil
    }

    private static func importPhoto(_ staged: URL, original: URL) async throws {
        try await PHPhotoLibrary.shared().performChanges {
            addResource(to: PHAssetCreationRequest.forAsset(), staged: staged, original: original)
        }
    }

    @available(macOS 27, *)
    private static func importWithKeywords(_ staged: URL, original: URL, keywords: Set<String>) async throws -> String? {
        // Track the created asset so a keyword failure cannot trigger a second import.
        let identifier = OSAllocatedUnfairLock<String?>(initialState: nil)
        try await PHPhotoLibrary.shared().performChanges {
            let request = PHAssetCreationRequest.forAsset()
            addResource(to: request, staged: staged, original: original)
            identifier.withLock { $0 = request.placeholderForCreatedAsset?.localIdentifier }
        }
        if let id = identifier.withLock({ $0 }),
           let asset = PHAsset.fetchAssets(withLocalIdentifiers: [id], options: nil).firstObject,
           asset.canPerform(.properties) {
            let missing = keywords.subtracting(asset.extendedMetadata.keywords)
            if missing.isEmpty { return nil }
            do {
                try await PHPhotoLibrary.shared().performChanges {
                    let request = PHAssetChangeRequest(for: asset)
                    missing.sorted().forEach { request.addKeyword($0) }
                }
                if let updated = PHAsset.fetchAssets(withLocalIdentifiers: [id], options: nil).firstObject,
                   keywords.isSubset(of: Set(updated.extendedMetadata.keywords)) {
                    return nil
                }
            } catch {
                return "Photo saved to Photos, but Framewise couldn’t add all its keywords. \(error.localizedDescription)"
            }
        }
        return "Photo saved to Photos, but Framewise couldn’t verify all its keywords."
    }

    private static func addResource(to request: PHAssetCreationRequest, staged: URL, original: URL) {
        let options = PHAssetResourceCreationOptions()
        options.originalFilename = original.lastPathComponent
        options.shouldMoveFile = false
        request.addResource(with: .photo, fileURL: staged, options: options)
    }

    private enum ImportError: LocalizedError {
        case accessUnavailable, accessDenied, fileChanged

        var errorDescription: String? {
            switch self {
            case .accessUnavailable: "This build of Framewise doesn’t have permission to add photos."
            case .accessDenied: "Allow Framewise to add photos in System Settings under Privacy & Security."
            case .fileChanged: "The file has changed since it was reviewed. Scan again before saving it to Photos."
            }
        }
    }
}
