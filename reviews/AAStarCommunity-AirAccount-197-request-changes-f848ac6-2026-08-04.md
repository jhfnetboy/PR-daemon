## AAStarCommunity/AirAccount#197 — REQUEST_CHANGES

- Head: `f848ac6` (chore: pilot 初始化 + 仓库卫生, gitignore 挡 73MB PDF/PSK 密钥)
- Pipeline: pr-daemon-loop v4, 4-round (DeepSeek R1a+R1b parallel → Opus R2 independent → Codex R3 adversarial PK in isolated worktree at PR head → Opus R4 final)
- Triage: escalated from a docs/chore-looking diff to 4-round because it touches automation-consumed pilot config (`.pilot.yml`, `docs/agent/tasks.md` task ledger) + a new production-SSH ops script, and R1b flagged a Medium finding on it.

## Blocking

**[Medium] `.pilot.yml:5` — `integration_branch: main` is refused by pilot's own `git-guard.sh merge-pr`.**
Both `base_branch` and `integration_branch` are set to `main`, which is also this repo's actual GitHub default branch. `git-guard.sh merge-pr` hard-refuses via two independent checks: a hardcoded trunk-name pattern match (line 149: `main|master|develop|release*|hotfix*`) and a live comparison against `gh repo view --json defaultBranchRef` (line 160-161). Reproduced mechanically by Codex R3:
```
$ sh git-guard.sh merge-pr 197 --integration main
integration 'main' is a trunk branch — merge PRs into an integration branch (e.g. preview), not trunk
```
Effect: every unattended `pilot run` on this repo will develop → open a PR → die at the merge step, forever. The file's own comment (`.pilot.yml:3`, "集成分支即 main(pilot 的 PR 合并目标)") asserts exactly what the guard forbids.

Fix — create a real non-trunk integration branch (`git branch preview main && git push -u origin preview`, set `integration_branch: preview`), or if this repo intentionally merges by hand under branch protection, drop the misleading comment and document that `pilot run` terminates at "PR opened, manual merge required."

## Confirmed findings

- **[Low] `kms/deploy/selfcheck.sh` hardcodes production KMS topology into a PUBLIC repo** (verified `gh repo view --json visibility` → `PUBLIC`). Commits both nodes' Tailscale IPs, the dvt1/dvt2/dvt3 ↔ 板A/板B/DK2 role mapping, which node fronts `kms.aastar.io` vs `kms1.aastar.io`, systemd unit names, `root@` SSH login, and the 2-of-3 signing threshold — free reconnaissance for a threshold-signing keystore, permanently in git history. Move `NODES` to an untracked, gitignored file.
- **[Low] `.goutou.json:3` — `aliases: ["airaccount","kms"]` is dead config.** Verified against the goutou skill: only singular `repoId` is consumed for `labelName=repo:<REPO_ID>` matching. The file's own note claims dual-label matching that isn't implemented — a task labeled only `repo:airaccount` would silently never reach this repo's goutou instance.
- **[Low] `selfcheck.sh:63` always exits 0** regardless of node/threshold failures — unusable as a cron/monitoring probe as-is.
- **[Low] `StrictHostKeyChecking=no`** — real (if Tailscale-narrowed) MITM-on-first-connect window.
- **[Low]** `mx93b` operator-private ssh alias mixed with raw IPs (false alarms for other operators); `$dvtunit` unquoted in remote command (latent injection sink once `NODES` is externalized); `pr_daemon_root` in `.pilot.yml` duplicates the skill's built-in default and hardcodes one operator's machine layout.

## Rejected (from R1)

- R1a "missing `set -e`" — intentional and correct: `-e` would abort the whole sweep on the first unreachable node, suppressing the report for the other two.
- R1b "[Medium] hardcoded SSH host/IP = missing secret management" — the IPs are Tailscale CGNAT (100.64.0.0/10) identifiers, not credentials; reframed as the topology-leak finding above instead.

## Verified clean

- Neither `imx93-docs/` nor `kms/docs/dk2-school-wifi/` was ever committed to any of this repo's 8 remote branches (`git log --all` after full `git fetch --all --prune`) — purely preventive gitignoring, no BFG/history-rewrite needed.
- `git ls-tree` at PR head: zero tracked paths match either new ignore pattern.
- `selfcheck.sh` passes `bash -n`, is genuinely read-only (systemctl status + curl `/health` only).

## R1 (DeepSeek dual-pass)

R1a and R1b both read only `kms/deploy/selfcheck.sh` and missed the three new config files entirely — including the PR's actual blocking defect (`.pilot.yml`). R1a's one finding was wrong-by-design; R1b's Medium was severity-wrong (conflated CGNAT identifiers with secrets), though its StrictHostKeyChecking Low held up.

## R2 (Opus independent) → R3 (Codex PK) → R4 (Opus final)

R2 was the sole source of the blocking finding — cross-referenced the committed `.pilot.yml` against the real `git-guard.sh` source. R3 (Codex, worktree pinned to PR head `f848ac6`) independently re-derived the same conclusion by reading both files verbatim and *executing* the guard to reproduce the exact failure — CONFIRM, no counter-evidence. R4 additionally caught the public-repo topology leak that neither R1 nor R2 flagged, via `gh repo view --json visibility`.

## Self-assessment

- 轮数: 实际跑了 4 轮 (R1a+R1b DeepSeek 并行 → Opus R2 独立读全量diff → Codex R3 独立 worktree 对抗挑战+真实执行验证 → Opus R4 最终裁决)。skill 要求(triage 后): 4-round。一致 ✅
- 每轮每模型实际做了什么:
  · R1 DeepSeek(flash): 喂了 7 个文件的完整压缩 diff(3888 tokens,无丢弃)。R1a 全量扫描只看到 shell 脚本,给了 1 条错误的 finding(缺 -e,实为有意设计);R1b 安全专项扫描也只看 shell 脚本,给了 1 条 Medium(硬编码 IP,判定过重)+ 1 条 Low(StrictHostKeyChecking,成立)。两遍都完全没读 .pilot.yml/.goutou.json/docs/agent/*.md 三类新配置文件。
  · R2 Opus: 独立通读全量 diff(先于看 R1 结果),自己发现 .pilot.yml 的 integration_branch=main 与 pilot 自身 git-guard.sh 的 trunk 检测矛盾这条 Medium finding(R1 完全没看到);另外独立发现 .goutou.json aliases 死配置(交叉核对了 goutou SKILL.md 的实际消费逻辑)、selfcheck.sh 恒 exit 0、$dvtunit 未加引号、mx93b 别名可移植性问题共 4 条 Low;并对 R1 的两条做了驳回(-e 有意设计;硬编码 IP 是 Tailscale CGNAT 标识符非密钥)。
  · R3 Codex(gpt-5.5): 用 scripts/codex_pk.sh 直接 Bash 前台同步调用(未走 Agent(codex:codex-rescue)),在独立 worktree(`git worktree add /tmp/airaccount-pr197-wt origin/chore/repo-hygiene --detach`,固定在 PR head f848ac6,未碰主 checkout)里跑,喂了 .pilot.yml 全文 + git-guard.sh 全文(verbatim,非我复述)。它自己 `nl -ba` 读了两个文件、`git symbolic-ref` 确认 origin/HEAD=main、`grep` 了 docs/agent/*.md 找有无绕过说明(没有),然后**实际执行** `sh git-guard.sh merge-pr 197 --integration main` 复现了 die,CONFIRM,severity unchanged。
  · R4 Opus 裁决: REQUEST_CHANGES。逐条尊重了 Codex 的 CONFIRM(未无凭无据驳回);额外做了全量 diff 补扫,用 `gh repo view --json visibility` 核实仓库是 PUBLIC,抓到前三轮都没提的"生产 KMS 拓扑硬编码进公开仓库"这条新发现(topology leak);还独立核实了 .pilot.yml 的 pr_daemon_root 键与 pilot skill 内置默认值重复(冗余)。
- 机械证据:
  · `git log --all --oneline -- imx93-docs/ kms/docs/dk2-school-wifi/`(fetch --all --prune 后,覆盖全部 8 个远程分支)= 0 命中,证明两个新忽略目录从未入过库,纯预防性 gitignore。
  · `bash -n kms/deploy/selfcheck.sh` = 语法通过。
  · `sh git-guard.sh merge-pr 197 --integration main` = 复现 "integration 'main' is a trunk branch" 报错(Codex R3 独立跑出,我事后未重复但信任 Codex 的可复现命令输出,因其在隔离 worktree 内对着 PR head 的真实文件跑)。
  · `gh repo view AAStarCommunity/AirAccount --json visibility,isPrivate` = 我自己独立重跑核实 `{"isPrivate":false,"visibility":"PUBLIC"}`,验证 R4 的 topology-leak finding 站得住,不是幻觉。
  · `grep -n "repoId\|aliases" ~/.claude/skills/goutou/SKILL.md` = 确认 goutou 只消费单数 repoId,不读 aliases,验证 R2 的死配置 finding。
- **DeepSeek flash 评级**: **2/5** — R1a/R1b 两遍都完全没扫到本 PR 真正的阻塞项(.pilot.yml 与 pilot 自身 guard 矛盾),因为它们只看了 diff 里"看起来像代码"的 shell 脚本,忽略了三个 YAML/JSON/Markdown 配置文件——这恰恰是本 PR 唯一藏着真 bug 的地方。R1b 给出的那条 Medium(硬编码 IP)还判severity过重(把内网 VPN 标识符当密钥处理)。R1a 的建议(补 -e)是反模式,与脚本设计意图相反。两遍加起来 1 条 Low 站住,1 条 Low 判断方向对但被 R2 重新框定为拓扑泄露而非硬编码本身,其余全部要么假阳性要么完全跑题。改进建议:R1 prompt 应显式提示"非代码类文件(.yml/.json/task 文档)如果与本仓库/工具链已有的自动化脚本存在字段级耦合,也要检查一致性",而不是隐含假设"配置/文档文件天然安全,只需看 shell/代码文件"——这次的核心 bug 恰好完全长在配置耦合层。
- 与 skill 设计是否一致: 一致。4-round 的每一轮都真实跑了(不是虚标);R2/R3 的分工(R2 独立发现 + R3 用真实命令对抗验证而非纯推理)是本轮价值最大的部分,直接对应 skill 里"credibility = mechanical evidence, not model count"的硬性要求。
- 改进建议: 无需改 skill 本身;这次的执行完全符合设计,唯一值得记的是"R1 对纯 config/docs 文件的盲区"这个模式(pr-daemon-loop v4 pipeline 的已知短板之一,建议后续在 R1 prompt 模板里补充上述提示)。
