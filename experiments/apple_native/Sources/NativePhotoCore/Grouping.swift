import Foundation
public enum Grouping {
    public static func level(distance: Double, sift: Bool = false) throws -> String {
        guard distance.isFinite && distance >= 0 else { throw CocoaError(.fileReadInvalidFileName) }
        let vision = distance < 0.45
        if !vision && !sift { return "unmatched" }
        return vision && (distance < 0.40 || sift) ? "likely" : "potential"
    }
    public static func components(count: Int, edges: [(Int,Int)]) -> [[Int]] {
        var adjacency = [[Int]](repeating: [], count: count)
        for (a,b) in edges { precondition(a >= 0 && b >= 0 && a < count && b < count); adjacency[a].append(b); adjacency[b].append(a) }
        var seen = Set<Int>(), groups: [[Int]] = []
        for start in 0..<count where !seen.contains(start) {
            var stack = [start], members: [Int] = []
            while let i = stack.popLast() { if seen.insert(i).inserted { members.append(i); stack += adjacency[i] } }
            groups.append(members.sorted())
        }
        return groups.sorted { $0.count == $1.count ? $0.lexicographicallyPrecedes($1) : $0.count > $1.count }
    }
}
