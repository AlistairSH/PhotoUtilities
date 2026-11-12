import Foundation
import Vision
import ImageIO

public enum Registration {
    /// Geometric evidence only. A returned matrix is not a match verdict and
    /// supplies neither mutual SIFT inliers nor spatial coverage equivalence.
    public static func probe(reference: URL, floating: URL, padToCommonCanvas: Bool = false) throws -> [String: Any] {
        func decode(_ url: URL) throws -> CGImage {
            guard let source = CGImageSourceCreateWithURL(url as CFURL,nil), CGImageSourceGetCount(source) == 1,
                  let image = CGImageSourceCreateThumbnailAtIndex(source,0,[kCGImageSourceCreateThumbnailFromImageAlways:true,
                    kCGImageSourceCreateThumbnailWithTransform:true,kCGImageSourceThumbnailMaxPixelSize:1024] as CFDictionary) else { throw CocoaError(.fileReadCorruptFile) }
            return image
        }
        var a = try decode(reference), b = try decode(floating)
        let dimensions = [[a.width,a.height],[b.width,b.height]]
        if padToCommonCanvas {
            let width = max(a.width,b.width), height = max(a.height,b.height)
            func pad(_ image: CGImage) throws -> CGImage {
                guard let context = CGContext(data:nil,width:width,height:height,bitsPerComponent:8,
                    bytesPerRow:width*4,space:CGColorSpace(name:CGColorSpace.sRGB)!,
                    bitmapInfo:CGImageAlphaInfo.premultipliedLast.rawValue) else { throw CocoaError(.fileReadCorruptFile) }
                context.setFillColor(CGColor(gray:0,alpha:1))
                context.fill(CGRect(x:0,y:0,width:width,height:height))
                context.draw(image,in:CGRect(x:0,y:0,width:image.width,height:image.height))
                guard let result = context.makeImage() else { throw CocoaError(.fileReadCorruptFile) }
                return result
            }
            a = try pad(a); b = try pad(b)
        }
        guard a.width == b.width && a.height == b.height else { return ["status":"unsupported_dimensions","recommendation":"unassessed"] }
        let request = VNHomographicImageRegistrationRequest(targetedCGImage:b,options:[:])
        request.revision = 1
        try VNImageRequestHandler(cgImage:a).perform([request])
        guard let result = request.results?.first else { throw CocoaError(.fileReadCorruptFile) }
        let m = result.warpTransform
        let matrix = (0..<3).map { column in (0..<3).map { row in Double(m[column][row]) } }
        guard matrix.flatMap({$0}).allSatisfy({$0.isFinite}) else { throw CocoaError(.fileReadCorruptFile) }
        return ["status":"ok","matrix_columns":matrix,"confidence":Double(result.confidence),"revision":1,
                "recommendation":"unassessed","sift_equivalent":false,
                "input_dimensions":dimensions,"canvas_dimensions":[a.width,a.height],
                "canvas_policy":padToCommonCanvas ? "bottom-left-black-pad-no-resize" : "none"]
    }
}
