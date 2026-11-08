import Foundation
import CryptoKit
import Vision
import NativePhotoCore
import NativeSIFT

public struct AnalysisInput: Sendable, Codable {
    /// Source identity is independent of its location; a future Photos adapter can supply an asset ID.
    public let id: String
    public let url: URL
    public init(id: String, url: URL) { self.id = id; self.url = url }
}
public struct AnalysisProgress: Sendable {
    public enum Stage: String, Sendable { case validating, analyzing, matching, ranking, verifying, complete }
    public let stage: Stage
    public let completed: Int
    public let total: Int
    public let sourceID: String?
}
public struct AnalyzedSource: Sendable, Codable {
    public let input: AnalysisInput
    public let sha256: String
    public let rotation: RotationEvidence
    public let siftKeypoints: Int

    public func matchesFile() throws -> Bool {
        try AnalysisCoordinator.digest(input.url, checkpoint: { try Task.checkCancellation() }) == sha256
    }
}
public struct PhotoReview: Sendable, Codable {
    public let sourceID: String
    public let tier: String
    public let reasons: [String]
    public let compositionAdvisories: [String]
    public let topPickReasons: [String]
    public let possibleMissedFocus: Bool
    public let focusReasons: [String]
    public let relativeFocus: String?
    public let rankWithinSet: Int
    public let setSize: Int
    public var tierLabel: String { tier == "Review" ? "Keep & Review" : tier }
}
public struct AnalysisConfiguration: Sendable, Codable {
    public let autoRotate: Bool
    public let visionFeaturePrintRevision: Int
    public let visionThreshold: Double
    public let likelyThreshold: Double
    public let openCVVersion: String
    public let numericalBackend: String
    public let operatingSystem: String
}
public struct AnalysisPairEvidence: Sendable, Codable {
    public let a: Int
    public let b: Int
    public let visionDistance: Double
    public let sift: SIFTMatch
}
public struct AnalysisResult: Sendable, Codable {
    public let configuration: AnalysisConfiguration
    /// Monotonic wall-clock seconds by phase, plus total; optional for older saved results.
    public let timings: [String: Double]?
    public let sources: [AnalyzedSource]
    public let batch: ReviewBatch
    public let pairEvidence: [AnalysisPairEvidence]
    public let photos: [PhotoReview]
    public let orderedGroups: [[Int]]
    public let orderedUngrouped: [Int]
    /// Complete policy evidence, reasons and measurements, in the existing review JSON format.
    public let policyJSON: Data
}

/// Serial actor keeps Vision/SIFT handles confined and CPU work away from MainActor.
/// At most one display scale is decoded at a time. Only compact feature handles,
/// measurements and pair records survive between images. Calls on this actor queue.
public actor AnalysisCoordinator {
    public init() {}

    /// Read-only file analysis. The caller retains sandbox/security-scoped access
    /// for the duration. Failure/cancellation throws; no partial result is published.
    /// Progress executes on this actor; hop to MainActor before updating UI state.
    /// Cancellation is cooperative between synchronous Vision/measurement/SIFT operations.
    public func analyze(_ inputs: [AnalysisInput], autoRotate: Bool = true,
                        progress: @Sendable (AnalysisProgress) -> Void = { _ in }) async throws -> AnalysisResult {
        let started = ProcessInfo.processInfo.systemUptime
        var previousStage: AnalysisProgress.Stage?
        var phaseStarted = started
        var timings: [String: Double] = [:]
        func check() throws { try Task.checkCancellation() }
        func report(_ stage: AnalysisProgress.Stage, _ done: Int, _ total: Int, _ id: String? = nil) {
            if previousStage != stage {
                let now = ProcessInfo.processInfo.systemUptime
                if let previousStage { timings[previousStage.rawValue] = now-phaseStarted }
                previousStage = stage; phaseStarted = now
            }
            progress(AnalysisProgress(stage:stage,completed:done,total:total,sourceID:id))
        }
        try check()
        guard !inputs.isEmpty, inputs.count <= 500,
              inputs.allSatisfy({ !$0.id.isEmpty && $0.url.isFileURL }),
              Set(inputs.map(\.id)).count == inputs.count,
              Set(inputs.map { $0.url.standardizedFileURL.resolvingSymlinksInPath() }).count == inputs.count else {
            throw ReviewError.invalid("Expected 1...500 distinct local files with unique source IDs")
        }
        guard SIFTFeatures.openCVVersion == "4.11.0" else { throw ReviewError.invalid("Expected pinned OpenCV 4.11.0") }
        var hashes: [String] = []
        report(.validating,0,inputs.count)
        for input in inputs {
            try check()
            guard ["jpg","jpeg","heic","heif","png","tif","tiff"].contains(input.url.pathExtension.lowercased()),
                  try input.url.resourceValues(forKeys:[.isRegularFileKey]).isRegularFile == true else {
                throw ReviewError.invalid("Unsupported image file: \(input.url.path)")
            }
            hashes.append(try Self.digest(input.url,checkpoint:check))
            report(.validating,hashes.count,inputs.count,input.id)
        }
        var sources: [AnalyzedSource] = [], images: [ReviewImage] = [], scales: [ReviewScale] = []
        var prints: [VNFeaturePrintObservation] = [], features: [SIFTFeatures] = []
        report(.analyzing,0,inputs.count)
        for (i,input) in inputs.enumerated() {
            try check()
            try autoreleasepool {
                let evidence = try LivePhotoAnalysis.analyze(url:input.url,autoRotate:autoRotate,checkpoint:check) { rgba,w,h in
                    features.append(try SIFTFeatures(rgba:rgba,width:w,height:h))
                }
                sources.append(AnalyzedSource(input:input,sha256:hashes[i],rotation:evidence.rotation,siftKeypoints:features.last!.keypointCount))
                images.append(ReviewImage(path:input.url.path,ranking:evidence.scales[0].ranking_native))
                scales += evidence.scales
                prints.append(evidence.featurePrint)
            }
            report(.analyzing,i+1,inputs.count,input.id)
        }
        let total = inputs.count*(inputs.count-1)/2
        var pairs: [ReviewPair] = []
        var pairEvidence: [AnalysisPairEvidence] = []
        pairs.reserveCapacity(total)
        pairEvidence.reserveCapacity(total)
        report(.matching,0,total)
        for a in inputs.indices {
            for b in inputs.indices where b > a {
                try check()
                let compared: (ReviewPair, AnalysisPairEvidence) = try autoreleasepool {
                    var distance: Float = 0
                    try prints[a].computeDistance(&distance,to:prints[b])
                    let match = try features[a].compare(to:features[b])
                    return (ReviewPair(a:a,b:b,level:try Grouping.level(distance:Double(distance),sift:match.candidate)),
                            AnalysisPairEvidence(a:a,b:b,visionDistance:Double(distance),sift:match))
                }
                pairs.append(compared.0)
                pairEvidence.append(compared.1)
                // Bound UI traffic while preserving cancellation at every pair.
                if pairs.count % 32 == 0 || pairs.count == total { report(.matching,pairs.count,total) }
            }
        }
        // Release per-image native descriptors before full-batch policy evaluation.
        features.removeAll(); prints.removeAll()
        try check()
        report(.ranking,0,1)
        try check()
        let batch = try ReviewBatch(images:images,pairs:pairs,scales:scales)
        let policy = try ReviewPolicy.evaluate(batch)
        let policyJSON = try JSONSerialization.data(withJSONObject:policy,options:[.sortedKeys])
        let groups = (policy["groups"] as! [[String:Any]]).map { $0["members"] as! [Int] }
        let ungrouped = policy["unmatched"] as! [Int]
        let sets = groups + (ungrouped.isEmpty ? [] : [ungrouped])
        let rows = policy["images"] as! [[String:Any]]
        var photos: [PhotoReview] = []
        for (i,row) in rows.enumerated() {
            let tier = row["tier_review"] as! [String:Any], focus = row["focus_review"] as! [String:Any]
            let set = sets.first { $0.contains(i) }!
            photos.append(PhotoReview(sourceID:inputs[i].id,tier:tier["tier"] as! String,
                reasons:tier["reasons"] as! [String],compositionAdvisories:tier["composition_advisories"] as! [String],
                topPickReasons:tier["top_pick_reasons"] as! [String],possibleMissedFocus:focus["review_suggestion"] as! Bool,
                focusReasons:focus["reason"] as! [String],relativeFocus:(row["focus_comparison"] as? [String:Any])?["role"] as? String,
                rankWithinSet:set.firstIndex(of:i)!+1,setSize:set.count))
        }
        report(.ranking,1,1)
        report(.verifying,0,inputs.count)
        for (i,input) in inputs.enumerated() {
            try check()
            guard try Self.digest(input.url,checkpoint:check) == hashes[i] else {
                throw ReviewError.invalid("Source changed during analysis: \(input.id)")
            }
            report(.verifying,i+1,inputs.count,input.id)
        }
        try check()
        let configuration = AnalysisConfiguration(autoRotate:autoRotate,visionFeaturePrintRevision:2,
            visionThreshold:0.45,likelyThreshold:0.40,openCVVersion:SIFTFeatures.openCVVersion,
            numericalBackend:"accelerate",operatingSystem:ProcessInfo.processInfo.operatingSystemVersionString)
        report(.complete,inputs.count,inputs.count)
        timings["total"] = ProcessInfo.processInfo.systemUptime-started
        let result = AnalysisResult(configuration:configuration,timings:timings,sources:sources,batch:batch,pairEvidence:pairEvidence,photos:photos,orderedGroups:groups,
            orderedUngrouped:ungrouped,policyJSON:policyJSON)
        return result
    }

    fileprivate static func digest(_ url: URL, checkpoint: () throws -> Void) throws -> String {
        let file = try FileHandle(forReadingFrom:url)
        defer { try? file.close() }
        var hash = SHA256()
        while true {
            try checkpoint()
            let data = try file.read(upToCount:1024*1024) ?? Data()
            if data.isEmpty { break }
            hash.update(data:data)
        }
        return hash.finalize().map { String(format:"%02x",$0) }.joined()
    }
}
