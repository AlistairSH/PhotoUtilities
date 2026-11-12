import CoreGraphics
import CryptoKit
import Darwin
import Foundation
import ImageIO
import UniformTypeIdentifiers

struct CheckFailure: Error { let message: String }

func require(_ condition: @autoclosure () throws -> Bool, _ message: String) throws {
    guard try condition() else { throw CheckFailure(message: message) }
}

func mustFail(_ message: String, operation: () throws -> Void) throws {
    do { try operation() } catch { return }
    throw CheckFailure(message: message)
}

func hash(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
func hash(_ url: URL) throws -> String { try hash(Data(contentsOf: url)) }
func load(_ url: URL) throws -> FileFavorite.Snapshot { try FileFavorite.load(url, expectedDigest: hash(url)) }
func write(_ favorite: Bool, _ url: URL) throws {
    let checksum = try FileFavorite.write(favorite, to: url, expectedDigest: hash(url))
    try require(hash(url) == checksum, "Review checksum did not follow replacement")
}

func makeImage(_ url: URL, _ type: UTType, keywords: [String]? = nil) throws {
    let context = CGContext(data: nil, width: 32, height: 24, bitsPerComponent: 8, bytesPerRow: 0,
                            space: CGColorSpace(name: CGColorSpace.displayP3)!,
                            bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue)!
    context.setFillColor(red: 0.8, green: 0.1, blue: 0.3, alpha: 1)
    context.fill(CGRect(x: 3, y: 5, width: 21, height: 9))
    let destination = CGImageDestinationCreateWithURL(url as CFURL, type.identifier as CFString, 1, nil)!
    var properties: [CFString: Any] = [
        kCGImagePropertyOrientation: 6,
        kCGImagePropertyExifDictionary: [kCGImagePropertyExifDateTimeOriginal: "2020:02:01 03:04:05"],
        kCGImagePropertyGPSDictionary: [kCGImagePropertyGPSLatitude: 51.5, kCGImagePropertyGPSLatitudeRef: "N"],
        kCGImagePropertyTIFFDictionary: [kCGImagePropertyTIFFCompression: 5]
    ]
    if let keywords {
        properties[kCGImagePropertyIPTCDictionary] = [
            kCGImagePropertyIPTCKeywords: keywords,
            kCGImagePropertyIPTCCaptionAbstract: "Keep this caption"
        ]
    }
    CGImageDestinationAddImage(destination, context.makeImage()!, properties as CFDictionary)
    try require(CGImageDestinationFinalize(destination), "Couldn't write \(type) fixture")
}

// A minimal actual PSD: planar RGB composite, with a raw compression header.
// Image I/O can read it but doesn't have a PSD encoder on every macOS release.
func makePSD(_ url: URL) throws {
    var psd = Data("8BPS".utf8) + Data([0, 1, 0, 0, 0, 0, 0, 0, 0, 3])
    psd += Data([0, 0, 0, 16, 0, 0, 0, 16, 0, 8, 0, 3])
    psd += Data(repeating: 0, count: 14) // Empty color/resources/layer sections and raw compression.
    psd += Data((0..<768).map { UInt8(truncatingIfNeeded: $0 * 47) })
    try psd.write(to: url)
}

func be(_ d: Data, _ p: Int, _ n: Int) -> Int {
    (0..<n).reduce(0) { ($0 << 8) | Int(d[p + $1]) }
}

// Independent payload extraction from the test fixtures. Checks bytes from the
// actual encoded files, not decoded pixel equality or a mock metadata writer.
func protectedBytes(_ d: Data, ext: String) throws -> [Data] {
    switch ext {
    case "jpg":
        var p = 2, blocks: [Data] = []
        while p < d.count - 4 {
            let marker = d[p + 1], length = be(d, p + 2, 2)
            if marker == 0xda { return blocks + [Data(d[p...])] }
            if marker != 0xed && !(marker == 0xe1 && d[(p + 4)...].starts(with: "http://ns.adobe.com/xap/1.0/\0".utf8)) {
                blocks.append(Data(d[p..<(p + 2 + length)]))
            }
            p += length + 2
        }
    case "png":
        var p = 8, blocks: [Data] = []
        while p < d.count {
            let end = p + be(d, p, 4) + 12
            if d[(p + 4)..<(p + 8)] != Data("iTXt".utf8) { blocks.append(Data(d[p..<end])) }
            p = end
        }
        return blocks
    case "tif":
        func n(_ p: Int, _ size: Int) -> Int {
            d[0] == 0x4d ? be(d, p, size) : (0..<size).reduce(0) { $0 | Int(d[p + $1]) << ($1 * 8) }
        }
        let ifd = n(4, 4)
        var strip = 0, length = 0, icc = Data()
        for i in 0..<n(ifd, 2) {
            let p = ifd + 2 + i * 12
            switch n(p, 2) {
            case 273: strip = n(p + 8, n(p + 2, 2) == 3 ? 2 : 4)
            case 279: length = n(p + 8, n(p + 2, 2) == 3 ? 2 : 4)
            case 34675: icc = d.subdata(in: n(p + 8, 4)..<(n(p + 8, 4) + n(p + 4, 4)))
            default: break
            }
        }
        try require(strip > 0 && length > 0 && !icc.isEmpty, "Invalid TIFF payload fixture")
        return [Data(d[strip..<(strip + length)]), icc]
    case "psd":
        let size = 30 + be(d, 26, 4)
        return [Data(d[..<size]), Data(d[(size + 4 + be(d, size, 4))...])]
    default: break
    }
    throw CheckFailure(message: "Missing encoded payload in \(ext) fixture")
}

let legacyPacket = """
<r:RDF xmlns:r="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
       xmlns:d="http://purl.org/dc/elements/1.1/" xmlns:custom="urn:test">
  <r:Description r:about="" custom:label="Portrait">
    <d:title><r:Alt><r:li xml:lang="x-default">Original title</r:li></r:Alt></d:title>
    <d:subject><r:Bag><r:li>People</r:li><r:li>Framewise:Favorite</r:li></r:Bag></d:subject>
  </r:Description>
</r:RDF>
"""

func checkFavorites(in folder: URL) throws {
    let keywords = ["Keep me", "Framewise:Favorite-ish", "framewise:favorite"]
    for (ext, type) in [("jpg", UTType.jpeg), ("png", .png), ("tif", .tiff), ("psd", nil)] {
        for initiallyFavorite in [false, true] {
            if type == nil && initiallyFavorite { continue }
            let file = folder.appendingPathComponent("test-\(initiallyFavorite).\(ext)")
            if let type {
                try makeImage(file, type, keywords: initiallyFavorite ? keywords + [FileFavorite.keyword] : nil)
            } else { try makePSD(file) }
            if ext == "jpg" {
                let padded = try Data(contentsOf: file) + Data([0, 0])
                try padded.write(to: file)
            }
            let before = try protectedBytes(Data(contentsOf: file), ext: ext)
            try require(load(file).isFavorite == initiallyFavorite, "Incorrect initial \(ext) Favorite")
            for value in [!initiallyFavorite, initiallyFavorite, !initiallyFavorite, initiallyFavorite] {
                try write(value, file)
                try require(load(file).isFavorite == value, "Incorrect \(ext) Favorite after reopening")
                try require(protectedBytes(Data(contentsOf: file), ext: ext) == before, "Changed encoded \(ext) payload")
                if initiallyFavorite {
                    let source = CGImageSourceCreateWithURL(file as CFURL, nil)!
                    let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil)! as NSDictionary
                    let iptc = properties[kCGImagePropertyIPTCDictionary] as? NSDictionary
                    let stored = iptc?[kCGImagePropertyIPTCKeywords] as? [String] ?? []
                    try require(stored.filter { $0 != FileFavorite.keyword } == keywords, "Changed unrelated keywords")
                    try require(iptc?[kCGImagePropertyIPTCCaptionAbstract] as? String == "Keep this caption", "Lost caption")
                    let exif = properties[kCGImagePropertyExifDictionary] as? NSDictionary
                    try require(exif?[kCGImagePropertyExifDateTimeOriginal] as? String == "2020:02:01 03:04:05",
                                "Lost EXIF capture date")
                    try require(properties[kCGImagePropertyGPSDictionary] != nil && properties[kCGImagePropertyOrientation] as? Int == 6,
                                "Lost GPS or orientation")
                }
            }
            try require(!FileManager.default.fileExists(atPath: FileFavorite.sidecarURL(file).path), "Created a sidecar")
        }
    }

    let jpeg = folder.appendingPathComponent("legacy.jpg")
    let sidecar = FileFavorite.sidecarURL(jpeg)
    try makeImage(jpeg, .jpeg)
    let old = Data(legacyPacket.utf8)
    try old.write(to: sidecar)
    let before = try hash(jpeg)
    let migrated = try load(jpeg)
    try require(migrated.isFavorite && !migrated.sessionOnly && migrated.updatedDigest != nil && migrated.note != nil,
                "Favorite did not migrate and report the retained companion: \(migrated)")
    try require(hash(jpeg) != before && Data(contentsOf: sidecar) == old, "Migration changed the companion")
    try write(false, jpeg)
    try require(!load(jpeg).isFavorite, "A retained sidecar resurrected a removed Favorite")
    try require(Data(contentsOf: sidecar) == old, "Removal edited the companion")
    let externallyEdited = Data(legacyPacket.replacingOccurrences(of: "Original title", with: "Revised title").utf8)
    try externallyEdited.write(to: sidecar)
    try require(!load(jpeg).isFavorite, "An unrelated sidecar edit resurrected a removed Favorite")
    try write(true, jpeg)
    try require(load(jpeg).isFavorite, "Favorite did not survive reopening")

    let suppression = folder.appendingPathComponent("old-removal.jpg")
    try makeImage(suppression, .jpeg, keywords: ["Keep me", FileFavorite.keyword])
    let suppressionPacket = Data("""
        <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
                 xmlns:f="urn:framewise:metadata:1.0">
          <rdf:Description rdf:about=""><f:EmbeddedFavoriteRemoved>True</f:EmbeddedFavoriteRemoved></rdf:Description>
        </rdf:RDF>
        """.utf8)
    try suppressionPacket.write(to: FileFavorite.sidecarURL(suppression))
    let cleared = try load(suppression)
    try require(!cleared.isFavorite && cleared.updatedDigest != nil, "Old removal did not migrate")
    try write(true, suppression)
    try require(load(suppression).isFavorite && Data(contentsOf: FileFavorite.sidecarURL(suppression)) == suppressionPacket,
                "Old removal overrode a later explicit Favorite")

    // Embed a packet with arbitrary XMP, without using the writer under test.
    let custom = folder.appendingPathComponent("custom.jpg")
    try makeImage(custom, .jpeg)
    var customBytes = try Data(contentsOf: custom)
    let payload = Data("http://ns.adobe.com/xap/1.0/\0".utf8) + old
    let length = payload.count + 2
    customBytes.insert(contentsOf: Data([0xff, 0xe1, UInt8(length >> 8), UInt8(truncatingIfNeeded: length)]) + payload, at: 2)
    try customBytes.write(to: custom)
    try require(load(custom).isFavorite, "Existing embedded XMP Favorite not recognized")
    try write(false, custom)
    let stored = try FavoriteContainer.process(Data(contentsOf: custom), format: .jpeg).packet!
    let xml = String(decoding: stored, as: UTF8.self)
    for property in ["Original title", "xml:lang=\"x-default\"", "custom:label=\"Portrait\"", "People"] {
        try require(xml.contains(property), "Lost unrelated embedded XMP: \(property)")
    }
    try require(!load(custom).isFavorite, "XMP-only Favorite survived removal")

    let conventional = folder.appendingPathComponent("shared.xmp")
    let jpegSibling = folder.appendingPathComponent("shared.jpg")
    let pngSibling = folder.appendingPathComponent("shared.png")
    try makeImage(jpegSibling, .jpeg)
    try makeImage(pngSibling, .png)
    try old.write(to: conventional)
    let ambiguous = try load(jpegSibling)
    try require(!ambiguous.isFavorite && ambiguous.note != nil, "Ambiguous companion applied")
    try write(true, jpegSibling)
    try require(Data(contentsOf: conventional) == old, "Ambiguous sidecar changed")

    let raw = folder.appendingPathComponent("fixture.dng")
    let unsupported = Data("Not a supported image".utf8)
    try unsupported.write(to: raw)
    try old.write(to: FileFavorite.sidecarURL(raw))
    let session = try load(raw)
    try require(session.isFavorite && session.sessionOnly, "Legacy RAW Favorite did not initialize the session")
    try mustFail("Unsupported source was rewritten") { try write(false, raw) }
    try require(Data(contentsOf: raw) == unsupported && Data(contentsOf: FileFavorite.sidecarURL(raw)) == old,
                "Unsupported source or sidecar changed")

    let complex = folder.appendingPathComponent("offset-based.jpg")
    try makeImage(complex, .jpeg)
    var complexBytes = try Data(contentsOf: complex)
    complexBytes.insert(contentsOf: [0xff, 0xe2, 0, 6, 77, 80, 70, 0], at: 2)
    try complexBytes.write(to: complex)
    try mustFail("Offset-based JPEG was rewritten") { try write(true, complex) }
    try require(Data(contentsOf: complex) == complexBytes && !load(complex).isFavorite,
                "Failed verification changed the source")

    // A two-picture JPEG with a padded primary XMP packet. Both the MP index
    // and the auxiliary JPEG must remain byte-identical at their old offsets.
    let hdr = folder.appendingPathComponent("indexed.jpg")
    try makeImage(hdr, .jpeg)
    let image = try Data(contentsOf: hdr)
    func appSegment(_ marker: UInt8, _ payload: Data) -> Data {
        let size = payload.count + 2
        return Data([0xff, marker, UInt8(size >> 8), UInt8(truncatingIfNeeded: size)]) + payload
    }
    func long(_ value: Int) -> Data {
        withUnsafeBytes(of: UInt32(value).bigEndian) { Data($0) }
    }
    let packet = Data("http://ns.adobe.com/xap/1.0/\0<?xpacket begin=\"\" id=\"W5M0MpCehiHzreSzNTczkc9d\"?>".utf8)
        + Data(legacyPacket.replacingOccurrences(of: "<r:li>Framewise:Favorite</r:li>", with: "").utf8)
        + Data(repeating: 0x20, count: 2048) + Data("<?xpacket end=\"w\"?>".utf8)
    let app1 = appSegment(0xe1, packet)
    let primarySize = image.count + app1.count + 90
    let indexStart = 2 + app1.count
    let tiffBase = indexStart + 8
    let mpHeader = Data([77, 77, 0, 42, 0, 0, 0, 8, 0, 3])
    let fields = Data([
        0xb0, 0, 0, 7, 0, 0, 0, 4, 48, 49, 48, 48, // MPFVersion
        0xb0, 1, 0, 4, 0, 0, 0, 1, 0, 0, 0, 2,     // NumberOfImages
        0xb0, 2, 0, 7, 0, 0, 0, 32, 0, 0, 0, 50,   // MPEntry array
        0, 0, 0, 0                                   // No next directory
    ])
    let firstEntry = long(0x20030000) + long(primarySize) + long(0) + long(0)
    let secondEntry = long(0) + long(image.count) + long(primarySize - tiffBase) + long(0)
    let app2 = appSegment(0xe2, Data("MPF\0".utf8) + mpHeader + fields + firstEntry + secondEntry)
    let originalHDR = image.prefix(2) + app1 + app2 + image.dropFirst(2) + image
    try require(app2.count == 90, "Wrong MP index fixture length")
    try originalHDR.write(to: hdr)
    for favorite in [true, false] {
        try write(favorite, hdr)
        try require(load(hdr).isFavorite == favorite, "Indexed JPEG Favorite did not survive reopening")
        let updated = try Data(contentsOf: hdr)
        try require(updated.count == originalHDR.count && updated[indexStart...] == originalHDR[indexStart...],
                    "Indexed JPEG metadata edit moved an offset or changed image data")
    }

    let readOnly = folder.appendingPathComponent("permissions.jpg")
    try makeImage(readOnly, .jpeg)
    let contents = try hash(readOnly)
    try FileManager.default.setAttributes([.posixPermissions: 0o444], ofItemAtPath: readOnly.path)
    try mustFail("Read-only file was overwritten") { try write(true, readOnly) }
    try require(hash(readOnly) == contents, "A failed write changed the original")
    let date = Date(timeIntervalSince1970: 1_600_000_000)
    try FileManager.default.setAttributes([.posixPermissions: 0o640, .modificationDate: date], ofItemAtPath: readOnly.path)
    let creation = try FileManager.default.attributesOfItem(atPath: readOnly.path)[.creationDate] as? Date
    let attribute = "org.framewise.test"
    let value = Data("Preserve xattrs".utf8)
    try require(value.withUnsafeBytes { setxattr(readOnly.path, attribute, $0.baseAddress, value.count, 0, 0) } == 0,
                "Couldn't prepare xattr fixture")
    try write(true, readOnly)
    let attributes = try FileManager.default.attributesOfItem(atPath: readOnly.path)
    let mode = attributes[.posixPermissions] as? Int
    try require(attributes[.modificationDate] as? Date == date && attributes[.creationDate] as? Date == creation,
                "Lost original timestamps")
    var readValue = Data(count: value.count)
    let xattrLength = readValue.withUnsafeMutableBytes { getxattr(readOnly.path, attribute, $0.baseAddress, value.count, 0, 0) }
    try require(mode == 0o640 && xattrLength == value.count && readValue == value, "Lost file permissions or xattrs")
    let updated = try hash(readOnly)
    try mustFail("A stale edit was applied") { _ = try FileFavorite.write(false, to: readOnly, expectedDigest: contents) }
    try require(hash(readOnly) == updated && load(readOnly).isFavorite, "A rejected edit changed the Favorite")

    let linked = folder.appendingPathComponent("link.jpg")
    try FileManager.default.createSymbolicLink(at: linked, withDestinationURL: readOnly)
    try mustFail("A symbolic link was overwritten") { try write(false, linked) }
    try require(hash(readOnly) == updated, "Symbolic link destination changed")
}

let folder = FileManager.default.temporaryDirectory.appendingPathComponent("FramewiseFavoriteChecks-\(UUID())")
try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: false)
defer { try? FileManager.default.removeItem(at: folder) }
do {
    try checkFavorites(in: folder)
    for path in CommandLine.arguments.dropFirst() {
        let input = URL(fileURLWithPath: path)
        let copy = folder.appendingPathComponent("\(UUID()).\(input.pathExtension)")
        let before = try hash(input)
        try FileManager.default.copyItem(at: input, to: copy)
        let state = try load(copy)
        if state.sessionOnly {
            try mustFail("Unsupported sample was rewritten") { try write(!state.isFavorite, copy) }
            try require(hash(copy) == before, "Unsupported sample bytes changed")
        } else {
            let ext = input.pathExtension.lowercased()
            let layout = ["jpeg": "jpg", "tiff": "tif"][ext] ?? ext
            // The optional TIFF extractor expects a single strip. The main TIFF
            // fixtures exercise that case; other TIFF files use runtime verification.
            let originalPayload = ["jpg", "png", "psd"].contains(layout)
                ? try protectedBytes(Data(contentsOf: copy), ext: layout) : nil
            try write(!state.isFavorite, copy)
            try require(load(copy).isFavorite != state.isFavorite, "Favorite did not persist for sample")
            if let originalPayload {
                try require(protectedBytes(Data(contentsOf: copy), ext: layout) == originalPayload,
                            "Sample's encoded image data changed")
            }
            try write(state.isFavorite, copy)
        }
        try require(hash(input) == before, "Source sample changed")
        print("\(input.lastPathComponent): \(state.sessionOnly ? "session-only fallback" : "embedded toggle") verified on a copy")
    }
    print("Framewise filesystem Favorite checks passed.")
} catch {
    FileHandle.standardError.write(Data("Favorite checks failed: \(error)\n".utf8))
    exit(1)
}
