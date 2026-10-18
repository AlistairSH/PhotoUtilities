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
            kCGImagePropertyExifDictionary:[kCGImagePropertyExifDateTimeOriginal:"2020:01:02 03:04:05"],
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
