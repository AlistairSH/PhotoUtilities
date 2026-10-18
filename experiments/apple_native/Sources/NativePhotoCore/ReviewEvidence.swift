import Foundation

public struct ReviewMetric: Codable {
    public var laplacian_variance: Double
    public var tenengrad: Double
    public var pixels: Double?
}
public struct RegionMeasurement: Codable {
    public var region: ReviewMetric?
    public var outside: ReviewMetric?
    public var region_to_outside: [String: Double?]
}
public struct ReviewRegion: Codable {
    public var id: String
    public var box: [Double]
    public var usable: Bool
    public var smoothed: RegionMeasurement?
}
public struct ReviewDetail: Codable {
    public var global: [String: ReviewMetric]
    public var tile_tenengrad: [Double]
    public var regions: [ReviewRegion]
}
public struct EdgeReviewSummary: Codable {
    public var sufficient: Bool
    public var contrast_soft_fraction: Double?
}
public struct EdgeReviewRegion: Codable {
    public var id: String
    public var box: [Double]
    public var metrics: EdgeReviewSummary
}
public struct ExposureEvidence: Codable {
    public var global: Double
    public var subjects: [String: [Double]]
}
public struct FaceExpression: Codable {
    public var hasSmile: Bool
    public var leftEyeClosed: Bool
    public var rightEyeClosed: Bool
    public var hasLeftEyePosition: Bool
    public var hasRightEyePosition: Bool
}
public struct RankingEvidence: Codable {
    public var status: String
    public var face_qualities: [Double]
    public var overallScore: Double?
    public var isUtility: Bool?
    public var faces: [FaceExpression]?
}
public struct ReviewScale: Codable {
    public var path: String
    public var max_dimension: Int
    public var focus: ReviewDetail
    public var edge_flags: [String: Bool]
    public var edge_regions: [EdgeReviewRegion]
    public var exposure: ExposureEvidence?
    public var ranking_native: RankingEvidence
    public var pixel_size: [Int]
}
public struct ReviewImage: Codable {
    public var path: String
    public var ranking_native: RankingEvidence
}
public struct ReviewGroup: Codable {
    public var members: [Int]
    public var level: String
}
public struct ReviewPair: Codable {
    public var a: Int
    public var b: Int
    public var level: String
}
public struct ReviewBatch: Codable {
    public var images: [ReviewImage]
    public var pairs: [ReviewPair]
    public var groups: [ReviewGroup]
    public var unmatched: [Int]
    public var focus_rows: [ReviewScale]
    public func validate() throws {
        guard !images.isEmpty, images.count <= 500, Set(images.map(\.path)).count == images.count,
              focus_rows.count == 2*images.count else { throw ReviewError.invalid("Image identities or scale count") }
        for image in images {
            let n = image.ranking_native
            guard n.status == "ok", n.overallScore != nil, n.isUtility != nil, n.faces != nil else { throw ReviewError.invalid("Incomplete image ranking evidence") }
        }
        let names = Set(images.map(\.path))
        var keys = Set<String>()
        for row in focus_rows {
            guard names.contains(row.path), [1024,2048].contains(row.max_dimension),
                  keys.insert("\(row.path)\u{0}\(row.max_dimension)").inserted,
                  row.pixel_size.count == 2, row.pixel_size.allSatisfy({$0 > 0}),
                  row.focus.global["smoothed"] != nil, !row.focus.tile_tenengrad.isEmpty,
                  row.edge_flags["contrast_proxy"] != nil, row.ranking_native.status == "ok",
                  row.max_dimension != 1024 || (row.exposure != nil && row.ranking_native.overallScore != nil && row.ranking_native.isUtility != nil && row.ranking_native.faces != nil)
            else { throw ReviewError.invalid("Incomplete evidence: \(row.path) / \(row.max_dimension)") }
            for region in row.focus.regions {
                guard ["faces","people","animals","objectness","attention"].contains(String(region.id.split(separator:" ").first ?? "")), region.box.count == 4, region.box[2] > 0, region.box[3] > 0, region.smoothed?.region == nil || region.smoothed!.region!.pixels != nil else { throw ReviewError.invalid("Invalid subject box") }
            }
            for region in row.edge_regions {
                guard region.box.count == 4, !region.metrics.sufficient || region.metrics.contrast_soft_fraction != nil else { throw ReviewError.invalid("Incomplete edge region") }
            }
        }
        let partition = groups.flatMap(\.members)+unmatched
        guard partition.count == images.count, Set(partition) == Set(images.indices), groups.allSatisfy({$0.members.count > 1}) else { throw ReviewError.invalid("Invalid group partition") }
        var pairKeys = Set<String>()
        for p in pairs {
            guard p.a >= 0, p.a < p.b, p.b < images.count, ["likely","potential","unmatched"].contains(p.level),
                  pairKeys.insert("\(p.a)/\(p.b)").inserted else { throw ReviewError.invalid("Invalid direct pair") }
        }
        guard pairs.count == images.count*(images.count-1)/2 else { throw ReviewError.invalid("Incomplete pair evidence") }
    }
}
public enum ReviewError: Error { case invalid(String) }

func jsonObject<T: Encodable>(_ value: T) -> Any { try! JSONSerialization.jsonObject(with:JSONEncoder().encode(value)) }
func present(_ value: Any?) -> Any { value ?? NSNull() }
