import SwiftUI

struct LoginLobbyView: View {
    @EnvironmentObject private var viewModel: GameViewModel

    var body: some View {
        ZStack {
            backgroundLayer

            VStack(spacing: 16) {
                if viewModel.screen == .login {
                    loginView
                } else {
                    lobbyView
                }

                Spacer(minLength: 0)
            }
            .padding(20)
        }
    }

    private var backgroundLayer: some View {
        ZStack {
            LinearGradient(
                colors: [Color(red: 0.03, green: 0.04, blue: 0.09), Color(red: 0.08, green: 0.09, blue: 0.16)],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            .ignoresSafeArea()

            RadialGradient(
                colors: [Color.white.opacity(0.07), Color.clear],
                center: .center,
                startRadius: 30,
                endRadius: 380
            )
            .ignoresSafeArea()
        }
    }

    private var loginView: some View {
        VStack(spacing: 18) {
            Text("超级马里奥 - 联机版")
                .font(.custom("STKaiti", size: 58))
                .foregroundStyle(.white)
                .shadow(color: .black.opacity(0.35), radius: 8, y: 3)

            Text("请输入用户名登录游戏")
                .font(.custom("STKaiti", size: 42))
                .foregroundStyle(Color.white.opacity(0.7))
                .shadow(color: .black.opacity(0.3), radius: 4, y: 2)

            TextField("", text: $viewModel.username, prompt: Text("输入用户名...").foregroundStyle(Color.white.opacity(0.45)))
                .font(.custom("STKaiti", size: 42))
                .foregroundStyle(.white.opacity(0.88))
                .padding(.horizontal, 20)
                .padding(.vertical, 10)
                .frame(width: 540)
                .background(
                    RoundedRectangle(cornerRadius: 6)
                        .fill(Color.black.opacity(0.28))
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 6)
                        .stroke(Color.white.opacity(0.22), lineWidth: 1)
                )

            Button("进入大厅") {
                viewModel.connectAndLogin()
            }
            .font(.custom("STKaiti", size: 44))
            .foregroundStyle(.white)
            .frame(width: 300, height: 72)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(Color(red: 0.18, green: 0.53, blue: 1.0))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(Color.white.opacity(0.15), lineWidth: 1)
            )

            Text(viewModel.statusText)
                .font(.system(size: 14, weight: .medium))
                .foregroundStyle(.white.opacity(0.7))
                .lineLimit(2)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(.horizontal, 24)
    }

    private var lobbyCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("欢迎, \(viewModel.username)")
                .font(.custom("STKaiti", size: 56))
                .foregroundStyle(.white)

            Text("点击房间加入，或创建新房间。")
                .font(.custom("STKaiti", size: 42))
                .foregroundStyle(.white.opacity(0.72))

            Text("当前可加入房间: \(viewModel.rooms.count) 个")
                .font(.custom("STKaiti", size: 46))
                .foregroundStyle(Color(red: 0.89, green: 0.89, blue: 0.5))
                .padding(.top, 4)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var lobbyView: some View {
        VStack(spacing: 0) {
            lobbyCard
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.top, 14)

            if !viewModel.rooms.isEmpty {
                ScrollView {
                    VStack(spacing: 10) {
                        ForEach(viewModel.rooms) { room in
                            Button {
                                viewModel.joinRoom(room.roomId)
                            } label: {
                                HStack {
                                    Text("房间 \(room.roomId)")
                                        .font(.system(size: 20, weight: .semibold))
                                        .foregroundStyle(.white)
                                    Spacer()
                                    Text("\(room.players.count) 人")
                                        .font(.system(size: 16, weight: .medium))
                                        .foregroundStyle(.white.opacity(0.8))
                                }
                                .padding(.horizontal, 14)
                                .frame(height: 46)
                                .background(
                                    RoundedRectangle(cornerRadius: 8)
                                        .fill(Color.black.opacity(0.25))
                                )
                                .overlay(
                                    RoundedRectangle(cornerRadius: 8)
                                        .stroke(Color.white.opacity(0.15), lineWidth: 1)
                                )
                            }
                        }
                    }
                    .padding(.top, 10)
                }
                .frame(maxHeight: 190)
            }

            Text(viewModel.statusText)
                .font(.system(size: 14, weight: .medium))
                .foregroundStyle(.white.opacity(0.68))
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.top, 10)

            Spacer()

            HStack(spacing: 34) {
                lobbyActionButton(title: "刷新") {
                    viewModel.requestRooms()
                }
                lobbyActionButton(title: "创建房间") {
                    viewModel.createRoom()
                }
                lobbyActionButton(title: "退出登录") {
                    viewModel.shutdown()
                    viewModel.rooms = []
                    viewModel.screen = .login
                    viewModel.statusText = "请输入用户名并连接服务器"
                }
            }
            .padding(.bottom, 16)
            .padding(.top, 12)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 14)
    }

    private func lobbyActionButton(title: String, action: @escaping () -> Void) -> some View {
        Button(title, action: action)
            .font(.custom("STKaiti", size: 44))
            .foregroundStyle(.white)
            .frame(width: 210, height: 72)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(Color(red: 0.23, green: 0.56, blue: 0.97))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(Color.white.opacity(0.18), lineWidth: 1)
            )
    }
}
