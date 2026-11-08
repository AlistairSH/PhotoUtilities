import CoreTransferable
import Foundation
import ImageIO
import UniformTypeIdentifiers

/// Owns a private copy for analysis and for previews after the picker returns.
final class PickedPhotoFile: Transferable, Sendable {
    private static let stagingRoot = FileManager.default.temporaryDirectory
        .appendingPathComponent("PhotoReview-\(UUID().uuidString)", isDirectory: true)
    private static let extensionsByType: [String: [String]] = [
        UTType.jpeg.identifier: ["jpg", "jpeg"],
        UTType.heic.identifier: ["heic"],
        UTType.heif.identifier: ["heif"],
        UTType.png.identifier: ["png"],
        UTType.tiff.identifier: ["tiff", "tif"]
    ]

    let url: URL
    private let directory: URL

    static var transferRepresentation: some TransferRepresentation {
        FileRepresentation(importedContentType: .heic, importing: importFile)
        FileRepresentation(importedContentType: .heif, importing: importFile)
        FileRepresentation(importedContentType: .png, importing: importFile)
        FileRepresentation(importedContentType: .tiff, importing: importFile)
        FileRepresentation(importedContentType: .jpeg, importing: importFile)
    }

    private static let importFile: @Sendable (ReceivedTransferredFile) async throws -> PickedPhotoFile = { received in
        try PickedPhotoFile(copying: received.file)
    }

    init(copying source: URL, preferredName: String? = nil) throws {
        try Task.checkCancellation()
        guard let image = CGImageSourceCreateWithURL(source as CFURL, nil),
              CGImageSourceGetCount(image) == 1,
              let identifier = CGImageSourceGetType(image),
              let extensions = Self.extensionsByType[identifier as String],
              let fileExtension = extensions.first else {
            throw ImportError.unsupported(source.lastPathComponent)
        }

        let manager = FileManager.default
        let directory = Self.stagingRoot.appendingPathComponent(UUID().uuidString, isDirectory: true)
        let nameURL = preferredName.map { URL(fileURLWithPath: $0) } ?? source
        let name = extensions.contains(nameURL.pathExtension.lowercased())
            ? nameURL.lastPathComponent : nameURL.deletingPathExtension().lastPathComponent + "." + fileExtension
        let url = directory.appendingPathComponent(name)
        try manager.createDirectory(at: directory, withIntermediateDirectories: true,
                                    attributes: [.posixPermissions: 0o700])
        do {
            try manager.copyItem(at: source, to: url)
            try Task.checkCancellation()
        } catch {
            try? manager.removeItem(at: directory)
            throw error
        }
        self.directory = directory
        self.url = url
    }

    deinit { try? FileManager.default.removeItem(at: directory) }

    static func discardStaging() {
        try? FileManager.default.removeItem(at: stagingRoot)
    }

    enum ImportError: LocalizedError {
        case unavailable
        case unsupported(String)

        var errorDescription: String? {
            switch self {
            case .unavailable:
                return "Photos didn’t provide an image file."
            case .unsupported(let name):
                return "“\(name)” is unreadable or unsupported. Choose JPEG, HEIC, HEIF, PNG, or single-image TIFF photos."
            }
        }
    }
}
