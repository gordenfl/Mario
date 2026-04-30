import SpriteKit
import UIKit

final class SpriteKitGameScene: SKScene {
    private let tileSize: CGFloat = 32
    private let mapRows = 16
    private let serverCoordinateHeight: CGFloat = 480
    private let remoteRenderYOffset: CGFloat = 24
    private let cloudRenderYOffset: CGFloat = -14
    private let bushRenderYOffset: CGFloat = -10
    private let playerSize = CGSize(width: 26, height: 58)
    private let worldNode = SKNode()
    private let backgroundNode = SKNode()
    private let cameraAnchor = SKCameraNode()
    private let hudNode = SKNode()
    private let hudMarioLabel = SKLabelNode(fontNamed: "Menlo-Bold")
    private let hudScoreLabel = SKLabelNode(fontNamed: "Menlo-Bold")
    private let hudCoinLabel = SKLabelNode(fontNamed: "Menlo-Bold")
    private let hudWorldLabel = SKLabelNode(fontNamed: "Menlo-Bold")
    private let hudWorldValueLabel = SKLabelNode(fontNamed: "Menlo-Bold")
    private let hudTimeLabel = SKLabelNode(fontNamed: "Menlo-Bold")
    private let hudHpLabel = SKLabelNode(fontNamed: "Menlo-Bold")
    private let hudHpBarBg = SKShapeNode(rectOf: CGSize(width: 134, height: 12), cornerRadius: 3)
    private let hudHpBarFill = SKShapeNode(rectOf: CGSize(width: 130, height: 8), cornerRadius: 2)
    private let localPlayer = SKSpriteNode(color: .red, size: CGSize(width: 26, height: 30))
    private var remotePlayers: [Int: SKSpriteNode] = [:]
    private var drops: [String: SKSpriteNode] = [:]
    private var projectiles: [Int: SKSpriteNode] = [:]
    private var projectileStates: [Int: ProjectileStateModel] = [:]
    private var solidTiles: [String: SKSpriteNode] = [:]
    private var breakableTiles: Set<String> = []
    private var tileKinds: [String: TileKind] = [:]
    private var tileSheet: CGImage?
    private var brokenTilesApplied: Set<String> = []
    private var worldWidth: CGFloat = 60 * 32
    private var leftPressed = false
    private var rightPressed = false
    private var heading: Int8 = 1
    private var lastUpdate: TimeInterval = 0
    private var dropDirections: [String: Int] = [:]
    private var localClientId: Int = 0
    private var localAnimTextures: [AnimState: [SKTexture]] = [:]
    private var currentAnimState: AnimState?
    private let animActionKey = "mario_anim"
    private let remoteAnimActionKey = "remote_anim"
    private var fallbackTinted = false
    private var localAnimState: AnimState = .idle
    private var remoteAnimStates: [Int: AnimState] = [:]
    private var remoteFacing: [Int: Int8] = [:]
    private var hitFlashUntil: TimeInterval = 0
    private var jumpQueued = false
    private var jumpBufferFrames = 0

    private enum AnimState {
        case idle
        case run
        case jump
        case fall
    }

    var onLocalState: ((PlayerState) -> Void)?
    var onProjectileUpdate: ((ProjectileStateModel) -> Void)?
    var onProjectileDespawn: ((Int, ProjectileStateModel?) -> Void)?
    var onRemoteHit: ((Int) -> Void)?
    var onDropCollected: ((String) -> Void)?
    var onTileBreak: ((Int, Int) -> Void)?

    override func didMove(to view: SKView) {
        backgroundColor = SKColor(red: 0.45, green: 0.75, blue: 0.98, alpha: 1.0)
        addChild(backgroundNode)
        addChild(worldNode)
        camera = cameraAnchor
        addChild(cameraAnchor)
        setupHud()
        configureAnimationFrames()
        tileSheet = UIImage(named: "tiles")?.cgImage
        buildWorld()
        setupLocalPlayer()
    }

    func setInput(left: Bool, right: Bool) {
        leftPressed = left
        rightPressed = right
    }

    func setLocalClientId(_ id: Int) {
        localClientId = id
    }

    func triggerJump() {
        jumpQueued = true
        jumpBufferFrames = 8
    }

    func syncRemotePlayers(_ states: [Int: PlayerState]) {
        let keys = Set(states.keys)
        for id in remotePlayers.keys where !keys.contains(id) {
            remotePlayers[id]?.removeFromParent()
            remotePlayers.removeValue(forKey: id)
            remoteAnimStates.removeValue(forKey: id)
            remoteFacing.removeValue(forKey: id)
        }
        for (id, state) in states {
            let node = remotePlayers[id] ?? makeRemoteNode(id: id)
            node.position = CGPoint(x: CGFloat(state.x), y: fromServerY(state.y) - remoteRenderYOffset)
            applyRemoteAnimation(for: node, id: id, state: state)
        }
    }

    func syncDrops(_ states: [String: DropState]) {
        let keys = Set(states.keys)
        for id in drops.keys where !keys.contains(id) {
            drops[id]?.removeFromParent()
            drops.removeValue(forKey: id)
            dropDirections.removeValue(forKey: id)
        }
        for (id, drop) in states {
            let node = drops[id] ?? makeDropNode(id: id, type: drop.type)
            node.position.x = drop.x
            dropDirections[id] = drop.direction == 0 ? 1 : drop.direction
        }
    }

    func syncProjectiles(_ states: [Int: ProjectileStateModel]) {
        projectileStates = states
        let keys = Set(states.keys)
        for id in projectiles.keys where !keys.contains(id) {
            projectiles[id]?.removeFromParent()
            projectiles.removeValue(forKey: id)
        }
        for (id, state) in states {
            let node = projectiles[id] ?? makeProjectileNode(id: id)
            node.position = CGPoint(x: CGFloat(state.x), y: fromServerY(state.y))
        }
    }

    func applyBrokenTiles(_ keys: Set<String>) {
        for key in keys where !brokenTilesApplied.contains(key) {
            solidTiles[key]?.removeFromParent()
            solidTiles.removeValue(forKey: key)
            brokenTilesApplied.insert(key)
        }
    }

    override func update(_ currentTime: TimeInterval) {
        let dt = lastUpdate == 0 ? 1.0 / 60.0 : min(max(currentTime - lastUpdate, 1.0 / 120.0), 1.0 / 30.0)
        lastUpdate = currentTime
        applyInput()
        updateProjectiles(delta: dt)
        updateDrops(delta: dt)
        updateCamera()
        updateAnimations(currentTime: currentTime)
        detectDropPickup()
        detectTileBreak()
        detectProjectileHits(currentTime: currentTime)
        publishLocalState()
    }

    private func buildWorld() {
        let level = LevelLoader.loadLevel(named: "Level1-1")
        worldWidth = CGFloat(level.length) * tileSize
        breakableTiles = level.breakableTiles
        tileKinds = level.tileKinds
        buildBackground(level: level)
        for (x, y) in level.solidTiles {
            let kind = tileKinds["\(x):\(y)"] ?? .ground
            let node = makeTileNode(kind: kind, x: x, y: y)
            node.position = tileToWorld(x: x, y: y)
            node.physicsBody = SKPhysicsBody(rectangleOf: node.size)
            node.physicsBody?.isDynamic = false
            node.physicsBody?.friction = 0.8
            node.zPosition = 10
            worldNode.addChild(node)
            solidTiles["\(x):\(y)"] = node
        }
    }

    private func setupLocalPlayer() {
        if let first = localAnimTextures[.idle]?.first {
            localPlayer.texture = first
            localPlayer.size = CGSize(width: first.size().width * 2.0, height: first.size().height * 2.0)
        } else {
            localPlayer.size = playerSize
        }
        localPlayer.position = CGPoint(x: 48, y: tileToWorld(x: 0, y: 11).y)
        localPlayer.physicsBody = SKPhysicsBody(rectangleOf: playerSize)
        localPlayer.physicsBody?.allowsRotation = false
        localPlayer.physicsBody?.restitution = 0
        localPlayer.physicsBody?.friction = 0.3
        localPlayer.physicsBody?.linearDamping = 1.0
        localPlayer.physicsBody?.affectedByGravity = true
        worldNode.addChild(localPlayer)
        physicsWorld.gravity = CGVector(dx: 0, dy: -24)
    }

    private func applyInput() {
        var vx: CGFloat = 0
        if leftPressed {
            vx -= 180
            heading = -1
        }
        if rightPressed {
            vx += 180
            heading = 1
        }
        localPlayer.physicsBody?.velocity.dx = vx
        if jumpQueued || jumpBufferFrames > 0 {
            if isPlayerGrounded() {
                localPlayer.physicsBody?.applyImpulse(CGVector(dx: 0, dy: 40))
                jumpQueued = false
                jumpBufferFrames = 0
            } else {
                jumpBufferFrames = max(0, jumpBufferFrames - 1)
                if jumpBufferFrames == 0 {
                    jumpQueued = false
                }
            }
        }
        let minX = playerSize.width / 2
        let maxX = worldWidth - playerSize.width / 2
        if localPlayer.position.x < minX {
            localPlayer.position.x = minX
        }
        if localPlayer.position.x > maxX {
            localPlayer.position.x = maxX
        }
    }

    private func updateCamera() {
        let half = size.width / 2
        let deadZone: CGFloat = 84
        let targetX = localPlayer.position.x + CGFloat(heading) * deadZone
        let clampedX = min(max(targetX, half), max(half, worldWidth - half))
        let smoothed = cameraAnchor.position.x + (clampedX - cameraAnchor.position.x) * 0.14
        cameraAnchor.position = CGPoint(x: smoothed, y: 185)
    }

    private func publishLocalState() {
        let vy = localPlayer.physicsBody?.velocity.dy ?? 0
        let vx = localPlayer.physicsBody?.velocity.dx ?? 0
        let onGround = abs(vy) < 2.5
        var flags: UInt8 = 0
        if onGround { flags |= 0b0001 }
        if !onGround { flags |= 0b0010 }
        let state = PlayerState(
            x: localPlayer.position.x,
            y: toServerY(localPlayer.position.y),
            vx: vx / 60,
            vy: -(vy / 60),
            flags: flags,
            heading: heading
        )
        hudScoreLabel.text = "MARIO"
        hudCoinLabel.text = "o x\(max(0, Int(localPlayer.position.x) / 120))"
        hudWorldLabel.text = "WORLD"
        hudWorldValueLabel.text = "1-1"
        hudTimeLabel.text = "TIME"
        hudHpLabel.text = "30/30"
        onLocalState?(state)
    }

    private func updateProjectiles(delta: TimeInterval) {
        for (id, node) in projectiles {
            guard var state = projectileStates[id] else { continue }
            state.x += state.vx * Double(60 * delta)
            state.y += state.vy * Double(60 * delta)
            node.position = CGPoint(x: CGFloat(state.x), y: CGFloat(state.y))
            projectileStates[id] = state

            if state.ownerClientId == localClientId {
                var packet = state
                packet.flags = GameProtocol.projectileFlagUpdate
                onProjectileUpdate?(packet)
            }
        }
        for (id, node) in projectiles where node.position.x < 0 || node.position.x > worldWidth {
            despawnProjectile(id: id)
        }
    }

    private func updateDrops(delta: TimeInterval) {
        let speed: CGFloat = 80 * CGFloat(delta)
        for (id, node) in drops {
            let direction = dropDirections[id, default: 1]
            node.position.x += CGFloat(direction) * speed
            if node.position.x < 24 {
                node.position.x = 24
                dropDirections[id] = 1
            }
            if node.position.x > worldWidth - 24 {
                node.position.x = worldWidth - 24
                dropDirections[id] = -1
            }
        }
    }

    private func updateAnimations(currentTime: TimeInterval) {
        let vx = abs(localPlayer.physicsBody?.velocity.dx ?? 0)
        let vy = localPlayer.physicsBody?.velocity.dy ?? 0
        let onGround = abs(vy) < 22
        let movingIntent = leftPressed || rightPressed
        let standingLock = !movingIntent && vx < 18 && abs(vy) < 80
        let nextState: AnimState
        if standingLock {
            nextState = .idle
        } else if !onGround && vy > 90 {
            nextState = .jump
        } else if !onGround && vy < -90 {
            nextState = .fall
        } else if movingIntent && vx > 22 {
            nextState = .run
        } else {
            nextState = .idle
        }
        guard nextState != localAnimState else { return }
        localAnimState = nextState
        applyAnimation(nextState)
        localPlayer.xScale = heading >= 0 ? abs(localPlayer.xScale) : -abs(localPlayer.xScale)
        if currentTime < hitFlashUntil {
            localPlayer.colorBlendFactor = 0.75
            localPlayer.color = .white
        } else {
            localPlayer.colorBlendFactor = 0.0
        }
    }

    private func detectDropPickup() {
        let pickup = CGRect(
            x: localPlayer.position.x - playerSize.width / 2,
            y: localPlayer.position.y - playerSize.height / 2,
            width: playerSize.width,
            height: playerSize.height
        )
        for (id, node) in drops {
            if pickup.intersects(node.frame) {
                onDropCollected?(id)
                node.removeFromParent()
                drops.removeValue(forKey: id)
                dropDirections.removeValue(forKey: id)
            }
        }
    }

    private func detectTileBreak() {
        let vy = localPlayer.physicsBody?.velocity.dy ?? 0
        guard vy > 30 else { return }
        let headX = Int(localPlayer.position.x / tileSize)
        let headY = mapRows - 1 - Int((localPlayer.position.y + playerSize.height / 2 + 4) / tileSize)
        let key = "\(headX):\(headY)"
        guard breakableTiles.contains(key), let node = solidTiles[key] else { return }
        node.removeFromParent()
        solidTiles.removeValue(forKey: key)
        brokenTilesApplied.insert(key)
        onTileBreak?(headX, headY)
    }

    private func detectProjectileHits(currentTime: TimeInterval) {
        let localRect = localPlayer.frame
        for (id, projectile) in projectiles {
            guard let state = projectileStates[id] else { continue }
            if state.ownerClientId != localClientId && projectile.frame.intersects(localRect) {
                hitFlashUntil = currentTime + 0.12
                despawnProjectile(id: id)
                continue
            }
            if state.ownerClientId == localClientId {
                for (remoteId, remoteNode) in remotePlayers where projectile.frame.intersects(remoteNode.frame) {
                    onRemoteHit?(remoteId)
                    despawnProjectile(id: id)
                    break
                }
            }
        }
    }

    private func despawnProjectile(id: Int) {
        let previous = projectileStates[id]
        onProjectileDespawn?(id, previous)
        projectiles[id]?.removeFromParent()
        projectiles.removeValue(forKey: id)
        projectileStates.removeValue(forKey: id)
    }

    private func tileToWorld(x: Int, y: Int) -> CGPoint {
        let worldY = CGFloat(mapRows - y - 1) * tileSize + tileSize / 2
        let worldX = CGFloat(x) * tileSize + tileSize / 2
        return CGPoint(x: worldX, y: worldY)
    }

    private func isPlayerGrounded() -> Bool {
        let footY = localPlayer.position.y - playerSize.height / 2 - 3
        let sampleXs = [
            localPlayer.position.x - playerSize.width * 0.3,
            localPlayer.position.x,
            localPlayer.position.x + playerSize.width * 0.3
        ]
        for x in sampleXs {
            let tx = Int(floor(x / tileSize))
            let ty = mapRows - 1 - Int(floor(footY / tileSize))
            if solidTiles["\(tx):\(ty)"] != nil {
                return true
            }
        }
        return false
    }

    private func makeRemoteNode(id: Int) -> SKSpriteNode {
        let node = SKSpriteNode(texture: localAnimTextures[.idle]?.first, color: .clear, size: localPlayer.size)
        node.name = "remote_\(id)"
        node.colorBlendFactor = 0.0
        node.alpha = 1.0
        node.zPosition = 25
        worldNode.addChild(node)
        remotePlayers[id] = node
        return node
    }

    private func applyRemoteAnimation(for node: SKSpriteNode, id: Int, state: PlayerState) {
        let vx = abs(state.vx * 60)
        let vy = state.vy * 60
        let onGround = (state.flags & 0b0001) != 0 || abs(vy) < 18
        let moving = vx > 20
        let nextState: AnimState
        if !onGround && vy > 70 {
            nextState = .jump
        } else if !onGround && vy < -70 {
            nextState = .fall
        } else if moving {
            nextState = .run
        } else {
            nextState = .idle
        }

        // Avoid left-right flicker while idle: only change facing on meaningful movement
        // or when we receive a stable non-zero heading.
        var facing = remoteFacing[id] ?? 1
        if moving {
            if state.vx > 0.02 {
                facing = 1
            } else if state.vx < -0.02 {
                facing = -1
            } else if state.heading != 0 {
                facing = state.heading > 0 ? 1 : -1
            }
        } else if state.heading != 0 && abs(state.vx) > 0.005 {
            facing = state.heading > 0 ? 1 : -1
        }
        remoteFacing[id] = facing
        node.xScale = facing >= 0 ? abs(node.xScale) : -abs(node.xScale)

        guard remoteAnimStates[id] != nextState else { return }
        remoteAnimStates[id] = nextState
        node.removeAction(forKey: remoteAnimActionKey)

        guard let textures = localAnimTextures[nextState], !textures.isEmpty else { return }
        if textures.count == 1 {
            node.texture = textures[0]
            return
        }

        let frameTime: TimeInterval = nextState == .run ? 0.14 : 0.16
        let action = SKAction.repeatForever(.animate(with: textures, timePerFrame: frameTime, resize: false, restore: true))
        node.run(action, withKey: remoteAnimActionKey)
    }

    private func makeProjectileNode(id: Int) -> SKSpriteNode {
        let node = SKSpriteNode(color: .orange, size: CGSize(width: 10, height: 10))
        node.name = "proj_\(id)"
        node.zPosition = 30
        worldNode.addChild(node)
        projectiles[id] = node
        return node
    }

    private func makeDropNode(id: String, type: String) -> SKSpriteNode {
        let color: SKColor = type == "mushroom" ? .systemPink : .yellow
        let node = SKSpriteNode(color: color, size: CGSize(width: 18, height: 18))
        node.position.y = tileToWorld(x: 0, y: 9).y + 100
        node.name = "drop_\(id)"
        node.zPosition = 28
        worldNode.addChild(node)
        drops[id] = node
        return node
    }

    private func buildBackground(level: TileMapData) {
        backgroundNode.removeAllChildren()
        let skyHeight = CGFloat(mapRows) * tileSize
        let sky = SKSpriteNode(color: SKColor(red: 0.45, green: 0.75, blue: 0.98, alpha: 1.0), size: CGSize(width: CGFloat(level.length) * tileSize, height: skyHeight))
        sky.position = CGPoint(x: sky.size.width / 2, y: skyHeight / 2)
        sky.zPosition = -100
        backgroundNode.addChild(sky)

        for (x, y) in level.cloudTiles {

            drawCloud(atTileX: x, tileY: y)
        }
        for (x, y) in level.bushTiles {
            drawBush(atTileX: x, tileY: y)
        }
    }
    private func drawCloud(atTileX x: Int, tileY y: Int) {
        // PC 版云是 3x2 组合块：row 20 / 21, col 0..2
        for rowOffset in 0..<2 {
            for colOffset in 0..<3 {
                guard let tex = tileTexture(tileX: colOffset, tileY: 20 + rowOffset, sheetTile: 16) else { continue }
                let node = SKSpriteNode(texture: tex, size: CGSize(width: tileSize, height: tileSize))
                let base = tileToWorld(x: x + colOffset, y: y + rowOffset)
                node.position = CGPoint(x: base.x, y: base.y + cloudRenderYOffset)
                node.zPosition = -80
                node.alpha = 0.95
                backgroundNode.addChild(node)
            }
        }
    }
    private func drawBush(atTileX x: Int, tileY y: Int) {
        // PC 版草丛是 3x1 组合块：row 11, col 11..13
        for colOffset in 0..<3 {
            guard let tex = tileTexture(tileX: 11 + colOffset, tileY: 11, sheetTile: 16) else { continue }
            let node = SKSpriteNode(texture: tex, size: CGSize(width: tileSize, height: tileSize))
            let base = tileToWorld(x: x + colOffset, y: y)
            node.position = CGPoint(x: base.x, y: base.y + bushRenderYOffset)
            node.zPosition = -70
            backgroundNode.addChild(node)
        }
    }
    private func setupHud() {
        hudNode.removeAllChildren()
        hudNode.zPosition = 999
        cameraAnchor.addChild(hudNode)
        let leftX = -size.width * 0.5 + 34
        let topY = size.height * 0.5 - 16
        let centerX = -24.0
        let rightX = size.width * 0.5 - 170

        for label in [hudMarioLabel, hudScoreLabel, hudCoinLabel, hudWorldLabel, hudWorldValueLabel, hudTimeLabel, hudHpLabel] {
            label.fontSize = 16
            label.fontColor = .white
            label.horizontalAlignmentMode = .left
            label.verticalAlignmentMode = .top
            hudNode.addChild(label)
        }

        hudMarioLabel.position = CGPoint(x: leftX, y: topY)
        hudMarioLabel.text = "MARIO"
        hudScoreLabel.position = CGPoint(x: leftX, y: topY - 24)
        hudScoreLabel.text = "M000000"

        hudCoinLabel.position = CGPoint(x: leftX + 96, y: topY - 24)
        hudCoinLabel.text = "o x00"

        hudWorldLabel.position = CGPoint(x: centerX, y: topY)
        hudWorldLabel.text = "WORLD"
        hudWorldValueLabel.position = CGPoint(x: centerX + 21, y: topY - 22)
        hudWorldValueLabel.text = "1-1"

        hudTimeLabel.position = CGPoint(x: rightX, y: topY)
        hudTimeLabel.text = "TIME"

        hudHpBarBg.fillColor = .black
        hudHpBarBg.strokeColor = .white
        hudHpBarBg.lineWidth = 1
        hudHpBarBg.position = CGPoint(x: leftX + 72, y: topY - 42)
        hudNode.addChild(hudHpBarBg)

        hudHpBarFill.fillColor = SKColor(red: 0.86, green: 0.08, blue: 0.08, alpha: 1.0)
        hudHpBarFill.strokeColor = .clear
        hudHpBarFill.position = CGPoint(x: leftX + 72, y: topY - 42)
        hudNode.addChild(hudHpBarFill)

        hudHpLabel.fontSize = 14
        hudHpLabel.position = CGPoint(x: leftX + 145, y: topY - 34)
        hudHpLabel.text = "30/30"
    }

    private func configureAnimationFrames() {
        localAnimTextures.removeAll()

        // Match PC client big form: use mario_big_* frames from characters sheet.
        if let sheet = UIImage(named: "characters")?.cgImage {
            let idle = cropTexture(from: sheet, x: 259, y: 1, width: 16, height: 32)
            let run1 = cropTexture(from: sheet, x: 296, y: 1, width: 16, height: 32)
            let run2 = cropTexture(from: sheet, x: 315, y: 1, width: 16, height: 32)
            let run3 = cropTexture(from: sheet, x: 332, y: 1, width: 16, height: 32)
            let jump = cropTexture(from: sheet, x: 369, y: 1, width: 16, height: 32)
            localAnimTextures[.idle] = [idle]
            localAnimTextures[.run] = [run1, run2, run3]
            localAnimTextures[.jump] = [jump]
            localAnimTextures[.fall] = [jump]
            return
        }

        // Fallback only when characters sheet is unavailable.
        if let atlas = tryLoadAtlas(named: "MarioFrames") {
            localAnimTextures[.idle] = textures(in: atlas, prefix: "mario_idle_")
            localAnimTextures[.run] = textures(in: atlas, prefix: "mario_run_")
            localAnimTextures[.jump] = textures(in: atlas, prefix: "mario_jump_")
            localAnimTextures[.fall] = textures(in: atlas, prefix: "mario_fall_")
        }
    }

    private func applyAnimation(_ state: AnimState) {
        guard currentAnimState != state else { return }
        currentAnimState = state
        localPlayer.removeAction(forKey: animActionKey)

        guard let textures = localAnimTextures[state], !textures.isEmpty else {
            if !fallbackTinted {
                fallbackTinted = true
                localPlayer.colorBlendFactor = 0.18
                localPlayer.color = .red
            }
            return
        }

        if textures.count == 1 {
            localPlayer.texture = textures[0]
            return
        }
        let frameTime: TimeInterval = state == .run ? 0.14 : 0.16
        let action = SKAction.repeatForever(.animate(with: textures, timePerFrame: frameTime, resize: false, restore: true))
        localPlayer.run(action, withKey: animActionKey)
    }

    private func tryLoadAtlas(named name: String) -> SKTextureAtlas? {
        let atlas = SKTextureAtlas(named: name)
        return atlas.textureNames.isEmpty ? nil : atlas
    }

    private func textures(in atlas: SKTextureAtlas, prefix: String) -> [SKTexture] {
        atlas.textureNames
            .filter { $0.hasPrefix(prefix) }
            .sorted()
            .map { pixelTexture(atlas.textureNamed($0)) }
    }

    private func cropTexture(from sheet: CGImage, x: Int, y: Int, width: Int, height: Int) -> SKTexture {
        let rect = CGRect(x: x, y: y, width: width, height: height)
        let cropped = sheet.cropping(to: rect) ?? sheet
        let ui = UIImage(cgImage: cropped)
        return pixelTexture(SKTexture(image: ui))
    }

    private func tileTexture(tileX: Int, tileY: Int, sheetTile: Int) -> SKTexture? {
        guard let sheet = tileSheet else { return nil }
        let px = tileX * sheetTile
        let py = tileY * sheetTile
        let texture = SKTexture(image: UIImage(cgImage: sheet.cropping(to: CGRect(x: px, y: py, width: sheetTile, height: sheetTile)) ?? sheet))
        return pixelTexture(texture)
    }

    private func pixelTexture(_ texture: SKTexture) -> SKTexture {
        texture.filteringMode = .nearest
        return texture
    }

    private func fromServerY(_ y: Double) -> CGFloat {
        serverCoordinateHeight - CGFloat(y)
    }

    private func toServerY(_ y: CGFloat) -> Double {
        Double(serverCoordinateHeight - y)
    }

    private func makeTileNode(kind: TileKind, x: Int, y: Int) -> SKSpriteNode {
        switch kind {
        case .ground:
            if let tex = tileTexture(tileX: 0, tileY: 0, sheetTile: 16) {
                return SKSpriteNode(texture: tex, size: CGSize(width: tileSize, height: tileSize))
            }
        case .brick:
            if let tex = tileTexture(tileX: 1, tileY: 0, sheetTile: 16) {
                return SKSpriteNode(texture: tex, size: CGSize(width: tileSize, height: tileSize))
            }
        case .pipe:
            let aboveKey = "\(x):\(y - 1)"
            let isTop = tileKinds[aboveKey] != .pipe
            let isLeft = tileKinds["\(x - 1):\(y)"] != .pipe
            let tileX = isLeft ? 0 : 1
            let tileY = isTop ? 10 : 11
            if let tex = tileTexture(tileX: tileX, tileY: tileY, sheetTile: 16) {
                return SKSpriteNode(texture: tex, size: CGSize(width: tileSize, height: tileSize))
            }
        }
        return SKSpriteNode(color: .brown, size: CGSize(width: tileSize, height: tileSize))
    }   
}