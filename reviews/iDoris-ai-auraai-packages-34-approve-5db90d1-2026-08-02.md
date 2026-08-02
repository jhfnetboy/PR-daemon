## APPROVE — `actions/setup-node` v6 → v7

纯 CI action 版本号 bump，diff 只有 3 处同一行改动（`ci.yml` ×2、`release.yml` ×1），无其他内容。

**实际验证过的（不是只读 diff）：**

| 检查 | 结果 |
|---|---|
| `yaml.safe_load` 解析 PR head 上的两个 workflow | ✅ `ci.yml` → jobs `typecheck-test` / `publish-hygiene` / `changeset-check`；`release.yml` → job `release` |
| action runtime 是否变化（最常见的 major bump 破坏点） | ✅ v6.0.0 与 v7.0.0 **都是 `using: node24`**，runner 要求没变 |
| `runs-on` | 全部 `ubuntu-latest`，非自建 runner，不受 runner 版本影响 |
| v7.0.0 release notes | 无 breaking change 条目：新增 `cache-primary-key`/`cache-matched-key` 输出、迁移 ESM、`@actions/cache` 升到 5.1.0 |
| 现有用法兼容性 | `node-version: '22'` + `cache: 'pnpm'` + `registry-url` 均为 v7 保留参数 |

无阻塞问题，可以合。

---

### 📌 一个顺带发现（**与本 PR 无关，先不影响 approve**）

v7 的 changelog 里有一条 [Remove dummy NODE_AUTH_TOKEN export](https://github.com/actions/setup-node/pull/1558)。`release.yml` 里 setup-node 带了 `registry-url: 'https://registry.npmjs.org'`（会写出引用 `${NODE_AUTH_TOKEN}` 的 `.npmrc`），但 changesets 那步的 env 只给了 **`NPM_TOKEN`**，没有 `NODE_AUTH_TOKEN`：

```yaml
env:
  GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
  NPM_TOKEN: ${{ secrets.NPM_TOKEN }}     # ← .npmrc 引用的是 NODE_AUTH_TOKEN
```

我查了 release workflow 最近 5 次运行**全部 failure**，但失败原因是 `HttpError: Validation Failed: No commits between main and changeset-release/main`——卡在建 versioning PR 这一步，**`changeset publish` 从来没真正跑到过**。所以 v6 时代那个 dummy token 到底救没救过场，无从验证，我不能断言这里现在是坏的。

只是提醒：等哪天真要发包，先确认 npm 认证是走 `NODE_AUTH_TOKEN`（那就要改 env 名）还是走 `id-token: write` 的 OIDC Trusted Publisher（那 `registry-url` 那套 token 逻辑本来就不需要）。v7 拿掉 dummy 之后，如果之前是靠它蒙混，会直接暴露出来。

---

<sub>🤖 2-round: DeepSeek v4-flash R1（TRIAGE trivial，0 findings）→ 裁决。纯 action bump 按既定规则不跑 PK。工具实证：`yaml.safe_load` 解析两个 workflow + 对比 v6/v7 `action.yml` 的 `runs.using` + 拉取 v7.0.0 release notes + 查 release workflow 历史运行日志。</sub>
