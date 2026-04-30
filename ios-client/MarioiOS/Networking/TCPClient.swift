import Foundation
import Network

final class TCPClient {
    private let host: NWEndpoint.Host
    private let port: NWEndpoint.Port
    private var connection: NWConnection?
    private var recvBuffer = Data()
    private let queue = DispatchQueue(label: "mario.ios.tcp")

    var onMessage: (([String: Any]) -> Void)?
    var onStateChange: ((NWConnection.State) -> Void)?

    init(host: String, port: UInt16) {
        self.host = NWEndpoint.Host(host)
        self.port = NWEndpoint.Port(rawValue: port) ?? 8765
    }

    func connect() {
        let conn = NWConnection(host: host, port: port, using: .tcp)
        connection = conn
        conn.stateUpdateHandler = { [weak self] state in
            self?.onStateChange?(state)
            if case .ready = state {
                self?.receiveLoop()
            }
        }
        conn.start(queue: queue)
    }

    func disconnect() {
        connection?.cancel()
        connection = nil
    }

    func send(json: [String: Any]) {
        guard let conn = connection else { return }
        guard
            let payload = try? JSONSerialization.data(withJSONObject: json, options: []),
            var line = String(data: payload, encoding: .utf8)
        else { return }
        line.append("\n")
        conn.send(content: line.data(using: .utf8), completion: .contentProcessed { _ in })
    }

    private func receiveLoop() {
        connection?.receive(minimumIncompleteLength: 1, maximumLength: 4096) { [weak self] data, _, isComplete, error in
            guard let self else { return }
            if let data, !data.isEmpty {
                self.recvBuffer.append(data)
                self.drainJSONLines()
            }
            if isComplete || error != nil {
                self.disconnect()
                return
            }
            self.receiveLoop()
        }
    }

    private func drainJSONLines() {
        let newline = UInt8(ascii: "\n")
        while let index = recvBuffer.firstIndex(of: newline) {
            let lineData = recvBuffer.prefix(upTo: index)
            recvBuffer.removeSubrange(...index)
            guard !lineData.isEmpty else { continue }
            guard
                let obj = try? JSONSerialization.jsonObject(with: lineData, options: []),
                let dict = obj as? [String: Any]
            else { continue }
            onMessage?(dict)
        }
    }
}
