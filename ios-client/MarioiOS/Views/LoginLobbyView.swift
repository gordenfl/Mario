import SwiftUI

struct LoginLobbyView: View {
    @EnvironmentObject private var viewModel: GameViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Super Mario Multiplayer (iOS)")
                .font(.title2)
                .bold()

            TextField("服务器地址", text: $viewModel.host)
                .textFieldStyle(.roundedBorder)

            TextField("端口", text: $viewModel.portText)
                .textFieldStyle(.roundedBorder)
                .keyboardType(.numberPad)

            TextField("用户名", text: $viewModel.username)
                .textFieldStyle(.roundedBorder)

            HStack(spacing: 12) {
                Button("登录") {
                    viewModel.connectAndLogin()
                }
                .buttonStyle(.borderedProminent)

                if viewModel.screen == .lobby {
                    Button("刷新房间") {
                        viewModel.requestRooms()
                    }
                    .buttonStyle(.bordered)

                    Button("创建房间") {
                        viewModel.createRoom()
                    }
                    .buttonStyle(.bordered)
                }
            }

            Text(viewModel.statusText)
                .font(.footnote)
                .foregroundStyle(.secondary)

            if viewModel.screen == .lobby {
                List(viewModel.rooms) { room in
                    HStack {
                        Text("房间 \(room.roomId)")
                        Spacer()
                        Text(room.players.joined(separator: ", "))
                            .foregroundStyle(.secondary)
                    }
                    .contentShape(Rectangle())
                    .onTapGesture {
                        viewModel.joinRoom(room.roomId)
                    }
                }
            } else {
                Spacer()
            }
        }
        .padding(20)
    }
}
