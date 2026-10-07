# 农林小林对照与临时试用准备

日期2026-10-06。纠正参考对象：20czy/zafu_xiaolin_campus_agent，不是DeerFlow。页面署名不是采用架构的证据，以源码为准。

## 已核对的对方材料

- [项目README](https://github.com/20czy/zafu_xiaolin_campus_agent)：区分已列出的课表、通知、场馆mock能力与校园治理远景，不把教务/一卡通/OA等全部算作实际接通。
- [TaskPlanner.py](https://github.com/20czy/zafu_xiaolin_campus_agent/blob/master/fastapi/app/agent/TaskPlanner.py)：任务计划与depends_on。
- [ToolSelector.py](https://github.com/20czy/zafu_xiaolin_campus_agent/blob/master/fastapi/app/agent/ToolSelector.py)：技能发现和工具选择。
- [TaskExecutor.py](https://github.com/20czy/zafu_xiaolin_campus_agent/blob/master/fastapi/app/agent/TaskExecutor.py)：本地handler优先、任务结果引用。
- [ResponseGenerator.py](https://github.com/20czy/zafu_xiaolin_campus_agent/blob/master/fastapi/app/agent/ResponseGenerator.py)：汇总过程信息、画像与聊天历史。
- [registry.py](https://github.com/20czy/zafu_xiaolin_campus_agent/blob/master/fastapi/app/skills/registry.py)：技能元数据、别名、handler绑定与诊断。

这是当前主分支的静态审阅，没有部署或评测对方项目，因此不作性能、安全性或生产成熟度保证。

## 我们欠缺什么

| 方向 | 我们当前 | 建议借鉴/改造 |
|---|---|---|
| 任务规划 | 有限工具循环，没有显式依赖计划 | 简单查询直接工具；跨课表/吃饭/地点任务才拆计划 |
| 能力注册 | tools.py四个固定定义 | 每个能力独立描述、schema、handler、测试与真实/模拟标签；先不引入任意代码执行 |
| 上下文 | 条件与最近消息，无地图选择上下文 | selected_building_id/poi_id、明确起点、模拟课表；用户画像最小化，不能整份私人资料注入 |
| 场景范围 | 店铺/菜单/推荐/模拟课表 | 按真实需求加校园通知、建筑介绍、图书馆查询；预约先保持模拟并需确认 |
| 过程展示 | 状态文字与结果卡片 | 显示做了哪些查询、哪些条件通过、哪里失败、哪些事实待核；不展示内部思维链 |
| 结果表达 | 工具事实＋固定句式 | 模型解释只能引用已查到的事实ID，价格/楼层仍用结构化卡片 |
| 测试反馈 | 离线测试，缺真实模型固定题集 | 固定30–50题、多轮修改、工具正确率、预算违规、未知值表达、耗时与成本 |

我们已有的空间资料、三维交互、真实菜单证据与审核链应保留。不建议复制其整个FastAPI/Next.js/数据库栈；也不能宣称我们或对方算法显著更优。

## 本轮已实现的临时入口边界

- app_server.py默认8793仍为本机入口；显式--preview-origin启用独立8794预览。
- 仅精确HTTPS trycloudflare域名的Host/Origin可用；原静态资源白名单保留，无私有文件、审核或提交接口。
- PreviewModel不读取密钥；外网chat返回明确未启用提示，cancel拒绝。只读目录、菜单与条件筛选可用。
- POST整个测试实例每分钟最多30次；两小时后返回410。它是小规模试用保护，不是生产抗攻击或身份认证体系。持链接者可查看公开目录与可下载模型，不适合保密数据。
- 不公开8792管理端口；不安装系统服务、不改环境变量、密钥或数据库。
- 复用便携cloudflared。当前服务并未运行，端口检查8790/8792/8793/8794均无监听。

## 当前结果与启动步骤

8项新增HTTP边界测试通过；tests共141项通过。已成功生成过临时域名，但启动后端的Start-Process被执行环境策略拒绝。因此**没有可用公网入口，也没有公网页面/模型加载验收**。本轮创建的空隧道PID15364已关闭，没有动其他服务；失效地址不作为交付链接。

用户在本机PowerShell手动运行（代理未执行此脚本绕过拦截）：

```powershell
& 'D:\A-newdesktop\个人\本基\bnu_campus_blender_20260831\start_preview.ps1'
```

脚本创建新隧道、读取本次域名、启动独立预览、验证公网页面与状态，再输出链接及PID。若端口已有程序则停止并报错，不杀旧进程。失败只清理本次子进程。保持电脑唤醒；两小时后需重新开启，不能保证Cloudflare可用性。

脚本经过语法解析检查但未实际执行；用户运行成功后仍须核验公网GLB、目录、条件POST、错误提示、私有路径拒绝以及手机移动网络。

若PowerShell执行策略不允许，不自动修改系统配置。将错误反馈后再决定执行方式。

## 正式AI外测前的必要事项

需要用户确定访问保护方式和模型调用额度，再通过安全输入提供有效模型配置。不把“隧道通了”当成“智能体接通”；也不把模拟问答冒充真实模型。Quick Tunnel官方声明无可用性保证、不支持SSE；现有NDJSON需独立验证，不能凭不是SSE就保证逐块到达。

[Cloudflare官方说明](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)

## 本次纠错

1. 含糊引用先确认具体仓库；不再自行将“那个校园项目”替换为其他通用Agent项目。
2. 展示功能、源码实现、mock数据和Roadmap分别记录。
3. 公网地址生成与实际服务可用分开验收；启动被拦截即说明，不换壳绕过。
