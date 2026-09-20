# 现有 UI 约束

来源：`web/src/styles.css`、`archive.css`、`ui.jsx` 和现有页面。**未经明确需求不得改变全局视觉语言。** 本文件固化现状，不提出重新设计。

## 基础风格与 tokens

当前是柔和纸白底、深绿导航和克制的学术排版；没有 Tailwind、CSS-in-JS、组件库主题或专门 tokens 文件。CSS `:root` 是全局 token 主源，禁止复制第二份色板或为本次需求统一替换所有硬编码值。

| token/用途 | 当前值 |
| --- | --- |
| --ink / 正文 | #253c36 |
| --muted / 次要文案 | #78857e |
| --green / 主操作 | #346952 |
| --line / 边线 | #e4e8e1 |
| --paper / 纸面 | #fff |
| --soft / 柔和底 | #eff3eb |
| 页面背景 | #f7f8f4 |
| 侧栏背景/文字 | #203d33 / #dce5dc |
| focus-visible | 2px solid #80a78b，offset 3px |

状态沿用 `.neutral`（#eff2eb/#88907f）、`.success`（#e8f3e7/#4c7f4c）、`.warning`（#f8efdc/#957c39）、`.danger-text`（#aa6254）；不擅自把待确认警告换成成功状态。

## Typography / spacing / radius

- 正文字体栈：Inter、-apple-system、BlinkMacSystemFont、Segoe UI、PingFang SC、Microsoft YaHei、sans-serif；不从 CDN 新增字体。`--serif`：Songti SC、STSong、Georgia、serif，用于品牌/标题强调；公式由 KaTeX 渲染。
- 基础 h1：32px / 550 / line-height 1.45 / letter-spacing -1px；h2：17px/600；h3：15px/600。页面会局部覆盖；复用目标页面当前选择器，不能把档案 46px 标题扩散到全站。
- 常见正文辅助字号 11–12px；eyebrow 10px/600、letter-spacing 1.8px。控件继承字体。
- 当前没有严格 spacing scale。常见 gap 7/8/12/14/16/24px；`.paper` padding 25px、档案 36px（移动 24px）；新增元素就近复用，不为凑统一网格改存量尺寸。
- 圆角：input 8px，主/次按钮 7px，icon button 6px，paper 12px，recent-card 10px，pill 4px；档案卡 18px、藏章 14px；胶囊选择器 999px。

## 组件与交互复用

| 需求 | 复用方式 |
| --- | --- |
| 主/次按钮 | 原生 button + `.primary` / `.secondary`；inline-flex，gap 8px，padding 11px 16px，12px/500；紧凑版 `.compact` |
| 图标操作 | `.icon-button`，32×32；Lucide，与邻近 strokeWidth 一致；必须有 aria-label |
| 文字操作 | `.text-link` / `.text-button` |
| 卡片 | `.paper`，1px line 边框、白底、12px 圆角；按页面组合已有类 |
| 输入 | 原生 input/textarea/select；100% 宽，白底，#dce3d9 边框，8px radius，10px 12px padding |
| 表单标签 | label 纵向 flex、gap 7px、12px；复选框 16px，green accent |
| Markdown/公式 | `ui.jsx:Markdown`，不另起解析器、不注入任意 HTML |
| 弹窗 | `ui.jsx:Modal`，dialog/aria-modal、Escape、焦点循环和返回焦点；不能删这些交互 |
| 空态、等待、参考 | `Empty`、`Loading`、`Sources`；已关联知识才可跳转 |
| 选择题 | `Study.jsx:AnswerChoices`，aria-pressed，多选用 domain.toggleAnswer；只读照片作答用 readOnly |
| 藏章/分享 | `Archive.jsx` + `archive.js`，复用已有 SVG 与安全转义；不引入任意用户 HTML/CSS |

禁用状态沿用 opacity .45 和 not-allowed；不能仅视觉禁用而仍发送请求。保持 loading、错误提示、pending、不完整题警告和解析默认折叠语义。

## Layout / responsive

`.app-shell` flex；固定侧栏 232px，桌面 topbar 高 69px、sticky、padding 0 38px。学习区已有题目面板、图片、底部讨论和拖动高度行为；不要新增全局滚动层或重新排列工作区。

全局响应断点：min-width 1600、max-width 1200/960/720；档案 max-width 760。沿用这些断点及现有 mobile navigation。修改布局须检查至少 1440×1000 与 390×844，验证菜单、长题干、多选、公式、弹窗和可见按钮；不只检查空态。保留 reduced-motion 规则。

## 档案主题局部范围

| 变量 | paper | blueprint |
| --- | --- | --- |
| --archive-bg | #f3ead7 | #102b48 |
| --archive-ink | #3f3429 | #eefbff |
| --archive-line | #a67559 | #62c7dc |
| --archive-panel | #fbf5e9 | #173b5f |

主题只作用于 `.archive-root[data-theme]` 和分享 SVG，不能改写 :root、学习台或状态资格条件。分享统计默认关闭。

## UI 回归策略

现有 Vitest SSR 测试锁定解析默认隐藏、题目线程隔离、禁用状态等语义，但不验证浏览器布局。新增 Playwright 使用真实构建、隔离 API/SQLite，检查桌面/移动复习提交与持久化、知识入口、档案可见性、横向溢出和浏览器错误；输出复习/档案截图及失败 trace。

**目前截图是审阅证据，没有自动像素 diff，也没有声称完整视觉回归覆盖。** 少量截图对本项目值得保留；由于 macOS/Linux 的中文系统字体、字形和渲染不同，本次不把未经人工审核的单机截图设为跨平台 golden。需要全局 CSS/布局变更时，在固定 Linux + Chromium + 字体环境下审阅基准，再引入 2–4 个 `toHaveScreenshot` 案例（学习台、复习、档案纸本/蓝图）；更新 golden 必须展示 diff，不得自动全量接受。当前的规则、截图人工 review 和 UI 语义测试共同约束无意改界面，不能保证捕捉每个视觉变化。
