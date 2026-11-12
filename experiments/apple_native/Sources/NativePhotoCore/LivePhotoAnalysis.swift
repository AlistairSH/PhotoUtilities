import Foundation
import Vision
import ImageIO
import CoreGraphics
import CoreImage

/// Live evidence acquisition shared by the app-facing coordinator. No file writes.
public enum LivePhotoAnalysis {
    private static let ciContext = CIContext()
    private static func turned(_ image: CGImage, _ q: Int) throws -> CGImage {
        if q == 0 { return image }
        let view = CIImage(cgImage: image).oriented(CGImagePropertyOrientation(rawValue: [1,6,3,8][q])!)
        guard let result = ciContext.createCGImage(view, from: view.extent) else { throw NSError(domain:"rotation",code:1) }
        return result
    }
    private static func orientationEvidence(_ image: CGImage) throws -> [String: Any] {
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
    private static func rankingEvidence(_ image: CGImage, dimension: Int) throws -> [String: Any] {
        guard #available(macOS 15.0, iOS 18.0, *) else { throw NSError(domain:"ranking",code:1,userInfo:[NSLocalizedDescriptionKey:"Three-tier review requires macOS 15+"]) }
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

    public struct Evidence {
        public let scales: [ReviewScale]
        public let featurePrint: VNFeaturePrintObservation
        public let rotation: RotationEvidence
    }
    public static func analyze(url: URL, autoRotate: Bool = true,
                               checkpoint: () throws -> Void,
                               preview: (Data, Int, Int) throws -> Void) throws -> Evidence {
        guard #available(macOS 15.0, iOS 18.0, *) else {
            throw ReviewError.invalid("Tier analysis requires macOS 15 / iOS 18 or newer")
        }
        var rotation: [String: Any] = ["quarter_turns_clockwise":0,"status":"disabled"]
        var scales: [ReviewScale] = []
        var feature: VNFeaturePrintObservation?
        for dimension in [1024, 2048] {
            try checkpoint()
            try autoreleasepool {
                guard let source = CGImageSourceCreateWithURL(url as CFURL, nil),
                      CGImageSourceGetCount(source) == 1,
                      let decoded = CGImageSourceCreateThumbnailAtIndex(source, 0, [
                        kCGImageSourceCreateThumbnailFromImageAlways:true,
                        kCGImageSourceCreateThumbnailWithTransform:true,
                        kCGImageSourceThumbnailMaxPixelSize:dimension
                      ] as CFDictionary) else { throw ReviewError.invalid("Unreadable single image: \(url.path)") }
                if autoRotate && dimension == 1024 { rotation = try orientationEvidence(decoded) }
                try checkpoint()
                let thumbnail = try turned(decoded, rotation["quarter_turns_clockwise"] as! Int)
                guard let space = CGColorSpace(name:CGColorSpace.sRGB),
                      let context = CGContext(data:nil,width:thumbnail.width,height:thumbnail.height,
                        bitsPerComponent:8,bytesPerRow:thumbnail.width*4,space:space,
                        bitmapInfo:CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue)
                else { throw ReviewError.invalid("Cannot allocate display view") }
                context.draw(thumbnail,in:CGRect(x:0,y:0,width:thumbnail.width,height:thumbnail.height))
                guard let image = context.makeImage(), let bytes = context.data else { throw ReviewError.invalid("Cannot render display view") }
                let handler = VNImageRequestHandler(cgImage: image)
                var detectors: [String: Any] = [:]
                do {
                    let face = VNDetectFaceRectanglesRequest()
                    let human = VNDetectHumanRectanglesRequest(); human.upperBodyOnly = false
                    let animal = VNRecognizeAnimalsRequest()
                    let attention = VNGenerateAttentionBasedSaliencyImageRequest()
                    let objectness = VNGenerateObjectnessBasedSaliencyImageRequest()
                    let requests: [(String, VNRequest)] = [("faces",face),("people",human),("animals",animal),
                                                          ("attention",attention),("objectness",objectness)]
                    func region(_ observation: VNDetectedObjectObservation) -> [String: Any] {
                        let b = observation.boundingBox
                        return ["box":[Double(b.minX),Double(1-b.maxY),Double(b.width),Double(b.height)],"detection_confidence":observation.confidence]
                    }
                    for (name, request) in requests {
                        try checkpoint()
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

                try checkpoint()
                let pixels = Array(UnsafeBufferPointer(start:bytes.assumingMemoryBound(to:UInt8.self),count:image.width*image.height*4))
                let ranking = try rankingEvidence(image,dimension:dimension)
                let scale = try PhotoMeasurements.measure(pixels,width:image.width,height:image.height,
                    path:url.path,dimension:dimension,detectors:detectors,ranking:ranking,checkpoint:checkpoint)
                scales.append(scale)
                if dimension == 1024 {
                    let request = VNGenerateImageFeaturePrintRequest()
                    request.revision = 2; request.imageCropAndScaleOption = .scaleFit
                    try handler.perform([request])
                    guard let observation = request.results?.first else { throw ReviewError.invalid("Missing Vision feature print") }
                    feature = observation
                    try checkpoint()
                    try preview(Data(pixels),image.width,image.height)
                }
            }
        }
        guard let feature = feature else { throw ReviewError.invalid("Missing feature print") }
        let data = try JSONSerialization.data(withJSONObject:rotation)
        return Evidence(scales:scales,featurePrint:feature,rotation:try JSONDecoder().decode(RotationEvidence.self,from:data))
    }
}

public struct RotationEvidence: Codable, Sendable {
    public let quarter_turns_clockwise: Int
    public let status: String
    public let scores: [Double]?
}

public enum PhotoMeasurements {
    /// Caller supplies upright sRGB RGBA8 display pixels and native detector evidence.
    public static func measure(_ pixels: [UInt8], width: Int, height: Int, path: String,
                               dimension: Int, detectors: [String: Any], ranking: [String: Any],
                               checkpoint: () throws -> Void = {}) throws -> ReviewScale {
        guard [1024,2048].contains(dimension), width >= 3, height >= 3,
              max(width,height) <= dimension, pixels.count == width*height*4 else {
            throw ReviewError.invalid("Invalid display pixels")
        }
        for kind in ["faces","people","animals","objectness","attention"] {
            guard let detection = detectors[kind] as? [String:Any], detection["status"] as? String == "ok",
                  let regions = detection["regions"] as? [[String:Any]], regions.allSatisfy({ row in
                      guard let b = row["box"] as? [Double] else { return false }
                      return b.count == 4 && b.allSatisfy(\.isFinite) && b[2] > 0 && b[3] > 0
                  }) else { throw ReviewError.invalid("Incomplete detector: \(kind)") }
        }
        try checkpoint()
        let focus = Focus.regions(pixels,width:width,height:height,detectors:detectors,backend:.accelerate)
        try checkpoint()
        let edges = Edges.extract(Focus.gray(pixels),width:width,height:height)
        let global = Edges.summarize(edges)
        var regions: [[String:Any]] = []
        for kind in ["faces","people","animals","objectness","attention"] {
            let detection = detectors[kind] as! [String:Any]
            for (i,r) in (detection["regions"] as! [[String:Any]]).enumerated() {
                let b = r["box"] as! [Double]
                let x = max(0,b[0]), y = max(0,b[1]), right = min(1,b[0]+b[2]), bottom = min(1,b[1]+b[3])
                regions.append(["id":"\(kind) \(i+1)","box":b,
                    "metrics":Edges.summarize(edges,box:[x,y,max(0,right-x),max(0,bottom-y)],width:width,height:height)])
            }
        }
        try checkpoint()
        let row: [String:Any] = ["path":path,"max_dimension":dimension,"pixel_size":[width,height],
            "focus":focus,"edge_flags":Edges.flags(global),"edge_regions":regions,
            "exposure":Exposure.measure(pixels,width:width,height:height,detectors:detectors),"ranking_native":ranking]
        return try JSONDecoder().decode(ReviewScale.self,from:JSONSerialization.data(withJSONObject:row))
    }
}
