# 北师大校园 GF-2 / Sentinel-2 Blender 三维原型

## 1.12.1 临时外网试用准备（2026-10-06）

已新增独立只读预览模式与`start_preview.ps1`手动启动器，地图/菜单/条件筛选可供测试，明确禁用付费模型调用，精确域名核验、POST限流、两小时过期。**当前未开通**：本轮后端启动被执行环境策略拦截，空隧道已关闭，无有效公网链接。用户手动运行脚本后再做公网验收。

[农林小林架构对照、启动与限制](docs/xiaolin-comparison-preview-20261006.md)。未部署到生产、未公开审核入口、未改密钥。

## 产品 v1.12.0：三轮截图驱动UI迭代（2026-10-04）

[打开本机探索页](http://127.0.0.1:8793/explore/)。浮动短卡片、建筑内分类直达、完整商户条目、灰绿与暖白地图、统一字号与移动端折叠筛选已完成三轮截图复查。保留银杏花纹和真实Three.js交互，无需Cloudflare。

银杏已打包到现有CSS，纸纹复用已可加载资源，本版本不再需要重启来展示装饰。未更改模型密钥；当前助手未启用，地点浏览和无模型条件筛选仍可用。条件推荐的正餐分类存在独立待修问题，见验收记录。

[三轮记录与验收](docs/explore-1.12.0-acceptance.md) · [视觉QA](design-qa.md)。以下保留历史版本状态，不代表当前版本仍受相同阻塞。

## 产品 v1.11.0：水彩导览UI试用（2026-10-04）

[本机探索页](http://127.0.0.1:8793/explore/)已可预览新布局。沿用真实三维模型和数据，顶栏提问、左侧分类、建筑资料分节；建筑与商户分层浏览。

**尚未完整验收**：新银杏/纸纹素材已生成并通过隔离HTTP测试，但运行中的旧服务尚未重启，资源路由仍返回404。需在原终端停止8793服务，再在本项目运行`python app_server.py --port 8793`，刷新后做最终视觉检查。自动重启被执行环境拦截，未改端口或绕过限制；无公网部署、无密钥改动。当前模型未配置。

[实施、纠错与验收](docs/explore-1.11.0-acceptance.md) · [视觉QA](design-qa.md)。以下为历史版本记录。


## 产品 v1.10.0：校园导览手册UI精修（2026-10-03）

当前入口：[打开新版校园生活地图](http://127.0.0.1:8793/explore/)。沿用本机8793，无需Cloudflare；已运行时刷新即可。纸白与深绿、宋体标题、统一线性图标，桌面侧边分类栏与手机底部信息面板。场景、名录和业务接口保持原样。

本轮完成桌面、平板及手机尺寸检查、列表与详情切换、完整308条分页验收。模型未配置，地图、名录和结构化筛选可用；UI升级不等于缺失坐标已补齐。[验收与纠错](docs/explore-1.10.0-acceptance.md)。以下保留历史版本记录。

## 产品 v1.9.0：完整店铺名录与生活导览（2026-10-03）

当前入口：[打开校园生活地图](http://127.0.0.1:8793/explore/)。原8793已核对后重启；独立访问 `/map/` 会进入探索页面，经典对话版内嵌地图保留。未启动时在项目目录执行 `python app_server.py --port 8793`。仅本机，无公网隧道；当前模型未配置，资料查询与地图不依赖模型。

选择“吃喝”查看餐饮和饮品；点击“小吃街主排 · 13家”或“西北食堂西侧 · 6家”查看完整区域名录。没有坐标的店铺仍能打开详情，不能据此理解为精确定位已补齐。全部目录可按40条继续加载；同楼数量标记可展开店铺。手机面板支持展开、缩小和收起。

[实施验收与位置缺口](docs/explore-1.9.0-acceptance.md)。本轮不改白模、业务名录、营业时间或密钥；保留以下旧版本记录，不以历史端口说明作为当前推荐入口。

## 产品 v1.8.0：建筑优先校园导览（2026-10-03）

本轮入口：[1.8本地预览](http://127.0.0.1:8795/explore/)。默认基础上色与慢速漫游；点击建筑显示楼名，选择美食/饮品查看店铺。拖动、输入等操作停止漫游，底部按钮可继续。主楼后部拓扑已修复，道路保留深灰。

未运行时在项目目录执行 `python app_server.py --port 8795` 后打开 `/explore/`。只绑定本机，不需要Cloudflare。旧8793/8794进程不会自动更新Python路由；请使用本轮链接。此预览未配置大模型密钥，但本地目录、条件推荐和地图可用。

[本轮验收与限制](docs/explore-1.8.0-acceptance.md) · [水彩风格样稿](docs/design-1.8-watercolor-concept.png)。应用服务器现使用white_v7；旧工作台与填报服务未统一切换，其white_v6保留。以下为历史说明。

## 产品 v1.7.0：校园探索预览（2026-10-02）

当前本地预览：[地图与生活助手](http://127.0.0.1:8794/explore/)。默认白模，底部“示意上色”开启美术样例；顶部分类、助手输入与侧栏资料联动。原8793服务保留，未开启公网访问。新进程未配置模型，可使用地点、菜单与条件推荐，不能据此宣称大模型已连通。

如8794没有运行，在项目目录使用已有Python运行 `python app_server.py --port 8794`，再打开 `/explore/`。模型仍通过既有进程环境接口接入，不向前端或文件写密钥。端口已占用时不要重复启动或盲目停止其他进程。

[实施与验收](docs/explore-1.7.0-acceptance.md) · [美术、动画与生成提示](docs/explore-1.7.0-art-direction.md)。以下旧版本说明按当时状态保留。

## 产品 v1.5.0：本地生活助手（2026-10-01）

新用户入口：[京师智行](http://127.0.0.1:8793/)，暖白生活界面、对话、真实菜单、结构化条件筛选和三维白模联动。`./start_local_app.ps1` 隐藏输入进程级密钥；`./start_local_app.ps1 -WithoutModel` 仅使用本地业务功能。它不会启动Cloudflare或改变旧数据库。

架构、可调整模块、接口、验收和模型连接状态见[1.5.0开发说明](docs/agent-app-1.5.0.md)。本轮DeepSeek官方接口实测返回401，待确认有效密钥或用户授权的正确供应商地址。以下版本记录是历史说明，不代表当前运行状态。

## 产品 v1.2.0：协作采集（2026-09-23，本地验收）

2026-09-24 团队选择免凭证临时协作：队员从 g/kdy/lyx/ljz/ll 选择署名；公开入口只能提交候选，管理员审核入口限本机独立端口。详见最新版管理员文档与版本记录。

独立填报服务：`python contribution_server.py --port 8790`，打开 http://127.0.0.1:8790/ 。队友候选提交经过管理员审核后，正式生活接口才读取；原SQLite不迁移。图片上传复用已安装Pillow。真实账号与外网隧道尚未启用，须另行批准。

[队员填写教程](docs/团队采集填写教程_1.2.0.md) · [管理员与接口](docs/协作采集管理员与接口_1.2.0.md) · [研究对照](docs/可信推荐研究对照_1.2.0.md) · [实施与验收边界](docs/协作采集实施与纠错_2026-09-23.md)。新增语法检查：`node --check contribute/app.js`。

当前数据采集口径以9月22日报告为准：百度184/184个叶任务完成，合并275条地点、263个Shop对象、200条模拟商品；不等同现实全部营业商户。下方v1.1.0的“缺密钥、未采集”是当时历史状态，不代表当前进展。本轮没有补造真实菜单或完成现场试填。

## 产品 v1.1.0：校园生活推荐（2026-09-21）

本轮新增数据名录、百度分页续采、200条模拟菜品、Top 3规则推荐、课表和图书馆模拟预约。启动 `python campus_server.py --port 8787`，打开 http://127.0.0.1:8787/white/ 。默认端口仍是8786；本轮保留旧服务，在8787预览新版。

初始化：`python -m backend.bootstrap`；百度采集：`python -m backend.collector`（运行进程须已具备BAIDU_MAP_AK）；离线准备：`python -m backend.collector --prepare-only`；导出：`python -m backend.export`。不修改原数据库schema，不需要LLM或美团密钥即可演示。首次启动会生成带来源的初始目录及模拟样例，不包含本机私有百度审计。

当前24条初始餐饮名录不代表校园全店；合并接口还包含校门、建筑和历史记录。百度在线增量采集因缺少运行时密钥未执行，172个任务待续跑。请勿将模拟窗口、商品、价格、排队或图书馆预约当作真实服务。

契约与运行说明见 [生活API](docs/life-api.md)，完成情况、测试和缺口见 [阶段交付](docs/life-delivery-2026-09-21.md)。新增测试：`python -m unittest discover -s tests -v`；前端：`node --check white/life.js`。以下1.0.0及白模v4章节保留为历史和模型资料。

## 产品 v1.0.0（2026-09-21）

当前交付白模使用 **white_v6**，产品版本统一见 [VERSION](VERSION)，修改记录见 [CHANGELOG.md](CHANGELOG.md)。v6局部修正学五/学子超市片区高度并近似补建新乐群北侧低楼，沿用v4坐标框架；主体身份和米制高度仍有待核项。逐栋记录与同步状态见 [小吃街审核](docs/snack-audit-2026-09-24.md)，此前场地和南苑核对见 [地图审计](docs/map-audit-2026-09-24.md)。下方旧版本章节保留为历史记录。

下载并解压后，在项目目录执行 `python campus_server.py --port 8786`，打开 `http://127.0.0.1:8786/white/index.html`；信息编辑页为 `/information/index.html`。不要直接双击 HTML：本地文件协议不能正常提供模型和 POI API。Blender 用户可直接打开 `output/bnu_campus_white_v6.blend`。生活API与地图校验还依赖项目既有Python环境，不应把完整业务服务描述成仅需标准库。

发布包不含本机私有数据库，首次运行将建立空数据库；业务 POI 需自行录入，不等于本机记录已同步到 GitHub。静态校门和模型属性保留。三维显示依赖 WebGL，建议桌面浏览器。

验证：`node verify_web_syntax.cjs`、`node --check information/app.js`、`python -m unittest test_campus_api.py`。`test_poi_import.py` 属于本地私有百度审计数据的集成测试，需要原始审计 JSON、pyproj、eviltransform，净发布包不能独立运行该测试。历史重建脚本另需原始影像、GIS 依赖和 Blender，并非解压即可重新生成全部模型。

本地打包：`python package_release.py`，输出 `releases/` 中版本 ZIP 与 SHA-256 清单。不覆盖已有包。尚未确认地图、影像衍生材料的公开再分发权限，不建议直接公开仓库；不得提交 `data/`、AK 或 `.env`。模型含 OSM 衍生数据（© OpenStreetMap contributors，https://www.openstreetmap.org/copyright）；第三方依赖遵循其原有许可，本项目未赋予第三方素材新的许可。

这是一个可继续编辑的校园尺度三维可视化原型，目标是把本地遥感数据转成 Blender 中可观察的三维校园，而不是宣称已经得到测绘级实景三维。

## 已生成成果

### 白模版本（2026-09-18，独立表现版）

入口 `http://127.0.0.1:8765/white/index.html`，或双击 `打开白模版本.cmd`。沿用 v6 几何，移除全部影像贴图，使用中性灰白材质与白光，保留旋转、漫游和视角预设。独立文件 `output/bnu_campus_white.blend`、`output/bnu_campus_web_white.glb`；原彩色版保留。运行 Blender `-b --python build_white_model.py` 可复现，验证记录在 `output/scene_manifest_white.json`。白模只改变显示，不校正推断楼高或窗位。

### 单张校园示意图参照试作 v6（2026-09-07，独立试验版）

- 入口：`http://127.0.0.1:8765/reference/index.html`，或 `打开图示参照试作.cmd`；根页面默认仍为 v5。
- 47 栋按用户新图分组设置外观与体量，184 栋沿用 v5。新增主楼开放门廊、体育馆屋盖、两处裙房上塔体、横窗带、竖向立面肋、部分坡屋顶与运动场标线。
- 这是人工图示解读与参数化建模，不是摄影测量。对应关系、楼高、未见背面及细节为假设；没有实景还原率。
- 图示颜色与 2025 年高分影像可能属于不同年代，v6 的 47 栋屋顶采用图示概括色，v5 继续保留观测贴图；原始数据和 v5 模型不覆盖。
- 成果：`output/bnu_campus_gf2_sentinel2_v6.blend`、`output/bnu_campus_web_v6.glb`、`assets/campus_assets_v6.json`。原图完整保存在 `assets/reference_campus_diagram_20260907.png`。
- 复现：Blender 执行 `build_reference_v6.py`；打开生成的 v6 blend 后执行 `export_web_scene.py` 和 `verify_reference_v6.py`。网页脚本检查：`node verify_web_syntax.cjs`。
- 结构验证：`output/validation_reference_v6.json`。反馈复盘：`图示参照复盘_2026-09-07.md`。

### 高分影像重识别 v5（2026-09-05，当前版本）

- 三维入口：`http://127.0.0.1:8765/index.html?qa=1&view=roofs&v=20260905v5`。
- 原始影像与逐栋核查：`http://127.0.0.1:8765/recognition/index.html`。
- 从原始 GF2 四波段重新读取，真正重投影到 EPSG:32650 的约 0.8 m 网格；没有 AI 超分或补绘卫星细节。
- 231 个既有 OSM 轮廓内分析屋顶色谱、阴影和植被混入。25 栋红屋顶采用相对匹配后的贴图采样，建筑坐标不变；不是重新独立检测出 231 栋楼。
- 不再随机分配外墙颜色，不再添加无观测依据的屋顶设备。外墙、楼高、窗位仍是占位或推断。
- 当前模型：`output/bnu_campus_gf2_sentinel2_v5.blend`、`output/bnu_campus_web_v5.glb`；当前属性：`assets/campus_assets_v5.json`。v4 文件仍保留。
- 识别结果和带投影的分析栅格：`assets/gf2_reanalysis_v5/`；复盘：`重识别复盘_2026-09-05.md`。

复现 v5：先运行 `python reidentify_gf2.py`；再运行 Blender `-b --python build_blender_scene.py -- --gf2-v5`；随后用 Blender 打开 `output/bnu_campus_gf2_sentinel2_v5.blend`，分别执行 `export_web_scene.py` 和 `verify_scene.py`。不加 `--gf2-v5` 的建模命令仍生成旧版本。

### 2026-09-05 近景纹理修复（v4，历史版本）

- 入口：`http://127.0.0.1:8765/index.html?view=texture&v=20260905v4c`。右侧 **05 墙面特写** 检查砖缝和实体窗框；顶部 **收起面板** 腾出视野。
- 当前墙材：`assets/image2_brick_surface_v4.png` 与 `assets/image2_stone_surface_v4.png`。不再使用含窗户的 v2/v3 图集，避免双重窗位。
- 41,077 块窗面配套实体窗框与中梃；修正重复面、朝向、地理 UV、立面 UV 和 GLB 颜色乘子。场景为 273,597 个源多边形，导出的三角形数为 577,244；两个数量不是同一个指标。
- 实时网页截图：`output/web_facade_v4.jpg`、`output/web_texture_v4.jpg`。它们是浏览器实拍，不是 Image2 修图。
- 模型：`output/bnu_campus_gf2_sentinel2.blend` 和 `output/bnu_campus_web.glb` 已更新；旧版备份在 `output/backup_20260905/`。
- 验证：`verify_scene.py`，结果 `output/validation_20260905.json`。生成提示词、变更复盘和边界见 `修复复盘_2026-09-05.md`。

以下清单保留早期成果记录，其中带 v2 的纹理和细节预览已经不是当前版本。

- `output/bnu_campus_gf2_sentinel2.blend`：Blender 4.5 LTS 场景。
- `output/bnu_campus_hero.png`：斜视主预览。
- `output/bnu_campus_top.png`：俯视核对图。
- `output/bnu_campus_detail_enhanced.png`：以俯视图为细节参照生成的效果增强图。
- `output/bnu_campus_image2_texture_detail_v2.png`：Image2 纹理写入真实墙面后的 Blender 近景检查图。
- `output/bnu_campus_web.glb`：供网页观察者加载的轻量三维场景。
- `index.html`：三维观察者入口；`gallery.html` 保留原来的图片效果对比页。
- `打开观察者模式.cmd`：自动启动本地网页并用浏览器打开。
- `assets/gf2_bnu_truecolor.png`：高分二号校园真彩裁剪纹理。
- `assets/image2_facade_atlas_v2.png`：由 Image2 生成的四象限校园立面纹理图集；四张裁剪贴图用于 Blender 与 GLB。
- `assets/campus_assets.json`：坐标、建筑、道路、树木、地形和数据血缘。

## 数据与分工

- 高分二号：约 0.7–0.9 m 地面采样间隔，生成地表真彩纹理，并由红光/近红外计算 NDVI，提取树冠候选。
- Sentinel-2：目录中的北京 NDVI 成果分辨率约为数百米，只作为区域植被先验；完整 SAFE 数据覆盖山西，未用于北师大几何。
- Copernicus GLO-30：给底板提供低幅度地形起伏。
- OpenStreetMap：补充建筑轮廓、步道、运动场、绿地和水体。缺失高度时按层数、建筑类型和面积进行规则估计。

## 场景内容（v4 历史记录；v5 变更见顶部）

- 231 个建筑体块；
- 41,077 块规则化立面窗格、1,309 段屋顶女儿墙、180 个屋顶设备体块；
- 120 条校园步道；
- 28 个运动场、绿地或水体面；
- 520 棵由高分二号 NDVI 局部极大值生成的低多边形树；
- 两台相机、太阳光和环境补光。

当前模型为展示级规则化模型：高分二号纹理按地理坐标投影到建筑屋顶；Image2 无窗红砖和石材按约 2.4 × 2.4 m 重复到墙面，并以四种颜色乘子区分材质。窗格、窗框、女儿墙和屋顶设备是可旋转观察的网格；规则细节和生成纹理不代表真实门窗、设备或材料位置。“LOD1.5”是项目内部对细节程度的简称，不是测绘精度等级。

## 网页观察者模式

双击 `打开观察者模式.cmd` 即可进入，不要直接双击 `index.html`。浏览器安全机制会阻止普通本地网页读取 GLB，因此启动文件会在 `127.0.0.1:8765` 建立仅本机可访问的临时静态服务。

- 自由观察：左键拖动旋转，右键拖动平移，滚轮缩放，单击建筑查看来源说明。
- 进入校园：点击顶部按钮后，移动鼠标环顾，使用 WASD 或方向键移动，Q/E 调整高度，Esc 暂停。
- 预设视角：右侧可一键切换斜视全景、垂直俯视和近地观察。
- 图层控制：左侧可分别隐藏建筑及其规则化细节、道路、地表和树木，并调节漫游速度。
- 效果对比：顶部入口返回 Blender 原图、Image2 增强图和俯视图对比页面。

页面现已按“校园植物三维 WebGIS”的信息架构升级：

- 校园分布：三维场景、建筑/道路/地表/树木图层控制、建筑名称与 OSM ID 搜索。
- 空间统计：从 `campus_assets.json` 自动计算建筑数量、属性完整性、平均高度和要素组成。
- 技术路线：展示遥感预处理、GIS 要素、Blender 建模、GLB 发布和 WebGIS 交互流程。
- 数据说明：分别说明高分二号、Sentinel-2、OSM 与 DEM 的用途和精度边界。
- 属性联动：点击或检索建筑时，显示真实名称、用途、层数、估算高度、占地面积和 OSM ID。

## 复现（v4；v5 命令见顶部）

先运行：

```powershell
python .\prepare_assets.py
```

再运行：

```powershell
& 'C:\Program Files\Blender Foundation\Blender 4.5\blender.exe' --background --python .\build_blender_scene.py
```

最后导出网页模型：

```powershell
& 'C:\Program Files\Blender Foundation\Blender 4.5\blender.exe' --background .\output\bnu_campus_gf2_sentinel2.blend --python .\export_web_scene.py
```

## 精度边界

这是 LOD1/LOD1.5 视觉原型。建筑轮廓具有地理坐标，但多数建筑高度是规则估计；树木是树冠候选点而非逐株实测；没有立面照片、倾斜摄影或高分辨率 DSM，因此不具备真实外立面、屋顶细节和测绘级高程。若要升级为近实景模型，应补充校园建筑高度/层数、无人机倾斜摄影或 LiDAR/DSM，以及建筑立面照片。
