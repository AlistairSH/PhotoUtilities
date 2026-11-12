import Foundation
import Photos

enum FavoriteIdentity: Hashable, Sendable {
    case file(URL)
    case photos(String)
}

enum FavoriteState: Sendable {
    case known(Bool)
    case file(FileFavorite.Snapshot)
    case unavailable(String)

    var isFavorite: Bool {
        switch self {
        case let .known(value): value
        case let .file(value): value.isFavorite
        case .unavailable: false
        }
    }

    var unavailableReason: String? {
        if case let .unavailable(reason) = self { return reason }
        return nil
    }

    var fileSnapshot: FileFavorite.Snapshot? {
        if case let .file(snapshot) = self { return snapshot }
        return nil
    }

    var detail: String? {
        guard let fileSnapshot else { return unavailableReason }
        let detail = [fileSnapshot.sessionOnly ? "Favorite for this review only." : nil, fileSnapshot.note]
            .compactMap { $0 }.joined(separator: " ")
        return detail.isEmpty ? nil : detail
    }

}

enum PhotosFavorite {
    static func read(_ identifiers: [String]) async throws -> [String: FavoriteState] {
        guard !identifiers.isEmpty else { return [:] }
        try await ReviewRemoval.authorizePhotosAccess()
        try Task.checkCancellation()
        let assets = PHAsset.fetchAssets(withLocalIdentifiers: identifiers, options: nil)
        var states: [String: FavoriteState] = [:]
        for index in 0..<assets.count {
            let asset = assets.object(at: index)
            states[asset.localIdentifier] = .known(asset.isFavorite)
        }
        return states
    }

    static func write(_ favorite: Bool, identifier: String, loadedAt: Date) async throws -> Date? {
        try await ReviewRemoval.authorizePhotosAccess()
        guard let asset = PHAsset.fetchAssets(withLocalIdentifiers: [identifier], options: nil).firstObject,
              asset.canPerform(.properties) else { throw FavoriteError.photosUnavailable }
        guard asset.isFavorite != favorite else { return nil }
        let wasCurrent = asset.modificationDate.map { $0 <= loadedAt } ?? true
        try await PHPhotoLibrary.shared().performChanges {
            PHAssetChangeRequest(for: asset).isFavorite = favorite
        }
        // PhotoKit may advance modificationDate for a property edit. Keep the rotation
        // baseline current only when there was no known intervening edit before ours.
        return wasCurrent ? Date() : nil
    }
}

enum FavoriteError: LocalizedError {
    case photosUnavailable, fileChanged

    var errorDescription: String? {
        switch self {
        case .photosUnavailable: "This photo is unavailable or Photos doesn’t allow Framewise to change its Favorite."
        case .fileChanged: "The file changed since it was analyzed. Scan again before changing its Favorite."
        }
    }
}
