import SwiftUI
import SpriteKit
import UIKit

struct GameCanvasView: View {
    @EnvironmentObject private var viewModel: GameViewModel
    @State private var scene = SpriteKitGameScene(size: CGSize(width: 854, height: 480))

    var body: some View {
        ZStack {
            SpriteView(scene: scene)
                .ignoresSafeArea()
            .onAppear {
                configureScene()
            }
            .onChange(of: viewModel.remotePlayers) { (states: [Int: PlayerState]) in
                scene.syncRemotePlayers(states)
            }
            .onChange(of: viewModel.drops) { (drops: [String: DropState]) in
                scene.syncDrops(drops)
            }
            .onChange(of: viewModel.projectiles) { (projectiles: [Int: ProjectileStateModel]) in
                scene.syncProjectiles(projectiles)
            }
            .onChange(of: viewModel.brokenTiles) { (broken: Set<String>) in
                scene.applyBrokenTiles(broken)
            }
            .overlay {
                KeyboardInputCaptureView(
                    onMoveLeftChanged: { pressed in viewModel.setMove(left: pressed) },
                    onMoveRightChanged: { pressed in viewModel.setMove(right: pressed) },
                    onJump: { scene.triggerJump() },
                    onFire: { viewModel.fire() }
                )
                .allowsHitTesting(false)
            }
        }
    }

    private func configureScene() {
        scene.scaleMode = SKSceneScaleMode.aspectFill
        scene.setLocalClientId(viewModel.localClientIdentifier())
        scene.onLocalState = { (state: PlayerState) in
            Task { @MainActor in
                viewModel.updateLocalPlayerFromScene(state)
                let input = viewModel.currentInput()
                scene.setInput(left: input.left, right: input.right)
            }
        }
        scene.onRemoteHit = { remoteClientId in
            Task { @MainActor in
                viewModel.sceneDidHitRemote(clientId: remoteClientId)
            }
        }
        scene.onDropCollected = { dropId in
            Task { @MainActor in
                viewModel.sceneDidCollectDrop(dropId: dropId)
            }
        }
        scene.onTileBreak = { x, y in
            Task { @MainActor in
                viewModel.sceneDidBreakTile(x: x, y: y)
            }
        }
        scene.onProjectileUpdate = { projectile in
            Task { @MainActor in
                viewModel.sceneDidUpdateProjectile(projectile)
            }
        }
        scene.onProjectileDespawn = { id, lastKnown in
            Task { @MainActor in
                viewModel.sceneDidDespawnProjectile(id: id, lastKnown: lastKnown)
            }
        }
        scene.syncRemotePlayers(viewModel.remotePlayers)
        scene.syncDrops(viewModel.drops)
        scene.syncProjectiles(viewModel.projectiles)
        scene.applyBrokenTiles(viewModel.brokenTiles)
    }
}

private struct KeyboardInputCaptureView: UIViewRepresentable {
    let onMoveLeftChanged: (Bool) -> Void
    let onMoveRightChanged: (Bool) -> Void
    let onJump: () -> Void
    let onFire: () -> Void

    func makeUIView(context: Context) -> KeyboardInputUIView {
        let view = KeyboardInputUIView()
        view.onMoveLeftChanged = onMoveLeftChanged
        view.onMoveRightChanged = onMoveRightChanged
        view.onJump = onJump
        view.onFire = onFire
        DispatchQueue.main.async {
            _ = view.becomeFirstResponder()
        }
        return view
    }

    func updateUIView(_ uiView: KeyboardInputUIView, context: Context) {
        uiView.onMoveLeftChanged = onMoveLeftChanged
        uiView.onMoveRightChanged = onMoveRightChanged
        uiView.onJump = onJump
        uiView.onFire = onFire
    }
}

private final class KeyboardInputUIView: UIView {
    var onMoveLeftChanged: ((Bool) -> Void)?
    var onMoveRightChanged: ((Bool) -> Void)?
    var onJump: (() -> Void)?
    var onFire: (() -> Void)?

    override var canBecomeFirstResponder: Bool { true }

    override func didMoveToWindow() {
        super.didMoveToWindow()
        DispatchQueue.main.async { [weak self] in
            _ = self?.becomeFirstResponder()
        }
    }

    override func pressesBegan(_ presses: Set<UIPress>, with event: UIPressesEvent?) {
        for press in presses {
            guard let key = press.key else { continue }
            switch key.keyCode {
            case .keyboardLeftArrow:
                onMoveLeftChanged?(true)
            case .keyboardRightArrow:
                onMoveRightChanged?(true)
            case .keyboardUpArrow, .keyboardSpacebar:
                onJump?()
            case .keyboardF:
                onFire?()
            default:
                break
            }
        }
        super.pressesBegan(presses, with: event)
    }

    override func pressesEnded(_ presses: Set<UIPress>, with event: UIPressesEvent?) {
        for press in presses {
            guard let key = press.key else { continue }
            switch key.keyCode {
            case .keyboardLeftArrow:
                onMoveLeftChanged?(false)
            case .keyboardRightArrow:
                onMoveRightChanged?(false)
            default:
                break
            }
        }
        super.pressesEnded(presses, with: event)
    }

    override func pressesCancelled(_ presses: Set<UIPress>, with event: UIPressesEvent?) {
        onMoveLeftChanged?(false)
        onMoveRightChanged?(false)
        super.pressesCancelled(presses, with: event)
    }
}
