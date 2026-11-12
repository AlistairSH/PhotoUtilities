import Foundation
import NativePhotoCore

do {
    let batch = try JSONDecoder().decode(ReviewBatch.self,from:FileHandle.standardInput.readDataToEndOfFile())
    let result = try ReviewPolicy.evaluate(batch)
    var bytes = try JSONSerialization.data(withJSONObject:result,options:[.sortedKeys])
    bytes.append(10); FileHandle.standardOutput.write(bytes)
} catch { FileHandle.standardError.write(Data("Policy evidence rejected: \(error)\n".utf8)); exit(1) }
