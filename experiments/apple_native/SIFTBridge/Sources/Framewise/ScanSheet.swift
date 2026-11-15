import CoreImage
import CoreImage.CIFilterBuiltins
import CSIFT
import Foundation
import ImageIO
import UniformTypeIdentifiers

enum ScanLayout: String, CaseIterable, Identifiable, Sendable {
    case single = "Single photo"
    case prints = "Separate prints"
    case polaroids = "Polaroids"
    var id: Self { self }
}

enum ScanSheet {
    enum Failure: LocalizedError {
        case unreadable, boundary, border
        var errorDescription: String? {
            switch self {
            case .unreadable: "The sheet could not be opened as a single image."
            case .boundary: "Couldn’t identify the photo boundaries. Leave space around each print and use a contrasting background."
            case .border: "Couldn’t confidently identify the wide Polaroid border."
            }
        }
    }

    static func process(master: URL, layout: ScanLayout, in folder: URL, correctPolaroids: Bool = true) throws -> [URL] {
        guard let source = CGImageSourceCreateWithURL(master as CFURL, nil),
              CGImageSourceGetCount(source) == 1,
              let image = CIImage(contentsOf: master, options: [.applyOrientationProperty: true])
        else { throw Failure.unreadable }
        let context = CIContext()
        let colorSpace = CGColorSpace(name: CGColorSpace.sRGB)!
        let regions = layout == .single ? [] : try quads(image, context: context, polaroids: layout == .polaroids)
        let staging = folder.appendingPathComponent(".prints-\(UUID().uuidString)", isDirectory: true)
        let destination = folder.appendingPathComponent("Prints", isDirectory: true)
        try FileManager.default.createDirectory(at: staging, withIntermediateDirectories: false)
        defer { try? FileManager.default.removeItem(at: staging) }

        var names: [String] = []
        for index in 0..<max(1, regions.count) {
            try Task.checkCancellation()
            var printImage = image
            if !regions.isEmpty {
                let filter = CIFilter.perspectiveCorrection()
                filter.inputImage = image
                let corners = regions[index].map {
                    CGPoint(x: image.extent.minX + $0.x * image.extent.width,
                            y: image.extent.minY + (1 - $0.y) * image.extent.height)
                }
                filter.topLeft = corners[0]; filter.topRight = corners[1]
                filter.bottomRight = corners[2]; filter.bottomLeft = corners[3]
                guard let output = filter.outputImage else { throw Failure.boundary }
                printImage = output
            }
            if layout == .polaroids {
                printImage = try uprightPolaroid(printImage, context: context)
            }
            let name = String(format: "%02d.tiff", index + 1)
            let url = staging.appendingPathComponent(name)
            if layout == .polaroids && correctPolaroids {
                let originals = staging.appendingPathComponent("Uncorrected", isDirectory: true)
                try FileManager.default.createDirectory(at: originals, withIntermediateDirectories: true)
                try context.writeTIFFRepresentation(of: printImage, to: originals.appendingPathComponent(name),
                                                     format: .RGBA16, colorSpace: colorSpace)
                try correctedTIFF(printImage, to: url, context: context, colorSpace: colorSpace)
            } else {
                try context.writeTIFFRepresentation(of: printImage, to: url, format: .RGBA16, colorSpace: colorSpace)
            }
            names.append(name)
        }
        try Task.checkCancellation()
        try FileManager.default.moveItem(at: staging, to: destination)
        return names.map { destination.appendingPathComponent($0) }
    }

    private static func grayscale(_ image: CIImage, context: CIContext, width: Int, height: Int) throws -> [UInt8] {
        let extent = image.extent
        let scaled = image.transformed(by: CGAffineTransform(translationX: -extent.minX, y: -extent.minY))
            .transformed(by: CGAffineTransform(scaleX: CGFloat(width) / extent.width, y: CGFloat(height) / extent.height))
        guard let rendered = context.createCGImage(scaled, from: CGRect(x: 0, y: 0, width: width, height: height)) else {
            throw Failure.unreadable
        }
        var bytes = [UInt8](repeating: 0, count: width * height)
        let success = bytes.withUnsafeMutableBytes { buffer in
            guard let bitmap = CGContext(data: buffer.baseAddress, width: width, height: height, bitsPerComponent: 8,
                                         bytesPerRow: width, space: CGColorSpaceCreateDeviceGray(), bitmapInfo: 0)
            else { return false }
            bitmap.draw(rendered, in: CGRect(x: 0, y: 0, width: width, height: height))
            return true
        }
        guard success else { throw Failure.unreadable }
        return bytes
    }

    private static func quads(_ image: CIImage, context: CIContext, polaroids: Bool) throws -> [[CGPoint]] {
        let scale = min(1, 1800 / max(image.extent.width, image.extent.height))
        let width = max(1, Int(image.extent.width * scale))
        let height = max(1, Int(image.extent.height * scale))
        let gray = try grayscale(image, context: context, width: width, height: height)
        var corners = [Float](repeating: 0, count: 160)
        let count = Int(np_scan_quads(gray, Int32(width), Int32(height), polaroids ? 1 : 0, &corners))
        guard polaroids ? (1...4).contains(count) : (1...20).contains(count) else { throw Failure.boundary }
        let cards = (0..<count).map { offset in
            (0..<4).map { CGPoint(x: Double(corners[offset * 8 + $0 * 2]), y: Double(corners[offset * 8 + $0 * 2 + 1])) }
        }
        func center(_ card: [CGPoint]) -> CGPoint {
            CGPoint(x: card.map(\.x).reduce(0, +) / 4, y: card.map(\.y).reduce(0, +) / 4)
        }
        var rows: [[[CGPoint]]] = []
        for card in cards.sorted(by: { center($0).y < center($1).y }) {
            let height = card.map(\.y).max()! - card.map(\.y).min()!
            if let row = rows.firstIndex(where: { abs(center($0[0]).y - center(card).y) < height * 0.35 }) {
                rows[row].append(card)
            } else { rows.append([card]) }
        }
        return rows.flatMap { $0.sorted { center($0).x < center($1).x } }
    }

    private static func uprightPolaroid(_ image: CIImage, context: CIContext) throws -> CIImage {
        let gray = try grayscale(image, context: context, width: 400, height: 320)
        func mean(_ xs: Range<Int>, _ ys: Range<Int>) -> Double {
            let sum = ys.reduce(0) { total, y in total + xs.reduce(0) { $0 + Int(gray[y * 400 + $1]) } }
            return Double(sum) / Double(xs.count * ys.count)
        }
        let scores = [
            (mean(100..<300, 16..<80), CGImagePropertyOrientation.down),
            (mean(320..<384, 80..<240), .right),
            (mean(100..<300, 240..<304), .up),
            (mean(16..<80, 80..<240), .left)
        ]
        // Only compare opposite edges that can leave the print upright in
        // portrait orientation. Bright image content near a short border can
        // otherwise obscure the wide border when all four means compete.
        let portraitEdges = scores.filter { _, orientation in
            let size = image.oriented(orientation).extent.size
            return size.height > size.width
        }.sorted { $0.0 > $1.0 }
        guard portraitEdges.count == 2, portraitEdges[0].0 >= 90,
              portraitEdges[0].0 - portraitEdges[1].0 >= 25 else { throw Failure.border }
        return image.oriented(portraitEdges[0].1)
    }

    private static func correctedTIFF(_ image: CIImage, to url: URL, context: CIContext,
                                      colorSpace: CGColorSpace) throws {
        // The CLI's normalized sigmoid, gamma, level, gamma and red gamma.
        func sigmoid(_ x: Double) -> Double { 1 / (1 + exp(4 * (0.35 - x))) }
        let low = sigmoid(0), span = sigmoid(1) - low
        let curve = (0...65535).map { sample -> (UInt16, UInt16) in
            let contrasted = (sigmoid(Double(sample) / 65535) - low) / span
            let leveled = min(1, max(0, (pow(contrasted, 1 / 1.70) - 0.05) / 0.935))
            let value = pow(leveled, 1 / 1.09)
            return (UInt16((pow(value, 1 / 1.04) * 65535).rounded()), UInt16((value * 65535).rounded()))
        }
        let bounds = image.extent.integral
        let width = Int(bounds.width), height = Int(bounds.height)
        let stride = width * 8
        var pixels = Data(count: stride * height)
        try pixels.withUnsafeMutableBytes { buffer in
            context.render(image, toBitmap: buffer.baseAddress!, rowBytes: stride,
                           bounds: bounds, format: .RGBA16, colorSpace: colorSpace)
            let samples = buffer.bindMemory(to: UInt16.self)
            for row in 0..<height {
                if row % 32 == 0 { try Task.checkCancellation() }
                for column in 0..<width {
                    let index = (row * width + column) * 4
                    samples[index] = curve[Int(samples[index])].0
                    samples[index + 1] = curve[Int(samples[index + 1])].1
                    samples[index + 2] = curve[Int(samples[index + 2])].1
                }
            }
        }
        let corrected = CIImage(bitmapData: pixels, bytesPerRow: stride,
                                size: bounds.size, format: .RGBA16, colorSpace: colorSpace)
        try context.writeTIFFRepresentation(of: corrected, to: url, format: .RGBA16, colorSpace: colorSpace)
    }
}
