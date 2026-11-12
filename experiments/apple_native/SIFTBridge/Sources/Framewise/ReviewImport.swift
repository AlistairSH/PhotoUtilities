import Foundation
import NativePhotoAnalysis
import Photos

enum ReviewImport {
    static var photosAddAccessEnabled: Bool {
        Bundle.main.object(forInfoDictionaryKey: "NSPhotoLibraryAddUsageDescription") != nil
    }

    static func saveToPhotos(_ source: AnalyzedSource) async throws {
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

        try await PHPhotoLibrary.shared().performChanges {
            let request = PHAssetCreationRequest.forAsset()
            let options = PHAssetResourceCreationOptions()
            options.originalFilename = original.lastPathComponent
            options.shouldMoveFile = false
            request.addResource(with: .photo, fileURL: staged, options: options)
        }
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
