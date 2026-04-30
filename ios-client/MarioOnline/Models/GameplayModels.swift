import Foundation

enum TileKind: String {
    case ground
    case brick
    case pipe
}

struct TileMapData {
    let length: Int
    let solidTiles: [(x: Int, y: Int)]
    let breakableTiles: Set<String>
    let tileKinds: [String: TileKind]
    let cloudTiles: [(x: Int, y: Int)]
    let bushTiles: [(x: Int, y: Int)]
}
