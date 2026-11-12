import Foundation
import CryptoKit
import NativePhotoCore

// Replay already-oriented sRGB RGBA8 display views. No Vision inference, source
// photograph writing or production state is involved in this host adapter.
do {
    let args = Array(CommandLine.arguments.dropFirst())
    guard args.count == 2 || (args.count == 4 && args[2] == "--backend" && NumericalBackend(rawValue:args[3]) != nil) else { throw ReviewError.invalid("native-measure FIXTURE_DIRECTORY OUTPUT_JSONL [--backend scalar|accelerate]") }
    let backend = args.count == 4 ? NumericalBackend(rawValue:args[3])! : .accelerate
    let root = URL(fileURLWithPath:args[0]), output = URL(fileURLWithPath:args[1])
    guard !FileManager.default.fileExists(atPath:output.path) else { throw CocoaError(.fileWriteFileExists) }
    let manifest = try JSONSerialization.jsonObject(with:Data(contentsOf:root.appendingPathComponent("complete.json"))) as! [String: Any]
    let pixelHashes = manifest["pixels_sha256"] as! [String: String]
    let viewData = try Data(contentsOf:root.appendingPathComponent("views.json"))
    let viewHash = SHA256.hash(data:viewData).map { String(format:"%02x",$0) }.joined()
    guard viewHash == (manifest["files"] as! [String: String])["views.json"] else { throw ReviewError.invalid("Changed frozen views") }
    let views = try JSONSerialization.jsonObject(with:viewData) as! [[String: Any]]
    // O_EXCL prevents replacing a raced-in file or occupied symlink.
    let fd = open(output.path,O_WRONLY|O_CREAT|O_EXCL,0o600)
    guard fd >= 0 else { throw NSError(domain:NSPOSIXErrorDomain,code:Int(errno)) }
    let handle = FileHandle(fileDescriptor:fd,closeOnDealloc:true)
    defer { try? handle.close() }
    for view in views {
        try autoreleasepool {
            let index = view["index"] as! Int, scale = view["max_dimension"] as! Int
            let identity = String(format:"%04d-%d.rgba",index,scale)
            let pixelData = try Data(contentsOf:root.appendingPathComponent("pixels/"+identity))
            let sha = SHA256.hash(data:pixelData).map { String(format:"%02x",$0) }.joined()
            guard sha == pixelHashes[identity] else { throw ReviewError.invalid("Changed frozen pixels") }
            let pixels = [UInt8](pixelData)
            let w = view["width"] as! Int, h = view["height"] as! Int
            guard w > 0, h > 0, max(w,h) <= 2048, pixels.count == w*h*4 else { throw ReviewError.invalid("Invalid decoded pixels") }
            let detectors = view["detectors"] as! [String: Any]
            let started = ProcessInfo.processInfo.systemUptime
            let focusStarted = ProcessInfo.processInfo.systemUptime
            let focus = Focus.regions(pixels,width:w,height:h,detectors:detectors,backend:backend)
            let focusSeconds = ProcessInfo.processInfo.systemUptime-focusStarted
            let edgeStarted = ProcessInfo.processInfo.systemUptime
            let edges = Edges.extract(Focus.gray(pixels),width:w,height:h)
            let edgeSeconds = ProcessInfo.processInfo.systemUptime-edgeStarted
            let global = Edges.summarize(edges)
            var regions: [[String: Any]] = []
            for kind in ["faces","people","animals","objectness","attention"] {
                let detection = detectors[kind] as! [String: Any]
                for (i,region) in (detection["regions"] as! [[String: Any]]).enumerated() {
                    let box = (region["box"] as! [NSNumber]).map(\.doubleValue)
                    let x = max(0,box[0]), y = max(0,box[1]), right = min(1,box[0]+box[2]), bottom = min(1,box[1]+box[3])
                    regions.append(["id":"\(kind) \(i+1)","box":box,"metrics":Edges.summarize(edges,box:[x,y,max(0,right-x),max(0,bottom-y)],width:w,height:h)])
                }
            }
            let row: [String: Any] = ["path":view["path"]!,"max_dimension":scale,"index":index,
                "exposure":Exposure.measure(pixels,width:w,height:h,detectors:detectors),"focus":focus,"edge_global":global,"edge_flags":Edges.flags(global),"edge_regions":regions,
                "backend":backend.rawValue,"focus_seconds":focusSeconds,"edge_seconds":edgeSeconds,"measurement_seconds":ProcessInfo.processInfo.systemUptime-started]
            var bytes = try JSONSerialization.data(withJSONObject:row,options:[.sortedKeys]); bytes.append(10)
            try handle.write(contentsOf:bytes)
            FileHandle.standardError.write(Data("Measured \(index+1) / \(scale)\n".utf8))
        }
    }
    try handle.write(contentsOf:Data("{\"type\":\"complete\",\"scale_rows\":\(views.count)}\n".utf8))
} catch { FileHandle.standardError.write(Data("Native measurement failed: \(error)\n".utf8)); exit(1) }
