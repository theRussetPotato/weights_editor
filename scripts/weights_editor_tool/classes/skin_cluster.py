import random

from maya import cmds
from maya import OpenMaya
from maya import OpenMayaAnim

from PySide2 import QtGui

from weights_editor_tool import weights_editor_utils as utils
from weights_editor_tool.classes.skin_data import SkinData


class SkinCluster:

    def __init__(self, obj):
        self.obj = obj
        self.name = utils.get_skin_cluster(obj)
        self.skin_data = None
        self.get_skin_data()

    @classmethod
    def create(cls, obj):
        return cls(obj)

    def is_valid(self):
        return self.name is not None

    def get_skin_data(self):
        if self.is_valid():
            self.skin_data = SkinData.get(self)

    def has_data(self):
        if self.skin_data is not None and self.skin_data.data:
            return True
        return False

    def get_influences(self):
        return cmds.skinCluster(self.name, q=True, inf=True) or []

    def get_influence_ids(self):
        """
        Collects all influences and its ids from a skinCluster.

        Returns:
            A dictionary: {id(int):inf_name(string)}
        """
        has_infs = self.get_influences()
        if not has_infs:
            return {}

        skin_cluster_mobj = utils.to_mobject(self.name)
        mfn_skin_cluster = OpenMayaAnim.MFnSkinCluster(skin_cluster_mobj)

        inf_mdag_paths = OpenMaya.MDagPathArray()
        mfn_skin_cluster.influenceObjects(inf_mdag_paths)

        inf_ids = {}

        for i in range(inf_mdag_paths.length()):
            inf_id = int(mfn_skin_cluster.indexForInfluenceObject(inf_mdag_paths[i]))
            inf_ids[inf_id] = inf_mdag_paths[i].partialPathName()

        return inf_ids

    def collect_influence_colors(self, sat=250, brightness=150):
        """
        Generates a unique color for each influence.

        Args:
            sat(float)
            brightness(float)

        Returns:
            A dictionary of {inf_name:[r, g, b]...}
        """
        infs = self.get_influences()
        random.seed(0)
        random.shuffle(infs)

        inf_colors = {}

        hue_step = 360.0 / (len(infs))

        for i, inf in enumerate(infs):
            color = QtGui.QColor()
            color.setHsv(hue_step * i, sat, brightness)
            color.toRgb()

            inf_colors[inf] = [
                color.red() / 255.0,
                color.green() / 255.0,
                color.blue() / 255.0]

        return inf_colors

    def set_skin_weights(self, obj, vert_indexes, normalize=False):
        """
        Sets skin weights with the supplied data.

        Args:
            obj(string)
            vert_indexes(int[]): List of vertex indexes to only operate on.
            normalize(bool): Forces weights to be normalized.
        """
        # Get influence info to map with
        inf_data = self.get_influence_ids()
        inf_ids = list(inf_data.keys())
        inf_names = list(inf_data.values())

        # Remove all existing weights
        if utils.is_curve(self.obj):
            plug = "{0}.cv".format(obj)
        else:
            plug = "{0}.vtx".format(obj)

        selected_vertexes = [
            "{0}[{1}]".format(plug, index)
            for index in vert_indexes
        ]

        cmds.setAttr("{0}.nw".format(self.name), 0)
        cmds.skinPercent(self.name, selected_vertexes, prw=100, nrm=0)

        # Apply weights per vert
        for vert_index in vert_indexes:
            weight_list_attr = "{0}.weightList[{1}]".format(self.name, vert_index)
            for inf_name, weight_value in self.skin_data[vert_index]["weights"].items():
                index = inf_names.index(inf_name)
                weight_attr = ".weights[{0}]".format(inf_ids[index])
                cmds.setAttr("{0}{1}".format(weight_list_attr, weight_attr), weight_value)

            # Apply dual-quarternions
            dq_value = self.skin_data[vert_index]["dq"]
            cmds.setAttr("{0}.bw[{1}]".format(self.name, vert_index), dq_value)

        # Re-enable weights normalizing
        cmds.setAttr("{0}.nw".format(self.name), 1)

        if normalize:
            cmds.skinCluster(self.name, e=True, forceNormalizeWeights=True)
