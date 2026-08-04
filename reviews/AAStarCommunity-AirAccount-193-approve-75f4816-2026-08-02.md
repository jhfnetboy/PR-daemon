## APPROVE — 增量复审 `5173488` → `75f4816`

四条 blocking 全部修复，而且是**跑出来验证的，不是读出来的**。你还自己补了针对那两个 bug 的 pty 回归测试，并按建议把工具从 `docs/` 挪到了 `kms/scripts/oob/`。

### 四条 blocking 的验证结果

| | 原问题 | 现在 | 怎么验的 |
|---|---|---|---|
| **B1** | `echo __E__$?` 的标记撞上 shell 回显，每条命令真实输出被整个丢弃 | ✅ FIXED | `printf '__B__%s\n'` 把换行放进**带引号的格式串**里，回显里只有字面量 `\n`，只有真正执行才产生真换行。你的测试 `echo hello` → `out='hello'`（正是我上轮复现出 `''` 的那个用例）。R2 另做了一次扫描：80 列 pty、prompt 长度 45–75 逐一让 nonce 末字符落在**包括第 80 列换行边界**的每个位置，**31/31 无一误匹配** |
| **B2** | `drain()` 收到字节就续期，`--timeout` 不是上界，刷日志即挂死 | ✅ FIXED | `hard_deadline` 绝对截止 + 512KB `cap`，两者都不续期。`yes spam` 无限输出 **0.8s 返回 rc=124**；我另测无 shell 只刷启动日志 → **4.4s 返回 rc=124** |
| **B3** | 守卫 grep 自由文本，启动日志即可满足 | ✅ FIXED | 改成 `--json` 逐条带 rc + `[ "$who" = root ]` 精确相等。我实测：无 shell 的板 → rc=124 守卫中止；`echo rootless` → 精确捕获 `'rootless'`，被 `= root` 正确拒绝 |
| **B4** | `auto` 让守卫和关机各自 glob 设备（TOCTOU），`imx93` 匹配的是 SoC 家族 | ✅ FIXED | 破坏性路径硬拒 `auto`/空，两个进程收同一个显式 `$DEV` 不再 re-glob；hostname 改成对完整板名精确相等 |

> 关于 B3 我把上轮的前提也补验了：真实 i.MX93 启动序列确实能同时满足旧的两条 grep —— `Kernel command line: … root=/dev/mmcblk0p2 rootwait` 给 `root`，`imx93-11x11-lpddr4x-frdm.dtb` 给 `imx93`。上轮那条不是臆测。
>
> PK 轮把 B4 判为 PARTIAL，理由是「同主机名的孪生板」和「两进程之间换了设备」。我采纳为**新的、更弱的残留**（记在下面 Low 里），但原缺陷（family 子串 + 重新 glob）确实已消除，所以不按 PARTIAL 计。

你自己的 `test-serial-run.py` 我完整跑了一遍：**6/6 PASS**，包含输出里含假标记 `__E__deadbeef_0` 不误判、连续命令 rc/输出不错位。`py_compile` + `bash -n` 三个文件全过。

---

### 🟡 遗留问题（不阻塞合并，但建议排一下）

**Medium**

1. **`flock` 其实抓不到 screen/minicom —— 这是唯一一处「声称做了但没做」的地方。** `serial-run.py:60` 的 `fcntl.flock` 是协作锁，而 screen/minicom 根本不 flock。R2 在真实 `/dev/cu.*` 上实测：有对端不加锁地占着设备时，`serial.Serial()` 成功、`flock` 也被授予 —— 工具会**静默地和活着的 console 共用串口**，而报错文案「串口被占用(screen/minicom 还连着?)」方向正好是反的。实测 `fcntl.ioctl(fd, termios.TIOCEXCL)` 有效（非协作的后来者会拿到 `[Errno 16] Resource busy`）。顺带 `import serial` / `serial.Serial()` 仍未包 try，失败是裸 traceback。

2. **`--json` 和 `--read-secs` 同时用会污染 JSON 契约**（`serial-run.py:188-199,214`）：流式的控制台字节先写进 stdout，`json.dumps` 在后面，stdout 就不是合法 JSON 了。实测 stdout：`echo STREAMED\r\nSTREAMED\r\nboard# [{"cmd":"false","rc":1,"out":""}]`。wrapper 目前不会同时用这俩，但都是公开 flag。建议 `--json` 时所有非 JSON 输出一律走 stderr。

**Low**

3. `'login:' in txt`（`:138`）会被**每个串口 console 都会打的 `Last login: … on ttyLP0`** MOTD 误触发。实测：已经在 root shell 的板被带进登录分支，把 `root\r` 当成 shell 命令敲了进去。靠预热能自愈，但**设了 `SERIAL_PASSWORD` 时**，若后续出现形似 `Password:` 的文本，密码就会被当成 shell 命令敲上板子（进 shell history）。建议锚定「以 `login:` 结尾且不是 `Last login:`」的行；另 `or txt.rstrip().endswith('login:')` 是死代码，被前面的 `in` 完全覆盖。
4. 控制台持续刷日志时 512KB `cap` 会先于结束标记触发，于是**每条命令永久 rc=124**（实测：活 shell + `yes` 洪水 → 守卫两条命令 1.7s 内全 124）。是 fail-safe，但工具在那个场景下不可用。建议命中 cap 时保留尾窗继续找标记，或用一个区分「洪水」和「超时」的 rc。
5. 残留 TOCTOU：守卫与关机仍是两个进程，中间**锁被释放**；第二个进程会重跑 `ensure_login` 但**不再核对 hostname**。建议做成 `--require-user root --require-hostname "$HOST"` 单进程完成——这一个改动同时关掉 B4 残留、丢锁窗口和重复登录。
6. `sys.exit(0 if a.read_secs > 0 else rc)`（`:215`）只报最后一条的 rc，且 `--read-secs` 下恒 0，多命令时中间的失败不可见。建议 `results` 里任一 rc≠0 就非零退出。
7. 登录失败判定只看「是否仍停在 `Password:`」，板子打 `Login incorrect` 后重新回到 `login:` 的情况抓不到。
8. `cmd` 是不加引号插进 shell 行的。操作员输入本就是信任模型内的，但含换行或形似标记的字符串能拆行/伪造框定。建议 README 写明这条信任边界，并拒绝含 `\n`/`\r`/`__B__`/`__E__` 的 cmd。

**🔍 一条所有轮次都漏、R4 全量补扫才发现的**

9. `mx93b-serial-poweroff.sh:45-47` —— 关机那步用 `--read-secs 25`，而 `serial-run.py:215` 在这个模式下**硬编码 exit 0**。所以 `set -e` 永远抓不到「板子没理会 `systemctl poweroff`」，脚本随后**无条件**打印「✔ 若上方出现 'reboot: Power down'…」，把验证完全交给操作员的眼睛 —— 一块卡死的板子会给出一个干干净净的 exit 0。建议扫一下流式输出里有没有 `reboot: Power down`，没有就 exit 1。

### ✅ Rejected

| finding | 驳回理由 |
|---|---|
| DeepSeek：预热 3 次全失败却不中止 | 作者已注明是有意的，且真正把关破坏性操作的是下游守卫（rc + 精确 `whoami`/`hostname`），它会中止 |
| DeepSeek：密码在串口上明文 | 串口 console 没有带内认证通道，这一层做不了掩码；密码也从未进入工具的 stdout |
| DeepSeek：`MX93B_HOSTNAME` 可被有 env 控制权的人绕过 | 那是本地脚本的操作员逃生舱，不是信任边界；真正的板身份是那个强制的显式 `$DEV` |
| DeepSeek：nonce 无跨运行防重放 | nonce 是对抗 shell 回显的框定分隔符，不是认证令牌，不存在攻击者 |

---

<sub>🤖 增量复审 `5173488..75f4816`（7 文件，2 删 5 增）。4-round: R1a/R1b DeepSeek v4-flash 并行 → R2 Opus 独立评审（自跑 12 次 pty/串口实验）→ R3 Codex PK（真 Codex，非降级）→ R4 Opus 裁决 + 全量补扫（第 9 条出自这里）。工具实证：跑通作者的 `test-serial-run.py` 6/6；自写对抗测试（无 shell 只刷启动日志、非 root 用户、`--print-dev`/`--list`）；`py_compile` + `bash -n`；复验旧守卫被真实启动日志绕过的前提。</sub>
