// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "PAWilot",
    platforms: [.macOS(.v14)],
    products: [.executable(name: "PAWilot", targets: ["PAWilot"])],
    targets: [
        .target(name: "PawCore", path: "native/PawCore"),
        .executableTarget(name: "PAWilot", dependencies: ["PawCore"], path: "native/PAWilot"),
        .executableTarget(name: "PawCoreChecks", dependencies: ["PawCore"], path: "native/Tests")
    ]
)

