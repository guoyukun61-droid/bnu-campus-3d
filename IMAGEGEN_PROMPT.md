# Imagegen 细节增强记录

执行模式：Codex 内置 `image_gen` 编辑模式。

输入角色：

- Image 1：`output/bnu_campus_hero.png`，编辑目标。
- Image 2：`output/bnu_campus_top.png`，屋顶颜色、操场标线、院落、植被与地表细节参考。

最终提示词：

```text
Use case: precise-object-edit
Asset type: polished visualization preview for a Blender-based geospatial campus model
Primary request: refine the material and surface detail of Image 1 while using Image 2 as a top-down geographic and texture reference.
Input images: Image 1 is the edit target and must keep its exact camera, campus footprint, building locations, road network, sports fields, and overall composition. Image 2 is a supporting reference for correct roof colors, track markings, courtyards, vegetation placement, and ground details.
Style/medium: high-quality physically based architectural visualization, still recognizably a Blender geospatial model rather than a real aerial photograph.
Materials/textures: add restrained red-brick and pale-stone facade variation, believable horizontal window bands, sharper roof edges, subtle rooftop equipment inferred only where visible in Image 2, detailed running-track and court markings, varied natural tree foliage, soft ambient occlusion and realistic contact shadows.
Lighting/mood: clear late-afternoon daylight with balanced contrast and legible details; preserve the dark neutral presentation background.
Constraints: preserve all geometry, scale, camera angle, campus layout, satellite-ground registration, sports-field locations, and building count; change only material realism, texture clarity, lighting, and fine surface detail. No new or removed buildings, no invented landmark, no text, no labels, no logos, no watermark, no people, no vehicles added, no fantasy styling, no excessive saturation.
```
