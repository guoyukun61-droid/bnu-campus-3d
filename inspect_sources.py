from __future__ import annotations

import json
from pathlib import Path

import rasterio
from rasterio.warp import transform_bounds


SOURCES = [
    Path(r"D:\BaiduNetdiskDownload\GF2-20250624\beijingdata2025\GF2_PMS1_E116_3_N39_9_20250624_L1A14720897001_ORTHO_PSH.tif"),
    Path(r"D:\A-newdesktop\个人\本基\历史资料外表\2026-04-11-00_00_2026-04-11-23_59_Sentinel-2_L2A_NDVI.tiff"),
    Path(r"D:\A-newdesktop\class\地理\GIS实习\S2B_MSIL2A_20260509T031539_N0512_R118_T49SFB_20260509T070803\S2B_MSIL2A_20260509T031539_N0512_R118_T49SFB_20260509T070803.SAFE\GRANULE\L2A_T49SFB_A047906_20260509T032426\IMG_DATA\R10m\T49SFB_20260509T031539_TCI_10m.jp2"),
]


def describe(path: Path) -> dict:
    result = {
        "path": str(path),
        "exists": path.exists(),
        "size_mb": round(path.stat().st_size / 1024**2, 2) if path.exists() else None,
    }
    if not path.exists():
        return result
    with rasterio.open(path) as src:
        result.update(
            driver=src.driver,
            width=src.width,
            height=src.height,
            band_count=src.count,
            dtypes=list(src.dtypes),
            crs=str(src.crs),
            bounds_native=list(src.bounds),
            bounds_wgs84=list(transform_bounds(src.crs, "EPSG:4326", *src.bounds, densify_pts=21)),
            resolution=list(src.res),
            nodata=src.nodata,
        )
    return result


if __name__ == "__main__":
    print(json.dumps([describe(path) for path in SOURCES], ensure_ascii=False, indent=2))
