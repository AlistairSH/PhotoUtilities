import CryptoKit
import Darwin
import Foundation
import ImageIO
import UniformTypeIdentifiers

enum FileFavorite {
    static let keyword = "Framewise:Favorite"
    static func sidecarURL(_ image: URL) -> URL { image.appendingPathExtension("xmp") }

    private static func companion(for image: URL) throws -> (url: URL, data: Data?) {
        let fullName = sidecarURL(image)
        if let data = try readSidecar(at: fullName) { return (fullName, data) }
        let stem = image.deletingPathExtension()
        let conventional = stem.appendingPathExtension("xmp")
        guard let data = try readSidecar(at: conventional) else { return (fullName, nil) }

        // A conventional stem-only companion can belong to another rendition.
        let siblings = try FileManager.default.contentsOfDirectory(at: image.deletingLastPathComponent(),
                                                                   includingPropertiesForKeys: nil)
        let hasSameStem = siblings.contains { sibling in
            let ext = sibling.pathExtension.lowercased()
            return sibling.lastPathComponent != image.lastPathComponent
                && sibling.deletingPathExtension().lastPathComponent.caseInsensitiveCompare(stem.lastPathComponent) == .orderedSame
                && ext != "xmp"
        }
        guard !hasSameStem else { throw StorageError.ambiguousSidecar }
        return (conventional, data)
    }

    private static func readSidecar(at url: URL) throws -> Data? {
        do {
            let values = try URL(fileURLWithPath: url.path).resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey])
            guard values.isRegularFile == true, values.isSymbolicLink == false else {
                throw StorageError.invalidSidecar
            }
            guard let size = try url.resourceValues(forKeys: [.fileSizeKey]).fileSize,
                  size <= 8 * 1024 * 1024 else { throw StorageError.invalidSidecar }
            return try Data(contentsOf: url)
        } catch let error as CocoaError where error.code == .fileReadNoSuchFile || error.code == .fileNoSuchFile {
            return nil
        }
    }
}

struct FavoriteXMP {
    static let rdf = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
    static let dc = "http://purl.org/dc/elements/1.1/"
    static let framewise = "urn:framewise:metadata:1.0"

    let document: XMLDocument
    let graph: XMLElement
    private let trailingZeros: Int

    init(_ data: Data?) throws {
        let trailing = data?.reversed().prefix { $0 == 0 }.count ?? 0
        trailingZeros = trailing
        document = try XMLDocument(data: data.map { Data($0.dropLast(trailing)) } ?? Data("""
            <x:xmpmeta xmlns:x="adobe:ns:meta/">
              <rdf:RDF xmlns:rdf="\(Self.rdf)"><rdf:Description rdf:about=""/></rdf:RDF>
            </x:xmpmeta>
            """.utf8), options: [.nodePreserveAll, .nodeLoadExternalEntitiesNever])
        guard document.dtd == nil, let root = document.rootElement() else { throw FileFavorite.StorageError.unsafe }
        if root.localName == "RDF", root.uri == Self.rdf {
            graph = root
        } else {
            let graphs = root.elements(forLocalName: "RDF", uri: Self.rdf)
            guard graphs.count == 1 else { throw FileFavorite.StorageError.unsafe }
            graph = graphs[0]
        }
    }

    private var descriptions: [XMLElement] {
        graph.elements(forLocalName: "Description", uri: Self.rdf).filter {
            // Other RDF subjects may describe related resources, not this image.
            ($0.attribute(forLocalName: "about", uri: Self.rdf)?.stringValue ?? "").isEmpty
                && $0.attribute(forLocalName: "nodeID", uri: Self.rdf) == nil
        }
    }

    private func bags() throws -> [XMLElement] {
        try descriptions.flatMap { description in
            guard description.attribute(forLocalName: "subject", uri: Self.dc) == nil else {
                throw FileFavorite.StorageError.unsafe
            }
            return try description.elements(forLocalName: "subject", uri: Self.dc).map { subject in
                let containers = subject.elements(forLocalName: "Bag", uri: Self.rdf)
                    + subject.elements(forLocalName: "Seq", uri: Self.rdf)
                guard containers.count == 1,
                      subject.children?.compactMap({ $0 as? XMLElement }).count == 1 else {
                    throw FileFavorite.StorageError.unsafe
                }
                return containers[0]
            }
        }
    }

    private func favoriteItems(in bags: [XMLElement]) -> [XMLElement] {
        bags.flatMap { $0.elements(forLocalName: "li", uri: Self.rdf) }.filter {
            $0.stringValue == FileFavorite.keyword && $0.attributes?.isEmpty != false
                && $0.children?.allSatisfy { $0.kind == .text } == true
        }
    }

    func hasFavorite() throws -> Bool { try !favoriteItems(in: bags()).isEmpty }

    var legacyRemoval: Bool {
        descriptions.flatMap { $0.elements(forLocalName: "EmbeddedFavoriteRemoved", uri: Self.framewise) }
            .contains { $0.stringValue == "True" && $0.attributes?.isEmpty != false }
    }

    // Once a legacy state has been imported, the embedded state owns that
    // decision even if another editor later changes unrelated sidecar fields.
    private static let receipt = "ImportedFavoriteSidecar"
    func imported(_ legacyState: String) -> Bool {
        descriptions.flatMap { $0.elements(forLocalName: Self.receipt, uri: Self.framewise) }
            .contains { $0.stringValue == legacyState }
    }

    func update(favorite: Bool, receipt: String?) throws -> Bool {
        var changed = false
        let bags = try bags()
        let items = favoriteItems(in: bags)
        if !favorite && !items.isEmpty { items.forEach { $0.detach() }; changed = true }
        if favorite && items.isEmpty {
            changed = true
            let description = descriptions.first ?? append("rdf:Description", uri: Self.rdf, to: graph)
            let bag = bags.first ?? append("rdf:Bag", uri: Self.rdf,
                to: append("dc:subject", uri: Self.dc, to: description))
            append("rdf:li", uri: Self.rdf, to: bag).stringValue = FileFavorite.keyword
        }
        if let receipt, !imported(receipt) {
            changed = true
            let description = descriptions.first ?? append("rdf:Description", uri: Self.rdf, to: graph)
            append("framewise:\(Self.receipt)", uri: Self.framewise, to: description).stringValue = receipt
        }
        return changed
    }

    var data: Data { document.xmlData(options: [.nodePreserveAll]) + Data(repeating: 0, count: trailingZeros) }

    private func append(_ name: String, uri: String, to parent: XMLElement) -> XMLElement {
        let element = XMLElement(name: name, uri: uri)
        let prefix = String(name.prefix { $0 != ":" })
        let namespace = XMLNode(kind: .namespace)
        namespace.name = prefix
        namespace.stringValue = uri
        element.addNamespace(namespace)
        parent.addChild(element)
        return element
    }
}

extension FileFavorite {
    struct Snapshot: Sendable {
        let isFavorite: Bool
        let sessionOnly: Bool
        var note: String? = nil
        var updatedDigest: String? = nil
    }

    private struct Metadata {
        let format: FavoriteContainer.Format?
        let properties: NSDictionary
        let favorite: Bool

        init(_ source: CGImageSource?) {
            guard let source, CGImageSourceGetCount(source) > 0 else {
                format = nil; properties = [:]; favorite = false
                return
            }
            let type = CGImageSourceGetType(source).map { $0 as String }
            format = CGImageSourceGetCount(source) == 1 && CGImageSourceGetStatus(source) == .statusComplete
                ? type.flatMap(FavoriteContainer.Format.init(rawValue:)) : nil
            let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [String: Any] ?? [:]
            let iptcKey = kCGImagePropertyIPTCDictionary as String
            let keywordKey = kCGImagePropertyIPTCKeywords as String
            var iptc = properties[iptcKey] as? [String: Any] ?? [:]
            let keywords = iptc[keywordKey] as? [String] ?? (iptc[keywordKey] as? String).map { [$0] } ?? []
            let xmp = CGImageSourceCopyMetadataAtIndex(source, 0, nil)
            let subject = xmp.flatMap { CGImageMetadataCopyTagWithPath($0, nil, "dc:subject" as CFString) }
            let values = subject.flatMap(CGImageMetadataTagCopyValue) as? [CGImageMetadataTag] ?? []
            favorite = keywords.contains(keyword)
                || values.contains { CGImageMetadataTagCopyValue($0) as? String == keyword }
            var comparable = properties
            // IPTC Keywords may be a synthesized view of XMP or legacy IPTC.
            // Both sets of unrelated keywords are protected by the container edit.
            iptc.removeValue(forKey: keywordKey)
            comparable[iptcKey] = iptc.isEmpty ? nil : iptc
            comparable.removeValue(forKey: kCGImagePropertyFileSize as String)
            self.properties = comparable as NSDictionary
        }
    }

    private struct LegacyFavorite {
        let favorite: Bool
        let digest: String
        let note: String
        var receipt: String { favorite ? "favorite" : "removed" }
    }

    private static func legacy(_ image: URL) throws -> LegacyFavorite? {
        let (url, data) = try companion(for: image)
        guard let data else { return nil }
        let packet = try FavoriteXMP(data)
        let positive = try packet.hasFavorite()
        guard positive || packet.legacyRemoval else { return nil }
        return LegacyFavorite(favorite: positive, digest: digest(data),
            note: "Legacy companion “\(url.lastPathComponent)” was left untouched; its ownership cannot be verified.")
    }

    private static func isRAW(_ image: URL) -> Bool {
        UTType(filenameExtension: image.pathExtension)?.conforms(to: .rawImage) == true
    }

    static func load(_ image: URL, expectedDigest: String) -> Snapshot {
        let embedded = Metadata(CGImageSourceCreateWithURL(image as CFURL, nil))
        let format = isRAW(image) ? nil : embedded.format
        do {
            guard let old = try legacy(image) else {
                return Snapshot(isFavorite: embedded.favorite, sessionOnly: format == nil)
            }
            // The explicit old Framewise removal marker is the only legacy
            // value allowed to override an embedded positive Favorite.
            guard old.favorite != embedded.favorite else {
                return Snapshot(isFavorite: embedded.favorite, sessionOnly: format == nil, note: old.note)
            }
            guard let format else {
                return Snapshot(isFavorite: old.favorite, sessionOnly: true, note: old.note)
            }
            do {
                let data = try Data(contentsOf: image)
                let packet = try FavoriteContainer.process(data, format: format).packet
                if let packet, try FavoriteXMP(packet).imported(old.receipt) {
                    return Snapshot(isFavorite: embedded.favorite, sessionOnly: false, note: old.note)
                }
                let updated = try write(old.favorite, to: image, expectedDigest: expectedDigest, importing: old)
                return Snapshot(isFavorite: old.favorite, sessionOnly: false, note: old.note, updatedDigest: updated)
            } catch {
                return Snapshot(isFavorite: old.favorite, sessionOnly: true,
                                note: "Couldn’t migrate the Favorite. \(error.localizedDescription) \(old.note)")
            }
        } catch {
            return Snapshot(isFavorite: embedded.favorite, sessionOnly: format == nil,
                            note: "Legacy XMP companion ignored and left untouched. \(error.localizedDescription)")
        }
    }

    /// Returns the verified new checksum, allowing the review's change detection
    /// to accept this edit without weakening guards for rotation or Trash.
    static func write(_ favorite: Bool, to image: URL, expectedDigest: String) throws -> String {
        // An ambiguous or unreadable companion never prevents ordinary embedded edits.
        let old = try? legacy(image)
        return try write(favorite, to: image, expectedDigest: expectedDigest,
                         importing: old?.favorite != favorite ? old : nil)
    }

    private static func write(_ favorite: Bool, to image: URL, expectedDigest: String, importing old: LegacyFavorite?) throws -> String {
        let receipt = old?.receipt
        try Task.checkCancellation()
        let before = try fileStat(image)
        let original = try Data(contentsOf: image)
        guard digest(original) == expectedDigest else { throw StorageError.changed }
        let source = Metadata(CGImageSourceCreateWithData(original as CFData, nil))
        guard !isRAW(image), let format = source.format else { throw StorageError.unsafe }
        if favorite && source.favorite && receipt == nil { return expectedDigest }
        let candidate = try FavoriteContainer.process(original, format: format, favorite: favorite, receipt: receipt).bytes
        guard candidate != original else {
            guard favorite == source.favorite else { throw StorageError.unsafe }
            return expectedDigest
        }

        guard before.st_mode & 0o222 != 0, FileManager.default.isWritableFile(atPath: image.path) else {
            throw CocoaError(.fileWriteNoPermission)
        }
        let manager = FileManager.default
        let staging = try manager.url(for: .itemReplacementDirectory, in: .userDomainMask,
                                      appropriateFor: image, create: true)
        defer { try? manager.removeItem(at: staging) }
        let temporary = staging.appendingPathComponent(image.lastPathComponent)
        try candidate.write(to: temporary, options: .withoutOverwriting)
        let updatedDigest = digest(candidate)
        guard try digestFile(temporary) == updatedDigest else { throw StorageError.verification }
        let output = Metadata(CGImageSourceCreateWithURL(temporary as CFURL, nil))
        guard output.format == format, output.favorite == favorite,
              output.properties == source.properties else { throw StorageError.unsafe }
        if let receipt {
            guard let packet = try FavoriteContainer.process(candidate, format: format).packet,
                  try FavoriteXMP(packet).imported(receipt) else { throw StorageError.unsafe }
        }

        // Copy POSIX metadata, ACL and extended attributes (including resource
        // forks) before publication. Refuse if the volume won't preserve them.
        let copyResult = image.withUnsafeFileSystemRepresentation { src in
            temporary.withUnsafeFileSystemRepresentation { dst -> Int32 in
                guard let src, let dst else { return -1 }
                return copyfile(src, dst, nil, copyfile_flags_t(COPYFILE_METADATA | COPYFILE_NOFOLLOW))
            }
        }
        guard copyResult == 0 else { throw posixError() }
        let ready = try fileStat(temporary)
        guard ready.st_dev == before.st_dev, ready.st_mode == before.st_mode,
              ready.st_uid == before.st_uid, ready.st_gid == before.st_gid,
              ready.st_flags == before.st_flags else { throw StorageError.attributes }
        let handle = try FileHandle(forReadingFrom: temporary)
        defer { try? handle.close() }
        try handle.synchronize()
        guard try digestFile(temporary) == updatedDigest else { throw StorageError.attributes }
        if let old, try legacy(image)?.digest != old.digest { throw StorageError.changed }
        let current = try fileStat(image)
        guard sameVersion(before, current), try digestFile(image) == expectedDigest,
              try sameVersion(current, fileStat(image)) else { throw StorageError.changed }
        try Task.checkCancellation()
        let result = temporary.withUnsafeFileSystemRepresentation { src in
            image.withUnsafeFileSystemRepresentation { dst -> Int32 in
                guard let src, let dst else { return -1 }
                return rename(src, dst)
            }
        }
        guard result == 0 else { throw posixError() }
        return updatedDigest
    }

    private static func fileStat(_ url: URL) throws -> stat {
        var value = stat()
        guard url.isFileURL, url.withUnsafeFileSystemRepresentation({
            guard let path = $0 else { return -1 }
            return lstat(path, &value)
        }) == 0 else { throw posixError() }
        guard value.st_mode & S_IFMT == S_IFREG, value.st_nlink == 1,
              value.st_flags & UInt32(UF_IMMUTABLE | SF_IMMUTABLE | UF_APPEND | SF_APPEND) == 0 else {
            throw StorageError.attributes
        }
        return value
    }

    private static func sameVersion(_ a: stat, _ b: stat) -> Bool {
        a.st_dev == b.st_dev && a.st_ino == b.st_ino && a.st_size == b.st_size
            && a.st_mtimespec.tv_sec == b.st_mtimespec.tv_sec && a.st_mtimespec.tv_nsec == b.st_mtimespec.tv_nsec
            && a.st_ctimespec.tv_sec == b.st_ctimespec.tv_sec && a.st_ctimespec.tv_nsec == b.st_ctimespec.tv_nsec
    }

    private static func posixError() -> POSIXError { POSIXError(POSIXErrorCode(rawValue: errno) ?? .EIO) }
    private static func digest(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }


    private static func digestFile(_ url: URL) throws -> String {
        let stream = try FileHandle(forReadingFrom: url)
        defer { try? stream.close() }
        var hash = SHA256()
        while let bytes = try stream.read(upToCount: 1024 * 1024), !bytes.isEmpty {
            try Task.checkCancellation()
            hash.update(data: bytes)
        }
        return hash.finalize().map { String(format: "%02x", $0) }.joined()
    }

    enum StorageError: LocalizedError {
        case unsafe, invalidSidecar, ambiguousSidecar, changed, attributes, verification

        var errorDescription: String? {
            switch self {
            case .unsafe: "Framewise couldn’t verify a lossless metadata update for this image."
            case .invalidSidecar: "The XMP companion is invalid or unreadable."
            case .ambiguousSidecar: "Several image files share the name of this XMP companion."
            case .changed: "The image changed while saving. Scan again before retrying."
            case .attributes: "Framewise couldn’t safely replace this file and preserve its attributes."
            case .verification: "The temporary file did not match the verified update. The original was left untouched."
            }
        }
    }
}
