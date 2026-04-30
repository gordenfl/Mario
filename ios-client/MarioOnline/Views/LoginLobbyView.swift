import SwiftUI

struct LoginLobbyView: View {
    @EnvironmentObject private var viewModel: GameViewModel

    var body: some View {
        ZStack {
            LinearGradient(
                colors: [Color(red: 0.08, green: 0.1, blue: 0.2), Color(red: 0.18, green: 0.2, blue: 0.35)],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            .ignoresSafeArea()

            VStack(spacing: 16) {
                Image("title_screen")
                    .resizable()
                    .scaledToFit()
                    .frame(maxHeight: 96)
                    .clipShape(RoundedRectangle(cornerRadius: 12))

                if viewModel.screen == .login {
                    loginCard
                } else {
                    lobbyCard
                    List(viewModel.rooms) { room in
                        HStack {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("房间 \(room.roomId)")
                                    .font(.headline)
                                Text("玩家: \(room.players.joined(separator: ", "))")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                            Image(systemName: "chevron.right")
                                .foregroundStyle(.secondary)
                        }
                        .contentShape(Rectangle())
                        .onTapGesture {
                            viewModel.joinRoom(room.roomId)
                        }
                    }
                    .clipShape(RoundedRectangle(cornerRadius: 16))
                    .frame(maxHeight: 280)
                }

                Spacer(minLength: 0)
            }
            .padding(20)
        }
    }

    private var loginCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("登录")
                .font(.title2.bold())
                .foregroundStyle(.white)

            TextField("服务器地址", text: $viewModel.host)
                .textFieldStyle(.roundedBorder)

            TextField("端口", text: $viewModel.portText)
                .textFieldStyle(.roundedBorder)
                .keyboardType(.numberPad)

            TextField("用户名", text: $viewModel.username)
                .textFieldStyle(.roundedBorder)

            Button("进入房间列表") {
                viewModel.connectAndLogin()
            }
            .buttonStyle(.borderedProminent)

            Text(viewModel.statusText)
                .font(.footnote)
                .foregroundStyle(.white.opacity(0.85))
        }
        .padding(16)
        .background(.ultraThinMaterial.opacity(0.75))
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }

    private var lobbyCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("房间列表")
                .font(.title2.bold())
                .foregroundStyle(.white)

            HStack(spacing: 12) {
                Button("刷新房间") {
                    viewModel.requestRooms()
                }
                .buttonStyle(.bordered)

                Button("创建房间") {
                    viewModel.createRoom()
                }
                .buttonStyle(.borderedProminent)
            }

            Text(viewModel.statusText)
                .font(.footnote)
                .foregroundStyle(.white.opacity(0.85))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(.ultraThinMaterial.opacity(0.75))
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }
}
