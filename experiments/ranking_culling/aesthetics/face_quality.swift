import Foundation
import Vision
import ImageIO

func emit(_ row: [String:Any]) throws {
    var data=try JSONSerialization.data(withJSONObject:row,options:[.sortedKeys]);data.append(10)
    FileHandle.standardOutput.write(data)
}
do {
    guard #available(macOS 14.0, *) else {throw NSError(domain:"face-quality",code:1)}
    let paths=try JSONDecoder().decode([String].self,from:FileHandle.standardInput.readDataToEndOfFile())
    for (index,path) in paths.enumerated() {
        try autoreleasepool {
            let start=Date()
            do {
                let url=URL(fileURLWithPath:path)
                guard let source=CGImageSourceCreateWithURL(url as CFURL,nil),CGImageSourceGetCount(source)==1,
                      let properties=CGImageSourceCopyPropertiesAtIndex(source,0,nil) as? [String:Any] else {throw NSError(domain:"face-quality",code:2,userInfo:[NSLocalizedDescriptionKey:"Missing/unreadable/multi-image source"])}
                let raw=(properties[kCGImagePropertyOrientation as String] as? NSNumber)?.uint32Value ?? 1
                guard let orientation=CGImagePropertyOrientation(rawValue:raw) else {throw NSError(domain:"face-quality",code:3)}
                let request=VNDetectFaceCaptureQualityRequest();request.revision=3
                try VNImageRequestHandler(url:url,orientation:orientation).perform([request])
                let faces:[[String:Any]]=(request.results ?? []).map { observation in
                    let b=observation.boundingBox
                    return ["box":[b.minX,1-b.maxY,b.width,b.height],
                        "quality":observation.faceCaptureQuality.map { $0 as Any } ?? NSNull(),
                        "detection_confidence":observation.confidence]
                }
                try emit(["index":index,"path":path,"status":"ok","revision":request.revision,
                    "orientation":raw,"faces":faces,"seconds":Date().timeIntervalSince(start)])
            } catch {
                try emit(["index":index,"path":path,"status":"failed","error":String(describing:error),"seconds":Date().timeIntervalSince(start)])
            }
        }
    }
    try emit(["type":"complete","images":paths.count,"os":ProcessInfo.processInfo.operatingSystemVersionString])
} catch {FileHandle.standardError.write(Data("\(error)\n".utf8));exit(1)}
