import Foundation

struct TierRow {
    var id: Int
    var utility: Bool
    var aesthetic: Double
    var face: Double?
    var kind: String
    var lap: Double
    var ten: Double
    var clipping: Double
    var layout: Double?
    var closed: Double?
    var open: Double?
    var smile: Double?
    var lapPct = 0.0, tenPct = 0.0, aestheticPct = 0.0
    var reasons: [String] = [], composition: [String] = [], top: [String] = []
    var possibleCull = false
    var tier = "Review"
    var fullRank: Int? = nil
    var detailPct: Double { max(lapPct,tenPct) }
    var dictionary: [String: Any] {
        var row: [String: Any] = ["id":id,"utility":utility,"aesthetic":aesthetic,"face_quality":present(face),
            "detail_kind":kind,"laplacian":lap,"tenengrad":ten,"clipping":clipping,"layout":present(layout),
            "closed_fraction":present(closed),"open_fraction":present(open),"smile_fraction":present(smile),
            "laplacian_percentile":lapPct,"tenengrad_percentile":tenPct,"aesthetic_percentile":aestheticPct,
            "detail_percentile":detailPct,"reasons":reasons,"composition_advisories":composition,
            "possible_cull":possibleCull,"top_pick_reasons":top,"tier":tier]
        if let rank = fullRank { row["full_sample_rank"] = rank }
        return row
    }
}
public enum TierPolicy {
    static let tierOrder = ["Top Pick":0,"Review":1,"Possible Cull":2]
    static func percentile(_ value: Double,_ values: [Double]) -> Double {
        100*(Double(values.filter { $0 < value }.count)+0.5*Double(values.filter { $0 == value }.count))/Double(values.count)
    }
    static func detail(_ focus: ReviewDetail) -> (String,ReviewMetric) {
        for kind in ["faces","people","animals","attention","objectness"] {
            let regions = focus.regions.filter { $0.id.hasPrefix(kind+" ") && $0.usable && $0.smoothed?.region != nil }
            if var best = regions.first {
                for r in regions.dropFirst() where r.smoothed!.region!.pixels! > best.smoothed!.region!.pixels! { best = r }
                return (kind,best.smoothed!.region!)
            }
        }
        return ("global",focus.global["smoothed"]!)
    }
    static func layout(_ row: ReviewScale) -> Double? {
        var distances: [Double] = []
        let width = Double(row.pixel_size[0]), height = Double(row.pixel_size[1])
        for kind in ["attention","objectness"] {
            let boxes = row.focus.regions.filter { $0.id.hasPrefix(kind+" ") }.map(\.box)
            guard var box = boxes.first else { continue }
            for b in boxes.dropFirst() where b[2]*b[3] > box[2]*box[3] { box = b }
            let left = max(0,box[0]), top = max(0,box[1]), right = min(1,box[0]+box[2]), bottom = min(1,box[1]+box[3])
            if right <= left || bottom <= top { continue }
            let cx = (left+right)/2, cy = (top+bottom)/2
            let third: Double = 1.0/3.0
            let anchors: [(Double,Double)] = [(0.5,0.5),(third,third),(third,2*third),(2*third,third),(2*third,2*third)]
            distances.append(anchors.map { hypot((cx-$0.0)*width,(cy-$0.1)*height)/hypot(width,height) }.min()!)
        }
        return distances.isEmpty ? nil : distances.reduce(0,+)/Double(distances.count)
    }
    static func scope(_ input: [TierRow],_ reference: [TierRow],solo: Bool = false) -> [TierRow] {
        var rows = input
        for i in rows.indices {
            let r = rows[i]
            var reasons: [String] = []
            if r.utility { reasons.append("Utility image") }
            let comparable = reference.filter { $0.kind == r.kind }
            let lowDetail = solo ? r.detailPct <= 10 : comparable.contains { $0.id != r.id && r.lap > 0 && r.ten > 0 && $0.lap >= 1.5*r.lap && $0.ten >= 1.5*r.ten }
            if lowDetail { reasons.append("Low subject detail" + (solo ? " — bottom 10% of full sample" : " — peer ≥1.5× on both detail metrics")) }
            if r.clipping >= 2 && r.clipping-reference.map(\.clipping).min()! >= 2 { reasons.append("More endpoint clipping — ≥2 percentage points above best reference") }
            if r.closed == 1 && reference.contains(where: { $0.open == 1 }) { reasons.append("Both eyes reported closed on every assessed face; open-eye alternative available") }
            if let value = r.layout, value-reference.compactMap(\.layout).min()! >= 0.10 { reasons.append("Farther from center/thirds anchors — provisional composition suggestion") }
            rows[i].reasons = reasons; rows[i].possibleCull = !reasons.isEmpty
        }
        // Preserve the accepted order of operations: composition contributes to
        // provisional sort/survivor count, then becomes advisory before tiers.
        let aesthetic = rows.filter { !$0.possibleCull }.count > rows.count/2
        func key(_ r: TierRow) -> [Double] {
            [r.possibleCull ? 1:0,Double(r.reasons.count),-(r.open ?? 0.5),-(r.smile ?? 0),-(r.face ?? -1),
             aesthetic ? -r.aesthetic : (r.layout ?? 1),aesthetic ? (r.layout ?? 1) : -r.aesthetic,Double(r.id)]
        }
        return rows.sorted { key($0).lexicographicallyPrecedes(key($1)) }
    }
    static func finalize(_ input: TierRow,_ reference: [TierRow],solo: Bool = false) -> TierRow {
        var r = input
        r.composition = r.reasons.filter { $0.hasPrefix("Farther from center/thirds anchors") }
        r.reasons = r.reasons.filter { !r.composition.contains($0) }; r.possibleCull = !r.reasons.isEmpty
        r.top = []
        if r.possibleCull { r.tier = "Possible Cull"; return r }
        let lapPct = solo ? percentile(r.lap,reference.map(\.lap)) : r.lapPct
        let tenPct = solo ? percentile(r.ten,reference.map(\.ten)) : r.tenPct
        if min(lapPct,tenPct) <= 10 { r.tier = "Review"; return r }
        if solo {
            if r.aestheticPct >= 90 { r.top.append("Top aesthetic decile across the entire sample, with no technical cull flags") }
        } else {
            let others = reference.filter { $0.id != r.id }, qualities = reference.filter { $0.id != r.id }.compactMap(\.face)
            if let face = r.face, let maximum = qualities.max(), face-maximum >= 0.10 { r.top.append("Highest face-capture score ≥0.10 above every other scored group member") }
            let comparable = others.filter { $0.kind == r.kind }
            if !comparable.isEmpty && comparable.allSatisfy({ $0.lap > 0 && $0.ten > 0 && r.lap >= 1.5*$0.lap && r.ten >= 1.5*$0.ten }) {
                r.top.append("Subject detail ≥1.5× every same-kind peer on both Laplacian and Tenengrad")
            }
        }
        r.tier = r.top.isEmpty ? "Review" : "Top Pick"
        return r
    }
    static func stableTierSort(_ rows: [TierRow]) -> [TierRow] {
        rows.enumerated().sorted { a,b in let ta = tierOrder[a.element.tier]!, tb = tierOrder[b.element.tier]!
            return ta == tb ? a.offset < b.offset : ta < tb }.map(\.element)
    }
    public static func rank(_ batch: ReviewBatch) -> (rows: [[String: Any]],groups: [[Int]],unmatched: [Int]) {
        var rows: [TierRow] = []
        for (index,image) in batch.images.enumerated() {
            let small = batch.focus_rows.first { $0.path == image.path && $0.max_dimension == 1024 }!, large = batch.focus_rows.first { $0.path == image.path && $0.max_dimension == 2048 }!
            let native = image.ranking_native, (kind,metric) = detail(small.focus)
            let faces = native.faces!, assessed = faces.filter { $0.hasLeftEyePosition && $0.hasRightEyePosition }
            let clip = small.exposure!.subjects[kind].flatMap { $0.isEmpty ? nil : $0 } ?? [small.exposure!.global]
            rows.append(TierRow(id:index,utility:native.isUtility!,aesthetic:native.overallScore!,face:large.ranking_native.face_qualities.max(),kind:kind,lap:metric.laplacian_variance,ten:metric.tenengrad,
                clipping:clip.max()!,layout:layout(large),closed:assessed.isEmpty ? nil : Double(assessed.filter { $0.leftEyeClosed && $0.rightEyeClosed }.count)/Double(assessed.count),
                open:assessed.isEmpty ? nil : Double(assessed.filter { !$0.leftEyeClosed && !$0.rightEyeClosed }.count)/Double(assessed.count),
                smile:faces.isEmpty ? nil : Double(faces.filter(\.hasSmile).count)/Double(faces.count)))
        }
        let reference = rows
        for i in rows.indices {
            rows[i].lapPct = percentile(rows[i].lap,reference.map(\.lap)); rows[i].tenPct = percentile(rows[i].ten,reference.map(\.ten)); rows[i].aestheticPct = percentile(rows[i].aesthetic,reference.map(\.aesthetic))
        }
        var groups: [[Int]] = []
        for group in batch.groups {
            let members = group.members.map { rows[$0] }
            let ordered = stableTierSort(scope(members,members).map { finalize($0,members) })
            for row in ordered { rows[row.id] = row }
            groups.append(ordered.map(\.id))
        }
        let allRows = rows
        let ordered = stableTierSort(scope(allRows,allRows,solo:true).map { finalize($0,allRows,solo:true) })
        let unmatched = Set(batch.unmatched)
        for (position,var row) in ordered.enumerated() where unmatched.contains(row.id) { row.fullRank = position+1; rows[row.id] = row }
        return (rows.map(\.dictionary),groups,ordered.filter { unmatched.contains($0.id) }.map(\.id))
    }
}
public enum ReviewPolicy {
    public static func evaluate(_ batch: ReviewBatch) throws -> [String: Any] {
        try batch.validate()
        let focus = FocusPolicy.decisions(batch), relative = FocusPolicy.relative(batch), tiers = TierPolicy.rank(batch)
        let images: [[String: Any]] = batch.images.enumerated().map { i,image in
            var value: [String: Any] = ["path":image.path,"focus_review":focus[i],"tier_review":tiers.rows[i]]
            if let comparison = relative[i] { value["focus_comparison"] = comparison }
            return value
        }
        return ["images":images,"groups":zip(batch.groups,tiers.groups).map { ["members":$0.1,"level":$0.0.level] as [String: Any] },"unmatched":tiers.unmatched]
    }
}
