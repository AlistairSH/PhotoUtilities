import Foundation

public extension Focus {
    /// Compute derivatives once before regional selection. Rectangular guards
    /// implement the accepted binary-mask erosion/dilation without rescanning
    /// derivatives for each tile and region.
    static func regions(_ rgba: [UInt8], width w: Int, height h: Int, detectors: [String: Any]) -> [String: Any] {
        let pixels = smooth(gray(rgba),width:w,height:h)
        var lap = [Double](repeating:0,count:w*h), energy = lap
        if w >= 3 && h >= 3 {
            for y in 1..<h-1 { for x in 1..<w-1 {
                let i = y*w+x
                lap[i] = pixels[i-1]+pixels[i+1]+pixels[i-w]+pixels[i+w]-4*pixels[i]
                let dx = pixels[i-w+1]+2*pixels[i+1]+pixels[i+w+1]-pixels[i-w-1]-2*pixels[i-1]-pixels[i+w-1]
                let dy = pixels[i+w-1]+2*pixels[i+w]+pixels[i+w+1]-pixels[i-w-1]-2*pixels[i-w]-pixels[i-w+1]
                energy[i] = dx*dx+dy*dy
            }}
        }
        typealias Bounds = (l: Int,t: Int,r: Int,b: Int)
        func boxes(_ kind: String) -> [[String: Any]] { (detectors[kind] as? [String: Any])?["regions"] as? [[String: Any]] ?? [] }
        func coordinates(_ region: [String: Any]) -> [Double] {
            if let box = region["box"] as? [Double] { return box }
            if let box = region["box"] as? [CGFloat] { return box.map { Double($0) } }
            return (region["box"] as! [NSNumber]).map(\.doubleValue)
        }
        func bounds(_ b: [Double]) -> Bounds {
            let x = max(0,b[0]), y = max(0,b[1]), r = min(1,b[0]+b[2]), bottom = min(1,b[1]+b[3])
            return (Int(x*Double(w)),Int(y*Double(h)),Int((r*Double(w)).rounded(.toNearestOrEven)),Int((bottom*Double(h)).rounded(.toNearestOrEven)))
        }
        func stats(_ b: Bounds,accept: ((Int,Int) -> Bool)? = nil) -> [String: Double]? {
            let left = max(1,b.l), top = max(1,b.t), right = min(w-1,b.r), bottom = min(h-1,b.b)
            guard right > left && bottom > top else { return nil }
            var laps: [Double] = [], energies: [Double] = [], luminance: [Double] = []
            for y in top..<bottom { for x in left..<right {
                if let accept = accept, !accept(x,y) { continue }
                let i = y*w+x; laps.append(lap[i]); energies.append(energy[i]); luminance.append(pixels[i])
            }}
            guard laps.count >= 100 else { return nil }
            func mean(_ a: [Double]) -> Double { a.reduce(0,+)/Double(a.count) }
            func variance(_ a: [Double]) -> Double { let m = mean(a); return mean(a.map { ($0-m)*($0-m) }) }
            energies.sort()
            let q = Double(energies.count-1)*0.9, lo = Int(q)
            return ["pixels":Double(laps.count),"laplacian_variance":variance(laps),"tenengrad":mean(energies),
                "gradient_energy_p90":energies[lo]+(energies[min(lo+1,energies.count-1)]-energies[lo])*(q-Double(lo)),
                "luminance_mean":mean(luminance),"luminance_std":sqrt(variance(luminance))]
        }
        // An outside mask dilated by 3 then eroded by 1 excludes each source
        // rectangle expanded by 4. Empty rectangles contribute no excluded pixels.
        let semantic = ["faces","people","animals"].flatMap { kind in boxes(kind).map { bounds(coordinates($0)) } }.filter { $0.r > $0.l && $0.b > $0.t }
        var excluded = [Bool](repeating:false,count:w*h)
        for b in semantic {
            for y in max(0,b.t-4)..<min(h,b.b+4) { for x in max(0,b.l-4)..<min(w,b.r+4) { excluded[y*w+x] = true } }
        }
        let all: Bounds = (1,1,w-1,h-1)
        let semanticOutside = stats(all) { x,y in !excluded[y*w+x] }
        var output: [[String: Any]] = []
        for kind in ["faces","people","animals","objectness","attention"] {
            for (index,region) in boxes(kind).enumerated() {
                let box = coordinates(region), b = bounds(box), usable = min(b.r-b.l,b.b-b.t) >= 24
                var item: [String: Any] = ["id":"\(kind) \(index+1)","box":box,"pixels":[b.r-b.l,b.b-b.t],"usable":usable,"raw":NSNull(),"smoothed":NSNull()]
                if usable {
                    let inside = stats((b.l+1,b.t+1,b.r-1,b.b-1))
                    let background: [String: Double]?
                    if ["faces","people","animals"].contains(kind) { background = semanticOutside }
                    else { background = stats(all) { x,y in !excluded[y*w+x] && !(x >= b.l-4 && x < b.r+4 && y >= b.t-4 && y < b.b+4) } }
                    var ratios: [String: Any] = [:]
                    if let inside = inside, let background = background {
                        for key in ["laplacian_variance","tenengrad","gradient_energy_p90"] { ratios[key] = background[key]! > 0 ? inside[key]!/background[key]! : NSNull() }
                    }
                    item["smoothed"] = ["region":inside as Any? ?? NSNull(),"outside":background as Any? ?? NSNull(),"region_to_outside":ratios]
                }
                output.append(item)
            }
        }
        func boundary(_ n: Int,_ i: Int) -> Int { i*(n/4)+min(i,n%4) }
        var tiles: [Double] = []
        for y in 0..<4 { for x in 0..<4 {
            if let metric = stats((boundary(w,x)+1,boundary(h,y)+1,boundary(w,x+1)-1,boundary(h,y+1)-1)) { tiles.append(metric["tenengrad"]!) }
        }}
        return ["version":"swift-scalar-gaussian1-v2","treatment":"gaussian1","sigma":1.0,
                "global":["smoothed":stats(all) as Any? ?? NSNull()],"tile_tenengrad":tiles,"regions":output]
    }
}
