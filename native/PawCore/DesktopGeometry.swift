import Foundation
import CoreGraphics

public struct RoamingMotion {
    public private(set) var direction: CGFloat = -1
    public init() {}
    public mutating func advance(origin: CGPoint, size: CGSize, screen: CGRect, elapsed: Double, paused: Bool) -> CGPoint {
        guard !paused else { return PetBehavior.clampedOrigin(origin, size: size, screen: screen) }
        let step = min(max(elapsed, 0), 0.1) * 43
        var next = origin
        next.x += direction * step
        if next.x <= screen.minX + 8 { direction = 1 }
        if next.x + size.width >= screen.maxX - 8 { direction = -1 }
        return PetBehavior.clampedOrigin(next, size: size, screen: screen.insetBy(dx: 8, dy: 0))
    }
}

public enum BubbleGeometry {
    public static func frame(pet: CGRect, size: CGSize, screen: CGRect) -> CGRect {
        let x = pet.midX - size.width / 2
        let y = pet.maxY - 15 + size.height <= screen.maxY ? pet.maxY - 15 : pet.minY - size.height + 15
        return CGRect(origin: PetBehavior.clampedOrigin(CGPoint(x: x, y: y), size: size, screen: screen.insetBy(dx: 10, dy: 10)), size: size)
    }
}
