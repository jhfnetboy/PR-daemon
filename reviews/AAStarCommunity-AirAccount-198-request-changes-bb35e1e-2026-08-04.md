## AAStarCommunity/AirAccount#198 — REQUEST_CHANGES

- Head: `bb35e1e` (feat(oob): 带外工具补全 — serial-selfupdate 自拉升级 + 电源/控制台/WiFi 脚本)
- Pipeline: pr-daemon-loop v4, 4-round (DeepSeek R1a+R1b 并行 → Opus R2 独立通读 → Codex R3 对抗 PK → Opus R4 最终裁决)，security-sensitive hard rule 强制 4-round：minisign 信任锚 + 串口刷板。

## Blocking

**[High] `kms/scripts/oob/serial-selfupdate.sh:50` — pin 死的公钥 `B4D4EC2546A19EB2` 验不过任何一个已存在的 release，脚本今天跑不通。**
机械复现（不是推理）：下载真实的 `airaccount-node-v0.29.1`（脚本 README/用法示例里用的正是这个 tag）release 资产，直接跑 minisign：
```
$ minisign -Vm airaccount-node-v0.29.1.tar.gz -p pinned.pub  -x airaccount-node-v0.29.1.tar.gz.minisig
Signature key id in ...minisig is 8A54AF6372050E86 but the key id in the public key is B4D4EC2546A19EB2   (rc=1，失败)
$ minisign -Vm airaccount-node-v0.29.1.tar.gz -p updater.pub -x airaccount-node-v0.29.1.tar.gz.minisig
Signature and comment signature verified   (rc=0，release 自带的旧公钥反而验证通过)
```
即：这个 release 实际签的是旧 key `8A54AF6372050E86`，本 PR pin 的却是新 key（`kms/deploy/updater/updater-pubkey.pub` 由 #196 建立，#196 仍是 OPEN 状态、未合并）。按脚本自己 README 给的示例命令跑，今天会直接 `fail "minisign 验签失败 —— 签名不是 pin 的可信公钥所签,拒绝(疑似投毒/换源)"`。检查了最近 12 个 release，11 个根本没有 `.minisig` 资产（在 `SIGFILE` 检查处直接 fail），唯一有签名的这一个又是旧 key——救板工具在它自己文档给的例子上 12/12 失败。
Codex R3 独立复现同一结论（喂了脚本 hunk + 我的机械验证结果，要求它 CONFIRM/CHALLENGE）：`[CONFIRM] Hunk A pins new key; verified v0.29.1 minisig uses old key, so documented example aborts.`
Fix：merge 前用新 key 重签至少一个 release（如 v0.29.1），或者明确注明"本工具仅对 #196 之后发布的 release 生效"并把 README 示例换成一个真实能用的 tag；#196 应先于/随本 PR 合并。

**[High] `serial-selfupdate.sh:331-336`（健康轮询）+ `serial-selfupdate.sh:182-187`（rollback）— 超时预算错配 + 回滚结果从不校验，组合后可能"服务坏了但报告说已回滚成功"。**
健康检查在**一条**串口命令里跑 `for i in 1..10: curl -m5; sleep3`，最坏 ~80s，但外层 `python3 "$SR" --timeout 45` 只给 45s。真正该触发回滚的那条路径上，`serial-run.py` 45s 超时先到，返回空结果 → `health=''` → 触发 rollback，但此时板子那边的 shell 还在轮询循环里跑（还有 ~35s 没跑完），下一条发给它的 rollback 命令是打进一个还在忙的 shell。而 `rollback()` 本身把结果整体扔进 `>/dev/null 2>&1 || true`，从不解析回滚那条 `systemctl is-active` 到底成没成功，统一打印"已尝试回滚"——回滚失败和回滚成功在输出上完全看不出区别。
Codex R3 独立确认：`[CONFIRM] Hunk A2 health command can run 10*(5+3)=80s under --timeout 45, before rollback.` / `[CONFIRM] ... rollback redirects JSON to /dev/null and unconditionally fails with "已尝试回滚".`
Fix：轮询预算收进单命令超时内（如 5 次 ×(3+2)s ≈25s，`--timeout` 相应放宽到 ≥40s）；`rollback()` 用 `--json` 拿到 `is-active` 实际值，区分打印 ROLLBACK_OK / ROLLBACK_FAILED 并用不同 exit code。

**[Medium] `serial-selfupdate.sh:177`（`ins_rc` 分支）+ `:306-309`（备份/替换/启动三条串口命令）— 装新版失败时没走回滚，且服务仍会被重启到半写状态的二进制上。**
`cp -a → systemctl stop && install → systemctl start` 这三条是分别作为三个独立字符串发给 `serial-run.py` 的（验证了 `serial-run.py:172-189`：`for i, cmd in enumerate(a.cmds)` 无条件跑完每一条，不因前一条非零就中断）。所以即使第二条 `install` 失败，第三条 `systemctl start` 依然会执行——对着一个可能被截断的 `$REMOTE_BIN` 重启服务。而脚本这时只是 `fail`，没调用已经定义好、且此刻备份已经在 `$BAK` 的 `rollback()`。
Codex R3 独立确认：`[CONFIRM] Hunk C exits via fail on ins_rc; separate serial args mean command 3 still starts service.`
Fix：`ins_rc != 0` 时改调 `rollback()`；三条命令用 `&&` 串成一条发送，让板子端 shell 自己短路。

**[Medium] `serial-selfupdate.sh:128-146`（下载校验批次）— 同一条 `serial-run.py` 无短路特性，导致 sha256/tar-path 检查形同虚设，坏包已经被解压了才被 Mac 端事后拒绝。**
这条批次是 `curl 下载 → sha256sum -c → tar 路径检查 → tar xzf` 四条独立命令，同样因为 `serial-run.py` 无条件跑完全部，即使第 2 条 sha256 校验失败或第 3 条查出 `BADPATH`，第 4 条 `tar xzf` 依然会在板子上执行——`fail` 只在 Mac 端事后基于 `sha_out`/`path_out` 才触发。可利用性受限于必须先过 Mac 端 minisign 关（需要伪造签名），但这条防线的设计意图是"先查后展开"，实际是"先展开后查"。
Fix：把这四步用 `&&` 串成一条命令发送，让板子端在 sha256/路径检查失败时短路，不执行 `tar xzf`。

**[Medium] `serial-selfupdate.sh:11` 注释 vs `:137` 实现 — 文档承诺的 tar 加固比实际实现的强得多。**
头部注释写"tar 加固(拒绝绝对路径/../symlink/hardlink/设备节点/多顶层)"，但 `:137` 实际只有 `tar -tzf node.tgz | grep -Eq '^/|(^|/)\.\./'` 一条路径字符串检查，完全没有对 tar entry 类型的检查（symlink/hardlink/device node 都不会被这条 grep 拦下）。"多顶层"目前是意外地被后面 `test -f airaccount-node-*/kms/kms-api-server` 的 glob 多重展开报错间接挡住（不是设计出来的防御）。
Codex R3 独立确认：`[CONFIRM] Hunk B only rejects absolute/../ path strings; no tar type inspection for symlink/hardlink/device nodes.`
Fix：要么用 `tar -tvzf` 做 entry 类型检查落实注释承诺的防御范围，要么把注释改成如实反映当前只做路径字符串检查。

## Confirmed findings（Low，非阻塞）

- `mac-mini-console-dk2.sh:68-77` — 日志轮转发生在 `has-session` 提前退出检查**之前**：对一个已在跑的常驻控制台重复执行 `up`，会把 `$LOG` 从 `pipe-pane` 打开的 fd 底下 rename 走，之后的输出继续写进 `$LOG.1`、`$LOG` 永久空掉；再下一次轮转还会把 `$LOG.1` 的活日志静默 mv 成 `$LOG.2` 丢弃。
- `mac-mini-console-dk2.sh` / `kms/scripts/wifi-switch.sh` — 两个新脚本 mode 是 `100644`，但文档说 `./script.sh` 直接执行，缺可执行位。
- `kms/scripts/wifi-switch.sh:384` — `awk -v s="$TARGET_SSID" '$0 ~ s'` 是对整行（含 bssid/flags）做正则/子串匹配后取 `head -1`，SSID 若和别的行有前缀重叠会连错网。
- `serial-selfupdate.sh:355` — `rm -rf /tmp/su` 只在成功路径执行；每条 `fail`/`rollback` 退出都会把已解压、被判定为不可信的目录留在板上。
- 合并顺序悬空引用：README/脚本注释说信任锚公钥"= `kms/deploy/updater/updater-pubkey.pub`(#196 确立)"，但 #196 仍 OPEN，该文件在本分支树里不存在。核实了 pin 死的公钥**值**本身与 #196 (commit `b91e195`) 将引入的内容逐字节一致，纯粹是引用了一个还不存在的路径，不是密钥内容错误。

## Rejected（来自 R1）

- R1a "wpa_cli 缺 `|| true`" — 那一整批命令末尾已经是 `>&2 || true`，`set -e` 不会在那触发。
- R1a "jq 用在板上但注释说板上没 jq" — 那个 `jq` 是解析已经取回 Mac 端的 `$verjson`，跑在 Mac 上；板子端解析全是 grep，符合注释。
- R1a "`#!/bin/sh` 用 `seq` 是 bashism" — `seq` 是外部二进制（busybox 也带），不是 shell 内建，`/bin/sh` 下能跑。
- R1b 五条"env var 命令注入"（`WIFI_SELECT_ID`/`PORTAL_MARKER`/`EXPECT_VERSION`/`REMOTE_BIN`/`KMS_SERVICE`）— 都是操作员手动跑这个 Mac 端救板工具时自己设的环境变量，不是攻击者可控输入，R1b 自己 prompt 里的 input-controllability rule 本就该排除这类。
- R1b "硬编码 pubkey 是漏洞" — pin 死公钥正是这个方案的核心防御（脚本注释明确写"绝不信 release 自带的 updater.pub"，避免循环信任），不是漏洞。
- R1b "TARBALL_URL SSRF" — 核实 `gh release view --json assets` 返回的 `.url` 是 `browser_download_url`，且下载内容还有 sha256 pin 住，不构成 SSRF。
- R1b "DECLARED_SHA 让完整性校验被绕过" — 该 sha256 比对的对象已经是 Mac 端 minisign 验证过的同一份 tarball，minisign 才是主防线，sha256 只是在途完整性的次要检查。
- R1b "$BAK 在 /tmp 有符号链接风险" — 事实错误，`$BAK` 是 `$REMOTE_BIN.bak-$STAMP`，在 `/opt/airaccount/` 下，不在 `/tmp`；只有 `$WORK`（`mktemp -d`）在 /tmp，且用法标准。

## R1（DeepSeek 双通道）

R1a 全量扫描给了 5 条（1 Medium + 4 Low），只有"tar 类型检查缺失"这条（后被 R2/Codex 独立确认）站得住，其余 4 条都是误读（`|| true` 位置、Mac/板端执行上下文搞反、把外部命令当 bashism）。R1b 安全专项给了 9 条，**全部被拒绝**：5 条是操作员环境变量误判为攻击面（违反了它自己 prompt 里定义的 input-controllability rule），2 条把 pin 公钥这个正确设计当成漏洞，1 条没看到 minisign 才是上游主防线，1 条关于 `$BAK` 路径的事实错误。

## R2（Opus 独立）→ R3（Codex PK）→ R4（Opus 最终裁决）

R2 独立通读全量 diff（先于看 R1），自己推出了最关键的 [High] pin-key-验不过-任何-release 这条，随后也被我本人用真实下载的 release + `minisign -Vm` 命令机械复现（不是推理）。R2 另给了 4 条 Medium（健康轮询超时预算、rollback 结果不校验、`ins_rc` 分支未回滚、tar 加固注释与实现不符）+ 若干 Low。R3 Codex 用 `scripts/codex_pk.sh` 直接 Bash 前台同步调用（未走 Agent(codex:codex-rescue)），喂了脚本原文 hunk + 我的机械验证结果，5/5 全部 CONFIRM，没有一条被驳回。R4 在此基础上做全量 diff 补扫，读了 `serial-run.py` 源码验证"批次内命令互不短路"这一底层机制，额外抓到一条前三轮都没提的新 Medium（下载校验批次同样因为无短路而形同虚设，坏包被解压后才事后拒绝）。

## 结论

信任锚设计本身（Mac 端 minisign pin 公钥 → 板端 hash-pin）是对的，没有找到绕过手段。问题全在接缝处：pin 的 key 属于一条还没落地的签名链（#196 未合并），导致这个救板工具从合并那天起就打不通任何现有 release；再加上串口命令批次普遍缺乏失败短路，使得"先验证再执行"的意图在多处退化成"先执行再事后报告"。这些都不是不可恢复的（备份永远先于替换发生），但这个工具存在的意义就是在 SSH 已经不通的时候接管，"状态不明、需要人工在同一条已经不可靠的通道上诊断"恰恰是它本该消除的失败模式。
