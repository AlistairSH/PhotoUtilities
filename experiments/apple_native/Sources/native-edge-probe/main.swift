import Foundation
import CryptoKit
import NativePhotoCore

do {
    let args = Array(CommandLine.arguments.dropFirst())
    guard args.count == 4, let index = Int(args[1]),let scale = Int(args[2]) else { throw ReviewError.invalid("native-edge-probe FIXTURE INDEX SCALE NEW_OUTPUT_DIR") }
    let root = URL(fileURLWithPath:args[0]), output = URL(fileURLWithPath:args[3])
    let manifest = try JSONSerialization.jsonObject(with:Data(contentsOf:root.appendingPathComponent("complete.json"))) as! [String: Any]
    let viewsData = try Data(contentsOf:root.appendingPathComponent("views.json"))
    func sha(_ data: Data) -> String { SHA256.hash(data:data).map { String(format:"%02x",$0) }.joined() }
    guard sha(viewsData) == (manifest["files"] as! [String: String])["views.json"] else { throw ReviewError.invalid("Changed views") }
    let views = try JSONSerialization.jsonObject(with:viewsData) as! [[String: Any]]
    guard let view = views.first(where:{ ($0["index"] as! Int) == index && ($0["max_dimension"] as! Int) == scale }) else { throw ReviewError.invalid("Missing view") }
    let name = String(format:"%04d-%d.rgba",index,scale)
    let pixels = try Data(contentsOf:root.appendingPathComponent("pixels/"+name))
    guard sha(pixels) == (manifest["pixels_sha256"] as! [String: String])[name] else { throw ReviewError.invalid("Changed pixels") }
    // mkdir refuses existing directories, including occupied symlinks.
    guard mkdir(output.path,0o700) == 0 else { throw NSError(domain:NSPOSIXErrorDomain,code:Int(errno)) }
    let width = view["width"] as! Int,height = view["height"] as! Int
    var traceFailure: Error? = nil
    let edges = Edges.extract(Focus.gray([UInt8](pixels)),width:width,height:height) { name,values in
        if traceFailure == nil {
            do { try values.withUnsafeBytes { Data($0) }.write(to:output.appendingPathComponent(name+".f32"),options:.withoutOverwriting) }
            catch { traceFailure = error }
        }
    }
    if let error = traceFailure { throw error }
    try JSONEncoder().encode(edges).write(to:output.appendingPathComponent("profiles.json"),options:.withoutOverwriting)
    print("Edge trace complete: \(edges.width.count) profiles")
} catch { FileHandle.standardError.write(Data("\(error)\n".utf8)); exit(1) }
