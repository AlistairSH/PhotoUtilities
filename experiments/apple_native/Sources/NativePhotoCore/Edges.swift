import Foundation

public struct EdgeProfiles: Codable {
    public var x: [Double] = [], y: [Double] = [], width: [Double] = [], contrast: [Double] = [], angle: [Double] = []
    public var censored: [Bool] = []
}
public enum Edges {
    static func quantile(_ input: [Double],_ q: Double) -> Double {
        let a = input.sorted(), index = Double(a.count-1)*q, low = Int(index)
        return a[low]+(a[min(low+1,a.count-1)]-a[low])*(index-Double(low))
    }
    public static func extract(_ gray: [UInt8],width w: Int,height h: Int, trace: ((String,[Float]) -> Void)? = nil) -> EdgeProfiles {
        precondition(w > 0 && h > 0 && gray.count == w*h)
        guard w > 36 && h > 36 else { return EdgeProfiles() }
        let weights = (-4...4).map { exp(-Double($0*$0)/2) }, total = (-4...4).map { exp(-Double($0*$0)/2) }.reduce(0,+)
        let k = weights.map { Float($0/total) }, input = gray.map { Float($0)/255 }
        var horizontal = [Float](repeating:0,count:w*h), image = horizontal
        for y in 0..<h { for x in 0..<w {
            var value = input[y*w+Focus.reflect(x-4,w)]*k[0]
            for d in -3...4 { value = value.addingProduct(input[y*w+Focus.reflect(x+d,w)],k[d+4]) }
            horizontal[y*w+x] = value
        }}
        for y in 0..<h { for x in 0..<w {
            var value = horizontal[y*w+x]*k[4]
            for d in 1...4 { value = value.addingProduct(horizontal[Focus.reflect(y-d,h)*w+x]+horizontal[Focus.reflect(y+d,h)*w+x],k[4+d]) }
            image[y*w+x] = value
        }}
        trace?("gaussian",image)
        var dx = image, dy = image, magnitude = image
        for y in 0..<h { for x in 0..<w {
            let l = Focus.reflect(x-1,w), r = Focus.reflect(x+1,w), t = Focus.reflect(y-1,h), b = Focus.reflect(y+1,h)
            dx[y*w+x] = 2*(image[y*w+r]-image[y*w+l])+((image[t*w+r]-image[t*w+l])+(image[b*w+r]-image[b*w+l]))
            dy[y*w+x] = (((image[b*w+l]+image[b*w+r])+image[b*w+x])+image[b*w+x])-(((image[t*w+l]+image[t*w+r])+image[t*w+x])+image[t*w+x])
            magnitude[y*w+x] = sqrt((dy[y*w+x]*dy[y*w+x]).addingProduct(dx[y*w+x],dx[y*w+x]))
        }}
        trace?("dx",dx); trace?("dy",dy); trace?("magnitude",magnitude)
        var candidates: [(Int,Int,Float)] = []
        for y in stride(from:18,to:h-18,by:3) { for x in stride(from:18,to:w-18,by:3) { candidates.append((x,y,magnitude[y*w+x])) } }
        if candidates.isEmpty { return EdgeProfiles() }
        let threshold = max(0.002,quantile(candidates.map { Double($0.2) },0.75))
        candidates = candidates.filter { $0.2 > Float(threshold) }
        if candidates.count > 3000 {
            var rng = SeededSampling()
            let take = rng.choice(population:candidates.count,count:3000)
            candidates = take.map { candidates[$0] }
        }
        if let trace = trace { trace("selected_x",candidates.map { Float($0.0) }); trace("selected_y",candidates.map { Float($0.1) }) }
        func sample(_ values: [Float],_ x: Float,_ y: Float) -> Float {
            let xx = Int((x*32).rounded(.toNearestOrEven)), yy = Int((y*32).rounded(.toNearestOrEven))
            let ix = xx >> 5, iy = yy >> 5, fx = Float(xx & 31)/32, fy = Float(yy & 31)/32
            let a = values[Focus.reflect(iy,h)*w+Focus.reflect(ix,w)], b = values[Focus.reflect(iy,h)*w+Focus.reflect(ix+1,w)]
            let c = values[Focus.reflect(iy+1,h)*w+Focus.reflect(ix,w)], d = values[Focus.reflect(iy+1,h)*w+Focus.reflect(ix+1,w)]
            return a*((1-fx)*(1-fy))+b*(fx*(1-fy))+c*((1-fx)*fy)+d*(fx*fy)
        }
        var output = EdgeProfiles()
        for (xi,yi,m) in candidates {
            let nx = dx[yi*w+xi]/m, ny = dy[yi*w+xi]/m
            let before = sample(magnitude,Float(xi)-nx,Float(yi)-ny), after = sample(magnitude,Float(xi)+nx,Float(yi)+ny)
            let shift: Float = before > max(m,after) ? -1 : after > m ? 1 : 0
            // Baseline promotes integer +/-1 shifts to float64, then remap
            // coordinates back to float32; retain that operation boundary.
            let x = Double(xi)+Double(nx)*Double(shift), y = Double(yi)+Double(ny)*Double(shift)
            let profile: [Float] = (-16...16).map { offset in
                sample(image,Float(x+Double(nx*Float(offset))),Float(y+Double(ny*Float(offset))))
            }
            let gradient = (0..<32).map { profile[$0+1]-profile[$0] }
            var peak = 14
            for i in 15..<18 where gradient[i] > gradient[peak] { peak = i }
            let height = gradient[peak]
            if height <= 0 { continue }
            var left = peak, right = peak
            while left > 0 && gradient[left-1] > Float(0.05)*height { left -= 1 }
            while right < 31 && gradient[right+1] > Float(0.05)*height { right += 1 }
            let contrast = Double(profile[right+1]-profile[left])
            if contrast < 10.0/255 { continue }
            func crossing(_ fraction: Double) -> Double {
                // NumPy interp search uses rightmost equal sample on plateaus.
                let target = Double(profile[left]+Float(fraction*contrast))
                if target < Double(profile[left]) { return Double(left) }
                if target > Double(profile[right+1]) { return Double(right+1) }
                var lo = left, hi = right+2
                while lo < hi { let middle = (lo+hi)/2; if Double(profile[middle]) <= target { lo = middle+1 } else { hi = middle } }
                let lower = lo-1
                if lower >= right+1 { return Double(right+1) }
                if lower < left { return Double(left) }
                return Double(lower)+(target-Double(profile[lower]))/(Double(profile[lower+1])-Double(profile[lower]))
            }
            let angle = atan2(ny,nx), pi = Float.pi
            var wrapped = angle.truncatingRemainder(dividingBy:pi)
            if wrapped < 0 { wrapped += pi }
            output.x.append(x); output.y.append(y); output.width.append(crossing(0.9)-crossing(0.1)); output.contrast.append(contrast)
            output.angle.append(Double(wrapped)); output.censored.append(left == 0 || right == 31)
        }
        return output
    }
    public static func summarize(_ edges: EdgeProfiles,box: [Double]? = nil,width: Int = 1,height: Int = 1) -> [String: Any] {
        let indices = edges.width.indices.filter { i in
            guard let b = box else { return true }
            let x = edges.x[i]/Double(width), y = edges.y[i]/Double(height)
            return x >= b[0] && x < b[0]+b[2] && y >= b[1] && y < b[1]+b[3]
        }
        guard !indices.isEmpty else { return ["edges":0,"sufficient":false,"median_width":NSNull(),"contrast_soft_fraction":NSNull(),"direction_ratio":NSNull()] }
        let widths = indices.map { edges.width[$0] }, contrasts = indices.map { edges.contrast[$0] }
        let bins = indices.map { Int(floor((edges.angle[$0]+Double.pi/8)/(Double.pi/4)))%4 }
        let medians: [Double?] = (0..<4).map { bin in let values = widths.indices.filter { bins[$0] == bin }.map { widths[$0] }; return values.count >= 25 ? quantile(values,0.5) : nil }
        var directions: [(Double,Double)] = []
        for (i,j) in [(0,2),(1,3)] { if let a = medians[i], let b = medians[j], min(a,b) > 0 { directions.append((max(a,b)/min(a,b),max(a,b))) } }
        let best = directions.max { $0.0 == $1.0 ? $0.1 < $1.1 : $0.0 < $1.0 }
        let acutance = zip(contrasts,widths).map { $0.0/max($0.1,1e-6) }
        let soft = widths.indices.filter { widths[$0] > (contrasts[$0] <= 50.0/255 ? 5 : 3) }.count
        return ["edges":indices.count,"sufficient":indices.count >= 50,"median_width":quantile(widths,0.5),"width_q25":quantile(widths,0.25),"width_q75":quantile(widths,0.75),
                "contrast_soft_fraction":Double(soft)/Double(indices.count),"median_acutance":quantile(acutance,0.5),"normal_bin_medians":medians.map { present($0) },
                "direction_ratio":present(best?.0),"direction_wide_width":present(best?.1),"censored_fraction":Double(indices.filter { edges.censored[$0] }.count)/Double(indices.count)]
    }
    public static func flags(_ summary: [String: Any]) -> [String: Bool] {
        guard summary["sufficient"] as! Bool else { return ["edge_width":false,"contrast_proxy":false,"directional":false] }
        let directional = (summary["direction_ratio"] as? Double).map { $0 >= 1.6 && (summary["direction_wide_width"] as! Double) >= 4.5 } ?? false
        return ["edge_width":(summary["median_width"] as! Double) >= 4,"contrast_proxy":(summary["contrast_soft_fraction"] as! Double) >= 0.6,"directional":directional]
    }
}
