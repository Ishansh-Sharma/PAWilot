import SwiftUI
import AppKit
import PawCore

@main
struct PAWilotApp {
    @MainActor static func main() {
        let app = NSApplication.shared
        let delegate = AppDelegate()
        app.delegate = delegate
        withExtendedLifetime(delegate) { app.run() }
    }
}

final class CompanionPanel: NSPanel {
    override var canBecomeKey: Bool { false }
    override var canBecomeMain: Bool { false }
}

final class ChatBubblePanel: NSPanel {
    var dismissed: (() -> Void)?
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { false }
    override func cancelOperation(_ sender: Any?) { dismissed?() }
    override func keyDown(with event: NSEvent) {
        if event.keyCode == 53 { dismissed?() } else { super.keyDown(with: event) }
    }
}

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate {
    let service = AgentService()
    private var pet: CompanionPanel?
    private var surface: KittenSurface?
    private var bubble: ChatBubblePanel?
    private var menuItem: NSStatusItem?
    private var timer: Timer?
    private var outsideMonitor: Any?
    private var motion = RoamingMotion()
    private var lastTick = ProcessInfo.processInfo.systemUptime
    private var behaviorTime = 0.0
    private var animationTime = 0.0
    private var lastFrame = -1
    private var nudge: CompanionPanel?
    private var nudgeUntil = 0.0
    private var activityTimer: Timer?
    private var reporting = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        installMenu()
        createPet()
        // Deliberately no chat, dashboard, activation, or Space switch at launch.
        Task { await service.start() }
        let timer = Timer(timeInterval: 1.0 / 30, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated { self?.tick() }
        }
        timer.tolerance = 0.004
        RunLoop.main.add(timer, forMode: .common)
        self.timer = timer
        let sampler = Timer(timeInterval: 10, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated { self?.observeActivity() }
        }
        sampler.tolerance = 2
        RunLoop.main.add(sampler, forMode: .common)
        activityTimer = sampler
        outsideMonitor = NSEvent.addGlobalMonitorForEvents(matching: [.leftMouseDown, .rightMouseDown]) { [weak self] _ in
            MainActor.assumeIsolated { self?.hideBubble() }
        }
        NotificationCenter.default.addObserver(self, selector: #selector(screenChanged), name: NSApplication.didChangeScreenParametersNotification, object: nil)
    }

    func installMenu() {
        // Standard responder-chain shortcuts are needed even for an accessory app.
        let mainMenu = NSMenu()
        let appItem = NSMenuItem()
        let appMenu = NSMenu()
        let quitItem = NSMenuItem(title: "Quit PAWilot", action: #selector(quit), keyEquivalent: "q")
        quitItem.target = self
        appMenu.addItem(quitItem); appItem.submenu = appMenu; mainMenu.addItem(appItem)
        let editItem = NSMenuItem(title: "Edit", action: nil, keyEquivalent: "")
        let edit = NSMenu(title: "Edit")
        for (title, selector, key) in [("Undo", "undo:", "z"), ("Cut", "cut:", "x"),
                                       ("Copy", "copy:", "c"), ("Paste", "paste:", "v"), ("Select All", "selectAll:", "a")] {
            edit.addItem(withTitle: title, action: NSSelectorFromString(selector), keyEquivalent: key)
        }
        editItem.submenu = edit; mainMenu.addItem(editItem); NSApp.mainMenu = mainMenu

        menuItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        menuItem?.button?.image = NSImage(systemSymbolName: "pawprint.fill", accessibilityDescription: "PAWilot")
        let menu = NSMenu()
        menu.addItem(withTitle: "Talk to Paw", action: #selector(showChat), keyEquivalent: "")
        menu.addItem(withTitle: "Show / hide kitten", action: #selector(togglePet), keyEquivalent: "")
        menu.addItem(withTitle: "Toggle quiet mode", action: #selector(toggleQuiet), keyEquivalent: "")
        menu.addItem(.separator())
        menu.addItem(withTitle: "Quit PAWilot", action: #selector(quit), keyEquivalent: "q")
        for item in menu.items { item.target = self }
        menuItem?.menu = menu
    }

    func createPet() {
        let screen = NSScreen.screens.first { $0.frame.contains(NSEvent.mouseLocation) } ?? NSScreen.main!
        let visible = screen.visibleFrame
        let size = CGSize(width: 180, height: 180)
        var origin = CGPoint(x: visible.midX + 100, y: visible.minY + 12)
        if let saved = UserDefaults.standard.array(forKey: "petPosition") as? [Double], saved.count == 2 {
            let candidate = CGPoint(x: saved[0], y: saved[1])
            let target = NSScreen.screens.first { $0.visibleFrame.contains(candidate) }?.visibleFrame ?? visible
            origin = PetBehavior.clampedOrigin(candidate, size: size, screen: target)
        }
        let panel = CompanionPanel(contentRect: CGRect(origin: origin, size: size), styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        panel.title = "Paw kitten"
        panel.isOpaque = false; panel.backgroundColor = .clear; panel.hasShadow = false
        panel.level = .floating; panel.hidesOnDeactivate = false
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .ignoresCycle]
        panel.ignoresMouseEvents = true
        let view = KittenSurface(frame: CGRect(origin: .zero, size: size))
        view.clicked = { [weak self] in
            guard let self else { return }
            if self.service.chatVisible { self.hideBubble() } else { self.showChat() }
        }
        view.moved = { [weak self] in self?.positionBubble(); self?.positionNudge() }
        panel.contentView = view
        surface = view; pet = panel
        panel.orderFrontRegardless()
        if KittenAtlas.shared.frames.count != 16 { service.error = "Kitten assets are missing. Rebuild PAWilot from Cursor." }
    }

    private func tick() {
        let now = ProcessInfo.processInfo.systemUptime
        let delta = min(max(now - lastTick, 0), 0.1)
        lastTick = now
        guard let pet, let surface, pet.isVisible, let screen = pet.screen ?? NSScreen.main else { return }
        let pixelHit = surface.opaque(at: NSEvent.mouseLocation)
        // Keep the hover pause stable when a pose change moves the silhouette.
        let hovered = pixelHit || (surface.hovered && pet.frame.contains(NSEvent.mouseLocation))
        surface.hovered = hovered
        pet.ignoresMouseEvents = !(pixelHit || surface.isDragging)
        let nudging = nudge?.isVisible == true
        if nudging && now > nudgeUntil { hideNudge() }
        let attending = service.chatVisible || nudging
        if !attending && !hovered && !surface.isDragging && !service.state.settings.quiet_mode { behaviorTime += delta }
        let selected = PetBehavior().state(elapsed: behaviorTime, quiet: service.state.settings.quiet_mode,
                                            busy: service.busy, hovered: hovered, chatting: attending)
        let paused = selected != .walking || surface.isDragging || attending || hovered
        let origin = motion.advance(origin: pet.frame.origin, size: pet.frame.size, screen: screen.visibleFrame, elapsed: delta, paused: paused)
        if origin != pet.frame.origin { pet.setFrameOrigin(origin) }
        animationTime += delta
        let frame = KittenAtlas.shared.index(state: selected, time: animationTime)
        let changed = surface.state != selected || surface.facingRight != (motion.direction > 0) || lastFrame != frame
        surface.state = selected; surface.facingRight = motion.direction > 0; surface.animationTime = animationTime
        // Sitting and sleeping poses breathe, so they redraw continuously; walking redraws per frame.
        if changed || selected != .walking { surface.needsDisplay = true; lastFrame = frame }
    }

    /// Reports the foreground app and window title to the local service every few seconds.
    private func observeActivity() {
        guard service.ready, service.state.settings.activity_awareness, !reporting,
              let sample = ActivityMonitor.current() else { return }
        reporting = true
        Task {
            let message = await service.reportActivity(sample)
            reporting = false
            if let message, !service.chatVisible { showNudge(message) }
            else if message == nil { offerTitleAccess() }
        }
    }

    /// Once, Paw itself asks to read window titles; the macOS prompt appears only if the user agrees.
    private func offerTitleAccess() {
        guard !ActivityMonitor.canReadTitles, !service.chatVisible, nudge == nil,
              !UserDefaults.standard.bool(forKey: "askedTitleAccess") else { return }
        UserDefaults.standard.set(true, forKey: "askedTitleAccess")
        showNudge("I can see which app you're in, but not what's in it. Let me read window titles so I know what you're watching or working on?",
                  action: "Allow…", seconds: 90) { ActivityMonitor.requestTitleAccess() }
    }

    private func showNudge(_ text: String, action: String = "Talk to Paw", seconds: Double = 30, onAction: (() -> Void)? = nil) {
        guard let pet, pet.isVisible else { return }
        hideNudge()
        let panel = CompanionPanel(contentRect: .zero, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        panel.title = "Paw check-in"
        panel.isOpaque = false; panel.backgroundColor = .clear; panel.hasShadow = true
        panel.level = .floating; panel.hidesOnDeactivate = false
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .ignoresCycle]
        panel.isReleasedWhenClosed = false
        panel.contentView = NSHostingView(rootView: NudgeView(text: text, action: action,
            open: { [weak self] in
                self?.hideNudge()
                if let onAction { onAction() } else { self?.showChat() }
            },
            dismiss: { [weak self] in self?.hideNudge() }))
        nudge = panel
        nudgeUntil = ProcessInfo.processInfo.systemUptime + seconds
        positionNudge()
        pet.addChildWindow(panel, ordered: .above)
        panel.orderFrontRegardless()   // never activates PAWilot or switches Spaces
    }
    private func positionNudge() {
        guard let pet, let nudge, let screen = pet.screen ?? NSScreen.main else { return }
        nudge.setFrame(BubbleGeometry.frame(pet: pet.frame, size: CGSize(width: 270, height: 132), screen: screen.visibleFrame), display: true)
    }
    private func hideNudge() {
        if let nudge { pet?.removeChildWindow(nudge); nudge.orderOut(nil) }
        nudge = nil
    }

    @objc func showChat() {
        guard let pet else { return }
        hideNudge()
        if !pet.isVisible { pet.orderFrontRegardless() }
        if bubble == nil {
            let panel = ChatBubblePanel(contentRect: .zero, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
            panel.title = "Chat with Paw"
            panel.isOpaque = false; panel.backgroundColor = .clear; panel.hasShadow = true
            panel.level = .floating; panel.hidesOnDeactivate = false; panel.isFloatingPanel = true
            panel.becomesKeyOnlyIfNeeded = false
            panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .ignoresCycle]
            panel.isReleasedWhenClosed = false; panel.delegate = self
            panel.contentView = NSHostingView(rootView: BubbleView(service: service) { [weak self] in self?.hideBubble() })
            panel.dismissed = { [weak self] in self?.hideBubble() }
            bubble = panel
        }
        service.chatVisible = true
        positionBubble()
        if let bubble { pet.addChildWindow(bubble, ordered: .above) }
        bubble?.makeKeyAndOrderFront(nil)
        // Nonactivating NSPanel accepts typing without activating another app/Space.
        if service.ready { Task { try? await service.refresh() } }
    }

    private func positionBubble() {
        guard service.chatVisible, let pet, let bubble, let screen = pet.screen ?? NSScreen.main else { return }
        bubble.setFrame(BubbleGeometry.frame(pet: pet.frame, size: CGSize(width: 350, height: 400), screen: screen.visibleFrame), display: true)
    }
    func hideBubble() {
        service.chatVisible = false
        if let bubble { pet?.removeChildWindow(bubble); bubble.orderOut(nil) }
    }
    func windowDidResignKey(_ notification: Notification) {
        if let window = notification.object as? NSWindow, window === bubble { hideBubble() }
    }
    @objc func screenChanged() {
        guard let pet else { return }
        let screen = pet.screen ?? NSScreen.main!
        pet.setFrameOrigin(PetBehavior.clampedOrigin(pet.frame.origin, size: pet.frame.size, screen: screen.visibleFrame))
        positionBubble(); positionNudge()
    }
    @objc func togglePet() { hideBubble(); hideNudge(); if pet?.isVisible == true { pet?.orderOut(nil) } else { pet?.orderFrontRegardless() } }
    @objc func toggleQuiet() {
        var settings = service.state.settings; settings.quiet_mode.toggle()
        Task { await service.mutate("settings", method: "PUT", value: settings) }
    }
    @objc func quit() { NSApp.terminate(nil) }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }
    func applicationWillTerminate(_ notification: Notification) {
        timer?.invalidate(); activityTimer?.invalidate()
        if let outsideMonitor { NSEvent.removeMonitor(outsideMonitor) }
        if let origin = pet?.frame.origin { UserDefaults.standard.set([origin.x, origin.y], forKey: "petPosition") }
        service.stop()
    }
}
