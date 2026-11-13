import AppKit
import ApplicationServices
import SwiftUI
import PawCore

/// Observes which app and window are in front. Observation only: Paw never controls other apps.
@MainActor
enum ActivityMonitor {
    struct Sample: Encodable, Equatable {
        var app: String
        var bundle_id: String
        var title: String
    }

    /// Apps whose window titles can reveal secrets are recorded by name only.
    private static let titleless: Set<String> = [
        "com.apple.keychainaccess", "com.apple.Passwords", "com.1password.1password",
        "com.agilebits.onepassword7", "com.bitwarden.desktop", "com.lastpass.LastPass"
    ]

    static var canReadTitles: Bool { AXIsProcessTrusted() }

    /// Shows the system Accessibility prompt. Called only from an explicit button in Settings.
    static func requestTitleAccess() {
        let key = kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String
        _ = AXIsProcessTrustedWithOptions([key: true] as CFDictionary)
    }

    static func current() -> Sample? {
        if CGDisplayIsAsleep(CGMainDisplayID()) != 0 { return nil }
        if let session = CGSessionCopyCurrentDictionary() as? [String: Any],
           (session["CGSSessionScreenIsLocked"] as? NSNumber)?.boolValue == true { return nil }
        guard let app = NSWorkspace.shared.frontmostApplication,
              app.processIdentifier != ProcessInfo.processInfo.processIdentifier else { return nil }
        let bundle = app.bundleIdentifier ?? ""
        let name = ActivityText.clean(app.localizedName ?? bundle, limit: 120)
        guard !name.isEmpty else { return nil }
        var title = ""
        if canReadTitles && !titleless.contains(bundle) {
            let element = AXUIElementCreateApplication(app.processIdentifier)
            AXUIElementSetMessagingTimeout(element, 0.3)
            var window: CFTypeRef?
            if AXUIElementCopyAttributeValue(element, kAXFocusedWindowAttribute as CFString, &window) == .success,
               let window, CFGetTypeID(window) == AXUIElementGetTypeID() {
                var value: CFTypeRef?
                if AXUIElementCopyAttributeValue(window as! AXUIElement, kAXTitleAttribute as CFString, &value) == .success {
                    title = ActivityText.clean(value as? String ?? "", limit: 300)
                }
            }
        }
        return Sample(app: name, bundle_id: String(bundle.prefix(200)), title: title)
    }
}

/// Small speech bubble Paw shows beside itself when it has something to say unprompted.
struct NudgeView: View {
    let text: String
    var action = "Talk to Paw"
    let open: () -> Void
    let dismiss: () -> Void
    private let green = Color(red: 0.28, green: 0.40, blue: 0.32)
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(text).font(.system(size: 12)).lineSpacing(2).lineLimit(5)
                .frame(maxWidth: .infinity, alignment: .leading)
            HStack {
                Button(action, action: open).buttonStyle(.borderedProminent)
                Button("Not now", action: dismiss).buttonStyle(.bordered)
            }.controlSize(.small)
        }
        .padding(12).frame(width: 270, height: 132, alignment: .topLeading)
        .background(Color(red: 0.985, green: 0.98, blue: 0.965), in: RoundedRectangle(cornerRadius: 15))
        .overlay(RoundedRectangle(cornerRadius: 15).strokeBorder(green.opacity(0.25)))
        .foregroundStyle(Color(red: 0.20, green: 0.27, blue: 0.24))
        .tint(green).preferredColorScheme(.light)
        .accessibilityElement(children: .contain).accessibilityLabel("Paw check-in")
    }
}
