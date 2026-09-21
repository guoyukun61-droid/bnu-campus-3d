from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

import bpy
from mathutils import Vector


PROJECT_DIR = Path(__file__).resolve().parent
ASSET_DIR = PROJECT_DIR / "assets"
OUTPUT_DIR = PROJECT_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
REANALYSIS = '--gf2-v5' in sys.argv
SUFFIX = '_v5' if REANALYSIS else ''
ASSETS_PATH = ASSET_DIR / ("campus_assets_v5.json" if REANALYSIS else "campus_assets.json")
TEXTURE_PATH = ASSET_DIR / ("gf2_reanalysis_v5/truecolor_utm.png" if REANALYSIS else "gf2_bnu_truecolor.png")
IMAGE2_FACADE_TEXTURES = {
    "red": ASSET_DIR / "image2_brick_surface_v4.png",
    "warm": ASSET_DIR / "image2_stone_surface_v4.png",
    "cool": ASSET_DIR / "image2_stone_surface_v4.png",
    "stone": ASSET_DIR / "image2_stone_surface_v4.png",
}
UV_EXTENT: tuple[float, float, float, float] | None = None


def reset_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.meshes, bpy.data.curves, bpy.data.materials, bpy.data.cameras, bpy.data.lights):
        for block in list(datablocks):
            if block.users == 0:
                datablocks.remove(block)


def make_principled_material(
    name: str,
    color: tuple[float, float, float, float],
    roughness: float = 0.6,
    metallic: float = 0.0,
) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    material.diffuse_color = color
    return material


def make_facade_material(
    name: str,
    wall_color: tuple[float, float, float, float],
    texture_path: Path,
) -> bpy.types.Material:
    """Image2 façade texture with a glTF-compatible base-color path."""
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    for node in nodes:
        nodes.remove(node)
    output = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    uv_map = nodes.new("ShaderNodeUVMap")
    uv_map.uv_map = "Facade_UV"
    image_node = nodes.new("ShaderNodeTexImage")
    image_node.image = bpy.data.images.load(str(texture_path), check_existing=True)
    image_node.interpolation = "Linear"
    image_node.extension = "REPEAT"
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.11
    bump.inputs["Distance"].default_value = 0.10
    bsdf.inputs["Roughness"].default_value = 0.64
    bsdf.inputs["Metallic"].default_value = 0.0
    bsdf.inputs["Base Color"].default_value = wall_color
    material.diffuse_color = wall_color
    material["texture_source"] = "Image2 window-free surface v4"
    links.new(uv_map.outputs["UV"], image_node.inputs["Vector"])
    tint = nodes.new("ShaderNodeMixRGB")
    tint.blend_type = "MULTIPLY"
    tint.inputs[0].default_value = 1.0
    tint.inputs[2].default_value = wall_color
    links.new(image_node.outputs["Color"], tint.inputs[1])
    links.new(tint.outputs[0], bsdf.inputs["Base Color"])
    links.new(image_node.outputs["Color"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    return material


def make_projected_roof_material() -> bpy.types.Material:
    """Project the georeferenced GF-2 texture onto every roof top."""
    material = bpy.data.materials.new("GF2_Projected_Roofs")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    for node in nodes:
        nodes.remove(node)
    output = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    image_node = nodes.new("ShaderNodeTexImage")
    image_node.image = bpy.data.images.load(str(TEXTURE_PATH), check_existing=True)
    image_node.interpolation = "Linear"
    uv_map = nodes.new("ShaderNodeUVMap")
    uv_map.uv_map = "Roof_Geo_UV"
    hue = nodes.new("ShaderNodeHueSaturation")
    hue.inputs["Saturation"].default_value = 1.08
    hue.inputs["Value"].default_value = 1.04
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.10
    bump.inputs["Distance"].default_value = 0.32
    bsdf.inputs["Roughness"].default_value = 0.52
    bsdf.inputs["Specular IOR Level"].default_value = 0.32
    links.new(uv_map.outputs["UV"], image_node.inputs["Vector"])
    links.new(image_node.outputs["Color"], hue.inputs["Color"])
    links.new(image_node.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(image_node.outputs["Color"], bump.inputs["Height"])
    if not REANALYSIS:
        links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    return material


def make_ground_material() -> bpy.types.Material:
    material = bpy.data.materials.new("GF2_TrueColor_Ground")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    for node in nodes:
        nodes.remove(node)
    output = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    image_node = nodes.new("ShaderNodeTexImage")
    image_node.image = bpy.data.images.load(str(TEXTURE_PATH), check_existing=True)
    image_node.interpolation = "Linear"
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.08
    bump.inputs["Distance"].default_value = 0.25
    bsdf.inputs["Roughness"].default_value = 0.72
    bsdf.inputs["Specular IOR Level"].default_value = 0.28
    links.new(image_node.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(image_node.outputs["Color"], bump.inputs["Height"])
    if not REANALYSIS:
        links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    return material


def make_terrain_mesh(data: dict, material: bpy.types.Material) -> bpy.types.Object:
    extent = data["coordinate_system"]["extent_m"]
    x_min, y_min, x_max, y_max = extent
    grid = data["terrain"]["relative_elevation_m"]
    size = data["terrain"]["size"]
    relief_scale = 0.24
    vertices = []
    uvs = []
    for row in range(size):
        v = row / (size - 1)
        y = y_min + v * (y_max - y_min)
        for col in range(size):
            u = col / (size - 1)
            x = x_min + u * (x_max - x_min)
            z = grid[row][col] * relief_scale
            vertices.append((x, y, z))
            uvs.append((u, v))
    faces = []
    for row in range(size - 1):
        for col in range(size - 1):
            a = row * size + col
            b = a + 1
            c = a + size + 1
            d = a + size
            faces.append((a, b, c, d))
    mesh = bpy.data.meshes.new("CampusTerrainMesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    uv_layer = mesh.uv_layers.new(name="GF2_UV")
    for polygon in mesh.polygons:
        for loop_index in polygon.loop_indices:
            vertex_index = mesh.loops[loop_index].vertex_index
            uv_layer.data[loop_index].uv = uvs[vertex_index]
    obj = bpy.data.objects.new("GF2_Satellite_Terrain", mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)
    return obj


def terrain_height(data: dict, x: float, y: float) -> float:
    x_min, y_min, x_max, y_max = data["coordinate_system"]["extent_m"]
    grid = data["terrain"]["relative_elevation_m"]
    size = data["terrain"]["size"]
    u = min(1.0, max(0.0, (x - x_min) / (x_max - x_min))) * (size - 1)
    v = min(1.0, max(0.0, (y - y_min) / (y_max - y_min))) * (size - 1)
    i, j = int(u), int(v)
    i1, j1 = min(i + 1, size - 1), min(j + 1, size - 1)
    fu, fv = u - i, v - j
    z00, z10 = grid[j][i], grid[j][i1]
    z01, z11 = grid[j1][i], grid[j1][i1]
    z0 = z00 * (1 - fu) + z10 * fu
    z1 = z01 * (1 - fu) + z11 * fu
    return (z0 * (1 - fv) + z1 * fv) * 0.24


def polygon_mesh(
    name: str,
    coords: list[list[float]],
    base_z: float,
    height: float,
    side_material: bpy.types.Material,
    top_material: bpy.types.Material,
    bevel: float = 0.45,
    roof_offset: tuple[float, float] = (0.0, 0.0),
) -> bpy.types.Object | None:
    if len(coords) < 3:
        return None
    n = len(coords)
    vertices = [(x, y, base_z) for x, y in coords] + [(x, y, base_z + height) for x, y in coords]
    faces = [tuple(reversed(range(n))), tuple(range(n, n * 2))]
    faces.extend((i, (i + 1) % n, (i + 1) % n + n, i + n) for i in range(n))
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    if UV_EXTENT is not None:
        x_min, y_min, x_max, y_max = UV_EXTENT
        roof_uv_layer = mesh.uv_layers.new(name="Roof_Geo_UV")
        facade_uv_layer = mesh.uv_layers.new(name="Facade_UV")
        # Adding a CustomData layer may invalidate existing RNA references.
        roof_uv_layer = mesh.uv_layers["Roof_Geo_UV"]
        facade_uv_layer = mesh.uv_layers["Facade_UV"]
        for polygon in mesh.polygons:
            for loop_index in polygon.loop_indices:
                vertex = mesh.vertices[mesh.loops[loop_index].vertex_index].co
                u = (vertex.x + roof_offset[0] - x_min) / (x_max - x_min)
                v = (vertex.y + roof_offset[1] - y_min) / (y_max - y_min)
                roof_uv_layer.data[loop_index].uv = (u, v)
                facade_uv_layer.data[loop_index].uv = (0.0, 0.0)
        for edge_index, polygon in enumerate(mesh.polygons[2:]):
            start = coords[edge_index]
            end = coords[(edge_index + 1) % n]
            edge_length = math.hypot(end[0] - start[0], end[1] - start[1])
            facade_coords = (
                (0.0, 0.0),
                (edge_length / 2.4, 0.0),
                (edge_length / 2.4, height / 2.4),
                (0.0, height / 2.4),
            )
            for loop_index, uv in zip(polygon.loop_indices, facade_coords):
                facade_uv_layer.data[loop_index].uv = uv
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(side_material)
    obj.data.materials.append(top_material)
    mesh.polygons[0].material_index = 1
    mesh.polygons[1].material_index = 1
    for polygon in mesh.polygons[2:]:
        polygon.material_index = 0
    if bevel > 0:
        modifier = obj.modifiers.new(name="SoftEdges", type="BEVEL")
        modifier.width = min(bevel, height * 0.08)
        modifier.segments = 2
    return obj


def build_buildings(data: dict, materials: dict) -> list[bpy.types.Object]:
    collection = bpy.data.collections.new("Buildings")
    bpy.context.scene.collection.children.link(collection)
    created = []
    palette = [materials["wall_warm"], materials["wall_stone"], materials["wall_red"], materials["wall_cool"]]
    for building in data["buildings"]:
        coords = building["coords"]
        cx, cy = polygon_centroid(coords)
        z = terrain_height(data, cx, cy) + 0.25
        index = int(building["osm_id"] or 0) % len(palette)
        side_material = palette[index]
        if building.get("name") and ("library" in building["name"].lower() or "图书" in building["name"]):
            side_material = materials["wall_stone"]
        observation = building.get('gf2_observation', {})
        offset = observation.get('roof_sampling_offset') or {}
        if REANALYSIS:
            side_material = materials['unobserved_wall']
        ref = building.get('reference_observation')
        if ref:
            side_material = materials[ref['style']]
        obj = polygon_mesh(
            f"Building_{building['osm_id']}",
            coords,
            z,
            building["height"],
            side_material,
            materials[ref['roof_material']] if ref else materials["roof"],
            roof_offset=(offset.get('dx_m', 0.0), offset.get('dy_m', 0.0)),
        )
        if obj is None:
            continue
        for old_collection in list(obj.users_collection):
            old_collection.objects.unlink(obj)
        collection.objects.link(obj)
        obj["osm_id"] = building["osm_id"]
        obj["building_name"] = building.get("name", "")
        obj["height_m"] = building["height"]
        obj["floors_estimated"] = building["floors"]
        if REANALYSIS:
            obj['roof_observation'] = json.dumps(observation, ensure_ascii=False)
            obj['facade_source'] = 'unobserved neutral placeholder; not classified from rooftop'
        if ref:
            obj['facade_source'] = 'single user diagram interpretation; hidden faces extrapolated'
            obj['reference_observation'] = json.dumps(ref, ensure_ascii=False)
        created.append(obj)
    return created


def polygon_signed_area(coords: list[list[float]]) -> float:
    return 0.5 * sum(
        coords[i][0] * coords[(i + 1) % len(coords)][1]
        - coords[(i + 1) % len(coords)][0] * coords[i][1]
        for i in range(len(coords))
    )


def polygon_centroid(coords: list[list[float]]) -> tuple[float, float]:
    area6 = 6.0 * polygon_signed_area(coords)
    if abs(area6) < 1e-8:
        return (
            sum(point[0] for point in coords) / len(coords),
            sum(point[1] for point in coords) / len(coords),
        )
    cx = cy = 0.0
    for index, point in enumerate(coords):
        next_point = coords[(index + 1) % len(coords)]
        cross = point[0] * next_point[1] - next_point[0] * point[1]
        cx += (point[0] + next_point[0]) * cross
        cy += (point[1] + next_point[1]) * cross
    return cx / area6, cy / area6


def append_box(vertices, faces, center_x, center_y, z0, size_x, size_y, height):
    base = len(vertices)
    x0, x1 = center_x - size_x / 2, center_x + size_x / 2
    y0, y1 = center_y - size_y / 2, center_y + size_y / 2
    z1 = z0 + height
    vertices.extend(
        [
            (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
            (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
        ]
    )
    faces.extend(
        [
            (base, base + 3, base + 2, base + 1),
            (base + 4, base + 5, base + 6, base + 7),
            (base, base + 1, base + 5, base + 4),
            (base + 1, base + 2, base + 6, base + 5),
            (base + 2, base + 3, base + 7, base + 6),
            (base + 3, base, base + 4, base + 7),
        ]
    )


def build_building_details(data: dict, materials: dict) -> dict[str, int]:
    """Add export-safe rule-based LOD1.5 facade and roof details."""
    collection = bpy.data.collections.new("Building_Details")
    bpy.context.scene.collection.children.link(collection)
    window_vertices, window_faces = [], []
    frame_vertices, frame_faces = [], []
    parapet_vertices, parapet_faces = [], []
    equipment_vertices, equipment_faces = [], []
    window_count = parapet_count = equipment_count = 0

    for building in data["buildings"]:
        if building.get('reference_observation'):
            continue  # The reference variant supplies its own facade geometry.
        coords = building["coords"]
        if len(coords) < 3:
            continue
        cx, cy = polygon_centroid(coords)
        base_z = terrain_height(data, cx, cy) + 0.25
        height = float(building["height"])
        top_z = base_z + height
        floors = max(1, int(building.get("floors") or round(height / 3.4)))
        floor_height = height / floors
        orientation = 1.0 if polygon_signed_area(coords) >= 0 else -1.0

        for edge_index, start in enumerate(coords):
            end = coords[(edge_index + 1) % len(coords)]
            dx, dy = end[0] - start[0], end[1] - start[1]
            length = math.hypot(dx, dy)
            if length < 2.8:
                continue
            ux, uy = dx / length, dy / length
            nx, ny = orientation * dy / length, -orientation * dx / length
            pbase = len(parapet_vertices)
            parapet_vertices.extend(
                [
                    (start[0], start[1], top_z), (end[0], end[1], top_z),
                    (end[0], end[1], top_z + 0.62), (start[0], start[1], top_z + 0.62),
                ]
            )
            parapet_faces.append((pbase, pbase + 1, pbase + 2, pbase + 3))
            parapet_count += 1

            margin = min(1.1, length * 0.16)
            usable = length - 2 * margin
            if usable < 1.2:
                continue
            columns = max(1, min(26, int(usable / 2.85)))
            cell = usable / columns
            panel_width = min(2.05, cell * 0.72)
            for floor in range(floors):
                z0 = base_z + floor * floor_height + floor_height * 0.31
                z1 = base_z + floor * floor_height + floor_height * 0.73
                if z1 - z0 < 0.55:
                    continue
                for column in range(columns):
                    center_distance = margin + cell * (column + 0.5)
                    half = panel_width / 2
                    a_distance, b_distance = center_distance - half, center_distance + half
                    offset = 0.075
                    ax = start[0] + ux * a_distance + nx * offset
                    ay = start[1] + uy * a_distance + ny * offset
                    bx = start[0] + ux * b_distance + nx * offset
                    by = start[1] + uy * b_distance + ny * offset
                    base = len(window_vertices)
                    window_vertices.extend([(ax, ay, z0), (bx, by, z0), (bx, by, z1), (ax, ay, z1)])
                    window_faces.append((base, base + 1, base + 2, base + 3))
                    # Raised perimeter and center mullion share the glass layout.
                    def point(distance, z, depth):
                        return (start[0] + ux * distance + nx * depth,
                                start[1] + uy * distance + ny * depth, z)
                    fbase = len(frame_vertices)
                    frame_vertices.extend([
                        point(a_distance-.09,z0-.09,.16), point(b_distance+.09,z0-.09,.16),
                        point(b_distance+.09,z1+.09,.16), point(a_distance-.09,z1+.09,.16),
                        point(a_distance,z0,.085), point(b_distance,z0,.085),
                        point(b_distance,z1,.085), point(a_distance,z1,.085),
                        point(center_distance-.035,z0,.13), point(center_distance+.035,z0,.13),
                        point(center_distance+.035,z1,.13), point(center_distance-.035,z1,.13),
                    ])
                    for face in [(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7),(8,9,10,11)]:
                        frame_faces.append(tuple(fbase+i for i in face))
                    window_count += 1

        if not REANALYSIS and float(building.get("area") or 0) >= 360 and height >= 7:
            xs = [point[0] for point in coords]
            ys = [point[1] for point in coords]
            box_x = min(7.0, max(2.4, (max(xs) - min(xs)) * 0.13))
            box_y = min(6.0, max(2.1, (max(ys) - min(ys)) * 0.13))
            box_height = 1.15 + (int(building["osm_id"]) % 4) * 0.22
            append_box(equipment_vertices, equipment_faces, cx, cy, top_z + 0.08, box_x, box_y, box_height)
            equipment_count += 1

    detail_specs = [
        ("Facade_Window_Panels", window_vertices, window_faces, materials["windows"]),
        ("Facade_Window_Frames", frame_vertices, frame_faces, materials["frames"]),
        ("Roof_Parapets", parapet_vertices, parapet_faces, materials["parapet"]),
        ("Rooftop_Equipment", equipment_vertices, equipment_faces, materials["equipment"]),
    ]
    for name, vertices, faces, material in detail_specs:
        mesh = bpy.data.meshes.new(f"{name}_mesh")
        mesh.from_pydata(vertices, [], faces)
        mesh.validate(verbose=False)
        mesh.update()
        obj = bpy.data.objects.new(name, mesh)
        collection.objects.link(obj)
        obj.data.materials.append(material)
        obj["detail_level"] = "rule_based_lod1_5"

    return {"windows": window_count, "parapets": parapet_count, "rooftop_units": equipment_count}


def make_curve_object(
    name: str,
    coords: list[list[float]],
    z: float,
    width: float,
    material: bpy.types.Material,
    collection: bpy.types.Collection,
) -> bpy.types.Object:
    curve_data = bpy.data.curves.new(name=f"{name}_curve", type="CURVE")
    curve_data.dimensions = "3D"
    curve_data.resolution_u = 1
    curve_data.bevel_resolution = 0
    curve_data.bevel_depth = width / 2
    spline = curve_data.splines.new("POLY")
    spline.points.add(len(coords) - 1)
    for point, (x, y) in zip(spline.points, coords):
        point.co = (x, y, z, 1.0)
    obj = bpy.data.objects.new(name, curve_data)
    collection.objects.link(obj)
    obj.data.materials.append(material)
    return obj


def build_roads(data: dict, materials: dict) -> int:
    collection = bpy.data.collections.new("Road_Accents")
    bpy.context.scene.collection.children.link(collection)
    count = 0
    x_min, y_min, x_max, y_max = data["coordinate_system"]["extent_m"]
    for road in data["roads"]:
        kind = road["kind"]
        if kind not in {"footway", "path", "cycleway", "pedestrian"}:
            continue
        coords = road["coords"]
        if any(x < x_min - 8 or x > x_max + 8 or y < y_min - 8 or y > y_max + 8 for x, y in coords):
            continue
        cx = sum(p[0] for p in coords) / len(coords)
        cy = sum(p[1] for p in coords) / len(coords)
        z = terrain_height(data, cx, cy) + 0.18
        make_curve_object(
            f"Path_{road['osm_id']}", coords, z, min(road["width"], 2.0), materials["path"], collection
        )
        count += 1
    return count


def build_surfaces(data: dict, materials: dict) -> int:
    collection = bpy.data.collections.new("Campus_Surfaces")
    bpy.context.scene.collection.children.link(collection)
    count = 0
    for surface in data["surfaces"]:
        # The GF-2 texture contains track lanes and court markings at higher
        # visual fidelity than a flat OSM pitch polygon, so leave pitches exposed.
        if surface["kind"] == "pitch":
            continue
        coords = surface["coords"]
        cx = sum(p[0] for p in coords) / len(coords)
        cy = sum(p[1] for p in coords) / len(coords)
        z = terrain_height(data, cx, cy) + 0.2
        mat = materials[surface["kind"]]
        obj = polygon_mesh(f"Surface_{surface['osm_id']}", coords, z, 0.12, mat, mat, bevel=0.0)
        if obj:
            for old_collection in list(obj.users_collection):
                old_collection.objects.unlink(obj)
            collection.objects.link(obj)
            count += 1
    return count


def add_cylinder_geometry(vertices, faces, mats, x, y, z0, radius, height, sides, material_index):
    base = len(vertices)
    vertices.extend((x + radius * math.cos(2 * math.pi * i / sides), y + radius * math.sin(2 * math.pi * i / sides), z0) for i in range(sides))
    vertices.extend((x + radius * math.cos(2 * math.pi * i / sides), y + radius * math.sin(2 * math.pi * i / sides), z0 + height) for i in range(sides))
    faces.append(tuple(base + i for i in reversed(range(sides))))
    mats.append(material_index)
    faces.append(tuple(base + sides + i for i in range(sides)))
    mats.append(material_index)
    for i in range(sides):
        faces.append((base + i, base + (i + 1) % sides, base + sides + (i + 1) % sides, base + sides + i))
        mats.append(material_index)


def add_canopy_geometry(vertices, faces, mats, x, y, z, radius, height, sides, material_index):
    base = len(vertices)
    vertices.append((x, y, z + height * 0.62))
    top_index = base
    rings = [
        (z - height * 0.24, radius * 0.55),
        (z, radius),
        (z + height * 0.32, radius * 0.68),
    ]
    for rz, rr in rings:
        vertices.extend((x + rr * math.cos(2 * math.pi * i / sides), y + rr * math.sin(2 * math.pi * i / sides), rz) for i in range(sides))
    bottom_center = len(vertices)
    vertices.append((x, y, z - height * 0.42))
    for ring in range(2):
        start_a = base + 1 + ring * sides
        start_b = start_a + sides
        for i in range(sides):
            faces.append((start_a + i, start_a + (i + 1) % sides, start_b + (i + 1) % sides, start_b + i))
            mats.append(material_index)
    last_ring = base + 1 + 2 * sides
    first_ring = base + 1
    for i in range(sides):
        faces.append((last_ring + i, last_ring + (i + 1) % sides, top_index))
        mats.append(material_index)
        faces.append((bottom_center, first_ring + (i + 1) % sides, first_ring + i))
        mats.append(material_index)


def build_trees(data: dict, materials: dict) -> bpy.types.Object:
    random.seed(20260831)
    vertices, faces, face_materials = [], [], []
    for index, tree in enumerate(data["trees"]):
        x, y = tree["x"], tree["y"]
        ground = terrain_height(data, x, y) + 0.12
        total_height = tree["height"] * random.uniform(0.86, 1.14)
        crown_radius = tree["crown_radius"] * random.uniform(0.68, 0.92)
        trunk_height = total_height * 0.42
        add_cylinder_geometry(vertices, faces, face_materials, x, y, ground, max(0.22, crown_radius * 0.11), trunk_height, 7, 0)
        foliage_index = 1 + (index % 3)
        add_canopy_geometry(vertices, faces, face_materials, x, y, ground + trunk_height + total_height * 0.18, crown_radius, total_height * 0.58, 8, foliage_index)
    mesh = bpy.data.meshes.new("GF2_Derived_Tree_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("GF2_NDVI_Trees", mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(materials["trunk"])
    obj.data.materials.append(materials["leaf_1"])
    obj.data.materials.append(materials["leaf_2"])
    obj.data.materials.append(materials["leaf_3"])
    for polygon, material_index in zip(mesh.polygons, face_materials):
        polygon.material_index = material_index
        polygon.use_smooth = material_index > 0
    obj["source"] = data['vegetation']['method']
    obj["tree_count"] = len(data["trees"])
    return obj


def make_base(data: dict, materials: dict) -> None:
    x_min, y_min, x_max, y_max = data["coordinate_system"]["extent_m"]
    width, height = x_max - x_min, y_max - y_min
    bpy.ops.mesh.primitive_cube_add(location=((x_min + x_max) / 2, (y_min + y_max) / 2, -9.0))
    base = bpy.context.object
    base.name = "Presentation_Base"
    base.scale = (width / 2 + 18, height / 2 + 18, 8.0)
    base.data.materials.append(materials["base"])
    bevel = base.modifiers.new("BaseBevel", "BEVEL")
    bevel.width = 5.0
    bevel.segments = 3


def look_at(obj: bpy.types.Object, target: tuple[float, float, float]) -> None:
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def add_camera(name: str, location: tuple[float, float, float], target, ortho_scale: float) -> bpy.types.Object:
    camera_data = bpy.data.cameras.new(name)
    camera = bpy.data.objects.new(name, camera_data)
    bpy.context.collection.objects.link(camera)
    camera.location = location
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = ortho_scale
    camera.data.lens = 55
    camera.data.clip_start = 0.5
    camera.data.clip_end = 10000.0
    look_at(camera, target)
    return camera


def setup_lighting() -> None:
    world = bpy.context.scene.world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.45, 0.55, 0.65, 1.0)
    background.inputs["Strength"].default_value = 0.8

    sun_data = bpy.data.lights.new("Late_Afternoon_Sun", type="SUN")
    sun_data.energy = 2.7
    sun_data.angle = math.radians(18)
    sun = bpy.data.objects.new("Late_Afternoon_Sun", sun_data)
    bpy.context.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(32), math.radians(-20), math.radians(-38))

    area_data = bpy.data.lights.new("Sky_Fill", type="AREA")
    area_data.energy = 1200
    area_data.shape = "DISK"
    area_data.size = 1400
    area = bpy.data.objects.new("Sky_Fill", area_data)
    bpy.context.collection.objects.link(area)
    area.location = (-500, -200, 1300)
    look_at(area, (0, 0, 0))


def setup_scene() -> None:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = False
    scene.render.resolution_percentage = 100
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.image_settings.color_depth = "8"
    scene.view_settings.look = "AgX - Medium Low Contrast"
    scene.render.filepath = str(OUTPUT_DIR / f"bnu_campus_hero{SUFFIX}.png")
    scene.camera.data.dof.use_dof = False


def create_materials() -> dict:
    return {
        "unobserved_wall": make_facade_material("Facade_Unobserved_Neutral", (.76,.72,.64,1), IMAGE2_FACADE_TEXTURES['stone']),
        "ground": make_ground_material(),
        "base": make_principled_material("MapBase", (0.025, 0.033, 0.045, 1), 0.5, 0.18),
        "wall_warm": make_facade_material("CampusWarmFacade", (0.85, 0.68, 0.47, 1), IMAGE2_FACADE_TEXTURES["warm"]),
        "wall_stone": make_facade_material("CampusStoneFacade", (0.90, 0.90, 0.87, 1), IMAGE2_FACADE_TEXTURES["stone"]),
        "wall_red": make_facade_material("CampusRedBrick", (0.92, 0.83, 0.78, 1), IMAGE2_FACADE_TEXTURES["red"]),
        "wall_cool": make_facade_material("CampusCoolFacade", (0.66, 0.75, 0.80, 1), IMAGE2_FACADE_TEXTURES["cool"]),
        "roof": make_projected_roof_material(),
        "windows": make_principled_material("FacadeGlass", (0.075, 0.16, 0.22, 1), 0.32, 0.05),
        "frames": make_principled_material("FacadeWindowFrames", (0.48, 0.50, 0.49, 1), 0.48, 0.18),
        "parapet": make_principled_material("RoofParapet", (0.34, 0.31, 0.27, 1), 0.76),
        "equipment": make_principled_material("RooftopEquipment", (0.19, 0.23, 0.23, 1), 0.62, 0.06),
        "path": make_principled_material("Footpaths", (0.42, 0.40, 0.36, 1), 0.86),
        "pitch": make_principled_material("SportsPitch", (0.075, 0.32, 0.16, 1), 0.82),
        "grass": make_principled_material("Grass", (0.11, 0.31, 0.13, 1), 0.9),
        "water": make_principled_material("Water", (0.04, 0.27, 0.40, 1), 0.22, 0.08),
        "trunk": make_principled_material("TreeTrunks", (0.15, 0.07, 0.025, 1), 0.92),
        "leaf_1": make_principled_material("LeavesDeep", (0.035, 0.095, 0.025, 1) if REANALYSIS else (0.025, 0.22, 0.075, 1), 0.78),
        "leaf_2": make_principled_material("LeavesMid", (0.07, 0.16, 0.045, 1) if REANALYSIS else (0.055, 0.34, 0.10, 1), 0.8),
        "leaf_3": make_principled_material("LeavesLight", (0.13, 0.22, 0.06, 1) if REANALYSIS else (0.14, 0.42, 0.12, 1), 0.82),
    }


def render_views(hero_camera: bpy.types.Object, top_camera: bpy.types.Object) -> None:
    scene = bpy.context.scene
    scene.camera = hero_camera
    setup_scene()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT_DIR / f"bnu_campus_gf2_sentinel2{SUFFIX}.blend"))
    bpy.ops.render.render(write_still=True)

    scene.camera = top_camera
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 1600
    scene.render.filepath = str(OUTPUT_DIR / f"bnu_campus_top{SUFFIX}.png")
    bpy.ops.render.render(write_still=True)
    scene.camera = hero_camera
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.filepath = str(OUTPUT_DIR / f"bnu_campus_hero{SUFFIX}.png")
    bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT_DIR / f"bnu_campus_gf2_sentinel2{SUFFIX}.blend"))


def main() -> None:
    global UV_EXTENT
    reset_scene()
    data = json.loads(ASSETS_PATH.read_text(encoding="utf-8"))
    for item in data["buildings"] + data["surfaces"]:
        clean = []
        for p in item["coords"]:
            if not clean or math.dist(p, clean[-1]) > .001:
                clean.append(p)
        if len(clean) > 2 and math.dist(clean[0], clean[-1]) < .001:
            clean.pop()
        if polygon_signed_area(clean) < 0:
            clean.reverse()
        item["coords"] = clean
    UV_EXTENT = tuple(data["coordinate_system"]["extent_m"])
    materials = create_materials()
    make_base(data, materials)
    make_terrain_mesh(data, materials["ground"])
    buildings = build_buildings(data, materials)
    building_details = build_building_details(data, materials)
    path_count = build_roads(data, materials)
    surface_count = build_surfaces(data, materials)
    build_trees(data, materials)
    setup_lighting()
    x_min, y_min, x_max, y_max = data["coordinate_system"]["extent_m"]
    width, depth = x_max - x_min, y_max - y_min
    span = max(width, depth)
    hero_camera = add_camera(
        "HeroCamera",
        (span * 0.92, -span * 1.08, span * 0.88),
        (-20, 30, 10),
        span * 1.28,
    )
    top_camera = add_camera("TopCamera", (0, 0, span * 2.2), (0, 0, 0), span * 1.04)
    bpy.context.scene.camera = hero_camera
    render_views(hero_camera, top_camera)
    print(
        json.dumps(
            {
                "buildings": len(buildings),
                "building_details": building_details,
                "paths": path_count,
                "surfaces": surface_count,
                "trees": len(data["trees"]),
                "blend": str(OUTPUT_DIR / f"bnu_campus_gf2_sentinel2{SUFFIX}.blend"),
                "hero": str(OUTPUT_DIR / f"bnu_campus_hero{SUFFIX}.png"),
                "top": str(OUTPUT_DIR / f"bnu_campus_top{SUFFIX}.png"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
