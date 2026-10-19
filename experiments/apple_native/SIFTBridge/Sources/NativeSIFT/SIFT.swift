import Foundation
import CSIFT

public struct SIFTMatch: Codable, Equatable, Sendable {
    public let mutualMatches: Int
    public let inliers: Int
    public let inlierFraction: Double
    public let coverageA: Double
    public let coverageB: Double
    public let candidate: Bool
}
public struct SIFTError: Error, CustomStringConvertible {
    public let description: String
    public init(description: String) { self.description = description }
}
/// Owned, reusable keypoints/descriptors from an upright sRGB RGBA8 display preview.
/// Does not retain pixels, read files, launch processes or modify input buffers.
/// The class is deliberately not Sendable; callers own their scheduling policy.
public final class SIFTFeatures {
    private let handle: OpaquePointer
    public static var openCVVersion: String { String(cString:npsift_version()) }
    public var keypointCount: Int { Int(npsift_count(handle)) }
    public init(rgba: Data, width: Int, height: Int, bytesPerRow: Int? = nil) throws {
        guard (1...1024).contains(width), (1...1024).contains(height) else {
            throw SIFTError(description:"Expected preview dimensions 1...1024")
        }
        let stride = bytesPerRow ?? width*4
        guard stride >= width*4, stride <= Int.max/height, rgba.count >= (height-1)*stride+width*4 else {
            throw SIFTError(description:"Invalid RGBA8 row stride or truncated data")
        }
        var output: OpaquePointer?
        var error = [CChar](repeating:0,count:1024)
        let status = rgba.withUnsafeBytes { bytes in
            npsift_extract_rgba(bytes.bindMemory(to:UInt8.self).baseAddress,rgba.count,
                               Int32(width),Int32(height),stride,&output,&error,error.count)
        }
        guard status == 0, let output = output else { throw SIFTError(description:String(cString:error)) }
        handle = output
    }
    deinit { npsift_destroy(handle) }
    public func compare(to other: SIFTFeatures) throws -> SIFTMatch {
        var result = NPSIFTResult()
        var error = [CChar](repeating:0,count:1024)
        guard npsift_compare(handle,other.handle,&result,&error,error.count) == 0 else {
            throw SIFTError(description:String(cString:error))
        }
        return SIFTMatch(mutualMatches:Int(result.mutual_matches),inliers:Int(result.inliers),
                         inlierFraction:result.inlier_fraction,coverageA:result.coverage_a,
                         coverageB:result.coverage_b,candidate:result.sift_candidate != 0)
    }
}
