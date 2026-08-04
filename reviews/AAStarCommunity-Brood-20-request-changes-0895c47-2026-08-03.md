## REQUEST_CHANGES — AuraAI → iDoris.ai 品牌重命名只做了 5/6 处

纯文档 PR：把 5 份 research markdown 里的 `AuraAI` 品牌引用统一改成 `iDoris.ai`。逐条核对了全部替换，**5 个改动文件内部无残留、无拼写错误、无行为变更**（全是文本替换，不碰代码/配置/CI）。但整个重命名的范围覆盖不完整——**同一份 pitch 交付物里还有一处旧品牌没改**。

### Blocking

- **[Low] research/hyphae/pitch_deck/slides.html:301** — 投资人 pitch deck 第 9 页「① 我们已经启动建设」列表第一项仍是 `<li><b>AuraAI 在建</b>：Agent24（桌面 Agent 框架）</li>`。
  - **问题**：这句话和 `PITCH_8MIN.md` 里被本次 PR 改成 `iDoris.ai 在建：Agent24` 的**同一句话**（口述稿 → 演示稿一一对应）。两个并行交付物现在品牌互相矛盾：口述稿说 `iDoris.ai 在建`，slides 演示稿说 `AuraAI 在建`。
  - **触发场景**：任何投递给投资人的场合，deck 展示的是过时的 `AuraAI` 品牌——正是本次 PR 要消除的不一致。
  - **建议修复**：`slides.html:301` 改为 `<li><b>iDoris.ai 在建</b>：Agent24（桌面 Agent 框架）</li>`（与 `PITCH_8MIN.md` 的改动对齐）。

### 已核实（无需改动）

- 5 个文件内部 `AuraAI` 引用**零残留**（grep 确认），全部正确替换为 `iDoris.ai`，无 `Aura` 单字残留、无拼写错误。
- `research/hyphae/` + `hyphae-agents/` + `loyalty-network/` 全树范围 grep 后，唯一漏网的就是上面 `slides.html:301` 一处。
- `README.md` 第 2 节标题 `与 iDoris / iDoris.ai 的关系` 语义正确：`iDoris` = 产品（个人 AI），`iDoris.ai` = org（体系），与下方示意图一致，非冗余。

### Rounds

- **R1a (DeepSeek-full)**：1 finding [Low] README 标题「iDoris / iDoris.ai 冗余」——核验后**驳回**（产品 vs org 区分是真实语义，非冗余）。
- **R1b (DeepSeek-security)**：无安全面（纯文档）。
- **2-round**（纯文档文本替换，无 src/contracts/lib/CI 触碰，triaged 2-round）。

### Issue 说明

PR body 提到「从 #13 摘出」，但当前 #13 的内容是 ETHGlobal faucet 领水机器人（与 hyphae research 无关），无 DoD 可映射。建议顺手修正 PR body 的 issue 引用以免误导。
