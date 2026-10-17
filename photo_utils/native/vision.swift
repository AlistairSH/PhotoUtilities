import Foundation
import Vision
import ImageIO
import CoreGraphics
import CoreImage

// Read-only, normalized image analysis. JSON lines keep preview buffers bounded.
func emit(_ row: [String: Any]) throws {
    var bytes = try JSONSerialization.data(withJSONObject: row, options: [.sortedKeys])
    bytes.append(10)
    FileHandle.standardOutput.write(bytes)
}

let ciContext = CIContext()
func turned(_ image: CGImage, _ q: Int) throws -> CGImage {
    if q == 0 { return image }
    let view = CIImage(cgImage: image).oriented(CGImagePropertyOrientation(rawValue: [1,6,3,8][q])!)
    guard let result = ciContext.createCGImage(view, from: view.extent) else { throw NSError(domain:"rotation",code:1) }
    return result
}
func orientationEvidence(_ image: CGImage) throws -> [String: Any] {
    var scores: [Double] = []
    for q in 0..<4 {
        let candidate = try turned(image,q)
        let faces = VNDetectFaceLandmarksRequest()
        let bodies = VNDetectHumanBodyPoseRequest()
        try VNImageRequestHandler(cgImage:candidate).perform([faces,bodies])
        var score = 0.0
        for f in faces.results ?? [] {
            if let roll = f.roll, abs(roll.doubleValue) < Double.pi/6, f.confidence >= 0.8 {
                score += Double(f.confidence) * sqrt(f.boundingBox.width*f.boundingBox.height)
            }
        }
        for body in bodies.results ?? [] {
            let points = try body.recognizedPoints(.all)
            if let neck = points[.neck], let root = points[.root], neck.confidence >= 0.5, root.confidence >= 0.5,
               neck.location.y-root.location.y > 0.1, abs(neck.location.x-root.location.x) < 0.5*(neck.location.y-root.location.y) {
                score += Double(min(neck.confidence,root.confidence))*Double(neck.location.y-root.location.y)
            }
        }
        scores.append(score)
    }
    let order = (0..<4).sorted { scores[$0] > scores[$1] }
    let chosen = order[0]
    let certain = scores[chosen] >= 0.08 && scores[chosen]-scores[order[1]] >= 0.05 && scores[chosen] >= 1.5*scores[order[1]]
    let horizon = VNDetectHorizonRequest()
    try VNImageRequestHandler(cgImage:image).perform([horizon])
    return ["quarter_turns_clockwise":certain ? chosen : 0, "status":certain ? "assessed" : "uncertain",
            "scores":scores, "evidence":"Upright faces/body pose; horizon cannot resolve upside-down ambiguity",
            "horizon_radians":horizon.results?.first?.angle ?? 0,
            "horizon_confidence":horizon.results?.first?.confidence ?? 0]
}
func rankingEvidence(_ image: CGImage, dimension: Int) throws -> [String: Any] {
    guard #available(macOS 15.0, *) else { throw NSError(domain:"ranking",code:1,userInfo:[NSLocalizedDescriptionKey:"Three-tier review requires macOS 15+"]) }
    let quality = VNDetectFaceCaptureQualityRequest()
    quality.revision = 2
    try VNImageRequestHandler(cgImage:image).perform([quality])
    var row: [String: Any] = ["status":"ok","face_qualities":(quality.results ?? []).compactMap { $0.faceCaptureQuality.map { Double($0) } }, "face_quality_revision":quality.revision]
    if dimension == 1024 {
        let aesthetic = VNCalculateImageAestheticsScoresRequest(); aesthetic.revision = 1
        try VNImageRequestHandler(cgImage:image).perform([aesthetic])
        guard let score = aesthetic.results?.first,
              let detector = CIDetector(ofType:CIDetectorTypeFace,context:ciContext,options:[CIDetectorAccuracy:CIDetectorAccuracyHigh]) else { throw NSError(domain:"ranking",code:2) }
        row["overallScore"] = score.overallScore; row["isUtility"] = score.isUtility
        row["aesthetic_revision"] = aesthetic.revision
        row["faces"] = detector.features(in:CIImage(cgImage:image),options:[CIDetectorEyeBlink:true,CIDetectorSmile:true,CIDetectorImageOrientation:1]).compactMap { feature -> [String: Any]? in
            guard let f = feature as? CIFaceFeature else { return nil }
            return ["hasSmile":f.hasSmile,"leftEyeClosed":f.leftEyeClosed,"rightEyeClosed":f.rightEyeClosed,
                    "hasLeftEyePosition":f.hasLeftEyePosition,"hasRightEyePosition":f.hasRightEyePosition]
        }
    }
    return row
}

do {
    guard #available(macOS 14.0, *) else {
        throw NSError(domain: "photo-utils", code: 1,
                      userInfo: [NSLocalizedDescriptionKey: "Vision revision 2 requires macOS 14 or newer"])
    }
    let paths = try JSONDecoder().decode([String].self, from: FileHandle.standardInput.readDataToEndOfFile())
    let ranking = CommandLine.arguments.contains("--tiers")
    let autoRotate = CommandLine.arguments.contains("--auto-rotate")
    let focus = CommandLine.arguments.contains("--focus") || ranking
    var observations: [VNFeaturePrintObservation] = []
    for (index, path) in paths.enumerated() {
        var rotation: [String: Any] = ["quarter_turns_clockwise":0,"status":"disabled"]
        for dimension in focus ? [1024, 2048] : [1024] {
        try autoreleasepool {
            guard let source = CGImageSourceCreateWithURL(URL(fileURLWithPath: path) as CFURL, nil),
                  CGImageSourceGetCount(source) == 1,
                  let decoded = CGImageSourceCreateThumbnailAtIndex(source, 0, [
                    kCGImageSourceCreateThumbnailFromImageAlways: true,
                    kCGImageSourceCreateThumbnailWithTransform: true,
                    kCGImageSourceThumbnailMaxPixelSize: dimension
                  ] as CFDictionary) else { throw NSError(domain:"decode",code:1,userInfo:[NSLocalizedDescriptionKey:"Unreadable single image: \(path)"]) }
            if autoRotate && dimension == 1024 { rotation = try orientationEvidence(decoded) }
            let thumbnail = try turned(decoded,rotation["quarter_turns_clockwise"] as! Int)
            guard let space = CGColorSpace(name: CGColorSpace.sRGB),
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
            row["rotation"] = rotation
            if ranking { row["ranking_native"] = try rankingEvidence(image,dimension:dimension) }
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
