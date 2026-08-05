## Verdict: APPROVE（首轮，head `ebadd1d1`）—— **只读端点，边界都处理到了**

`GET /api/communities/:slug/images` 这个新端点我逐条核过：

| 检查 | 结果 |
|---|---|
| DB binding 缺失 | ✅ `503 database_unavailable`，不是崩 |
| slug 缺失 | ✅ `400 missing_slug` |
| 社区不存在 | ✅ `404 community_not_found`，且判的是 `!community \|\| !community.id`（不是只判 falsy） |
| SQL 注入 | ✅ 两条查询都用 `?1` 参数绑定，`slug` 和 `community.id` 都没有拼接 |
| 空图廊 | ✅ `results ?? []` → `{ok:true, data:[]}`，不是 404 |
| `public_url` 为 NULL | ✅ 回落到 `/api/media/${r2_key}` |
| 缓存 | ✅ `Cache-Control: public, max-age=60`，只读端点合适 |
| 方法白名单 | ✅ `onRequest` 兜底返回 `methodNotAllowed(["GET","OPTIONS"])`，OPTIONS 单独给 204 + CORS |

`thumbUrl` 用 Cloudflare Image Resizing 的 `/cdn-cgi/image/...` 前缀，注释说明了「zone 上没开这个功能时 CF 直接返回原图，所以客户端总能回落到 `url`」——**这个降级路径写在注释里而不是靠猜**，好。

### 驳回 R1a 的注入质疑

> R1a：「从 `public_url` 拼缩略图 URL 是潜在注入点，如果那个字段将来变成用户可控的话」

**追了写入端，不成立**（`functions/api/uploads/community-image.ts`）：

```ts
const id = crypto.randomUUID();
const r2Key = `community-images/${communityId}/${id}.${ext}`;
const publicUrl = `/api/media/${r2Key}`;      // ← 服务端拼的,不接受客户端传值
```
- `public_url` **从不来自请求体**，是服务端用 `crypto.randomUUID()` 拼出来的；
- 而且那个上传端点第 19 行就是 `requireAdmin(request, runtimeEnv)`，**匿名根本进不去**。

它的「如果将来变成用户可控」是个合理的假设句，但当前两道都堵着。

### 非阻塞

- **[Low] `ext` 进了 `r2Key`，值得确认它是白名单出来的。** 我看到 `r2Key` 用了 `${ext}`——它如果来自文件名后缀且未经白名单，理论上能影响对象键（不是这个 PR 引入的，属上传端点）。这个 PR 只读不写，不受影响，但既然 `public_url` 的可信度是上面那条驳回的依据，值得顺手确认一下 `ext` 的来源。
- **[Low] `alt` 直接透传给前端。** 它由管理员在上传时填，可信度高；但既然图廊现在渲染到详情页，值得确认渲染侧是用 `textContent` / 属性绑定而不是 `innerHTML` 拼。（`scripts/assets/interactions.js` 里其它地方是走 `esc()` 的，方向是对的。）

### Assumptions

- 用 `gh repo clone` 拉了一份只读副本到 scratchpad 做评审上下文（本地 `~/Dev/auraai/NextStop` 也有一份，我没有碰它），未改动任何仓库文件。
- **没有向生产发请求** —— 结论都是读代码得出的；`public_url` 的可信度是**追到写入端**确认的，不是假设的。
- **R2/R3/R4 未跑** —— 单个只读端点，无争议项。本 review 标 **2 轮 + 机械验证**，不冒充 4 轮。

---
*Reviewed by clestons（`$pr` v4，**2 轮 + 机械验证**，首轮 head `ebadd1d1`）：DeepSeek R1a+R1b
（`deepseek-v4-flash`；1 条注入质疑追到写入端后不成立）→ Sonnet 机械验证（逐条核对错误分支与参数绑定、
追 `public_url` 到 `uploads/community-image.ts` 确认服务端生成且端点有 `requireAdmin`）→
**Opus R2 未跑（只读端点）；Codex R3 未跑；R4 未跑**。*

### 自评

- **DeepSeek v4-flash 本轮：3/5。** 它的概括准确（「correctly handles DB errors, missing communities, and fallback URLs」），唯一那条 finding **问对了维度**——「这个值可信吗」正是评审 URL 拼接该问的第一个问题，而且它自己加了「if that field is ever user-controlled」这个限定，没有把假设说成事实。扣分只因为它没去追写入端（同一个仓库、一次 grep 的距离）。
- **下次怎么榨出更多信号**：这类「读某字段拼 URL/路径」的 diff，判据永远是**那个字段谁能写**。下次在 prompt 里写死：「对 diff 里每一个被读取后用于拼接的 DB 字段，找到它的写入点，说明写入者需要什么权限、值是否来自请求体」。这是一次 grep 能完成的追踪，flash 有机会做对。
