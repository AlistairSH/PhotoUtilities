import Foundation

/// Scalar reference port. Pixels are display-view, 8-bit RGB, as in the accepted helper.
/// Uses the pinned baseline's integer grayscale and sigma-one Gaussian rounding.
public enum Focus {
    static func reflect(_ p: Int, _ n: Int) -> Int {
        if n == 1 { return 0 }
        var x = p
        while x < 0 || x >= n { x = x < 0 ? -x : 2*n-x-2 }
        return x
    }
    public static func gray(_ rgba: [UInt8]) -> [UInt8] {
        stride(from: 0, to: rgba.count, by: 4).map { i in
            UInt8((9798*Int(rgba[i])+19235*Int(rgba[i+1])+3735*Int(rgba[i+2])+16384)>>15)
        }
    }
    public static func smooth(_ gray: [UInt8], width w: Int, height h: Int) -> [Double] {
        precondition(w > 0 && h > 0 && gray.count == w*h)
        // Pinned OpenCV 4.11 sigma=1 / uint8 kernel, 8-bit fixed-point.
        // Preserve a single final rounding after the two separable passes.
        let k = [1,14,62,102,62,14,1]
        var horizontal = [Int](repeating:0,count:w*h)
        var output = [Double](repeating:0,count:w*h)
        for y in 0..<h { for x in 0..<w {
            for d in -3...3 { horizontal[y*w+x] += Int(gray[y*w+reflect(x+d,w)])*k[d+3] }
        }}
        for y in 0..<h { for x in 0..<w {
            var value = 0
            for d in -3...3 { value += horizontal[reflect(y+d,h)*w+x]*k[d+3] }
            output[y*w+x] = Double((value+32768)>>16)/255
        }}
        return output
    }
    public static func metrics(_ pixels: [Double], width w: Int, height h: Int,
                               mask: [Bool]? = nil) -> [String: Double]? {
        precondition(w > 0 && h > 0 && pixels.count == w*h && (mask == nil || mask!.count == w*h))
        guard w >= 3 && h >= 3 else { return nil }
        func p(_ x: Int,_ y: Int) -> Double { pixels[y*w+x] }
        var laps: [Double] = [], energies: [Double] = [], luminance: [Double] = []
        for y in 1..<h-1 { for x in 1..<w-1 {
            if let mask = mask, (-1...1).contains(where: { dy in (-1...1).contains { dx in !mask[(y+dy)*w+x+dx] } }) { continue }
            let lap = p(x-1,y)+p(x+1,y)+p(x,y-1)+p(x,y+1)-4*p(x,y)
            let dx = p(x+1,y-1)+2*p(x+1,y)+p(x+1,y+1)-p(x-1,y-1)-2*p(x-1,y)-p(x-1,y+1)
            let dy = p(x-1,y+1)+2*p(x,y+1)+p(x+1,y+1)-p(x-1,y-1)-2*p(x,y-1)-p(x+1,y-1)
            laps.append(lap); energies.append(dx*dx+dy*dy); luminance.append(p(x,y))
        }}
        guard laps.count >= 100 else { return nil }
        func mean(_ a: [Double]) -> Double { a.reduce(0,+)/Double(a.count) }
        func variance(_ a: [Double]) -> Double { let m = mean(a); return mean(a.map { ($0-m)*($0-m) }) }
        energies.sort()
        let q = Double(energies.count-1)*0.9, lo = Int(q)
        let quantile = energies[lo] + (energies[min(lo+1,energies.count-1)]-energies[lo])*(q-Double(lo))
        return ["pixels":Double(laps.count), "laplacian_variance":variance(laps), "tenengrad":mean(energies),
                "gradient_energy_p90":quantile, "luminance_mean":mean(luminance), "luminance_std":sqrt(variance(luminance))]
    }
}
