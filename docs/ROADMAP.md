# PR-Daemon 长期 TODO

> 只记「跨会话才做得完」的事。一次性的修复不进这里。

## 1. Triage 学习回路(分三步,不许跳步)

目标:根据 PR 特征**准确**判断该跑 2 轮还是 4 轮，把 4 轮触发率从当前的 67% 降下来，
而不是靠一刀切的保守规则。

**为什么现在不能直接做「学习」** —— 2026-08-05 的数据体检结果:

| 判定 | n | REQUEST_CHANGES 率 |
|---|---|---|
| 2 轮 | 66 | 9% |
| 4 轮 | 169 | 49% |

区分度 5.4 倍,说明现有规则本身判得不错;问题是 4 轮触发 180/267 = **67%**,其中一半最后是 APPROVE。
但 `flagged_miss = 0` **不能**当作「2 轮从没漏过」的证据 —— 267 条里只有 2 条真被 audit 过。
拿一个没人测量的指标去做优化，等于优化空气。

### 步骤

- [ ] **① 统一 signals 词表。** 现在是自由文本，同一个概念三套写法(`feat` / `type:feat`、
      `docs` / `type:docs` / `docs-only`)，无法聚合。定一份封闭词表，`triage_db.py record` 校验，
      非词表内的值直接拒绝。历史数据尽量归一化回填。
- [ ] **② 让 audit 真跑起来。** 抽查已判 2 轮的 PR，事后补跑 4 轮，看有没有漏掉的阻断项，
      结果写回 `triage_decisions.audited` / `audit_found_issue` / `flagged_miss`。
      目标:攒够足以支撑判断的样本，而不是继续对着 n=2 讲故事。
- [ ] **③ 攒够带标签样本后再谈规则/学习。** 在 ① ② 完成前不做任何「预测模型」。

### 在此之前的确定收益:机械短路(零风险,不需要学习)

- [ ] head 未变 → 直接跳过(本轮手工发现了 3 个这种情况:Brood#37、CMIC#142/#143)
- [ ] 纯 bump / 纯 docs / dependabot → 直接 2 轮
- [ ] 已 merge / closed → 直接跳过(已在 Step 0，保持)

## 2. 让 PR 一次就对(比加快 review 更省)

`docs/PRE-PR-RULES.md` —— 从 127 份 review 存档的 74 条阻断项统计出来的机械自检规则。

- [ ] 内化进产 PR 的仓库(Brood/pilot、AirAccount 等)的开发 skill:开 PR 前必须逐条跑
- [ ] 其中 F4(`$VAR` 后跟中文必须加花括号)零误报、零判断，**应该直接进 CI**
- [ ] B2(悬空文档引用检查)同样适合直接进 CI
- [ ] 跑一段时间后回头统计:阻断项的类别分布有没有真的变化(这是唯一的效果检验)

## 3. 性能:唯一的杠杆是「少跑不该跑的轮」

2026-08-05 首份分轮画像(AirAccount#196，20.2 min):

```
R4 38.8%  R2 32.2%  R3 19.8%   ← 三个判断轮合计 91%
verify 6.5%  r1ab 1.7%  prep 0.9%  post 0.2%
未计时 16%(reviewer 自己读码)
```

结论:提速 R1、流水线化准备段都动不了关键路径(已实测推翻了先前「流水线能省 25-35%」的估算，
实际 6-10%)。真正的杠杆是让 **post-R2 严重度闸门**更常触发(R2 全 Low → 跳过 Codex)。

- [ ] 攒够 round_timings 样本后,统计闸门实际触发率
- [ ] 评估 R4 是否可以在「R2 无 Medium+ 且 R3 跳过」时也简化(R4 现在是最贵的一轮)

## 4. 数据质量

- [ ] `duration_seconds` / `round_timings` 只有 2026-08-05 之后的行有;历史行是 NULL 且**不回填**
      (没测过的东西不许编)
- [ ] `review_rounds` 已从存档回填 66 行(`scripts/backfill_review_rounds.py`)
- [ ] round-profile 的「未计时部分」占比要盯着 —— 现在 16%,如果涨上去说明打点漏了阶段

## 5. 增量复审这条路是瞎的(2026-08-06,待 jason review)

来源:CoLivingOS#74 / #75 两次增量复审的自评。两次的 blocking **全部**由 Opus R2 或
reviewer 手工实证发现,DeepSeek R1 两次都是 0 命中 + 假阳性。

| PR | 轮数 | 耗时 | R1a | R1b | 本轮 blocking 谁找到的 |
|---|---|---|---|---|---|
| CoLivingOS#74 | 4 | 19 min | 0/2(全假阳性) | 0/2(全假阳性) | reviewer 手工换文件重跑 + Opus R2 独立撞上 |
| CoLivingOS#75 | 3 | 9 min | 0/1(误报) | 0(正确判 clean) | Opus R2 扫 diff **之外**的漏改点 |

不是模型弱,是**喂进去的东西结构上不可能包含答案**。下面五条按性价比排序。

### 5.1 增量复审的漏改点 —— 喂 R1 试过了,不管用;该喂的是 Opus R2

**问题**:增量复审的 blocking 几乎都是**漏改点** —— 上一轮提的 finding 只改了一半,
剩下那半**不在这次的 diff 里**。只看 diff 的 R1,结构上就发现不了。
CoLivingOS#75 两条 blocking(`TODO:68` 的总结句、`tasks.md:964/966` 的活规格)都是这一类。

**已做(PR #3):** `scripts/fetch_prior_review.py` + `deepseek_review.py --prior-review FILE`,
把上一轮 review 正文插在 diff **之前**,要求逐条判 FIXED/PARTIAL/NOT FIXED。

**⚠️ 实测结论:这个方案没有解决它想解决的问题。** 原来这条写着「🔴 最高性价比」,
是我在**没有对照**的情况下写的 —— 第一次验证时我把自己刚写完的那条 review 喂了回去,
它逐条复述了一遍,看起来很成功。那是循环论证。

真做对照(只喂**上一轮**的 review,那一轮从没提过这两处):

| 配置 | 找到 `TODO:68`? | 找到 `tasks.md:964/966`? |
|---|:--:|:--:|
| 增量 diff + 上一轮 review | ❌ | ❌ |
| **`-U40` 加宽 diff**(两处都真的出现在喂进去的文本里,grep 验过)+ 上一轮 review | ❌ | ❌ |

第二行才是关键:那两处**就在**它读到的文本里,它还是没找到,反而多了两条 "No issue" 的凑数行。
所以瓶颈不是「看不到」,是 flash 在这类判断上不行。两轮实测 R1a 0/4、0/1,
两次的 blocking 全部由 **Opus R2** 找到。

**接下来该做的**(未做):把这套输入 —— 上一轮 review 正文 + `-U40` 加宽 diff ——
喂给**实际找到东西的那一轮**,也就是 Opus R2,而不是继续加强 R1。

- [x] `scripts/fetch_prior_review.py`
- [x] `deepseek_review.py --prior-review FILE`
- [ ] **R2 的 prompt 带上 prior review + 加宽 diff**(真正的杠杆)
- [ ] 增量复审的 diff 默认 `-U40` 而非 `-U3`(漏改点通常紧挨着改对的那处)
- [ ] SKILL.md Step 2 后插入取 prior review 这一步,写明增量复审必须带 ——
      但别再宣称它能让 R1 抓到漏改点

> 教训归教训,单独记一条:**验证一个「让模型发现 X」的改动时,不能把答案喂进去。**
> 我第一次就是这么验的,并据此把它标成了最高性价比。

### 5.2 「回归测试不承重」应该做成机械检查,不该靠人肉

**问题**:CoLivingOS#74 加了一条回归测试,**对着修复前的代码也是绿的** —— 它挡不住 bug
回来。这是我手工把 `statements.ts` 换回父提交版本重跑才发现的。这个 bug 类**完全可机械化**,
而且值钱:一条不会失败的回归测试比没有更糟,它让 diff 看起来已经把问题钉死了。

**方案**:`scripts/verify_regression_test.py <repo> <pr>` —— PR 同时改了 src 和 test 时:
1. 建临时 worktree 停在 PR head
2. 把**本 PR 改过的 src 文件**逐个换回父提交版本
3. 只跑**本 PR 新增/修改的那几个 test**
4. 仍然全绿 → 报 `[Medium] 回归测试不承重` finding

- [ ] 写脚本(先只支持 vitest/jest,按 `describe`/`it` 名字过滤)
- [ ] 接进 `$pr` 的 4-round 路径,作为 R2 之前的机械证据
- [ ] 跑一段时间统计命中率,决定要不要推广到 2-round

### 5.3 Codex 那 366 秒 —— 不是挂起,是**正在干活时被硬上限杀掉**

**原来写的**:「codex exec 挂起 366s 才回退,31.6% 的时间花在等一个已经死了的进程」。
**这句是错的**,是我没看那次运行留下的产物就下的结论。

评审(PR #1 的对抗评审)翻出了 `pk-74.out.raw`:**99,590 字节**,codex banner、工具调用、
一段 node 复现脚本打出的 jsSum/exactSum 对照表,结尾停在 `hook: PostToolUse`。
mtime 21:58:46 → 22:04:38 ≈ 352s ≈ 360s 硬上限。它**从头到尾都在输出**,
是被 `CODEX_MAX_SECS=360` 在干活的中途杀掉的。

逻辑上也该早点想到:stall 检测是「90s 没有新输出就杀」,那么能撑到硬上限的运行,
按构造就是每 90s 内都有输出 —— 也就是「没挂」的定义。

所以:
- **那 366s 不是浪费在死进程上,是我们把一个快做完的 PK 挑战砍了。** 真正的损失是
  #74 那轮 R3 本可以有真 Codex 的结论,却退化成了 DeepSeek 兜底。
- **对 rc=3(硬上限)熔断是错的** —— 一个 PR 慢一点就把最强挑战者关掉 30 分钟。
- 熔断该留给另一个真实故障:codex 从头到尾一声不吭(rc=2 且产出接近 0)。

**已做(PR #1)**:熔断只对静默挂起触发;rc=3 永不熔断,改为提示调大上限。

- [x] `codex_pk.sh` 加熔断读写(只对 silent stall)
- [ ] **重新评估 `CODEX_MAX_SECS=360`** —— 有一次实测证据表明它对真实 PK 偏小。
      在调大之前先收集几次 raw 产出大小与耗时,别又拿一个样本下结论。
- [ ] R3 的标签要从 `codex_pk.sh` stdout 第一行(`CHALLENGER:`)**原样读出来**再写进
      `--round-models`,而不是由执行者凭印象填。熔断让这件事更容易出错:R3 现在 2 秒返回、
      transcript 里连 `codex attempt 1/1` 都没有,读起来像一轮正常的快速 round。

> 教训和 5.1 是同一条:**下结论前先看那次运行自己留下的证据。** 5.1 是把答案喂进去验证,
> 5.3 是根本没打开那个 99KB 的输出文件。两次都是「省掉一次核对」换来一个自信的错误判断。

### 5.4 巡检范围被我写了第二套源 —— 这正是 skill 明令禁止重建的东西

**问题**:本会话为了「只审 CoLivingOS」,我**手写 cron prompt 把仓库名写死在里面**,
绕过了 `start_loop_scope.py`。SKILL.md「⛔ ONE list, ONE command」那节专门讲过范围
曾经有三份互相打架的源、合并花了多大力气 —— 我又造了第四份,而且它只活在 cron prompt 里,
`$pr list` 完全看不见。

**方案**:范围收窄要走那**一条命令**,不许写进 prompt。
`$pr start [Nm] [all] [--only <repo>[,<repo>]]`,`--only` 落到
`start_loop_scope.py targets --only ...`,cron prompt 里永远只有那一行命令。
`$pr list` 要能显示「当前巡检被 --only 收窄到 X」。

- [ ] `start_loop_scope.py targets` 加 `--only`
- [ ] `$pr start` 解析 `--only` 并透传;SKILL.md 记一句「范围绝不写进 cron prompt」

### 5.5 idle 自停把「用户直接点名审的 PR」算成空转

**问题**:本会话真审了 2 个 PR 并 post 了结论,但因为不是在 cron 周期**内**审的,
`idle_rounds` 照样从 0 累到 3,1 小时后巡检自停了。计数器记的是「本周期 k」,
而它想表达的是「最近有没有进展」。

**方案**:idle 记账改成读**最近一次 post 的时间戳**(`model_review_runs.finished_at`
的 max),而不是本周期的 k。距上次 post > 60 min 才算真空转。
这和 #74 那个 lock 的 mtime 修法是同一个道理 —— 计数器要表示「距上次进展多久」。

- [ ] `start` skill 的 Step D 改成时间戳判据
- [ ] 顺带:`$pr start` 时把 `finished_at` 的 max 读出来当基线,别一上来就从 0 数
