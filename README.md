# 北师大校园 GF-2 / Sentinel-2 Blender 三维原型

## 产品 v1.0.0（2026-09-21）

当前交付白模使用 **white_v4**，产品版本统一见 [VERSION](VERSION)，修改记录见 [CHANGELOG.md](CHANGELOG.md)。下方旧版本章节保留为历史记录，不代表最新白模。

下载并解压后，在项目目录执行 `python campus_server.py --port 8786`，打开 `http://127.0.0.1:8786/white/index.html`；信息编辑页为 `/information/index.html`。运行网页服务仅需 Python 3 标准库。不要直接双击 HTML：本地文件协议不能正常提供模型和 POI API。Blender 用户可直接打开 `output/bnu_campus_white_v4.blend`。

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
