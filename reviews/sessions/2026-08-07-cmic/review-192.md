## ❌ REQUEST_CHANGES —— 判据选对了，但「让它常驻」之后少了两样常驻界面必须有的东西

先说对的部分，因为这个改动的**前提和判据都是对的**：

- `DESKTOP_MIN_PX = 721`（`:162`）对 `chat.html:61` 的 `@media (max-width: 720px)` —— 严丝合缝互补，整数宽度上没有缝。
- 而且比 PR 正文说的还稳一点：`.hist-docked` 是 JS 在 `:184` 用 `classList.toggle('hist-docked', open && isDesktop())` 打的，**不是媒体查询**。所以「docked 还是 overlay」和 `closeIfOverlay` 用的是**同一个函数**，结构上不可能漂。
- `closeIfOverlay` 走 `setOpen` 而不是 `userToggle` 是对的 —— `setOpen`（`:181-196`）刻意不写 `PREF_KEY`，注释里还记着当初为什么（页面加载时的一次 `setOpen` 把「窗口一度偏窄」当成了用户的选择钉死）。移动端点历史自动收起因此不会污染偏好。核过了。
- 没有 TDZ：`closeIfOverlay` 是 `:212` 的 `const`，而初始化期间唯一真正执行的 `setOpen` 在 `:250`，`refresh()`（`:215`，函数声明）只从 `setOpen` 的 `:195` 进入 —— 都在 `:212` 之后。
- `railNew`（`:205`）不收起是对的，不是漏改：`rail.hidden = open`（`:187`），图标栏只在抽屉已经关着的时候才够得到。

---

### 🔴 1 [Med] `refresh()` 只在「打开」时跑，而桌面现在永远不关 —— 列表会一直高亮**上一个**会话

`grep -n "refresh()"` 全文只有两处：`:195`（`setOpen` 里的 `if (open) void refresh();`）和 `:215` 的定义本身。

而 `.hist-item.on` 是渲染时算的（`:219` `const cur = activeId();` → `:224` `c.id === cur ? ' on' : ''`）。

于是桌面上：点历史 B → `closeIfOverlay()` 空转 → `hooks.onOpen(B)` 改掉 `activeId()` → **但列表不会重渲**，`.on` 还挂在 A 上，本次会话余下时间都是错的。标题（服务端改名）、turn 数、排序同理，全部冻在最后一次打开抽屉那一刻。

改之前，`setOpen(false)` + 下次打开会重跑 `refresh()` —— 那是一次**意外的**重新同步，而这个 PR 恰好把它拿掉了。

⚠️ 一个常驻的导航栏高亮着错的那一行，正是这个 PR 论证要修的那件事的反面。

**修法一行**：`:229` 那个 handler 里 `await hooks.onOpen(...)` 之后补 `if (!panel.hidden) void refresh();`
（`onNew` 不受影响 —— `startNewConversation` → `newChat()` 最后是 `location.href`，整页导航。）

### 🔴 2 [Med] 跨断点 resize 之后留下的透明遮罩，会把「用户从没设过的偏好」再写一次

`isDesktop()` 只在 `setOpen` 和 `closeIfOverlay` 里采样，**全文没有任何 breakpoint 变化监听**。

所以：在 ≤720px 打开抽屉（`hist-docked` 关、`#hist-veil` 显示），然后转横屏或拉宽窗口到 ≥721px —— `hist-docked` 不会补上，遮罩也不会消失。而 `chat.html:54`：

```css
.hist-veil { position: fixed; inset: 0; background: #0000; z-index: 30; }
```

**全屏、完全透明（`#0000`）、z-index 30、没有 `pointer-events: none`。** 那条 `#00000026` 的可见底色只在 `@media (max-width:720px)` 里（`:63`）。也就是说在桌面宽度下它是一张**看不见的全屏点击拦截板**，盖在 `.thread-wrap` 和 `.dock` 上面（那两个都没有 z-index）。

用户接下来在对话区或输入框点的第一下被它吃掉 → `veil.onclick` → `userToggle(false)` → 抽屉关掉，**并且把 `cmic.histOpen='0'` 写进 localStorage**。

⚠️ 这正是 `:189-194` 那段注释记录、并且用 `PREF_RESET_KEY` 清理过的那个 bug —— 「用户从没设置过任何东西，偏好却被钉死」—— 从另一扇门走了回来。而它的症状就是反馈 #1：以后每次访问导航都是收起的。

改之前，下一次点历史会跑 `setOpen(false)`，顺手把遮罩清掉、把 `hist-docked` 重算 —— 又是一次**意外的**自愈，也被这个 PR 拿掉了。

**修法**：把 `setOpen` 里管布局的那半抽成 `syncChrome(open)`，在 `setOpen` 里调，同时挂到
`matchMedia(\`(min-width:${DESKTOP_MIN_PX}px)\`).addEventListener('change', …)` 上，条件是 `!panel.hidden`，**且不碰 `PREF_KEY`**。

---

### 两条 Low

- **`:224` 的 `.hist-item.on` 只是视觉的。** 列表在桌面上现在是常驻的了，读屏用户没有任何办法知道哪个会话是当前的 —— 加 `aria-current="true"`（和上面第 1 条一起改，同一个位置）。顺带：`chat.html:258` 的 `<aside id="hist-panel">` 是个没有名字的 complementary landmark，而它收起态的孪生兄弟 `#hist-rail` 是个正经带 `aria-label` 的 `<nav>`。另外现在点一条历史会把整个 thread 换掉、而焦点还留在侧栏，全文没有任何 `aria-live` / `role="status"` 会播报这件事。
- **这个行为改动没带 e2e。** 新的不变量一条测试就够（`23-nav-shell.spec.ts`）：桌面宽度点 `.hist-item` → `#hist-panel` 仍可见、`html.hist-docked` 仍为真、`localStorage['cmic.histOpen']` **没被写过**；390×844 下 → `#hist-panel` 隐藏且 `cmic.histOpen` 仍未被写。最后那条断言正好能抓住第 2 条那一类。

### 顺带一句：这套抽屉 e2e 可能本来就不是安全网

`16-conversation-history.spec.ts:87` 和 `:97` 都是先 `setViewportSize({width: 390})`、再 `page.locator('#hist-handle').click()` 去**打开**抽屉。但 `:186` 是 `handle.hidden = !open` —— **把手只在抽屉已经展开时才存在**，它的作用是「收起」；移动端默认收起，打开的入口是 `#rail-hist`。

我没有 node_modules、跑不了这套测试，所以**不下断言**。但结构上这两处看着就是点一个 hidden 元素来开抽屉。四个 spec（16/23/27/28）都钉了抽屉行为，在把它们当作这次改动的护栏之前，值得先确认它们现在是不是真的绿。

<sub>Rounds — R1a/R1b DeepSeek(v4-flash)：R1a 一条 [Low]「`isDesktop()` 在这个 diff 里没定义，请确认它在作用域内」—— 零信息，它在同一个文件上方 45 行（`:167`）；R1b 正确判定无安全面。R2 Opus：独立发现上面两条 Medium 和两条 Low，并独立复核了我那五条核验；它还确认了 `refresh()` 重渲不会叠加 handler（`list.innerHTML` 先销毁旧节点，`.onclick` 是属性赋值不是 `addEventListener`），以及 `mountDrawer` 只在 `chat.ts:2036` 调一次。R3 Codex / R4 未跑：两条 Medium 都由直接文件证据判定（`grep refresh()` 全文两处、`chat.html:54` 的 veil CSS），不是推理链。按实跑轮数标 **3-round**。</sub>
