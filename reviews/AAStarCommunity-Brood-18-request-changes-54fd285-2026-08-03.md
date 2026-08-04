## 🔴 REQUEST_CHANGES — 上轮 4 项 blocking 已修，但 fix 在它本要改对的端口图上引入了新的错误

感谢修正提交 `54fd285`。**上轮 4 项 blocking 已全部确认修复**（均对照真实 AirAccount 代码逐行验证）：

- ✅ systemd 路径：已补 `mkdir -p /opt/frp && cp` + 启动改为 `/opt/frp/frps|frpc` + `daemon-reload`，与 systemd 单元 `ExecStart` 一致
- ✅ 端口：KMS=**3000**（只绑 127.0.0.1）、DVT=**8080**（见 `node1-school-mx93.toml`）
- ✅ API 路径：`/kms/CreateKey`→`/CreateKey`；health 期望值 `{"status":"healthy","service":"kms-api","version":"0.29.0"}` 与真实 `KMS_VERSION`（api_server.rs:4270）**逐字一致**
- ✅ 交叉引用：`backlog/docs/doc-8` → `research/global-network/china-kms-tunnel-setup.md`

**但 fix 在 `china-node-architecture.md`（它本要改对的那个文件）引入了一处新回归**，且架构图仍残留与真实 KMS 不符的 API 描述。照抄仍会误导。已全部对照真实代码验证。

### Blocking

1. **[High] `china-node-architecture.md` — `管理 UI（:8080）` 端口冲突 + 服务不存在（fix 引入的回归）**
   图上「管理 UI」和「DVT 节点进程」**都在 :8080**；且真实部署**不存在独立的 UI 服务**——Web UI 是 KMS 自己挂在 :3000 上（`GET /test`、`GET /portal`，见 api_server.rs 路由）。上轮的正确口径是 KMS=3000 / DVT=8080，fix 却把 UI 猜成了 8080，恰好在它要修正的端口图上制造了冲突。
   **Fix**: 删掉独立的「管理 UI」框，改为在 KMS:3000 下列出 `/test`、`/portal`；`:443 /ui/* → MX93:8080` 同步改为指向 KMS:3000 的 UI 路径（或删除）。

2. **[Med] `china-node-architecture.md` KMS 框 — `POST /sign`（小写）张冠李戴**
   小写 `/sign` 是 **:3100 回环 BLS signer**（`RUST_SIGNER_URL`，`x-signer-token`）的路由，**不在** KMS :3000 API 上；:3000 真实签名端点是根路径**大写 `POST /Sign`**。
   **Fix**: 改为 `POST /Sign`。

3. **[Med] `china-node-architecture.md` KMS 框 — `POST /account/register` 不存在**
   全仓库 grep 无此路由（api_server.rs 无 `account`/`register`）。属虚构端点。
   **Fix**: 删除，或换成真实端点。

4. **[Med] `china-node-architecture.md` — nginx 路由与 Path A 互相矛盾，且都不匹配真实 KMS**
   nginx 图写 `:443 /api/* → MX93:3000`，但 KMS 是**根路径**服务（无 `/api` 前缀）；Path A 又写裸 `POST https://kms.domain.com/sign`（无 `/api`、小写）。同一文件对对外路径两种说法，均 ≠ 真实根路径大写 `Sign`。
   **Fix**: 统一为根路径 `POST /Sign`（nginx 要么加 rewrite 去掉前缀，要么去掉 `/api/*`）。

5. **[Med] `china-kms-tunnel-setup.md` Step6 — curl body 非法 JSON**
   `'{"KeySpec":"...","Description":"test",...}'` 尾逗号 + `...`，逐字复制必 400。
   **Fix**: 给完整合法 JSON（提交前用 `python3 -m json.tool` / `jq` 校验）。

6. **[Med] `cloudflare-tunnel-global-availability.md` — 顶层 `token =`（:113,:122）是 pre-v0.52 旧写法**
   当前 frp TOML 需 `[auth] token = ...`，按现状 auth 会被静默忽略。
   **Fix**: 移入 `[auth]` 段。

7. **[Med] `cloudflare-tunnel-global-availability.md` — `[webServer] addr="0.0.0.0" port=7500` 无凭据**
   frp 面板默认 admin/admin 暴露公网。
   **Fix**: 加 `user`/`password`，或绑 `127.0.0.1`。

8. **[Med] `china-kms-tunnel-setup.md` Step5 — `[[httpPlugins]]` 不是 vhost TLS 证书配置位**
   这是 frp HTTP 插件块；vhost HTTPS 证书应在 frps.toml `vhostHTTPSCertFile`/`vhostHTTPSKeyFile`。按现状 certbot 证书永远接不进去。

### 已修复确认（上轮 blocking）
见开头 4 项 ✅。

### Suggestions
- 下一提交把 `china-node-architecture.md` 按真实拓扑**重画**（删幻影 UI 框、列真实根路由 `Sign`/`CreateKey`/`health`），别再猜端口约定。
- 所有剩余修正都是纯文本小改，建议一次性合入一个 commit，增量 diff 干净。
- 给 setup doc 每个 curl body 加 JSON-lint 步骤作为 PR 自身验证。

---

`[4-round, v4-pipeline]` — 增量复审：DeepSeek R1a+R1b（`deepseek-v4-flash`，双通道并行）→ Opus R2 独立读 diff + 对照真实 AirAccount 代码验证 → Codex R3 PK（gpt-5.5，**确认全部 6 项 findings、0 挑战**）→ Opus R4 终裁 + 补扫（新增 TLS `[[httpPlugins]]` 项）。

**结论：REQUEST_CHANGES。** 上轮 4 项 blocking 修得干净；这次要求把 fix 自己引入的 UI:8080 回归 + 架构图残留的虚构/错配端点一起修掉。全部是小文本修改，一轮即可收敛。
