import Foundation
import Vision
import CoreImage
import ImageIO

let paths = try JSONDecoder().decode([String].self, from: FileHandle.standardInput.readDataToEndOfFile())
let detector = CIDetector(ofType: CIDetectorTypeFace, context: CIContext(), options: [CIDetectorAccuracy: CIDetectorAccuracyHigh])!
for path in paths {
    try autoreleasepool {
        var row: [String: Any] = ["path": path]
        do {
            guard let source = CGImageSourceCreateWithURL(URL(fileURLWithPath: path) as CFURL, nil),
                  let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
                throw NSError(domain: "cascade", code: 1)
            }
            let request = VNCalculateImageAestheticsScoresRequest()
            request.revision = 1
            try VNImageRequestHandler(cgImage: image).perform([request])
            guard let score = request.results?.first else { throw NSError(domain: "cascade", code: 2) }
            row["overallScore"] = score.overallScore
            row["isUtility"] = score.isUtility
            let features = detector.features(in: CIImage(cgImage: image), options: [CIDetectorEyeBlink: true, CIDetectorSmile: true, CIDetectorImageOrientation: 1])
            row["faces"] = features.compactMap { feature -> [String: Any]? in
                guard let f = feature as? CIFaceFeature else { return nil }
                let width = Double(image.width), height = Double(image.height)
                return ["box": [f.bounds.minX / width, 1 - f.bounds.maxY / height, f.bounds.width / width, f.bounds.height / height],
                        "hasSmile": f.hasSmile, "leftEyeClosed": f.leftEyeClosed,
                        "rightEyeClosed": f.rightEyeClosed, "hasLeftEyePosition": f.hasLeftEyePosition,
                        "hasRightEyePosition": f.hasRightEyePosition]
            }
            row["status"] = "ok"
        } catch { row["status"] = "failed"; row["error"] = String(describing: error) }
        var data = try JSONSerialization.data(withJSONObject: row, options: [.sortedKeys])
        data.append(10)
        FileHandle.standardOutput.write(data)
    }
}
