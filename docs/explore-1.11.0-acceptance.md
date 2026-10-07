# 1.11 水彩导览UI实施与阶段验收

日期：2026-10-04。状态：代码与功能检查完成，完整素材视觉验收待本地重启。

## 改动边界

根据用户选定的[银杏水彩样稿](design-1.11-target.png)实现UI。只改app/explore的HTML、CSS、main.js与服务资源白名单、测试、版本文档。未修改数据库、地理位置、楼栋几何、营业时间、菜单、模型配置或密钥。既有白模、道路、点选、建筑高亮与漫游仍由Three.js渲染。样稿中的水彩校园是概念画，不是实际测绘地图，本轮没有将3D材质完全转换为该画风。

## UI结构

- 顶栏88px：品牌、唯一提问入口、我的对话与经典版。
- 桌面分类栏88px、资料栏344px；平板资料栏300px，手机切换为横向分类与可展开底部面板。
- 标题宋体28px，分节黑体16px，正文14px，辅助13px；手机紧凑地图控制保留适用缩放。
- 建筑资料分为简介和楼内服务；没有依据的介绍继续标待补。默认不展示商户菜单，主动打开服务分类并选择吃喝后，科技楼显示二层瑞幸。
- 纹饰占独立留白，pointer-events:none，不覆盖操作和正文。素材来自内置ImageGen，完整提示见app/explore/art/ui-provenance-1.11.json。

## 已验证

1. `python -m unittest discover -s tests`：133项通过，包括新图片HTTP路径、PNG头、MIME、nosniff与未授权目录404。
2. `python -m unittest test_campus_api.py test_poi_import.py`：9项通过。
3. `node verify_web_syntax.cjs`、`node --check information/app.js`、`node --check app/explore/main.js`通过。
4. 六组Node测试：explore、explore-directory、explore-ui、presentation、map_locations、explore-materials均通过。
5. 浏览器实测1488×1056、1024×768、390×844、320×568。建筑搜索→科技楼→楼内服务→吃喝→二层瑞幸可达；我的对话打开历史面板；手机展开/关闭可用。
6. 小吃街主排13条和西北食堂西侧组6条完整可见，顺序未被UI修改；缺坐标仍保留列表，不声称已准确定位。
7. 320px页面scrollWidth=320，底部最后按钮right=301；390px修复后资料区clientWidth=scrollWidth=359。字体实测28/16/14/13px。
8. 浏览器采集的console error列表为空，但不能据此忽略HTTP资源失败；单独GET新图片证实旧8793返回404。

## 本次纠错与避免重复

- 用户希望字体有逻辑：使用统一角色字号，而非随组件任意缩小到10px。
- 用户希望保留花纹：生成真正的低调背景素材，装饰放在留白，不用静态整屏图冒充应用。
- 平板地图工具栏和视角栏碰撞：1024px实测发现后提高工具栏位置，复拍确认间隔。
- 手机装饰容器沿用桌面负边距导致横向滚动：取消负右边距，实测宽度一致。以后背景装饰也必须进行窄屏溢出检查。
- 不把代码修改等同服务生效：服务只在启动时构建白名单；VERSION实时显示1.11不能证明新路由已加载。

## 阻塞与下一次操作

旧服务PID在本轮核对为47540，127.0.0.1:8793，Python app_server.py；configured=false。重启命令被执行环境拒绝，未尝试其他路径绕过、未启动替代端口。已请用户在原终端停止后重新运行`python app_server.py --port 8793`。

重启后必须重新核对两张素材200、纸纹与银杏实际渲染、桌面/手机截图及控制台，更新根design-qa.md；当前final result: blocked。不把隔离测试服务可加载图片当作8793已生效。

阶段截图：design-1.11-desktop-pending.png、design-1.11-tablet-pending.png、design-1.11-mobile-pending.png，均为真实运行页面、暂未加载新增纹饰。
