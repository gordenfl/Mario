import Foundation

struct RoomInfo: Decodable, Identifiable {
    let roomId: String
    let players: [String]
    let isFull: Bool?

    var id: String { roomId }

    enum CodingKeys: String, CodingKey {
        case roomId = "room_id"
        case players
        case isFull = "is_full"
    }
}

struct RoomReadyPlayer: Decodable {
    let username: String
    let hp: Int?
    let spawn: String?
    let clientId: Int?

    enum CodingKeys: String, CodingKey {
        case username, hp, spawn
        case clientId = "client_id"
    }
}

struct UDPBootstrap: Decodable {
    let port: Int?
    let token: String
    let clientId: Int
    let host: String?

    enum CodingKeys: String, CodingKey {
        case port, token, host
        case clientId = "client_id"
    }
}

struct PlayerState: Equatable {
    var x: Double = 48
    var y: Double = 352
    var vx: Double = 0
    var vy: Double = 0
    var flags: UInt8 = 0
    var heading: Int8 = 1
}
