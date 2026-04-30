import Combine
import Foundation
import Network
import SwiftUI

struct DropState: Equatable {
    let id: String
    var type: String
    var x: Double
    var direction: Int
}

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
    @Published var drops: [String: DropState] = [:]
    @Published var projectiles: [Int: ProjectileStateModel] = [:]
    @Published var brokenTiles: Set<String> = []

    private var tcp: TCPClient?
    private let udp = UDPClient()
    private var udpStateTimer: Timer?
    private var roomRefreshTimer: Timer?
    private var currentHeading: Int8 = 1
    private var movingLeft = false
    private var movingRight = false
    private var localUdpClientId: Int?
    private var clientIdToUsername: [Int: String] = [:]
    private var pendingProjectilePackets: [Int: ProjectileStateModel] = [:]
    private var remoteLastUdpAt: [Int: TimeInterval] = [:]
    private let snapshotSuppressionWindow: TimeInterval = 0.35
    private var offlineDemoMode = false
    private var offlineProjectileCounter = 0

    init() {
        udp.onPacket = { [weak self] msgType, clientId, _, _, payload in
            Task { @MainActor in
                self?.handleUDP(msgType: msgType, clientId: clientId, payload: payload)
            }
        }
        setupOfflineDemoIfNeeded()
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
        startLobbyAutoRefresh()
        screen = .lobby
    }

    func shutdown() {
        stopGameplayLoop()
        stopLobbyAutoRefresh()
        tcp?.send(json: ["type": "leave_room"])
        tcp?.disconnect()
        udp.close()
    }

    func setMove(left: Bool? = nil, right: Bool? = nil) {
        if let left { movingLeft = left }
        if let right { movingRight = right }
    }

    func fire() {
        if offlineDemoMode {
            offlineProjectileCounter = (offlineProjectileCounter + 1) & 0xFFFF
            let speed = 5.6
            let direction = currentHeading >= 0 ? 1.0 : -1.0
            let projectile = ProjectileStateModel(
                projectileId: offlineProjectileCounter,
                x: localPlayer.x + 14 * direction,
                y: localPlayer.y + 10,
                vx: speed * direction,
                vy: speed * 0.12,
                flags: GameProtocol.projectileFlagSpawn,
                ownerClientId: localClientIdentifier()
            )
            projectiles[projectile.projectileId] = projectile
            return
        }
        udp.sendActionFire(directionRight: currentHeading >= 0)
    }

    func currentInput() -> (left: Bool, right: Bool) {
        (movingLeft, movingRight)
    }

    func localClientIdentifier() -> Int {
        localUdpClientId ?? 0
    }

    func updateLocalPlayerFromScene(_ state: PlayerState) {
        localPlayer = state
        currentHeading = state.heading
    }

    func sceneDidCollectDrop(dropId: String) {
        tcp?.send(json: ["type": "drop_collected", "drop_id": dropId])
        drops.removeValue(forKey: dropId)
    }

    func sceneDidBreakTile(x: Int, y: Int) {
        let key = "\(x):\(y)"
        guard !brokenTiles.contains(key) else { return }
        brokenTiles.insert(key)
        tcp?.send(json: ["type": "tile_break", "x": x, "y": y])
    }

    func sceneDidHitRemote(clientId: Int) {
        guard let target = clientIdToUsername[clientId] else { return }
        tcp?.send(json: ["type": "player_hit", "target": target, "damage": 5])
    }

    func sceneDidUpdateProjectile(_ projectile: ProjectileStateModel) {
        pendingProjectilePackets[projectile.projectileId] = projectile
    }

    func sceneDidDespawnProjectile(id: Int, lastKnown: ProjectileStateModel?) {
        guard var projectile = lastKnown else { return }
        projectile.flags = GameProtocol.projectileFlagDespawn
        pendingProjectilePackets[id] = projectile
        projectiles.removeValue(forKey: id)
    }

    private func handleTCP(message: [String: Any]) {
        let type = message["type"] as? String ?? ""
        switch type {
        case "login_ok":
            statusText = "登录成功"
            screen = .lobby
            startLobbyAutoRefresh()
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
            parseRoomReadyPlayers(message)
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
        case "spawn_drop":
            handleSpawnDrop(message)
        case "drop_collected":
            if let dropId = message["drop_id"] as? String {
                drops.removeValue(forKey: dropId)
            }
        case "drop_direction":
            if
                let dropId = message["drop_id"] as? String,
                var drop = drops[dropId]
            {
                drop.direction = (message["direction"] as? Int) ?? drop.direction
                drops[dropId] = drop
            }
        case "tile_break":
            if
                let x = message["x"] as? Int,
                let y = message["y"] as? Int
            {
                brokenTiles.insert("\(x):\(y)")
            }
        default:
            break
        }
    }

    private func handleUDP(msgType: UInt8, clientId: UInt8, payload: Data) {
        switch msgType {
        case GameProtocol.msgPlayerState:
            guard let state = GameProtocol.unpackPlayerState(payload) else { return }
            if Int(clientId) != localUdpClientId {
                let id = Int(clientId)
                remotePlayers[id] = state
                remoteLastUdpAt[id] = ProcessInfo.processInfo.systemUptime
            }
        case GameProtocol.msgProjectileState:
            guard let projectile = GameProtocol.unpackProjectileState(payload, ownerClientId: Int(clientId)) else { return }
            let isDespawn = (projectile.flags & GameProtocol.projectileFlagDespawn) != 0
            if isDespawn {
                projectiles.removeValue(forKey: projectile.projectileId)
            } else {
                projectiles[projectile.projectileId] = projectile
            }
        default:
            break
        }
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
        stopLobbyAutoRefresh()
        screen = .game
        localPlayer = PlayerState()
        remotePlayers = [:]
        remoteLastUdpAt = [:]
        drops = [:]
        projectiles = [:]
        brokenTiles = []
        pendingProjectilePackets = [:]

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
        localUdpClientId = udpInfo.clientId
        udp.open(host: udpHost, port: udpPort, token: udpInfo.token, clientId: udpInfo.clientId)
        startGameplayLoop()
    }

    private func applySnapshot(_ message: [String: Any]) {
        guard let players = message["players"] as? [[String: Any]] else { return }
        let now = ProcessInfo.processInfo.systemUptime
        for p in players {
            guard let clientId = p["client_id"] as? Int else { continue }
            if let username = p["username"] as? String {
                clientIdToUsername[clientId] = username
            }
            let x = p["x"] as? Double ?? 0
            let y = p["y"] as? Double ?? 0
            let vx = p["vx"] as? Double ?? 0
            let vy = p["vy"] as? Double ?? 0
            let flags = UInt8((p["flags"] as? Int) ?? 0)
            let heading = Int8((p["heading"] as? Int) ?? 1)
            if clientId != localUdpClientId {
                if let lastUdpAt = remoteLastUdpAt[clientId], now - lastUdpAt < snapshotSuppressionWindow {
                    // UDP is fresher for movement; avoid air-time flicker from stale TCP snapshots.
                    continue
                }
                remotePlayers[clientId] = PlayerState(x: x, y: y, vx: vx, vy: vy, flags: flags, heading: heading)
            }
        }
    }

    private func startGameplayLoop() {
        stopGameplayLoop()
        udpStateTimer = Timer.scheduledTimer(withTimeInterval: 1.0 / 30.0, repeats: true) { [weak self] _ in
            guard let self else { return }
            guard !self.offlineDemoMode else { return }
            self.udp.sendPlayerState(self.localPlayer)
            for projectile in self.pendingProjectilePackets.values {
                self.udp.sendProjectileState(projectile)
            }
            self.pendingProjectilePackets.removeAll()
        }
    }

    private func stopGameplayLoop() {
        udpStateTimer?.invalidate()
        udpStateTimer = nil
    }

    private func handleSpawnDrop(_ message: [String: Any]) {
        guard let id = message["drop_id"] as? String else { return }
        let dropType = (message["drop_type"] as? String) ?? "coin"
        let x = (message["x"] as? Double) ?? 48
        let direction = (message["direction"] as? Int) ?? 1
        drops[id] = DropState(id: id, type: dropType, x: x, direction: direction)
    }

    private func parseRoomReadyPlayers(_ message: [String: Any]) {
        clientIdToUsername = [:]
        guard let players = message["players"] as? [[String: Any]] else { return }
        for p in players {
            guard
                let username = p["username"] as? String,
                let clientId = p["client_id"] as? Int
            else { continue }
            clientIdToUsername[clientId] = username
        }
    }

    private func startLobbyAutoRefresh() {
        stopLobbyAutoRefresh()
        roomRefreshTimer = Timer.scheduledTimer(withTimeInterval: 2.0, repeats: true) { [weak self] _ in
            guard let self else { return }
            guard self.screen == .lobby else { return }
            self.requestRooms()
        }
    }

    private func stopLobbyAutoRefresh() {
        roomRefreshTimer?.invalidate()
        roomRefreshTimer = nil
    }

    private func setupOfflineDemoIfNeeded() {
        guard offlineDemoMode else { return }
        screen = .game
        statusText = "离线演示模式"
        localUdpClientId = 0
        localPlayer = PlayerState(x: 48, y: 80, vx: 0, vy: 0, flags: 1, heading: 1)
        drops = [
            "demo_coin_1": DropState(id: "demo_coin_1", type: "coin", x: 420, direction: 0),
            "demo_mushroom_1": DropState(id: "demo_mushroom_1", type: "mushroom", x: 680, direction: 1),
        ]
        projectiles = [:]
        brokenTiles = []
        startGameplayLoop()
    }
}
