from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
import rasterio
import requests
from PIL import Image
from pyproj import Transformer
from rasterio.windows import from_bounds
from shapely.geometry import LineString, Point, Polygon
from shapely.prepared import prep


PROJECT_DIR = Path(__file__).resolve().parent
ASSET_DIR = PROJECT_DIR / "assets"
ASSET_DIR.mkdir(parents=True, exist_ok=True)

GF2_PATH = Path(
    r"D:\BaiduNetdiskDownload\GF2-20250624\beijingdata2025\GF2_PMS1_E116_3_N39_9_20250624_L1A14720897001_ORTHO_PSH.tif"
)
SENTINEL_NDVI_PATH = Path(
    r"D:\A-newdesktop\个人\本基\历史资料外表\2026-04-11-00_00_2026-04-11-23_59_Sentinel-2_L2A_NDVI.tiff"
)
DEM_PATH = Path(
    r"D:\A-newdesktop\个人\本基\trae_peojection\花粉过敏微博分析项目\data\dem\copernicus_glo30\Copernicus_DSM_COG_10_N39_00_E116_00_DEM.tif"
)

# BNU main campus: west/east campus blocks bounded by the surrounding arterial roads.
# A narrow edge context is retained so the campus still reads as part of Beijing.
BBOX_WGS84 = (116.3547, 39.9555, 116.3652, 39.9664)
LON0 = (BBOX_WGS84[0] + BBOX_WGS84[2]) / 2
LAT0 = (BBOX_WGS84[1] + BBOX_WGS84[3]) / 2
TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:32650", always_xy=True)
X0, Y0 = TO_UTM.transform(LON0, LAT0)


def percentile_stretch(array: np.ndarray, valid: np.ndarray) -> np.ndarray:
    out = np.zeros(array.shape, dtype=np.uint8)
    for idx in range(array.shape[0]):
        band = array[idx].astype(np.float32)
        sample = band[valid]
        low, high = np.percentile(sample, (2, 98))
        scaled = np.clip((band - low) / max(high - low, 1e-6), 0, 1)
        out[idx] = np.round(scaled * 255).astype(np.uint8)
    return out


def crop_gf2() -> tuple[np.ndarray, np.ndarray, dict]:
    with rasterio.open(GF2_PATH) as src:
        window = from_bounds(*BBOX_WGS84, transform=src.transform).round_offsets().round_lengths()
        data = src.read([1, 2, 3, 4], window=window, boundless=True, fill_value=0)
        transform = src.window_transform(window)
        valid = np.all(data > 0, axis=0)
        rgb = percentile_stretch(data[[2, 1, 0]], valid)
        rgb_hwc = np.moveaxis(rgb, 0, -1)
        Image.fromarray(rgb_hwc, "RGB").save(ASSET_DIR / "gf2_bnu_truecolor.png", optimize=True)

        red = data[2].astype(np.float32)
        nir = data[3].astype(np.float32)
        ndvi = np.divide(nir - red, nir + red, out=np.zeros_like(red), where=(nir + red) != 0)
        ndvi[~valid] = np.nan

        metadata = {
            "source": str(GF2_PATH),
            "bands": "B3/B2/B1 true color; B4 and B3 for NDVI",
            "shape": list(data.shape),
            "crop_bounds_wgs84": list(BBOX_WGS84),
            "crop_transform": list(transform)[:6],
            "valid_ratio": float(valid.mean()),
            "ndvi_percentiles": {
                str(p): float(np.nanpercentile(ndvi, p)) for p in (2, 25, 50, 75, 98)
            },
        }
    return rgb_hwc, ndvi, metadata


def sentinel_prior() -> dict:
    lon, lat = LON0, LAT0
    with rasterio.open(SENTINEL_NDVI_PATH) as src:
        row, col = src.index(lon, lat)
        r0, r1 = max(0, row - 1), min(src.height, row + 2)
        c0, c1 = max(0, col - 1), min(src.width, col + 2)
        values = src.read(window=((r0, r1), (c0, c1))).astype(np.float32)
        finite = values[np.isfinite(values)]
        median = float(np.median(finite)) if finite.size else 0.0
        return {
            "source": str(SENTINEL_NDVI_PATH),
            "note": "Regional-scale NDVI prior only; pixel size is too coarse for campus geometry.",
            "nearest_pixel": [int(row), int(col)],
            "sample_median": median,
            "sample_min": float(np.min(finite)) if finite.size else None,
            "sample_max": float(np.max(finite)) if finite.size else None,
            "resolution_degrees": list(src.res),
        }


def query_osm() -> dict:
    south, west, north, east = BBOX_WGS84[1], BBOX_WGS84[0], BBOX_WGS84[3], BBOX_WGS84[2]
    query = f"""
    [out:json][timeout:60];
    (
      way["building"]({south},{west},{north},{east});
      way["highway"]({south},{west},{north},{east});
      way["leisure"="pitch"]({south},{west},{north},{east});
      way["natural"="water"]({south},{west},{north},{east});
      way["landuse"="grass"]({south},{west},{north},{east});
    );
    out tags geom;
    """
    endpoints = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
    ]
    last_error = None
    for endpoint in endpoints:
        try:
            response = requests.post(
                endpoint,
                data={"data": query},
                headers={"User-Agent": "Codex-BNU-campus-prototype/1.0"},
                timeout=90,
            )
            response.raise_for_status()
            payload = response.json()
            (ASSET_DIR / "osm_raw.json").write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )
            payload["_source_endpoint"] = endpoint
            return payload
        except Exception as exc:  # try mirror
            last_error = f"{type(exc).__name__}: {exc}"
    raise RuntimeError(f"Overpass query failed: {last_error}")


def to_xy(lon: float, lat: float) -> tuple[float, float]:
    x, y = TO_UTM.transform(lon, lat)
    return x - X0, y - Y0


def clean_polygon(coords: list[tuple[float, float]]) -> Polygon | None:
    if len(coords) < 4:
        return None
    poly = Polygon(coords)
    if not poly.is_valid:
        poly = poly.buffer(0)
    if poly.is_empty or poly.geom_type != "Polygon" or poly.area < 8:
        return None
    return poly.simplify(0.3, preserve_topology=True)


def infer_height(tags: dict, area: float) -> tuple[float, int]:
    def first_number(value: str | None) -> float | None:
        if not value:
            return None
        token = value.lower().replace("meters", "").replace("meter", "").replace("m", "").strip()
        try:
            return float(token.split(";")[0])
        except ValueError:
            return None

    height = first_number(tags.get("height"))
    levels = first_number(tags.get("building:levels"))
    if height is None and levels is not None:
        height = levels * 3.4 + 0.6
    if height is None:
        kind = tags.get("building", "yes")
        if kind in {"shed", "garage", "garages", "roof"}:
            height = 4.0
        elif area > 5000:
            height = 22.0
        elif area > 1800:
            height = 17.0
        elif area > 500:
            height = 13.0
        else:
            height = 9.0
    height = float(np.clip(height, 3.0, 80.0))
    floors = max(1, int(round((height - 0.6) / 3.4)))
    return height, floors


def parse_osm(payload: dict) -> tuple[list[dict], list[dict], list[dict]]:
    buildings: list[dict] = []
    roads: list[dict] = []
    surfaces: list[dict] = []
    for element in payload.get("elements", []):
        geometry = element.get("geometry") or []
        tags = element.get("tags") or {}
        coords = [to_xy(item["lon"], item["lat"]) for item in geometry]
        if "building" in tags:
            poly = clean_polygon(coords)
            if poly is None:
                continue
            height, floors = infer_height(tags, poly.area)
            buildings.append(
                {
                    "osm_id": element.get("id"),
                    "name": tags.get("name") or tags.get("name:zh") or "",
                    "kind": tags.get("building", "yes"),
                    "height": round(height, 2),
                    "floors": floors,
                    "roof_shape": tags.get("roof:shape", "flat"),
                    "coords": [[round(x, 2), round(y, 2)] for x, y in poly.exterior.coords[:-1]],
                    "area": round(poly.area, 2),
                }
            )
        elif "highway" in tags and len(coords) >= 2:
            line = LineString(coords).simplify(0.6)
            if line.length < 4:
                continue
            kind = tags.get("highway", "path")
            width_default = {
                "primary": 10,
                "secondary": 8,
                "tertiary": 7,
                "residential": 5.5,
                "service": 3.4,
                "footway": 1.8,
                "path": 1.4,
                "cycleway": 2.2,
            }.get(kind, 2.4)
            try:
                width = float(str(tags.get("width", width_default)).replace("m", "").strip())
            except ValueError:
                width = width_default
            roads.append(
                {
                    "osm_id": element.get("id"),
                    "kind": kind,
                    "name": tags.get("name", ""),
                    "width": round(float(np.clip(width, 1.0, 14.0)), 2),
                    "coords": [[round(x, 2), round(y, 2)] for x, y in line.coords],
                }
            )
        elif tags.get("leisure") == "pitch" or tags.get("natural") == "water" or tags.get("landuse") == "grass":
            poly = clean_polygon(coords)
            if poly is None:
                continue
            surface_type = "pitch" if tags.get("leisure") == "pitch" else "water" if tags.get("natural") == "water" else "grass"
            surfaces.append(
                {
                    "osm_id": element.get("id"),
                    "kind": surface_type,
                    "sport": tags.get("sport", ""),
                    "name": tags.get("name", ""),
                    "coords": [[round(x, 2), round(y, 2)] for x, y in poly.exterior.coords[:-1]],
                }
            )
    return buildings, roads, surfaces


def vegetation_threshold(ndvi: np.ndarray, sentinel: dict) -> float:
    finite = ndvi[np.isfinite(ndvi)]
    sample = finite[(finite > -0.2) & (finite < 0.8)]
    scaled = np.clip((sample + 0.2) / 1.0 * 255, 0, 255).astype(np.uint8)
    otsu_value, _ = cv2.threshold(scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    gf2_otsu = otsu_value / 255.0 - 0.2
    prior = sentinel.get("sample_median", 0.0)
    prior_adjust = float(np.clip(prior, -0.2, 0.8)) * 0.015
    return float(np.clip(gf2_otsu + prior_adjust, 0.10, 0.24))


def create_tree_points(
    ndvi: np.ndarray,
    threshold: float,
    buildings: list[dict],
    surfaces: list[dict],
    max_trees: int = 520,
) -> list[dict]:
    height, width = ndvi.shape
    x_min, y_min = to_xy(BBOX_WGS84[0], BBOX_WGS84[1])
    x_max, y_max = to_xy(BBOX_WGS84[2], BBOX_WGS84[3])
    meters_per_px_x = (x_max - x_min) / width
    meters_per_px_y = (y_max - y_min) / height

    work = np.nan_to_num(ndvi, nan=-1.0).astype(np.float32)
    min_distance_m = 8.5
    radius_px = max(4, int(round(min_distance_m / ((meters_per_px_x + meters_per_px_y) / 2))))
    kernel_size = radius_px * 2 + 1
    maxima = work >= cv2.dilate(work, np.ones((kernel_size, kernel_size), np.uint8)) - 1e-6
    candidates = np.argwhere(maxima & (work >= threshold))
    candidates = sorted(candidates, key=lambda rc: float(work[rc[0], rc[1]]), reverse=True)

    exclusion_polys = []
    for building in buildings:
        exclusion_polys.append(Polygon(building["coords"]).buffer(2.0))
    for surface in surfaces:
        if surface["kind"] in {"pitch", "water"}:
            exclusion_polys.append(Polygon(surface["coords"]).buffer(1.0))
    prepared = [prep(poly) for poly in exclusion_polys if not poly.is_empty]

    accepted: list[dict] = []
    occupied: list[tuple[float, float]] = []
    for row, col in candidates:
        x = x_min + (col + 0.5) * meters_per_px_x
        y = y_max - (row + 0.5) * meters_per_px_y
        point = Point(x, y)
        if any(poly.contains(point) for poly in prepared):
            continue
        if any((x - px) ** 2 + (y - py) ** 2 < min_distance_m**2 for px, py in occupied[-180:]):
            continue
        score = float(work[row, col])
        crown = float(np.clip(2.5 + 3.2 * (score - threshold) / max(0.55 - threshold, 0.1), 2.2, 5.8))
        accepted.append(
            {
                "x": round(x, 2),
                "y": round(y, 2),
                "ndvi": round(score, 4),
                "height": round(crown * 2.15, 2),
                "crown_radius": round(crown, 2),
            }
        )
        occupied.append((x, y))
        if len(accepted) >= max_trees:
            break
    return accepted


def sample_terrain(size: int = 40) -> dict:
    xs = np.linspace(BBOX_WGS84[0], BBOX_WGS84[2], size)
    ys = np.linspace(BBOX_WGS84[1], BBOX_WGS84[3], size)
    points = [(float(x), float(y)) for y in ys for x in xs]
    with rasterio.open(DEM_PATH) as src:
        elevations = np.array([value[0] for value in src.sample(points)], dtype=np.float32).reshape(size, size)
    valid = np.isfinite(elevations) & (elevations > -100)
    base = float(np.median(elevations[valid]))
    elevations = np.where(valid, elevations - base, 0.0)
    elevations = cv2.GaussianBlur(elevations, (5, 5), 0)
    return {
        "source": str(DEM_PATH),
        "size": size,
        "base_elevation_m": round(base, 3),
        "relative_elevation_m": np.round(elevations, 3).tolist(),
    }


def main() -> None:
    _, ndvi, gf2_meta = crop_gf2()
    sentinel = sentinel_prior()
    osm_payload = query_osm()
    buildings, roads, surfaces = parse_osm(osm_payload)
    threshold = vegetation_threshold(ndvi, sentinel)
    trees = create_tree_points(ndvi, threshold, buildings, surfaces)
    terrain = sample_terrain()
    x_min, y_min = to_xy(BBOX_WGS84[0], BBOX_WGS84[1])
    x_max, y_max = to_xy(BBOX_WGS84[2], BBOX_WGS84[3])
    data = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "project": "Beijing Normal University main-campus Blender prototype",
        "coordinate_system": {
            "source": "EPSG:4326",
            "metric": "EPSG:32650",
            "origin_wgs84": [LON0, LAT0],
            "origin_utm": [X0, Y0],
            "bbox_wgs84": list(BBOX_WGS84),
            "extent_m": [x_min, y_min, x_max, y_max],
        },
        "gf2": gf2_meta,
        "sentinel2": sentinel,
        "vegetation": {
            "gf2_ndvi_threshold": threshold,
            "tree_count": len(trees),
            "method": "GF-2 local NDVI maxima, OSM building/pitch/water exclusions, Sentinel-2 regional prior",
        },
        "osm": {
            "endpoint": osm_payload.get("_source_endpoint"),
            "building_count": len(buildings),
            "road_count": len(roads),
            "surface_count": len(surfaces),
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        },
        "terrain": terrain,
        "buildings": buildings,
        "roads": roads,
        "surfaces": surfaces,
        "trees": trees,
    }
    (ASSET_DIR / "campus_assets.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    summary = {
        "buildings": len(buildings),
        "roads": len(roads),
        "surfaces": len(surfaces),
        "trees": len(trees),
        "gf2_ndvi_threshold": threshold,
        "gf2_texture": str(ASSET_DIR / "gf2_bnu_truecolor.png"),
        "assets": str(ASSET_DIR / "campus_assets.json"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
