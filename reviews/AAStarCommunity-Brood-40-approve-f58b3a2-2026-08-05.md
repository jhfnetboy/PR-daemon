## Verdict: APPROVE（首轮，head `f58b3a28`）—— **修法选对了那一侧，而且我把三条路径都跑过了**

`dist` 可复现守卫被 `projectHealth.averageTaskAge` 这个按墙钟算的字段带红。这个 PR 在比对**之前**把它 pin 回已提交的值。

**三件事我实跑验证：**

**1. YAML 真解析 + heredoc 终止符落在行首。** 这是这类改动最容易踩的坑——`python3 - <<'PY'` 的终止符如果带前导空白就不会终止 heredoc，整段脚本会被当成 python 输入吞掉。我用 `yaml.safe_load` 解析后把 `run` 脚本抽出来看实际字符串：
```
heredoc 起始行 19: "python3 - <<'PY'"
heredoc 终止行 34: 'PY'   → 行首 ✅
```
YAML 块标量剥掉公共缩进之后，`PY` 确实在列 0。三个 job（`task-yaml` / `docs-gate` / `dist-reproducible`）都解析正常。

**2. 正常路径真的把漂移抹平了。** 我把 `dist/api/statistics.json` 里的值改成 `99999`（模拟时钟漂移），跑那段 python：
```
pinned averageTaskAge to committed value 98 (1 site(s))
→ git status --porcelain dist/api/statistics.json  为空
```
守卫由红转绿，而且**只动了这一个字段**。

**3. R1a 说的那个失败路径不成立。** 它断言「`git show HEAD:` 在文件未提交时会报错并让 workflow 失败」。我建了个临时 git 仓库、把文件放进工作区但**从不提交**，跑同一段脚本：
```
HEAD 里有这个文件吗: 无   ← 正是它说的场景
no committed averageTaskAge to pin against — comparing as-is
rc=0                      ← 不挂
文件内容: {"averageTaskAge": 77}   ← 没被改坏
```
`subprocess.run` **没有传 `check=True`**，而且代码显式写了 `if old.returncode == 0 else None`。两道都挡住了。

### 三个设计判断我认为都是对的

- **中和而不是从 payload 里删掉这个字段** —— 注释自己论证了：SPA bundle 会读它，删掉等于「为了让 CI 好看而在真实站点上把一个真数字抹白」，那是修错了一侧。这个取舍写得比修法本身更有价值。
- **文本替换而不是 JSON round-trip** —— 重新序列化会引入自己的字节差异（非 ASCII 转义、键序），**制造出这个 job 本来要检测的那种假 diff**。判断准确。
- **只 pin 一个整数，其余每个字节照旧受守卫保护** —— 范围收得很紧。

### 非阻塞

- **[Low] pin 到「已提交的值」= 只保证「和提交的那份一致」，不保证语义正确。** 如果某次提交里这个数字本身就是错的，守卫会一直绿着替它背书。注释里其实已经隐含了这个口径，但值得写明一句——否则以后有人可能会指望这个守卫顺便校验数值。
- **[Low] 正则 `"averageTaskAge":\s*-?\d+` 不接受小数。** 现在 CLI 产出的是整数（我看到的是 `98`），所以今天没问题；哪天它改成 `98.5`，`m` 会匹配不上 → 走「no committed value」分支 → 守卫又开始随机变红，而且**不会有任何提示说明原因**（那条 print 的措辞是「没有可 pin 的已提交值」，看不出是格式变了）。建议正则放宽成 `-?[\d.]+`，或者在匹配失败时把实际读到的片段也打出来。

### Assumptions

- 在独立 worktree（head `f58b3a28`）和一个一次性临时 git 仓库里验证，未改动 `~/Dev/aastar/Brood` 任何文件；worktree 跑完 `git status --porcelain` 为 0。
- **CI yaml 是真解析的**（`yaml.safe_load`），不是手动模拟步骤命令——heredoc 终止符那条只有真解析才看得出来。
- **R2/R3/R4 未跑** —— 单文件、单步骤的 CI 修复，无争议项，三条路径都有我自己实跑的输出。本 review 标 **2 轮 + 机械验证**，不冒充 4 轮。

---
*Reviewed by clestons（`$pr` v4，**2 轮 + 机械验证**，首轮 head `f58b3a28`）：DeepSeek R1a
（`deepseek-v4-flash`；1 条实测证伪）→ Sonnet 机械验证（`yaml.safe_load` 解析并抽出 run 脚本核对
heredoc 终止符位置、把字段改成 99999 后实跑 pin 脚本确认 diff 转干净、建临时 git 仓库复现
「HEAD 里没有该文件」场景确认 rc=0 且文件不被改坏）→ **Opus R2 未跑（单步骤 CI 修复）；
Codex R3 未跑；R4 未跑**。*

### 自评

- **DeepSeek v4-flash 本轮：2/5。** 唯一一条 finding 指对了位置（`git show HEAD:` 那一句确实是这段脚本里唯一会失败的外部调用），但**没读旁边那两个守卫**——`capture_output=True` 且没有 `check=True`、以及显式的 `returncode == 0` 三元。它给的建议（`|| true` 或 `git cat-file -e`）恰恰是代码已经用等价方式做过的事。
- **下次怎么榨出更多信号**：这类「往 CI 里塞一段脚本」的 diff，最该问的是**它自己会不会成为新的失败源**。下次在 prompt 里写死：「对新增脚本里的每一个外部调用（`git` / `subprocess` / 文件 IO），说明它失败时会发生什么，并指出代码里对应的守卫在哪一行；找不到守卫才算 finding」。要求它**指出守卫所在行**，就能把这类「有守卫但没看见」的误报挡掉。
