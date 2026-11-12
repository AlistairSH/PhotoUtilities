import Foundation
import Photos
import NativePhotoAnalysis

enum ReviewRemoval {
    static var photosLibraryAccessEnabled: Bool {
        Bundle.main.object(forInfoDictionaryKey: "NSPhotoLibraryUsageDescription") != nil
    }

    static func trash(_ source: AnalyzedSource) throws {
        let url = source.input.url
        let keys: Set<URLResourceKey> = [.isRegularFileKey, .isSymbolicLinkKey, .fileResourceIdentifierKey]
        func metadata() throws -> URLResourceValues {
            try URL(fileURLWithPath: url.path).resourceValues(forKeys: keys)
        }
        let before = try metadata()
        guard before.isRegularFile == true, before.isSymbolicLink == false,
              try source.matchesFile() else { throw RemovalError.fileChanged }
        let after = try metadata()
        guard after.isRegularFile == true, after.isSymbolicLink == false,
              let identity = before.fileResourceIdentifier,
              identity.isEqual(after.fileResourceIdentifier) else { throw RemovalError.fileChanged }
        try FileManager.default.trashItem(at: url, resultingItemURL: nil)
    }

    static func authorizePhotosAccess() async throws {
        guard photosLibraryAccessEnabled else { throw RemovalError.accessUnavailable }
        var access = PHPhotoLibrary.authorizationStatus(for: .readWrite)
        if access == .notDetermined {
            access = await PHPhotoLibrary.requestAuthorization(for: .readWrite)
        }
        guard access == .authorized || access == .limited else { throw RemovalError.accessDenied }
    }

    static func deleteFromPhotos(identifier: String) async throws {
        try await authorizePhotosAccess()
        guard let asset = PHAsset.fetchAssets(withLocalIdentifiers: [identifier], options: nil).firstObject,
              asset.canPerform(.delete) else { throw RemovalError.assetUnavailable }
        try await PHPhotoLibrary.shared().performChanges {
            PHAssetChangeRequest.deleteAssets([asset] as NSArray)
        }
    }

    enum RemovalError: LocalizedError {
        case fileChanged, accessUnavailable, accessDenied, assetUnavailable

        var errorDescription: String? {
            switch self {
            case .fileChanged: return "The file has changed since it was analyzed. Analyze it again before moving it to Trash."
            case .accessUnavailable: return "This build of Framewise doesn’t have Photos library access."
            case .accessDenied: return "Allow Framewise access to Photos in System Settings under Privacy & Security."
            case .assetUnavailable: return "The selected photo is unavailable or Photos doesn’t allow it to be deleted."
            }
        }
    }
}
