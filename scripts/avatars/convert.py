"""Convert one Rocketbox character to a web-ready GLB (run by Blender, unattended).

blender --background --factory-startup --python convert.py -- <fbx> <textures dir> <out.glb> <texture px> <report.json>

Keeps the 15 Oculus visemes and 52 ARKit blendshapes under their standard names, drops the
other shape keys, shrinks textures, makes the materials non-metallic, and exports with the
skeleton and textures unchanged.
"""

import json
import os
import re
import sys

import bpy

fbx, textures, out, size, report_path = sys.argv[sys.argv.index("--") + 1 :]
size = int(size)


def standard_name(key: str) -> str | None:
    match = re.match(r"^(?:blendShape1\.)?AA_VI_\d+_(\w+)$", key)
    if match:
        return "viseme_" + {"Sil": "sil", "KK": "kk"}.get(match.group(1), match.group(1))
    match = re.match(r"^(?:blendShape1\.)?AK_\d+_(\w+)$", key)
    if match:
        return match.group(1)[0].lower() + match.group(1)[1:]
    return None


bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=fbx, use_image_search=True)

# The FBX names its textures; they live in the character's Textures folder.
missing = []
for image in bpy.data.images:
    if image.source != "FILE":
        continue
    # Paths in the FBX come from the artist's Windows machine: split on either separator.
    candidate = os.path.join(textures, re.split(r"[\\/]", image.filepath)[-1])
    if os.path.exists(candidate):
        image.filepath = candidate
        image.reload()
    # Images load lazily; reading the size forces the load.
    if not image.size[0]:
        missing.append(image.name)
if missing:
    sys.exit(f"Textures not found: {missing}")

kept, dropped = [], 0
for obj in bpy.data.objects:
    keys = obj.data.shape_keys if obj.type == "MESH" else None
    if not keys:
        continue
    for block in list(keys.key_blocks):
        if block == keys.reference_key:
            continue
        name = standard_name(block.name)
        if name is None:
            obj.shape_key_remove(block)
            dropped += 1
        else:
            block.name = name
            kept.append(name)

# The FBX importer maps the 3ds Max materials' reflection to Metallic 1, which renders skin
# as dark, patchy metal; nothing in these characters is metal.
for material in bpy.data.materials:
    if not material.use_nodes:
        continue
    for node in material.node_tree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            metallic = node.inputs["Metallic"]
            for link in list(metallic.links):
                material.node_tree.links.remove(link)
            metallic.default_value = 0.0

for image in bpy.data.images:
    if image.size[0] > size or image.size[1] > size:
        image.scale(size, size)

bpy.ops.export_scene.gltf(
    filepath=out,
    export_format="GLB",
    export_skins=True,
    export_morph=True,
    export_morph_normal=False,
    export_image_format="AUTO",
)
bones = [b.name for o in bpy.data.objects if o.type == "ARMATURE" for b in o.data.bones]
with open(report_path, "w") as handle:
    json.dump(
        {
            "shape_keys": sorted(set(kept)),
            "dropped_shape_keys": dropped,
            "bones": bones,
            "materials": [m.name for m in bpy.data.materials],
            "metallic": sorted(
                {
                    n.inputs["Metallic"].default_value
                    for m in bpy.data.materials
                    if m.use_nodes
                    for n in m.node_tree.nodes
                    if n.type == "BSDF_PRINCIPLED"
                }
            ),
            "images": sorted({re.split(r"[\\/]", i.filepath)[-1] for i in bpy.data.images if i.size[0]}),
            "bytes": os.path.getsize(out),
        },
        handle,
        indent=2,
    )
