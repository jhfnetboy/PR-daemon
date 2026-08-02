# AAStarCommunity/AirAccount#192 — APPROVE ✅ [2-round]

承接 #191 的 2 个 Low 残留 follow-up，质量好，无新问题。

## 变更概要

| 文件 | 改了什么 |
|------|----------|
| `kms/deploy/updater/aastar-node-updater.sh` | +`fetch_required` 分流 curl 22(HTTP 4xx/5xx→die) vs 其它网络错误(静默重试)；`requires_ta_version` schema 加 semver 正则 |
| `kms/tests/updater/test-updater.sh` | +T20(4xx拒绝)、T20b(网络静默)、T21(非法requires_ta_version) |

## 逐项验证

### 1. `fetch_required` — curl 22 分流 ✅
- `fetch()` 用 `curl -fSL`（line 163），`-f` 下 curl exit 22 **仅** HTTP 4xx/5xx，不涵盖 DNS/连接/超时。分类正确。
- `die()`（line 41）始终 `exit 1`，fail-closed 语义无漏洞。
- `give_up_quiet()`（line 43）`exit 0`，静默重试。两条路径互斥覆盖所有非零退出码。
- **正确。**

### 2. `requires_ta_version` semver 正则 ✅
- jq regex `^v?[0-9]+\.[0-9]+\.[0-9]+$` 与 `ver_valid()`（line 86）和 `ver_norm()`（line 64）一致——都 strip `v` 前缀后再校验 `x.y.z`。整个版本处理管线对 "v" 前缀处理统一。
- 与 `min_version` 的正则完全一致（同一行 and-chain），无不一致。
- **正确。**

### 3. 测试覆盖 ✅
- T20: `exit 22` → updater check 失败 + current 不变（验证 die 路径）
- T20b: `exit 7` → updater check exit 0 静默（验证 give_up_quiet 路径）
- T21: `requires_ta_version:"latest"` → schema 拒绝 + current/seen 均不污染
- **充分。**

## DeepSeek R1a/R1b 交叉验证

| 来源 | Finding | 验证结果 |
|------|---------|----------|
| R1a [Medium] `die` 可能不退出非零 | die() 始终 `exit 1` | ❌ 假阳性 |
| R1a [Low] "v" 前缀未在整个管线强制 | ver_valid/ver_norm 均 strip v | ❌ 假阳性 |
| R1b [Medium] curl 22 也涵盖其他失败 | `-f` 下 22 仅 HTTP 错误 | ❌ 假阳性 |
| R1b [Low] version 字符串路径遍历 | version 仅用于 jq/semver 比较，不参与文件路径 | ❌ 假阳性 |

## Issue compliance

N/A — 无关联 issue。

## 结论

无阻塞问题。两个修复合计 52 行增/3 行删，改动精准、测试充分、无害回归路径。`fetch_required` 提升了对端点异常（404/篡改/撤除）的感知能力，`requires_ta_version` regex 消除了与 `state.current` 同类的 `ver_cmp→10#` 运算崩溃隐患。

**APPROVE** ✅
