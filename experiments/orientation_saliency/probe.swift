import Foundation
import Vision
import ImageIO
import CoreGraphics
import CoreImage

let context = CIContext()
func emit(_ row: [String:Any]) throws {
    var data=try JSONSerialization.data(withJSONObject:row,options:[.sortedKeys]);data.append(10)
    FileHandle.standardOutput.write(data)
}
let paths=try JSONDecoder().decode([String].self,from:FileHandle.standardInput.readDataToEndOfFile())
for (index,path) in paths.enumerated() {
    for q in 0..<4 {
        try autoreleasepool {
            do {
                guard let source=CGImageSourceCreateWithURL(URL(fileURLWithPath:path) as CFURL,nil),CGImageSourceGetCount(source)==1,
                      let original=CGImageSourceCreateThumbnailAtIndex(source,0,[kCGImageSourceCreateThumbnailFromImageAlways:true,kCGImageSourceCreateThumbnailWithTransform:true,kCGImageSourceThumbnailMaxPixelSize:768] as CFDictionary)
                else { throw NSError(domain:"decode",code:1) }
                let view=CIImage(cgImage:original).oriented(CGImagePropertyOrientation(rawValue:[1,6,3,8][q])!)
                guard let image=context.createCGImage(view,from:view.extent),let space=CGColorSpace(name:CGColorSpace.sRGB),
                      let pixels=CGContext(data:nil,width:image.width,height:image.height,bitsPerComponent:8,bytesPerRow:image.width*4,space:space,bitmapInfo:CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue)
                else { throw NSError(domain:"pixels",code:1) }
                pixels.draw(image,in:CGRect(x:0,y:0,width:image.width,height:image.height))
                guard let normalized=pixels.makeImage(),let bytes=pixels.data else { throw NSError(domain:"pixels",code:2) }
                let handler=VNImageRequestHandler(cgImage:normalized)
                let horizon=VNDetectHorizonRequest();horizon.revision=1
                let objects=VNGenerateObjectnessBasedSaliencyImageRequest();objects.revision=2
                let attention=VNGenerateAttentionBasedSaliencyImageRequest();attention.revision=2
                var detectors:[String:Any]=[:]
                for (name,request) in [("objects",objects as VNRequest),("attention",attention as VNRequest)] {
                    do {
                        try handler.perform([request])
                        let observations=name=="objects" ? objects.results?.first?.salientObjects : attention.results?.first?.salientObjects
                        detectors[name]=["status":"ok","boxes":(observations ?? []).map { o -> [Double] in
                            let b=o.boundingBox;return [b.minX,1-b.maxY,b.width,b.height]
                        }]
                    } catch { detectors[name]=["status":"failed","error":String(describing:error)] }
                }
                var h:[String:Any]=[:]
                do {
                    try handler.perform([horizon])
                    if let result=horizon.results?.first { h=["status":"ok","angle":result.angle,"confidence":result.confidence] }
                    else { h=["status":"missing"] }
                } catch { h=["status":"failed","error":String(describing:error)] }
                try emit(["index":index,"path":path,"q":q,"status":"ok","width":image.width,"height":image.height,
                          "rgba":Data(bytes:bytes,count:image.width*image.height*4).base64EncodedString(),"detectors":detectors,"horizon":h])
            } catch { try emit(["index":index,"path":path,"q":q,"status":"failed","error":String(describing:error)]) }
        }
    }
}
