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
    let focus = CommandLine.arguments.contains("--focus")
    var observations: [VNFeaturePrintObservation] = []
    for (index, path) in paths.enumerated() {
        for dimension in focus ? [1024, 2048] : [1024] {
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
            var detectors: [String: Any] = [:]
            if focus {
                let face = VNDetectFaceRectanglesRequest()
                let human = VNDetectHumanRectanglesRequest(); human.upperBodyOnly = false
                let animal = VNRecognizeAnimalsRequest()
                let attention = VNGenerateAttentionBasedSaliencyImageRequest()
                let objectness = VNGenerateObjectnessBasedSaliencyImageRequest()
                let requests: [(String, VNRequest)] = [("faces",face),("people",human),("animals",animal),
                                                      ("attention",attention),("objectness",objectness)]
                func region(_ observation: VNDetectedObjectObservation) -> [String: Any] {
                    let b = observation.boundingBox
                    return ["box":[b.minX,1-b.maxY,b.width,b.height],"detection_confidence":observation.confidence]
                }
                for (name, request) in requests {
                    // An unavailable detector fails the analysis rather than
                    // masquerading as an empty subject list.
                    try handler.perform([request])
                    var boxes: [[String: Any]] = []
                    if name == "faces" { boxes = (face.results ?? []).map { region($0) } }
                    if name == "people" { boxes = (human.results ?? []).map { region($0) } }
                    if name == "animals" {
                        boxes = (animal.results ?? []).map { observation in
                            var row = region(observation)
                            row["labels"] = observation.labels.map { ["identifier":$0.identifier,"confidence":$0.confidence] as [String: Any] }
                            return row
                        }
                    }
                    if name == "attention" { boxes = (attention.results?.first?.salientObjects ?? []).map { region($0) } }
                    if name == "objectness" { boxes = (objectness.results?.first?.salientObjects ?? []).map { region($0) } }
                    detectors[name] = ["status":"ok","revision":request.revision,"regions":boxes]
                }
            }
            var row: [String: Any] = ["type":dimension == 1024 ? "image" : "focus",
                "index":index,"path":path,"width":image.width,"height":image.height,
                "max_dimension":dimension,"detectors":detectors,
                "rgba":Data(bytes:bytes,count:image.width*image.height*4).base64EncodedString()]
            if dimension == 1024 {
                let request = VNGenerateImageFeaturePrintRequest()
                request.revision = 2; request.imageCropAndScaleOption = .scaleFit
                try handler.perform([request])
                guard let feature = request.results?.first else { throw NSError(domain:"photo-utils",code:4) }
                observations.append(feature); row["revision"] = request.revision
            }
            try emit(row)
        }
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
