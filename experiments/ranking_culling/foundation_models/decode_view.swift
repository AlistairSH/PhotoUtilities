import Foundation
import ImageIO
import CoreGraphics
import UniformTypeIdentifiers
// Read one original, export one temporary full-size upright sRGB PNG.
// The caller deletes it after scoring; original bytes are never written.
do {
    guard CommandLine.arguments.count==4 else {throw NSError(domain:"decode",code:1)}
    let path=CommandLine.arguments[1],output=CommandLine.arguments[2]
    guard !FileManager.default.fileExists(atPath:output),
          let source=CGImageSourceCreateWithURL(URL(fileURLWithPath:path) as CFURL,nil),CGImageSourceGetCount(source)==1,
          let properties=CGImageSourceCopyPropertiesAtIndex(source,0,nil) as? [String:Any],
          let w=properties[kCGImagePropertyPixelWidth as String] as? Int,
          let h=properties[kCGImagePropertyPixelHeight as String] as? Int,
          let image=CGImageSourceCreateThumbnailAtIndex(source,0,[
            kCGImageSourceCreateThumbnailFromImageAlways:true,
            kCGImageSourceCreateThumbnailWithTransform:true,
            kCGImageSourceThumbnailMaxPixelSize:min(max(w,h),Int(CommandLine.arguments[3]) ?? 1024)
          ] as CFDictionary),
          let space=CGColorSpace(name:CGColorSpace.sRGB),
          let context=CGContext(data:nil,width:image.width,height:image.height,bitsPerComponent:8,
            bytesPerRow:image.width*4,space:space,bitmapInfo:CGImageAlphaInfo.premultipliedLast.rawValue|CGBitmapInfo.byteOrder32Big.rawValue)
    else {throw NSError(domain:"decode",code:2,userInfo:[NSLocalizedDescriptionKey:"Unreadable, multi-image, missing source or occupied output"])}
    context.draw(image,in:CGRect(x:0,y:0,width:image.width,height:image.height))
    guard let normalized=context.makeImage(),let destination=CGImageDestinationCreateWithURL(URL(fileURLWithPath:output) as CFURL,UTType.png.identifier as CFString,1,nil) else {throw NSError(domain:"decode",code:3)}
    CGImageDestinationAddImage(destination,normalized,nil)
    guard CGImageDestinationFinalize(destination) else {throw NSError(domain:"decode",code:4)}
    let row:[String:Any]=["source":path,"width":image.width,"height":image.height,"source_width":w,"source_height":h,
                         "orientation":properties[kCGImagePropertyOrientation as String] ?? 1,"color_space":"sRGB","bits":8]
    FileHandle.standardOutput.write(try JSONSerialization.data(withJSONObject:row,options:[.sortedKeys]))
} catch {FileHandle.standardError.write(Data("\(error)\n".utf8));exit(1)}
