## APPROVE — pilot 三级规划台账

纯文档 + 一个工具配置，零代码改动。这类 PR 值得审的不是 diff 本身，而是**它对仓库现状做的事实断言**——你在 PR 描述里说这四条是「对着 master 的代码重新核过、不是照抄 7 月 2 日的结论」，我逐条独立核了一遍。

### 四条「beta 阻塞项已闭合」——全部属实

| 断言 | 核实结果 | 我看到的证据（`origin/master`） |
|---|---|---|
| `operator/status` 500（`hasRole(undefined)`）已修 | ✅ | `operator.controller.ts` 里有显式 guard：`if (!address || !isAddress(address)) return { …, registered: false, spoStatus: null, v4Status: null }`，注释也点明了 `passing undefined to the contract's hasRole(user) reverts`。第二个端点另有 `targetAddress` 的 undefined 分支 |
| 服务存活监控已有 | ✅ | `scripts/ops/yaa-liveness.sh` + `io.aastar.yaa-monitor.plist` + `io.aastar.yaa-frontend.plist` 三个文件都在 |
| 社会恢复已验证（48h timelock 链上证明） | ✅ | `docs/SOCIAL_RECOVERY_TEST_REPORT.md` 里写明目标是证明 `executeRecovery()` 在 48h 前 revert，且 `RECOVERY_DELAY_MS = 48*60*60*1000` 与合约的 `RECOVERY_DELAY` 对齐 |
| 建号已脱离 legacy 路径 | ✅ | `CreateAccountDialog.tsx` ~169-199 用的是 `prepareCreateWithPasskey` + `initialTokenConfigs.map(...)`，注释明确写了 `replaces the legacy single-shot createWithP256Guardians` |

把这四条记为 DONE 并另开 T1.1.5 回写评估文档，是对的处理方式。

### `.pilot.yml` 实际解析验证

不只是肉眼看，用 `yaml.safe_load` 真解析了 PR head 上的文件：

```
✓ {'base_branch': 'master', 'integration_branch': 'master',
   'protect_patterns': ['release', 'hotfix', '7702'],
   'remote': 'origin', 'allow_remote_cleanup': False, 'docs_dir': 'docs/agent'}
protect_patterns 类型: ['str', 'str', 'str']
```

`"7702"` 加引号是必要的——不加会被 YAML 解析成整数 `7702`，分支名匹配就废了。你处理对了。

### ✅ Rejected

DeepSeek 安全轮报了一条 `[Medium] .pilot.yml 允许直推 master、绕过 review gate`。**核实后不成立**，两个独立理由：

1. GitHub 侧 `master` 的分支保护实际是 `required_approving_review_count: 1` 且 `enforce_admins: true` —— 配置文件里写什么都改不了这个。
2. 注释里提到的 `git-guard.sh` 确实存在，只是在工具侧（`~/.claude/skills/pilot/scripts/git-guard.sh`）而不是仓库里，所以「仓库里搜不到这个文件」不构成问题。

`integration_branch: master` 是如实反映现状（#433–#449 全是直接合 master，本仓库没有 preview 分支），注释也把为什么不能写 `preview` 讲清楚了——写成 `preview` 反而会让 `merge-pr` 拒绝一切合并。

### 一条建议

R1 提到 T1.4.1（gas retry，标了「涉钱」）的验收命令只有 type-check/lint，没有对 gas 上限的断言。涉钱的 task 建议把验收命令写成可机器验证的硬断言（比如断言重试后的 gas 不超过某个倍数上限），否则「验收通过」和「逻辑正确」之间还是隔着人工判断。

---

<sub>🤖 2-round: DeepSeek v4-flash R1a/R1b 并行 → 裁决。纯 docs + 工具配置、零代码改动，按既定规则不跑 PK。工具实证：`yaml.safe_load` 解析 PR head 上的 `.pilot.yml`；对 `origin/master` 用 `git show` 逐条核四项断言的代码证据；`gh api` 读 master 分支保护规则驳回 R1b 那条 Medium。</sub>
