import AppKit
import SwiftUI
import PawCore

final class KittenAtlas {
    static let shared = KittenAtlas()
    struct Frame {
        let image: NSImage
        let width: Int
        let height: Int
        let alpha: [UInt8]
        let floor: CGFloat
        /// Horizontal extent of the feet, used to place the contact shadow.
        let footMin: CGFloat
        let footMax: CGFloat
    }
    let frames: [Frame]

    private init() {
        guard let url = Bundle.main.resourceURL?.appendingPathComponent("kitten/kitten-sprites.png"),
              let source = NSImage(contentsOf: url), let cg = source.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
            frames = []; return
        }
        var decoded: [Frame] = []
        for index in 0..<16 {
            let x0 = (index % 4) * cg.width / 4, x1 = (index % 4 + 1) * cg.width / 4
            let y0 = (index / 4) * cg.height / 4, y1 = (index / 4 + 1) * cg.height / 4
            guard let crop = cg.cropping(to: CGRect(x: x0, y: y0, width: x1 - x0, height: y1 - y0)) else { continue }
            let width = crop.width, height = crop.height
            var bytes = [UInt8](repeating: 0, count: width * height * 4)
            let valid = bytes.withUnsafeMutableBytes { raw -> Bool in
                guard let context = CGContext(data: raw.baseAddress, width: width, height: height, bitsPerComponent: 8,
                                              bytesPerRow: width * 4, space: CGColorSpaceCreateDeviceRGB(),
                                              bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue) else { return false }
                context.draw(crop, in: CGRect(x: 0, y: 0, width: width, height: height))
                return true
            }
            guard valid else { continue }
            let alpha = stride(from: 3, to: bytes.count, by: 4).map { bytes[$0] }
            var floor = 0
            for y in 0..<height where alpha[(y * width)..<((y + 1) * width)].contains(where: { $0 > 80 }) { floor = y }
            var footMin = width, footMax = 0
            for y in max(0, floor - 14)...floor {
                for x in 0..<width where alpha[y * width + x] > 80 { footMin = min(footMin, x); footMax = max(footMax, x) }
            }
            if footMin > footMax { footMin = 0; footMax = width }
            decoded.append(Frame(image: NSImage(cgImage: crop, size: NSSize(width: width, height: height)),
                                 width: width, height: height, alpha: alpha, floor: CGFloat(floor),
                                 footMin: CGFloat(footMin), footMax: CGFloat(footMax)))
        }
        frames = decoded
    }

    func index(state: PetState, time: Double) -> Int {
        switch state {
        case .walking: return Int(time * 9) % 8
        case .sleeping: return 12 + Int(time / 2) % 4
        case .listening, .interaction, .working: return time.truncatingRemainder(dividingBy: 6) > 5.7 ? 11 : 9
        default: return time.truncatingRemainder(dividingBy: 7) > 6.7 ? 11 : 8
        }
    }
}

struct KittenView: View {
    var state: PetState
    var time: Double
    var body: some View {
        if KittenAtlas.shared.frames.count == 16 {
            Image(nsImage: KittenAtlas.shared.frames[KittenAtlas.shared.index(state: state, time: time)].image)
                .resizable().scaledToFit().accessibilityLabel("Photorealistic kitten")
        }
    }
}

final class KittenSurface: NSView {
    var clicked: (() -> Void)?
    var moved: (() -> Void)?
    var isDragging = false
    var hovered = false
    var facingRight = false
    var state: PetState = .sitting
    var animationTime: Double = 0
    private var mouseStart = CGPoint.zero
    private var originStart = CGPoint.zero
    private var didDrag = false
    private let atlas = KittenAtlas.shared
    override var isFlipped: Bool { true }

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        setAccessibilityElement(true)
        setAccessibilityRole(.button)
        setAccessibilityLabel("Paw kitten — click to chat, drag to carry")
    }
    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }
    override func accessibilityPerformPress() -> Bool { clicked?(); return true }

    private var frameData: KittenAtlas.Frame? {
        guard atlas.frames.count == 16 else { return nil }
        return atlas.frames[atlas.index(state: state, time: animationTime)]
    }
    private let scale: CGFloat = 0.53
    private let ground: CGFloat = 8
    // Pose blending across state changes (sit → walk → sleep) instead of a hard cut.
    private var shownState: PetState?
    private var previousFrame: KittenAtlas.Frame?
    private var currentFrame: KittenAtlas.Frame?
    private var changedAt = -10.0

    private func imageRect(_ frame: KittenAtlas.Frame, breath: CGFloat = 1) -> CGRect {
        // Breathing stretches the body upward from the ground line, so the feet never slide.
        CGRect(x: (bounds.width - CGFloat(frame.width) * scale) / 2,
               y: bounds.height - ground - frame.floor * scale * breath,
               width: CGFloat(frame.width) * scale, height: CGFloat(frame.height) * scale * breath)
    }
    private func drawShadow(_ frame: KittenAtlas.Frame, opacity: CGFloat) {
        // Soft contact shadow so the kitten sits on the desktop rather than floating over it.
        let left = (bounds.width - CGFloat(frame.width) * scale) / 2
        let minX = left + frame.footMin * scale, maxX = left + frame.footMax * scale
        let width = max(40, (maxX - minX) * 1.08)
        let rect = CGRect(x: (minX + maxX) / 2 - width / 2, y: bounds.height - ground - 7, width: width, height: 13)
        NSGradient(colors: [NSColor.black.withAlphaComponent(0.34 * opacity), NSColor.black.withAlphaComponent(0.12 * opacity), .clear],
                   atLocations: [0, 0.55, 1], colorSpace: .deviceRGB)?
            .draw(in: NSBezierPath(ovalIn: rect), relativeCenterPosition: .zero)
    }
    override func draw(_ dirtyRect: NSRect) {
        NSColor.clear.setFill(); dirtyRect.fill(using: .copy)
        guard let frame = frameData else { return }
        if shownState != state {
            if shownState != nil { previousFrame = currentFrame; changedAt = animationTime }
            shownState = state
        }
        currentFrame = frame
        let mix = Liveliness.blend(sinceChange: animationTime - changedAt)
        let breath = Liveliness.breath(state: state, time: animationTime)
        NSGraphicsContext.saveGraphicsState()
        if facingRight {
            let transform = NSAffineTransform()
            transform.translateX(by: bounds.width, yBy: 0)
            transform.scaleX(by: -1, yBy: 1)
            transform.concat()
        }
        let hints: [NSImageRep.HintKey: Any] = [.interpolation: NSImageInterpolation.high]
        if mix < 1, let previousFrame {
            drawShadow(previousFrame, opacity: 1 - mix)
            previousFrame.image.draw(in: imageRect(previousFrame), from: .zero, operation: .sourceOver, fraction: 1 - mix, respectFlipped: true, hints: hints)
        }
        drawShadow(frame, opacity: mix)
        frame.image.draw(in: imageRect(frame, breath: breath), from: .zero, operation: .sourceOver, fraction: mix, respectFlipped: true, hints: hints)
        NSGraphicsContext.restoreGraphicsState()
    }

    func opaque(at screenPoint: CGPoint) -> Bool {
        guard let window, let frame = frameData else { return false }
        var local = convert(window.convertPoint(fromScreen: screenPoint), from: nil)
        if facingRight { local.x = bounds.width - local.x }
        let rect = imageRect(frame)
        guard rect.contains(local) else { return false }
        let x = Int((local.x - rect.minX) / rect.width * CGFloat(frame.width))
        let y = Int((local.y - rect.minY) / rect.height * CGFloat(frame.height))
        guard x >= 0, y >= 0, x < frame.width, y < frame.height else { return false }
        return frame.alpha[y * frame.width + x] > 45
    }
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
    override func mouseDown(with event: NSEvent) {
        isDragging = true; didDrag = false
        mouseStart = NSEvent.mouseLocation; originStart = window?.frame.origin ?? .zero
    }
    override func mouseDragged(with event: NSEvent) {
        guard let window else { return }
        let point = NSEvent.mouseLocation
        let dx = point.x - mouseStart.x, dy = point.y - mouseStart.y
        didDrag = didDrag || abs(dx) + abs(dy) > 4
        let screen = NSScreen.screens.first { $0.frame.contains(point) } ?? window.screen ?? NSScreen.main
        guard let screen else { return }
        window.setFrameOrigin(PetBehavior.clampedOrigin(CGPoint(x: originStart.x + dx, y: originStart.y + dy), size: window.frame.size, screen: screen.visibleFrame))
        moved?()
    }
    override func mouseUp(with event: NSEvent) {
        isDragging = false
        if !didDrag { clicked?() }
        if let origin = window?.frame.origin { UserDefaults.standard.set([origin.x, origin.y], forKey: "petPosition") }
        moved?()
    }
}
