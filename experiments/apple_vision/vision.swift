import Foundation
import Vision
import ImageIO
import CoreGraphics

// Independent read-only spike. Each input is decoded/oriented/color-converted locally.
let started = Date()
var observations: [VNFeaturePrintObservation] = []
var rows: [[String: Any]] = []
do {
    for path in CommandLine.arguments.dropFirst() {
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
        else { throw NSError(domain: "vision-spike", code: 1, userInfo: [NSLocalizedDescriptionKey: "Unsupported or unreadable single image: \(path)"]) }
        context.draw(thumbnail, in: CGRect(x: 0, y: 0, width: thumbnail.width, height: thumbnail.height))
        guard let image = context.makeImage(), let bytes = context.data else { fatalError("No pixel buffer") }
        let request = VNGenerateImageFeaturePrintRequest()
        request.revision = 2
        request.imageCropAndScaleOption = .scaleFit
        try VNImageRequestHandler(cgImage: image).perform([request])
        guard let feature = request.results?.first else { throw NSError(domain: "vision-spike", code: 2) }
        observations.append(feature)
        // Buffer order is explicitly RGBA; deliver identical normalized pixels to NumPy/OpenCV.
        rows.append(["path": path, "width": image.width, "height": image.height,
                     "rgba": Data(bytes: bytes, count: image.width * image.height * 4).base64EncodedString(),
                     "revision": request.revision, "elements": feature.elementCount])
    }
    var pairs: [[String: Any]] = []
    for i in observations.indices {
        for j in observations.indices where j > i {
            var distance: Float = 0
            try observations[i].computeDistance(&distance, to: observations[j])
            pairs.append(["a": i, "b": j, "vision_distance": distance])
        }
    }
    let output: [String: Any] = ["images": rows, "pairs": pairs, "seconds": Date().timeIntervalSince(started),
      "supported_revisions": VNGenerateImageFeaturePrintRequest.supportedRevisions.map { $0 }]
    FileHandle.standardOutput.write(try JSONSerialization.data(withJSONObject: output, options: [.sortedKeys]))
} catch {
    FileHandle.standardError.write(Data("\(error)\n".utf8)); exit(1)
}
