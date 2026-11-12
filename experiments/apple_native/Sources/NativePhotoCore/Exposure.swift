import Foundation
public enum Exposure {
    public static func measure(_ rgba: [UInt8],width w: Int,height h: Int,detectors: [String: Any]) -> [String: Any] {
        func clipping(_ left: Int,_ top: Int,_ right: Int,_ bottom: Int) -> Double? {
            guard right > left && bottom > top else { return nil }
            var clipped = 0
            for y in top..<bottom { for x in left..<right {
                let i = (y*w+x)*4
                if (rgba[i] >= 254 && rgba[i+1] >= 254 && rgba[i+2] >= 254) || (rgba[i] <= 1 && rgba[i+1] <= 1 && rgba[i+2] <= 1) { clipped += 1 }
            }}
            return 100*(Double(clipped)/Double((right-left)*(bottom-top)))
        }
        var subjects: [String: [Double]] = [:]
        for (kind,detection) in detectors {
            var values: [Double] = []
            for region in (detection as! [String: Any])["regions"] as! [[String: Any]] {
                let b = (region["box"] as! [NSNumber]).map(\.doubleValue)
                if let value = clipping(max(0,Int(floor(b[0]*Double(w)))),max(0,Int(floor(b[1]*Double(h)))),min(w,Int(ceil((b[0]+b[2])*Double(w)))),min(h,Int(ceil((b[1]+b[3])*Double(h))))) { values.append(value) }
            }
            subjects[kind] = values
        }
        return ["global":clipping(0,0,w,h)!,"subjects":subjects]
    }
}
