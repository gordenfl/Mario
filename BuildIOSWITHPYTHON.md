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

## 2. 应用目录里要放什么？（不能只放 `client_kivy`）

- **必须有**：仓库根目录的 **`main.py`** + **`client_kivy/`** + **`client/`**  
  - `client/`：贴图、关卡 JSON、`client/network` 联机协议等；只拷 `client_kivy` 会缺资源、缺网络包。
- **绝不能打进包**：任何 **`venv` / `.venv`**（例如 `client_kivy/.venv`）。里面的 `bin/python3` 等是 **符号链接**，同步进 `YourApp` 后，模拟器会报 **`invalid symlink`**，安装失败。

若你曾对 **`整个仓库根`** 执行 `toolchain create`，会把 `client_kivy/.venv` 一并拷进去 → 触发上述错误。

**推荐**：先用脚本生成「干净目录」，再对这个目录做 `toolchain create`：

```bash
chmod +x scripts/prepare_ios_app_folder.sh
./scripts/prepare_ios_app_folder.sh
```

会在 **`build/ios_app/`** 生成只含 `main.py`、`client/`、`client_kivy/`（已排除 `.venv` 等）的副本。下面第 5 步用这个路径的**绝对路径**。

---

## 3. 为什么要单独建 `~/kivy-ios-work`（与你现在的做法）

这样做是对的：**不要把 kivy-ios 的虚拟环境、`dist/`、`build/`、以及生成的 `mario-ios/` 塞进 Mario 仓库**，所以在你 **Home 下**建 **`~/kivy-ios-work`** 专门用来：

| 位置 | 里面有什么 |
|------|------------|
| **`~/kivy-ios-work/`** | Python venv、`pip install kivy-ios`、执行 **`toolchain build`** 产生的大量 **`dist/`、`build/`**、以及 **`toolchain create` 在当前目录生成的 `mario-ios/`** |
| **Mario 仓库里的 `build/ios_app/`** | 只由 **`./scripts/prepare_ios_app_folder.sh`** 生成，里面是 **`main.py` + `client/` + `client_kivy/`**（给 Xcode 同步用的「应用源码」） |

两者关系：**始终在 Mario 仓库里跑 prepare 脚本** → 再 **cd 到 `~/kivy-ios-work`，激活 venv**，用 **Mario 下 `build/ios_app` 的绝对路径** 去 create（工程会生成在 **当前目录**，即 `~/kivy-ios-work/mario-ios`，不会在仓库里）。

初始化一次即可：

```bash
mkdir -p ~/kivy-ios-work && cd ~/kivy-ios-work
python3.11 -m venv venv
source venv/bin/activate
pip install "Cython==3.0.11" kivy-ios
```

（完整顺序见下面 **§4 → §5**：必须先 **`toolchain build`**，再 **`prepare_ios_app`** + **`toolchain create`**。）

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

先执行 **`./scripts/prepare_ios_app_folder.sh`**，再使用 **`build/ios_app` 的绝对路径**（不要用仓库根目录，除非你已经删掉 `client_kivy/.venv`）：

```bash
# 应在已 activate 的 kivy-ios venv 里执行；当前目录一般为 ~/kivy-ios-work
toolchain create mario /Users/yiliu/Mario/build/ios_app
```

会在 **当前目录**（例如 `~/kivy-ios-work`）下生成 **`mario-ios/`**，**不会**出现在 Mario 仓库里。打开工程：

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
5. **相机相关 Purpose 字符串（上架 vs 本地调试）**  
   - **本游戏代码不调设备摄像头**（`Camera.py` 等是关卡视口滚动）。**Signing & Capabilities** 里也不要手动加 Camera 能力（你的截图里为空是对的）。  
   - **但**：Kivy / SDL 等 **静态链进去的库** 可能引用系统里与相机相关的符号，App Store 预检会报 **ITMS-90683**，邮件里写明：**即便应用不使用这些 API，只要二进制/SDK 触发了规则，仍须在 Info.plist 里提供 `NSCameraUsageDescription`**。这与「是否在 Capabilities 里打开相机」是两回事。  
   - **处理方式**：在 **`mario-Info.plist`**（名称以工程为准）的 `<dict>` 里 **增加**（不要删其它键）：
     ```xml
     <key>NSCameraUsageDescription</key>
     <string>Mario Fight does not use your camera for gameplay. This key is required because bundled third-party frameworks may reference camera-related system APIs.</string>
     ```
     也可直接复制仓库里的片段：**`ios/appstore_privacy_plist_fragment.xml`**。  
   - 以后若收到 **相册 / 麦克风** 同类邮件，再在同一 plist 里按邮件要求补 `NSPhotoLibraryUsageDescription` / `NSMicrophoneUsageDescription` 及对应英文说明即可。

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
| **Xcode 里 YourApp 没有 `.py`** | ① 终端执行 `./scripts/prepare_ios_app_folder.sh`，确认打印 **`OK: N Python files`**（N 应大于 0）。② **`toolchain create` 必须用 `build/ios_app` 的绝对路径**，不能用整个仓库根（除非你确认没有 `.venv`）。③ 若仍空：删掉旧的 **`mario-ios`** 目录，重新执行 **`toolchain create mario "/…/Mario/build/ios_app"`**。④ 若你改过 Build Phase：若有 **`compileall` + `find … -name '*.py' -delete`**，会把源码删掉 —— 删掉这类自定义脚本或改用官方默认。 |
| **ITMS-90683：Missing NSCameraUsageDescription** | 按 **§6 第 5 条**在 plist **增加**（不是删除）`NSCameraUsageDescription`；文案说明游戏本身不使用相机、因引擎/SDK 仍需声明。片段见 **`ios/appstore_privacy_plist_fragment.xml`**。 |
| **Redundant Binary Upload（已存在 build `1.1`）** | App Store Connect **按 Build 字符串去重**，同一 **Version**（如 1.1）下每次上传必须 **递增 Build**（`CFBundleVersion`）。在 Xcode：选中 Target → **General** → **Build** 改成未用过的值（例如 `1.1` → **`2`** 或 **`1.1.1`**），再 **Archive → Distribute**。Marketing **Version** 仍可保持 **1.1**。若 plist 里手写 **`CFBundleVersion`**，须与 Xcode **Build** 一致或改由 Xcode 统一管理。 |

---

## 10. 与旧文档的差异说明

此前文档里的 **`toolchain create mobile ../client`** 指向 pygame 客户端目录；现在联机推荐使用 **`client_kivy`** + **`client/`**，入口 **`main.py`** 在仓库根；**生成 Xcode 时用 `prepare_ios_app_folder.sh` 输出的目录**：**`toolchain create … "/…/Mario/build/ios_app"`**，不要对整个仓库根执行 create（易带入 `.venv`）。
