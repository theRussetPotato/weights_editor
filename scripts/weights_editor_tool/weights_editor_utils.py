import sys
import os
import shiboken2

from maya import cmds
from maya import mel
from maya import OpenMaya
from maya import OpenMayaUI
from maya import OpenMayaAnim

from PySide2 import QtCore
from PySide2 import QtGui
from PySide2 import QtWidgets


from weights_editor_tool import constants


if sys.version_info > (3, 0):
    def long(value):
        return int(value)


def show_error_msg(title, msg, parent):
    QtWidgets.QMessageBox.critical(parent, title, msg)


def get_maya_window():
    if not cmds.about(batch=True):
        ptr = OpenMayaUI.MQtUtil.mainWindow()
        return shiboken2.wrapInstance(long(ptr), QtWidgets.QWidget)


def load_pixmap(file_name, width=None, height=None):
    resources_dir = os.path.abspath(os.path.join(__file__, "..", "resources", "icons"))
    pixmap = QtGui.QPixmap(os.path.join(resources_dir, file_name))

    if width is not None:
        pixmap = pixmap.scaledToWidth(width, QtCore.Qt.SmoothTransformation)

    if height is not None:
        pixmap = pixmap.scaledToHeight(height, QtCore.Qt.SmoothTransformation)

    return pixmap


def convert_version_string(ver_str):
    return tuple(map(int, ver_str.lstrip("v").split(".")))


def is_version_string_greater(ver_str_1, ver_str_2):
    return convert_version_string(ver_str_1) > convert_version_string(ver_str_2)


def create_shortcut(key_sequence, callback):
    maya_window = get_maya_window()

    if maya_window:
        shortcut = QtWidgets.QShortcut(key_sequence, maya_window)
        shortcut.setContext(QtCore.Qt.ApplicationShortcut)
        shortcut.activated.connect(callback)
        return shortcut


def wrap_layout(widgets, orientation=QtCore.Qt.Vertical, spacing=None, margins=None, parent=None):
    if orientation == QtCore.Qt.Horizontal:
        new_layout = QtWidgets.QHBoxLayout()
    else:
        new_layout = QtWidgets.QVBoxLayout()

    for widget in widgets:
        if widget == "stretch":
            new_layout.addStretch()
        elif widget == "splitter":
            frame = QtWidgets.QFrame(parent=parent)
            frame.setStyleSheet("QFrame {background-color: rgb(50, 50, 50);}")

            if orientation == QtCore.Qt.Vertical:
                frame.setFixedHeight(2)
            else:
                frame.setFixedWidth(2)

            new_layout.addWidget(frame)
        elif type(widget) == int:
            new_layout.addSpacing(widget)
        else:
            if QtCore.QObject.isWidgetType(widget):
                new_layout.addWidget(widget)
            else:
                new_layout.addLayout(widget)

    if spacing is not None:
        new_layout.setSpacing(spacing)

    if margins is not None:
        new_layout.setContentsMargins(*margins)

    return new_layout


def is_in_component_mode():
    return cmds.selectMode(q=True, component=True) or bool(cmds.ls(hilite=True))


def get_selected_mesh():
    """
    Returns:
        A mesh from the selection or None if nothing valid was found.
    """
    sel = cmds.ls(sl=True, long=True, transforms=True)
    
    if not sel:
        shapes = cmds.ls(sl=True, long=True, objectsOnly=True)
        if shapes:
            sel = cmds.listRelatives(shapes[0], f=True, parent=True)

    if not sel:
        return

    if not cmds.listRelatives(sel[0], shapes=True, type=["mesh", "nurbsCurve"]):
        return
    
    return sel[0]


def to_mobject(obj):
    """
    Gets an object as a MObject wrapper.
    
    Args:
        obj(string): An object's name.
    
    Returns:
        An MObject.
    """
    msel_list = OpenMaya.MSelectionList()
    msel_list.add(obj)
    mobject = OpenMaya.MObject()
    msel_list.getDependNode(0, mobject)
    return mobject


def is_curve(obj):
    """
    Detects and returns True if supplied object is a nurbs curve.
    """
    if cmds.objectType(obj) == "nurbsCurve":
        return True
    
    shapes = cmds.listRelatives(obj, f=True, shapes=True, type="nurbsCurve")
    if shapes:
        return True
    
    return False


def get_vert_count(obj):
    if is_curve(obj):
        curve_degree = cmds.getAttr("{0}.degree".format(obj))
        curve_spans = cmds.getAttr("{0}.spans".format(obj))
        return curve_degree + curve_spans
    else:
        return cmds.polyEvaluate(obj, vertex=True)


def is_close(val1, val2, rel_tol=1e-09, abs_tol=1e-15):
    """
    Determines if the two float values are close enough to each other.
    https://www.python.org/dev/peps/pep-0485/#proposed-implementation
    """
    return abs(val1 - val2) <= max(rel_tol * max(abs(val1), abs(val2)), abs_tol)


def clamp(min_value, max_value, value):
    """
    Clamps a value to the supplied range.
    """
    return max(min_value, min(value, max_value))


def remap_range(old_min, old_max, new_min, new_max, old_value):
    """
    Converts a value from one range to another.
    """
    old_range = old_max - old_min
    new_range = new_max - new_min
    return ((old_value - old_min) * new_range / old_range) + new_min


def lerp_color(start_color, end_color, blend_value):
    """
    Lerps between two colors by supplied blend value.
    
    Args:
        start_color(QColor)
        end_color(QColor)
        blend_value(float): A value between 0.0 to 1.0
                            0.0=start_color
                            0.5=50% mix of both colors
                            1.0=end_color
    
    Returns:
        A QColor.
    """
    r = start_color.red() + (end_color.red() - start_color.red()) * blend_value
    g = start_color.green() + (end_color.green() - start_color.green()) * blend_value
    b = start_color.blue() + (end_color.blue() - start_color.blue()) * blend_value
    return QtGui.QColor(r, g, b)


def extract_indexes(flatten_list):
    """
    Converts a flattened vertex list to numbers.
    
    Args:
        flatten_list(string[]): ["obj.vtx[0]", "obj.vtx[1]", ..]
    
    Returns:
        A list of integers.
    """
    return [
        int(word[word.index("[") + 1: -1])
        for word in flatten_list
    ]


def get_all_vert_indexes(obj):
    """
    Gets and returns all vertexes from the supplied object.
    """
    if is_curve(obj):
        return cmds.ls("{0}.cv[*]".format(obj), long=True, flatten=True)
    else:
        return cmds.ls("{0}.vtx[*]".format(obj), long=True, flatten=True)


def get_vert_indexes(obj):
    """
    Gets and returns selected vertexes from the supplied object.
    """
    if is_curve(obj):
        return cmds.ls("{0}.cv[*]".format(obj), sl=True, long=True, flatten=True)
    else:
        components = filter(lambda x: x.startswith(obj), cmds.ls(sl=True, long=True, type="float3"))
        return cmds.ls(cmds.polyListComponentConversion(components, toVertex=True), long=True, flatten=True)


def get_skin_cluster(obj):
    """
    Get's an object's skinCluster.
    
    Args:
        obj(string)
    
    Returns:
        Object's skinCluster.
    """
    skin_clusters = cmds.ls(cmds.listHistory(obj) or [], type="skinCluster")
    if skin_clusters:
        return skin_clusters[0]


def build_skin_cluster(obj, skin_jnts, max_infs=5, skin_method=0, dqs_support_non_rigid=False, name="skinCluster"):
    """
    Creates a skinCluster with supplied joints.

    Args:
        obj(string): Object to add skinCluster to.
        skin_jnts(string[]): List of joints to skin with.
        max_infs(int): Number of max influences skinCluster.
        skin_method(int): Skinning method of skinCluster.
        dqs_support_non_rigid(bool)
        name(string): The name of the new sking cluster.

    Returns:
        The name of the new skinCluster.
    """
    skin_cluster = get_skin_cluster(obj)
    if skin_cluster:
        cmds.delete(skin_cluster)

    new_skin_cluster = cmds.skinCluster(
        skin_jnts, obj,
        toSelectedBones=True,
        maximumInfluences=max_infs,
        skinMethod=skin_method,
        name=name)[0]

    cmds.setAttr("{}.dqsSupportNonRigid".format(new_skin_cluster), dqs_support_non_rigid)

    return new_skin_cluster


def get_influences(skin_cluster):
    return cmds.skinCluster(skin_cluster, q=True, inf=True) or []


def get_influence_ids(skin_cluster):
    """
    Collects all influences and its ids from a skinCluster.

    Returns:
        A dictionary: {id(int):inf_name(string)}
    """
    has_infs = get_influences(skin_cluster)
    if not has_infs:
        return {}

    skin_cluster_mobj = to_mobject(skin_cluster)
    mfn_skin_cluster = OpenMayaAnim.MFnSkinCluster(skin_cluster_mobj)

    inf_mdag_paths = OpenMaya.MDagPathArray()
    mfn_skin_cluster.influenceObjects(inf_mdag_paths)

    inf_ids = {}

    for i in range(inf_mdag_paths.length()):
        inf_id = int(mfn_skin_cluster.indexForInfluenceObject(inf_mdag_paths[i]))
        inf_ids[inf_id] = inf_mdag_paths[i].partialPathName()

    return inf_ids


def toggle_display_colors(obj, enabled):
    """
    Sets attribute to show vertex colors.
    
    Args:
        obj(string)
        enabled(bool)
    """
    if obj is not None and cmds.objExists(obj) and cmds.listRelatives(obj, f=True, shapes=True, type="mesh"):
        state = cmds.getAttr("{0}.displayColors".format(obj))
        if state != enabled:
            cmds.setAttr("{0}.displayColors".format(obj), enabled)


def get_weight_color(weight, start_color=[0, 0, 1], mid_color=[0, 1, 0], end_color=[1, 0, 0], full_color=[1.0, 1.0, 1.0]):
    """
    Gets color that represents supplied weight value.
    A value of 0 will be bias towards start_color, 1.0 will be biased towards end_color.
    
    Args:
        weight(float): A value between 0.0 to 1.0.
        start_color(float[]): Represents rbg when weight is 0.0.
        mid_color(float[]): Represents rbg when weight is 0.5.
        end_color(float[]): Represents rbg when weight is 1.0.
        full_color(float[]): Represents rbg when weight is equal to 1.0.
    
    Returns:
        An rbg list.
    """
    if weight == 1.0:
        r, g, b = full_color
    elif weight < 0.5:
        w = weight * 2
        r = start_color[0] + w * (mid_color[0] - start_color[0])
        g = start_color[1] + w * (mid_color[1] - start_color[1])
        b = start_color[2] + w * (mid_color[2] - start_color[2])
    else:
        w = (weight - 0.5) * 2
        r = mid_color[0] + w * (end_color[0] - mid_color[0])
        g = mid_color[1] + w * (end_color[1] - mid_color[1])
        b = mid_color[2] + w * (end_color[2] - mid_color[2])

    return [r, g, b]


def apply_vert_colors(obj, colors, vert_indexes):
    """
    Sets vert colors on the supplied mesh.
    
    Args:
        obj(string): Object to edit vert colors.
        colors(float[]): A list of rgb values.
        vert_indexes(int[]): A list of vertex indexes.
                             This should match the length of colors.
    """
    obj_shapes = cmds.listRelatives(obj, f=True, shapes=True) or []
    
    old_pcolor = set(cmds.ls(cmds.listHistory(obj_shapes), type="polyColorPerVertex"))
    
    color_array = OpenMaya.MColorArray()
    int_array = OpenMaya.MIntArray()
    
    for rgb, vert_index in zip(colors, vert_indexes):
        color_array.append(OpenMaya.MColor(rgb[0], rgb[1], rgb[2]))
        int_array.append(vert_index)
    
    selection_list = OpenMaya.MSelectionList()
    dag_path = OpenMaya.MDagPath()
    selection_list.add(obj)
    selection_list.getDagPath(0, dag_path)
    
    mfn_mesh = OpenMaya.MFnMesh(dag_path)
    mfn_mesh.setVertexColors(color_array, int_array) # This creates polyColorPerVertex
    
    new_pcolor = set(cmds.ls(cmds.listHistory(obj_shapes), type="polyColorPerVertex"))
    
    dif_pcolor = list(new_pcolor.difference(old_pcolor))
    if dif_pcolor:
        cmds.addAttr(dif_pcolor[0], ln=constants.POLY_COLOR_PER_VERT, dt="string")
        cmds.rename(dif_pcolor[0], constants.POLY_COLOR_PER_VERT)


def get_vert_neighbours(obj, vert_index):
    """
    Fetches adjacent vertexes.
    
    Args:
        obj(string)
        vert_index(int)
    
    Returns:
        A list of vertex indexes.
    """
    if is_curve(obj):
        return []
    
    # Get surrounding edges
    edge_string = cmds.polyInfo("{0}.vtx[{1}]".format(obj, vert_index), vertexToEdge=True)[0]
    edge_indexes = edge_string.split()[2:]
    
    # Convert edges back to vertexes
    neighbours = set()

    for edge_index in edge_indexes:
        vert_string = cmds.polyInfo("{0}.e[{1}]".format(obj, edge_index), edgeToVertex=True)[0]
        for v in vert_string.split()[2:]:
            if v.isdigit():
                neighbours.add(int(v))

    return list(neighbours)


def br_smooth_verts(flood=1.0, ignore_lock=True):
    last_ctx = cmds.currentCtx()

    try:
        mel.eval("source brSmoothWeightsToolCtx;")
        mel.eval("brSmoothWeightsToolCtx;")

        cmds.brSmoothWeightsContext(
            cmds.currentCtx(),
            e=True,
            affectSelected=True,
            flood=flood,
            ignoreLock=ignore_lock)
    finally:
        cmds.setToolTo(last_ctx)


def delete_temp_inputs(obj):
    """
    Deletes extra inputs the tool creates to see weight colors.
    """
    inputs = cmds.ls(cmds.listHistory(obj), type=["polyColorPerVertex", "createColorSet"])
    for input in inputs:
        if cmds.attributeQuery(constants.COLOR_SET, node=input, exists=True) or \
                cmds.attributeQuery(constants.POLY_COLOR_PER_VERT, node=input, exists=True):
            cmds.delete(input)
