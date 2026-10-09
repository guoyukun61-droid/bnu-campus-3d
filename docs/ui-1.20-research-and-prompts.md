# 1.20.0-ui.1：校园地图册设计与提示词

日期：2026-10-09。范围为 `/explore/`，不改三维几何、道路、正式资料、账号、模型凭据或原工作台。

## 参考与证据边界

| 来源 | 观察与采用 | 本轮访问边界 |
|---|---|---|
| [Colonia Zacamil](https://coloniazacamil.com/) | 用户提供的全景截图中，三维主体、深色胶囊导航、低密度热点和克制的浮层形成清楚主次；采用地图主导和工具收敛 | 官方网页文字可读取。浏览器三维页连续超时；不能声称已遍历其内部镜头与全部交互。已有入口截图不是内部验收 |
| [Apple Maps](https://www.apple.com/maps/) | 官方展示地点卡汇聚地址、营业、照片和动作；采用身份优先、主要事实其次、证据折叠和逐层展开 | 官方文字已读；最初浏览器DOM调用超时，后续成功截取首页首屏 `ui-1.20-ref-apple-hero.jpg`。未实测原生App和详细地点卡交互 |
| [Earth Studio Camera Target](https://earth.google.com/studio/docs/advanced-features/camera-target/) | 相机围绕明确目标组织，区分目标位置和相机位置；采用围绕建筑的连续镜头和人工接管 | 官方说明已读并截取 `ui-1.20-ref-earth-target.jpg`；未观看嵌入视频，不是引入其运行时或复制影像 |

不复制三个网站的品牌、付费字体、源代码、三维资产或纹理。设计结论是本项目的转译，并非对参考站全部实现的逆向判断。

## 可实施的界面提示词

设计一套北京师范大学海淀校园的互动地图册。地图是舞台，不是聊天面板的背景图。顶部以一条紧凑深墨色胶囊承担分类，右侧暖白纸页承担地点详情与对话，底部只有一个提问入口。普通模式先显示建筑身份，进入吃喝后才展开商铺和窗口。建筑名称使用克制宋体，功能文字使用本机黑体，金额使用等宽数字。只保留深墨、暖白、银杏金三个视觉角色。金色只点亮目标与关键操作；不要紫色霓虹、满屏玻璃、卡片套卡片或每段文字一个彩色标签。左下角以大留白、短句和一张原创银杏版画引导发现。镜头要让人知道正在看哪个建筑；手动拖动立即接管。手机不是缩小版桌面：地点页默认只占44dvh，对话62dvh，保留地图，看地图/继续对话不销毁输入与阅读位置。

## 实际图片生成提示词

模型：内置图片生成；未上传私有地图数据，未使用生成视频代替应用。

> Create one premium editorial UI ornament asset, transparent PNG, square 1024x1024. This is NOT a UI mockup, NOT a map, NOT text. Fine hand-engraved ginkgo leaf botanical linework, 3 airy fan-shaped leaves with elegant vein details, short curved stems, scattered very fine broken contour-like concentric arcs and a few tiny dots. Composition concentrated in the LOWER RIGHT corner and a narrow sweep along the bottom, upper-left 70 percent remains transparent empty space for interface text. Restrained monochrome antique brass ink #a28745 with some pale warm-grey lines. Sophisticated university campus atlas aesthetic, Japanese copperplate botanical print and archival cartographic marginalia, clean individual strokes, very fine but sharp, modest artful asymmetry. No opaque background, no paper rectangle, no gradients, no shadows, no lettering, no logos, no extra branches, no dense all-over pattern. Asset will be displayed on a warm ivory information sheet at 220 pixels; important leaf contours must remain readable. Original artwork, do not copy any website artwork.

交付 `app/explore/art/atlas-ornament-v1.png`，来源与SHA256见同目录manifest。PNG是静态装饰，不是测绘纹理；实际动效用CSS、WAAPI和Three.js完成。原始生成图保留，旧银杏PNG未删除。删除了CSS内不再使用的约1MB base64文本，装饰通过独立图片请求加载，界面不依赖图片成功才显示。

## 动效审查

| Before | After | Why |
|---|---|---|
| 地图焦点按固定面板宽度偏移 | 测量实际遮挡、寻找空矩形、目标包围球适配视距 | 右侧卡与手机底部卡都不遮住目标 |
| 打开卡片仅替换文字 | 260ms纸页面板进入；220ms内容切换 | 空间关系与层级变化可感知 |
| 原地跳到固定方位 | 保留当前方位、720ms可中断目标镜头 | 避免方向丢失与正上方翻转 |
| 一边读信息一边持续自转 | 指针、输入、键盘接管即停；明确按钮恢复 | 动画服务探索，不干扰阅读 |
| 后台仍按墙钟推进 | 后台暂停；减少动态与键盘禁用过渡 | 可访问性与稳定性优先 |

## 调整入口

- `explore.css`：单一token系统、两种屏幕布局、字体层级、纸张/墨色与触控尺寸。
- `index.html`：语义区域、唯一输入框、导览按钮；没有另造假演示页面。
- `main.js`：面板状态、输入框迁移、窗口分组、加载更多、导览与遮挡采样。
- `state.js`：纯搜索/分组/镜头数学，无DOM，便于实验。
- `scene.js`：OrbitControls、相机、真实模型定位与可中断漫游。
- `app_server.py`：只为新PNG增加精确公开路由；manifest和其他私有目录不开放。

技能影响：frontend-design用于明确地图主导的视觉方向；ui-animation用于可中断、后台暂停和减少动态；imagegen用于生成独立原创装饰素材，而不是伪造效果截图。
