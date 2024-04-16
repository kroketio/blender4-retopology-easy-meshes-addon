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

import bpy, addon_utils, os, textwrap, tempfile, shutil, subprocess
from bpy.props import StringProperty, BoolProperty, IntProperty, FloatProperty, FloatVectorProperty, EnumProperty, PointerProperty
from bpy.types import Panel, Menu, Operator, PropertyGroup

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
        description="Desired vertex count of the output mesh",
        default = 800,
        min = 100,
        max = 50000
        )


class WM_OT_HelloWorld(Panel):
    bl_idname = "OBJECT_PT_lowpolybake"
    bl_label = "LowPolyBake"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_context = "objectmode"
    bl_category = "LowPolyBake"

    def draw(self, context):
        layout = self.layout

        # wrapp = textwrap.TextWrapper(width=30)
        # wList = wrapp.wrap(text="Select your mesh and click generate")
        # for text in wList:
        #     row = layout.row(align=True)
        #     row.alignment = 'EXPAND'
        #     row.label(text=text)
        layout.label(text="Select your mesh and click generate")

        scene = context.scene
        mytool = scene.my_tool
        layout.prop(mytool, "target_vertex_count")
        layout.prop(mytool, "boundaries")

        col = layout.column(align=True)
        col.operator(WM_OT_DoWork.bl_idname, text="Generate lowpoly", icon="MESH_DATA")


class WM_OT_DoWork(bpy.types.Operator):
    bl_idname = "wm.dowork"
    bl_label = "Minimal Operator"

    # def draw(self, context): # Draw options (typically displayed in the tool-bar)
    #     row = self.layout
    #     row.prop(self, "report_flag", text="Report Hello World")

    def execute(self, context):
        rtn = lambda: {'FINISHED'}
        if context.object.type != "MESH":
            self.report({'ERROR'}, "Select a MESH")
            return rtn()

        if not os.path.exists(PATH_INSTANT_MESHES):
            self.report({'ERROR'}, f"Path does not exist: {PATH_INSTANT_MESHES}")
            return rtn()

        highpoly = context.object

        _print("create tmp dir")
        path_tmp = tempfile.mkdtemp()
        path_highpoly = os.path.join(path_tmp, "highpoly.obj")
        path_lowpoly = os.path.join(path_tmp, "lowpoly.obj")

        _print("create tmp object")
        highpoly_tmp = highpoly.copy()
        highpoly_tmp.data = highpoly.data.copy()
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

        _print(f"export highpoly to {path_highpoly}")
        bpy.ops.export_scene.obj(
            filepath=path_highpoly,
            use_selection=True,
            use_materials=False  # UVs get destroyed anyway
        )

        _print("remove tmp object")
        highpoly_tmp.select_set(True)
        bpy.ops.object.delete()
        bpy.ops.object.select_all(action='DESELECT')

        args = [PATH_INSTANT_MESHES, path_highpoly, "--vertices", "800", "--output", path_lowpoly]
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
        lowpoly = bpy.context.object
        lowpoly.name = highpoly.name + "_lowpoly"
        toggle_shading(lowpoly)

        _print("low poly diffuse image")
        lowpoly_image = bpy.data.images.new("lowpoly", width=1024, height=1024)
        bpy.ops.object.select_all(action='DESELECT')

        _print("low poly smart UV project")
        lowpoly.select_set(True)
        bpy.context.view_layer.objects.active = lowpoly
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.smart_project()
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')

        _print("low poly material")
        lowpoly_mat = bpy.data.materials.new(name="Material")
        lowpoly_mat.use_nodes = True

        _print("low poly material, assign to model")
        lowpoly.data.materials.append(lowpoly_mat)

        _print("low poly material, set diffuse image to Base Color")
        node_tex = lowpoly_mat.node_tree.nodes.new("ShaderNodeTexImage")
        node_tex.location = [-300, 300]
        node_tex.image = lowpoly_image
        links = lowpoly_mat.node_tree.links
        links.new(node_tex.outputs[0], lowpoly_mat.node_tree.nodes[0].inputs["Base Color"])

        _print("bake")
        bpy.context.scene.render.engine = 'CYCLES'
        lowpoly.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT')
        highpoly.select_set(True)

        bpy.ops.object.bake(
            type="DIFFUSE",
            width=1024,
            height=1024,
            use_selected_to_active=True,
            cage_extrusion=0.06,
            pass_filter={"COLOR"})

        shutil.rmtree(path_tmp)

        self.report({'INFO'}, "done")
        return rtn()


classes = [
    WM_OT_HelloWorld,
    MY_PG_SceneProperties,
    WM_OT_DoWork
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.my_tool = PointerProperty(type=MY_PG_SceneProperties)

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)

if __name__ == '__main__':
    register()

