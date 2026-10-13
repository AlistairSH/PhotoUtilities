import Foundation
import Vision
import ImageIO
import CoreGraphics
import UniformTypeIdentifiers

// Original-file requests, explicit EXIF orientation, bounded report previews.
func emit(_ row: [String: Any]) throws {
    var data = try JSONSerialization.data(withJSONObject: row, options: [.sortedKeys])
    data.append(10); FileHandle.standardOutput.write(data)
}
do {
    guard #available(macOS 15.0, *) else { throw NSError(domain: "aesthetics", code: 1, userInfo: [NSLocalizedDescriptionKey: "Requires macOS 15+"]) }
    let paths = try JSONDecoder().decode([String].self, from: FileHandle.standardInput.readDataToEndOfFile())
    for (index, path) in paths.enumerated() {
        try autoreleasepool {
            let started = Date()
            do {
                let url = URL(fileURLWithPath: path)
                guard let source = CGImageSourceCreateWithURL(url as CFURL, nil), CGImageSourceGetCount(source) == 1,
                    let type = CGImageSourceGetType(source),
                    ["public.jpeg", "public.heic", "public.heif", "public.png", "public.tiff"].contains(type as String),
                    let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [String: Any]
                else { throw NSError(domain: "aesthetics", code: 2, userInfo: [NSLocalizedDescriptionKey: "Missing, unsupported, unreadable or multi-image input"]) }
                let rawOrientation = (properties[kCGImagePropertyOrientation as String] as? NSNumber)?.uint32Value ?? 1
                guard let orientation = CGImagePropertyOrientation(rawValue: rawOrientation) else { throw NSError(domain: "aesthetics", code: 3) }
                let request = VNCalculateImageAestheticsScoresRequest(); request.revision = 1
                try VNImageRequestHandler(url: url, orientation: orientation).perform([request])
                guard let observation = request.results?.first, observation.overallScore.isFinite else { throw NSError(domain: "aesthetics", code: 4) }
                guard let preview = CGImageSourceCreateThumbnailAtIndex(source, 0, [
                    kCGImageSourceCreateThumbnailFromImageAlways: true,
                    kCGImageSourceCreateThumbnailWithTransform: true,
                    kCGImageSourceThumbnailMaxPixelSize: 1200
                ] as CFDictionary) else { throw NSError(domain: "aesthetics", code: 5) }
                let bytes = NSMutableData()
                guard let destination = CGImageDestinationCreateWithData(bytes, UTType.jpeg.identifier as CFString, 1, nil) else { throw NSError(domain: "aesthetics", code: 6) }
                CGImageDestinationAddImage(destination, preview, [kCGImageDestinationLossyCompressionQuality: 0.85] as CFDictionary)
                guard CGImageDestinationFinalize(destination) else { throw NSError(domain: "aesthetics", code: 7) }
                try emit(["index":index,"path":path,"status":"ok","overallScore":observation.overallScore,
                    "isUtility":observation.isUtility,"revision":request.revision,"orientation":rawOrientation,
                    "preview":(bytes as Data).base64EncodedString(),"preview_width":preview.width,"preview_height":preview.height,
                    "seconds":Date().timeIntervalSince(started)])
            } catch {
                try emit(["index":index,"path":path,"status":"failed","error":String(describing:error),"seconds":Date().timeIntervalSince(started)])
            }
        }
    }
    try emit(["type":"complete","images":paths.count,"os":ProcessInfo.processInfo.operatingSystemVersionString])
} catch { FileHandle.standardError.write(Data("\(error)\n".utf8)); exit(1) }
