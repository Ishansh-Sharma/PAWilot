import Foundation
import CoreGraphics

public enum PetState: String, CaseIterable, Codable {
    case idle, sitting, sleeping, walking, interaction, listening, working
}

public enum ActivityText {
    /// Collapses whitespace and control characters and bounds the length of observed text.
    public static func clean(_ text: String, limit: Int) -> String {
        let blank = CharacterSet.whitespacesAndNewlines.union(.controlCharacters)
        let spaced = String(String.UnicodeScalarView(text.unicodeScalars.map { blank.contains($0) ? " " : $0 }))
        return String(spaced.split(separator: " ").joined(separator: " ").prefix(max(0, limit)))
    }
}

/// Subtle procedural motion that keeps still photographic frames from looking frozen.
public enum Liveliness {
    /// Vertical scale around the ground line: slow chest rise while sitting, deeper while asleep.
    public static func breath(state: PetState, time: Double) -> CGFloat {
        switch state {
        case .walking: return 1
        case .sleeping: return 1 + 0.018 * CGFloat(sin(time * 2 * .pi / 4.4))
        default: return 1 + 0.009 * CGFloat(sin(time * 2 * .pi / 3.1))
        }
    }
    /// Blend weight of the incoming pose after a state change (0 = old pose, 1 = new pose).
    public static func blend(sinceChange: Double, duration: Double = 0.28) -> CGFloat {
        let t = min(max(sinceChange / duration, 0), 1)
        return CGFloat(t * t * (3 - 2 * t))
    }
}

public struct PetBehavior {
    public init() {}

    public func state(elapsed: TimeInterval, quiet: Bool, busy: Bool, hovered: Bool, chatting: Bool) -> PetState {
        if quiet { return .sleeping }
        if busy { return .working }
        if hovered { return .interaction }
        if chatting { return .listening }
        switch Int(max(0, elapsed)) % 64 {
        case 0..<5: return .sitting
        case 5..<22: return .walking
        case 22..<29: return .idle
        case 29..<48: return .walking
        default: return .sleeping
        }
    }

    public static func clampedOrigin(_ origin: CGPoint, size: CGSize, screen: CGRect) -> CGPoint {
        CGPoint(x: min(max(origin.x, screen.minX), max(screen.minX, screen.maxX - size.width)),
                y: min(max(origin.y, screen.minY), max(screen.minY, screen.maxY - size.height)))
    }
}

