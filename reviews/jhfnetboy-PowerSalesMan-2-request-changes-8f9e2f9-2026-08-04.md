## jhfnetboy/PowerSalesMan#2 — REQUEST_CHANGES (round 4, incremental re-review)

- Head: `8f9e2f9a86ccc96a60265c28e0df69ab76598f67` (incremental re-review; prior head `598419b69e99ac5fd0a495f42e5977640c603623`, prior verdict REQUEST_CHANGES)
- Pipeline: pr-daemon-loop v4, 4-round on the incremental diff (DeepSeek R1a+R1b → Opus R2 independent → Codex R3 PK in the actual PR-branch checkout → Opus R4 final)
- Local checkout: `/Users/jason/Dev/tools/PowerSalesMan` (not in `config/repo-roots.json`; personal repo, allowlisted via `~/.config/prbot/repos.conf`)

## 结论:REQUEST_CHANGES

`v4-pipeline [4-round, incremental re-review]` — DeepSeek R1a+R1b(并行) → Opus R2(独立通读增量diff+挑战R1) → Codex R3(PK,已在 PR 分支实际 worktree 内跑真实命令验证) → Opus R4(终裁+全量扫描)。

这是对上一轮 REQUEST_CHANGES(head `598419b`)的复审。自那以后新增两个 commit(`92edfbd`、`8f9e2f9a`,当前 head)。**上一轮的三条阻塞项一条都没有真正解决,而新增的功能又引入了一条新的高危回归。**

---

### 🔴 Blocking(继承自上一轮,未解决)

1. **[Critical] 泄露的登陆码 `psm-lpNP4OkF` 依然完整存在于分支历史里。** `92edfbd` 只是把 12 个 `.playwright-mcp/*.yml` 从工作树里删掉、补了 `.gitignore`,但这是一个纯删除 commit,**不会改变祖先 commit 的 blob**——`598419b`(引入这些文件的那个 commit)依然是当前 head `8f9e2f9a` 的祖先。实测(在 PR 分支实际 checkout 上):
   ```
   $ git show 598419b:.playwright-mcp/page-2026-08-04T05-29-09-702Z.yml | grep -i psm-
   textbox "Password / access code" [active]: psm-lpNP4OkF
   ```
   任何人 `git log`/`git show` 这个分支(code review 本身就需要这么做)依然能拿到这把能直接登进控制台的真实凭证。
   **修复**:立刻在服务端 revoke 这个 grant(`code_hash`+`revoked` 校验意味着撤销立即生效);对分支做 history rewrite(`git filter-repo` 或交互式 rebase 重建历史)后 force-push。只删工作树文件不是修复。

2. **[High] 同一批 blob 里的真实客户 PII 同样只是从工作树消失,历史里还在。** 公司地址、电话、联系人邮箱、内部管理员邮箱等——和上面同一个修复方案。

3. **[Medium] 收件人(`to`)依然从未落库。** `cloudflare/src/store.ts:87-96` `updateOutreach()` 白名单还是只有 `["content","status"]`,`schema.sql` 的 `outreach` 表也没有 `to`/`reply_to`/`sender` 列。这两个新 commit 都没碰这块。

### 🔴 Blocking(本轮新引入)

4. **[High] 冷邮件发信端点删掉了发件人校验闸门,任何登陆会话现在都能以创始人身份发信,且完全无法追溯操作人。** 对比 `598419b` → `8f9e2f9a` 的 diff:
   ```diff
   -        const senderEmail = normalizeSenderEmail(session.email, senderDomain);
   -        if (!senderEmail) return json({ error: "no_sender_email" }, 400);
   -        const from = `${senderDisplayName(session.label, senderEmail)} <${senderEmail}>`;
   +        const from = env.COLD_EMAIL_FROM ?? "iDoris <jason@idoris.ai>";
   +        const replyTo = normalizeSenderEmail(session.email, senderDomain) ?? undefined;
   ```
   这个 400 硬闸门原本保证"会话里没有合法邮箱就发不出信",删掉之后:`from` 恒为创始人身份,`replyTo` 无效时静默变成 `undefined`,发信照常进行,而落库只有 `status:"sent"`,操作人完全不可追溯。**且这个回归同时存在于 `cloudflare/src/worker.ts`(Cloudflare 生产)和 `src/server.ts`(本地 Node 镜像),两个运行时都受影响**(Codex 用真实文件内容分别验证过两处)。
   叠加阻塞项 1(登陆码依然有效):拿到泄露码的外部人可以直接以创始人身份对数据库里任意真实联系人发信,而这正是这个 PR 标题("发件 key 不外泄")想要防止的那类冒充。
   **修复**:恢复发件人校验闸门,或在 `senderEmail` 无效时强制 fallback 到 `ADMIN_EMAIL` 并在 DB 记录真实操作人(session/grant id);同时给 `to` 补上 `/api/send` 那边已有的格式校验(`/^[^\s@,;]+@[^\s@,;]+\.[^\s@,;]+$/`)。

5. **[Medium] 新增的品牌 HTML 邮件模块存在 HTML 结构破坏 bug。** `cloudflare/src/email-shell.ts` 的 `bodyToHtml()` 里 `bold(linkify(esc(para)))` 顺序有问题:`linkify` 的字符类 `[^\s<>"]+` 允许 `*`,于是纯文本里的 `https://a.com/**foo**` 会先被 linkify 包成 `<a href="https://a.com/**foo**" ...>`,随后 `bold` 在这个 **已生成的 href 属性值内部**插入 `<strong style="...">`,把属性提前截断、标签提前闭合。Codex 实测复现:
   ```
   输入: https://a.com/**foo**
   输出: <a href="https://a.com/<strong style="color:#16161D;font-weight:600">foo</strong>" style="color:#E2762B;text-decoration:underline">...
   ```
   邮件正文里只要出现"链接 + `**加粗**`"这个组合,发出去的品牌邮件结构就会破损,`style="..."` 这类属性文本可能以裸文本形式露给收件人。
   **修复**:调换顺序为 `linkify(bold(esc(para)))`(bold 生成的标签含 `<`/`"`,天然截断 linkify 的匹配),或者先给已生成标签打占位符再 linkify。

### 🔍 供参考(非阻塞,本轮扫描顺带发现)

- **[Medium] `/api/send` 落库的记录被复用到冷邮件端点会把上一个客户的邮箱泄露给下一个客户。** `/api/send` 存档时把内容存成 `To: x@y\nSubject: S\n\nbody` 这种伪 header 格式,但 `splitEmail()` 只匹配 `^\s*Subject:`,不识别 `To:` 行。如果这条记录后续通过 `/api/outreach/:id/send`(收件人由调用方传入,未做格式校验)重新发送,`subject` 会退化成默认的 "Hello from iDoris",而正文会原样带着上一条记录里 `To: 客户A的邮箱` 这一行,发给客户B——等于把客户A的邮箱地址写进发给客户B的品牌邮件正文里。这是既有代码 + 本轮新逻辑组合出的问题,建议和阻塞项3一起解决:把收件人/主题落成独立字段,而不是塞进 `content` 里用伪 header 猜。
- **[Low]** `cloudflare/src/worker.ts:208,241` 的 `assetBase: url.origin` 取自入站请求 Host——preview / `*.workers.dev` / 本地地址发出的邮件会内嵌收件人打不开的品牌图片链接,建议换成固定的 `PUBLIC_BASE_URL` env。
- **[Low]** `cloudflare/src/worker.ts:207` (`/api/send`,以销售本人身份) 与 `:233`(`/api/outreach/:id/send`,以创始人身份)发件身份不统一,同一条"线程"里客户会看到 2-3 个不同的 From,又没有 `In-Reply-To`/`References`,大概率无法被邮件客户端归并成同一线程,容易被判垃圾邮件。
- **[Low]** `.gitignore` 新加的 `*.png`/`*.jpeg` 是仓库级通配,只对 `cloudflare/public/brand/*.png` 开了口子,以后其他地方要加图片会被静默忽略。
- **[Info]** `cloudflare/src/worker.ts`(生产)和 `src/server.ts`(本地开发镜像)本轮再次被当作"同一逻辑维护两份"来改(contact 兜底、发件身份都同步改了),但只有 `worker.ts` 接了新的 `wrapHtml` 品牌邮件——本地预览和线上渲染出的邮件从此长得不一样,这种"改一处必须记得改两处"的模式下次很容易漏改出线上事故。
- **[Info]** `cloudflare/public/index.html` 与 `src/webpage.html` 本轮又是逐字节相同的改动(第三次观察到这个模式),建议抽出共享文件或用生成脚本维护同步,而不是手动保持两份一致。

---

## R1(DeepSeek 双通道,仅增量 diff)

**R1a**(全量):2 条,均为边缘情况——`replyTo` 可能为 undefined(其实就是本轮阻塞项4的一个侧面,R1a 没意识到闸门被删这个根因)、linkify 正则可能截断尾部标点。**没抓到闸门删除、也没抓到继承自上一轮的凭证泄露仍未解决**。
**R1b**(安全专项):2 条,均为误判——"`COLD_EMAIL_FROM` 环境变量可被冒充"(env 由部署方控制,不是攻击者输入)、"linkify 可能放行 `javascript:` 协议"(正则强制要求字面量 `https?://` 前缀,`javascript:` 根本不会匹配)。**同上一轮一样,再次完全没扫到真正的安全问题**——这次是新引入的发件人闸门回归,以及继承的凭证泄露仍未解决这两条。

## R2(Opus 独立通读增量 diff)

独立读 diff 后先于 R1 找出闸门被删(标为 High)、`bold`/`linkify` 顺序 bug(标为 Medium)、两个发信路径身份不一致(Medium)三条 R1 完全没提到的问题;评估 R1 的 4 条时,正确驳回了 R1b 的两条误判,并独立复核确认"删除文件不等于清除历史"这条 git 语义推理成立、`updateOutreach` 白名单确实没变。触发 post-R2 gate(存在 Medium+),进入 Codex R3。

## R3(Codex PK,`scripts/codex_pk.sh` 直接 Bash 同步调用,在 PR 分支实际 checkout `/Users/jason/Dev/tools/PowerSalesMan` 内跑)

针对 R2 的 4 条核心 finding(F1 历史泄露、F2 闸门回归、F3 HTML 结构破坏、F4 收件人未落库)逐条要求 Codex 自己跑命令验证,而不是只读我给的描述。**4/4 全部 CONFIRM,且全部带真实命令输出**:`git log`/`git show` 验证祖先关系与历史里的明文凭证、贴出当前 `worker.ts`/`store.ts`/`schema.sql` 源码验证闸门确实被删、白名单确实没变,并且**额外跑了一段 `node -e` 现场复现 F3 的 HTML 结构破坏**(具体输出见上方阻塞项5)。同时独立发现 R2 也没注意到的点:F2 的闸门回归**不止 `worker.ts`,`src/server.ts` 里一模一样的闸门也被删了**——已并入阻塞项4。

## R4(Opus 终裁 + 全量扫描)

综合以上,裁定 REQUEST_CHANGES。全量扫描里补了两条 R1/R2/R3 都没提到的问题:(a) `/api/send` 存档记录里的伪 `To:` header 被 `splitEmail()` 忽略,复用到冷邮件端点会把上一个客户的邮箱写进发给下一个客户的邮件正文(已并入"供参考"部分,建议和收件人落库一起解决);(b) 逐条核实并接受了 Codex 的全部 4 条 CONFIRM,没有降级任何一条。

## Self-assessment

- 轮数: 实际跑了 4 轮(R1a+R1b DeepSeek 并行 → Opus R2 独立读增量diff → Codex R3 在 PR 分支实际本地 checkout 内直接 Bash 同步调用真实命令对抗验证 → Opus R4 最终裁决)。triage_db 记录为 4-round(security-sensitive)。一致 ✅
- 每轮每模型实际做了什么:
  · R1 DeepSeek(flash): 在 598419b..8f9e2f9a 的增量 diff(含新文件 email-shell.ts)上并行跑了 R1a(全量)+ R1b(安全专项)。两者加起来 4 条 finding,2 条是边缘情况(有一定价值但没抓到根因),2 条是误判(已被 R2 用具体反证驳回)。**关键问题:R1a/R1b 都没有独立发现继承自上一轮的 Critical 泄露仍未解决,也没抓到本轮真正新引入的高危闸门删除回归**——这是本轮最重要的两条 finding,全靠 Sonnet 执行者先手动用 git 命令验证、再由 Opus R2 独立确认。
  · R2 Opus: 独立通读增量 diff(未先看 R1),自己找出闸门删除(High)、HTML 结构破坏(Medium)、发信身份不一致(Medium)三条 R1 完全没提到的问题;对我提供的"历史泄露未解决"的 git 语义推理做了独立复核而不是照单全收。
  · R3 Codex: `bash scripts/codex_pk.sh` 直接前台同步调用(未走 Agent(codex:codex-rescue),避免转后台取不回的坑),cwd 设在 `/Users/jason/Dev/tools/PowerSalesMan`(本来就在 PR 分支 `feat/reply-in-console`、head 正好是 `8f9e2f9a`,未额外建 worktree,因为这是我自己独占的本地 checkout,没有其它并发工作在跑)。给了 Codex shell 访问权限,要求它自己跑命令验证而不是读我的转述——它跑了 `git log`/`git show` 验证祖先关系和历史明文凭证、`nl`/`sed` 读当前源码验证闸门被删和白名单未变,并且**现场写了一段 `node -e` 复现 HTML 结构破坏 bug 并贴出真实输出**。4/4 CONFIRM,外加一条 R2 也没注意到的 MISSED(闸门回归同时存在于 src/server.ts)。
  · R4 Opus 裁决: REQUEST_CHANGES,独立核对了 Codex 的全部 4 条证据(未打折扣接受),并在全量扫描里补了一条 R1/R2/R3 都没提到的问题(`/api/send` 记录复用到冷邮件端点会把上一个客户邮箱写进给下一个客户的邮件正文)。
- 机械证据: `git show 598419b:.playwright-mcp/page-2026-08-04T05-29-09-702Z.yml | grep -i psm-` → 命中明文登陆码(Sonnet 执行者亲自验证,R2/R3/R4 各自独立复核同一结论);`git log --oneline 598419b..8f9e2f9a` 确认只有 2 个新 commit;`grep -n "updateOutreach" -A 20 cloudflare/src/store.ts` → 白名单仍是 `["content","status"]`;Codex 在实际 checkout 内跑 `git log`/`git show`/`nl`/`sed`/`node -e` 全部拿到真实输出(见上方阻塞项 1/4/5 里贴出的原始命令与结果)。
- **DeepSeek flash 评级**: **2/5** — R1a 的 2 条 finding 都是真实存在的边缘情况(非纯假阳性),但都是表面症状而非本轮的核心问题;R1b 的 2 条 finding 全部是假阳性,且再次(与上一轮同一个模式)完全没有识别出真正的安全问题——本轮的安全核心是"上一轮标为 Critical 的凭证泄露压根没修"和"新引入了一个删除权限校验的高危回归",这两条都需要跨 commit 比对(diff 598419b..8f9e2f9a 而非只看当前 diff)或对 git 历史语义的理解,单纯读增量 diff 的表层内容抓不住。改进建议:re-review 场景下,R1 prompt 应显式给出"上一轮标记为未解决/blocking 的具体条目列表",并明确要求"逐条核对是否被本次改动修复",而不是只喂增量 diff 让它自由发挥——目前 R1 完全不知道这是一次复审,也不知道上一轮说了什么。
- 与 skill 设计是否一致: 基本一致。触发条件判断(security-sensitive → 强制 4-round)、post-R2 gate(存在 Medium+ → 必须跑 Codex)、Codex 直接 Bash 前台调用(而非 Agent 转后台)、"仅增量 diff 而非重复全量 review"(遵循 [[feedback_incremental_diff_on_resubmit]])均按 skill 要求执行。
- 改进建议:
  1. **v4 skill 的 R1 步骤应该为"复审"场景加一个显式变体**——检测到这是 head 变化的复审(而不是全新 PR)时,自动把上一轮 REQUEST_CHANGES 的原始 blocking 条目列表塞进 R1a/R1b 的 prompt 里,要求逐条判定 fixed/unfixed,而不是让 DeepSeek 在完全不知情的情况下只看增量 diff。这次连续两轮 R1 都完全漏掉"历史里的凭证根本没删"这类需要跨轮记忆的问题,单看增量 diff 结构性地看不出来。
  2. `.state/pr-daemon/pr-watch.sqlite` 的 `pr_watch_targets` 更新这次遇到持续的 `database is locked`(与同时在跑的 `review_watch.py --loop` 守护进程争抢写锁),重试多次(含 python sqlite3 + busy_timeout)均未在会话内成功完成,已转后台重试。这不影响本次 review 已经发布到 GitHub 这个权威结论,但如果频繁发生,建议给 `review_watch.py` 的写操作加显式的短事务 + `PRAGMA busy_timeout`,避免和交互式 review 会话互相锁死。

