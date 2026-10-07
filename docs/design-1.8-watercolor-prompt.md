# 1.8 水彩风格样稿来源

2026-10-03。使用内置 image_gen，不使用CLI、不需要修改密钥。输出：`design-1.8-watercolor-concept.png`。此图仅供风格选择，未作为纹理加载。输出中建筑细节存在生成性重绘，不能反推几何或真实窗位。

输入1：项目已有 `assets/user_reference_campus_illustration.png`，构图与美术参考。
输入2：`assets/gf2_reanalysis_v5/truecolor_utm.png`，仅提供屋顶/地表配色，不证明立面。
外站10图研究未完成；这次没有把未取得的截图交给生成模型。

## 实际提示词

Use case: stylized-concept. Create ONE landscape 16:9 refined cartoon-watercolor campus map art-direction proof, not a surveyed map or texture atlas. Reference image 1 is the user's existing Beijing Normal University campus illustration: retain the overall campus composition, twin sports grounds, main building and street layout as closely as possible. Reference image 2 is the GF2 top-down view: use only general rooftop red / gray and vegetation palettes, never infer facade facts from satellite pixels. Reinterpret as a warm, beautifully crafted animated watercolor miniature campus, crisp simplified geometry, restrained ink outlines, granular paper plaster, blue-gray window rhythm, terracotta and gray roof washes, rounded hand-painted trees, soft shadows. Strong clear dark graphite roads against pale sage ground; preserve continuous roads, do not wash them out. Camera bird's-eye like image 1. Architecture remains readable and uncluttered, charming but not toy plastic, no neon, no photorealism. Minimal overlay UI: top center slim dark pine input bar text '想去哪里？'; below small category controls '建筑  美食  饮品  运动'. Upper left restrained Chinese serif wordmark '京师智行'. Lower right small label exactly '水彩风格样稿 · 非实景复原'. Large map dominates. No claims of accuracy, no store pins, no fake metrics, no giant marketing slogan, no complex info cards. This is a standalone visual style sample, not the screenshot of a working app.

## 人工检查

图中道路较原浅色方案清晰，屋顶、窗带与树冠区分，水彩颗粒柔和；左上标识仍比实际应用大，不能直接照搬。正式模型继续使用基础上色；下一步需先确定是否采用此美术方向，再做有限楼栋可平铺材质与性能测试。
