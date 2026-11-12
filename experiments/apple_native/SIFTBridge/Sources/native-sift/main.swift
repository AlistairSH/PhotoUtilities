import Foundation
import CryptoKit
import NativeSIFT
import NativePhotoCore

struct ImageInput: Decodable {
    let index: Int
    let width: Int
    let height: Int
    let pixels: String
    let sha256: String
}
struct PairInput: Decodable { let a: Int; let b: Int; let vision_distance: Double }
struct Input: Decodable { let images: [ImageInput]; let pairs: [PairInput] }
func emit(_ row: [String:Any]) throws {
    let data = try JSONSerialization.data(withJSONObject:row,options:[.sortedKeys])
    FileHandle.standardOutput.write(data); FileHandle.standardOutput.write(Data([10]))
}
func fail(_ text: String) -> SIFTError { SIFTError(description:text) }

do {
    guard CommandLine.arguments.count == 2 else { throw fail("Usage: native-sift INPUT.json (frozen RGBA8 preview manifest)") }
    guard SIFTFeatures.openCVVersion == "4.11.0" else { throw fail("Expected pinned OpenCV 4.11.0") }
    let input = try JSONDecoder().decode(Input.self,from:Data(contentsOf:URL(fileURLWithPath:CommandLine.arguments[1])))
    guard !input.images.isEmpty, input.images.count <= 500,
          input.pairs.count <= input.images.count*(input.images.count-1)/2 else { throw fail("Invalid batch size") }
    var identities = Set<String>()
    for pair in input.pairs {
        guard pair.a >= 0, pair.a < pair.b, pair.b < input.images.count,
              pair.vision_distance.isFinite, pair.vision_distance >= 0,
              identities.insert("\(pair.a):\(pair.b)").inserted else { throw fail("Invalid/duplicate pair or Vision distance") }
    }
    let start = ProcessInfo.processInfo.systemUptime
    var features: [SIFTFeatures] = []
    for (index,image) in input.images.enumerated() {
        guard image.index == index else { throw fail("Nonsequential image identity") }
        let feature: SIFTFeatures = try autoreleasepool {
            let data = try Data(contentsOf:URL(fileURLWithPath:image.pixels))
            guard SHA256.hash(data:data).map({String(format:"%02x",$0)}).joined() == image.sha256 else { throw fail("Pixel checksum mismatch") }
            let feature = try SIFTFeatures(rgba:data,width:image.width,height:image.height)
            try emit(["type":"image","index":index,"keypoints":feature.keypointCount])
            return feature
        }
        features.append(feature)
    }
    for pair in input.pairs {
        try autoreleasepool {
            let match = try features[pair.a].compare(to:features[pair.b])
            let level = try Grouping.level(distance:pair.vision_distance,sift:match.candidate)
            try emit(["type":"pair","a":pair.a,"b":pair.b,"mutual_matches":match.mutualMatches,
                      "inliers":match.inliers,"inlier_fraction":match.inlierFraction,
                      "coverage_a":match.coverageA,"coverage_b":match.coverageB,
                      "sift_candidate":match.candidate,"level":level])
        }
    }
    try emit(["type":"complete","images":features.count,"pairs":input.pairs.count,
              "opencv_version":SIFTFeatures.openCVVersion,"seconds":ProcessInfo.processInfo.systemUptime-start])
} catch {
    FileHandle.standardError.write(Data("\(error)\n".utf8)); exit(1)
}
