import Foundation
import CoreImage
import ImageIO
import UniformTypeIdentifiers
import Darwin

public enum ImageHandling {
    public static func properties(_ url: URL) throws -> [String: Any] {
        guard let source = CGImageSourceCreateWithURL(url as CFURL,nil),
              let properties = CGImageSourceCopyPropertiesAtIndex(source,0,nil) as? [String: Any] else { throw CocoaError(.fileReadCorruptFile) }
        return properties
    }
    /// Display derivative only: explicit 8-bit sRGB, orientation normalized.
    /// RAW uses ImageIO's supported preview; this does not claim sensor RAW development parity.
    public static func derivative(source: URL, destination: URL, clockwiseDegrees: Double = 0,
                                  crop: CGRect? = nil, maximumDimension: Int? = nil) throws {
        guard clockwiseDegrees.isFinite, maximumDimension == nil || maximumDimension! > 0,
              source.standardizedFileURL != destination.standardizedFileURL,
              let input = CGImageSourceCreateWithURL(source as CFURL,nil), CGImageSourceGetCount(input) == 1,
              let original = CGImageSourceCreateImageAtIndex(input,0,nil) else { throw CocoaError(.fileReadCorruptFile) }
        var properties = CGImageSourceCopyPropertiesAtIndex(input,0,nil) as? [String: Any] ?? [:]
        let orientation = (properties[kCGImagePropertyOrientation as String] as? NSNumber)?.int32Value ?? 1
        var image = CIImage(cgImage:original).oriented(forExifOrientation:orientation)
        func normalize(_ input: CIImage) -> CIImage { input.transformed(by:CGAffineTransform(translationX:-input.extent.minX,y:-input.extent.minY)) }
        image = normalize(image)
        if clockwiseDegrees != 0 { image = normalize(image.transformed(by:CGAffineTransform(rotationAngle:-clockwiseDegrees * .pi/180))) }
        // Crop coordinates: pixels in the transformed upright view, origin bottom-left.
        if let crop = crop {
            guard !crop.isNull, !crop.isInfinite, crop.width > 0, crop.height > 0, image.extent.contains(crop) else { throw CocoaError(.fileReadInvalidFileName) }
            image = normalize(image.cropped(to:crop))
        }
        if let limit = maximumDimension {
            let scale = min(1,Double(limit)/max(image.extent.width,image.extent.height))
            image = image.transformed(by:CGAffineTransform(scaleX:scale,y:scale))
        }
        let space = CGColorSpace(name:CGColorSpace.sRGB)!
        guard let rendered = CIContext().createCGImage(image,from:image.extent.integral,format:.RGBA8,colorSpace:space) else { throw CocoaError(.fileWriteUnknown) }
        let ext = destination.pathExtension.lowercased()
        let types = ["png":UTType.png,"jpg":UTType.jpeg,"jpeg":UTType.jpeg,"heic":UTType.heic,"tif":UTType.tiff,"tiff":UTType.tiff]
        guard let type = types[ext] else { throw CocoaError(.fileWriteUnsupportedScheme) }
        properties[kCGImagePropertyOrientation as String] = 1
        properties[kCGImagePropertyPixelWidth as String] = rendered.width
        properties[kCGImagePropertyPixelHeight as String] = rendered.height
        // Retain supported capture/GPS/IPTC properties, but normalize geometry.
        // ImageIO does not promise arbitrary ExifTool tag or XMP round-trip parity.
        var exif = properties[kCGImagePropertyExifDictionary as String] as? [String: Any] ?? [:]
        exif[kCGImagePropertyExifPixelXDimension as String] = rendered.width
        exif[kCGImagePropertyExifPixelYDimension as String] = rendered.height
        exif.removeValue(forKey:kCGImagePropertyExifMakerNote as String)
        properties[kCGImagePropertyExifDictionary as String] = exif
        var tiff = properties[kCGImagePropertyTIFFDictionary as String] as? [String: Any] ?? [:]
        tiff[kCGImagePropertyTIFFOrientation as String] = 1
        properties[kCGImagePropertyTIFFDictionary as String] = tiff
        properties.removeValue(forKey:kCGImagePropertyProfileName as String)
        let temporary = destination.deletingLastPathComponent().appendingPathComponent(".native-\(UUID().uuidString).\(ext)")
        defer { try? FileManager.default.removeItem(at:temporary) }
        guard let output = CGImageDestinationCreateWithURL(temporary as CFURL,type.identifier as CFString,1,nil) else { throw CocoaError(.fileWriteUnknown) }
        CGImageDestinationAddImage(output,rendered,properties as CFDictionary)
        guard CGImageDestinationFinalize(output) else { throw CocoaError(.fileWriteUnknown) }
        // Atomic no-replace publication: link fails even for an occupied symlink.
        guard link(temporary.path,destination.path) == 0 else { throw NSError(domain:NSPOSIXErrorDomain,code:Int(errno)) }
    }
}
