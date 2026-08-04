## 🔴 REQUEST_CHANGES — 纯文档 PR，但部署指南与真实 AirAccount KMS 不符

感谢整理这三篇全球网络调研。整体架构思路（香港 VPS + frp 主动出站绕过 GFW）成立，`china-kms-tunnel-setup.md` 的 frp 配置主体正确。但作为**给社区照着操作的部署指南**，有以下**已对照 AirAccount 真实代码验证**的 blocking 问题——照抄会失败或误导。

> 证据来源：`AirAccount/kms/deploy/topology-aastar-3node/node1-school-mx93.toml`、`kms/host/src/api_server.rs` 路由、`kms/README.md`。均已逐行核对。

### Blocking（Medium）

1. **[Med] `china-kms-tunnel-setup.md` Step2/3 — systemd 单元指向不存在的路径**
   `ExecStart=/opt/frp/frps|frpc -c /opt/frp/*.toml`，但安装步骤只 `tar` 解压后在解压目录 `./frps`，从未把二进制拷到 `/opt/frp/` → 按文档操作 systemd 单元第一次启动就失败。
   **Fix**: 在 `systemctl enable` 前补 `mkdir -p /opt/frp && cp frps frps.toml /opt/frp/`（frpc 同理）。

2. **[Med] `china-node-architecture.md` — KMS/UI/DVT 端口画反了**
   文档写 KMS=`:8080`、UI=`:3000`、DVT=`:9001`；真实部署是 **KMS=3000（只绑 127.0.0.1）、DVT=8080**（见 node1-school-mx93.toml）。与同 PR 的 `china-kms-tunnel-setup.md`（KMS `:3000`，正确）自相矛盾。照着架构文档把 frpc `localPort` 指向 8080 会连到 DVT 而不是 KMS。
   **Fix**: 统一为 KMS=3000，DVT/UI=8080；`cloudflare-tunnel-global-availability.md` 的 frp `localPort = 8080`（kms-node）同样应为 **3000**。

3. **[Med] `china-kms-tunnel-setup.md` — API 路径与 `/health` 期望返回值不符合真实 KMS**
   - 文档写 `POST /kms/CreateKey`、`POST /kms/Sign`；真实路由是**根路径** `POST /CreateKey`、`POST /Sign`（`warp::path("CreateKey")`，无 `/kms` 前缀；`/kms/sign` 小写形式存在但 `/kms/CreateKey` 不存在）。
   - Step6 `期望返回：{"status":"ok","version":"0.27.3",...}`；真实 `/health` 返回 `{"status":"healthy","service":"kms-api","version":KMS_VERSION,...}`，当前版本 **0.29.0**。
   **Fix**: 去掉 `/kms/` 前缀（含 Step2 架构图），按真实 JSON 修正期望输出。

4. **[Med] `china-node-architecture.md` — 交叉引用指向不存在的文件**
   `详细部署步骤见：backlog/docs/doc-8 - 🌐-China-KMS-Tunnel-Setup.md` —— `backlog/docs/` 只有 doc-1/doc-6/doc-7，**没有 doc-8**；实际文件在 `research/global-network/china-kms-tunnel-setup.md`（frontmatter `id: doc-8`）。
   **Fix**: 修正引用路径。

### 建议一并处理（Low）

- **[安全] 三篇指南都把签名端点（`POST /CreateKey`、`/sign`）通过隧道暴露到公网，却从未声明 KMS API 自身必须启用鉴权**（x-api-key / AWS-KMS AccessKey）。若按文档裸奔部署，将变成一个**未鉴权签名预言机**——强烈建议在指南里加一段「KMS 侧鉴权必配」。R1b 安全通道对此返回 0 发现，是我方补扫抓到的。
- Step5 TLS：`[[httpPlugins]]` 不是 frp vhost 证书配置位；真实配置是 frps.toml `vhostHTTPSCertFile`/`vhostHTTPSKeyFile`，当前 certbot 证书从未接进 frps.toml。
- `cloudflare-tunnel-global-availability.md` frp 配置用**旧版顶层 `token =`**（pre-v0.52），与 setup.md 钉的 v0.61.1 `auth.token =` 不一致，照抄会被静默忽略。
- `[webServer] addr="0.0.0.0" port=7500` 无凭据 → frp 面板默认 admin/admin 暴露公网。
- `china-node-architecture.md` 双 relay 示例 `serverAddr` 重复 + 用 `;` 注释 → 非法 TOML；frp 单进程不支持多 server。
- wstunnel 示例 `wss://` 需 TLS 但未配证书，客户端缺 `--tls-verify-disable`。
- Step6 curl 示例 body 带尾逗号 + `...` → 非法 JSON。
- 三篇对 KMS API 表面描述互相矛盾（`/kms/Sign` vs `/sign`+/account/register vs 根 `/CreateKey`，其中 `/account/register` 不存在），建议统一以真实 repo 为准。

### 轮次信息
`[4-round, v4-pipeline]` — DeepSeek R1a+R1b（双通道并行）→ Opus R2 战略评审（独立读 diff + 验证真实 repo）→ Codex R3 PK（gpt-5.5，确认全部 4 项 blocking、0 挑战）→ Opus R4 终裁 + 补扫。

**结论：REQUEST_CHANGES。** 修完上面 4 项 blocking（+建议的低级项）即可合入。这是研究/部署文档，但文档里每个照抄命令都应是 ground truth——建议以 `~/Dev/aastar/AirAccount/kms/` 真实部署为准统一三篇。
