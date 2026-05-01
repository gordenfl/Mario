import SpriteKit
import UIKit

final class SpriteKitGameScene: SKScene {
    // PC baseline constants (client/traits/go.py, jump.py, classes/Camera.py, sprites/Mario.json)
    private let logicFps: CGFloat = 60
    private let tileSize: CGFloat = 32
    private let mapRows = 16
    private let serverCoordinateHeight: CGFloat = 480
    private let smallMarioScale: CGFloat = 2.0
    private let bigMarioScale: CGFloat = 2.0
    private let pcGravityPerFrame: CGFloat = 0.8
    // Tuned so the mobile JumpTrait-style implementation reaches ~132px apex.
    private let pcJumpVelocityPerFrame: CGFloat = 12.0
    private let pcJumpHeight: CGFloat = 132
    private let spriteKitStableGravity: CGFloat = 24.0
    private let pcAccelPerFrame: CGFloat = 0.4
    private let pcDecelPerFrame: CGFloat = 0.25
    private let pcMaxRunSpeedPerFrame: CGFloat = 3.2
    private let sceneDownShiftPx: CGFloat = 54
    private let cloudRenderYOffset: CGFloat = 0
    private let bushRenderYOffset: CGFloat = 0
    private let playerSize = CGSize(width: 32, height: 64)
    private let worldNode = SKNode()
    private let backgroundNode = SKNode()
    private let collisionDebugNode = SKNode()
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
    private var dropTypes: [String: String] = [:]
    private var projectiles: [Int: SKSpriteNode] = [:]
    private var projectileStates: [Int: ProjectileStateModel] = [:]
    private var solidTiles: [String: SKSpriteNode] = [:]
    private var breakableTiles: Set<String> = []
    private var tileKinds: [String: TileKind] = [:]
    private var tileSheet: CGImage?
    private var itemsSheet: CGImage?
    private var coinTextures: [SKTexture] = []
    private var mushroomTexture: SKTexture?
    private var brokenTilesApplied: Set<String> = []
    private var collisionDebugBoxes: [String: SKShapeNode] = [:]
    private var worldWidth: CGFloat = 60 * 32
    private var leftPressed = false
    private var rightPressed = false
    private var heading: Int8 = 1
    private var lastUpdate: TimeInterval = 0
    private var dropDirections: [String: Int] = [:]
    private var dropVerticalSpeed: [String: CGFloat] = [:]
    private var dropGrounded: [String: Bool] = [:]
    /// Matches PC `SkyMushroom.pos_x` float + `rect.x = int(pos_x)` (trunc toward zero), not smooth sub-pixel drift.
    private var mushroomLogicalX: [String: CGFloat] = [:]
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
    private var horizontalVelocity: CGFloat = 0
    private var jumpVerticalVelocity: CGFloat = 0
    private var jumpStartY: CGFloat = 0
    private var jumpInProgress = false
    private var jumpObeyGravity = false
    private let dropCoinAnimKey = "drop_coin_anim"
    private let fireRecoilActionKey = "mario_fire_recoil"
    private var cameraLookAhead: CGFloat = 0
    private let pcCoinSize: CGFloat = 32
    private let pcMushroomSize: CGFloat = 32
    // PC `SkyMushroom.speed` (client/entities/sky_drop.py): 1.2 px per 60Hz frame.
    private let pcMushroomSpeedPerFrame: CGFloat = 1.2
    private let showCollisionDebugBounds = true

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
        worldNode.addChild(collisionDebugNode)
        camera = cameraAnchor
        addChild(cameraAnchor)
        setupHud()
        configureAnimationFrames()
        tileSheet = UIImage(named: "tiles")?.cgImage
        itemsSheet = UIImage(named: "Items")?.cgImage ?? UIImage(named: "items")?.cgImage
        configureDropTextures()
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

    func triggerFireAnimation() {
        let direction: CGFloat = heading >= 0 ? 1 : -1
        let recoil = SKAction.moveBy(x: -direction * 4, y: 0, duration: 0.045)
        recoil.timingMode = .easeOut
        let recover = SKAction.moveBy(x: direction * 4, y: 0, duration: 0.06)
        recover.timingMode = .easeIn
        let flashOn = SKAction.run { [weak self] in
            self?.localPlayer.color = .orange
            self?.localPlayer.colorBlendFactor = 0.25
        }
        let flashOff = SKAction.run { [weak self] in
            self?.localPlayer.colorBlendFactor = 0.0
        }
        let sequence = SKAction.sequence([flashOn, recoil, recover, flashOff])
        localPlayer.removeAction(forKey: fireRecoilActionKey)
        localPlayer.run(sequence, withKey: fireRecoilActionKey)
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
            // Server/PC uses top-left style coordinates; SpriteKit positions by center.
            // Convert remote position to center anchor to keep feet on the same ground line.
            let anchorXOffset = node.size.width * 0.5
            let anchorYOffset = node.size.height * 0.5
            node.position = CGPoint(
                x: CGFloat(state.x) + anchorXOffset,
                y: fromServerY(state.y) - anchorYOffset
            )
            applyRemoteAnimation(for: node, id: id, state: state)
        }
    }

    func syncDrops(_ states: [String: DropState]) {
        let keys = Set(states.keys)
        for id in drops.keys where !keys.contains(id) {
            drops[id]?.removeFromParent()
            drops.removeValue(forKey: id)
            dropTypes.removeValue(forKey: id)
            dropDirections.removeValue(forKey: id)
            dropVerticalSpeed.removeValue(forKey: id)
            dropGrounded.removeValue(forKey: id)
            mushroomLogicalX.removeValue(forKey: id)
        }
        for (id, drop) in states {
            let node = drops[id] ?? makeDropNode(id: id, type: drop.type)
            dropTypes[id] = drop.type
            applyDropAppearance(node, type: drop.type)
            if drop.type == "mushroom" {
                // Keep PC-like local motion once grounded.
                // Only snap on spawn/large divergence, while still honoring server direction updates.
                let isGrounded = dropGrounded[id] ?? false
                let dx = drop.x - node.position.x
                if !isGrounded || abs(dx) > tileSize * 2.0 {
                    node.position.x = drop.x
                    mushroomLogicalX[id] = drop.x
                }
            } else {
                node.position.x = drop.x
            }
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
            // Server projectile coordinates use top-left semantics.
            // Convert to SpriteKit center anchor so muzzle alignment matches PC.
            node.position = CGPoint(
                x: CGFloat(state.x) + node.size.width * 0.5,
                y: fromServerY(state.y) - node.size.height * 0.5
            )
        }
    }

    func applyBrokenTiles(_ keys: Set<String>) {
        for key in keys where !brokenTilesApplied.contains(key) {
            solidTiles[key]?.removeFromParent()
            solidTiles.removeValue(forKey: key)
            collisionDebugBoxes[key]?.removeFromParent()
            collisionDebugBoxes.removeValue(forKey: key)
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
        collisionDebugNode.removeAllChildren()
        collisionDebugBoxes.removeAll()
        buildBackground(level: level)
        for (x, y) in level.solidTiles {
            let key = "\(x):\(y)"
            let kind = tileKinds["\(x):\(y)"] ?? .ground
            let node = makeTileNode(kind: kind, x: x, y: y)
            let base = tileToWorld(x: x, y: y)
            if kind == .pipe {
                // Keep collision grid from tile indices, but visually align pipe body/cap
                // to the same row as PC rendering.
                node.position = CGPoint(x: base.x, y: base.y - tileSize)
                // Draw pipes in front to mask remote interpolation overlap.
                node.zPosition = 35
            } else {
                node.position = base
                node.zPosition = 10
            }
            worldNode.addChild(node)
            solidTiles[key] = node
            addCollisionDebugBox(key: key, kind: kind, logicalX: x, logicalY: y)
        }
    }

    private func addCollisionDebugBox(key: String, kind: TileKind, logicalX x: Int, logicalY y: Int) {
        guard showCollisionDebugBounds else { return }
        let base = tileToWorld(x: x, y: y)
        let center = kind == .pipe
            ? CGPoint(x: base.x, y: base.y - tileSize)
            : base
        let path = makeDashedRectPath(width: tileSize, height: tileSize, dash: 6, gap: 4)
        let shape = SKShapeNode(path: path)
        shape.position = center
        shape.zPosition = 95
        shape.strokeColor = kind == .pipe
            ? SKColor.systemOrange.withAlphaComponent(0.9)
            : SKColor.systemYellow.withAlphaComponent(0.85)
        shape.lineWidth = 1.2
        shape.fillColor = .clear
        collisionDebugNode.addChild(shape)
        collisionDebugBoxes[key] = shape
    }

    private func makeDashedRectPath(width: CGFloat, height: CGFloat, dash: CGFloat, gap: CGFloat) -> CGPath {
        let halfW = width * 0.5
        let halfH = height * 0.5
        let path = CGMutablePath()

        func addDashedLine(from start: CGPoint, to end: CGPoint) {
            let dx = end.x - start.x
            let dy = end.y - start.y
            let length = hypot(dx, dy)
            guard length > 0 else { return }
            let ux = dx / length
            let uy = dy / length
            var traveled: CGFloat = 0
            while traveled < length {
                let segStart = traveled
                let segEnd = min(traveled + dash, length)
                let p1 = CGPoint(x: start.x + ux * segStart, y: start.y + uy * segStart)
                let p2 = CGPoint(x: start.x + ux * segEnd, y: start.y + uy * segEnd)
                path.move(to: p1)
                path.addLine(to: p2)
                traveled += dash + gap
            }
        }

        let topLeft = CGPoint(x: -halfW, y: halfH)
        let topRight = CGPoint(x: halfW, y: halfH)
        let bottomRight = CGPoint(x: halfW, y: -halfH)
        let bottomLeft = CGPoint(x: -halfW, y: -halfH)

        addDashedLine(from: topLeft, to: topRight)
        addDashedLine(from: topRight, to: bottomRight)
        addDashedLine(from: bottomRight, to: bottomLeft)
        addDashedLine(from: bottomLeft, to: topLeft)
        return path
    }

    private func setupLocalPlayer() {
        let marioScale = bigMarioScale
        if let first = localAnimTextures[.idle]?.first {
            localPlayer.texture = first
            localPlayer.size = CGSize(width: first.size().width * marioScale, height: first.size().height * marioScale)
        } else {
            localPlayer.size = playerSize
        }
        let spawnX: CGFloat = 48
            let spawnGroundY = groundSurfaceY(atX: spawnX)
        localPlayer.position = CGPoint(x: spawnX, y: spawnGroundY + playerSize.height * 0.5)
        worldNode.addChild(localPlayer)
        // Use PC JumpTrait-style vertical motion instead of SpriteKit gravity.
        physicsWorld.gravity = .zero
    }

    private func applyInput() {
        let accelPerTickSpeed = pcAccelPerFrame * logicFps
        let decelPerTickSpeed = pcDecelPerFrame * logicFps
        let maxRunSpeedPerSecond = pcMaxRunSpeedPerFrame * logicFps

        if leftPressed {
            horizontalVelocity -= accelPerTickSpeed
        }
        if rightPressed {
            horizontalVelocity += accelPerTickSpeed
        }
        if !leftPressed && !rightPressed {
            if horizontalVelocity > 0 {
                horizontalVelocity = max(0, horizontalVelocity - decelPerTickSpeed)
            } else if horizontalVelocity < 0 {
                horizontalVelocity = min(0, horizontalVelocity + decelPerTickSpeed)
            }
        }
        horizontalVelocity = min(max(horizontalVelocity, -maxRunSpeedPerSecond), maxRunSpeedPerSecond)
        let headingVelocityThreshold = pcAccelPerFrame * logicFps * 0.6
        if horizontalVelocity > headingVelocityThreshold {
            heading = 1
        } else if horizontalVelocity < -headingVelocityThreshold {
            heading = -1
        }
        moveLocalPlayerHorizontally(deltaX: horizontalVelocity / logicFps)
        if jumpQueued || jumpBufferFrames > 0 {
            if isPlayerGrounded() {
                jumpVerticalVelocity = pcJumpVelocityPerFrame
                jumpStartY = localPlayer.position.y
                jumpInProgress = true
                jumpObeyGravity = false
                jumpQueued = false
                jumpBufferFrames = 0
            } else {
                jumpBufferFrames = max(0, jumpBufferFrames - 1)
                if jumpBufferFrames == 0 {
                    jumpQueued = false
                }
            }
        }
        applyJumpTraitVerticalMotion()
        let minX = playerSize.width / 2
        let maxX = worldWidth - playerSize.width / 2
        if localPlayer.position.x < minX {
            localPlayer.position.x = minX
            horizontalVelocity = max(0, horizontalVelocity)
        }
        if localPlayer.position.x > maxX {
            localPlayer.position.x = maxX
            horizontalVelocity = min(0, horizontalVelocity)
        }
    }

    private func moveLocalPlayerHorizontally(deltaX: CGFloat) {
        guard deltaX != 0 else { return }

        var targetX = localPlayer.position.x + deltaX
        let halfW = playerSize.width * 0.5
        let halfH = playerSize.height * 0.5
        let sampleYs = [
            localPlayer.position.y - halfH + 6,
            localPlayer.position.y,
            localPlayer.position.y + halfH - 6
        ]

        if deltaX > 0 {
            let frontX = targetX + halfW
            if sampleYs.contains(where: { isSolidTileAt(worldX: frontX, worldY: $0) }) {
                let tileX = Int(floor(frontX / tileSize))
                targetX = CGFloat(tileX) * tileSize - halfW - 0.01
                horizontalVelocity = min(0, horizontalVelocity)
            }
        } else {
            let frontX = targetX - halfW
            if sampleYs.contains(where: { isSolidTileAt(worldX: frontX, worldY: $0) }) {
                let tileX = Int(floor(frontX / tileSize))
                targetX = CGFloat(tileX + 1) * tileSize + halfW + 0.01
                horizontalVelocity = max(0, horizontalVelocity)
            }
        }

        localPlayer.position.x = targetX
    }

    private func applyJumpTraitVerticalMotion() {
        // Equivalent to PC JumpTrait: hold initial jump phase, then obey gravity.
        let decelHeight = pcJumpHeight - ((pcJumpVelocityPerFrame * pcJumpVelocityPerFrame) / (2 * pcGravityPerFrame))
        let wasGrounded = isPlayerGrounded()
        let previousFootY = localPlayer.position.y - playerSize.height * 0.5
        if !wasGrounded && !jumpInProgress {
            jumpObeyGravity = true
        }
        if jumpInProgress {
            if (localPlayer.position.y - jumpStartY) >= decelHeight || jumpVerticalVelocity <= 0 {
                jumpInProgress = false
                jumpObeyGravity = true
            }
        }
        if jumpObeyGravity {
            jumpVerticalVelocity -= pcGravityPerFrame
        }

        if jumpVerticalVelocity != 0 {
            localPlayer.position.y += jumpVerticalVelocity
        }

        // Ground snap only when falling into ground; don't pre-snap while still above it.
        if jumpVerticalVelocity <= 0 {
            let footY = localPlayer.position.y - playerSize.height * 0.5
            if let landingTop = landingSurfaceYCrossed(previousFootY: previousFootY, currentFootY: footY) {
                let targetCenterY = landingTop + playerSize.height * 0.5
                if localPlayer.position.y <= targetCenterY {
                    localPlayer.position.y = targetCenterY
                    jumpVerticalVelocity = 0
                    jumpObeyGravity = false
                    jumpInProgress = false
                }
            }
        }
    }

    private func updateCamera() {
        let half = size.width / 2
        // Match PC camera framing: keep hero around 58% viewport width.
        let anchorX = size.width * 0.58
        let targetX = localPlayer.position.x - anchorX + half
        let clampedX = min(max(targetX, half), max(half, worldWidth - half))
        let cameraY = tileSize * 5.78 + sceneDownShiftPx
        cameraAnchor.position = CGPoint(x: clampedX, y: cameraY)
    }

    private func publishLocalState() {
        let vy = jumpVerticalVelocity * logicFps
        let vx = horizontalVelocity
        let onGround = abs(vy) < (pcGravityPerFrame * logicFps * 0.2)
        var flags: UInt8 = 0
        if onGround { flags |= 0b0001 }
        if !onGround { flags |= 0b0010 }
        // Match PC/Server coordinate semantics: publish top-left sprite origin.
        let topLeftX = localPlayer.position.x - localPlayer.size.width * 0.5
        let topLeftYInScene = localPlayer.position.y + localPlayer.size.height * 0.5
        let state = PlayerState(
            x: topLeftX,
            y: toServerY(topLeftYInScene),
            vx: vx / 60,
            vy: -jumpVerticalVelocity,
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
        let gravity: CGFloat = tileSize * 9.0
        for (id, node) in drops {
            let type = dropTypes[id] ?? "coin"
            if dropGrounded[id] == true {
                if type == "mushroom" {
                    let direction = dropDirections[id, default: 1]
                    let directionSign: CGFloat = direction >= 0 ? 1 : -1
                    var lx = mushroomLogicalX[id] ?? node.position.x
                    let step = pcMushroomSpeedPerFrame * logicFps * CGFloat(delta) * directionSign
                    let nextLx = lx + step
                    let frontX = nextLx + directionSign * (node.size.width * 0.5 + 1)
                    let sampleYs = [
                        node.position.y - node.size.height * 0.3,
                        node.position.y,
                        node.position.y + node.size.height * 0.3
                    ]
                    let hitWall = sampleYs.contains { sampleY in
                        isSolidTileAt(worldX: frontX, worldY: sampleY)
                    }
                    if hitWall {
                        dropDirections[id] = directionSign > 0 ? -1 : 1
                    } else {
                        lx = nextLx
                        mushroomLogicalX[id] = lx
                        node.position.x = lx.rounded(.towardZero)
                    }
                    let horizontalPadding = tileSize * 0.75
                    if node.position.x < horizontalPadding {
                        node.position.x = horizontalPadding
                        mushroomLogicalX[id] = horizontalPadding
                        dropDirections[id] = 1
                    } else if node.position.x > worldWidth - horizontalPadding {
                        node.position.x = worldWidth - horizontalPadding
                        mushroomLogicalX[id] = worldWidth - horizontalPadding
                        dropDirections[id] = -1
                    }
                    let dropFootY = node.position.y - node.size.height * 0.5
                    let groundY = groundSurfaceY(atX: node.position.x, belowWorldY: dropFootY) + node.size.height * 0.5
                    node.position.y = groundY
                }
                continue
            }

            let vy = (dropVerticalSpeed[id] ?? 0) - gravity * CGFloat(delta)
            dropVerticalSpeed[id] = vy
            node.position.y += vy * CGFloat(delta)

            let dropFootY = node.position.y - node.size.height * 0.5
            let groundY = groundSurfaceY(atX: node.position.x, belowWorldY: dropFootY) + node.size.height * 0.5
            if node.position.y <= groundY {
                node.position.y = groundY
                dropVerticalSpeed[id] = 0
                dropGrounded[id] = true
                if type == "mushroom", mushroomLogicalX[id] == nil {
                    mushroomLogicalX[id] = node.position.x
                }
            }
        }
    }

    private func updateAnimations(currentTime: TimeInterval) {
        let vx = abs(horizontalVelocity)
        let vy = jumpVerticalVelocity * logicFps
        let onGroundThreshold = pcGravityPerFrame * logicFps
        let onGround = isPlayerGrounded() && abs(vy) < onGroundThreshold
        let movingIntent = leftPressed || rightPressed
        let standingLock = !movingIntent && vx < (pcAccelPerFrame * logicFps) && abs(vy) < (onGroundThreshold * 3.5)
        let nextState: AnimState
        if !onGround {
            // Keep jump pose for the entire airborne phase on mobile.
            nextState = .jump
        } else if standingLock {
            nextState = .idle
        } else if movingIntent && vx > (pcAccelPerFrame * logicFps * 1.1) {
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
                dropTypes.removeValue(forKey: id)
                dropDirections.removeValue(forKey: id)
                dropVerticalSpeed.removeValue(forKey: id)
                dropGrounded.removeValue(forKey: id)
                mushroomLogicalX.removeValue(forKey: id)
            }
        }
    }

    private func detectTileBreak() {
        let vy = jumpVerticalVelocity * logicFps
        let upwardBreakThreshold = pcAccelPerFrame * logicFps * 1.25
        guard vy > upwardBreakThreshold else { return }
        let headX = Int(localPlayer.position.x / tileSize)
        let headProbeOffset = tileSize * 0.125
        let headY = mapRows - 1 - Int((localPlayer.position.y + playerSize.height / 2 + headProbeOffset) / tileSize)
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
            if isSolidTileAt(worldX: x, worldY: footY) {
                return true
            }
        }
        return false
    }

    private func landingSurfaceYUnderPlayer(footY: CGFloat) -> CGFloat? {
        let sampleXs = [
            localPlayer.position.x - playerSize.width * 0.3,
            localPlayer.position.x,
            localPlayer.position.x + playerSize.width * 0.3
        ]
        var best: CGFloat?
        for x in sampleXs {
            let top = groundSurfaceY(atX: x, belowWorldY: footY)
            if top <= footY + 0.01 {
                if best == nil || top > best! {
                    best = top
                }
            }
        }
        return best
    }

    private func landingSurfaceYCrossed(previousFootY: CGFloat, currentFootY: CGFloat) -> CGFloat? {
        let upper = max(previousFootY, currentFootY)
        let lower = min(previousFootY, currentFootY)
        let sampleXs = [
            localPlayer.position.x - playerSize.width * 0.3,
            localPlayer.position.x,
            localPlayer.position.x + playerSize.width * 0.3
        ]
        var best: CGFloat?
        for x in sampleXs {
            let top = groundSurfaceY(atX: x, belowWorldY: upper)
            // Detect landing planes crossed within this frame (prevents pipe-top tunneling).
            if top <= upper + 0.01 && top >= lower - 0.01 {
                if best == nil || top > best! {
                    best = top
                }
            }
        }
        return best
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
        let onGroundThreshold = pcGravityPerFrame * logicFps
        let onGround = (state.flags & 0b0001) != 0 || abs(vy) < onGroundThreshold
        let moving = vx > (pcAccelPerFrame * logicFps)
        let nextState: AnimState
        if !onGround && vy > (pcJumpVelocityPerFrame * logicFps * 0.35) {
            nextState = .jump
        } else if !onGround && vy < -(pcJumpVelocityPerFrame * logicFps * 0.35) {
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

        let frameTime: TimeInterval = nextState == .run ? TimeInterval(7.0 / logicFps) : TimeInterval(8.0 / logicFps)
        let action = SKAction.repeatForever(.animate(with: textures, timePerFrame: frameTime, resize: false, restore: true))
        node.run(action, withKey: remoteAnimActionKey)
    }

    private func makeProjectileNode(id: Int) -> SKSpriteNode {
        let node = SKSpriteNode(color: .orange, size: CGSize(width: 16, height: 16))
        node.name = "proj_\(id)"
        node.zPosition = 30
        worldNode.addChild(node)
        projectiles[id] = node
        return node
    }

    private func makeDropNode(id: String, type: String) -> SKSpriteNode {
        let dropSize = type == "mushroom" ? pcMushroomSize : pcCoinSize
        let node = SKSpriteNode(color: .clear, size: CGSize(width: dropSize, height: dropSize))
        applyDropAppearance(node, type: type)
        node.position.y = tileToWorld(x: 0, y: 9).y + tileSize * 3.125
        node.name = "drop_\(id)"
        node.zPosition = 28
        worldNode.addChild(node)
        drops[id] = node
        dropTypes[id] = type
        dropVerticalSpeed[id] = 0
        dropGrounded[id] = false
        return node
    }

    private func groundSurfaceY(atX x: CGFloat, belowWorldY referenceY: CGFloat? = nil) -> CGFloat {
        let tileX = Int(floor(x / tileSize))
        var bestTop: CGFloat?
        for tileY in 0..<mapRows {
            let key = "\(tileX):\(tileY)"
            guard solidTiles[key] != nil else { continue }
            let kind = tileKinds[key] ?? .ground
            guard kind == .ground || kind == .pipe || kind == .brick else { continue }
            let baseTop = tileToWorld(x: tileX, y: tileY).y + tileSize * 0.5
            // Pipe sprites are rendered one tile lower to match PC visuals.
            // Keep grounding/collision top aligned to that rendered position.
            let top = kind == .pipe ? (baseTop - tileSize) : baseTop
            if let referenceY {
                // Only consider standable surfaces at or below current feet.
                if top > referenceY + 0.01 {
                    continue
                }
            }
            if bestTop == nil || top > bestTop! {
                bestTop = top
            }
        }
        if let bestTop {
            return bestTop
        }
        return tileToWorld(x: tileX, y: mapRows - 2).y + tileSize * 0.5
    }

    private func isSolidTileAt(worldX x: CGFloat, worldY y: CGFloat) -> Bool {
        let tileX = Int(floor(x / tileSize))
        let tileY = mapRows - 1 - Int(floor(y / tileSize))
        guard tileY >= 0, tileY < mapRows else { return false }
        let directKey = "\(tileX):\(tileY)"
        if solidTiles[directKey] != nil {
            // Pipe visuals/collision are shifted down by 1 tile for PC parity.
            // Ignore the original logical pipe row to avoid a hidden extra blocking layer.
            if tileKinds[directKey] != .pipe {
                return true
            }
        }
        // Pipe visuals are shifted down by 1 tile for PC parity.
        // A world point on the rendered pipe corresponds to logical (tileY - 1).
        let shiftedKey = "\(tileX):\(tileY - 1)"
        if tileY - 1 >= 0, tileKinds[shiftedKey] == .pipe, solidTiles[shiftedKey] != nil {
            return true
        }
        return false
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
                node.position = CGPoint(
                    x: base.x,
                    y: base.y + cloudRenderYOffset
                )
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
            node.position = CGPoint(
                x: base.x,
                y: base.y + bushRenderYOffset
            )
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
        let frameTime: TimeInterval = state == .run ? TimeInterval(7.0 / logicFps) : TimeInterval(8.0 / logicFps)
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

    private func configureDropTextures() {
        coinTextures = []
        mushroomTexture = nil
        guard let sheet = itemsSheet else { return }

        // PC coin animation uses Items.png tiles (x: 0..3, y: 7), 16x16, deltaTime=10.
        for frameX in 0..<4 {
            if let texture = itemTexture(tileX: frameX, tileY: 7, sheetTile: 16) {
                coinTextures.append(texture)
            }
        }
        // PC mushroom sprite is cropped at pixel (0,16) with 16x16 size.
        if let crop = sheet.cropping(to: CGRect(x: 0, y: 16, width: 16, height: 16)) {
            mushroomTexture = pixelTexture(SKTexture(image: UIImage(cgImage: crop)))
        } else if let tileFallback = itemTexture(tileX: 0, tileY: 1, sheetTile: 16) {
            mushroomTexture = tileFallback
        }
    }

    private func applyDropAppearance(_ node: SKSpriteNode, type: String) {
        node.removeAction(forKey: dropCoinAnimKey)
        node.colorBlendFactor = 0.0
        node.texture = nil
        let side = type == "mushroom" ? pcMushroomSize : pcCoinSize
        node.size = CGSize(width: side, height: side)

        if type == "mushroom" {
            if let texture = mushroomTexture {
                node.texture = texture
            } else {
                node.color = .systemPink
                node.colorBlendFactor = 1.0
            }
            return
        }

        if let first = coinTextures.first {
            node.texture = first
            if coinTextures.count > 1 {
                let action = SKAction.repeatForever(.animate(with: coinTextures, timePerFrame: 10.0 / 60.0, resize: false, restore: true))
                node.run(action, withKey: dropCoinAnimKey)
            }
        } else {
            node.color = .yellow
            node.colorBlendFactor = 1.0
        }
    }

    private func itemTexture(tileX: Int, tileY: Int, sheetTile: Int) -> SKTexture? {
        guard let sheet = itemsSheet else { return nil }
        let px = tileX * sheetTile
        let py = tileY * sheetTile
        guard let crop = sheet.cropping(to: CGRect(x: px, y: py, width: sheetTile, height: sheetTile)) else { return nil }
        return pixelTexture(SKTexture(image: UIImage(cgImage: crop)))
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