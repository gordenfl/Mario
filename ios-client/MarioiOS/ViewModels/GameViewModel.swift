import Combine
import Foundation
import Network
import SwiftUI

@MainActor
final class GameViewModel: ObservableObject {
    enum Screen {
        case login
        case lobby
        case game
    }

    @Published var screen: Screen = .login
    @Published var host: String = "127.0.0.1"
    @Published var portText: String = "8765"
    @Published var username: String = ""
    @Published var statusText: String = "请输入用户名并连接服务器"
    @Published var rooms: [RoomInfo] = []
    @Published var localPlayer = PlayerState()
    @Published var remotePlayers: [Int: PlayerState] = [:]

    private var tcp: TCPClient?
    private let udp = UDPClient()
    private var udpStateTimer: Timer?
    private var moveTimer: Timer?
    private var currentHeading: Int8 = 1
    private var movingLeft = false
    private var movingRight = false

    init() {
        udp.onPacket = { [weak self] msgType, clientId, _, _, payload in
            Task { @MainActor in
                self?.handleUDP(msgType: msgType, clientId: clientId, payload: payload)
            }
        }
    }

    func connectAndLogin() {
        let trimmedName = username.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedName.isEmpty else {
            statusText = "用户名不能为空"
            return
        }
        guard let port = UInt16(portText) else {
            statusText = "端口格式错误"
            return
        }
        username = trimmedName
        statusText = "正在连接..."

        let client = TCPClient(host: host, port: port)
        tcp = client
        client.onStateChange = { [weak self] state in
            Task { @MainActor in
                switch state {
                case .failed(let error):
                    self?.statusText = "TCP 连接失败: \(error.localizedDescription)"
                default:
                    break
                }
            }
        }
        client.onMessage = { [weak self] message in
            Task { @MainActor in
                self?.handleTCP(message: message)
            }
        }
        client.connect()
        client.send(json: ["type": "login", "username": trimmedName])
    }

    func requestRooms() {
        tcp?.send(json: ["type": "list_rooms"])
    }

    func createRoom() {
        tcp?.send(json: ["type": "create_room"])
        statusText = "正在创建房间..."
    }

    func joinRoom(_ roomId: String) {
        tcp?.send(json: ["type": "join_room", "room_id": roomId])
        statusText = "正在加入房间 \(roomId)..."
    }

    func leaveRoom() {
        tcp?.send(json: ["type": "leave_room"])
        stopGameplayLoop()
        screen = .lobby
    }

    func shutdown() {
        stopGameplayLoop()
        tcp?.send(json: ["type": "leave_room"])
        tcp?.disconnect()
        udp.close()
    }

    func setMove(left: Bool? = nil, right: Bool? = nil) {
        if let left { movingLeft = left }
        if let right { movingRight = right }
    }

    func fire() {
        udp.sendActionFire(directionRight: currentHeading >= 0)
    }

    private func handleTCP(message: [String: Any]) {
        let type = message["type"] as? String ?? ""
        switch type {
        case "login_ok":
            statusText = "登录成功"
            screen = .lobby
            requestRooms()
        case "rooms":
            decodeRooms(message)
            statusText = "房间列表已更新"
        case "room_created":
            if let roomId = message["room_id"] as? String {
                statusText = "房间 \(roomId) 已创建，等待对手"
            }
        case "room_joined":
            if let roomId = message["room_id"] as? String {
                statusText = "已加入房间 \(roomId)，等待开始"
            }
        case "room_waiting":
            statusText = "等待另一名玩家加入..."
        case "room_ready":
            statusText = "房间就绪，进入游戏"
            enterGame(with: message)
        case "state_snapshot":
            applySnapshot(message)
        case "error":
            let text = message["message"] as? String ?? "未知错误"
            statusText = "服务器错误: \(text)"
        case "game_over":
            let winner = message["winner"] as? String ?? "unknown"
            statusText = "对局结束，获胜者: \(winner)"
            stopGameplayLoop()
        default:
            break
        }
    }

    private func handleUDP(msgType: UInt8, clientId: UInt8, payload: Data) {
        guard msgType == GameProtocol.msgPlayerState else { return }
        guard let state = GameProtocol.unpackPlayerState(payload) else { return }
        remotePlayers[Int(clientId)] = state
    }

    private func decodeRooms(_ message: [String: Any]) {
        guard let raw = message["rooms"] else {
            rooms = []
            return
        }
        guard
            let data = try? JSONSerialization.data(withJSONObject: raw, options: []),
            let decoded = try? JSONDecoder().decode([RoomInfo].self, from: data)
        else {
            rooms = []
            return
        }
        rooms = decoded
    }

    private func enterGame(with roomReady: [String: Any]) {
        screen = .game
        localPlayer = PlayerState()
        remotePlayers = [:]

        guard
            let udpAny = roomReady["udp"],
            let udpData = try? JSONSerialization.data(withJSONObject: udpAny, options: []),
            let udpInfo = try? JSONDecoder().decode(UDPBootstrap.self, from: udpData)
        else {
            statusText = "UDP 参数解析失败"
            return
        }

        let udpHost = (udpInfo.host?.isEmpty == false ? udpInfo.host! : host)
        let udpPort = UInt16(clamping: udpInfo.port ?? Int(portText) ?? 8765)
        udp.open(host: udpHost, port: udpPort, token: udpInfo.token, clientId: udpInfo.clientId)
        startGameplayLoop()
    }

    private func applySnapshot(_ message: [String: Any]) {
        guard let players = message["players"] as? [[String: Any]] else { return }
        for p in players {
            guard let clientId = p["client_id"] as? Int else { continue }
            let x = p["x"] as? Double ?? 0
            let y = p["y"] as? Double ?? 0
            let vx = p["vx"] as? Double ?? 0
            let vy = p["vy"] as? Double ?? 0
            let flags = UInt8((p["flags"] as? Int) ?? 0)
            let heading = Int8((p["heading"] as? Int) ?? 1)
            remotePlayers[clientId] = PlayerState(x: x, y: y, vx: vx, vy: vy, flags: flags, heading: heading)
        }
    }

    private func startGameplayLoop() {
        stopGameplayLoop()
        moveTimer = Timer.scheduledTimer(withTimeInterval: 1.0 / 60.0, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.updateMovement() }
        }
        udpStateTimer = Timer.scheduledTimer(withTimeInterval: 1.0 / 30.0, repeats: true) { [weak self] _ in
            guard let self else { return }
            self.udp.sendPlayerState(self.localPlayer)
        }
    }

    private func stopGameplayLoop() {
        udpStateTimer?.invalidate()
        udpStateTimer = nil
        moveTimer?.invalidate()
        moveTimer = nil
    }

    private func updateMovement() {
        var vx = 0.0
        if movingLeft {
            vx -= 2.8
            currentHeading = -1
        }
        if movingRight {
            vx += 2.8
            currentHeading = 1
        }
        localPlayer.vx = vx
        localPlayer.heading = currentHeading
        localPlayer.x += vx
        localPlayer.x = min(max(localPlayer.x, 16), 1500)
    }
}
