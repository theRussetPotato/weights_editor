import random

import maya.cmds as cmds
import maya.OpenMaya as OpenMaya
import maya.OpenMayaAnim as OpenMayaAnim

from resources import variables

if variables.qt_version > 4:
    from PySide2 import QtGui
    from PySide2 import QtCore
    from PySide2 import QtWidgets
else:
    from PySide import QtGui
    from PySide import QtCore
    QtWidgets = QtGui


def get_selected_mesh():
    """
    Returns:
        A mesh from the selection or None if nothing valid was found.
    """
    sel = cmds.ls(sl=True, transforms=True)
    
    if not sel:
        shapes = cmds.ls(sl=True, objectsOnly=True)
        if shapes:
            sel = cmds.listRelatives(shapes[0], parent=True)
    
    obj = None
    
    if not sel:
        return
    
    if not cmds.listRelatives(sel[0], shapes=True, type="mesh"):
        if not cmds.listRelatives(sel[0], shapes=True, type="nurbsCurve"):
            return
    
    return sel[0]


def to_m_object(obj):
    """
    Gets an object as a MObject wrapper.
    
    Args:
        obj(string): An object's name.
    
    Returns:
        An MObject.
    """
    sel = OpenMaya.MSelectionList()
    sel.add(obj)
    node = OpenMaya.MObject()
    sel.getDependNode(0, node)
    return node


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


def is_close(val1, val2, rel_tol=1e-09, abs_tol=0.0):
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
    old_range = old_max-old_min
    new_range = new_max-new_min
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
    r = start_color.red()+(end_color.red()-start_color.red())*blend_value
    g = start_color.green()+(end_color.green()-start_color.green())*blend_value
    b = start_color.blue()+(end_color.blue()-start_color.blue())*blend_value
    
    return QtGui.QColor(r, g, b)


def flatten_list_to_indexes(flatten_list):
    """
    Converts a flattened vertex list to numbers.
    
    Args:
        flatten_list(string[]): ["obj.vtx[0]", "obj.vtx[1]", ..]
    
    Returns:
        A list of integers.
    """
    return [int(word[word.index("[")+1:-1]) 
            for word in flatten_list]


def get_selected_vertexes(obj):
    """
    Gets and returns selected vertexes from the supplied object.
    """
    if is_curve(obj):
        flatten_list = cmds.ls("{0}.cv[*]".format(obj), sl=True, fl=True)
    else:
        flatten_list = cmds.ls("{0}.vtx[*]".format(obj), sl=True, fl=True)
    
    return flatten_list_to_indexes(flatten_list)


def get_skin_cluster(obj):
    """
    Get's an object's skinCluster.
    
    Args:
        obj(string)
    
    Returns:
        Object's skinCluster.
    """
    skin_clusters = cmds.ls(cmds.listHistory(obj), type="skinCluster")
    if skin_clusters:
        return skin_clusters[0]


def switch_to_color_set(obj):
    """
    Switches supplied object's color set to display skin weights.
    Needs to do this otherwise we risk overwriting another color set.
    
    Args:
        obj(string)
    """
    color_set_name = "weightsEditorColorSet"
    
    obj_shapes = cmds.listRelatives(obj, f=True, shapes=True) or []
    old_color_sets = set(cmds.ls(cmds.listHistory(obj_shapes), type="createColorSet"))
    
    obj_color_sets = cmds.polyColorSet(obj, q=True, allColorSets=True) or []
    
    if color_set_name not in obj_color_sets:
        cmds.polyColorSet(obj, create=True, clamped=False, representation="RGB", colorSet=color_set_name)
    
    cmds.polyColorSet(obj, currentColorSet=True, colorSet=color_set_name)
    
    new_color_sets = set(cmds.ls(cmds.listHistory(obj_shapes), type="createColorSet"))
    
    dif_color_sets = list(new_color_sets.difference(old_color_sets))
    if dif_color_sets:
        cmds.addAttr(dif_color_sets[0], ln="weightsEditorCreateColorSet", dt="string")
        cmds.rename(dif_color_sets[0], "weightsEditorCreateColorSet")


def toggle_display_colors(obj, enabled):
    """
    Sets attribute to show vertex colors.
    
    Args:
        obj(string)
        enabled(bool)
    """
    if obj is not None and cmds.objExists(obj) and cmds.listRelatives(obj, f=True, shapes=True, type="mesh"):
        cmds.setAttr("{0}.displayColors".format(obj), enabled)


def get_influence_ids(skin_cluster):
    """
    Collects all influences and its ids from a skinCluster.
    
    Args:
        skin_cluster(string): A skinCluster's name.
    
    Returns:
        A dictionary: {id(int):inf_name(string)}
    """
    has_infs = cmds.skinCluster(skin_cluster, q=True, influence=True) or []
    if not has_infs:
        return []
    
    skin_cluster_node = to_m_object(skin_cluster)
    skin_cluster_fn = OpenMayaAnim.MFnSkinCluster(skin_cluster_node)
    
    # Collect influences
    inf_array = OpenMaya.MDagPathArray()
    skin_cluster_fn.influenceObjects(inf_array)
    
    # {inf_name(string):id(int)}
    inf_ids = {}
    
    for x in range(inf_array.length()):
        inf_path = inf_array[x].partialPathName()
        inf_id = int(skin_cluster_fn.indexForInfluenceObject(inf_array[x]))
        inf_ids[inf_id] = inf_path
    
    return inf_ids


def get_skin_data(skin_cluster):
    """
    Re-factored code by Tyler Thornock
    Faster than cmds.skinPercent() and more practical than OpenMaya.MFnSkinCluster()
    
    Args:
        skin_cluster(string): A skinCluster's name.
    
    Returns:
        A dictionary.
        {vert_index:{"weights":{inf_name:weight_value...}, "dq"float}}
    """
    # Create skin cluster function set
    skin_cluster_node = to_m_object(skin_cluster)
    skin_cluster_fn = OpenMayaAnim.MFnSkinCluster(skin_cluster_node)
    
    # Get MPlugs for weights
    weight_list_plug = skin_cluster_fn.findPlug("weightList")
    weights_plug = skin_cluster_fn.findPlug("weights")
    weight_list_obj = weight_list_plug.attribute()
    weight_obj = weights_plug.attribute()
    weight_inf_ids = OpenMaya.MIntArray()
    
    skin_weights = {}
    
    # Get current ids
    inf_ids = get_influence_ids(skin_cluster)
    vert_count = weight_list_plug.numElements()
    
    for vert_index in range(vert_count):
        data = {}
        
        # Get inf indexes of non-zero weights
        weights_plug.selectAncestorLogicalIndex(vert_index, weight_list_obj)
        weights_plug.getExistingArrayAttributeIndices(weight_inf_ids)
        
        # {inf_name:weight_value...}
        vert_weights = {}
        inf_plug = OpenMaya.MPlug(weights_plug)
        
        for inf_id in weight_inf_ids:
            inf_plug.selectAncestorLogicalIndex(inf_id, weight_obj)
            
            try:
                inf_name = inf_ids[inf_id]
                vert_weights[inf_name] = inf_plug.asDouble()
            except KeyError as e:
                pass
        
        data["weights"] = vert_weights
        
        dq_value = cmds.getAttr("{0}.bw[{1}]".format(skin_cluster, vert_index) )
        data["dq"] = dq_value
        
        skin_weights[vert_index] = data
    
    return skin_weights


def update_weight_value(weight_data, inf_name, new_value):
    """
    Updates weight_data with an influence's value while distributing the difference 
    to the rest of its influences. The sum should always be 1.0.
    
    Args:
        weight_data(dict): {inf_name:inf_value...}
                           This is found in skin_data and represents a vertex.
        inf_name(string): Influence to update.
        new_value(float): A number between 0 and 1.0.
    """
    assert new_value >= 0 and new_value <= 1, "Value needs to be within 0.0 to 1.0."
    
    # Ignore if trying to set to a locked influence
    is_inf_locked = cmds.getAttr("{0}.lockInfluenceWeights".format(inf_name))
    if is_inf_locked:
        return
    
    # Add in influence with 0 weight if it's not already in
    if inf_name not in weight_data:
        weight_data[inf_name] = 0
    
    # Get total of all unlocked weights
    total = 0
    unlock_count = 0
    for inf in weight_data:
        is_locked = cmds.getAttr("{0}.lockInfluenceWeights".format(inf))
        if not is_locked:
            total += weight_data[inf]
            unlock_count += 1
    
    if unlock_count > 1:
        # New value must not exceed total
        new_value = min(new_value, total)
        
        # Distribute weights
        dif = (total-new_value) / (total-weight_data[inf_name])
        
        for inf in weight_data:
            is_locked = cmds.getAttr("{0}.lockInfluenceWeights".format(inf))
            if is_locked:
                continue
            
            if inf == inf_name:
                weight_data[inf] = new_value
            else:
                weight_data[inf] *= dif
    
    # Remove all influences with 0 value
    for key in weight_data.keys():
        if is_close(0.0, weight_data[key]):
            weight_data.pop(key)
    
    # Force weight to be 1 if there's only one influence left
    if len(weight_data) == 1:
        weight_data[weight_data.keys()[0]] = 1.0


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
        w = weight*2
        r = start_color[0] + w * (mid_color[0]-start_color[0])
        g = start_color[1] + w * (mid_color[1]-start_color[1])
        b = start_color[2] + w * (mid_color[2]-start_color[2])
    else:
        w = (weight-0.5)*2
        r = mid_color[0] + w * (end_color[0]-mid_color[0])
        g = mid_color[1] + w * (end_color[1]-mid_color[1])
        b = mid_color[2] + w * (end_color[2]-mid_color[2])
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
        cmds.addAttr(dif_pcolor[0], ln="weightsEditorPolyColorPerVertex", dt="string")
        cmds.rename(dif_pcolor[0], "weightsEditorPolyColorPerVertex")


def collect_influence_colors(skin_cluster, sat=250, brightness=150):
    """
    Generates a unique color for each influence.
    
    Args:
        skin_cluster(string): SkinCluster to get influences from.
        sat(float)
        brightness(float)
    
    Returns:
        A dictionary of {inf_name:[r, g, b]...}
    """
    infs = cmds.skinCluster(skin_cluster, q=True, inf=True)
    random.seed(0)
    random.shuffle(infs)
    
    inf_colors = {}
    
    hue_step = 360.0/(len(infs))
    for i, inf in enumerate(infs):
        color = QtGui.QColor()
        color.setHsv(hue_step*i, sat, brightness)
        color.toRgb()
        inf_colors[inf] = [color.red()/255.0, 
                           color.green()/255.0, 
                           color.blue()/255.0]
    
    return inf_colors


def display_multi_color_influence(obj, skin_cluster, skin_data, filter=[]):
    """
    Mimics Softimage and displays all influences at once with their own unique color.
    
    Args:
        obj(string)
        skin_cluster(string)
        skin_data(dict)
        filter(int[]): List of vertex indexes to only operate on.
    
    Returns:
        A dictionary of {inf_name:[r, g, b]...}
    """
    inf_colors = collect_influence_colors(skin_cluster)
    
    vert_colors = []
    vert_indexes = []
    
    for vert_index in skin_data:
        if filter and vert_index not in filter:
            continue
        
        sorted_weights = sorted(skin_data[vert_index]["weights"].iteritems(), key=lambda(k, v):(v, k))
        strongest_inf, _ = sorted_weights[-1]
        picked_color = inf_colors.get(strongest_inf)
        vert_colors.append(picked_color)
        vert_indexes.append(vert_index)
    
    apply_vert_colors(obj, vert_colors, vert_indexes)
    
    return inf_colors


def display_influence(obj, skin_data, influence, color_style=0, filter=[]):
    """
    Colors a mesh to visualize skin data.
    
    Args:
        obj(string)
        skin_data(dict)
        influence(string): Name of influence to display.
        color_style(int): 0=Max theme, 1=Maya theme.
        filter(int[]): List of vertex indexes to only operate on.
    """
    if color_style == 0:
        # Max
        low_rgb = [0.0, 0.0, 1.0]
        mid_rgb = [0.0, 1.0, 0.0]
        end_rgb = [1.0, 0.0, 0.0]
        no_rgb = [0.05, 0.05, 0.05]
        full_rgb = [1.0, 1.0, 1.0]
    elif color_style == 1:
        # Maya
        low_rgb = [0.5, 0.0, 0.0]
        mid_rgb = [1.0, 0.5, 0.0]
        end_rgb = [1.0, 1.0, 0.0]
        no_rgb = [0.0, 0.0, 0.0]
        full_rgb = [1.0, 1.0, 1.0]
    
    vert_colors = []
    vert_indexes = []
    
    for vert_index in skin_data:
        if filter and vert_index not in filter:
            continue
        
        weights_data = skin_data[vert_index]["weights"]
        
        if influence in weights_data:
            weight_value = weights_data[influence]
            rgb = get_weight_color(weight_value, start_color=low_rgb, 
                                   mid_color=mid_rgb, end_color=end_rgb, full_color=full_rgb)
        else:
            rgb = no_rgb
        
        vert_colors.append(rgb)
        vert_indexes.append(vert_index)
    
    apply_vert_colors(obj, vert_colors, vert_indexes)


def select_inf_vertexes(obj, infs, skin_data):
    """
    Selects effected vertexes by supplied influences.
    
    Args:
        obj(string)
        infs(string[]): List of influences to select from.
        skin_data(dict)
    """
    infs_set = set(infs)
    effected_verts = set()
    
    for vert_index in skin_data:
        vert_infs = skin_data[vert_index]["weights"].keys()
        
        is_effected = infs_set.intersection(vert_infs)
        if is_effected:
            if is_curve(obj):
                effected_verts.add("{0}.cv[{1}]".format(obj, vert_index))
            else:
                effected_verts.add("{0}.vtx[{1}]".format(obj, vert_index))
    
    cmds.select(list(effected_verts))


def set_skin_weights(obj, skin_data, vert_indexes, normalize=False):
    """
    Sets skin weights with the supplied data.
    
    Args:
        obj(string): Object with a skinCluster.
        skin_data(dict): Data to set with.
        vert_indexes(int[]): List of vertex indexes to only operate on.
        normalize(bool): Forces weights to be normalized.
    """
    # Get skin cluster
    skin_cluster = get_skin_cluster(obj)
    if skin_cluster is None:
        OpenMaya.MGlobal.displayError("Unable to detect a skinCluster on {0}.".format(obj))
        return
    
    # Get influence info to map with
    inf_data = get_influence_ids(skin_cluster)
    inf_ids = inf_data.keys()
    inf_names = inf_data.values()
    
    # Remove all existing weights
    if is_curve(obj):
        selected_vertexes = ["{0}.cv[{1}]".format(obj, id) for id in vert_indexes]
    else:
        selected_vertexes = ["{0}.vtx[{1}]".format(obj, id) for id in vert_indexes]
    
    cmds.setAttr("{0}.nw".format(skin_cluster), 0)
    cmds.skinPercent(skin_cluster, selected_vertexes, prw=100, nrm=0)
    
    # Apply weights per vert
    for vert_index in vert_indexes:
        weight_list_attr = "{0}.weightList[{1}]".format(skin_cluster, vert_index)
        for inf_name, weight_value in skin_data[vert_index]["weights"].items():
            index = inf_names.index(inf_name)
            inf_id = inf_ids[index]
            weight_attr = ".weights[{0}]".format(inf_id)
            cmds.setAttr("{0}{1}".format(weight_list_attr, weight_attr), weight_value)
        
        # Apply dual-quarternions
        dq_value = skin_data[vert_index]["dq"]
        cmds.setAttr("{0}.bw[{1}]".format(skin_cluster, vert_index), dq_value)
    
    # Re-enable weights normalizing
    cmds.setAttr("{0}.nw".format(skin_cluster), 1)
    
    if normalize:
        cmds.skinCluster(skin_cluster, e=True, forceNormalizeWeights=True)


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
            if not v.isdigit():
                continue
            neighbours.add(int(v))
    return list(neighbours)


def average_by_neighbours(obj, vert_index, skin_data):
    """
    Averages weights of surrounding vertexes.
    
    Args:
        obj(string)
        vert_index(int)
        skin_data(dict)
    
    Returns:
        A dictionary of the new weights. {int_name:weight_value...}
    """
    old_weights = skin_data[vert_index]["weights"]
    new_weights = {}
    
    # Collect unlocked infs and total value of unlocked weights
    unlocked = []
    total = 0.0
    for inf in old_weights:
        is_locked = cmds.getAttr("{0}.lockInfluenceWeights".format(inf))
        if is_locked:
            new_weights[inf] = old_weights[inf]
        else:
            unlocked.append(inf)
            total += old_weights[inf]
    
    # Need at least 2 unlocked influences to continue
    if len(unlocked) < 2:
        return old_weights
    
    # Add together weight of each influence from neighbours
    neighbours = get_vert_neighbours(obj, vert_index)
    for index in neighbours:
        for inf, value in skin_data[index]["weights"].items():
            # Ignore if locked
            if inf not in unlocked:
                continue
            
            # Ignore if influence doesn't already effect vertex
            #if inf not in old_weights:
                #continue
            
            # Add weight
            if inf not in new_weights:
                new_weights[inf] = 0.0
            new_weights[inf] += value
    
    # Get sum of all new weight values
    total_all = sum([new_weights[inf] 
                     for inf in new_weights 
                     if inf in unlocked])
    
    # Average values
    if total_all:
        for inf in new_weights:
            if inf not in unlocked:
                continue
            new_weights[inf] *= total/total_all
    
    return new_weights


def smooth_weights(obj, vert_indexes, skin_data, normalize_weights=True):
    """
    Runs an algorithm to smooth weights on supplied vertex indexes.
    
    Args:
        obj(string)
        vert_indexes(int[])
        skin_data(dict)
    """
    # Don't set new weights right away so new values don't interfere
    # when calculating other indexes.
    weights_to_set = {}
    for vert_index in vert_indexes:
        new_weights = average_by_neighbours(obj, vert_index, skin_data)
        weights_to_set[vert_index] = new_weights
    
    # Set weights
    for vert_index, weights in weights_to_set.items():
        skin_data[vert_index]["weights"] = weights
    
    set_skin_weights(obj, skin_data, vert_indexes, normalize=normalize_weights)


def prune_weights(obj, skin_cluster, prune_value):
    """
    Runs prune weights on selected vertexes on supplied object.
    
    Args:
        obj(string)
        skin_cluster(string)
        prune_value(float): Removes any weights below this value.
    
    Returns:
        True on success.
    """
    if is_curve(obj):
        flatten_list = cmds.ls("{0}.cv[*]".format(obj), sl=True, fl=True)
    else:
        flatten_list = cmds.ls("{0}.vtx[*]".format(obj), sl=True, fl=True)
        
    if not flatten_list:
        OpenMaya.MGlobal.displayWarning("No vertexes are selected.")
        return
    
    cmds.skinPercent(skin_cluster, flatten_list, prw=prune_value, nrm=True)
    
    return True


def delete_temp_inputs(obj):
    """
    Deletes extra inputs the tool creates to see weight colors.
    """
    inputs = cmds.ls(cmds.listHistory(obj), type=["polyColorPerVertex", "createColorSet"])
    for input in inputs:
        if cmds.attributeQuery("weightsEditorCreateColorSet", node=input, exists=True) or cmds.attributeQuery("weightsEditorPolyColorPerVertex", node=input, exists=True):
            cmds.delete(input)