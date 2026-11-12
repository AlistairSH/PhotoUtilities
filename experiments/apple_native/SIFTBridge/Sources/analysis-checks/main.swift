import Foundation
import CoreGraphics
import ImageIO
import NativePhotoAnalysis
import NativePhotoCore

func expectRejection(_ body: () async throws -> AnalysisResult) async throws {
    do { _ = try await body(); throw ReviewError.invalid("CHECK FAILED: unexpectedly succeeded") }
    catch ReviewError.invalid(let text) where text.hasPrefix("CHECK FAILED") { fatalError(text) }
    catch {}
}
func writeImage(_ url: URL) throws {
    let width = 96, height = 96
    var pixels = [UInt8](repeating:255,count:width*height*4)
    for i in 0..<width*height {
        pixels[4*i] = UInt8((i*37+i/width*13)%256)
        pixels[4*i+1] = UInt8((i*17+i/width*7)%256)
        pixels[4*i+2] = UInt8((i*29)%256)
    }
    let data = Data(pixels)
    let provider = CGDataProvider(data:data as CFData)!
    let image = CGImage(width:width,height:height,bitsPerComponent:8,bitsPerPixel:32,bytesPerRow:width*4,
        space:CGColorSpace(name:CGColorSpace.sRGB)!,bitmapInfo:CGBitmapInfo(rawValue:CGImageAlphaInfo.premultipliedLast.rawValue),
        provider:provider,decode:nil,shouldInterpolate:false,intent:.defaultIntent)!
    let destination = CGImageDestinationCreateWithURL(url as CFURL,"public.png" as CFString,1,nil)!
    CGImageDestinationAddImage(destination,image,nil)
    guard CGImageDestinationFinalize(destination) else { throw ReviewError.invalid("Synthetic image export") }
}

@main struct AnalysisChecks {
    static func main() async throws {
        let coordinator = AnalysisCoordinator()
        let missing = AnalysisInput(id:"one",url:URL(fileURLWithPath:"/does-not-exist.jpg"))
        try await expectRejection { try await coordinator.analyze([]) }
        try await expectRejection { try await coordinator.analyze([missing,missing]) }
        try await expectRejection { try await coordinator.analyze([AnalysisInput(id:"remote",url:URL(string:"https://example.com/photo.jpg")!)]) }
        let task = Task { try await coordinator.analyze([missing]) }
        task.cancel()
        do { _ = try await task.value; fatalError("Ignored cancellation") }
        catch is CancellationError {} catch { fatalError("Cancellation did not precede file access: \(error)") }
        print("Input rejection and cancellation-before-I/O checks passed")
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("analysis-checks-"+UUID().uuidString)
        try FileManager.default.createDirectory(at:root,withIntermediateDirectories:false)
        defer { try? FileManager.default.removeItem(at:root) }
        let first = root.appendingPathComponent("one.png"), second = root.appendingPathComponent("two.png")
        try writeImage(first); try FileManager.default.copyItem(at:first,to:second)
        let original = try Data(contentsOf:first)
        let inputs = [AnalysisInput(id:"one",url:first),AnalysisInput(id:"two",url:second)]
        let result = try await coordinator.analyze(inputs,autoRotate:false)
        precondition(result.photos.count == 2 && result.batch.pairs.count == 1)
        precondition(result.batch.pairs[0].level == "likely" && result.orderedGroups.count == 1)
        precondition(Set(result.photos.map(\.rankWithinSet)) == Set([1,2]))
        precondition(result.photos.allSatisfy { $0.setSize == 2 })
        do {
            _ = try ReviewBatch(images:result.batch.images,pairs:[ReviewPair(a:0,b:99,level:"likely")],scales:result.batch.focus_rows)
            fatalError("Accepted out-of-bounds pair")
        } catch {}
        let after = try Data(contentsOf:first)
        precondition(after == original)
        for stage in [AnalysisProgress.Stage.analyzing,.matching,.ranking,.verifying] {
            let cancelled = Task {
                try await coordinator.analyze(inputs,autoRotate:false) { value in
                    if value.stage == stage { withUnsafeCurrentTask { $0?.cancel() } }
                }
            }
            do { _ = try await cancelled.value; fatalError("Ignored cancellation at \(stage)") }
            catch is CancellationError {}
        }
        // Mutate only a disposable synthetic source after analysis, before final verification.
        try await expectRejection {
            try await coordinator.analyze(inputs,autoRotate:false) { value in
                if value.stage == .verifying && value.completed == 0 {
                    try! Data("changed disposable source".utf8).write(to:second)
                }
            }
        }
        // A failed/cancelled run must not leave the actor unusable.
        try original.write(to:second)
        let recovered = try await coordinator.analyze([inputs[0]],autoRotate:false)
        precondition(recovered.orderedGroups.isEmpty && recovered.orderedUngrouped == [0])
        precondition(recovered.photos[0].rankWithinSet == 1 && recovered.photos[0].setSize == 1)
        print("Live result, group ordering and source preservation checks passed")
    }
}
