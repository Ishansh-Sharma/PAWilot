import Foundation
import Security

@MainActor
final class AgentService: ObservableObject {
    @Published var state = AppState()
    @Published var ready = false
    @Published var busy = false
    @Published var error: String?
    @Published var status = "Starting your local companion…"
    @Published var chatVisible = false
    @Published var conversationRequest = 0
    @Published var lastMode = "offline"
    private var process: Process?
    private var input: Pipe?
    private var output: Pipe?
    private var token = ""
    private var baseURL: URL?
    private let session: URLSession = {
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = 130
        config.timeoutIntervalForResource = 140
        config.connectionProxyDictionary = [:]
        return URLSession(configuration: config)
    }()

    func start() async {
        guard process == nil else { return }
        do {
            let resources = Bundle.main.resourceURL!
            let runtimeURL = resources.appendingPathComponent("runtime.json")
            let config = try JSONDecoder().decode(Runtime.self, from: Data(contentsOf: runtimeURL))
            guard FileManager.default.isExecutableFile(atPath: config.python) else {
                throw ServiceError(message: "Python runtime is missing. Run scripts/setup.sh and scripts/build-app.sh from Cursor.")
            }
            var bytes = [UInt8](repeating: 0, count: 32)
            guard SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes) == errSecSuccess else {
                throw ServiceError(message: "Could not generate a secure session token.")
            }
            token = Data(bytes).base64EncodedString()
            let support = ProcessInfo.processInfo.environment["PAWILOT_DATA_DIR"].map { URL(fileURLWithPath: $0) }
                ?? FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("PAWilot")
            let child = Process()
            child.executableURL = URL(fileURLWithPath: config.python)
            child.arguments = ["-m", "pawilot"]
            child.currentDirectoryURL = resources
            child.environment = ["PATH": "/usr/bin:/bin", "PYTHONPATH": resources.appendingPathComponent("backend").path,
                                 "PYTHONUNBUFFERED": "1", "PYTHONDONTWRITEBYTECODE": "1", "HOME": NSHomeDirectory()]
            let stdin = Pipe(), stdout = Pipe()
            child.standardInput = stdin
            child.standardOutput = stdout
            child.standardError = FileHandle.standardError
            child.terminationHandler = { [weak self] _ in
                guard let owner = self else { return }
                Task { @MainActor [owner] in
                    guard owner.process != nil else { return }
                    owner.ready = false
                    owner.status = "Local service stopped"
                    owner.error = "The local service stopped. Quit and reopen PAWilot to restart it. Your saved records remain on disk."
                }
            }
            try child.run()
            process = child; input = stdin; output = stdout
            var bootstrap = try JSONSerialization.data(withJSONObject: ["token": token, "data_dir": support.path])
            bootstrap.append(0x0A)
            try stdin.fileHandleForWriting.write(contentsOf: bootstrap)
            let handle = stdout.fileHandleForReading
            let data = await Task.detached {
                var collected = Data()
                while !collected.contains(0x0A) && collected.count < 4096 {
                    let chunk = handle.availableData
                    if chunk.isEmpty { break }
                    collected.append(chunk)
                }
                return collected
            }.value
            let startup = try JSONDecoder().decode(Startup.self, from: data)
            guard (1024...65535).contains(startup.port) else { throw ServiceError(message: "Invalid local service port") }
            baseURL = URL(string: "http://127.0.0.1:\(startup.port)")!
            for attempt in 0..<30 {
                do {
                    try await refresh()
                    ready = true
                    status = state.settings.ai_enabled ? "Gemini enabled" : "Offline · stays on this Mac"
                    return
                } catch {
                    if attempt == 29 { throw error }
                    try await Task.sleep(nanoseconds: 200_000_000)
                }
            }
        } catch {
            self.error = error.localizedDescription
            status = "Setup needs attention"
            stop()
        }
    }

    func stop() {
        let child = process
        process = nil
        try? input?.fileHandleForWriting.close()
        if child?.isRunning == true { child?.terminate() }
        input = nil; output = nil; ready = false
    }

    func request(_ path: String, method: String = "GET", body: Data? = nil, query: [URLQueryItem] = []) async throws -> Data {
        guard let baseURL else { throw ServiceError(message: "The local service is still starting.") }
        var components = URLComponents(url: baseURL.appendingPathComponent(path), resolvingAgainstBaseURL: false)!
        if !query.isEmpty { components.queryItems = query }
        var request = URLRequest(url: components.url!)
        request.httpMethod = method
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = body
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            let json = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
            throw ServiceError(message: json?["detail"] as? String ?? "The request could not be completed. Check the entered values.")
        }
        return data
    }

    func refresh() async throws {
        state = try JSONDecoder().decode(AppState.self, from: await request("state"))
        status = state.settings.ai_enabled ? "Gemini enabled" : "Offline · stays on this Mac"
    }

    func send(_ text: String) async {
        guard ready, !busy else { return }
        busy = true; error = nil
        defer { busy = false }
        do {
            let data = try await request("chat", method: "POST", body: JSONEncoder().encode(["text": text]))
            let result = try JSONDecoder().decode(ChatResult.self, from: data)
            lastMode = result.mode
            try await refresh()
        } catch { self.error = error.localizedDescription }
    }

    /// Reports the foreground app/window. Returns Paw's check-in text when it has one.
    func reportActivity(_ sample: ActivityMonitor.Sample) async -> String? {
        guard ready, let body = try? JSONEncoder().encode(sample),
              let data = try? await request("activity", method: "POST", body: body),
              let result = try? JSONDecoder().decode(ActivityResult.self, from: data) else { return nil }
        if result.nudge != nil { try? await refresh() }
        return result.nudge?.message
    }

    @discardableResult
    func mutate<T: Encodable>(_ path: String, method: String, value: T) async -> Bool {
        do {
            _ = try await request(path, method: method, body: JSONEncoder().encode(value))
            try await refresh()
            error = nil
            return true
        } catch { self.error = error.localizedDescription; return false }
    }

    @discardableResult
    func delete(_ path: String) async -> Bool {
        do {
            _ = try await request(path, method: "DELETE")
            try await refresh()
            error = nil
            return true
        } catch { self.error = error.localizedDescription; return false }
    }

    struct Runtime: Decodable { var python: String }
    struct Startup: Decodable { var port: Int }
    struct ChatResult: Decodable { var message: String; var mode: String }
    struct ActivityResult: Decodable {
        struct Nudge: Decodable { var message: String }
        var recorded: Bool
        var nudge: Nudge?
    }
}

