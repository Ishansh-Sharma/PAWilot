import Foundation

struct PersonalRecord: Codable, Identifiable, Equatable {
    var id: String
    var kind: String
    var title: String
    var detail: String
    var status: String
    var due: String?
    var created_at: String
    var updated_at: String
    var goal_id: String?
    var priority: String
    var effort_minutes: Int?
    var source: String?

    var input: RecordInput { RecordInput(kind: kind, title: title, detail: detail, status: status, due: due, goal_id: goal_id, priority: priority, effort_minutes: effort_minutes) }
}

struct RecordInput: Codable {
    var kind: String
    var title: String
    var detail: String = ""
    var status: String = "active"
    var due: String? = nil
    var goal_id: String? = nil
    var priority: String = "normal"
    var effort_minutes: Int? = nil
}

struct Message: Codable, Identifiable {
    var id: String
    var role: String
    var content: String
    var created_at: String
}

struct Action: Codable, Identifiable {
    struct Payload: Codable {
        var kind: String?
        var title: String?
        var detail: String?
        var due: String?
        var goal_id: String?
        var priority: String?
        var effort_minutes: Int?
    }
    var id: String
    var type: String
    var payload: Payload
    var status: String
    var result_id: String?
    var created_at: String
}

struct Preferences: Codable {
    var model = "gemini-3.8-flash"
    var ai_enabled = false
    var semantic_memory = false
    var quiet_mode = false
    var briefings_enabled = false
    var activity_awareness = true
    var nudges_enabled = true
}

struct ActivitySession: Codable, Identifiable {
    var id: Int
    var app: String
    var bundle_id: String
    var title: String
    var started_at: String
    var ended_at: String
}

struct AppState: Codable {
    var records: [PersonalRecord] = []
    var messages: [Message] = []
    var actions: [Action] = []
    var settings = Preferences()
    var has_api_key = false
    var connections: [String: String] = [:]
    var profile = PersonalProfile()
    var retrieval = RetrievalStatus()
    var activity: [ActivitySession] = []
}

struct ServiceError: LocalizedError {
    let message: String
    var errorDescription: String? { message }
}


struct PersonalProfile: Codable {
    var name = ""
    var about = ""
    var preferences = ""
    var constraints = ""
    var timezone = ""
}

struct RetrievalStatus: Codable {
    var mode: String?
    var indexed: Int?
    var total: Int?
    var record_ids: [String]?
}

struct ImportCandidate: Codable, Identifiable {
    var id: String
    var kind: String
    var title: String
    var detail: String
    var source: String
}

struct ImportPreview: Decodable {
    struct Stats: Decodable {
        var conversations: Int
        var user_messages: Int
        var skipped_messages: Int
        var unsupported_conversations: Int
        var candidates: Int
    }
    var session_id: String
    var stats: Stats
    var offset: Int
    var candidates: [ImportCandidate]
}

struct ImportSelection: Encodable {
    var candidate_id: String
    var record: RecordInput
}
struct ImportCommit: Encodable {
    var session_id: String
    var selections: [ImportSelection]
}
struct ImportResult: Decodable {
    var created: Int
    var duplicates: Int
}

func sourceLabel(_ source: String?) -> String? {
    guard let source, let data = source.data(using: .utf8),
          let value = try? JSONSerialization.jsonObject(with: data) as? [String: String] else { return nil }
    return "ChatGPT: " + (value["conversation"] ?? "Imported conversation")
}
