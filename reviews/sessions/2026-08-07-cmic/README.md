# 2026-08-07/08 CMIC 巡检存档（#189–#193，9 轮 review）

**为什么有这个目录**：这一晚的中间产物原本只在 `/tmp` —— 尤其 Codex R3 的输出各 110KB+，
是全流程里最贵、最难复现的一段。仓库最近那条 commit 的题目就是「review 的记忆不能只活在对话里」，
而当晚它自己又只活在 `/tmp` 里。归档于会话结束时补做。

## 里面是什么

| 文件 | 是什么 |
|---|---|
| `pr-<N>-r1a.md` / `-r1b.md` | DeepSeek v4-flash 的 R1 双通道原始输出 |
| `pr-<N>-r3.md` | Codex(gpt-5.5) R3 对抗轮原始输出（含完整推理轨迹） |
| `pr-<N>-codex-prompt.md` | 喂给 Codex 的 prompt 原文 —— 想复盘「为什么它挑对/挑错」要看这个 |
| `pr-<N>-comp.diff` | 喂给各轮的压缩 diff（各轮看到的**同一份**输入） |
| `review-<N>.md` | 最终 post 到 GitHub 的 review 正文 |

后缀 `190c/190d/190e` = #190 的第 3/4/5 轮（那个 PR 一晚上审了 5 轮）。

## 没存进来的

- **各 Opus 子代理（R2/R4）的完整输出**：它们经由 Agent 工具返回，不落文件系统。
  只有被我采信、写进 `review-<N>.md` 和 `model_review_runs.misses` 的部分留下来了。
  这是目前最大的一块缺口 —— R2 今晚 5 次挖出我漏的东西、2 次纠正我自己的核验错误，
  而它的原始输出没有一份存档。**要做 R2 的效果分析，得先让 Agent 输出也落盘。**
- 每轮的自评块（对话里）：主体内容已塞进 `model_review_runs.summary`，但结构化字段没有。

## 结构化数据在哪

- `reviews/model-evals/model-evals.sqlite` → `model_review_runs` id **1167–1175**
  （score / verdict / rounds / round_models / round_timings / useful_findings /
   false_positives / misses / summary，未截断）
- `reviews/model-evals/triage.sqlite` → `triage_decisions`，#189–#193
  （当晚漏记，会话结束时补录，`created_at` 因此晚于实际决策时刻）
- GitHub PR comment 是 review 正文的权威副本；这里的 `review-<N>.md` 是同一份内容的本地镜像

## 这批数据能拿来回答什么

1. **DeepSeek v4-flash 值不值那个槽位** —— 9 轮里逐轮评级都在 `summary` 里，
   分布很分明：纯文档 PR 1/5、真实代码 diff 4/5、增量轮 0–2/5（带 `--prior-review` 反而更差）。
2. **R4 的「先证伪本轮最强 finding」到底有没有用** —— 当晚 4 次改变结论（#189 降级、
   #191 直接翻转成 APPROVE、#190 两次），有 `review-<N>.md` 的 Rounds 段可逐条追。
3. **同一个 PR 连审 5 轮的收敛形状** —— #190 从「整段 HTML 塞进公开页」到「默认拒绝的位图白名单」，
   而且连着四轮出现同一个模式：**每次修复堵住自己那洞、又开一个同形状的小口子**。
