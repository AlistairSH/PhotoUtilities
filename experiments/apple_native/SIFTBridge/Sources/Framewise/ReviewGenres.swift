import Foundation
import NativePhotoAnalysis
import Photos
import SwiftUI

struct ReviewGenres {
    var labels: Set<SceneGenre> = []
    var dismissed: Set<SceneGenre> = []
    var savedLabels: Set<SceneGenre> = []
    var detail: String?
    var failureReason: String?
    var analysisUnavailable = false
}

enum PhotosGenres {
    struct Change {
        let keywords: Set<String>
        let editedAt: Date?
    }

    @available(macOS 27, *)
    @MainActor static func write(identifier: String, adding: Set<String>, removing: Set<String>,
                                 loadedAt: Date) async throws -> Change {
        try await ReviewRemoval.authorizePhotosAccess()
        guard let asset = PHAsset.fetchAssets(withLocalIdentifiers: [identifier], options: nil).firstObject,
              asset.canPerform(.properties) else { throw GenreError.assetUnavailable }
        let before = Set(asset.extendedMetadata.keywords)
        let additions = adding.subtracting(before)
        let removals = removing.intersection(before)
        guard !additions.isEmpty || !removals.isEmpty else {
            return Change(keywords: before, editedAt: nil)
        }
        try Task.checkCancellation()
        try await PHPhotoLibrary.shared().performChanges {
            let request = PHAssetChangeRequest(for: asset)
            additions.forEach { request.addKeyword($0) }
            removals.forEach { request.removeKeyword($0) }
        }
        guard let updated = PHAsset.fetchAssets(withLocalIdentifiers: [identifier], options: nil).firstObject
        else { throw GenreError.verification }
        let after = Set(updated.extendedMetadata.keywords)
        let expected = before.subtracting(removals).union(additions)
        guard expected.isSubset(of: after), after.isDisjoint(with: removing) else {
            throw GenreError.verification
        }
        let wasCurrent = asset.modificationDate.map { $0 <= loadedAt } ?? true
        return Change(keywords: after, editedAt: after == expected && wasCurrent ? Date() : nil)
    }
}

enum GenreError: LocalizedError {
    case assetUnavailable, verification

    var errorDescription: String? {
        switch self {
        case .assetUnavailable: "Framewise can’t edit keywords on this Photos asset."
        case .verification: "Framewise couldn’t verify the saved keywords in Photos."
        }
    }
}

struct GenreControls: View {
    let state: ReviewGenres
    let enabled: Bool
    let toggle: (SceneGenre) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach(SceneGenre.allCases.filter(state.labels.contains), id: \.self) { genre in
                HStack(spacing: 5) {
                    Text(genre.rawValue)
                    Button("Remove \(genre.rawValue)", systemImage: "xmark") { toggle(genre) }
                        .labelStyle(.iconOnly)
                        .buttonStyle(.borderless)
                        .help("Remove \(genre.rawValue)")
                        .disabled(!enabled)
                }
            }
            Menu("Add Genre", systemImage: "tag") {
                ForEach(SceneGenre.allCases.filter { !state.labels.contains($0) }, id: \.self) { genre in
                    Button(genre.rawValue) { toggle(genre) }
                }
            }
            .fixedSize()
            .disabled(!enabled || state.labels.count == SceneGenre.allCases.count)
            if state.analysisUnavailable {
                Text("Automatic genre analysis unavailable.").foregroundStyle(.secondary)
            }
            if let detail = state.detail {
                Text(detail).foregroundStyle(.secondary).help(state.failureReason ?? detail)
            }
        }
        .font(.caption)
    }
}
