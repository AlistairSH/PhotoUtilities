import Foundation
import NativeSIFT
import CSIFT

var count = 0
func check(_ value: @autoclosure () throws -> Bool,_ name:String) throws {
    count += 1
    if try !value() { throw SIFTError(description:name) }
}
func rejects(_ action: () throws -> Void) throws {
    var failed = false
    do { try action() } catch { failed = true }
    try check(failed,"Expected rejection")
}
do {
    try check(SIFTFeatures.openCVVersion == "4.11.0","Pinned version")
    let flat = Data(repeating:128,count:64*64*4)
    let a = try SIFTFeatures(rgba:flat,width:64,height:64)
    let empty = try a.compare(to:a)
    try check(a.keypointCount == 0 && !empty.candidate && empty.inliers == 0,"No features is unassessed, not a match")
    try rejects { _ = try SIFTFeatures(rgba:flat,width:0,height:64) }
    try rejects { _ = try SIFTFeatures(rgba:flat,width:1025,height:1) }
    try rejects { _ = try SIFTFeatures(rgba:Data(),width:64,height:64) }
    try rejects { _ = try SIFTFeatures(rgba:flat,width:64,height:64,bytesPerRow:255) }
    try rejects { _ = try SIFTFeatures(rgba:flat,width:64,height:64,bytesPerRow:Int.max) }
    let size = 256
    var pixels = Data(repeating:100,count:size*size*4)
    var state: UInt64 = 14
    func next(_ maximum: Int) -> Int {
        state = state &* 6364136223846793005 &+ 1
        return Int((state >> 32) % UInt64(maximum))
    }
    pixels.withUnsafeMutableBytes { (bytes:UnsafeMutableRawBufferPointer) in
        for p in stride(from:3,to:bytes.count,by:4) { bytes[p]=255 }
        for _ in 0..<180 {
            let cx=next(size), cy=next(size), radius=next(7)+2
            let color=[UInt8(next(256)),UInt8(next(256)),UInt8(next(256))]
            for y in max(0,cy-radius)...min(size-1,cy+radius) {
                for x in max(0,cx-radius)...min(size-1,cx+radius) where (x-cx)*(x-cx)+(y-cy)*(y-cy)<=radius*radius {
                    let p=(y*size+x)*4
                    bytes[p]=color[0];bytes[p+1]=color[1];bytes[p+2]=color[2]
                }
            }
        }
    }
    let before = pixels
    let textured = try SIFTFeatures(rgba:pixels,width:size,height:size)
    let duplicate = try SIFTFeatures(rgba:pixels,width:size,height:size)
    let result = try textured.compare(to:duplicate)
    try check(textured.keypointCount >= 12 && result.candidate,"Textured identical previews match")
    try check(result == (try textured.compare(to:duplicate)),"Repeatable seeded geometry")
    try check(pixels == before,"Extraction preserves bytes")
    // Padded rows must not become image content.
    let rowBytes=size*4, paddedRowBytes=size*4+8
    var padded = Data(repeating:77,count:size*paddedRowBytes)
    for y in 0..<size { padded.replaceSubrange(y*paddedRowBytes..<y*paddedRowBytes+rowBytes,with:pixels[y*rowBytes..<y*rowBytes+rowBytes]) }
    let paddedFeatures = try SIFTFeatures(rgba:padded,width:size,height:size,bytesPerRow:paddedRowBytes)
    try check(try textured.compare(to:paddedFeatures) == result,"Stride preserves matching")
    var handle:OpaquePointer?; var error=[CChar](repeating:0,count:256)
    let invalid = flat.withUnsafeBytes { bytes in
        npsift_extract_rgba(bytes.bindMemory(to:UInt8.self).baseAddress,1,64,64,256,&handle,&error,error.count)
    }
    try check(invalid != 0 && handle == nil,"C boundary rejects truncated buffers")
    var output=NPSIFTResult()
    try check(npsift_compare(nil,nil,&output,&error,error.count) != 0,"C boundary rejects missing handles")
    print("Passed \(count) SIFT bridge checks")
} catch { FileHandle.standardError.write(Data("CHECK FAILED: \(error)\n".utf8)); exit(1) }
