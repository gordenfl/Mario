# Stage 1：网络层双通道结构改造计划

目标：保持现有 TCP 行为的同时，把 UDP 通道的基础“骨架”搭好，后续阶段可以逐步迁移高频消息。

1. 客户端侧

- 新增模块 client/network/udp_client.py

  - 提供 UdpClient 类，封装：
    - open(token: str, client_id: int, server_host: str, server_port: int)：创建非阻塞 UDP socket 并发送握手包。
    - send(packet: bytes) / sendto(msg_type, payload_dict)：序列号递增、时间戳自动附带。
    - poll(handle_func)：读取所有可用数据，解码后回调。
    - close()：关闭 socket。
  - 统一管理序号、时间戳、握手状态。消息打包先用 struct，暂不实现所有类型，只保留握手和空壳。

- 重构 NetworkClient

  - 拆为 TcpClient（当前逻辑）+ 持有 UdpClient 实例。
  - 新增方法：

    ```PY
        def enable_udp(self, token: str, client_id: int, port: int): ...     
        def send_udp_state(self, state_dict): pass #Stage 1 先留空实现     
        def poll_udp(self): pass
        ```

  - 现阶段 poll() 仍只处理 TCP；poll_udp() 在主循环中单独调用（暂时不会有消息）。

- 客户端握手管理

  - 登录/加入房间成功后，服务器通过 TCP 回复 UDP 参数（token、client_id、port）。
  - run_game() 内部在实例化 Mario 后调用 network.enable_udp(...)，并在游戏主循环尾部调用 network.poll_udp()。

- 数据结构定义

  - 在 client/network/protocol.py（新文件）中定义常量：

        ```PY
        MSG_HANDSHAKE = 0x00     MSG_ACK = 0x80     MSG_STATE = 0x01     MSG_PROJECTILE = 0x02     MSG_ACTION = 0x03     ...
        HEADER_STRUCT = struct.Struct("!BBH I")
        ```

  - pack_message(msg_type, client_id, seq, timestamp, payload_bytes) / unpack_header(data) timestamp

        ```
            MSG_STATE = 0x01     
            MSG_PROJECTILE = 0x02     
            MSG_ACTION = 0x03     
            ...     
            HEADER_STRUCT = struct.Struct("!BBH I")  # type, client_id, seq, timestamp
        ```

  - pack_message(msg_type, client_id, seq, timestamp, payload_bytes) / unpack_header(data) 函数。

- UI/业务代码无改动
Stage1 仅确保结构和握手完成，不改变现有行为。

----

2. 服务器侧

- 新增 udp_server.py 或在 server/server.py 中创建 UDP Endpoint
  - 使用 asyncio.create_datagram_endpoint 创建 UdpProtocol：
    - datagram_received(data, addr)：解析头部，校验 token（从房间的 client_udp_info 查找）。
    - Stage1 先只记录 client_id -> addr 映射，并回一次简短 ACK（例如 msg_type=0x80）。
  - 将 GameServer.start() 中 asyncio.start_server() 后追加 UDP endpoint 启动。

- 房间结构调整

  - Room 增加字段 udp_clients: Dict[int, UdpClientInfo]，包含：

    - address, token, last_seq, last_timestamp.
    - 在 handle_login / handle_join_room / notify_room_ready 中生成 token，并通过 TCP 把 token/port/client_id 下发给对应客户端。
- 管理类方法

  - 新增 register_udp_hello(room_id, client_id, addr)：校验 token 后写入映射。
  - send_udp(room, client_id, msg_type, payload)：Stage 1 先只打印日志或发送心跳，不做真实数据。
- 消息协议

  - 与客户端共享 protocol.py（可放在 common 目录或 duplications Stage1 先简单 copy —— 之后再提取公共包）。

- 保持现有 TCP 逻辑

  - 所有实际的状态更新仍走 TCP，直到 Stage2 正式迁移。

----

3. 代码调整点清单

    |文件 |操作|
    |-|-|
    client/network/__init__.py|导入新类
    client/network/__init__.py|导出新类
    client/network/protocol.py|定义 UDP 常量/函数
    client/network/udp_client.py|新建、实现握手/发送/接收骨架
    client/network/network_client.py|重构为组合模式，新增 enable/poll UDP 接口
    client/main.py | 在 run_game() 中调用 enable_udp 和 poll_udp（Stage1 暂无实际消息处理）
    server/server.py | 引入 UDP endpoint 创建、房间 token 下发、握手处理
    common 目录（可选）| 共享协议常量；暂时可以重复定义，Stage2 时再抽离.

---

4. Stage1 验收标准

- 游戏仍可通过 TCP 正常登录/对战。
- 服务器日志看到客户端 UDP 握手成功（打印 client_id, addr）。
- 客户端主循环无异常，多执行几分钟无资源泄漏。
- 新增结构未经实现的 send_udp_state 等方法暂时为空，不影响现有逻辑。

---

如果这个结构 OK，我们就可以着手实现 Stage1 的代码（我可以直接创建所需文件和骨架，保证编译通过）。需要我继续动手的话告诉我。
