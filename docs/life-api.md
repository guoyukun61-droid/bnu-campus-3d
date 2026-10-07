# 校园生活 API 1.1.0

## 运行

在项目根目录执行：

    python -m backend.bootstrap
    python campus_server.py --port 8787

打开 http://127.0.0.1:8787/white/ 。默认端口仍为8786；本轮预览采用8787，保留原8786进程。网页、模型和API同源，信息工作台位于 /information/。使用已有 Python 3.13；Web服务和推荐仅依赖标准库。百度采集另需现有 pyproj、shapely、eviltransform。

仅单机、单服务进程使用。Host/Origin校验不是多用户认证，不可直接公开部署。预约使用进程内锁，不能用两个进程同时写同一个预约JSON。

## 数据位置与对象

- backend/seeds/catalog.py：源名录及显式模拟样例的生成规则。
- data/life/catalog.json：可编辑主数据，启动不覆盖已有行；新增缺失的预定义店铺ID时只追加。
- data/life/baidu_normalized.json：百度标准化记录；重复整理保留已有版本。
- data/life/raw/：不含密钥的响应快照。
- data/life/collection.json：分页游标、任务状态、请求计数和截断状态。
- data/life/reservations.json：虚构预约，原子替换保存；取消保留记录。
- data/life/exports/：按时间命名的名录和覆盖报告，不自动清理。
- data/campus_info.sqlite3：原库，生活服务只读适配；原编辑工作台维持原协议。

backend/schemas.py 校验结构版本、ID唯一性、父子引用、有限数值和来源字段。

POI 字段：id、name、category、zone、address、floor、source、status、location、location_crs、location_source、building_id、opening_hours、hours_source、access_scope。location 为 {x,y} 或 null，单位是本地UTM米；building_id 可空。zone 为 campus/affiliated/nearby/unknown，不表示产权。status 为核验状态；business_status 单独保存百度营业提示。opening_hours 为 [["10:30","13:30"]] 或 null，小时采用北京时间。分区复杂的食堂不合并成虚假全天营业。

Shop：id、poi_id、name、floor、source、status、opening_hours。
Item：id、shop_id、name、price、price_source、tags、source、available、serving_minutes、image_url、image_kind、dietary_verified。price 未知为 null；百度人均消费另存 average_price，不转换为单品价格。
DynamicState：shop_id、queue_minutes、crowd_level、available、source、valid_from、valid_until。
ScheduleEvent：id、user_id、name、location、start、end、source。
Reservation：id、request_id、seat_id、user_id、start、end、status、source。

id 是实体身份，名称可以修订；同一building_id可有多个场所。兰蕙餐厅通过明确身份映射关联旧库，旧库编辑优先；其他疑似别名只进入核对清单。

## HTTP 契约

统一前缀 /api/life。GET 列表返回 {"records": [...]}，coverage 返回统计对象。

| 方法 | 路径 | 参数 |
|---|---|---|
| GET | /pois、/shops、/items | q、category、zone、poi_id、shop_id、building_id、source、status；精确值过滤 |
| GET | /locations | 用户可选地点；当前教八、教九、图书馆 |
| GET | /schedule | user_id、date=YYYY-MM-DD |
| GET | /dynamic-state | shop_id 可选、at=带时区ISO时间 |
| GET | /library/slots | start、end，须URL编码加号 |
| GET | /library/reservations | user_id 可选 |
| GET | /coverage | 名录量、模拟量、任务状态、缺口、疑似重复、适配器状态 |
| POST | /recommendations | 见下方示例 |
| POST | /library/reservations | request_id、seat_id、user_id、start、end |
| POST | /library/reservations/{id}/cancel | user_id |

POST 必须是 application/json、正文不超过32KiB，并有同源 Origin。成功200，参数错误400，同源拒绝403，未知路径404，预约冲突409，类型错误415，文件不可访问503。GET/HEAD不写入预约。私有目录、后端源码和隐藏文件不经静态服务提供。

推荐输入示例：

    {
      "current_location": "教八",
      "current_time": "2026-09-21T11:45:00+08:00",
      "budget": 20,
      "max_queue_minutes": 10,
      "available_minutes": 105,
      "next_class": {"time": "2026-09-21T13:30:00+08:00", "location": "教九"},
      "taste": ["辣"],
      "avoid": ["米饭"],
      "likes": ["鸡肉"],
      "dietary_requirements": [],
      "mapped_only": true,
      "mode": "demo",
      "top_k": 3
    }

top_k=1..3；mapped_only默认false，网页默认true，避免把模拟位置当成空间依据。mode=demo允许显式模拟字段；mode=verified要求已核验店铺、真实商品和真实动态数据，当前会如实返回空结果。时间必须带时区，按Asia/Shanghai对应+08:00处理。

输出含 recommendations、rejected（按被排除商品数计数）、candidate_count、available_minutes、notice。每条推荐带 poi_id/shop_id/item_id、rank、price、score、score_parts、walking_minutes、return_walking_minutes、queue_minutes、total_estimated_minutes、reason、sources、simulation 和 feasibility。

总时间 = 去程步行 + 排队 + 出餐 + 用餐 + 下一课堂步行 + 缓冲。
当前默认用餐15分钟、缓冲5分钟；距离估时按70米/分钟和1.3绕行系数，不是导航路线。缺坐标时demo步行使用8分钟占位，返回 sources.walking=simulated；真实模式不使用。没有下一课时返程为0。

后端先检查硬约束再排序。饮食安全条件必须有独立核验，不能从普通食材标签推断无过敏原或清真认证。不同shop_id去重，可能出现同栋楼的不同楼层推荐。权重在 backend/seeds/ranking.json 中独立配置。

## 模拟预约

只允许 demo-student-1 / demo-student-2，座位 demo-A01..demo-A04。时段同日08:00–22:00、正时长且不超过4小时。使用半开区间，因此16:00–17:00与17:00–18:00不冲突。

request_id在同一用户内幂等：相同内容重复返回原结果，不同内容返回409；已取消的请求仍返回原已取消记录，新预约必须使用新request_id。相同座位或者相同用户重叠预约返回409。只允许对应虚构用户取消，重复取消不重复写入。该身份选择没有认证能力，仅供本地演示。

## 百度采集与报告

    python query_baidu_pois.py --prepare-only
    python -m backend.collector --max-requests 300
    python -m backend.export

2026-09-21 实测：当前 AK 的矩形请求返回 9，圆形及城市检索返回 0。首次可选择 `--geometry circle`，用网格中心和半对角线加 20 米的半径覆盖网格；后续直接续采会读取已保存模式。含成功分页的任务不允许切换模式，以免混合分页造成漏收。圆形检索 `radius_limit=true` 的 total 可能不准确，数量不足会细分，最终不足仍保留 incomplete。它不是现实商户完整率。

新增百度商户依据分类生成稳定的 Shop 对象；没有菜单的商户只进入列表，不凭人均消费生成商品价格。`/coverage` 包含 query_geometry、requests_total 和 unfinished_tasks，供核查具体分区及分页。

密钥只从进程环境 BAIDU_MAP_AK 读取；不要把密钥写到参数、源码、日志或提交中。不自动修改.env或系统环境变量。缺少密钥仍可准备任务并整理既有审计，但必须显示 blocked_missing_key。

任务为500米网格分类检索及已知店名补查。分页大小20；疑似达到文档150结果限制时细分，最小网格/最大深度后仍截断标为truncated；结果数量不足标为incomplete，不计为完成。每秒最多一次、每轮最多300次（含重试），配额或鉴权失败立即保存并停止。重新执行续跑pending/failed任务；incomplete/truncated待核对，不无限重试。

精确范围使用近似主校区多边形外扩1000米；校外仅保留餐饮候选。现有南院已知名录以affiliated保留。BD-09经近似转换到WGS84，再投影EPSG:32650减去现有原点。不是测量坐标。只有唯一包含关系才生成候选建筑关联，不吸附最近建筑。

美团正式适配器标记not_configured。更换真实数据时实现同形对象并替换相应适配器；不改变上层HTTP结构。LLM、真实学校预约、支付和路网规划均未接入。
