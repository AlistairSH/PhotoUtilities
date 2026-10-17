import Foundation
import Vision
import CoreVideo
import ImageIO
import UniformTypeIdentifiers
@main struct Probe {
 static func main() async {
  do { try await run() } catch {
    let row=["status":"failed","error":String(describing:error)]
    if let data=try? JSONSerialization.data(withJSONObject:row,options:[.sortedKeys]) { FileHandle.standardOutput.write(data) }
    exit(1)
  }
 }
 static func run() async throws {
  let request = GenerateIterativeSegmentationRequest(seedPoint: NormalizedPoint(x: 0.5, y: 0.5))
  var row: [String: Any] = ["asset_status": String(describing: await request.assetStatus), "revision": String(describing: request.revision)]
  if CommandLine.arguments.contains("--download") {
    do { try await request.downloadAssets(); row["after_download"] = String(describing: await request.assetStatus) }
    catch { row["download_error"] = String(describing: error) }
  }
  if CommandLine.arguments.count == 5 {
    let args=CommandLine.arguments
    guard let x=Double(args[2]), let y=Double(args[3]), (0...1).contains(x), (0...1).contains(y),
      !FileManager.default.fileExists(atPath: args[4]) else { throw NSError(domain:"segmentation",code:1) }
    let seeded=GenerateIterativeSegmentationRequest(seedPoint: NormalizedPoint(x:x,y:y));seeded.qualityLevel = .balanced
    if await seeded.assetStatus != .ready { try await seeded.downloadAssets() }
    guard await seeded.assetStatus == .ready else { throw NSError(domain:"segmentation",code:2,userInfo:[NSLocalizedDescriptionKey:"Model assets not ready"]) }
    row["inference_asset_status"]="ready"
    let start=Date()
    if let mask=try await ImageRequestHandler(URL(fileURLWithPath:args[1])).perform(seeded) {
      let image=try mask.cgImage
      guard let destination=CGImageDestinationCreateWithURL(URL(fileURLWithPath:args[4]) as CFURL,UTType.png.identifier as CFString,1,nil) else { throw NSError(domain:"segmentation",code:3) }
      CGImageDestinationAddImage(destination,image,nil)
      guard CGImageDestinationFinalize(destination) else { throw NSError(domain:"segmentation",code:4) }
      row["mask_width"]=mask.size.width;row["mask_height"]=mask.size.height;row["pixel_format"]=mask.pixelFormat
      row["status"]="ok";row["seed"]=[x,y];row["quality"]="balanced";row["seconds"]=Date().timeIntervalSince(start)
    } else { row["status"]="no_mask" }
  }
  FileHandle.standardOutput.write(try JSONSerialization.data(withJSONObject: row, options: [.sortedKeys]))
 }
}
