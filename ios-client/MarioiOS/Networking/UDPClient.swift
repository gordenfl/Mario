import Foundation
import Network

final class UDPClient {
    private var connection: NWConnection?
    private let queue = DispatchQueue(label: "mario.ios.udp")
    private var token: String = ""
    private var clientId: UInt8 = 0
    private var seq: UInt16 = 0
    private var connected = false

    var onPacket: ((UInt8, UInt8, UInt16, UInt32, Data) -> Void)?

    func open(host: String, port: UInt16, token: String, clientId: Int) {
        close()
        self.token = token
        self.clientId = UInt8(clientId & 0xFF)
        seq = 0
        connected = false

        let nwHost = NWEndpoint.Host(host)
        let nwPort = NWEndpoint.Port(rawValue: port) ?? 8765
        let conn = NWConnection(host: nwHost, port: nwPort, using: .udp)
        connection = conn
        conn.stateUpdateHandler = { [weak self] state in
            guard let self else { return }
            if case .ready = state {
                self.sendHello()
                self.receiveLoop()
            }
        }
        conn.start(queue: queue)
    }

    func close() {
        connection?.cancel()
        connection = nil
        connected = false
    }

    func sendPlayerState(_ state: PlayerState) {
        let payload = GameProtocol.packPlayerState(state)
        send(msgType: GameProtocol.msgPlayerState, payload: payload)
    }

    func sendActionFire(directionRight: Bool) {
        let payload = GameProtocol.packAction(
            actionType: GameProtocol.actionFire,
            param: directionRight ? 1 : 0,
            extra: 0
        )
        send(msgType: GameProtocol.msgAction, payload: payload)
    }

    private func sendHello() {
        let payload = token.data(using: .utf8) ?? Data()
        send(msgType: GameProtocol.msgHello, payload: payload)
    }

    private func send(msgType: UInt8, payload: Data) {
        guard let connection else { return }
        let packet = GameProtocol.packMessage(
            msgType: msgType,
            clientId: clientId,
            seq: seq,
            timestamp: GameProtocol.currentMillis(),
            payload: payload
        )
        seq &+= 1
        connection.send(content: packet, completion: .contentProcessed { _ in })
    }

    private func receiveLoop() {
        connection?.receiveMessage { [weak self] content, _, _, _ in
            guard let self else { return }
            if let content, let packet = GameProtocol.unpackMessage(content) {
                if packet.msgType == GameProtocol.msgHelloAck {
                    self.connected = true
                }
                self.onPacket?(packet.msgType, packet.clientId, packet.seq, packet.timestamp, packet.payload)
            }
            self.receiveLoop()
        }
    }
}
