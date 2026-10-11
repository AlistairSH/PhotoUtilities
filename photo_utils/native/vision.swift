import Foundation
import Vision
import ImageIO
import CoreGraphics

// Read-only, normalized image analysis. JSON lines keep preview buffers bounded.
func emit(_ row: [String: Any]) throws {
    var bytes = try JSONSerialization.data(withJSONObject: row, options: [.sortedKeys])
    bytes.append(10)
    FileHandle.standardOutput.write(bytes)
}

do {
    guard #available(macOS 14.0, *) else {
        throw NSError(domain: "photo-utils", code: 1,
                      userInfo: [NSLocalizedDescriptionKey: "Vision revision 2 requires macOS 14 or newer"])
    }
    let paths = try JSONDecoder().decode([String].self, from: FileHandle.standardInput.readDataToEndOfFile())
    var observations: [VNFeaturePrintObservation] = []
    for (index, path) in paths.enumerated() {
        try autoreleasepool {
            guard let source = CGImageSourceCreateWithURL(URL(fileURLWithPath: path) as CFURL, nil),
                  CGImageSourceGetCount(source) == 1,
                  let thumbnail = CGImageSourceCreateThumbnailAtIndex(source, 0, [
                    kCGImageSourceCreateThumbnailFromImageAlways: true,
                    kCGImageSourceCreateThumbnailWithTransform: true,
                    kCGImageSourceThumbnailMaxPixelSize: 1024
                  ] as CFDictionary),
                  let space = CGColorSpace(name: CGColorSpace.sRGB),
                  let context = CGContext(data: nil, width: thumbnail.width, height: thumbnail.height,
                    bitsPerComponent: 8, bytesPerRow: thumbnail.width * 4, space: space,
                    bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue)
            else { throw NSError(domain: "photo-utils", code: 2, userInfo: [NSLocalizedDescriptionKey: "Unsupported or unreadable single image: \(path)"]) }
            context.draw(thumbnail, in: CGRect(x: 0, y: 0, width: thumbnail.width, height: thumbnail.height))
            guard let image = context.makeImage(), let bytes = context.data else {
                throw NSError(domain: "photo-utils", code: 3)
            }
            let request = VNGenerateImageFeaturePrintRequest()
            request.revision = 2
            request.imageCropAndScaleOption = .scaleFit
            try VNImageRequestHandler(cgImage: image).perform([request])
            guard let feature = request.results?.first else { throw NSError(domain: "photo-utils", code: 4) }
            observations.append(feature)
            try emit(["type": "image", "index": index, "path": path,
                      "width": image.width, "height": image.height, "revision": request.revision,
                      "rgba": Data(bytes: bytes, count: image.width * image.height * 4).base64EncodedString()])
        }
    }
    for i in observations.indices {
        for j in observations.indices where j > i {
            var distance: Float = 0
            try observations[i].computeDistance(&distance, to: observations[j])
            try emit(["type": "pair", "a": i, "b": j, "vision_distance": distance])
        }
    }
    try emit(["type": "complete", "images": paths.count,
              "os": ProcessInfo.processInfo.operatingSystemVersionString])
} catch {
    FileHandle.standardError.write(Data("\(error)\n".utf8))
    exit(1)
}
