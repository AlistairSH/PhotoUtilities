import Foundation

public enum FocusPolicy {
    static let metrics = ["laplacian_variance","tenengrad"]
    static func overlap(_ a: [Double],_ b: [Double]) -> Double {
        let area = max(0,min(a[0]+a[2],b[0]+b[2])-max(a[0],b[0])) * max(0,min(a[1]+a[3],b[1]+b[3])-max(a[1],b[1]))
        let total = a[2]*a[3]+b[2]*b[3]-area
        return total > 0 ? area/total : 0
    }
    static func kind(_ id: String) -> String { String(id.split(separator:" ")[0]) }
    static func lowDetail(_ r: ReviewRegion) -> Bool {
        guard r.usable, let m = r.smoothed, m.outside != nil else { return false }
        return metrics.allSatisfy { key in guard let v = m.region_to_outside[key] ?? nil else { return false }; return v < 1 }
    }
    static func semantic(_ row: ReviewScale) -> [EdgeReviewRegion] {
        let faces = row.edge_regions.filter { $0.id.hasPrefix("faces") }
        var result = faces
        for r in row.edge_regions {
            if r.id.hasPrefix("animals") { result.append(r) }
            if r.id.hasPrefix("people") {
                let b = r.box
                if !faces.contains(where: { f in let cx = f.box[0]+f.box[2]/2, cy = f.box[1]+f.box[3]/2
                    return b[0] <= cx && cx <= b[0]+b[2] && b[1] <= cy && cy <= b[1]+b[3]
                }) { result.append(r) }
            }
        }
        return result
    }
    static func signals(_ rows: [ReviewScale]) -> [String: Double] {
        var values: [String: Double] = [:]
        for row in rows {
            let g = row.focus.global["smoothed"]!
            values["\(row.max_dimension)/laplacian_variance"] = g.laplacian_variance
            values["\(row.max_dimension)/tenengrad"] = g.tenengrad
            values["\(row.max_dimension)/peak_tile_tenengrad"] = row.focus.tile_tenengrad.max()!
        }
        return values
    }
    public static func decisions(_ batch: ReviewBatch) -> [[String: Any]] {
        let paired = batch.images.map { image in [1024,2048].map { scale in batch.focus_rows.first { $0.path == image.path && $0.max_dimension == scale }! } }
        let allSignals = paired.map(signals)
        return paired.enumerated().map { index,scales in
            let small = scales[0], large = scales[1]
            var cues: [[String: Any]] = []
            let attentionOnly = !small.focus.regions.contains { $0.usable && !$0.id.hasPrefix("attention") }
            for r in small.focus.regions {
                let k = kind(r.id)
                if (k == "attention" && !attentionOnly) || !lowDetail(r) { continue }
                let alternatives = large.focus.regions.filter { kind($0.id) == k }
                var match: ReviewRegion? = nil, best = -1.0
                for candidate in alternatives { let score = overlap(candidate.box,r.box); if score > best { best = score; match = candidate } }
                guard let match = match, best >= 0.5, lowDetail(match) else { continue }
                let reason = (k == "attention" ? "\(r.id) is an uncertain attention-only focus fallback; subject identity is unknown. " : "") + "\(r.id) has less measured detail than outside pixels in both metrics at both resolutions."
                cues.append(["region":r.id,"box":r.box,"matching_region_2048":match.id,
                             "ratios_1024":jsonObject(r.smoothed!.region_to_outside),"ratios_2048":jsonObject(match.smoothed!.region_to_outside),"reason":reason])
            }
            let priority = ["faces":0,"people":1,"animals":2,"objectness":3,"attention":4]
            cues = cues.enumerated().sorted { a,b in let ka = priority[kind(a.element["region"] as! String)]!, kb = priority[kind(b.element["region"] as! String)]!
                return ka == kb ? a.offset < b.offset : ka < kb }.map(\.element)
            let values = allSignals[index]
            var tail: [String: Double] = [:]
            for key in values.keys { tail[key] = Double(allSignals.filter { $0[key]! <= values[key]! }.count)/Double(paired.count) }
            let globalLow = paired.count >= 20 && tail.values.allSatisfy { $0 <= 0.1 }
            var reasons = cues.map { $0["reason"] as! String }
            if globalLow { reasons.append("Low global detail and low strongest-tile detail across both resolutions in this reference batch.") }
            let baseline = !cues.isEmpty || globalLow
            let contradictory = small.focus.regions.filter { r in
                guard ["faces","people","animals"].contains(kind(r.id)), let measured = r.smoothed else { return false }
                return metrics.allSatisfy { ((measured.region_to_outside[$0] ?? nil) ?? 0) >= 1 }
            }.map(\.id)
            let globalCount = scales.filter { $0.edge_flags["contrast_proxy"]! }.count
            let semanticExists = scales.contains { $0.edge_regions.contains { ["faces","people","animals"].contains(kind($0.id)) } }
            let fallback = !semanticExists && scales.contains { row in row.edge_regions.contains { $0.id.hasPrefix("objectness") && $0.metrics.sufficient && $0.metrics.contrast_soft_fraction! >= 0.6 } }
            let a = semantic(small), b = semantic(large)
            let stable = !a.isEmpty && !b.isEmpty && [a,b].allSatisfy { $0.allSatisfy { $0.metrics.sufficient && $0.metrics.contrast_soft_fraction! < 0.6 } } && a.count == b.count && a.allSatisfy { r in b.contains { kind(r.id) == kind($0.id) && overlap(r.box,$0.box) >= 0.5 } }
            let cleared = globalCount == 1 && stable
            if !baseline && globalCount > 0 && !cleared { reasons.append("Broad edge transitions suggest overall softness.") }
            if !baseline && fallback { reasons.append("Objectness region suggests softness; no semantic subject was detected.") }
            let final = baseline || fallback || (globalCount > 0 && !cleared)
            return ["path":small.path,"review_suggestion":final,"category":final ? "manual_review" : "unassessed",
                    "subject_cues":cues,"global_low_detail":globalLow,"contrary_regions":contradictory,"reason":reasons,
                    "global_measurements":values,"global_lower_tail_fractions":tail,"severe_blur_candidate":false,
                    "baseline_review":baseline,"global_contrast_review":globalCount > 0,"regional_fallback_review":fallback,"scale_confirmation_cleared":cleared]
        }
    }
    public static func relative(_ batch: ReviewBatch) -> [Int: [String: Any]] {
        func evidence(_ index: Int,_ scale: Int) -> (String,[ReviewRegion]) {
            let row = batch.focus_rows.first { $0.path == batch.images[index].path && $0.max_dimension == scale }!
            for kind in ["faces","people","animals","objectness","attention"] {
                let subjects = row.focus.regions.filter { $0.id.hasPrefix(kind) && $0.usable && $0.smoothed?.region != nil }
                if !subjects.isEmpty { return (kind,subjects) }
            }
            return ("global",[ReviewRegion(id:"global",box:[0,0,1,1],usable:true,smoothed:RegionMeasurement(region:row.focus.global["smoothed"]!,outside:nil,region_to_outside:[:]))])
        }
        var result: [Int: [String: Any]] = [:]
        for group in batch.groups {
            let members = Set(group.members)
            var wins = Dictionary(uniqueKeysWithValues:group.members.map { ($0,[Int]()) }), losses = wins
            for pair in batch.pairs where pair.level != "unmatched" && members.contains(pair.a) && members.contains(pair.b) {
                for (better,worse) in [(pair.a,pair.b),(pair.b,pair.a)] {
                    var convincing = true
                    for scale in [1024,2048] {
                        let (ka,ra) = evidence(better,scale), (kb,rb) = evidence(worse,scale)
                        if ka != kb || ra.count != rb.count { convincing = false; break }
                        let aa = ra.map { $0.box[2]*$0.box[3] }.sorted(), ab = rb.map { $0.box[2]*$0.box[3] }.sorted()
                        if zip(aa,ab).contains(where: { min($0.0,$0.1) <= 0 || max($0.0,$0.1) > 2*min($0.0,$0.1) }) { convincing = false; break }
                        for key in metrics {
                            let va = ra.map { key == "laplacian_variance" ? $0.smoothed!.region!.laplacian_variance : $0.smoothed!.region!.tenengrad }.min()!
                            let vb = rb.map { key == "laplacian_variance" ? $0.smoothed!.region!.laplacian_variance : $0.smoothed!.region!.tenengrad }.min()!
                            if vb <= 0 || va < 1.5*vb { convincing = false }
                        }
                    }
                    if convincing { wins[better]!.append(worse); losses[worse]!.append(better) }
                }
            }
            for i in group.members {
                let role: String? = !wins[i]!.isEmpty && losses[i]!.isEmpty ? "sharper" : !losses[i]!.isEmpty && wins[i]!.isEmpty ? "softer" : nil
                result[i] = ["role":present(role),"sharper_than":wins[i]!,"softer_than":losses[i]!,"note":"Relative focus candidate within directly matched photos; texture and framing may affect it."]
            }
        }
        return result
    }
}
