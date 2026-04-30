# Mario iOS Client (SwiftUI)

这是基于当前 Python 客户端协议做的 iOS 版本基础实现，已对齐：

- TCP: JSON + `\n` 分隔消息（`login`/`list_rooms`/`create_room`/`join_room`/`leave_room` 等）
- UDP: 与现有 `client/network/protocol.py` 一致的 header 和 payload 编码
- 场景: 登录 -> 大厅 -> 游戏（简化渲染）

## 目录

- `MarioiOS/MarioiOSApp.swift`: App 入口
- `MarioiOS/ContentView.swift`: 场景切换
- `MarioiOS/Networking/`: TCP/UDP 与二进制协议
- `MarioiOS/ViewModels/GameViewModel.swift`: 业务状态和消息处理
- `MarioiOS/Views/`: 登录大厅 UI、游戏画布和触控输入

## 在 Xcode 中运行

1. 新建一个 iOS App（SwiftUI + Swift）。
2. 将 `ios-client/MarioiOS/` 下所有 `.swift` 文件拖进项目 target。
3. 运行你的 Python 服务器（默认 `8765`）。
4. 在 iOS App 里输入服务器地址与用户名，登录后创建或加入房间。

## 当前实现边界

- 已实现：房间流程、TCP 消息处理、UDP 握手、玩家状态同步、发射动作上报。
- 简化项：暂未移植原 Pygame 完整关卡渲染、物理碰撞、道具/砖块实体系统。

如果你要，我下一步可以继续把 iOS 客户端升级到 SpriteKit 版本，把地图、摄像机、碰撞与子弹表现补齐，做到更接近现在的 PC 客户端体验。
