from re import I


bl_info = {
    "name" : "Retopology - Easy Meshes",
    "description" : "Easy retopology",
    "author" : "Kroket Ltd.",
    "version" : (0, 0, 1),
    "blender" : (3, 60, 0),
    "location" : "View3D",
    "warning" : "",
    "support" : "COMMUNITY",
    "doc_url" : "",
    "category" : "3D View"
}

from dataclasses import dataclass
import bpy, addon_utils, os, textwrap, tempfile, shutil, subprocess
from bpy.props import StringProperty, BoolProperty, IntProperty, FloatProperty, FloatVectorProperty, EnumProperty, PointerProperty, EnumProperty
from bpy.types import Panel, Menu, Operator, PropertyGroup

@dataclass
class Ctx:
    from_obj: bpy.types.Object = None
    to_obj: bpy.types.Object = None

ctx = Ctx()

def _print(msg):
    print(f"InstantLowPolyBake: {msg}")

def get_addon_path():
    mods = addon_utils.modules()
    for mod in mods:
        if "retopology-easy" in mod.__file__:
            return os.path.dirname(mod.__file__)
    self.report({'ERROR'}, "error detecting addon path")

def toggle_shading(object):
    if not object:
        return
    if not object.type == 'MESH':
        return
    if not object.data:
        return
    polygons = object.data.polygons
    for polygon in polygons:
        polygon.use_smooth = not polygon.use_smooth
    object.data.update()

def object_exists(obj):
    try:
        obj.name
        return True
    except:
        return False

PATH_ADDON = get_addon_path()
#PATH_ADDON = "/home/dsc/PycharmProjects/blender-retopology-for-lazy-artists"

if os.name == 'nt':
    PATH_INSTANT_MESHES = os.path.join(PATH_ADDON, "Instant Meshes.exe")
else:
    PATH_INSTANT_MESHES = os.path.join(PATH_ADDON, "Instant Meshes")


class MY_PG_SceneProperties(PropertyGroup):
    # use an annotation
    boundaries: BoolProperty(
        name="Align to boundaries",
        description="only applies when the mesh is not closed",
        default = False
        )

    target_vertex_count: IntProperty(
        name = "Target vertex count",
        description="Desired vertex count of the output mesh. In most cases, this number is a lie. It generally never gets to this target, but at least you can control the resulting vertex count this way.",
        default = 800,
        min = 100,
        max = 25000
        )

    bake_extrusion: FloatProperty(
        name = "Bake extrusion",
        description="In meters, fixes bad baking results. Increase this value if your model is big in terms of object dimensions",
        default = 30,
        min = 0.0,
        max = 200.0
        )

    merge_by_distance: BoolProperty(
        name="Merge by distance",
        description="Object cleanup, produces better results. Does not modify the original model",
        default = True
        )

    bake_diffuse_dimension: EnumProperty(
        items=(
            ("A", "512", "512x512"),
            ("B", "1024", "1024x1024"),
            ("C", "2048", "2048x2048"),
            ("D", "4096", "4096x4096")
        ),
        name="Diffuse",
        default="B",
        description="Size of the lowpoly diffuse material",
    )


# @TODO: dunno how to fetch values from a combobox, nor do I care to find out, lets do this lookup instead
bake_diffuse_dimensions_lookup = {
    "A": 512,
    "B": 1024,
    "C": 2048,
    "D": 4096
}


class HelloWorld(Panel):
    bl_idname = "OBJECT_PT_lowpolybake"
    bl_label = "LowPolyBake"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_context = "objectmode"
    bl_category = "LowPolyBake"

    def draw(self, context):
        layout = self.layout

        layout.label(text="Select your mesh and click generate")

        scene = context.scene
        g = scene.g
        layout.row(align=True) 
        layout.label(text="- Mesh")
        layout.prop(g, "target_vertex_count")
        layout.prop(g, "boundaries")
        layout.row(align=True)
        layout.label(text="- Blender")
        layout.prop(g, "bake_diffuse_dimension")
        layout.prop(g, "merge_by_distance")
        layout.prop(g, "bake_extrusion")
        layout.row(align=True)
        layout.label(text="- Actions")
        col = layout.column(align=True)
        col.operator(GenLowPoly.bl_idname, text="Generate lowpoly", icon="MESH_DATA")
        col = layout.column(align=True)
        col.operator(GenBake.bl_idname, text="(re)Bake", icon="OBJECT_DATA")


class GenBake(bpy.types.Operator):
    bl_idname = "wm.genbake"
    bl_label = "Minimal Operator"

    def execute(self, context):
        rtn = lambda: {'FINISHED'}

        # user params
        g = context.scene.g
        extrusion = float(g.bake_extrusion)
        diffuse_dimension = bake_diffuse_dimensions_lookup[str(g.bake_diffuse_dimension)]

        if not object_exists(ctx.to_obj):
            self.report({'ERROR'}, "target object does not exist (anymore?). Re-do your lowpoly generation")
            return rtn()
        if not object_exists(ctx.from_obj):
            self.report({'ERROR'}, "source object does not exist (anymore?). Re-do your lowpoly generation")
            return rtn()

        _print(f"bake: dimensions: {diffuse_dimension}, extrusion: {extrusion}")
        bpy.ops.object.select_all(action='DESELECT')
        bpy.context.scene.render.engine = 'CYCLES'
        ctx.to_obj.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT')
        ctx.from_obj.select_set(True)

        bpy.ops.object.bake(
            type="DIFFUSE",
            width=diffuse_dimension,
            height=diffuse_dimension,
            use_selected_to_active=True,
            cage_extrusion=extrusion,
            pass_filter={"COLOR"})


class GenLowPoly(bpy.types.Operator):
    bl_idname = "wm.genlowpoly"
    bl_label = "Minimal Operator"

    def execute(self, context):
        rtn = lambda: {'FINISHED'}
        if context.object.type != "MESH":
            self.report({'ERROR'}, "Select a MESH")
            return rtn()

        if not os.path.exists(PATH_INSTANT_MESHES):
            self.report({'ERROR'}, f"Path does not exist: {PATH_INSTANT_MESHES}")
            return rtn()

        ctx.from_obj = context.object
        g = context.scene.g
        diffuse_dimension = bake_diffuse_dimensions_lookup[str(g.bake_diffuse_dimension)]

        # user params
        target_vertex_count = str(g.target_vertex_count)

        _print("create tmp dir")
        path_tmp = tempfile.mkdtemp()
        path_highpoly = os.path.join(path_tmp, "highpoly.obj")
        path_lowpoly = os.path.join(path_tmp, "lowpoly.obj")
        highpoly_tmp = None

        if g.merge_by_distance:
            _print("create tmp object")
            highpoly_tmp = ctx.from_obj.copy()
            highpoly_tmp.data = ctx.from_obj.data.copy()
            highpoly_tmp.animation_data_clear()
            bpy.context.collection.objects.link(highpoly_tmp)

            _print("cleanup: merge by distance")
            bpy.ops.object.select_all(action='DESELECT')
            highpoly_tmp.select_set(True)
            bpy.context.view_layer.objects.active = highpoly_tmp
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.mesh.remove_doubles(threshold=0.0001, use_unselected=False, use_sharp_edge_from_normals=False)
            bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.select_all(action='DESELECT')

            highpoly_tmp.select_set(True)
        else:
            bpy.ops.object.select_all(action='DESELECT')
            ctx.from_obj.select_set(True)

        _print(f"export highpoly to {path_highpoly}")

        export_args = {
            "filepath": path_highpoly,
        }

        if not bpy.app.version_string.startswith("3"):
            # 4 and above
            bpy.ops.wm.obj_export(
                filepath=path_highpoly,
                export_uv=False,
                export_materials=False,
                export_selected_objects=True
            )
        else:
            bpy.ops.export_scene.obj(
                filepath=path_highpoly,
                use_selection=True,
                use_materials=False)

        if g.merge_by_distance:
            _print("remove tmp object")
            highpoly_tmp.select_set(True)
            bpy.ops.object.delete()
            bpy.ops.object.select_all(action='DESELECT')

        args = [PATH_INSTANT_MESHES, path_highpoly,
                "--vertices", target_vertex_count,
                "--output", path_lowpoly,
                "--deterministic"]
        boundaries = False
        if boundaries:
            args.append("--boundaries")

        try:
            _print(f"starting instant meshes: {' '.join(args)}")
            res = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        except Exception as ex:
            self.report({'ERROR'}, f"Something went wrong trying to start {PATH_INSTANT_MESHES}; {str(ex)}")
            return rtn()

        exitcode = res.returncode
        if exitcode != 0:
           self.report({'ERROR'}, f"Instant Meshes reported a faulty exitcode, something went wrong: {res.stdout}")

        _print("import lowpoly")
        bpy.ops.wm.obj_import(filepath=path_lowpoly)
        ctx.to_obj = bpy.context.object
        ctx.to_obj.name = ctx.from_obj.name + "_lowpoly"
        toggle_shading(ctx.to_obj)

        _print("low poly diffuse image")
        lowpoly_image = bpy.data.images.new("lowpoly", width=diffuse_dimension, height=diffuse_dimension)
        bpy.ops.object.select_all(action='DESELECT')

        _print("low poly smart UV project")
        ctx.to_obj.select_set(True)
        bpy.context.view_layer.objects.active = ctx.to_obj
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.smart_project()
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')

        _print("low poly material")
        lowpoly_mat = bpy.data.materials.new(name="Material")
        lowpoly_mat.use_nodes = True

        _print("low poly material, assign to model")
        ctx.to_obj.data.materials.append(lowpoly_mat)

        _print("low poly material, set diffuse image to Base Color")
        node_tex = lowpoly_mat.node_tree.nodes.new("ShaderNodeTexImage")
        node_tex.location = [-300, 300]
        node_tex.image = lowpoly_image
        links = lowpoly_mat.node_tree.links
        links.new(node_tex.outputs[0], lowpoly_mat.node_tree.nodes[0].inputs["Base Color"])

        shutil.rmtree(path_tmp)

        self.report({'INFO'}, "done")
        return rtn()


classes = [
    HelloWorld,
    MY_PG_SceneProperties,
    GenLowPoly,
    GenBake
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.g = PointerProperty(type=MY_PG_SceneProperties)

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
    # @TODO: del

if __name__ == '__main__':
    register()

