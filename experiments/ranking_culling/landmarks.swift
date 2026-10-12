import Foundation
import Vision
import ImageIO
import CoreGraphics

// Separate facial-landmark diagnostic; preserves the working detection helper.
func region(_ observation: VNDetectedObjectObservation) -> [String: Any] {
    let b = observation.boundingBox
    return ["box": [b.minX, 1-b.maxY, b.width, b.height], "detection_confidence": observation.confidence]
}
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
        for dimension in [1024, 2048] {
        try autoreleasepool {
            guard let source = CGImageSourceCreateWithURL(URL(fileURLWithPath: path) as CFURL, nil),
                  CGImageSourceGetCount(source) == 1,
                  let thumbnail = CGImageSourceCreateThumbnailAtIndex(source, 0, [
                    kCGImageSourceCreateThumbnailFromImageAlways: true,
                    kCGImageSourceCreateThumbnailWithTransform: true,
                    kCGImageSourceThumbnailMaxPixelSize: dimension
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
            let handler = VNImageRequestHandler(cgImage: image)
            let face = VNDetectFaceLandmarksRequest()
            face.revision = VNDetectFaceLandmarksRequestRevision3
            face.constellation = .constellation76Points
            var detectors: [String: Any] = [:]
            do {
                try handler.perform([face])
                let faces = (face.results ?? []).map { observation -> [String: Any] in
                    var row = region(observation)
                    let b = observation.boundingBox
                    var features: [String: Any] = [:]
                    if let marks = observation.landmarks {
                        let parts: [(String, VNFaceLandmarkRegion2D?)] = [
                            ("leftEye", marks.leftEye), ("rightEye", marks.rightEye),
                            ("leftEyebrow", marks.leftEyebrow), ("rightEyebrow", marks.rightEyebrow),
                            ("nose", marks.nose), ("outerLips", marks.outerLips)]
                        for (name, part) in parts {
                            if let part = part {
                                features[name] = (0..<part.pointCount).map { i -> [Double] in
                                    let point = part.normalizedPoints[i]
                                    return [Double(b.minX) + Double(point.x) * Double(b.width),
                                            1 - (Double(b.minY) + Double(point.y) * Double(b.height))]
                                }
                            }
                        }
                    }
                    row["features"] = features
                    return row
                }
                detectors["faces"] = ["status":"ok", "revision":face.revision, "regions":faces]
            } catch {
                detectors["faces"] = ["status":"failed", "revision":face.revision, "error":String(describing:error)]
            }
            try emit(["type": "image", "index": index, "path": path,
                      "width": image.width, "height": image.height, "max_dimension": dimension, "detectors": detectors,
                      "rgba": Data(bytes: bytes, count: image.width * image.height * 4).base64EncodedString()])
        }
    }
    }
    try emit(["type": "complete", "images": paths.count,
              "os": ProcessInfo.processInfo.operatingSystemVersionString])
} catch {
    FileHandle.standardError.write(Data("\(error)\n".utf8))
    exit(1)
}
