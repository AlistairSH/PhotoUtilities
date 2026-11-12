import CryptoKit
import Foundation

/// Edits only container records that hold XMP or IPTC keywords. All other ranges
/// are copied verbatim, including JPEG scans, PNG IDAT, TIFF strips/tiles and PSD layers.
enum FavoriteContainer {
    enum Format: String {
        case jpeg = "public.jpeg", png = "public.png", tiff = "public.tiff", psd = "com.adobe.photoshop-image"
    }

    private static let unsafe = FileFavorite.StorageError.unsafe
    private static let jpegXMP = Data("http://ns.adobe.com/xap/1.0/\0".utf8)
    private static let pngXMPName = Data("XML:com.adobe.xmp\0".utf8)
    private static let pngXMP = pngXMPName + Data(repeating: 0, count: 4)
    private static let photoshop = Data("Photoshop 3.0\0".utf8)

    /// With no requested change, only reads the packet. Structural ambiguity fails closed.
    static func process(_ data: Data, format: Format, favorite: Bool? = nil,
                        receipt: String? = nil) throws -> (bytes: Data, packet: Data?) {
        var packet: Data?
        var seenPacket = false
        func xmp(_ original: Data?) throws -> Data? {
            guard !seenPacket else { throw unsafe }
            seenPacket = true
            packet = original
            guard let favorite, original != nil || favorite || receipt != nil else { return original }
            let xml: FavoriteXMP
            do { xml = try FavoriteXMP(original) } catch { throw unsafe }
            return try xml.update(favorite: favorite, receipt: receipt) ? xml.data : original
        }

        var edits: [(Range<Int>, Data)] = []
        func edit(_ range: Range<Int>, _ value: Data) {
            if data[range] != value { edits.append((range, value)) }
        }

        switch format {
        case .jpeg:
            guard data.starts(with: [0xff, 0xd8]) else { throw unsafe }
            var p = 2, firstScan: Int?
            var ended = false, entropy = false, hasPictureIndex = false
            var xmpEdit: (segment: Range<Int>, packet: Range<Int>, updated: Data)?
            while p < data.count {
                if entropy {
                    guard let marker = data[p...].firstIndex(of: 0xff) else { throw unsafe }
                    p = marker
                }
                let start = p
                guard data[p] == 0xff else { throw unsafe }
                repeat { p += 1 } while p < data.count && data[p] == 0xff
                guard p < data.count else { throw unsafe }
                let marker = data[p]
                p += 1
                if entropy && (marker == 0 || (0xd0...0xd7).contains(marker)) { continue }
                entropy = false
                if marker == 0xd9 { ended = true; break }
                guard marker >= 0xc0, marker != 0xd8, !(0xd0...0xd7).contains(marker),
                      let length = data.number(p, 2), length >= 2, length <= data.count - p else { throw unsafe }
                let end = p + length
                let body = data[(p + 2)..<end]
                if marker == 0xe1 && body.starts(with: jpegXMP) {
                    let packetRange = (body.startIndex + jpegXMP.count)..<end
                    if let value = try xmp(Data(data[packetRange])), favorite != nil {
                        xmpEdit = (start..<end, packetRange, value)
                    }
                } else if marker == 0xe2 && body.starts(with: "MPF\0".utf8) {
                    hasPictureIndex = true
                } else if (marker == 0xe1 && body.starts(with: "http://ns.adobe.com/xmp/extension/".utf8))
                    || marker == 0xeb {
                    // Extended XMP and JUMBF/signatures.
                    throw unsafe
                } else if favorite == false && marker == 0xed && body.starts(with: photoshop) {
                    let original = Data(body.dropFirst(photoshop.count))
                    let updated = try resources(original, removeIPTC: true, xmp: nil)
                    if updated != original { edit(start..<end, try segment(marker, photoshop + updated)) }
                }
                if marker == 0xda {
                    if firstScan == nil { firstScan = start }
                    entropy = true
                }
                p = end
            }
            guard ended, let firstScan else { throw unsafe }
            if hasPictureIndex {
                // MPF offsets can point to gain maps and other JPEGs after EOI.
                // Change only the primary XMP bytes, without moving any offsets.
                if favorite != nil {
                    guard edits.isEmpty, let xmpEdit, xmpEdit.packet.upperBound <= firstScan else { throw unsafe }
                    let original = Data(data[xmpEdit.packet])
                    if xmpEdit.updated != original {
                        edit(xmpEdit.packet, try fixedSizeXMP(xmpEdit.updated, replacing: original))
                    }
                }
            } else {
                // Keep scanner padding after EOI. Unknown trailers may contain images.
                guard data[p...].allSatisfy({ $0 == 0 }) else { throw unsafe }
                if let xmpEdit {
                    edit(xmpEdit.segment, try segment(0xe1, jpegXMP + xmpEdit.updated))
                } else if !seenPacket, let value = try xmp(nil) {
                    edit(firstScan..<firstScan, try segment(0xe1, jpegXMP + value))
                }
            }
        case .png:
            guard data.starts(with: [137, 80, 78, 71, 13, 10, 26, 10]) else { throw unsafe }
            var p = 8, firstData: Int?, ended = false
            while p < data.count {
                guard data.count - p >= 12, let length = data.number(p, 4),
                      length <= data.count - p - 12 else { throw unsafe }
                let type = data[(p + 4)..<(p + 8)]
                let body = data[(p + 8)..<(p + 8 + length)]
                let end = p + length + 12
                if type.elementsEqual("iTXt".utf8) && body.starts(with: pngXMPName) {
                    // Language and translated keyword fields may vary. Preserve them.
                    var q = body.startIndex + pngXMPName.count
                    guard body.endIndex - q >= 4, body[q] == 0, body[q + 1] == 0,
                          let languageEnd = body[(q + 2)...].firstIndex(of: 0),
                          let translatedEnd = body[(languageEnd + 1)...].firstIndex(of: 0) else { throw unsafe }
                    q = translatedEnd + 1
                    if let value = try xmp(Data(body[q...])), favorite != nil {
                        edit(p..<end, chunk(Data(body[..<q]) + value))
                    }
                } else if (type.elementsEqual("tEXt".utf8) || type.elementsEqual("zTXt".utf8))
                    && (body.starts(with: pngXMPName) || body.starts(with: "Raw profile type xmp\0".utf8)) {
                    throw unsafe
                } else if type.elementsEqual("IDAT".utf8) && firstData == nil {
                    firstData = p
                } else if type.elementsEqual("IEND".utf8) {
                    ended = true
                    p = end
                    break
                } else if type.elementsEqual("acTL".utf8) || type.elementsEqual("dSIG".utf8) {
                    throw unsafe
                }
                p = end
            }
            guard ended, p == data.count, let firstData else { throw unsafe }
            if !seenPacket, let value = try xmp(nil) { edit(firstData..<firstData, chunk(pngXMP + value)) }
        case .psd:
            guard data.starts(with: "8BPS".utf8), data.number(4, 2) == 1,
                  let colors = data.number(26, 4), colors <= data.count - 30 else { throw unsafe }
            let p = 30 + colors
            guard let length = data.number(p, 4), length <= data.count - p - 4 else { throw unsafe }
            let end = p + 4 + length
            let updated = try resources(Data(data[(p + 4)..<end]), removeIPTC: favorite == false, xmp: xmp)
            if favorite != nil {
                guard updated.count <= Int(UInt32.max) else { throw unsafe }
                edit(p..<end, Data.number(updated.count, 4) + updated)
            }
        case .tiff:
            let little = data.starts(with: [0x49, 0x49])
            guard little || data.starts(with: [0x4d, 0x4d]),
                  data.number(2, 2, little) == 42,
                  let ifd = data.number(4, 4, little), ifd >= 8,
                  let count = data.number(ifd, 2, little), count <= (data.count - ifd - 6) / 12,
                  data.number(ifd + 2 + 12 * count, 4, little) == 0 else { throw unsafe }
            var tail = Data()
            func field(_ value: Data) throws -> Data {
                if value.count <= 4 { return value + Data(repeating: 0, count: 4 - value.count) }
                if (data.count + tail.count) % 2 != 0 { tail.append(0) }
                let offset = data.count + tail.count
                guard offset <= Int(UInt32.max) - value.count else { throw unsafe }
                tail.append(value)
                return Data.number(offset, 4, little)
            }
            var imageFields: [Int: [Int]] = [:]
            let imageTags = [273, 279, 324, 325, 513, 514] // strip, tile and legacy JPEG data
            var lastTag = -1
            var insertion = ifd + 2 + count * 12
            for index in 0..<count {
                let p = ifd + 2 + index * 12
                guard let tag = data.number(p, 2, little), tag > lastTag else { throw unsafe }
                lastTag = tag
                // DNG and TIFF-based camera RAW are never edited.
                guard tag != 50706, tag != 33421, tag != 33422 else { throw unsafe }
                if tag == 262 {
                    let interpretation = data.number(p + 8, 2, little)
                    guard interpretation != 32803, interpretation != 34892 else { throw unsafe }
                }
                if imageTags.contains(tag) {
                    guard let type = data.number(p + 2, 2, little), type == 3 || type == 4,
                          let elements = data.number(p + 4, 4, little), elements > 0 else { throw unsafe }
                    let width = type == 3 ? 2 : 4
                    let size = elements * width
                    let offset = size <= 4 ? p + 8 : data.number(p + 8, 4, little) ?? -1
                    guard offset >= 0, size <= data.count - offset else { throw unsafe }
                    imageFields[tag] = (0..<elements).map { data.number(offset + $0 * width, width, little)! }
                }
                if tag > 700 { insertion = min(insertion, p) }
                guard tag == 700 || (favorite == false && (tag == 33723 || tag == 34377)) else { continue }
                guard let type = data.number(p + 2, 2, little),
                      let elements = data.number(p + 4, 4, little),
                      type == 1 || type == 7 || (tag == 33723 && type == 4) else { throw unsafe }
                // Legacy IPTC sometimes packs its byte stream into endian-aware LONGs.
                let length = elements * (type == 4 ? 4 : 1)
                let offset = length <= 4 ? p + 8 : data.number(p + 8, 4, little) ?? -1
                guard offset >= 0, offset <= data.count, length <= data.count - offset else { throw unsafe }
                let original = Data(data[offset..<(offset + length)])
                let updated: Data?
                switch tag {
                case 700: updated = try xmp(original)
                case 33723:
                    if type == 4 {
                        func ordered(_ bytes: Data) -> Data {
                            guard little else { return bytes }
                            var result = Data()
                            for offset in stride(from: 0, to: bytes.count, by: 4) {
                                result.append(contentsOf: bytes[offset..<(offset + 4)].reversed())
                            }
                            return result
                        }
                        let iim = ordered(original)
                        var filtered = try iptc(iim)
                        filtered += Data(repeating: 0, count: (4 - filtered.count % 4) % 4)
                        updated = ordered(filtered)
                    } else { updated = try iptc(original) }
                default: updated = try resources(original, removeIPTC: true, xmp: nil)
                }
                if favorite != nil, let updated, updated != original {
                    guard updated.count <= Int(UInt32.max) else { throw unsafe }
                    edit((p + 4)..<(p + 12), Data.number(updated.count / (type == 4 ? 4 : 1), 4, little) + (try field(updated)))
                }
            }
            if !seenPacket, let value = try xmp(nil) {
                guard count < Int(UInt16.max), value.count <= Int(UInt32.max) else { throw unsafe }
                let entry = Data.number(700, 2, little) + Data.number(1, 2, little)
                    + Data.number(value.count, 4, little) + (try field(value))
                // Add a directory without moving any existing TIFF values, private
                // offsets, strip/tile data or auxiliary directories.
                if (data.count + tail.count) % 2 != 0 { tail.append(0) }
                let newIFD = data.count + tail.count
                guard newIFD <= Int(UInt32.max) - (count + 1) * 12 - 6 else { throw unsafe }
                let end = ifd + 2 + count * 12 + 4
                var directory = Data(data[(ifd + 2)..<end])
                for (range, value) in edits {
                    directory.replaceSubrange((range.lowerBound - ifd - 2)..<(range.upperBound - ifd - 2), with: value)
                }
                directory.insert(contentsOf: entry, at: insertion - ifd - 2)
                tail += Data.number(count + 1, 2, little) + directory
                edits.removeAll()
                edit(4..<8, Data.number(newIFD, 4, little))
            }
            // The metadata edits must not overlap encoded data even if a
            // malformed TIFF aliases image payloads with its directory.
            var hasImageData = false
            for (offsetTag, sizeTag) in [(273, 279), (324, 325), (513, 514)] {
                guard imageFields[offsetTag] != nil || imageFields[sizeTag] != nil else { continue }
                guard let offsets = imageFields[offsetTag], let sizes = imageFields[sizeTag],
                      offsets.count == sizes.count else { throw unsafe }
                for (offset, size) in zip(offsets, sizes) {
                    guard offset >= 8, size > 0, size <= data.count - offset,
                          !edits.contains(where: { $0.0.overlaps(offset..<(offset + size)) }) else { throw unsafe }
                    hasImageData = true
                }
            }
            guard hasImageData else { throw unsafe }
            if !tail.isEmpty { edit(data.count..<data.count, tail) }
        }

        var updated = data
        for (range, value) in edits.sorted(by: { $0.0.lowerBound > $1.0.lowerBound }) { updated.replaceSubrange(range, with: value) }
        return (updated, packet)
    }

    private static func fixedSizeXMP(_ updated: Data, replacing original: Data) throws -> Data {
        // Adobe XMP permits space padding immediately before the writable packet trailer.
        let trailers = [Data("<?xpacket end=\"w\"?>".utf8), Data("<?xpacket end='w'?>".utf8)]
        func trailer(in packet: Data) -> Range<Int>? {
            for marker in trailers {
                if let range = packet.range(of: marker, options: .backwards),
                   packet[range.upperBound...].allSatisfy({ $0 == 0 || $0 == 0x20 || $0 == 0x0a || $0 == 0x0d || $0 == 0x09 }) {
                    return range
                }
            }
            return nil
        }
        guard trailer(in: original) != nil, let end = trailer(in: updated) else { throw unsafe }
        let content = updated[..<end.lowerBound]
        let whitespace = content.reversed().prefix { [0x20, 0x0a, 0x0d, 0x09].contains($0) }.count
        let prefix = content.dropLast(whitespace)
        let suffix = updated[end.lowerBound...]
        let padding = original.count - prefix.count - suffix.count
        guard padding >= 0 else { throw unsafe }
        return prefix + Data(repeating: 0x20, count: padding) + suffix
    }

    private static func segment(_ marker: UInt8, _ body: Data) throws -> Data {
        guard body.count <= Int(UInt16.max) - 2 else { throw unsafe }
        return Data([0xff, marker]) + Data.number(body.count + 2, 2) + body
    }

    private static let crcTable: [UInt32] = (0..<256).map { byte in
        (0..<8).reduce(UInt32(byte)) { crc, _ in (crc >> 1) ^ ((crc & 1 == 0) ? 0 : 0xedb88320) }
    }
    private static func chunk(_ body: Data) -> Data {
        let typed = Data("iTXt".utf8) + body
        let crc = typed.reduce(UInt32.max) { crc, byte in
            (crc >> 8) ^ crcTable[Int((crc ^ UInt32(byte)) & 255)]
        } ^ UInt32.max
        return Data.number(body.count, 4) + typed + Data.number(Int(crc), 4)
    }

    private static func iptc(_ data: Data) throws -> Data {
        var p = 0, result = Data()
        while p < data.count {
            if data.count - p <= 3 && data[p...].allSatisfy({ $0 == 0 }) {
                result += data[p...]
                break
            }
            guard data[p] == 0x1c, let size = data.number(p + 3, 2) else { throw unsafe }
            let lengthBytes = size & 0x7fff
            var header = 5, length = size
            if size >= 0x8000 {
                guard (1...4).contains(lengthBytes), let extended = data.number(p + 5, lengthBytes) else { throw unsafe }
                header += lengthBytes
                length = extended
            }
            guard header <= data.count - p, length <= data.count - p - header else { throw unsafe }
            let end = p + header + length
            if data[p + 1] != 2 || data[p + 2] != 25
                || !data[(p + header)..<end].elementsEqual(FileFavorite.keyword.utf8) {
                result += data[p..<end]
            }
            p = end
        }
        return result
    }

    private static func resources(_ data: Data, removeIPTC: Bool, xmp: ((Data?) throws -> Data?)?) throws -> Data {
        var p = 0, records: [(header: Data, id: Int, value: Data, padding: Data)] = []
        var sawXMP = false, digest: Data?
        while p < data.count {
            guard data.count - p >= 12, data[p..<(p + 4)].elementsEqual("8BIM".utf8),
                  let id = data.number(p + 4, 2) else { throw unsafe }
            let name = Int(data[p + 6]) + 1
            let sizeOffset = p + 6 + name + name % 2
            guard let length = data.number(sizeOffset, 4), length + length % 2 <= data.count - sizeOffset - 4 else {
                throw unsafe
            }
            let end = sizeOffset + 4 + length
            var value = Data(data[(sizeOffset + 4)..<end])
            if id == 0x0424, let xmp {
                sawXMP = true
                value = try xmp(value) ?? value
            } else if id == 0x0404 && removeIPTC {
                let updated = try iptc(value)
                if updated != value {
                    guard digest == nil else { throw unsafe }
                    digest = Data(Insecure.MD5.hash(data: updated))
                    value = updated
                }
            }
            records.append((Data(data[p..<sizeOffset]), id, value,
                            Data(data[end..<(end + length % 2)])))
            p = end + length % 2
        }
        if !sawXMP, let value = try xmp?(nil) {
            records.append((Data("8BIM".utf8) + Data([0x04, 0x24, 0, 0]), 0x0424, value, Data()))
        }
        var result = Data()
        for record in records {
            let value = record.id == 0x0425 ? digest ?? record.value : record.value
            guard value.count <= Int(UInt32.max) else { throw unsafe }
            result += record.header + Data.number(value.count, 4) + value
            if value.count % 2 != 0 { result += record.padding.isEmpty ? Data([0]) : record.padding }
        }
        return result
    }
}

private extension Data {
    func number(_ offset: Int, _ size: Int, _ little: Bool = false) -> Int? {
        guard offset >= 0, size <= count - offset else { return nil }
        return (0..<size).reduce(0) { value, i in
            (value << 8) | Int(self[offset + (little ? size - i - 1 : i)])
        }
    }

    static func number(_ value: Int, _ size: Int, _ little: Bool = false) -> Data {
        Data((0..<size).map { UInt8(truncatingIfNeeded: value >> ((little ? $0 : size - $0 - 1) * 8)) })
    }
}
