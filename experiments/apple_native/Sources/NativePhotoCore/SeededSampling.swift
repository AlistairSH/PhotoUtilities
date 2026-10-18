import Foundation

/// Compatibility for the accepted NumPy 2.0.2 default_rng(0) choice path only.
/// Fixed seed, not a general replacement for NumPy random or SeedSequence.
/// Algorithm references and attributions: ../../THIRD_PARTY.md.
public struct SeededSampling {
    var high: UInt64 = 0x1aa1b5345996452d
    var low: UInt64 = 0x09585eb7a69561e3
    var spare: UInt32? = nil
    public init() {}
    public mutating func next64() -> UInt64 {
        let product = low.multipliedFullWidth(by:4865540595714422341)
        let added = product.low.addingReportingOverflow(0x588133bc447873a9)
        high = product.high &+ (high &* 4865540595714422341) &+ (low &* 2549297995355413924) &+ 0x418ddadb3af71a82 &+ (added.overflow ? 1:0)
        low = added.partialValue
        let value = high ^ low, rotation = high >> 58
        return (value >> rotation) | (value << ((0 &- rotation) & 63))
    }
    mutating func next32() -> UInt32 {
        if let value = spare { spare = nil; return value }
        let value = next64(); spare = UInt32(truncatingIfNeeded:value >> 32)
        return UInt32(truncatingIfNeeded:value)
    }
    mutating func bounded(_ inclusive: Int) -> Int {
        precondition(inclusive >= 0 && inclusive < Int(UInt32.max))
        if inclusive == 0 { return 0 }
        let bound = UInt64(inclusive+1), threshold = (UInt64(UInt32.max)-UInt64(inclusive))%bound
        while true {
            let value = UInt64(next32())*bound, leftover = value & 0xffffffff
            if leftover >= threshold { return Int(value >> 32) }
        }
    }
    public mutating func choice(population n: Int, count k: Int) -> [Int] {
        precondition(n >= k && k >= 0 && n < Int(UInt32.max))
        if k == 0 { return [] }
        if n > 10000 && k > n/50 {
            var values = Array(0..<n)
            for i in stride(from:n-1,through:max(n-k,1),by:-1) { let j = bounded(i); values.swapAt(i,j) }
            return Array(values.suffix(k))
        }
        var selected = Set<Int>(), values: [Int] = []
        for j in n-k..<n {
            let draw = bounded(j), value = selected.contains(draw) ? j : draw
            selected.insert(value); values.append(value)
        }
        if k > 1 { for i in stride(from:k-1,through:1,by:-1) { let j = bounded(i); values.swapAt(i,j) } }
        return values
    }
}
