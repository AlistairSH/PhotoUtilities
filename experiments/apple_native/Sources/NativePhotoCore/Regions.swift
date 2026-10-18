import Foundation

public extension Focus {
    /// Same normalized top-left box convention and pixel guards as baseline.
    static func regions(_ rgba: [UInt8], width w: Int, height h: Int, detectors: [String: Any]) -> [String: Any] {
        let pixels = smooth(gray(rgba),width:w,height:h)
        func boxes(_ kind: String) -> [[String: Any]] { (detectors[kind] as? [String: Any])?["regions"] as? [[String: Any]] ?? [] }
        func coordinates(_ region: [String: Any]) -> [Double] {
            (region["box"] as! [CGFloat]).map { Double($0) }
        }
        func bounds(_ b: [Double]) -> (Int,Int,Int,Int) {
            let x = max(0,b[0]), y = max(0,b[1]), r = min(1,b[0]+b[2]), bottom = min(1,b[1]+b[3])
            return (Int(x*Double(w)),Int(y*Double(h)),Int((r*Double(w)).rounded(.toNearestOrEven)),Int((bottom*Double(h)).rounded(.toNearestOrEven)))
        }
        func mask(_ b: (Int,Int,Int,Int)) -> [Bool] {
            var result = [Bool](repeating:false,count:w*h)
            if b.2 > b.0 && b.3 > b.1 { for y in max(0,b.1)..<min(h,b.3) { for x in max(0,b.0)..<min(w,b.2) { result[y*w+x] = true } } }
            return result
        }
        var excluded = [Bool](repeating:false,count:w*h)
        for kind in ["faces","people","animals"] { for region in boxes(kind) {
            let m = mask(bounds(coordinates(region)))
            for i in m.indices where m[i] { excluded[i] = true }
        }}
        var output: [[String: Any]] = []
        for kind in ["faces","people","animals","objectness","attention"] {
            for (index,region) in boxes(kind).enumerated() {
                let box = coordinates(region), b = bounds(box), m = mask(b)
                var item: [String: Any] = ["id":"\(kind) \(index+1)","box":box,"pixels":[b.2-b.0,b.3-b.1],"usable":min(b.2-b.0,b.3-b.1)>=24,"raw":NSNull(),"smoothed":NSNull()]
                if min(b.2-b.0,b.3-b.1)>=24 {
                    var outside = [Bool](repeating:true,count:w*h)
                    // Complement of a 7x7 dilation; skip clipped neighbors outside image.
                    for y in 0..<h { for x in 0..<w where excluded[y*w+x] || m[y*w+x] {
                        for yy in max(0,y-3)...min(h-1,y+3) { for xx in max(0,x-3)...min(w-1,x+3) { outside[yy*w+xx] = false } }
                    }}
                    let inside = metrics(pixels,width:w,height:h,mask:m)
                    let background = metrics(pixels,width:w,height:h,mask:outside)
                    var ratios: [String: Any] = [:]
                    if let inside = inside, let background = background {
                        for metric in ["laplacian_variance","tenengrad","gradient_energy_p90"] {
                            ratios[metric] = background[metric]! > 0 ? inside[metric]!/background[metric]! : NSNull()
                        }
                    }
                    item["smoothed"] = ["region":inside as Any? ?? NSNull(),"outside":background as Any? ?? NSNull(),"region_to_outside":ratios]
                }
                output.append(item)
            }
        }
        var tiles: [Double] = []
        func boundary(_ n: Int,_ i: Int) -> Int { i*(n/4)+min(i,n%4) }
        for y in 0..<4 { for x in 0..<4 {
            let m = mask((boundary(w,x),boundary(h,y),boundary(w,x+1),boundary(h,y+1)))
            if let value = metrics(pixels,width:w,height:h,mask:m) { tiles.append(value["tenengrad"]!) }
        }}
        return ["version":"swift-scalar-gaussian1-v1","treatment":"gaussian1","sigma":1.0,
                "global":["smoothed":metrics(pixels,width:w,height:h) as Any? ?? NSNull()],"tile_tenengrad":tiles,"regions":output]
    }
}
