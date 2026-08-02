## REQUEST_CHANGES — `docs(oob)` 串口救板工具

工具本身要解决的问题是真的，两个脚本的结构也清楚。但 `serial-run.py` 的标记解析有一个**可复现的 High**：每条命令的真实输出会被整个丢掉。这条会连带把 `mx93b-serial-poweroff.sh` 的安全守卫架空，所以先请修再合。

---

### 🔴 Blocking 1 — `__E__` 标记匹配到的是命令回显，不是标记本身（实测复现）

`serial-run.py` 发的是 `send(cmd + '; echo __E__$?')`。shell 会先把这一整行回显回来，所以缓冲区里 `__E__` 的**第一次出现是在回显里**，而不是执行结果里。于是：

- `if '__E__' in buf: break` —— 可能在真实输出到达前就跳出
- `body = clean[:clean.find('__E__')]` —— 从回显处截断，**真实输出全部落在截断点之后，被丢弃**

我把 `drain()` / `slow()` / `send()` / 解析这一段逐字复制出来，接到一个真实 pty 上跑的 `bash`（只换了传输层，逻辑没改）：

```
=== RAW BUFFER ===
'whoami; echo __E__$?\r\njason\r\n__E__0\r\nbash-3.2$ '
=== body after truncation ===
'whoami; echo '
=== FINAL printed output ===
''
=== expected ===
'jason'
```

`rc` 是对的（`re.search(r'__E__(\d+)')` 需要数字，回显里的 `$?` 不匹配，所以命中了真标记 `__E__0`），但**标准输出恒为空**。

> ⚠️ 与 PR 描述的出入，需要你确认：描述里说关机流程已对板 B 实跑成功。但按上面的行为，守卫的 `who=` 会拿到空串 → `grep -q root` 失败 → 脚本应该在第一步就 `✗ 没拿到 root shell` 中止，根本走不到关机。所以要么板 B 的 console 回显行为和普通 echoing shell 不同，要么当时守卫是**靠控制台残留文本**通过的（见 Blocking 3）。我的复现是 pty + bash，不是真串口 + getty，这个差异我没法在这里消掉——但两种解释都需要说明，不能当作没事。

**修法（一次解决三个 bug）**：用同一个正则决定全部三件事——
```python
m = re.search(r'__E__(\d+)', clean)
# break 条件也用 m，而不是 '__E__' in buf
body = clean[:m.start()] if m else clean
rc = int(m.group(1)) if m else 124   # 没匹配到 = 超时，必须是错误，不能沿用上一条的 rc
```
更稳的做法是每次运行生成一个 nonce（`__E__<nonce>_<rc>`），回显和结果就再也不会撞。

---

### 🔴 Blocking 2 — `drain()` 让 `--timeout` / `--read-secs` 都不是上界

```python
if n:
    b += s.read(n)
    end = time.time() + t     # 有数据就续期
```
`drain(t)` 只在**静默 t 秒**后才返回；而调用方 `while time.time() < end: buf += drain(0.4)` 只在两次 drain **之间**检查外层 deadline。控制台持续刷日志时 drain 永不返回 → `--timeout` 失效、`--read-secs 25` 同样失效，工具无限挂起，`buf` 无界增长（且 `'__E__' in buf` 每轮全量重扫，O(n²)）。

讽刺的是：板子在被救援时正是最可能刷 kernel log 的状态——**这个工具在它被设计要处理的场景下最容易挂死**。

**修法**：给 `drain` 传一个绝对 deadline（`hard_end`）作为 while 的第二个条件，并给 `buf` 设上限。

---

### 🔴 Blocking 3 — 关机守卫可以被启动日志文本满足

```bash
who="$("${RUN[@]}" 'whoami' 'hostname' 2>/dev/null || true)"
echo "$who" | grep -q root  || abort
echo "$who" | grep -qi imx93 || abort
```

守卫对**合并输出**做两次独立子串 grep，既不检查 `__E__0` 标记是否出现，也不检查哪条命令产生了哪个串。内核/U-Boot 启动日志本身就能同时满足两条：`Machine model: NXP i.MX93 11x11 EVK` 命中 `imx93`，`re-mounted root filesystem` 命中 `root`。即：**一块没有 shell、只在刷启动日志的板也能通过守卫**，然后收到一个盲发的 `systemctl poweroff`。

叠加 Blocking 1 之后更糟：真实输出既然被丢弃，能让守卫通过的就只剩控制台残留噪声了。

**修法**：`serial-run.py` 输出带 rc 的分条结果，守卫要求 `whoami` 精确等于 `root` 且 rc=0、`hostname` 用 `grep -qx` 精确匹配。

---

### 🔴 Blocking 4 — 守卫和关机各自解析设备（TOCTOU），可能关错板

`DEV` 默认是字符串 `auto`，而守卫和 `systemctl poweroff` 是**两个独立的 python 进程**，各自重跑一次 `find_dev('auto')` 重新 glob `/dev`。两次之间枚举结果可变（故障板掉线、另一个适配器成为唯一候选、第二接口枚举出来），**守卫验的设备不保证是被关机的设备**。

而且 `grep -qi imx93` 匹配的是 **SoC 家族**不是这块板：实验室里只要还插着另一块 i.MX93，`auto` 选中它、守卫照样打印「✓ 确认是 imx93 板」，然后关掉错误的板。脚本名字叫 `mx93b-*`，检查却分辨不出 B 和 A。

**修法**：wrapper 里解析一次拿到具体设备路径（加个 `--print-dev`），后续一律用具体路径；破坏性脚本里直接拒绝 `auto`；主机名检查用 `MX93B_HOSTNAME`（默认 `mx93b`）+ `grep -qx`，不要用家族子串。

---

### 🟡 Confirmed（非 blocking，建议一并修）

| | 位置 | 问题 |
|---|---|---|
| M | `serial-run.py` 超时路径 | 没读到 `__E__` 时 `rc` 沿用上一条命令的值且仍以它退出；「命令成功」和「压根没读到结果」不可区分。迟到的标记会被下一条命令的 buf 吃掉，后续所有命令的 rc/输出整体错位一格 |
| M | `serial-run.py` 登录状态机 | 固定 sleep + 单次 drain 的盲猜。时序错位时 `--password` 可能发在**回显开启**的 `login:` 提示处，明文密码打上 console 并进系统 auth 日志 |
| M | `--password` 走 argv | `ps` 里可见；且默认空值在板子确实需要密码时是静默失败（只发了个 `\r` 就当作已登录继续）。建议读环境变量，并把「发完仍停在 `Password:`」当硬错误 |
| M | 无串口独占锁 | macOS 上 `/dev/cu.*` 非排他。已有 screen/minicom 连着时，守卫可能读到别人会话的输出，而关机命令照发。脚本注释里自己提到「是否已在别处占用串口」，代码没做检测。建议 `fcntl.flock(..., LOCK_EX\|LOCK_NB)` |
| L | `serial.Serial()` 无 try/except | `s.close()` 不在 finally；异常 traceback 被 wrapper 的 `2>/dev/null` 吞掉，操作员只看到误导性的「没拿到 root shell」 |
| L | wrapper 的 `2>/dev/null` | 同时吞掉了 `find_dev` 的「多个串口设备」「找不到串口设备」——这恰恰是最可能的真实失败原因 |
| L | docstring 与实现不符 | 说 `--read-secs` 模式恒 0，实际 `break` 后仍 `sys.exit(rc)` |
| L | `--read-secs` 缓冲到最后才打印 | 盯着板子关机的人 25 秒看不到任何东西，建议流式输出 |

### ✅ Rejected

- DeepSeek R1b 报的「命令注入」——`cmds` 是操作员自己敲的位置参数，无不可信输入源，且进程本来就有 root console 的裸写权限，不存在提权。

### 建议

- 让 `serial-run.py` 输出机器可读的分条结果（每行一个 `{"cmd":…,"rc":…,"out":…}`，或成对的 `__B__<nonce>` / `__E__<nonce>:<rc>`），wrapper 就再也不用 grep 自由文本——这一个改动同时干掉 Blocking 1、rc 错位、和 Blocking 3。
- 文件放在 `docs/` 且标题是 `docs(oob)`，但这是 mode 100755、唯一用途是关一台真板子的可执行运维工具。归在 docs 下会绕过运维脚本的评审/测试要求，也不会被任何 lint/CI 覆盖。建议移到 `kms/tools/` 或 `scripts/oob/`，docs 里只留说明和链接。
- 加个 `README.md`：pyserial 前置依赖、「先关掉 screen/minicom」、守卫中止时该怎么办——会用到这套工具的人本来就已经处在糟糕的处境里了。

---

<sub>🤖 4-round pipeline: R1a/R1b DeepSeek v4-flash（并行，全量+安全）→ R2 Opus 独立评审 → R3 PK 挑战 → R4 Opus 裁决 + 全量补扫。Blocking 1 由 R4 补扫发现（前三轮均漏），已用 pty 复现验证。R3 本轮为 DeepSeek 兜底：`codex exec` 零输出挂起 7 分钟被 kill。</sub>
