# 使用 kivy-ios 把 `client_kivy` 打成 iOS 工程（Xcode / 真机 / IPA）

本仓库的联机客户端在 **`client_kivy/`**，依赖 **Kivy + Pillow**，联机走 **`client/network`**（标准库 `socket` / `ssl`）。  
下面流程在 **Mac** 上完成：先用 **kivy-ios** 交叉编译 Python 与依赖，再 **生成 Xcode 工程**，最后在 Xcode 里签名、运行或导出 IPA。

---

## 1. 前置条件

- **macOS**，已安装 **Xcode**（建议最新稳定版）并接受许可：`sudo xcodebuild -license`
- **Xcode Command Line Tools**：`xcode-select --install`
- **Homebrew** 与编译依赖：

```bash
brew install autoconf automake libtool pkg-config
brew link libtool
```

- **Python 3.11**（与当前 kivy-ios 常用版本一致；勿混用已废弃的 Python 2）

```bash
pip3 install "Cython==3.0.11"
```

更多官方说明： [Kivy iOS 前置](https://kivy.org/doc/stable/guide/packaging-ios-prerequisites.html) 。

---

## 2. 仓库里已有 iOS 入口 `main.py`

kivy-ios 要求应用目录根目录有 **`main.py`**。  
仓库根目录已提供 **`main.py`**，会把 `sys.path` 指到本仓库并启动 `MarioFightKivyApp`。

生成 Xcode 工程时，请把 **整个 Mario 仓库根目录** 作为「应用目录」（内含 `client/`、`client_kivy/`、`main.py`），这样资源与网络代码路径与桌面一致。

---

## 3. 建议单独建目录放编译产物（可选）

在任意目录（例如家目录下）建空文件夹，专门跑 toolchain，避免污染仓库：

```bash
mkdir -p ~/kivy-ios-work && cd ~/kivy-ios-work
python3.11 -m venv venv
source venv/bin/activate
pip install "Cython==3.0.11" kivy-ios
```

---

## 4. 编译 iOS 依赖（recipe）

首次会比较久。一般需要 Python、OpenSSL、Kivy、Pillow（`client_kivy` 里 `PIL.Image` 用到了 Pillow）：

```bash
toolchain build python3 openssl kivy pillow
```

若某一步失败，可看终端报错；Pillow 在部分 Xcode 版本上会遇到已知问题，可到 [kivy-ios Issues](https://github.com/kivy/kivy-ios/issues) 搜对应关键字。

仅验证最小链路时，可先按官方文档试：

```bash
toolchain build kivy
```

再按需补：`toolchain build pillow` 等。

---

## 5. 生成 Xcode 工程

将 **`/绝对路径/到/Mario`** 换成你本机克隆路径（**必须是绝对路径**）：

```bash
toolchain create mario /Users/yiliu/Mario
```

会在 **当前目录** 下生成 **`mario-ios/`**（名称随 `create` 的第一个参数变化），其中有 **`mario.xcodeproj`**。

```bash
open mario-ios/mario.xcodeproj
```

说明（与官方一致）：每次在 Xcode 里 **Run**，会把「应用目录」里的代码同步进工程里的 YourApp 目录；**不要**只在 `mario-ios` 里改业务代码而不改仓库里的源文件，否则下次同步会覆盖。

---

## 6. Xcode 里必查项

1. **签名**：Targets → Signing & Capabilities → Team、Bundle Identifier（不要与别人冲突）。
2. **脚本沙盒**：若 Run Script 阶段复制代码失败，在 Build Settings 搜 **`ENABLE_USER_SCRIPT_SANDBOX`**，设为 **NO**（与旧版文档一致）。
3. **横屏**：Deployment Info 勾 **Landscape**（游戏为横屏虚拟分辨率 852×480）。
4. **连局域网 HTTP 服务器**（例如 `http://192.168.x.x:8765`）：默认 ATS 可能拦截非 HTTPS。在 **Info.plist** 增加 **App Transport Security**，例如允许任意加载（仅调试方便；上架前应收紧）：
   - `NSAppTransportSecurity` → `NSAllowsArbitraryLoads` = `YES`  
   或只为你的域名/IP 配例外。

---

## 7. 真机调试与导出 IPA

- **真机**：数据线连手机，选设备后点 Run。
- **IPA**：菜单 **Product → Archive**，归档完成后 **Distribute App**，选 **Development / Ad Hoc**（需在 Apple Developer 配好证书与两台手机的 **UDID** 或 App Store 流程）。

两台手机测试常用：**Ad Hoc** + **包含两台设备 UDID 的描述文件**，导出 IPA 后用 Apple Configurator、TestFlight 或企业分发工具安装（具体依账号类型而定）。

---

## 8. 更新依赖后刷新 Xcode 工程

若在 `toolchain create` **之后** 又多编译了 recipe（例如后来执行了 `toolchain build pillow`），在项目目录执行：

```bash
toolchain update mario-ios
```

再打开 Xcode 重新编译。

---

## 9. 常见问题

| 现象 | 方向 |
|------|------|
| `Application quit abnormally` | 看 Xcode 控制台日志；多为缺 recipe 或资源路径错误 |
| Pillow 编译失败 | 查 kivy-ios 版本与 Xcode 版本；Issues 里常有补丁说明 |
| 进游戏连不上服务器 | 检查 ATS、手机与服务器是否同网、防火墙；默认服务器 IP 在 `client_kivy/screens.py` / 环境变量 |

---

## 10. 与旧文档的差异说明

此前文档里的 **`toolchain create mobile ../client`** 指向 pygame 客户端目录；现在联机推荐使用 **`client_kivy`**，并且 **`main.py` 在仓库根目录**，应对 **`toolchain create ... /绝对路径/Mario`**，不要把应用目录设成单独的 `client/`。
