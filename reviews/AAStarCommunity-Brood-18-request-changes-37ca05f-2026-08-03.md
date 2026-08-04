## 🔴 REQUEST_CHANGES — round-2 的 7/8 已修干净，但本轮新引入 1 处事实错误，且 443 拓扑矛盾 + KMS 鉴权缺口仍未收敛

感谢 `37ca05f`。**上轮 8 项里 7 项已确认修复**（均对照真实 AirAccount 代码逐行验证）：phantom UI:8080 已删（内置 UI 真实路由 `/`、`/test`、`/portal` 均在 :3000）、`POST /Sign` 根路径大写正确（api_server.rs:6726，小写 `/sign` 是 :3100 回环 BLS signer）、`POST /CreateKey` 真实、nginx 改根路径转发、curl body 与 `kms/test-full-api.sh:85-89` 逐字一致、`auth.token` 段正确、webServer 已绑 127.0.0.1 加口令。

**但本轮 fix 在它要修对的那个 TLS 段落里引入了一处新的错误事实，另外两个跨轮问题依然在。** 均已对照真实代码 / frp 官方文档验证。

### Blocking

1. **[Sec] 三篇指南仍全程未提 KMS API 鉴权（第 3 轮）——照抄必 401，且可能变成公开签名预言机**
   真实 KMS 是 **fail-closed**：`api_server.rs` 的 `db_api_key_filter` 一旦 DB 有 key 就强制校验 `x-api-key`；未 provision 时打印 *"all requests will be REJECTED until you run `kms-admin api-key generate` or set `KMS_API_KEY`"*。`kms/host/src/bin/api_key.rs` 提供 CLI，`kms/test-full-api.sh:7,21,42,108` 每条受保护路由都带 `-H "x-api-key: $API_KEY"`。
   **文档现状**：Step 6 的 `POST /CreateKey` curl 没带 `x-api-key`——照抄直接 401；若读者为了"跑通"去开 `KMS_ALLOW_OPEN_MODE=1`，公开隧道就成了**开放签名预言机**。
   **Fix**: 在暴露隧道前加**必做 Step**——IMX93 上 `kms-admin api-key generate`（或 export `KMS_API_KEY`），并在 CreateKey/Sign 测试 curl 里加 `-H "x-api-key: $KMS_API_KEY"`。

2. **[Med] `china-kms-tunnel-setup.md` Step5 note — 本轮引入的错误事实：frps 并非"没有 vhost 证书字段"**
   文档写 *"frps.toml **没有** `vhostHTTPSCertFile`/`vhostHTTPSKeyFile` 这类字段…只有 frpc 端插件这一条路"*——**错误**。frp v0.52+ 的 frps 明确支持 `vhostHTTPSCertFile`/`vhostHTTPSKeyFile`（服务端终结 TLS，见 frp server-config 文档）。`https2http` 是**可行路径之一**，不是唯一路径。已选的机制本身正确（frpc 插件终结 + 明文转发 :3000），错的是"没有/只有"这个绝对化表述，且与上轮 finding #8 的整改口径直接矛盾。
   **Fix**: 一行改——改为"两条路径都存在：frps 侧 `vhostHTTPSCertFile`/`vhostHTTPSKeyFile` 服务端终结，或 frpc 侧 `https2http` 插件终结；本文档选 frpc 端，因为证书要留在 IMX93（NAT 后）。"

3. **[Med] 跨文档 :443 归属矛盾 — nginx 与 frps 不可能同时占 443**
   - `china-kms-tunnel-setup.md` frps.toml：`vhostHTTPSPort = 443`（frps 自己占 443，https2http 插件在 frpc 终结 TLS）
   - `china-node-architecture.md`：`nginx :443 /* → frp → MX93:3000` + Path A "nginx 直接转发根路径 → frp server"
   两者描述的是**互斥的 TLS 终结拓扑**——frps 占 443 则 nginx 无法再 bind 443。nginx 块本轮被改过（`/api/*`→`/*`），但没有和 setup 文档的 https2http 流程对齐。
   **Fix**: 选一种拓扑并在两篇里统一。**推荐删掉 nginx**：KMS 是根路径服务，nginx 按路径路由本来就无意义；DNS 直指 VPS:443 → frps → 隧道 → frpc 插件终结 → :3000。同步改架构图 + Path A step 3 + Path C。

### 上轮修复确认（7/8）
✅ phantom UI:8080 删除，内置 UI `/`、`/test`、`/portal` 真实（api_server.rs:6435/6451/6454）
✅ `POST /Sign` 根路径大写（api_server.rs:6726）；`POST /CreateKey` 真实（6679）；`/account/register` 已删
✅ nginx 根路径转发、无 /api 前缀
✅ Step6 curl body 与 `test-full-api.sh:85-89` 逐字一致（ECC_SECG_P256K1 / Origin EXTERNAL / PasskeyPublicKey=04+64字节）+ jq 校验提示
✅ `auth.token` 进 [auth] 段（frp v0.52+）；webServer 127.0.0.1 + user/password

### Suggestions
- F2 改写的同一行里，`[[httpPlugins]]` 被描述成"给 dashboard/OIDC 用"不准确——它是 frps 的 vhost-HTTP 鉴权插件中间件钩子，跟 dashboard 无关，顺手改准。
- certbot `--manual --preferred-challenges dns` 会阻塞等 TXT 记录——注明要建 `_acme-challenge` 记录后回车；域名在 CF 上可直接 `--dns-cloudflare`。
- Step 3 的 `localIP/localPort` 与 Step 5 插件版同名 proxy 并存，逐字照抄可能同时写入（frp 会拒绝该 proxy）——建议 Step 3 直接给插件版，或注明"删掉 localIP/localPort 两行"。
- "简化验证"的 tcp 裸转发会短暂把明文 KMS 暴露到 VPS 公网 remotePort——建议限定防火墙来源或注明验证完立即移除。

### 轮次信息
`[4-round, v4-pipeline]` — DeepSeek R1a+R1b（`deepseek-v4-flash`，双通道并行）→ Opus R2 战略评审（独立读 diff + 对照真实 AirAccount 代码）→ Codex R3 PK（gpt-5.5 / codex exec v0.145.0，**确认全部 3 项、0 挑战**）→ Opus R4 终裁 + 补扫。

**结论：REQUEST_CHANGES。** 7/8 修得干净；剩下的是：① 把 `kms-admin api-key generate` + `x-api-key` 头补成必做 Step（这是第 3 轮没动的安全缺口），② 修掉 Step5 新引入的错误绝对化表述，③ 统一 :443 拓扑（建议删 nginx）。①②③ 都是小文本修改，一轮可收敛。
