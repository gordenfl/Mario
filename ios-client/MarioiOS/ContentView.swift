import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var viewModel: GameViewModel

    var body: some View {
        Group {
            switch viewModel.screen {
            case .login, .lobby:
                LoginLobbyView()
            case .game:
                GameCanvasView()
            }
        }
        .onDisappear {
            viewModel.shutdown()
        }
    }
}
