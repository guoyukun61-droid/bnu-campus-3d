# 流动对话窗口 · 1.20.0-ui.2

日期：2026-10-09。范围：用户确认的 Dynamic Island 状态连续性 + Family 触发点展开 + 克制玻璃边缘，不重做整个地图。

## 交互与实现

地图输入 → 紧凑查询岛 → 回答摘要 → 用户展开完整对话 → 看地图/关闭回到输入。

- 阅读中的完整对话收到追问时保持展开；查询结束不抢正在浏览的地点卡，也不自动重开窗口。
- 摘要取自同一响应消息，最多150个Unicode字符加省略号、视觉最多3行。不是额外模型生成的结论；未知项、依据、卡片与重试在完整回答中保留。
- `index.html` 新增 `chat-island` 摘要和 `dialog-shell` 装饰壳。无新路由、依赖。
- `main.js` 的 `renderIsland` 渲染状态，`setChatPeek` 管理阅读/紧凑态，`morphChat` 处理过渡。不改变消息存储和请求协议。
- 装饰壳使用旧/新矩形做FLIP；正文仅位移/淡入，不缩放。关闭时动画内层form，避免覆盖外层居中的translateX；反向时从当前外壳位置接续并取消旧动画。
- CSS沿用暖白/墨绿/银杏金。`--dialog-radius` 控制壳圆角；内高光而非大面积玻璃折射，没有复制第三方设计资产。
- 参考方向：https://emilkowal.ski/ui/dynamic-island 、https://motion.dev/examples/js-family-dialog 、https://developer.apple.com/videos/play/wwdc2025/219/ 。依据此前已讨论方向实现，非其源码复刻或系统级Liquid Glass实现。

## 自动验收

```powershell
node --test tests/*.test.mjs tests/test_explore_interaction.cjs
node --check app/explore/main.js
node --check information/app.js
node verify_web_syntax.cjs
python -m unittest test_campus_api.py test_poi_import.py tests.test_explore
```

结果：52项Node runner条目通过，其中交互文件内部38个行为场景；15项Python测试通过。两者不能相加成90项Node测试。全量后端412项未本轮重跑，后端未改。

新增：地图提问紧凑/阅读中不收起、完成不抢焦点、150字摘要、错误恢复、正文不缩放、快速反向取消、后台清理、减少动态直达、菜单恢复inert、身份重置清摘要。原有DOM稳定、滚动、账号边界与工具上下文保护保留。

## 浏览器验收与迭代

使用 `python -m tests.run_agent_preview` 环回隔离服务；模型 `isolated-ui-fixture-not-real-ai`。截图中地点来自现有只读目录，但回答流程是测试替身，不代表DeepSeek成功。

1. 桌面1280×720：发送、查询状态、完成摘要、展开答案；输入不随正文滚动。检查后取消聊天面重复的CSS入场，只保留WAAPI过渡。
2. 手机390×844：发送、展开、填写未发送追问、快速收放，草稿保留。发现欢迎区伪元素6px溢出；修正后scrollWidth=390。
3. 实际滚动522px，收起再展开仍522px；输入下缘819px、视口844px。恢复桌面视口，浏览器错误日志为空。

真实浏览器截图：`ui-1.20-fluid-desktop-compact.jpg`、`ui-1.20-fluid-mobile-compact.jpg`、`ui-1.20-fluid-mobile-full.jpg`。

待验：实机键盘/安全区、真实AI、公网、账号切换全链路。动画配置/取消已验，但未做低端机帧率基准，不能声称所有设备60fps。未开隧道，未改凭据，未push。

## 修改意见总结

“流动感”不是仅加大圆角，也不是让正文不停漂浮。入口、查询、摘要与阅读应形成连续状态；交接时运动，阅读时稳定。不要为局部交互重做用户认可的地图、字体与配色。
