## jhfnetboy/PowerSalesMan#2 — REQUEST_CHANGES (round 5, incremental re-review)

- Head: `bc973c06007ca1abc06412b648b3e78845ba8fcb` (incremental re-review; prior head `8f9e2f9a86ccc96a60265c28e0df69ab76598f67`, prior verdict REQUEST_CHANGES)
- Pipeline: pr-daemon-loop v4, 4-round on the incremental diff (DeepSeek R1a+R1b → Opus R2 independent → Codex R3 PK, real shell access in the actual PR-branch checkout → Opus R4 final)
- Local checkout: `/Users/jason/Dev/tools/PowerSalesMan` (personal repo, explicitly requested single-PR review; not in `config/repo-roots.json`)

## 结论:REQUEST_CHANGES

`v4-pipeline [4-round, incremental re-review]` — DeepSeek R1a+R1b(并行,喂了上一轮的4条blocking清单要求逐条判定fixed/unfixed) → Opus R2(独立通读增量diff+挑战R1) → Codex R3(PK,`scripts/codex_pk.sh`直接同步调用,真实运行在PR分支实际checkout内,自己跑命令验证而非读转述) → Opus R4(终裁+全量扫描)。

这是对上一轮 REQUEST_CHANGES(head `8f9e2f9a`)的复审。自那以后新增两个 commit(`18af360e`、`bc973c06`,当前 head)。**上一轮的4条阻塞项一条都没有真正解决(其中1条从"未解决"变成"更差"),而新增的功能(邮件预览、LINE按钮、UI重排)又引入了2条新的高危问题。**

---

### 🔴 Blocking(继承自上一轮,未解决)

1. **[Critical] 泄露的登陆码 `psm-lpNP4OkF` 依然完整存在于分支历史里。** 本轮两个新 commit 都没碰历史。实测:`git merge-base --is-ancestor 598419b HEAD` → `IS_ANCESTOR`;`git show 598419b:.playwright-mcp/page-2026-08-04T05-29-09-702Z.yml | grep -i psm-` → 命中明文登陆码。**修复**:立刻在服务端 revoke 这个 grant;对分支做 history rewrite(`git filter-repo`)后 force-push。只删工作树文件不是修复。

2. **[High] 冷邮件端点(`/api/outreach/:id/send`)依然没有发件人校验闸门,也依然没有把操作人写进 DB。** `cloudflare/src/worker.ts:253-262` / `src/server.ts:202-203,238`,`updateOutreach` 白名单仍只有 `["content","status"]`,`schema.sql` 的 `outreach` 表仍无 `to`/`reply_to`/`sender` 列。**本轮把这条从"未解决"变成了"更差"**:`replyTo` 从 `normalizeSenderEmail(session.email, senderDomain) ?? undefined`(至少还会带上有效 session 邮箱)改成了硬编码 `env.COLD_EMAIL_REPLY_TO ?? "jason@idoris.ai"` —— 冷邮件流程里最后一点操作人痕迹也被去掉了。叠加阻塞项1(登陆码依然有效):拿到泄露码的外部人可以以创始人身份对任意地址发信,且系统里**完全没有取证线索**。**修复**:恢复校验闸门 + 给 `to`/操作人加列持久化。

3. **[Medium] `cloudflare/src/email-shell.ts` 的 `bodyToHtml()` 依然存在 `bold(linkify(esc(para)))` 顺序 bug。** 现场复现(Codex `node -e`):`See https://example.com/**bold** now` → `<a href="https://example.com/<strong style="color:#16161D;font-weight:600">bold</strong>" ...>` —— href 属性被提前截断。这一轮新增的预览功能(见下方阻塞项5)用**不带 sandbox 的 iframe**直接渲染这段被破坏的 HTML,离用户更近了一步。**修复**:调换顺序为 `linkify(bold(esc(para)))`。

### 🔴 Blocking(本轮新引入)

4. **[Medium] 模板语言字段可触发原型属性访问,污染客户邮件称呼或直接 500。** `cloudflare/src/worker.ts:166` + `src/server.ts:167` 新增:
   ```
   const honorific: Record<string, (n: string) => string> = { th: ..., zh: ..., en: ... };
   const lang = tpl.lang in honorific ? tpl.lang : "en";
   const contact = primary?.name ? honorific[lang](primary.name) : teamOf[lang](company.name);
   ```
   `honorific`/`teamOf` 是普通对象字面量,`in` 操作符会命中继承的 `Object.prototype` 键;`tpl.lang` 来自模板记录(`store.ts:107-117`),没有服务端枚举校验。Codex 现场 `node -e` 复现:`lang="toString"` → 通过 `in` 校验,称呼渲染成 `[object Object]` 混进真实客户邮件;`lang="__defineGetter__"` → 抛 `TypeError`,该模板的所有 outreach 生成直接 500。**修复**:改用 `Object.hasOwn(honorific, tpl.lang)` 或 `Map`/`Object.create(null)`,并在模板创建/编辑时把 `lang` 校验到 `["en","zh","th"]` 白名单。

5. **[High] 新增的 `/api/preview` 端点没有同步加到本地 Node 开发服务器,且前端预览请求失败时静默显示垃圾内容而不是报错。** `cloudflare/src/worker.ts:202` 加了 `/api/preview`,但 `src/server.ts`(本地开发镜像)完全没有这个路由——实测 `grep -n "api/preview" src/server.ts` 零匹配,请求会落到 `src/server.ts:286` 的兜底 `404 {error:"not found"}`。而 `cloudflare/public/index.html:704-708` 的 `showPreview()`:
   ```js
   const r = await api("/api/preview", {...}).then(x => x.json());
   $("pv-meta").textContent = "From: " + r.from + ...;
   $("pv-frame").srcdoc = r.html;
   $("pvbox").classList.remove("hidden");
   ```
   对任何非 200 响应(本地开发的 404、未来可能的 500/400)都不做 `.ok` 检查——`r.json()` 照样解析出 `{error:"not found"}`,`r.from`/`r.html` 均为 `undefined`,代码继续把弹窗打开,展示 `From: undefined` 和空白 iframe。**这个功能存在的唯一目的就是"发出去之前让人看到客户会看到的样子",失败时却悄悄显示错误内容而不是报错**,本地开发环境下这个 bug 100% 必现。**修复**:在 `src/server.ts` 补上 `/api/preview` 路由;`showPreview()` 检查响应状态,失败时在 `pv-meta` 显示错误、不打开弹窗。

---

### 🔍 供参考(非阻塞)

- **[Medium]** `cloudflare/public/index.html:606-607` 的 `parseSent()`(`/im`,任意行匹配 `Subject:`)和实际发信路径 `cloudflare/src/worker.ts:16` 的 `splitEmail()`(仅字符串开头匹配)用不同正则——Codex 用同一输入分别跑两个正则,拆分结果不一致,意味着预览可能显示和实际发出内容不同的主题/正文拆分。建议抽成共享函数,`/api/preview` 服务端统一处理拆分。
- **[Medium]** `cloudflare/public/index.html:637` 的 `showPreview(p.subject, p.body, o.status !== "sent")` 用 `status!=="sent"` 判断 `cold`,但已发送的冷邮件 `status` 也是 `"sent"`——schema 里没有字段区分"走了冷邮件路径"还是"普通发信路径"(两条路径都写 `channel:"email", status:"sent"`),重新打开一封已发出冷邮件的预览会显示 `From: <操作人>`,而实际发出的是创始人身份。
- **[Medium]** `coldNote` 三语文案(`index.html`/`webpage.html` 的 :275/:310/:345)依然写着"客户回信仍回到你这里"/"Replies come back to you",但 `worker.ts:255-256` 本轮已把 `replyTo` 硬编码为创始人——文案在说和代码相反的话。
- **[Medium]**(Codex 主动发现,未经提示)`src/server.ts:231-233` 的冷邮件 Reply-To 依然从操作人 session 邮箱取值,与 `cloudflare/src/worker.ts:253-256` 硬编码创始人身份**不一致**——本地开发环境测出来的行为和线上不一样。
- **[Low]** `cloudflare/public/index.html` 的 `<iframe id="pv-frame">` 接收 `srcdoc` 但没有 `sandbox` 属性,在 app 自己的 origin 里渲染邮件 HTML(邻居就是 session cookie)。
- **[Low]** `cloudflare/src/email-shell.ts` 落款去掉了可读的 LINE ID 文字,只剩一个链接按钮——纯文本/剥离链接的客户端从此没有办法看到 LINE 联系方式。

---

## R1(DeepSeek 双通道,仅增量 diff,本轮显式喂入上一轮4条blocking清单要求逐条判定)

**R1a**(全量):REGRESSION_CHECK 3/4 判对(item1/2/4 UNTOUCHED),item3 判为 **WORSE**(唯一一处比 R1b 强的判断)。新增2条 finding 均为误判(`/api/preview` "泄露发件人邮箱"——实为返回调用者自己的 session 邮箱,已被 401 网关保护;LINE ID 转小写——LINE ID 本身就只能是小写)。
**R1b**(安全专项):REGRESSION_CHECK item3 判成 UNTOUCHED(错,应为 WORSE),`SECURITY_FINDINGS: none`——完全没扫到这轮真正的安全面(新增的准无鉴权渲染端点、无 sandbox 的同源 iframe、冷邮件信封里最后一点操作人痕迹被去除)。本轮专项通道再次是表现最差的一路。

## R2(Opus 独立通读增量 diff)

独立复核继承的4项(用 `git merge-base --is-ancestor`、`git show`、grep store.ts/schema.sql、node 复现 bold/linkify bug),判定item3为**更差**而非"未变"(与R1a一致,驳回R1b);正确驳回R1a的2条误判;独立新增5条 Medium + 2条 Low(模板语言原型属性问题、预览/发信解析器不一致、预览cold标记错误、文案与代码矛盾、iframe无sandbox、LINE ID文字被删)。战略层面指出:三个功能重复维护两份(worker.ts/server.ts、index.html/webpage.html)导致本轮新bug已经在两处重复出现;信封身份(from/replyTo)散落在4个地方手写,没有统一函数,这正是预览和实际发信能对不上的根因。触发 post-R2 gate(存在 Medium+),进入 Codex R3。

## R3(Codex PK,`scripts/codex_pk.sh` 直接 Bash 同步调用,真实运行在 PR 分支实际 checkout `/Users/jason/Dev/tools/PowerSalesMan` 内)

对 R2 的5条新 finding(F1-F5)+ 3条继承阻塞项的复审(F6-F8)逐条要求 Codex 自己跑命令验证。**8/8 全部 CONFIRM,且全部带真实命令输出**:`git merge-base`/`git show` 验证历史泄露仍在;现场写 `node -e` 复现原型属性称呼bug(`toString`→`[object Object]`,`__defineGetter__`→TypeError)和 bold/linkify HTML 破坏;分别跑两个正则验证预览/发信解析器输出不一致;读 schema 确认无字段区分冷/普通发信。**主动额外发现**一条3轮都没提到的问题:`src/server.ts` 的冷邮件 Reply-To 依然按操作人 session 取值,与 `worker.ts` 的硬编码创始人身份不一致——本地开发环境和线上行为已经分叉。

## R4(Opus 终裁 + 全量扫描)

综合以上,裁定 REQUEST_CHANGES。全量扫描新增2条前3轮都没提到、且已被我(执行者)用 grep 现场验证为真的问题:(a)`/api/preview` 完全没加到 `src/server.ts`(本地开发服务器),而 `src/webpage.html` 已经上线了预览按钮和 `showPreview()`——本地开发环境这个功能100%会打到404;(b)`showPreview()` 对非200响应不做检查,`r.json()` 照样解析成功,于是把 `From: undefined` 和空 iframe 的错误弹窗当正常预览展示给操作人——这条正好命中(a),本地开发环境必现。

## Self-assessment

- 轮数: 实际跑了 4 轮(R1a+R1b DeepSeek 并行 → Opus R2 独立读增量diff → Codex R3 在 PR 分支实际本地 checkout 内直接 Bash 同步调用真实命令对抗验证 → Opus R4 最终裁决 + 我本人对R4新发现的2条又做了一次 grep 现场复核)。triage 要求4-round(security-sensitive:认证/发信身份/凭证泄露)。一致 ✅
- 每轮每模型实际做了什么:
  · R1 DeepSeek(flash): 在 `8f9e2f9a..bc973c0` 的增量 diff 上并行跑 R1a(全量)+ R1b(安全专项),本轮 prompt 显式注入了上一轮的4条blocking清单+"逐条判fixed/unfixed"任务(采纳上上轮自评里提出的改进建议)。R1a 3/4 判对+1条关键判断("更差"而非"未变")比R1b强;R1b 判错item3且安全专项通道 fast-exit 到"none",完全没扫到本轮真正的安全面。R1a新增的2条finding均为误判,被R2驳回。
  · R2 Opus: 独立读增量diff(未先看R1),自己跑 git/grep/node 验证继承4项状态,判定item3为WORSE;正确驳回R1a的2条误判;独立新增5条Medium+2条Low,并给出"信封身份散落4处手写""双份代码库同步维护"的战略判断。
  · R3 Codex: `bash scripts/codex_pk.sh` 直接前台同步调用,cwd在 `/Users/jason/Dev/tools/PowerSalesMan`(本来就在PR分支`feat/reply-in-console`、head正好是`bc973c0`)。给了Codex真实shell访问权限,要求自己跑命令验证而非读转述——8/8 CONFIRM,全部带真实命令/node repro输出,外加1条R2也没注意到的MISSED(server.ts/worker.ts的reply-to分叉)。
  · R4 Opus裁决: REQUEST_CHANGES,逐条接受Codex的全部8条CONFIRM(未打折扣),全量扫描补了2条新问题(`/api/preview`未同步到server.ts + `showPreview()`失败时静默展示错误内容),我本人用grep对这2条又做了一次独立验证(见上方"Both R4 findings verified against actual code"),确认属实。
- 机械证据: `git merge-base --is-ancestor 598419b HEAD`→`IS_ANCESTOR`;`git show 598419b:.playwright-mcp/page-2026-08-04T05-29-09-702Z.yml | grep -i psm-`→命中明文登陆码;Codex `node -e` 复现原型属性称呼bug和bold/linkify HTML破坏(均有实际输出);`grep -n "api/preview" src/server.ts`→零匹配(我本人复核);`sed -n '704,712p' cloudflare/public/index.html`→确认showPreview()确实无.ok检查(我本人复核)。
- **DeepSeek flash 评级**:**2/5** —— 本轮R1a在"逐条判fixed/unfixed"这个新增的显式任务上表现有改善(3/4判对,且抓住了item3"更差"这个关键转折,是本轮唯一一处R1a优于R1b的判断),说明上一轮的改进建议(把上一轮blocking清单显式塞进prompt)确实有效,值得继续沿用。但R1a本轮新增的2条finding依然都是误判(0/2),R1b(安全专项)依然是表现最差的一路——SECURITY_FINDINGS直接fast-exit到none,完全没扫到这轮真实存在的3类安全相关面(新端点认证边界、无sandbox的HTML渲染、信封身份进一步弱化)。改进建议:R1b的fast-exit判断标准需要收紧——只要diff新增了一个处理用户输入并渲染HTML/返回身份信息的端点(如本轮的`/api/preview`),就不该判定为"无安全相关面";可以在SECURITY_PROMPT里加一条"新增/修改的API端点默认视为安全相关面,除非确认是纯静态内容"。
- 与 skill 设计是否一致: 一致。触发条件(security-sensitive→强制4-round)、post-R2 gate(存在Medium+→必须跑Codex)、Codex直接Bash前台调用、"仅增量diff而非重复全量review"(遵循[[feedback_incremental_diff_on_resubmit]])均按skill要求执行。R1 prompt显式注入上一轮blocking清单这个改进(源自上一轮自评的建议)本轮首次实践,效果部分验证(R1a判断变准,R1b仍不行)。
- 改进建议:
  1. 上一轮自评提出的"R1复审场景应显式喂入上一轮blocking清单"这个改进已在本轮实践且有初步效果(R1a的regression_check判断质量提升),建议正式写进skill的R1步骤,而不只是执行者临时手动拼接。
  2. R1b(安全专项)的fast-exit判定条件建议收紧:新增/修改任何处理用户可控输入并渲染成HTML、或返回身份/凭证类信息的API端点,不应该判定为"无安全相关面"直接fast-exit——这是本轮R1b连续第N次完全空手的根本原因。
