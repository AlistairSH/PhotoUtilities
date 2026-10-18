import Foundation
import Accelerate

public enum NumericalBackend: String { case scalar, accelerate }

/// Fixed-policy population moments and interpolated order statistics. Accelerate
/// changes reduction order only; the scalar implementation remains a test oracle.
public enum Statistics {
    public static func mean(_ values: [Double],backend: NumericalBackend) -> Double {
        precondition(!values.isEmpty)
        if backend == .scalar { return values.reduce(0,+)/Double(values.count) }
        var result = 0.0
        vDSP_meanvD(values,1,&result,vDSP_Length(values.count))
        return result
    }
    public static func variance(_ values: [Double],backend: NumericalBackend) -> Double {
        let m = mean(values,backend:backend)
        if backend == .scalar { return values.map { ($0-m)*($0-m) }.reduce(0,+)/Double(values.count) }
        // Bound scratch memory independently of image/region size. Centered
        // squares avoid the cancellation of E[x²]-E[x]² on low-contrast images.
        let capacity = min(values.count,65536)
        var centered = [Double](repeating:0,count:capacity), offset = -m, sum = 0.0
        values.withUnsafeBufferPointer { source in
            centered.withUnsafeMutableBufferPointer { scratch in
                var start = 0
                while start < values.count {
                    let count = min(capacity,values.count-start)
                    var partial = 0.0
                    vDSP_vsaddD(source.baseAddress!+start,1,&offset,scratch.baseAddress!,1,vDSP_Length(count))
                    vDSP_svesqD(scratch.baseAddress!,1,&partial,vDSP_Length(count))
                    sum += partial; start += count
                }
            }
        }
        return sum/Double(values.count)
    }
    /// Three-way quickselect keeps duplicate-rich/flat image data linear. The
    /// selected rank and adjacent minimum give the same interpolation as sorting.
    public static func quantile(_ values: inout [Double],fraction: Double,backend: NumericalBackend) -> Double {
        precondition(!values.isEmpty && fraction >= 0 && fraction <= 1)
        let position = Double(values.count-1)*fraction, rank = Int(position), weight = position-Double(rank)
        if backend == .scalar {
            values.sort()
            return values[rank]+(values[min(rank+1,values.count-1)]-values[rank])*weight
        }
        var left = 0, right = values.count-1
        while left < right {
            let a = values[left], b = values[(left+right)/2], c = values[right]
            let pivot = max(min(a,b),min(max(a,b),c))
            var low = left, current = left, high = right
            while current <= high {
                if values[current] < pivot { values.swapAt(low,current); low += 1; current += 1 }
                else if values[current] > pivot { values.swapAt(current,high); high -= 1 }
                else { current += 1 }
            }
            if rank < low { right = low-1 }
            else if rank > high { left = high+1 }
            else { break }
        }
        let lower = values[rank]
        guard weight > 0, rank+1 < values.count else { return lower }
        var upper = Double.infinity
        for i in rank+1..<values.count { upper = min(upper,values[i]) }
        return lower+(upper-lower)*weight
    }
}
