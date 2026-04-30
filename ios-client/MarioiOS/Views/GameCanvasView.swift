import SwiftUI

struct GameCanvasView: View {
    @EnvironmentObject private var viewModel: GameViewModel

    var body: some View {
        VStack(spacing: 12) {
            Text("游戏中")
                .font(.headline)

            ZStack {
                Rectangle()
                    .fill(Color.black.opacity(0.85))
                    .frame(height: 260)
                    .overlay(alignment: .bottom) {
                        Rectangle()
                            .fill(Color.green.opacity(0.5))
                            .frame(height: 24)
                    }

                playerMarker(x: viewModel.localPlayer.x, y: viewModel.localPlayer.y, color: .red)

                ForEach(Array(viewModel.remotePlayers.keys), id: \.self) { key in
                    if let state = viewModel.remotePlayers[key] {
                        playerMarker(x: state.x, y: state.y, color: .blue)
                    }
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: 12))

            HStack(spacing: 20) {
                Button("←") { viewModel.setMove(left: true) }
                    .simultaneousGesture(DragGesture(minimumDistance: 0).onEnded { _ in
                        viewModel.setMove(left: false)
                    })
                    .buttonStyle(.borderedProminent)

                Button("发射") { viewModel.fire() }
                    .buttonStyle(.bordered)

                Button("→") { viewModel.setMove(right: true) }
                    .simultaneousGesture(DragGesture(minimumDistance: 0).onEnded { _ in
                        viewModel.setMove(right: false)
                    })
                    .buttonStyle(.borderedProminent)
            }

            Button("退出房间") { viewModel.leaveRoom() }
                .buttonStyle(.bordered)
        }
        .padding()
    }

    @ViewBuilder
    private func playerMarker(x: Double, y: Double, color: Color) -> some View {
        let clampedX = min(max(x / 1600.0, 0), 1) * 320.0 - 160.0
        let clampedY = min(max(y / 480.0, 0), 1) * 220.0 - 110.0
        Circle()
            .fill(color)
            .frame(width: 16, height: 16)
            .offset(x: clampedX, y: clampedY)
    }
}
