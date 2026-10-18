import Foundation
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers
import CryptoKit
import NativePhotoCore

var checks = 0
func check(_ condition: @autoclosure () throws -> Bool, _ message: String) throws {
    checks += 1
    if try !condition() { throw NSError(domain:message,code:checks) }
}
func mustThrow(_ action: () throws -> Void) throws {
    var failed = false
    do { try action() } catch { failed = true }
    try check(failed,"Expected error")
}
func hash(_ url: URL) throws -> SHA256.Digest { SHA256.hash(data:try Data(contentsOf:url)) }

do {
    try check(try Grouping.level(distance:0.399999) == "likely","Strict likely threshold")
    try check(try Grouping.level(distance:0.40) == "potential","Likely boundary")
    try check(try Grouping.level(distance:0.45) == "unmatched","Vision boundary")
    try check(try Grouping.level(distance:0.45,sift:true) == "potential","SIFT-only")
    try check(try Grouping.level(distance:0.44,sift:true) == "likely","Dual support")
    try mustThrow { _ = try Grouping.level(distance:.nan) }
    try mustThrow { _ = try Grouping.level(distance:-1) }
    try check(Grouping.components(count:5,edges:[(0,1),(1,2)]) == [[0,1,2],[3],[4]],"Chained groups and singles")
    let flat = Focus.smooth([UInt8](repeating:128,count:400),width:20,height:20)
    let metric = Focus.metrics(flat,width:20,height:20)!
    try check(metric["tenengrad"]! < 1e-20 && metric["laplacian_variance"]! < 1e-20,"Flat image")
    try check(metric["pixels"] == 324,"One-pixel erosion")
    try check(Focus.metrics(flat,width:20,height:20,mask:[Bool](repeating:false,count:400)) == nil,"Empty mask")
    let gray: [UInt8] = (0..<1600).map { (($0%40)/5)%2 == 0 ? 0 : 255 }
    let raw = Focus.metrics(gray.map {Double($0)/255},width:40,height:40)!
    let blur = Focus.metrics(Focus.smooth(gray,width:40,height:40),width:40,height:40)!
    try check(blur["tenengrad"]! < raw["tenengrad"]! && blur["laplacian_variance"]! < raw["laplacian_variance"]!,"Controlled blur")
    let detectorKinds = ["faces","people","animals","objectness","attention"]
    var detectors = Dictionary(uniqueKeysWithValues:detectorKinds.map { ($0,["regions":[]] as [String: Any]) })
    detectors["faces"] = ["regions":[["box":[CGFloat(0),CGFloat(0),CGFloat(1),CGFloat(1)]]]]
    let rgba = (0..<1600).flatMap { i in [gray[i],gray[i],gray[i],UInt8(255)] }
    let regional = Focus.regions(rgba,width:40,height:40,detectors:detectors)
    let region = (regional["regions"] as! [[String: Any]])[0]
    try check(region["usable"] as! Bool,"Native CGFloat detector bridge")
    try check((regional["tile_tenengrad"] as! [Double]).count == 0,"Small tiles remain unmeasured")
    let gaussianVectors: [(Int,Int,String)] = [(1,1,"6e340b9cffb37a989ca544e6bb780a2c78901d3fb33738768511a30617afa01d"),
        (3,2,"b7c21b2c981102e21f1903c4b4cb536acafed5104fd9ffd8b9912cca4ebac0e5"),
        (73,69,"adad37d6737e0f2ad905dc83a3a3f457532dd7c89f9789ffcfcc67df16c67784")]
    for (w,h,expected) in gaussianVectors {
        let input = (0..<w*h).map { UInt8(($0*73+$0/17)%256) }
        let output = Data(Focus.smooth(input,width:w,height:h).map { UInt8(($0*255).rounded()) })
        let actual = SHA256.hash(data:output).map { String(format:"%02x",$0) }.joined()
        try check(actual == expected,"Pinned Gaussian pixels \(w)x\(h)")
    }
    var rng = SeededSampling()
    try check((0..<5).map { _ in rng.next64() } == [11749869230777074271,4976686463289251617,755828109848996024,304881062738325533,15002187965291974971],"PCG64 seed-zero raw vectors")
    let samplingVectors: [(Int,Int,String)] = [
        (20,5,"abc2cc65a368b64bee9bfbf72a7d9b665cae488748f7910e77e519b6e9ddb9a1"),
        (10001,3000,"bc124a0aeeeef959991d2e2747518592e50b83584629e54d69417761ef86b80d"),
        (149999,3000,"6fdca328b22e828d5f67b5835c4881d56fb2984f6ae968918f18ee285b197c45"),
        (150000,3000,"48bcf0273c0704e66c579b392a8900f358aa9d52de572e157aa20dc1e8c8e9d9"),
        (200001,3000,"4ec9a176d8000911c17d25867abbd1a66200123daf5a4e426d7b7ef6537fb652")]
    for (population,count,expected) in samplingVectors {
        var generator = SeededSampling(), data = Data()
        for var value in generator.choice(population:population,count:count).map({Int64($0).littleEndian}) { withUnsafeBytes(of:&value) { data.append(contentsOf:$0) } }
        let actual = SHA256.hash(data:data).map { String(format:"%02x",$0) }.joined()
        try check(actual == expected,"Pinned NumPy choice vector \(population)")
    }
    let flatEdges = Edges.extract([UInt8](repeating:128,count:6400),width:80,height:80)
    try check(flatEdges.width.isEmpty,"Flat image has no contrast edges")
    try check(!Edges.flags(Edges.summarize(flatEdges))["contrast_proxy"]!,"Missing edges cannot flag contrast")
    let root = FileManager.default.temporaryDirectory.appendingPathComponent("native-checks-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at:root,withIntermediateDirectories:false)
    defer { try? FileManager.default.removeItem(at:root) }
    let context = CGContext(data:nil,width:60,height:40,bitsPerComponent:8,bytesPerRow:240,
        space:CGColorSpace(name:CGColorSpace.sRGB)!,bitmapInfo:CGImageAlphaInfo.premultipliedLast.rawValue)!
    context.setFillColor(CGColor(red:1,green:0,blue:0,alpha:1)); context.fill(CGRect(x:0,y:0,width:30,height:40))
    context.setFillColor(CGColor(red:0,green:0,blue:1,alpha:1)); context.fill(CGRect(x:30,y:0,width:30,height:40))
    for type in [UTType.jpeg,UTType.heic,UTType.png,UTType.tiff] {
        let source = root.appendingPathComponent("original.\(type.preferredFilenameExtension!)")
        guard let writer = CGImageDestinationCreateWithURL(source as CFURL,type.identifier as CFString,1,nil) else { throw CocoaError(.fileWriteUnknown) }
        CGImageDestinationAddImage(writer,context.makeImage()!,[
            kCGImagePropertyOrientation:6,
            kCGImagePropertyExifDictionary:[kCGImagePropertyExifDateTimeOriginal:"2020:01:02 03:04:05",kCGImagePropertyExifColorSpace:65535],
            kCGImagePropertyIPTCDictionary:[kCGImagePropertyIPTCKeywords:["native-test"]]
        ] as CFDictionary)
        guard CGImageDestinationFinalize(writer) else { throw CocoaError(.fileWriteUnknown) }
        let before = try hash(source)
        for outputExtension in ["jpg","heic","png","tif"] {
            let dest = root.appendingPathComponent("export-\(type.preferredFilenameExtension!)-\(outputExtension).\(outputExtension)")
            try ImageHandling.derivative(source:source,destination:dest)
            let props = try ImageHandling.properties(dest)
            let exif = props[kCGImagePropertyExifDictionary as String] as? [String: Any]
            try check(exif?[kCGImagePropertyExifDateTimeOriginal as String] as? String == "2020:01:02 03:04:05","Capture date on derivative")
            try check((exif?[kCGImagePropertyExifColorSpace as String] as? NSNumber)?.intValue == 1,"Derivative EXIF sRGB tag")
            try check((props[kCGImagePropertyDepth as String] as? NSNumber)?.intValue == 8,"Explicit display derivative depth")
        }
        for angle in [0.0,90,180,270,3] {
            let dest = root.appendingPathComponent("\(type.preferredFilenameExtension!)-\(angle).png")
            try ImageHandling.derivative(source:source,destination:dest,clockwiseDegrees:angle)
            let properties = try ImageHandling.properties(dest)
            let width = (properties[kCGImagePropertyPixelWidth as String] as! NSNumber).intValue
            let height = (properties[kCGImagePropertyPixelHeight as String] as! NSNumber).intValue
            if angle == 0 || angle == 180 { try check(width == 40 && height == 60,"EXIF upright geometry") }
            if angle == 90 || angle == 270 { try check(width == 60 && height == 40,"Quarter-turn geometry") }
            try check((properties[kCGImagePropertyOrientation as String] as? NSNumber)?.intValue ?? 1 == 1,"Normalized orientation")
            let checksum = try hash(dest)
            try mustThrow { try ImageHandling.derivative(source:source,destination:dest) }
            try check(try hash(dest) == checksum,"Collision retains bytes")
            try check(try hash(source) == before,"Original unchanged")
        }
        let cropped = root.appendingPathComponent("crop-\(type.preferredFilenameExtension!).tif")
        try ImageHandling.derivative(source:source,destination:cropped,crop:CGRect(x:0,y:0,width:20,height:30),maximumDimension:15)
        let props = try ImageHandling.properties(cropped)
        try check((props[kCGImagePropertyPixelWidth as String] as? NSNumber)?.intValue == 10 && (props[kCGImagePropertyPixelHeight as String] as? NSNumber)?.intValue == 15,"Crop and resize")
        try mustThrow { try ImageHandling.derivative(source:source,destination:root.appendingPathComponent("bad.png"),crop:CGRect(x:-1,y:0,width:10,height:10)) }
        try mustThrow { try ImageHandling.derivative(source:source,destination:source) }
    }
    print("Passed \(checks) native checks")
} catch { FileHandle.standardError.write(Data("CHECK FAILED: \(error)\n".utf8)); exit(1) }
