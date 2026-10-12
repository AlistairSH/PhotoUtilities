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
            let request = VNDetectFaceRectanglesRequest()
            try VNImageRequestHandler(cgImage: image).perform([request])
            let faces = (request.results ?? []).map { face -> [String: Any] in
                let box = face.boundingBox
                return ["box": [box.minX, 1 - box.maxY, box.width, box.height],
                        "detection_confidence": face.confidence]
            }
            try emit(["type": "image", "index": index, "path": path,
                      "width": image.width, "height": image.height, "faces": faces, "face_revision": request.revision,
                      "rgba": Data(bytes: bytes, count: image.width * image.height * 4).base64EncodedString()])
        }
    }
    try emit(["type": "complete", "images": paths.count,
              "os": ProcessInfo.processInfo.operatingSystemVersionString])
} catch {
    FileHandle.standardError.write(Data("\(error)\n".utf8))
    exit(1)
}
