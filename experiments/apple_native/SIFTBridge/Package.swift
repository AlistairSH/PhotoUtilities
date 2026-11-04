// swift-tools-version: 5.9
import Foundation
import PackageDescription

// Dependency products stay outside Git. macOS static prefix OR Apple XCFramework.
let environment = ProcessInfo.processInfo.environment
let framework = "Artifacts/opencv2.xcframework"
let frameworkURL = URL(fileURLWithPath:#filePath).deletingLastPathComponent().appendingPathComponent(framework)
var dependencies: [Target.Dependency] = []
var cSettings: [CXXSetting] = []
var linkSettings: [LinkerSetting] = []
var binaryTargets: [Target] = []
if FileManager.default.fileExists(atPath:frameworkURL.path) {
    binaryTargets = [.binaryTarget(name:"OpenCV",path:framework)]
    dependencies = [.target(name:"OpenCV")]
} else if let root = environment["OPENCV_ROOT"], !root.isEmpty {
    cSettings = [.unsafeFlags(["-I",root+"/include/opencv4"])]
    linkSettings = [.unsafeFlags(["-L",root+"/lib","-L",root+"/lib/opencv4/3rdparty"])] +
        ["opencv_calib3d","opencv_features2d","opencv_flann","opencv_imgproc","opencv_core","zlib","tegra_hal"].map { .linkedLibrary($0) }
} else {
    fatalError("Set OPENCV_ROOT for the local macOS build, or stage the package with stage_apple_package.py and a locally built XCFramework. See README.md.")
}
let package = Package(name:"NativeSIFTBridge",platforms:[.macOS(.v14),.iOS(.v17)],
    products:[.library(name:"NativeSIFT",targets:["NativeSIFT"]),.library(name:"NativePhotoAnalysis",targets:["NativePhotoAnalysis"]),.executable(name:"native-sift",targets:["native-sift"]),.executable(name:"photo-review",targets:["photo-review"])],
    dependencies:[.package(path:"..")],
    targets: binaryTargets + [
        .target(name:"CSIFT",dependencies:dependencies,publicHeadersPath:"include",cxxSettings:cSettings,linkerSettings:linkSettings),
        .target(name:"NativeSIFT",dependencies:["CSIFT"]),
        .target(name:"NativePhotoAnalysis",dependencies:["NativeSIFT",.product(name:"NativePhotoCore",package:"apple_native")]),
        .executableTarget(name:"photo-review",dependencies:["NativePhotoAnalysis"]),
        .executableTarget(name:"native-analyze",dependencies:["NativePhotoAnalysis"]),
        .executableTarget(name:"analysis-checks",dependencies:["NativePhotoAnalysis",.product(name:"NativePhotoCore",package:"apple_native")]),
        .executableTarget(name:"native-sift",dependencies:["NativeSIFT",.product(name:"NativePhotoCore",package:"apple_native")]),
        .executableTarget(name:"sift-checks",dependencies:["NativeSIFT","CSIFT"])
    ],cxxLanguageStandard:.cxx17)
