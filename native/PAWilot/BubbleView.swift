import SwiftUI

struct BubbleView: View {
    @ObservedObject var service: AgentService
    let dismiss: () -> Void
    @State private var page = "chat"
    @State private var draft = ""
    @FocusState private var typing: Bool
    private let green = Color(red: 0.28, green: 0.40, blue: 0.32)

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 10) {
                Image(systemName: "pawprint.fill").foregroundStyle(green)
                Text("Paw").font(.system(size: 15, weight: .semibold, design: .rounded))
                Spacer()
                Button { page = "chat"; typing = true } label: { Image(systemName: "bubble.left") }.help("Conversation")
                Button { page = "settings" } label: { Image(systemName: "gearshape") }.help("Settings")
                Button(action: dismiss) { Image(systemName: "xmark") }.help("Close bubble")
            }.buttonStyle(.plain).padding(15)
            Divider()
            if let error = service.error {
                Text(error).font(.caption).foregroundStyle(.red).padding(9)
            }
            if page == "chat" { conversation }
            else { BubbleSettings(service: service) }
        }
        .frame(width: 350, height: 400)
        .background(Color(red: 0.985, green: 0.98, blue: 0.965), in: RoundedRectangle(cornerRadius: 19))
        .overlay(RoundedRectangle(cornerRadius: 19).strokeBorder(green.opacity(0.2)))
        .foregroundStyle(Color(red: 0.20, green: 0.27, blue: 0.24))
        .tint(green).preferredColorScheme(.light)
        .onChange(of: service.conversationRequest) { _, _ in page = "chat" }
        .onChange(of: service.chatVisible) { _, visible in
            if visible { page = "chat"; typing = true }
        }
    }

    private var conversation: some View {
        VStack(spacing: 0) {
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(alignment: .leading, spacing: 12) {
                        if service.state.messages.isEmpty {
                            Text("I'm here. What's on your mind?").font(.system(size: 16, weight: .medium, design: .rounded)).padding(.top, 12)
                            Text("Tell me a goal, or ask about your priorities.").font(.callout).foregroundStyle(.secondary)
                        }
                        ForEach(service.state.messages.suffix(20)) { message in
                            VStack(alignment: .leading, spacing: 4) {
                                Text(message.role == "user" ? "You" : "Paw").font(.system(size: 10, weight: .semibold)).foregroundStyle(.secondary)
                                Text(attributedMessage(message.content)).font(.system(size: 12)).lineSpacing(3).textSelection(.enabled)
                            }.padding(10).frame(maxWidth: .infinity, alignment: .leading)
                                .background(message.role == "user" ? green.opacity(0.08) : .white, in: RoundedRectangle(cornerRadius: 10))
                        }
                        ForEach(service.state.actions.filter { $0.status == "pending" }) { action in
                            VStack(alignment: .leading, spacing: 7) {
                                Text("Proposed \(action.payload.kind ?? "change")").font(.caption).foregroundStyle(.secondary)
                                Text(action.payload.title ?? "Review change").font(.system(size: 12, weight: .medium))
                                if let detail = action.payload.detail, !detail.isEmpty { Text(detail).font(.caption).foregroundStyle(.secondary) }
                                if let goalID = action.payload.goal_id {
                                    Text("Goal: " + (service.state.records.first { $0.id == goalID }?.title ?? "Goal no longer available")).font(.caption)
                                }
                                if let minutes = action.payload.effort_minutes { Text("\(minutes) minutes · \(action.payload.priority ?? "normal") priority").font(.caption) }
                                if let due = action.payload.due { Text("Due \(due)").font(.caption) }
                                HStack {
                                    Button("Approve & save") { decide(action, approve: true) }.buttonStyle(.borderedProminent)
                                    Button("Dismiss") { decide(action, approve: false) }.buttonStyle(.bordered)
                                }.controlSize(.small).disabled(service.busy)
                            }.padding(10).frame(maxWidth: .infinity, alignment: .leading)
                                .background(green.opacity(0.09), in: RoundedRectangle(cornerRadius: 10))
                        }
                        if service.busy { HStack { ProgressView().controlSize(.mini); Text("Thinking…").font(.caption) } }
                        Color.clear.frame(height: 1).id("end")
                    }.padding(12)
                }
                .onAppear { proxy.scrollTo("end", anchor: .bottom) }
                .onChange(of: service.state.messages.count) { _, _ in proxy.scrollTo("end", anchor: .bottom) }
                .onChange(of: service.busy) { _, _ in proxy.scrollTo("end", anchor: .bottom) }
            }
            VStack(spacing: 7) {
                HStack(alignment: .bottom) {
                    TextField("Talk to Paw…", text: $draft, axis: .vertical).textFieldStyle(.plain)
                        .font(.system(size: 12)).lineLimit(1...3).focused($typing).onSubmit(send)
                        .accessibilityIdentifier("chat-input")
                    Button(action: send) { Image(systemName: "arrow.up.circle.fill").font(.system(size: 23)).foregroundStyle(green) }
                        .buttonStyle(.plain).accessibilityLabel("Send message").disabled(draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || service.busy || !service.ready)
                }.padding(10).background(.white, in: RoundedRectangle(cornerRadius: 11))
                Text(service.ready ? (service.state.settings.ai_enabled ? "Gemini · review proposed changes" : "Offline · /goal, /task, /remember") : "Starting local service…")
                    .font(.system(size: 9)).foregroundStyle(.secondary)
            }.padding(12)
        }
    }
    private func attributedMessage(_ text: String) -> AttributedString {
        var value = AttributedString(text)
        for line in text.components(separatedBy: "\n") {
            guard let url = URL(string: line), url.scheme == "https",
                  let host = url.host, host == "mail.google.com" || host.hasSuffix(".slack.com"),
                  let range = value.range(of: line) else { continue }
            value[range].link = url
        }
        return value
    }
    func send() {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, service.ready, !service.busy else { return }
        draft = ""; Task { await service.send(text) }
    }
    func decide(_ action: Action, approve: Bool) {
        Task { await service.mutate("actions/\(action.id)/decision", method: "POST", value: ["approve": approve]) }
    }
}

struct BubbleSettings: View {
    @ObservedObject var service: AgentService
    @State private var settings = Preferences()
    @State private var key = ""
    @State private var notice = ""
    @State private var clearing = false
    @State private var working = false
    @State private var titleAccess = ActivityMonitor.canReadTitles
    private let accessPoll = Timer.publish(every: 2, on: .main, in: .common).autoconnect()
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                Text("Settings").font(.headline)
                AccountConnections(service: service)
                Text(service.state.has_api_key ? "Gemini key saved in macOS Keychain" : "Add your Gemini API key to start chatting.").font(.caption)
                SecureField(service.state.has_api_key ? "Replace Gemini API key" : "Gemini API key", text: $key)
                    .textFieldStyle(.roundedBorder).accessibilityIdentifier("gemini-api-key")
                Button("Save & enable Gemini") {
                    Task {
                        working = true; defer { working = false }
                        if await service.mutate("credentials/gemini", method: "PUT", value: ["value": key]) {
                            key = ""; settings.ai_enabled = true
                            notice = "Key saved. Tap Test connection, then return to chat."
                        }
                    }
                }.buttonStyle(.borderedProminent).disabled(key.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || working)
                Text("Gemini receives your messages, saved profile and relevant memories when you chat. Your local records stay on this Mac.")
                    .font(.caption).foregroundStyle(.secondary)
                Toggle("Use Gemini", isOn: $settings.ai_enabled)
                Toggle("Quiet mode", isOn: $settings.quiet_mode)
                Toggle("Notice what I'm working on", isOn: $settings.activity_awareness)
                Toggle("Check in when I drift from my goals", isOn: $settings.nudges_enabled).disabled(!settings.activity_awareness)
                Text("Paw notes the app and window title in front, on this Mac only, for 7 days. With Gemini on, a summary is sent when you chat and when Paw checks in.")
                    .font(.caption).foregroundStyle(.secondary)
                if settings.activity_awareness {
                    if titleAccess {
                        Text("Window titles: allowed").font(.caption)
                    } else {
                        Text("Paw currently sees app names only. Allow Accessibility to read window titles (for example which site or file).").font(.caption)
                        Button("Allow window titles…") { ActivityMonitor.requestTitleAccess() }
                    }
                }
                TextField("Gemini model ID", text: $settings.model).textFieldStyle(.roundedBorder)
                DisclosureGroup("Memory search") {
                    Toggle("Semantic search with Gemini", isOn: $settings.semantic_memory)
                    Text("Optional: send saved record text to Google's embedding model for meaning-based search. Otherwise Paw searches locally by keywords.").font(.caption)
                }
                Button("Save settings") { Task {
                    working = true; defer { working = false }
                    if await service.mutate("settings", method: "PUT", value: settings) { notice = "Settings saved." }
                } }.disabled(working)
                HStack {
                    Button("Test connection") { Task {
                        working = true; notice = "Checking Gemini…"; defer { working = false }
                        if await service.mutate("settings", method: "PUT", value: settings),
                           await service.mutate("credentials/gemini/check", method: "POST", value: [String:String]()) {
                            notice = "Gemini connected. Return to chat and ask about your goals."
                        } else { notice = "Connection test failed. See the error above." }
                    } }.disabled(!service.state.has_api_key || working)
                    if service.state.has_api_key {
                        Button("Remove key") { Task {
                            if await service.delete("credentials/gemini") { settings = service.state.settings; notice = "Key removed. Offline mode enabled." }
                        } }.disabled(working)
                    }
                }
                if working { ProgressView().controlSize(.small) }
                if !notice.isEmpty { Text(notice).font(.caption).textSelection(.enabled) }
                Divider()
                SavedContextSettings(service: service)
                DisclosureGroup("Recent activity (\(service.state.activity.count))") {
                    VStack(alignment: .leading, spacing: 6) {
                        if service.state.activity.isEmpty { Text("Nothing recorded.") }
                        ForEach(service.state.activity) { item in
                            Text(item.title.isEmpty ? item.app : item.app + " — " + item.title).lineLimit(2).textSelection(.enabled)
                        }
                        if !service.state.activity.isEmpty {
                            Button("Clear activity", role: .destructive) { Task { await service.delete("activity") } }
                        }
                    }.font(.caption).frame(maxWidth: .infinity, alignment: .leading)
                }
                DisclosureGroup("Action history") { BubbleActivity(service: service) }
                if clearing {
                    Text("Clear conversation and dismiss pending proposals? Saved context remains.").font(.caption)
                    HStack {
                        Button("Clear", role: .destructive) { Task { await service.delete("history"); clearing = false } }
                        Button("Keep") { clearing = false }
                    }
                } else { Button("Clear conversation…") { clearing = true } }
            }.padding(14).font(.system(size: 12))
        }.onAppear { settings = service.state.settings; titleAccess = ActivityMonitor.canReadTitles }
            .onReceive(accessPoll) { _ in titleAccess = ActivityMonitor.canReadTitles }
    }
}

struct SavedContextSettings: View {
    @ObservedObject var service: AgentService
    @State private var deleting: String?
    @State private var clearingProfile = false
    var body: some View {
        DisclosureGroup("Saved context (\(service.state.records.count) records)") {
            VStack(alignment: .leading, spacing: 10) {
                Text("Loaded locally. Ask Paw about these in chat; no profile form to fill in.").font(.caption).foregroundStyle(.secondary)
                DisclosureGroup("About you") {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(service.state.profile.name).bold()
                        Text(service.state.profile.about)
                        Text(service.state.profile.preferences)
                        Text(service.state.profile.constraints)
                        Text(service.state.profile.timezone)
                        if clearingProfile {
                            Text("Remove the profile summary? Individual saved records remain below.")
                            Button("Remove summary", role: .destructive) { Task {
                                await service.mutate("profile", method: "PUT", value: PersonalProfile()); clearingProfile = false
                            } }
                            Button("Keep summary") { clearingProfile = false }
                        } else { Button("Remove profile summary…") { clearingProfile = true } }
                    }.font(.caption).textSelection(.enabled)
                }
                ForEach(service.state.records) { record in
                    DisclosureGroup(record.title) {
                        VStack(alignment: .leading, spacing: 6) {
                            Text(record.kind.capitalized + " · " + record.status)
                            Text(record.detail).textSelection(.enabled)
                            if let source = sourceLabel(record.source) { Text(source).foregroundStyle(.secondary) }
                            if let due = record.due { Text("Due " + due) }
                            if let minutes = record.effort_minutes { Text("\(minutes) minutes") }
                            Button(record.status == "active" ? (record.kind == "task" ? "Mark done" : "Archive") : "Restore") {
                                var input = record.input; input.status = record.status == "active" ? "done" : "active"
                                Task { await service.mutate("records/\(record.id)", method: "PUT", value: input) }
                            }
                            if deleting == record.id {
                                Text("Permanently remove this saved record?")
                                Button("Delete", role: .destructive) { Task { await service.delete("records/\(record.id)"); deleting = nil } }
                                Button("Keep") { deleting = nil }
                            } else { Button("Remove…") { deleting = record.id } }
                        }.font(.caption).disabled(service.busy)
                    }
                }
            }.padding(.top, 6)
        }
    }
}

struct BubbleActivity: View {
    @ObservedObject var service: AgentService
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if service.state.actions.isEmpty { Text("No actions yet.") }
            ForEach(service.state.actions) { action in
                Text((action.payload.title ?? "Deleted record") + " · " + action.status).textSelection(.enabled)
            }
        }.font(.caption)
    }
}
