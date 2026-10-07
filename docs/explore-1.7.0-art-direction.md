# 1.7.0 美术与动画规范

日期：2026-10-02。阶段4为可操作的地图优先界面，阶段5为三栋建筑的示意材质试验，不是实景贴图完成版。

## 参考与取舍

参考用户提供的 [Colonia Zacamil](https://coloniazacamil.com/) 截图与网页说明：场景占主导、黑色胶囊导航、留白、点击兴趣点后探索。参考站说明支持拖动、缩放、点击标记；本轮外部站点在浏览器打开超时，未声称实际完整体验其动画，也未复制其源码、图片或模型。

本项目把叙事式漫游转成生活查询：顶部对话常驻；分类筛选与建筑高亮共用地点ID；右侧资料窗承载菜单、地点和对话，手机改为单个底部面板。保留原对话版作为回退入口。不是用大量装饰卡片盖住地图。

风格提示词：校园建筑微缩模型、暖白纸面、炭黑胶囊、草木绿点缀、宋体标题与清晰正文、低对比矿物表面、轻浮层、安静而可打断的镜头引导。避免霓虹、通用紫色渐变、自动巡航、假真实立面和夸张弹跳。

## 可调模块

| 文件 | 负责内容 | 调整边界 |
| --- | --- | --- |
| `app/explore/explore.css` | 颜色、字级、间距、响应式、面板过渡 | 不混入业务判断 |
| `main.js` | 页面交互、分类与详情、对话流、错误恢复 | 不直接改数据库或地理数据 |
| `state.js` | 分类、过滤、ID关联、纯状态、缓动 | 可独立单测 |
| `api.js` | 现有HTTP与流式协议 | 供应商、密钥留在后端 |
| `scene.js` | 相机、射线、POI、镜头避让、北向 | 保留原XY与模型几何 |
| `materials.js` | 示意颜色、三栋纸感材质、白模恢复 | 克隆材质，不修改GLB |
| `art/manifest.json` | 来源与非测量标记 | 不把生成图当实地证据 |

## 动画规则

- 点击地点后以720ms cubic-out过渡；拖动立即打断，模型回复只高亮而不抢镜头。
- 面板仅用透明度、位移过渡；键盘操作及减少动态偏好使用即时状态，不靠动画才能完成任务。
- 不自动旋转，不用弹跳吸引注意；页面后台暂停渲染。帧率未做实机性能基准。
- 窄屏面板展开时通过投影偏移留出选中建筑，不搬动建筑或POI坐标。指北针使用投影后的本地北向。

## 生成材质与提示词

产物：`app/explore/art/paper-plaster-v1.png`，本轮内置图像生成，约2.73MB，通用暖白纸感矿物表面。未上传用户照片作参考；原始输出直接复制，未后处理。页面没有将这张图当作餐品照片。

实际提示词：

```text
Use case: stylized-concept. Asset type: square seamless architectural material swatch for an interactive campus miniature, NOT a finished building. Primary request: one uniform off-white warm mineral plaster / handmade paper surface, delicate pencil hatching and fine natural grain, premium editorial architectural maquette aesthetic. Orthographic flat scan, texture fills entire frame. Very low contrast, warm ivory neutral base with tiny grey-beige irregular fibres. Even flat albedo illumination. Seamlessly tileable across both axes, no borders, no shadows, no perspective, no buildings, no windows, no objects, no writing, no logos. This is a clearly illustrative surface material for a 3D UI, not a measured real facade. 1024 square composition.
```

提示词要求可平铺，但未做数值接缝评估；当前只以低强度重复采样作示意纹理。生成“1024 square composition”是提示要求，不作为文件尺寸实测值。

示例建筑：新乐群499434918、学五499437078、科技楼172257586。保留原材质引用，上色使用克隆件。关闭上色时恢复原材质；选中高亮继续可用但纸纹强度归零。纹理下载失败回退纯色，模型下载失败仍可用清单。

## 实景纹理尚需哪些依据

高分影像主要提供屋顶和平面信息，不能确定立面颜色、窗户数量、层高。官网缩略图与现场照片要先核对建筑对象、拍摄方向、许可和拍摄时间，再决定立面贴图与UV分区。西北食堂西侧照片的准确网格归属尚未确定，且含人物，本轮没有公开原照或强贴模型。

下一步先为一栋楼收集可追溯四向照片，去除敏感内容，逐面核对；实景与示意两种模式继续分开。当前不需要为上色重建数据库或训练模型。

## 用户反馈与防重复

用户明确要求关注美术而不止控件可用：交付必须实际看桌面与手机画面。此次发现并修正旧地点标签残留、悬停反差不足、手机目标建筑被详情面板盖住。今后地图验收同时检查目标可见性、卡片内容、坐标语义和动画可打断性，不把UI截图等同地理精度验证。
