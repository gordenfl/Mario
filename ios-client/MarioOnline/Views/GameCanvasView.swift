import SwiftUI
import SpriteKit

struct GameCanvasView: View {
    @EnvironmentObject private var viewModel: GameViewModel
    @State private var scene = SpriteKitGameScene(size: CGSize(width: 960, height: 540))

    var body: some View {
        VStack(spacing: 14) {
            Text("游戏中")
                .font(.headline)
                .foregroundStyle(.white)

            GeometryReader { proxy in
                let width = proxy.size.width
                let height = min(proxy.size.height, width * 9.0 / 16.0)
                SpriteView(scene: scene)
                    .frame(width: width, height: height)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
            }
            .frame(height: 280)
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .overlay {
                RoundedRectangle(cornerRadius: 12)
                    .stroke(Color.white.opacity(0.25), lineWidth: 1)
            }
            .overlay(alignment: .topTrailing) {
                Text("16:9 横版")
                    .font(.caption2)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(.black.opacity(0.5))
                    .foregroundStyle(.white)
                    .clipShape(Capsule())
                    .padding(8)
            }
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

            HStack(spacing: 20) {
                holdButton("←", onPress: {
                    viewModel.setMove(left: true)
                }, onRelease: {
                    viewModel.setMove(left: false)
                })

                Button("发射") { viewModel.fire() }
                    .buttonStyle(.bordered)

                Button("跳跃") { scene.triggerJump() }
                    .buttonStyle(.borderedProminent)

                holdButton("→", onPress: {
                    viewModel.setMove(right: true)
                }, onRelease: {
                    viewModel.setMove(right: false)
                })
            }
            .padding(.vertical, 6)
            .padding(.horizontal, 10)
            .background(.ultraThinMaterial.opacity(0.7))
            .clipShape(RoundedRectangle(cornerRadius: 12))

            Button("退出房间") { viewModel.leaveRoom() }
                .buttonStyle(.bordered)
        }
        .padding()
        .background(
            LinearGradient(
                colors: [Color(red: 0.08, green: 0.1, blue: 0.2), Color(red: 0.13, green: 0.18, blue: 0.3)],
                startPoint: .top,
                endPoint: .bottom
            )
        )
    }

    private func configureScene() {
        scene.scaleMode = SKSceneScaleMode.resizeFill
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

    private func holdButton(_ title: String, onPress: @escaping () -> Void, onRelease: @escaping () -> Void) -> some View {
        Text(title)
            .font(.title2)
            .frame(width: 56, height: 44)
            .background(.blue.opacity(0.85))
            .foregroundStyle(.white)
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .gesture(
                DragGesture(minimumDistance: 0)
                    .onChanged { _ in onPress() }
                    .onEnded { _ in onRelease() }
            )
    }
}
