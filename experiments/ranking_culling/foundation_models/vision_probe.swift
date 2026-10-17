import Foundation
import Vision
import ImageIO
import CoreGraphics

func emit(_ row: [String: Any]) throws {
    var data = try JSONSerialization.data(withJSONObject: row, options: [.sortedKeys])
    data.append(10); FileHandle.standardOutput.write(data)
}
func box(_ o: VNDetectedObjectObservation) -> [Double] {
    let b = o.boundingBox; return [b.minX, 1-b.maxY, b.width, b.height]
}
let allowed = Set(["jpg", "jpeg", "heic", "heif", "png", "tif", "tiff"])
do {
    let paths = try JSONDecoder().decode([String].self, from: FileHandle.standardInput.readDataToEndOfFile())
    for (index, path) in paths.enumerated() {
      for dimension in [1024, 2048] {
        try autoreleasepool {
          let start = Date()
          do {
            let url = URL(fileURLWithPath: path)
            guard allowed.contains(url.pathExtension.lowercased()),
              let source = CGImageSourceCreateWithURL(url as CFURL, nil), CGImageSourceGetCount(source) == 1,
              let image = CGImageSourceCreateThumbnailAtIndex(source, 0, [
                kCGImageSourceCreateThumbnailFromImageAlways: true,
                kCGImageSourceCreateThumbnailWithTransform: true,
                kCGImageSourceThumbnailMaxPixelSize: dimension
              ] as CFDictionary) else { throw NSError(domain: "vision-probe", code: 1, userInfo: [NSLocalizedDescriptionKey: "Unsupported/unreadable single image"]) }
            let handler = VNImageRequestHandler(cgImage: image)
            let classification = VNClassifyImageRequest()
            let quality = VNDetectFaceCaptureQualityRequest()
            let landmarks = VNDetectFaceLandmarksRequest()
            let people = VNDetectHumanRectanglesRequest(); people.upperBodyOnly = false
            let animals = VNRecognizeAnimalsRequest()
            let attention = VNGenerateAttentionBasedSaliencyImageRequest()
            let objectness = VNGenerateObjectnessBasedSaliencyImageRequest()
            var results: [String: Any] = [:]
            for (name, request) in [("classification", classification as VNRequest), ("face_quality", quality),
                ("landmarks", landmarks), ("people", people), ("animals", animals),
                ("attention", attention), ("objectness", objectness)] {
              let requestStart = Date()
              do {
                try handler.perform([request])
                var observations: [[String: Any]] = []
                if name == "classification" {
                  observations = (classification.results ?? []).map { ["identifier": $0.identifier, "confidence": $0.confidence] }
                } else if name == "face_quality" {
                  observations = (quality.results ?? []).map { ["box": box($0), "confidence": $0.confidence,
                    "quality": $0.faceCaptureQuality.map { $0 as Any } ?? NSNull()] }
                } else if name == "landmarks" {
                  observations = (landmarks.results ?? []).map { face in
                    var points: [String: Any] = [:]
                    for (key, region) in [("left_eye", face.landmarks?.leftEye), ("right_eye", face.landmarks?.rightEye),
                        ("outer_lips", face.landmarks?.outerLips), ("all_points", face.landmarks?.allPoints)] {
                      if let region { points[key] = (0..<region.pointCount).map { i in
                        [Double(region.normalizedPoints[i].x), Double(region.normalizedPoints[i].y)] } }
                    }
                    return ["box": box(face), "confidence": face.confidence, "face_local_bottom_left_points": points]
                  }
                } else if name == "people" { observations = (people.results ?? []).map { ["box": box($0), "confidence": $0.confidence] }
                } else if name == "animals" { observations = (animals.results ?? []).map { ["box": box($0), "labels": $0.labels.map { ["identifier": $0.identifier, "confidence": $0.confidence] }] }
                } else if name == "attention" { observations = (attention.results?.first?.salientObjects ?? []).map { ["box": box($0), "confidence": $0.confidence] }
                } else { observations = (objectness.results?.first?.salientObjects ?? []).map { ["box": box($0), "confidence": $0.confidence] } }
                results[name] = ["status": "ok", "revision": request.revision, "observations": observations,
                  "seconds": Date().timeIntervalSince(requestStart)]
              } catch { results[name] = ["status": "failed", "revision": request.revision, "error": String(describing: error)] }
            }
            try emit(["index": index, "path": path, "status": "ok", "max_dimension": dimension,
              "width": image.width, "height": image.height, "requests": results, "seconds": Date().timeIntervalSince(start)])
          } catch { try emit(["index": index, "path": path, "status": "failed", "max_dimension": dimension, "error": String(describing: error)]) }
        }
      }
    }
    try emit(["type": "complete", "images": paths.count, "os": ProcessInfo.processInfo.operatingSystemVersionString])
} catch { FileHandle.standardError.write(Data("\(error)\n".utf8)); exit(1) }
