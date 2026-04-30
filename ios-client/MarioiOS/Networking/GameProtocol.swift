import Foundation

enum GameProtocol {
    static let msgHello: UInt8 = 0x00
    static let msgPlayerState: UInt8 = 0x01
    static let msgProjectileState: UInt8 = 0x02
    static let msgAction: UInt8 = 0x03
    static let msgHelloAck: UInt8 = 0x80

    static let actionFire: UInt8 = 1
    static let velocityScale: Double = 100.0

    static func currentMillis() -> UInt32 {
        let millis = UInt64(Date().timeIntervalSince1970 * 1000.0)
        return UInt32(truncatingIfNeeded: millis)
    }

    static func packHeader(msgType: UInt8, clientId: UInt8, seq: UInt16, timestamp: UInt32) -> Data {
        var data = Data()
        data.append(msgType)
        data.append(clientId)
        appendUInt16(seq, to: &data)
        appendUInt32(timestamp, to: &data)
        return data
    }

    static func packMessage(msgType: UInt8, clientId: UInt8, seq: UInt16, timestamp: UInt32, payload: Data = Data()) -> Data {
        packHeader(msgType: msgType, clientId: clientId, seq: seq, timestamp: timestamp) + payload
    }

    static func unpackMessage(_ data: Data) -> (msgType: UInt8, clientId: UInt8, seq: UInt16, timestamp: UInt32, payload: Data)? {
        guard data.count >= 8 else { return nil }
        let msgType = data[0]
        let clientId = data[1]
        let seq = readUInt16(data, at: 2)
        let ts = readUInt32(data, at: 4)
        return (msgType, clientId, seq, ts, data.dropFirst(8))
    }

    static func packPlayerState(_ state: PlayerState) -> Data {
        var data = Data()
        let x = safeInt16(state.x)
        let y = safeInt16(state.y)
        let vx = safeInt16(state.vx * velocityScale)
        let vy = safeInt16(state.vy * velocityScale)
        let heading = state.heading

        appendInt16(x, to: &data)
        appendInt16(y, to: &data)
        appendInt16(vx, to: &data)
        appendInt16(vy, to: &data)
        data.append(state.flags)
        data.append(UInt8(bitPattern: heading))
        return data
    }

    static func unpackPlayerState(_ payload: Data) -> PlayerState? {
        guard payload.count >= 10 else { return nil }
        let x = readInt16(payload, at: 0)
        let y = readInt16(payload, at: 2)
        let vx = readInt16(payload, at: 4)
        let vy = readInt16(payload, at: 6)
        let flags = payload[8]
        let heading = Int8(bitPattern: payload[9])
        return PlayerState(
            x: Double(x),
            y: Double(y),
            vx: Double(vx) / velocityScale,
            vy: Double(vy) / velocityScale,
            flags: flags,
            heading: heading
        )
    }

    static func packAction(actionType: UInt8, param: UInt8 = 0, extra: UInt16 = 0) -> Data {
        var data = Data()
        data.append(actionType)
        data.append(param)
        appendUInt16(extra, to: &data)
        return data
    }


    private static func safeInt16(_ value: Double) -> Int16 {
        let rounded = Int64(value.rounded())
        let minV = Int64(Int16.min)
        let maxV = Int64(Int16.max)
        if rounded < minV { return Int16.min }
        if rounded > maxV { return Int16.max }
        return Int16(rounded)
    }
    private static func appendUInt16(_ value: UInt16, to data: inout Data) {
        data.append(UInt8((value >> 8) & 0xFF))
        data.append(UInt8(value & 0xFF))
    }

    private static func appendUInt32(_ value: UInt32, to data: inout Data) {
        data.append(UInt8((value >> 24) & 0xFF))
        data.append(UInt8((value >> 16) & 0xFF))
        data.append(UInt8((value >> 8) & 0xFF))
        data.append(UInt8(value & 0xFF))
    }

    private static func appendInt16(_ value: Int16, to data: inout Data) {
        appendUInt16(UInt16(bitPattern: value), to: &data)
    }

    private static func readUInt16(_ data: Data, at index: Int) -> UInt16 {
        guard index >= 0, data.count >= index + 2 else { return 0 }
        return data.withUnsafeBytes { raw -> UInt16 in
            guard let base = raw.baseAddress else { return 0 }
            let ptr = base.assumingMemoryBound(to: UInt8.self)
            let high = UInt16(ptr[index])
            let low = UInt16(ptr[index + 1])
            return (high << 8) | low
        }
    }

    private static func readUInt32(_ data: Data, at index: Int) -> UInt32 {
        guard index >= 0, data.count >= index + 4 else { return 0 }
        return data.withUnsafeBytes { raw -> UInt32 in
            guard let base = raw.baseAddress else { return 0 }
            let ptr = base.assumingMemoryBound(to: UInt8.self)
            let b0 = UInt32(ptr[index])
            let b1 = UInt32(ptr[index + 1])
            let b2 = UInt32(ptr[index + 2])
            let b3 = UInt32(ptr[index + 3])
            return (b0 << 24) | (b1 << 16) | (b2 << 8) | b3
        }
    }

    private static func readInt16(_ data: Data, at index: Int) -> Int16 {
        Int16(bitPattern: readUInt16(data, at: index))
    }
}
