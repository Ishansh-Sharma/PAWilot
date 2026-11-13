import Foundation
import CoreGraphics
import PawCore

// Standalone checks deliberately avoid XCTest, which requires the full IDE on
// this machine. They run with Apple's standalone Command Line Tools only.
func check(_ condition: @autoclosure () -> Bool, _ name: String) {
    guard condition() else { fatalError("FAIL: \(name)") }
    print("PASS: \(name)")
}

let behavior = PetBehavior()
check(behavior.state(elapsed: 4, quiet: true, busy: true, hovered: true, chatting: true) == .sleeping, "Quiet mode overrides activity")
check(behavior.state(elapsed: 0, quiet: false, busy: true, hovered: true, chatting: true) == .working, "Work state takes priority")
check(behavior.state(elapsed: 0, quiet: false, busy: false, hovered: true, chatting: true) == .interaction, "Cursor interaction state")
check(behavior.state(elapsed: 0, quiet: false, busy: false, hovered: false, chatting: true) == .listening, "Conversation listening state")
let states = Set((0..<54).map { behavior.state(elapsed: Double($0), quiet: false, busy: false, hovered: false, chatting: false) })
check(states == Set([.sitting, .idle, .walking, .sleeping]), "Full autonomous state cycle")
check(PetBehavior.clampedOrigin(CGPoint(x: 80, y: -200), size: CGSize(width: 180, height: 180), screen: CGRect(x: -1440, y: 0, width: 1440, height: 900)) == CGPoint(x: -180, y: 0), "Drag clamp on negative-coordinate display")
var motion = RoamingMotion()
let screen = CGRect(x: 0, y: 0, width: 1000, height: 800)
let size = CGSize(width: 180, height: 180)
let origin = CGPoint(x: 400, y: 30)
check(motion.advance(origin: origin, size: size, screen: screen, elapsed: 0.1, paused: false).x < origin.x, "Kitten actually moves across desktop")
check(motion.advance(origin: origin, size: size, screen: screen, elapsed: 0.1, paused: true) == origin, "Chat and drag pause roaming")
let edge = motion.advance(origin: CGPoint(x: 8, y: 30), size: size, screen: screen, elapsed: 1, paused: false)
check(edge.x >= 8 && motion.direction == 1, "Screen edge reverses walking direction")
let resumed = motion.advance(origin: origin, size: size, screen: screen, elapsed: 300, paused: false)
check(abs(resumed.x - origin.x) <= 4.31, "Wake from sleep cannot teleport kitten")
for pet in [CGRect(x: 0, y: 0, width: 180, height: 180), CGRect(x: 820, y: 620, width: 180, height: 180)] {
    let bubble = BubbleGeometry.frame(pet: pet, size: CGSize(width: 350, height: 400), screen: screen)
    check(screen.contains(bubble), "Chat bubble fits on screen at edge")
}
check(ActivityText.clean("  Inbox\n(3) \u{0007}–  Gmail\t ", limit: 300) == "Inbox (3) – Gmail", "Window titles are normalised")
check(ActivityText.clean(String(repeating: "a", count: 500), limit: 300).count == 300, "Window titles are bounded")
check(Liveliness.breath(state: .walking, time: 1.3) == 1, "Walking has no breathing stretch")
let breaths = (0..<200).map { Liveliness.breath(state: .sleeping, time: Double($0) / 20) }
check(breaths.max()! <= 1.019 && breaths.min()! >= 0.981 && breaths.max()! > 1.015, "Sleeping breath is visible but subtle")
check(Liveliness.blend(sinceChange: 0) == 0 && Liveliness.blend(sinceChange: 5) == 1 && Liveliness.blend(sinceChange: 1, duration: 2) == 0.5, "Pose change eases between frames")
print("17 native behavior and geometry checks passed.")

