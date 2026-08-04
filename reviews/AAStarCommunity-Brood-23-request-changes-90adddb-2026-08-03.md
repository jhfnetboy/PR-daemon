## 审查结论:REQUEST_CHANGES

> **[4-round] v4-pipeline** · DeepSeek R1a+R1b → Opus R2 → Codex R3 PK → Opus R4 裁决
> PR: docs(backlog): tasks + progress-report refresh @ `90adddb`

**这是一个进度台账刷新 PR。它的全部价值就在事实准确性。经 gh api 机械核验,报告中存在多处虚构数据(不存在的仓库、不存在的提交、伪造的历史行)和明细/汇总自相矛盾。审的是 docs,但错的是事实,必须改。**

---

### 🔴 BLOCKING(3 High)

**H1 — doc-7 汇总表 TASK-13 行指向不存在的仓库**
- `AAStarCommunity/MyTask` → **HTTP 404**(真实是 `MushroomDAO/MyTask`,doc-7 明细区第 88 行自己都写对了)
- `AAStarCommunity/Cos72` 创建于 **2026-07-10**(扫描日 07-07 之后),扫描当时应引用 `MushroomDAO/Cos72`
- 修复:该行改回 `MushroomDAO/{MyTask,Cos72}`,日期 04-29 改为真实最后提交 **06-20**

**H2 — task-19/task-28/task-29 + doc-7 三行:系统性假日期「04-29 / 静默 ≥ 69 天」**
| 仓库 | 报告声称 | gh api 实测 |
|---|---|---|
| MushroomDAO/Spores | 04-29 | **2026-06-07** |
| MushroomDAO/Asset3 | 04-29 | **2026-06-07** |
| iDoris-ai/OpenCrab | 04-29 | **2026-06-20** |
- 同一批「04-29」在 3 个文件重复出现,而上一轮 06-21 扫描记录的是正确日期 → 扫描器把一条过期缓存当成了 last-commit。静默天数被夸大 40–52 天。

**H3 — task-35 + doc-7:`iDoris-ai/AI_Beginner_Courses` 仓库不存在,却用它把进度 50→55%**
- gh api → **404**(iDoris-ai org 只有 `courses`;用户名下只有 `AACourses`)
- 报告声称「新发现活跃仓库 近9天 2 次提交 2026-07-05 Agent Loop/Loop Engineering 讲义新增」→ 纯虚构引用
- 修复:删除该 claim,进度**回退 50%**,并给「新发现活跃仓库」加 200-OK 校验

### 🟠 CONFIRMED(6 Medium)

- **H4 task-34 + doc-7**:agent-speaker 声称 07-05/06/07 的 commits(kind:1111 comment / blossom tweaks / publish fix / admin color flag)**全部不存在**——仓库 main 历史 06-20→07-24 之间为空、07-01..07-10 合并 PR = 0。68→70% 建立在虚构提交上
- **H5 task-12**:新报告「20% / AAStarCommunity/demo 静默 ≥83 天」——**仓库指错**(demo 是 TASK-2 的 repo,task-12 引用的是 AirAccount);72→20% 无解释;与自身 frontmatter `status: Done` 矛盾;doc-7 明细仍写 72%,汇总表则完全漏掉 TASK-12
- **H6 doc-7 明细区整体过期,与汇总表矛盾**(同一份文档两个百分比打架):TASK-5 20% vs 95%、TASK-31 90% vs 98%、TASK-32 85% vs 30%、TASK-35 35% vs 55%、TASK-13 30% vs 35%
- **H7 doc-7 changelog**:**回溯插入 2026-06-29 行**(TASK-31 97% / TASK-5 92% "AirAccount v0.27.3 + SDK v0.29.7")——该日期从未有过扫描(updated_date 从 06-21 直接跳到 07-07),伪造历史;还把历史 06-21 行改成当时尚不存在的 org 名
- **H8 task-5**:声称「07-07: AirAccount — DVT BLS TEE 托管 Variant B 成型(blst TA + KMS+DVT joint deploy)」,实际 AirAccount 07-07 提交是 onboarding installer,提交内容与描述不符

### 🆕 MISSED(Opus R4 补扫 + 我已复核)

- **M1 task-26 + doc-7**:同一批假日期——声称「静默 62 天(最近 05-06)」,gh api 实测 UltraRelay-AAStar 默认分支最后提交是 **2026-06-03**(`chore: add @clestons as code owner`);报告自身「62 天」vs「静默超 53 天」内部就不自洽。修到 06-03 / ~34 天

### ✅ 核验通过的部分(避免误伤)

- org 改名 `AuraAIHQ→iDoris-ai` 的全部引用(Agent24/agent-speaker/simple-agent/OpenCrab/courses)**均可解析** ✓
- 真实验证:airaccount-contract v0.27.0 tag ✓、SuperPaymaster #329(07-05 merged)✓、v5.4.1-rc.1 tag ✓、CometENS v0.7.0 tag ✓、demo 静默 04-15(83 天)✓、MushroomDAO/launch #28 relayer 上限移除(06-24)✓——task-23 是唯一诚实条目
- 所有任务文件 frontmatter YAML 可解析;missing-key 均为全仓库既有宽松 schema,非本 PR 引入
- R1a F2(relayer 上限移除)、F3(kill switch)经核验为准确描述,已驳回

---

### 💡 建议

1. **修扫描脚本,别只改文档**——「04-15/04-29/05-06 假日期簇」+「仓库张冠李戴(demo→TASK-12、AI_Beginner_Courses→TASK-35、MyTask→AAStarCommunity)」指向 /sync-progress 的系统性 bug。重新提交前请对每个 date/repo/PR/tag 跑 gh-api 校验
2. **doc-7 明细与汇总必须单一数据源渲染**——本轮刷新把表改了却漏了明细,一份文档两个进度
3. task-34/35 title 改名 AuraAI→iDoris.ai 与仓库其余部分不一致(CLAUDE.md、orgs/auraai/PROFILE.md、sync-progress skill 仍映射 AuraAIHQ)——建议全仓对齐或本期先不改

---

### ROUNDS
- **R1a(DeepSeek full)**:4 Low,未抓到任何虚构数据
- **R1b(DeepSeek sec)**:0(纯 docs diff,正确)
- **R2(Opus strategic)**:ESCALATE — 8 findings(3 High 5 Med),确认 R1 全部 F1-F4
- **R3(Codex PK)**:8/8 CONFIRM,0 CHALLENGE
- **R4(Opus final)**:REQUEST_CHANGES + 补扫 MISSED M1
