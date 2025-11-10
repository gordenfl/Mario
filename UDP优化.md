# UDP优化

## UDP 数据包格式建议

所有 UDP 数据包采用二进制结构，首部字段一致，便于扩展：

| 偏移 | 字段 | 长度 | 说明 |
| --- | ---- | --- | --- |
|0|version|1 B|协议版本号（目前为 0x01）|
|0|msg_type|1 B|消息类型（0x01 状态、0x02 火球、0x03 动作请求、0x7F 快照确认等）|
|1|client_id|1 B|玩家在房间内的编号（0/1，登录后由服务器通过 TCP 下发）|
|2|seq|2 B|递增序号（每类消息独立计数），用于丢包检测/重复过滤|
|4|timestamp|4 B|客户端发送或服务器生成的毫秒时间戳（相对值即可）|
|8|payload …|可变|不同消息类型的结构|

示例负载：

0x01：玩家状态 PlayerState

    | vx (int16) | vy (int16) | x (int16) | y (int16) | facing (int8) | flags (int8) |

* 速度、位置使用 1/32 像素单位编码（乘 32）。
* facing：-1/0/1。
* flags：bit0=跳跃中，bit1=开火中，bit2=落空通知等。
* 服务器处理：若丢包则按最近状态插值；定期通过 TCP 发送权威快照纠正。

0x02：火球/抛射物 ProjectileState

    | projectile_id (uint16) | owner_id (uint8) | state_flags (uint8) || x (int16) | y (int16) | vx (int16) | vy (int16) |

* state_flags 表示 spawn / update / despawn。
* spawn 消息可附带冷却校验；命中结果仍应通过 TCP 可靠上报。

0x03：动作请求 ActionRequest

    | action_type (uint8) | param (uint8) | reserved (uint16) |

* 例如 action_type=1 射击、2 跳跃。服务器可快速响应，必要时用 TCP 做最终确认。

0x7F：快照确认 SnapshotAck（客户端→服务器，用来报告已收到的权威快照）

    | snapshot_id (uint16) |

> 补充：可以预留 0xFE/0xFF 做心跳或调试。

## 重构计划

### 阶段 0：准备

1. 在 NetworkClient 中分离 TCP 与 UDP 逻辑，准备 UdpClient 封装（可用 socket 非阻塞 + 单独线程或 asyncio datagram）。
2. 服务器 GameServer 在启动时再创建 UDP endpoint（asyncio.create_datagram_endpoint），统一交给房间管理。

### 阶段 1：UDP 握手与会话绑定

1. 玩家通过 TCP 登录、进入房间后，服务器下发：
    * client_id（0 或 1）
    * udp_token（随机 32bit，用于 UDP 包认证）
    * udp_port（服务器监听端口）

2. 客户端建立 UDP socket，发送 hello 包：msg_type=0x00，包含 token。
3. 服务器验证 token、记下 (room_id, client_id, udp_address) 映射；回 ACK 同时告知当前帧号。
3. 若 token 不匹配则丢弃。

### 阶段 2：高频状态迁移

1. 将 TCP 中 state_update 的发送改为 UDP PlayerState 包，每帧（或每 2 帧）发送。

2. 服务器收到后更新玩家的预测状态缓存，并立即转发给同房间其他玩家（可选择直接广播 UDP）。
3. 仍保留每 200~250ms 的 TCP 权威快照（含位置、速度、HP、死亡等）用于纠正。

### 阶段 3：火球等附加动作

1. 射击请求/火球轨迹采用 UDP：
    * 客户端先发 ActionRequest（射击）。
    * 服务器验证冷却后广播 ProjectileState spawn。
    * 定期（或加速后）继续用 UDP update，最终 despawn。

2. 火球命中、HP 变更仍通过 TCP 确认；UDP 可以附带“命中尝试”，服务器判定后用 TCP 通知。

### 阶段 4：补偿与容错

1. 客户端维护远端玩家状态队列，接收 PlayerState 后做插值/外推。
若 timestamp 滞后或跳跃过大，则等下一个 TCP 快照到来时矫正（可逐渐 lerp）。
2. 对于本地玩家，被 TCP 快照纠正时根据 timestamp 和预测位置做帧差补偿（限制一次矫正的最大距离，超过阈值瞬移）。

### 阶段 5：可靠性细节

1. UDP 包带 seq，服务器记录最近 seq；如果重复/过旧则丢弃。
2. 客户端根据服务器广播的 seq 判断是否丢包，必要时请求重发（可新增短消息 0x10 “ResendRequest”）；或者直接等待下次快照修复。
3. 添加轻量心跳：客户端每秒发送 UDP ping（0x0F），服务器回 pong；若连续多次未收到，判定失联并从 TCP 侧通知。

### 阶段 6：测试与优化

1. 在本地引入模拟丢包/延迟工具（如 tc netem）检查体验。
2. 优化包频率（例如本地无移动可降频发送）。
3. 打包时确保 UDP、TCP 端口配置和文档更新。
