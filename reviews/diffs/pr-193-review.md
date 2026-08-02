## [2-round] APPROVE — AAStarCommunity/AirAccount#193

**docs(oob): 串口救板工具 serial-run.py + mx93b-serial-poweroff.sh**

纯文档/工具类 PR，`kms/docs/out-of-band-console/` 下新增两个离线救板脚本，无生产运行时代码改动。

### 文件
- `kms/docs/out-of-band-console/serial-run.py` (153 行) — 通用串口命令执行器，自动设备发现、自动登录、ANSI 剥除、退出码透传
- `kms/docs/out-of-band-console/mx93b-serial-poweroff.sh` (29 行) — 板 B 优雅关机，先验证 root shell + imx93 hostname 再 `systemctl poweroff`

### 审查要点

**✅ 通过项：**
- 两个脚本结构清晰，注释完整，安全边界明确
- `mx93b-serial-poweroff.sh` 有双重安全检查：确认 root shell + 确认 hostname 含 `imx93`（防对错设备操作）
- `serial-run.py` 有设备自动发现 fallback 和多设备冲突提示
- PR 自述已确认 `py_compile` / `bash -n` 语法检查通过，且板 B 实跑关机验证成功
- 无运行时依赖变更，不影响任何生产代码路径

**R1 (DeepSeek) 发现项的裁决：**

| 发现 | 严重度 | 裁决 | 理由 |
|------|--------|------|------|
| `drain(0.6)` 循环可能使 `--read-secs` 实际超时 | Medium | **非阻塞** | 关机场景精度非关键，最多超几百 ms；可后续优化但不必阻塞合并 |
| login prompt 初期 drain 可能太短 | Low | **非阻塞** | 物理串口响应稳定，实际已验证通过 |
| 先发密码再检查登录是否成功 | Low | **非阻塞** | 串口场景——物理插线 = 已有完全控制权 |
| R1b: 空密码自动登录 root（security） | Medium | **False positive** | 调试串口 = 物理接触，非网络暴露面 |
| R1b: 串口未认证 root 登录（security） | Medium | **False positive** | 同上 |
| R1b: hostname grep 无加密验证（security） | Low | **False positive** | OOB 救板工具不需要 PKI；hostname 匹配已足够防误操作 |

### 建议（非阻塞）

- `serial-run.py` 的 `drain()` 在 `--read-secs` 模式下可加 `min(0.6, remaining)` 约束，使实际读取时长更接近参数值
- 可考虑给 `serial-run.py` 加一个 `--no-login` flag 给不需要登录的 bare-metal console 场景

### 结论

这是高质量的运维工具沉淀——从一次性排障脚本清理为参数化、文档齐全的可复用工具。无生产风险，**APPROVE**。
