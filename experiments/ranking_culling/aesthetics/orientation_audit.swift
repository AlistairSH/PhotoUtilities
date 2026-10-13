import Foundation
import Vision
import ImageIO
// A diagnostic only: compare original URL+EXIF with full-size transformed pixels.
func score(_ handler: VNImageRequestHandler) throws -> Float {
    let request = VNCalculateImageAestheticsScoresRequest(); request.revision = 1
    try handler.perform([request])
    guard let result = request.results?.first else { throw NSError(domain:"audit",code:1) }
    return result.overallScore
}
do {
    let paths = try JSONDecoder().decode([String].self,from:FileHandle.standardInput.readDataToEndOfFile())
    for path in paths {
        try autoreleasepool {
            let url=URL(fileURLWithPath:path)
            guard let source=CGImageSourceCreateWithURL(url as CFURL,nil),
                  let properties=CGImageSourceCopyPropertiesAtIndex(source,0,nil) as? [String:Any],
                  let width=properties[kCGImagePropertyPixelWidth as String] as? Int,
                  let height=properties[kCGImagePropertyPixelHeight as String] as? Int else {throw NSError(domain:"audit",code:2)}
            let orientationRaw=(properties[kCGImagePropertyOrientation as String] as? NSNumber)?.uint32Value ?? 1
            guard let orientation=CGImagePropertyOrientation(rawValue:orientationRaw),
                  let upright=CGImageSourceCreateThumbnailAtIndex(source,0,[
                      kCGImageSourceCreateThumbnailFromImageAlways:true,
                      kCGImageSourceCreateThumbnailWithTransform:true,
                      kCGImageSourceThumbnailMaxPixelSize:max(width,height)
                  ] as CFDictionary) else {throw NSError(domain:"audit",code:3)}
            let original=try score(VNImageRequestHandler(url:url,orientation:orientation))
            guard let rawImage=CGImageSourceCreateImageAtIndex(source,0,nil) else {throw NSError(domain:"audit",code:4)}
            let rawDecoded=try score(VNImageRequestHandler(cgImage:rawImage,orientation:orientation))
            let transformed=try score(VNImageRequestHandler(cgImage:upright,orientation:.up))
            let row:[String:Any]=["path":path,"orientation":orientationRaw,"url_score":original,
                "upright_pixels_score":transformed,"difference":transformed-original,
                "imageio_raw_score":rawDecoded,"url_vs_raw_difference":rawDecoded-original,
                "raw_vs_upright_difference":transformed-rawDecoded,
                "raw_dimensions":[width,height],"upright_dimensions":[upright.width,upright.height]]
            var data=try JSONSerialization.data(withJSONObject:row,options:[.sortedKeys]);data.append(10)
            FileHandle.standardOutput.write(data)
        }
    }
} catch {FileHandle.standardError.write(Data("\(error)\n".utf8));exit(1)}
