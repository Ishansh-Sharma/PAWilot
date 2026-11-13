import AppKit
import SwiftUI

struct AccountConnections: View {
    @ObservedObject var service: AgentService
    var body: some View {
        DisclosureGroup("Connected accounts") {
            VStack(alignment: .leading, spacing: 10) {
                AccountSettings(service: service, provider: "gmail", title: "Gmail")
                AccountSettings(service: service, provider: "slack", title: "Slack")
                Text("Search in chat with /gmail or /slack followed by keywords. Previews stay in chat history and may be included when you next ask Gemini a question.").font(.caption)
            }
        }
    }
}

private struct AccountSettings: View {
    @ObservedObject var service: AgentService
    let provider: String
    let title: String
    @State private var clientID = ""
    @State private var secret = ""
    @State private var busy = false
    @State private var editing = false
    var body: some View {
        DisclosureGroup(title) {
            VStack(alignment: .leading, spacing: 7) {
                let status = service.state.connections[provider] ?? "Setup required"
                Text(status).font(.caption)
                if status == "Setup required" || editing {
                    Text(provider == "gmail" ? "Enable Gmail API and use a Google Desktop OAuth client." : "Use a Slack app with PKCE, user scope search:read and redirect http://localhost:8766/paw/oauth.").font(.caption)
                    TextField("Client ID", text: $clientID)
                    if provider == "gmail" { SecureField("Desktop client secret", text: $secret) }
                    Button("Save registration") { Task {
                        busy = true; defer { busy = false }
                        if await service.mutate("connections/\(provider)/registration", method: "PUT", value: ["client_id":clientID,"client_secret":secret]) {
                            clientID = ""; secret = ""; editing = false
                        }
                    } }.disabled(clientID.isEmpty || (provider == "gmail" && secret.isEmpty))
                } else if status == "Connected" {
                    Button("Disconnect \(title)") { Task {
                        busy = true; defer { busy = false }
                        await service.delete("connections/\(provider)")
                    } }
                } else {
                    Button("Connect \(title)") { Task {
                        busy = true; defer { busy = false }
                        do {
                            let data = try await service.request("connections/\(provider)/authorize",method:"POST")
                            let response = try JSONDecoder().decode([String:String].self,from:data)
                            guard let raw = response["url"], let url = URL(string:raw),
                                  url.scheme == "https", url.host == (provider == "gmail" ? "accounts.google.com" : "slack.com"),
                                  NSWorkspace.shared.open(url) else { throw ServiceError(message:"Could not open the sign-in page.") }
                            try await service.refresh()
                        } catch { service.error = error.localizedDescription }
                    } }
                    Button("Change registration") { editing = true }
                }
            }.textFieldStyle(.roundedBorder).disabled(busy)
        }.task(id: service.state.connections[provider]) {
            guard service.state.connections[provider] == "Waiting for browser approval" else { return }
            while !Task.isCancelled {
                do { try await Task.sleep(nanoseconds: 2_000_000_000); try await service.refresh() }
                catch { return }
            }
        }.onAppear { Task { try? await service.refresh() } }
    }
}
