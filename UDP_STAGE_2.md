# Stage 2 行动计划（高频状态迁移到 UDP）

目标：让玩家位置/速度/朝向等高频状态通过 UDP 广播，TCP 只做偶发事件和权威快照，保证画面流畅同时容忍丢包。

---

1. 数据结构设计

* UDP PlayerState 包（客户端 → 服务器）：

    ```
    | msg_type=0x01 | client_id | seq | timestamp |  | x (int16) | y (int16) | vx (int16) | vy (int16) |  | flags (uint8) | facing (int8) |
    ```

  * 单位采用 1/32 像素（值 = 实际像素 * 32）降低误差。
  * flags: bit0=在地面、bit1=跳跃键、bit2=死亡、bit3=开火。

* 服务器缓存：Room 维护 latest_states[player_id] = {position, velocity, timestamp}。

2. 客户端发送逻辑

* 更新 NetworkClient：
  * 新增 send_udp_player_state(state_dict)，把 mario 的位置/速度/标志编码发出。
  * 在 run_game 主循环中（更新/绘制之后），调用 network.send_udp_player_state(...)。
  * 控制发送频率，每帧或隔帧（例如 60fps 下改为每 2 帧发送一次，后续可调）。

* 添加状态收集函数（现有 collect_local_state 可复用），追加 flags 与 facing。

3. 服务器接收与转发

* 在 handle_udp_datagram 中处理 MSG_PLAYER_STATE：
  * 校验握手；若 room.game_over，忽略。
  * 记录 last_seq，丢弃旧包。
  * 更新 room.latest_states[client_id] 与 timestamp。
  * 立即通过 UDP 广播给其它玩家（用新的 send_udp_state(room, source_client_id, payload)）。
* 对迟到/失序包：以 seq 或 timestamp 判定，忽略旧包即可。

4. 客户端接收 & 插值

* NetworkClient.poll_udp() 返回事件，run_game 里新增处理：
  * 对 MSG_PLAYER_STATE 调用 remote_players[...] .apply_udp_state(payload)。
  * RemotePlayer 新增预测/插值逻辑：存储上一个 UDP 位置 + 时间戳，用线性插值更新绘制位置；若长时间未更新，则逐步靠向服务器快照。

* 继续保留 TCP state_update（权威快照）。收到后对 remote_player 进行纠正（Lerp 或直接设置）。
* 对本地玩家（客户端自己）暂不过滤；服务器稍后发送快照时如需要纠正，再做帧差补偿。

5. 定时权威快照（TCP）

* 服务器每 250 ms 发送一次现状给所有客户端：包含每个玩家的 position、velocity、hp、dying 等。
  * 可复用现有 state_update 的结构，只是由服务器驱动。

* 客户端收到 TCP 快照时：更新 remote player 的权威位置（与 UDP 插值结合：如果误差 > 阈值，逐渐拉回；否则保持当前预测）。

6. 可靠性/心跳

* UDP 包内已有 timestamp/seq，客户端可以检测长时间未收到某玩家数据，自动使用最后快照或停止预测。
* 保留 Stage1 的 UDP HELLO/ACK 机制；必要时可在 Stage2 加一个简单心跳（如本地每秒发一次 MSG_PLAYER_STATE 即可起心跳作用）。

7. 交付与测试

* 单机模拟：在服务器端加日志验证广播；pilots 观察 remote player 动作是否顺畅。
* 人为制造丢包（tc netem 或 macOS pfctl）确认容忍度。
* Stage2 完成后保留 TODO Stage2 项目状态更新，准备 Stage3 (火球/action) 时避免冲突。

---

如果计划 OK，我将按此顺序开始实现 Stage2 的代码调整。需要任何细节调整或额外字段（例如加 HP、动画状态旗帜）再告诉我。我会在 todo 中追踪 Stage2 实现进度。
