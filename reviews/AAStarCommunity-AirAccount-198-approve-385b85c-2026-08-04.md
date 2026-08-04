## AAStarCommunity/AirAccount#198 — APPROVE

- Head: `385b85c` (fix(oob): 折入 pr-daemon 评审 —— 移出 serial-selfupdate.sh + 修 console/wifi 两处)
- Pipeline: pr-daemon-loop v4, incremental re-review of a REQUEST_CHANGES fix commit (prior head `bb35e1e`). Escalated to R1(DeepSeek dual-pass)+R2(Opus 独立通读)+R4(Opus 最终裁决)；R3 Codex 按 post-R2 全 Low 门控跳过。

## Fix verification — 全部 5 条 blocking + 5 条旧 Low 已解决

上一轮 `bb35e1e` 的 REQUEST_CHANGES 全部围绕 `serial-selfupdate.sh`（pin 死公钥验不过任何现存 release / 健康检查超时预算错配+回滚不校验 / 装失败不回滚+无短路 / 下载校验批次无短路 / tar 加固注释与实现不符）。本次修复**直接整体删除该文件（221 行）**，而非打补丁：

- `git grep serial-selfupdate 385b85c` 在改动树内零残留，逻辑没有以任何形式换皮重新出现
- 5 条 blocking [High]/[Medium] 全部随文件消失 → RESOLVED
- 3 条旧 Low 逐条实证验证：
  - `mac-mini-console-dk2.sh` 日志轮转顺序 — 用 `git show` 读完整文件确认 `has-session` 早退现在真的先于日志轮转执行，其余 `list/down/attach` 分支本就先 `exit`/`exec`，只有 `up` 路径会走到这里
  - `wifi-switch.sh` SSID 精确匹配 — 用合成 `list_networks` 输出（`0\t@JumboPlusIoT5GHz-guest` / `1\t@JumboPlusIoT5GHz`）实跑新旧两条 awk：旧的选中 id 0（错网），新的选中 id 1（对）
  - 两脚本可执行位 — `git ls-tree 385b85c` 确认均为 `100755`
- `serial-selfupdate.sh:355` 只在成功路径清理 `/tmp/su`、README 悬空引用 #196 未合并公钥文件 — 均随文件/文档段一并删除，RESOLVED

`R1a` 对本次增量的唯一发现（wifi-switch.sh SSID 前后空白可能匹配失败）**驳回**：`TARGET_SSID` 只由脚本自己的 `case` 分支传入两个硬编码字面量（`ChinaNet-AuRfsu-5G` / `@JumboPlusIoT5GHz`），不接受用户输入；`wpa_cli` 对 ssid 字段做转义，原始 tab 不可能出现在第 2 列破坏 `-F'\t'` 切分。`R1b`（安全专项）本轮无发现。

## Non-blocking（Low，建议后续跟进）

- **PR 标题/正文已过期** — 标题仍是"serial-selfupdate 自拉升级"，正文变更表仍列 `serial-selfupdate.sh`，"⚠️ 信任锚更新"整节描述的内容本 PR 已不包含。合并前建议改标题+正文，只描述实际范围（电源/控制台/WiFi 脚本）。
- **`kms/docs/auto-update-web-admin-design.md`（已在 main，本 PR 之前由 #194 引入）5 处引用 `serial-selfupdate.sh` 作为 break-glass 恢复路径**（含"板子 SSH/tailscale 全不通"恢复矩阵那一行），本 PR 合并后该文档指向一个仓库里从未真正存在过的实现。建议加"工具待补"标注或开 follow-up issue，别让恢复矩阵悄悄失真。
- **PR 正文承诺"合并后删除僵尸分支 `docs/oob-serial-rescue`"，但该分支只存在于本地（`git ls-remote` 无此远端分支），且现在是被删的 221 行逻辑唯一存活副本** — 真执行该承诺是不可逆的。建议先推远端或另存 patch，再决定是否删除。
- **`serial-power-off-b.sh:4`** — `exec .../mx93b-serial-poweroff.sh /dev/cu.usbmodem5B6D0040831` 不透传 `"$@"`，写死设备路径；被包装脚本里 `$1` 优先级高于 `MX93B_SERIAL` 环境变量，等于同时废掉命令行传参和环境变量两条覆盖通道。脚本自己注释说 A/B 板"同族主机名，靠显式设备区分"——探针换口/换板后这条路径就是唯一的板身份判据，写死后没有任何层能拦住关错板。建议改为 `exec ... "${1:-${MX93B_SERIAL:-/dev/cu.usbmodem5B6D0040831}}"`。
- **`wifi-switch.sh:143`** — `select_network` 30 秒连接超时失败分支只打印 WARN + `return 1`，不调用 `enable_network all` 回滚；而 `wpa_cli select_network` 语义是"选中目标网 + disable 其余全部"。失败后板子处于"目标网连不上 + 其他网络也被禁用"的双重失联状态——这个脚本本身很可能就是通过 WiFi SSH 远程跑的，一次切换失败即断线，只能靠串口救。建议失败分支补 `enable_network all`。

## Suggestions

- `mac-mini-console-dk2.sh` 的 `pick_dev()` 已是死代码（`up` 路径在 heredoc 里内联重实现了同样排除逻辑），注释却仍说"内层用 pick_dev"——删掉或让注释与实现一致。
- 新增的 `mx93a-poweroff.sh`/`mx93b-poweroff.sh`/`serial-power-off-b.sh` 落在仓库根，跟根目录既有的 `power-off2.sh`/`poweroff-imx93.sh` 是同类散件，建议随 #197 仓库卫生思路一并收进 `kms/scripts/oob/`。
- `kms/docs/out-of-band-console/mac-mini-console-dk2.sh` 是可执行脚本却放在 `docs/` 下，与 `kms/scripts/oob/` 的定位割裂，可考虑挪位。

## Rounds

- R1a(DeepSeek-full): 1 条 Low（SSID 空白）— 假阳性，R2/R4 均驳回
- R1b(DeepSeek-sec): 无发现
- R2(Opus 独立通读): 用 `git grep`/`git ls-tree`/`git diff --stat`/合成 awk 用例实证验证全部 5 条 blocking + 5 条旧 Low RESOLVED；独立补 3 条新 Low（标题正文过期、design.md 悬空引用、分支删除承诺）+ 2 条 Info（chmod 修复被 early-exit 跳过、并发 `up` 残余 TOCTOU，均判定不阻断）
- R3(Codex-PK): 按 post-R2 全 Low 门控跳过
- R4(Opus 最终裁决): 复核全量 diff（270 行，5 个改动文件），独立补 2 条 Low（`serial-power-off-b.sh` wrapper 吞参数废掉设备覆盖通道、`select_network` 失败不回滚导致远程板失联）；给出 APPROVE

## 结论

上一轮的信任锚问题不是被"修好"而是被"移除范围"解决——`serial-selfupdate.sh` 整体删除，本 PR 收窄成 5 个低风险运维脚本（日志轮转顺序、WiFi 精确匹配、电源关机 wrapper、串口控制台），逐条机械核实无一引入新的阻断问题。剩下的都是 Low：文档/PR 描述与实际范围脱节，以及两个新脚本里可用性/健壮性小问题（写死设备路径、切网失败不回滚）。均不阻断合并，建议后续 PR 跟进。
