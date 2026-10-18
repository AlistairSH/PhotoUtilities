// swift-tools-version: 5.9
import PackageDescription
let package = Package(name: "NativePhotoExperiment", platforms: [.macOS(.v14), .iOS(.v17)], products: [
    .library(name: "NativePhotoCore", targets: ["NativePhotoCore"]),
    .executable(name: "native-photo", targets: ["native-photo"])
], targets: [.target(name: "NativePhotoCore"), .executableTarget(name: "native-photo", dependencies: ["NativePhotoCore"]),
             .executableTarget(name: "native-checks", dependencies: ["NativePhotoCore"]),
             .executableTarget(name: "native-image", dependencies: ["NativePhotoCore"]),
             .executableTarget(name: "native-policy", dependencies: ["NativePhotoCore"]),
             .executableTarget(name: "native-measure", dependencies: ["NativePhotoCore"])])
