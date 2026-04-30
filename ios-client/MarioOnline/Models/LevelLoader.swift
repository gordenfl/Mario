import Foundation

enum LevelLoader {
    static func loadLevel(named name: String) -> TileMapData {
        guard
            let url =
                Bundle.main.url(forResource: name, withExtension: "json")
                ?? Bundle.main.url(forResource: name, withExtension: "json", subdirectory: "levels"),
            let data = try? Data(contentsOf: url),
            let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            let level = json["level"] as? [String: Any]
        else {
            return fallbackLevel()
        }

        let length = (json["length"] as? Int) ?? 60
        var solid = Set<String>()
        var breakable = Set<String>()
        var kinds: [String: TileKind] = [:]
        var clouds: [(Int, Int)] = []
        var bushes: [(Int, Int)] = []
        var levelBottomY = 15

        if let layers = level["layers"] as? [String: Any],
           let ground = layers["ground"] as? [String: Any],
           let xRange = ground["x"] as? [Int], xRange.count == 2,
           let yRange = ground["y"] as? [Int], yRange.count == 2 {
            levelBottomY = max(levelBottomY, yRange[1] - 1)
            for x in xRange[0]..<xRange[1] {
                for y in yRange[0]..<yRange[1] {
                    let key = "\(x):\(y)"
                    solid.insert(key)
                    kinds[key] = .ground
                }
            }
        }

        if let objects = level["objects"] as? [String: Any] {
            addTiles(from: objects["bricks"], into: &solid, kind: .brick, kinds: &kinds)
            collectTiles(from: objects["bricks"], into: &breakable)
            addTiles(from: objects["ground"], into: &solid, kind: .ground, kinds: &kinds)
            addPipeTiles(from: objects["pipe"], into: &solid, kinds: &kinds, levelBottomY: levelBottomY)
            clouds = collectPoints(from: objects["cloud"])
            bushes = collectPoints(from: objects["bush"])
        }

        let tiles = solid.compactMap { key -> (Int, Int)? in
            let parts = key.split(separator: ":")
            guard parts.count == 2, let x = Int(parts[0]), let y = Int(parts[1]) else { return nil }
            return (x, y)
        }
        return TileMapData(
            length: length,
            solidTiles: tiles,
            breakableTiles: breakable,
            tileKinds: kinds,
            cloudTiles: clouds,
            bushTiles: bushes
        )
    }

    private static func addTiles(from value: Any?, into set: inout Set<String>, kind: TileKind, kinds: inout [String: TileKind]) {
        guard let rows = value as? [[Any]] else { return }
        for row in rows {
            guard row.count >= 2, let x = row[0] as? Int, let y = row[1] as? Int else { continue }
            let key = "\(x):\(y)"
            set.insert(key)
            kinds[key] = kind
        }
    }

    private static func collectTiles(from value: Any?, into set: inout Set<String>) {
        guard let rows = value as? [[Any]] else { return }
        for row in rows {
            guard row.count >= 2, let x = row[0] as? Int, let y = row[1] as? Int else { continue }
            set.insert("\(x):\(y)")
        }
    }

    private static func collectPoints(from value: Any?) -> [(Int, Int)] {
        guard let rows = value as? [[Any]] else { return [] }
        var points: [(Int, Int)] = []
        for row in rows {
            guard row.count >= 2, let x = row[0] as? Int, let y = row[1] as? Int else { continue }
            points.append((x, y))
        }
        return points
    }

    private static func addPipeTiles(
        from value: Any?,
        into set: inout Set<String>,
        kinds: inout [String: TileKind],
        levelBottomY: Int
    ) {
        guard let rows = value as? [[Any]] else { return }
        for row in rows {
            guard
                row.count >= 3,
                let x = row[0] as? Int,
                let topY = row[1] as? Int,
                let height = row[2] as? Int
            else { continue }
            // Match PC logic (Level.addPipeSprite): pipe body extends well below
            // declared height, effectively reaching the visible ground.
            let declaredBottomY = topY + max(height, 1) - 1
            let pipeBottomY = max(declaredBottomY, levelBottomY)
            for y in topY...pipeBottomY {
                let k1 = "\(x):\(y)"
                let k2 = "\(x + 1):\(y)"
                set.insert(k1)
                set.insert(k2)
                kinds[k1] = .pipe
                kinds[k2] = .pipe
            }
        }
    }

    private static func fallbackLevel() -> TileMapData {
        var tiles: [(Int, Int)] = []
        for x in 0..<60 {
            for y in 14..<16 {
                tiles.append((x, y))
            }
        }
        var kinds: [String: TileKind] = [:]
        for (x, y) in tiles {
            kinds["\(x):\(y)"] = .ground
        }
        return TileMapData(length: 60, solidTiles: tiles, breakableTiles: [], tileKinds: kinds, cloudTiles: [], bushTiles: [])
    }
}
