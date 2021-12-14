import os
import time
import json
import glob

from maya import cmds
from maya import OpenMaya
from maya.api import OpenMaya as om2

#import maya_progress_bar
from weights_editor_tool import weights_editor_utils as utils


VERSION = 1.0
last_browsing_path = None


def launch_file_picker(file_mode, caption, ext="skin"):
    global last_browsing_path
    if last_browsing_path is None:
        last_browsing_path = cmds.workspace(q=True, fullName=True)

    picked_path = cmds.fileDialog2(
        caption=caption,
        fileMode=file_mode,
        fileFilter="*.{}".format(ext),
        dir=last_browsing_path)

    if picked_path:
        last_browsing_path = picked_path[0]
        return picked_path[0]


def get_selected_verts():
    """
    Extracts a list of vertex numbers from the selection.
    """
    return [
        int(vtx.split("[")[-1].rstrip("]"))
        for vtx in cmds.filterExpand(cmds.ls(sl=True), sm=31) or []
    ]


def find_influence_by_name(long_name):
    """
    Finds object by first searching with its long name then short name.

    Returns:
        The object's name or None if it doesn't exist.
    """
    if cmds.objExists(long_name):
        return long_name
    
    short_name = long_name.split("|")[-1]
    objs = cmds.ls(short_name, long=True)
    if objs:
        return objs[0]


def get_duplicate_inf_names(skin_cluster):
    return [
        inf
        for inf in cmds.skinCluster(skin_cluster, q=True, influence=True) or []
        if len(inf.split("|")) > 1
    ]


def build_skin_cluster(obj, skin_jnts, max_infs=5, skin_method=0, name="skinCluster"):
    """
    Creates a skinCluster with supplied joints.

    Args:
        obj(string): Object to add skinCluster to.
        skin_jnts(string[]): List of joints to skin with.
        max_infs(int): Number of max influences skinCluster.
        skin_method(int): Skinning method of skinCluster.
        name(string): The name of the new sking cluster.

    Returns:
        The name of the new skinCluster.
    """
    #skin_jnts = cmds.ls(skin_jnts, long=True)

    skin_cluster = utils.get_skin_cluster(obj)
    if skin_cluster:
        cmds.delete(skin_cluster)
        '''infs = cmds.ls(cmds.skinCluster(skin_cluster, q=True, influence=True) or [], long=True)

        for jnt in skin_jnts:
            if jnt not in infs:
                cmds.skinCluster(skin_cluster, e=True, ai=jnt, dr=4.0, ps=0, lw=False, wt=0)'''

    return cmds.skinCluster(
        skin_jnts, obj,
        toSelectedBones=True,
        maximumInfluences=max_infs,
        skinMethod=skin_method,
        name=name)[0]


def to_mfn_mesh(mesh):
    msel_list = om2.MSelectionList()
    msel_list.add(mesh)
    mdag_path = msel_list.getDagPath(0)
    return om2.MFnMesh(mdag_path)


def export_skin(obj, file_path):
    """
    Exports skin weights to a file.

    Args:
        obj(string): A object with a skinCluster.
        file_path(string): An absolute path to save weights to.
    """
    skin_cluster = utils.get_skin_cluster(obj)
    if skin_cluster is None:
        raise RuntimeError("Unable to detect a skinCluster on '{}'.".format(obj))

    output_dir = os.path.dirname(file_path)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    start_time = time.time()

    vert_data = {}
    skin_weights = utils.get_skin_data(skin_cluster)
    
    for vert_index, data in skin_weights.items():
        data["world_pos"] = cmds.xform("{}.vtx[{}]".format(obj, vert_index), q=True, ws=True, t=True)
        vert_data[vert_index] = data

    influence_data = {}
    influence_ids = utils.get_influence_ids(skin_cluster)

    for inf_id, inf in influence_ids.items():
        influence_data[inf_id] = {
            "name": inf,
            "world_matrix": cmds.xform(inf, q=True, ws=True, m=True)
        }

    skin_data = {
        "version": VERSION,
        "object": obj,
        "verts": vert_data,
        "influences": influence_data,
        "skin_cluster": {
            "name": skin_cluster,
            "vert_count": cmds.polyEvaluate(obj, vertex=True),
            "influence_count": len(influence_ids),
            "max_influences": cmds.getAttr("{}.maxInfluences".format(skin_cluster)),
            "skinning_method": cmds.getAttr("{}.skinningMethod".format(skin_cluster)),
            "dqs_support_non_rigid": cmds.getAttr("{}.dqsSupportNonRigid".format(skin_cluster))
        }
    }

    with open(file_path, "w") as f:
        f.write(json.dumps(skin_data))

    end_time = time.time()
    total_time = end_time - start_time

    OpenMaya.MGlobal.displayInfo(
        "Exported {} to {} in {:.2f} seconds".format(
            obj.split("|")[-1], file_path, total_time))


def export_all_skin(output_dir):
    export_count = 0

    for skin_cluster in cmds.ls(type="skinCluster"):
        meshes = cmds.ls(cmds.listHistory("{}.outputGeometry".format(skin_cluster)), type="mesh")
        if meshes:
            obj = cmds.listRelatives(meshes[0], f=True, parent=True)[0]
            file_path = os.path.join(output_dir, "{}.skin".format(obj.split("|")[-1]))
            export_skin(obj, file_path)
            export_count += 1

    OpenMaya.MGlobal.displayInfo(
        "Exported {} skin clusters to {}".format(export_count, output_dir))


def map_to_closest_vertexes(obj, verts_data, vert_filter=[]):
    weights_data = {}

    file_points = [
        om2.MPoint(*verts_data[index]["world_pos"])
        for index in sorted(verts_data.keys())
    ]

    # Build a temporary new mesh from the file's positions so that it's exposed to the api.
    temp_mfn_mesh = om2.MFnMesh()
    temp_mfn_mesh.addPolygon(file_points, False, 0)
    new_mesh = om2.MFnDagNode(temp_mfn_mesh.parent(0)).fullPathName()
    file_mfn_mesh = to_mfn_mesh(new_mesh)

    try:
        mfn_mesh = to_mfn_mesh(obj)
        mesh_points = mfn_mesh.getPoints(om2.MSpace.kWorld)

        for vert_index, point in enumerate(mesh_points):
            # Skip calculations if index is not in the filter.
            if vert_filter and vert_index not in vert_filter:
                continue

            # Get the closest face.
            closest_point = file_mfn_mesh.getClosestPoint(point, om2.MSpace.kWorld)
            face_index = closest_point[1]

            # Get face's vertexes and get the closest vertex.
            face_vertexes = file_mfn_mesh.getPolygonVertices(face_index)

            vert_distances = [
                (index, file_points[index].distanceTo(closest_point[0]))
                for index in face_vertexes
            ]

            closest_index = min(vert_distances, key=lambda dist: dist[1])[0]
            weights_data[vert_index] = closest_index
    finally:
        if cmds.objExists(new_mesh):
            cmds.undoInfo(stateWithoutFlush=False)
            cmds.delete(new_mesh)
            cmds.undoInfo(stateWithoutFlush=True)

    return weights_data


def read_skin_file(skin_path):
    with open(skin_path, "r") as f:
        skin_data = json.loads(f.read())

    skin_data["verts"] = {
        int(key): value
        for key, value in skin_data["verts"].items()
    }

    return skin_data


def import_skin(obj, file_path, world_space=False, vert_filter=[]):
    """
    Imports skin weights from a file.

    Args:
        obj(string): An object's name.
        file_path(string): An absolute path to save weights to.
        world_space(boolean): False=loads by point order, True=loads by world positions
        vert_filter(int[]): List of vertex numbers to import weights on. If empty it will import all all vertexes.
    """
    start_time = time.time()

    skin_data = read_skin_file(file_path)

    # Rename influences
    infs = {}

    for index in skin_data["verts"]:
        for inf in skin_data["verts"][index]["weights"]:
            if inf not in infs:
                if cmds.objExists(inf):
                    infs[inf] = inf
                else:
                    short_name = inf.split("|")[-1]
                    objs = cmds.ls(inf.split("|")[-1])

                    if objs:
                        infs[inf] = objs[0]
                    else:
                        cmds.createNode("joint", name=short_name)
                        infs[inf] = short_name

            skin_data["verts"][index]["weights"][infs[inf]] = skin_data["verts"][index]["weights"].pop(inf)

    if world_space:
        closest_vertexes = map_to_closest_vertexes(obj, skin_data["verts"], vert_filter)

        weights_data = {
            source_index: skin_data["verts"][file_index]
            for source_index, file_index in closest_vertexes.items()
        }
    else:
        # Bail if vert count with file and object don't match (import via point order only)
        file_vert_count = skin_data["skin_cluster"]["vert_count"]
        obj_vert_count = cmds.polyEvaluate(obj, vertex=True)
        if file_vert_count != obj_vert_count:
            raise RuntimeError("Vert count doesn't match. (Object: {}, File: {})".format(obj_vert_count, file_vert_count))

        weights_data = skin_data["verts"]

        if vert_filter:
            for vert_index in weights_data.keys():
                if vert_index not in vert_filter:
                    del weights_data[vert_index]

    # Get influences from file
    skin_jnts = []
    
    for inf_id, inf_data in skin_data["influences"].items():
        inf_name = inf_data["name"]
        inf = find_influence_by_name(inf_name)

        if inf is None:
            # Create new joint if influence is missing
            inf_short_name = inf_name.split("|")[-1]
            inf = cmds.createNode("joint", name=inf_short_name, skipSelect=True)
            cmds.xform(inf, ws=True, m=inf_data["world_matrix"])
            OpenMaya.MGlobal.displayWarning("Created '{}' because it was missing.".format(inf_short_name))

        skin_jnts.append(inf)
    
    # Create skinCluster with joints
    skin_cluster = build_skin_cluster(
        obj, skin_jnts,
        max_infs=skin_data["skin_cluster"]["max_influences"],
        skin_method=skin_data["skin_cluster"]["skinning_method"],
        name=skin_data["skin_cluster"]["name"])

    cmds.setAttr("{}.dqsSupportNonRigid".format(skin_cluster), skin_data["skin_cluster"]["dqs_support_non_rigid"])

    # Set weights to skinCluster
    vert_indexes = [
        vert_index
        for vert_index in weights_data
    ]

    utils.set_skin_weights(obj, weights_data, vert_indexes)

    # Display message
    total_time = time.time() - start_time

    OpenMaya.MGlobal.displayInfo(
        "Imported skin cluster onto {} in {:.2f} seconds".format(
            obj.split("|")[-1], total_time))


def import_all_skin(input_dir, use_world_positions):
    skin_paths = glob.glob(os.path.join(input_dir, "*.skin"))

    for skin_path in skin_paths:
        with open(skin_path, "r") as f:
            data = json.loads(f.read())

        if data["version"] < 1.1:
            cmds.warning(
                "Unable to import from file since it was exported with an older version: {}".format(skin_path))
            continue

        # First try to find object with its long name, then short name.
        obj = data["object"]
        if not cmds.objExists(obj):
            obj = obj.split("|")[-1]

        if not cmds.objExists(obj):
            cmds.warning("Unable to find object `{}`".format(obj))
            continue

        import_skin(obj, skin_path, use_world_positions=use_world_positions)


def run_export_tool():
    sel = cmds.ls(sl=True)
    if not sel:
        raise RuntimeError("Nothing is selected")

    picked_path = launch_file_picker(0, "Export skin")
    if not picked_path:
        return

    export_skin(sel[0], picked_path)


def run_export_all_tool():
    picked_path = launch_file_picker(2, "Directory to export all skin to")
    if picked_path:
        export_all_skin(picked_path)


def run_import_tool(use_world_positions):
    sel = cmds.ls(sl=True)
    if not sel:
        raise RuntimeError("Nothing is selected")

    vert_filter = get_selected_verts()
    if vert_filter:
        sel =cmds.ls(hilite=True)

    picked_path = launch_file_picker(1, "Import skin")
    if not picked_path:
        return

    import_skin(
        sel[0],
        picked_path,
        use_world_positions=use_world_positions,
        vert_filter=vert_filter)


def run_import_all_tool(use_world_positions):
    picked_path = launch_file_picker(2, "Directory to import all skin from")
    if picked_path:
        import_all_skin(picked_path, use_world_positions)
