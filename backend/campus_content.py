"""Read-only, identity-bound public building descriptions.

Content is a separate projection: it never changes geometry, shop membership,
opening hours, access rules, or the private source catalogue.  A checked source
supports only the short description; it does not verify the model footprint.
"""
from copy import deepcopy
import json
from pathlib import Path
from urllib.parse import urlsplit


SEED_PATH = Path(__file__).with_name("seeds") / "building-content-20261008.json"
CONTENT_SCOPE = "用途短介绍；不证明模型边界、楼层、营业时间、门禁或预约可用性。"
AREA_SCOPE = "内容导览区域，不是测绘边界；不据此创建坐标或自动归属店铺。"
_GENERATED_MARKER = "campus_content_v1"
_PLACEHOLDER_STATUS = "仅有基础名录，详细介绍待补充"
_ALLOWED_ORIGINS = {"official_public_source", "inferred", "model_inventory"}


def _document(content_document):
    if content_document is not None:
        if not isinstance(content_document, dict):
            raise ValueError("content_document must be a mapping")
        return content_document
    return json.loads(SEED_PATH.read_text(encoding="utf-8"))


def _safe_sources(entry, document):
    """Only publish the seed's public university evidence, never arbitrary fields."""
    result = []
    seen = set()
    for source_id in entry.get("source_ids", []):
        source = document.get("sources", {}).get(source_id, {})
        url = source.get("url", "")
        try:
            parsed = urlsplit(url)
            host = (parsed.hostname or "").lower()
            valid = (parsed.scheme == "https" and not parsed.username
                     and not parsed.password and parsed.port in (None, 443)
                     and (host == "bnu.edu.cn" or host.endswith(".bnu.edu.cn")))
        except (TypeError, ValueError):
            valid = False
        if not valid or url in seen or not source.get("title"):
            continue
        seen.add(url)
        result.append({
            "title": str(source["title"]), "url": url,
            "retrieved_at": source.get("retrieved_at"),
            "published_at": source.get("published_at"),
            "temporal_note": str(source.get("temporal_note") or ""),
        })
    return result


def _entry_content(entry, document):
    template = document.get("templates", {}).get(entry.get("template"), {})
    return {**template, **entry}


def _metadata(entry, document):
    origin = entry.get("content_origin", "model_inventory")
    if origin not in _ALLOWED_ORIGINS:
        raise ValueError("Unsupported public building content origin")
    links = _safe_sources(entry, document)
    description = str(entry.get("description") or "用途尚未核实，保留现有名称供人工核对。")
    status = entry.get("description_status") or {
        "official_public_source": "official_summary", "inferred": "inferred",
        "model_inventory": "identity_pending",
    }[origin]
    review_state = entry.get("review_state") or {
        "official_public_source": "source_checked_identity_bound",
        "inferred": "inference_pending", "model_inventory": "identity_pending",
    }[origin]
    if origin == "official_public_source" and not links:
        # Missing/unsafe evidence must not turn an unsupported statement into fact.
        description = "资料来源未通过公开链接校验，用途介绍暂不发布，待人工核对。"
        origin, status, review_state = "model_inventory", "unknown", "source_pending"
    elif origin == "inferred" and not description.startswith("推测："):
        description = "推测：" + description
    return {
        "description": description,
        "description_status": status,
        "content_origin": origin,
        "source_links": links,
        "review_state": review_state,
        "function_tags": list(entry.get("function_tags", [])) if status != "unknown" else [],
        "content_scope": CONTENT_SCOPE,
        "content_limitations": list(entry.get("limitations", [])),
        "content_version": str(document.get("version") or "unversioned"),
        "content_projection": _GENERATED_MARKER,
    }


def _has_existing_description(record):
    # Explicit field evidence, even for an empty value, means deliberate editing.
    evidence = record.get("field_evidence")
    if isinstance(evidence, dict) and "description" in evidence:
        return True
    if record.get("description_manually_edited"):
        return True
    description = record.get("description")
    if description in (None, ""):
        return False
    name = str(record.get("name") or "").strip()
    placeholders = {
        f"{name}的建筑位置。选择美食、饮品等分类可查看已关联的店铺。",
        "这栋建筑的名称与介绍尚待补充。",
    }
    return not (record.get("description_status") == _PLACEHOLDER_STATUS
                and description in placeholders)


def enrich_buildings(buildings, content_document=None):
    """Return copied records with descriptions; match exact ID AND original name.

    Accept raw ``osm_id`` or API ``id`` records, retaining every original field.
    If both IDs exist they must agree.  Names/IDs are not normalized or renamed.
    Existing descriptions win except the known old generated directory template.
    Pass an explicit document for deterministic isolated tests and alternate seeds.
    """
    document = _document(content_document)
    entries = {}
    for entry in document.get("buildings", []):
        building_id = str(entry.get("building_id") or "")
        if not building_id or building_id in entries:
            raise ValueError("Building content IDs must be present and unique")
        entries[building_id] = _entry_content(entry, document)

    result = []
    for building in buildings:
        record = deepcopy(building)
        if _has_existing_description(record):
            record.setdefault("description_status", "existing_description")
            record.setdefault("content_origin", "existing_record")
            record.setdefault("source_links", [])
            record.setdefault("review_state", "existing_description_preserved")
            record.setdefault("function_tags", [])
            record.setdefault("content_scope", CONTENT_SCOPE)
            result.append(record)
            continue
        building_id = str(record.get("id", record.get("osm_id", "")))
        name = str(record.get("name") or "").strip()
        entry = entries.get(building_id)
        id_conflict = ("id" in record and "osm_id" in record
                       and str(record["id"]) != str(record["osm_id"]))
        if entry and not id_conflict and name == entry.get("identity_name"):
            metadata = _metadata(entry, document)
        else:
            unnamed = name in ("", "未命名建筑")
            mismatch = bool(entry or id_conflict)
            metadata = _metadata({
                "description": ("尚未确认独立建筑身份和用途；保留模型体块用于空间浏览。"
                                if unnamed else "尚未匹配这栋建筑的可靠用途资料，保留现有名称供人工核对。"),
                "description_status": "unknown",
                "review_state": ("identity_mismatch" if mismatch else
                                 "unnamed_model_part" if unnamed else "identity_pending"),
            }, document)
        record.update(metadata)
        result.append(record)
    return result


def area_descriptions(content_document=None):
    """Return public thematic area summaries, never geometric area membership."""
    document = _document(content_document)
    result, seen = [], set()
    for entry in document.get("areas", []):
        area_id = str(entry.get("id") or "")
        if not area_id or area_id in seen:
            raise ValueError("Area content IDs must be present and unique")
        seen.add(area_id)
        item = {"id": area_id, "name": str(entry.get("name") or ""),
                **_metadata(entry, document)}
        item["content_scope"] = AREA_SCOPE
        item["area_type"] = "narrative_area"
        item["geometry"] = None
        result.append(item)
    return result
