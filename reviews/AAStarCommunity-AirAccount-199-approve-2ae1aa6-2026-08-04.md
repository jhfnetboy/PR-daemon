## ✅ APPROVE — [2-round] docs-only

**AAStarCommunity/AirAccount#199 · docs(ops): 社区节点初始化 + SD卡离线编辑 + 安全审计文档**

3 个新增 Markdown（`kms/docs/`，全为纯文档、无代码/配置改动），已对照本地 checkout（`~/Dev/aastar/AirAccount`，head `2ae1aa6`）逐条机械核验。Coverage: 0 files omitted.

---

### 核验证据（实跑结果）

| 文档 | 核验项 | 结果 |
|---|---|---|
| 设计文档 | 引用 `community-node-image-ci-design.md` / `phase2-image.md` / `kms-dvt-production-init.md` / `community-node-register-modelB-funding-service.md` / `setup-server.py`(`kms/node-setup/`) / `community-profiles/`(`kms/deploy/`) | ✅ 全部真实存在，非 404 |
| 设计文档 | `(#21)` 交叉引用 | ✅ 是被引用文档自身标题里的工作项号（`feat(node-setup): #21 ... (#183)`），非 GitHub PR #21，一致 |
| SD卡指南 | 实战配方命令（debugfs/e2fsck 缓冲设备/SUDO_ASKPASS+FDA） | ✅ 命令与文件系统语义正确；作者标注 2026-07-15 实测 |
| 审计报告 | H-1 `api_key_filter` fail-open 描述（`api_server.rs:6411` 区域） | ⚠️ 见下 — 该问题**已在 2026-07-03 当天被修** |
| 审计报告 | H-2 `&w.description[..8]` UTF-8 切片（`api_server.rs:4303`） | ⚠️ 见下 — 同样**已修复** |
| 审计报告 | M-1 `warp::body::bytes()` 先缓冲再比 `MAX_REQUEST_BODY_BYTES`（`api_server.rs:5836-5842`） | ✅ **仍成立**，`aws_kms_body` 路由目前无 `content_length_limit` |
| 审计报告 | 撤回项「公网可无认证导出私钥」 | ✅ 核验成立：host 无 export HTTP handler（仅 `ta_client.rs` 库方法 + `bin/export_key.rs` CLI）；TA `main.rs:1677-1681` `#[cfg(not(feature="export-secrets"))]` → `Err("disabled in production TA builds")` |
| 审计报告 | `kms/` ≈35K 行 Rust | ✅ 实测 37,024 行，量级一致 |

### 需要作者注意的一点（建议，不阻塞）

审计报告把 **H-1 / H-2 标为「已确认发现（可行动）」**，但这两个问题在**审计当日（2026-07-03 23:45–23:48）就已被修复**：
- H-1 fail-open → `8fad0f2 fix(kms): make API-key auth fail-closed by default`（`has_api_keys()` 改为 `unwrap_or(true)` + `KMS_ALLOW_OPEN_MODE=1` 显式开关）
- H-2 UTF-8 panic → `f2e1bfb fix(kms): prevent UTF-8 panic in stats page description truncation`

现在 repo HEAD 里 H-1/H-2 描述的代码状态已不存在，只有 **M-1（body 先缓冲后限长）仍是活的**。作为 dated 审计快照本身没问题，但为避免后来者把已修问题当现役漏洞处置（或反过来因对不上源码而怀疑 M-1 的可信度），建议在 H-1/H-2 条目各加一行 `✅ 已修复 (commit，日期)`，并把顶部状态表里的「可行动」范围收窄到 M-1。

### Suggestions
- 在 H-1/H-2 补「已修复」标注（含 commit SHA），保留 M-1 为当前唯一可行动项。
- 设计文档 `aastar-flash.sh` / config 分区均为待办项（`- [ ]`），落地后建议回链实现 commit。

### Rounds
- R1a (DeepSeek full): 3 Low，均为对存量代码的信息级引用，无本 diff 引入项
- R1b (DeepSeek security): 无安全发现（纯 markdown，无安全表面）
- 2-round 路径（docs-only，无 Opus/Codex）

---
*Review 由 pr-daemon 以 clestons 身份发布 · 纯 review，不做 merge 决策*
