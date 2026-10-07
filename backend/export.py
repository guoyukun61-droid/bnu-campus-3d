"""Export a timestamped private inventory and coverage bundle, without DB writes."""
import csv
from .storage import ROOT, now, write, read
from .service import LifeService

def main():
    directory=ROOT/"data/life"
    service=LifeService(directory,ROOT/"data/campus_info.sqlite3")
    catalog=service.catalog.snapshot()
    coverage=service.coverage()
    stamp=now().replace(":","").replace("+","_")
    output=directory/"exports"/stamp
    output.mkdir(parents=True,exist_ok=False)
    write(output/"catalog.json",catalog)
    write(output/"coverage.json",coverage)
    collection=read(directory/"collection.json",{})
    for filename,rows,columns in (
        ("collection_tasks.csv",collection.get("tasks",[]),("id","query","depth","page","status","total","error","last_success_at")),
        ("source_comparison.csv",catalog["pois"],("id","name","source","source_uid","retrieved_at","legacy_record_id","status")),
        ("dispositions.csv",coverage["dispositions"],("uid","name","status")),
    ):
        with (output/filename).open("x",encoding="utf-8-sig",newline="") as stream:
            writer=csv.DictWriter(stream,fieldnames=columns,extrasaction="ignore")
            writer.writeheader();writer.writerows(rows)
    fields=("id","name","category","zone","address","floor","building_id","status","source","location_source","hours_source","access_scope")
    with (output/"places.csv").open("x",encoding="utf-8-sig",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=fields,extrasaction="ignore")
        writer.writeheader();writer.writerows(catalog["pois"])
    with (output/"shops.csv").open("x",encoding="utf-8-sig",newline="") as stream:
        fields2=("id","poi_id","name","floor","source","status")
        writer=csv.DictWriter(stream,fieldnames=fields2,extrasaction="ignore")
        writer.writeheader();writer.writerows(catalog["shops"])
    lines=["# 数据覆盖与缺口报告","",f"生成时间：{now()}","",
        f"- 合并地点记录：{len(catalog['pois'])}（含建筑、校门和历史记录，不等于店铺数）。",
        f"- 有来源初始餐饮名录：{coverage['known_catalog_records']}。",
        f"- 模拟窗口：{coverage['simulated_shops']}；模拟菜品：{coverage['simulated_items']}。",
        f"- 百度任务：{coverage['completed_tasks']}/{coverage['total_leaf_tasks']}；状态：{coverage['collection_status']}。",
        f"- 缺坐标：{len(coverage['missing_coordinates'])}；缺结构化营业时间：{len(coverage['missing_hours'])}。",
        "- 现实店铺完整率：未知；现场全量清单尚未获得。","",
        "## 来源与处置","",
        "- 官方餐饮指南用于名称、楼层和公开营业时段；当前营业状态仍待核。",
        "- 原有清单用于周边餐饮和校内连锁店；坐标缺失保持为空。",
        "- 历史百度审计与本轮成功响应按 UID 整理；每条记录保留其获取时间，旧数据不冒充新抓取。",
        "- 商贸服务指南在本轮核验时返回404，校内非餐饮全业态名录待百度及现场补录。",
        "- 一个已知别名关系（兰蕙餐厅）保留旧库编辑与建筑关联；其他疑似重复不自动合并。",
        "- 表中模拟窗口和商品不得当作商户真实菜单。","",
        "## 逐场所补录",""]
    for gap in coverage["gaps"]:
        lines.append("- "+gap["name"]+"："+"、".join(gap["missing"]))
    lines+=["","## 当前阻塞","",
        f"当前采集状态：{coverage['collection_notice']}；失败、截断和未完成任务见 coverage.json。",
        "续采时临时提供运行时 BAIDU_MAP_AK，执行 python -m backend.collector；不得写入密钥文件。",
        "完整性还依赖逐楼层/档口核对；百度任务完成不等于现实全部商户收齐。"]
    (output/"coverage.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(output)
    print(f"places={len(catalog['pois'])}; simulated_items={coverage['simulated_items']}; collection={coverage['collection_status']}")
if __name__=="__main__":main()
