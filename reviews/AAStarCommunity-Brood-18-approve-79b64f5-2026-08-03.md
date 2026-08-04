## ✅ APPROVE — round-3 三个 blocking 全部解决，其中 F2 系上轮误报、本轮作者正确反转

对 `37ca05f` 的增量复审（`79b64f5`）。新增内容逐项对照 AirAccount KMS 源码 / frp 上游源码机械验证。

### Round-3 blocking findings 裁决

**F1 [Sec] KMS API 鉴权步骤缺失 → ✅ RESOLVED（源码逐项验证）**
- 新增 Step 6「配置 KMS API 鉴权（暴露公网前**必做**）」，Step 7 测试 curl 补 `-H "x-api-key: $KMS_API_KEY"`，三篇 docs 同步加鉴权说明。
- `db_api_key_filter` 真实 fail-closed（api_server.rs:5890）：有 key 则强制校验 `x-api-key`，缺失/非法 → `ApiError("Missing API key")` → HTTP **401**（api_server.rs:5793 `UNAUTHORIZED` 分支）——doc「漏带直接 401」准确。
- `/health` 无 `api_key_filter`（api_server.rs:6522）开放路由；`/CreateKey`（6674）/`/Sign`（6726-6728）/`/KeyStatus` 等均挂 filter——doc 声称的受保护路由集合准确。
- `KMS_ALLOW_OPEN_MODE=1` = 关闭鉴权 DEV/TEST ONLY（api_server.rs:6412/6417）；`KMS_API_KEY` env 回退（6408）；REJECT 日志引文与源码逐字一致（6421）。
- `api-key generate --label "cn-community-relay"` 命令真实（bin/api_key.rs:28-40）；key 格式 `kms_`+32hex（db.rs:1411）；只回显一次不可找回（api_key.rs:44）；`/usr/local/bin/api-key` 由 `kms/scripts/deploy.sh:63-65,99` 安装。全部命中。

**F2 [Med] frps vhost TLS 终结 → ✅ RESOLVED（上轮误报，作者反转正确）**
- 上轮 round-3 声称 frp frps 支持 `vhostHTTPSCertFile`/`vhostHTTPSKeyFile` 服务端 TLS 终结——**这是上轮的误报**，本轮作者反转方向。
- 机械验证（frp v0.61.0 源码 + 全仓库 code search）：`ServerConfig`（pkg/config/v1/server.go）只有 `vhostHTTPPort`/`vhostHTTPTimeout`/`vhostHTTPSPort`，全仓库对 `vhostHTTPSCertFile`/`vhostHTTPSKeyFile` **0 命中**；issue #3007 正是「frps 服务端终结 SSL」的 feature request，从未实现、stale 关闭。作者本轮改写的「frps 不做服务端 vhost TLS 终结，证书走 frpc 端 `https2http`/`https2https` 插件（`crtPath`/`keyPath`，proxy_plugin.go:120-127）」及「`[[httpPlugins]]` 是 manager 插件（`HTTPPluginOptions{name,addr,path,ops}`，common.go:128-134），与 dashboard/证书无关」全部属实。
- **按误报反转处理，不惩罚作者；在 PR 评论里明确认账。**

**F3 [Med] :443 归属矛盾 → ✅ RESOLVED（三篇统一）**
- nginx 全部删除（剩余 3 处引用均为「无 nginx」否定式）；frps 独占 :443——setup doc frps.toml `vhostHTTPSPort=443`（line 106）与 cloudflare doc 新增 `vhostHTTPSPort = 443` 一致；架构图 + Path A + Path C 统一为「frps :443 → 隧道 → frpc `https2http` 插件终结 TLS → MX93:3000」。Step 编号 1-7 干净无重复/断层。

### Suggestions（本轮新，非阻塞）
- Step 6 `KMS_API_KEY` 一句建议拆清：env 回退是**服务端（IMX93 进程环境）**机制（api_server.rs:6408）；客户端 `export KMS_API_KEY=...` 只用于拼 `-H x-api-key` 头，export 本身不代表已鉴权——可加半行注明，防读者漏掉 header。
- 可加半行：`api-key generate` 要跑在 IMX93 且与 server 用同一 `KMS_DB_PATH`，否则 key 落错 kms.db → Step 7 仍 401（doc 已写「在 IMX93 上生成」，且 api-key（bin/api_key.rs:11-19）与 server（api_server.rs:6333-6339）默认路径解析一致，风险低）。
- 观察（KMS 源码侧，非 doc 缺陷）：启动日志里的 `kms-admin api-key generate` 子命令实际不存在（`kms-admin` 二进制是别的管理子命令，生成工具是 `api-key`）——doc 忠实引用日志且随后给了正确的 `api-key generate` 命令，读者不会走偏；可顺手改 KMS 源码日志文案。

### 上轮 suggestion 遗留（非阻塞）
- certbot `--manual --preferred-challenges dns` 会阻塞等 TXT 记录——可注明建 `_acme-challenge` 后回车；域名在 CF 上可直接 `--dns-cloudflare`。
- Step 3 的 `localIP/localPort` 与 Step 5 插件版同名 proxy 并存，逐字照抄可能同时写入。
- 「简化验证」tcp 裸转发会短暂把明文 KMS 暴露到 VPS 公网 remotePort——建议限定防火墙来源或验证完移除。

### 轮次信息
`[4-round, v4-pipeline; R3 Codex skipped — post-R2 all Low]` — DeepSeek R1a+R1b（`deepseek-v4-flash`，双通道并行）→ Opus R2 战略评审（独立读 diff + 对照 frp/AirAccount 源码）→ post-R2 门禁全 Low → 跳过 Codex → Opus R4 终裁 + 增量全扫。

**结论：APPROVE。** 三个 blocking 全部收敛（其中 F2 是上轮误报、作者正确反转）；新增内容经源码/上游逐项机械验证属实。剩余均为非阻塞文案/建议。
