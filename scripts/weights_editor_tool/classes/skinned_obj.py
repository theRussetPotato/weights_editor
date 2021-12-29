import random

from maya import cmds
from maya import OpenMaya

from PySide2 import QtGui

from weights_editor_tool import constants
from weights_editor_tool.enums import ColorTheme
from weights_editor_tool import weights_editor_utils as utils
from weights_editor_tool.classes.skin_data import SkinData


class SkinnedObj:

    def __init__(self, obj):
        self.name = obj
        self.skin_cluster = None
        self.skin_data = None
        self.vert_count = None

        if self.is_valid():
            self.vert_count = utils.get_vert_count(self.name)
            self.update_skin_data()

    @classmethod
    def create(cls, obj):
        return cls(obj)

    @classmethod
    def create_empty(cls):
        return cls(None)

    def is_valid(self):
        return self.name is not None and cmds.objExists(self.name)

    def has_valid_skin(self):
        return self.skin_cluster is not None and self.has_skin_data()

    def short_name(self):
        return self.name.split("|")[-1]

    def update_skin_data(self):
        self.skin_cluster = None
        self.skin_data = SkinData.create_empty()

        if self.is_valid():
            self.skin_cluster = utils.get_skin_cluster(self.name)

            if self.skin_cluster:
                self.skin_data = SkinData.get(self.skin_cluster)

    def is_skin_corrupt(self):
        """
        Checks if topology changes were done after the skinCluster was applied.
        """
        vert_count = utils.get_vert_count(self.name)
        weights_count = len(cmds.getAttr("{0}.weightList[*]".format(self.skin_cluster)))
        return vert_count != weights_count

    def select_inf_vertexes(self, infs):
        """
        Selects effected vertexes by supplied influences.

        Args:
            infs(string[]): List of influences to select from.
        """
        infs_set = set(infs)
        effected_verts = set()

        for vert_index in self.skin_data:
            vert_infs = self.skin_data[vert_index]["weights"].keys()

            is_effected = infs_set.intersection(vert_infs)
            if is_effected:
                if utils.is_curve(self.name):
                    effected_verts.add("{0}.cv[{1}]".format(self.name, vert_index))
                else:
                    effected_verts.add("{0}.vtx[{1}]".format(self.name, vert_index))

        cmds.select(list(effected_verts))

    def flood_weights_to_closest(self):
        """
        Each vertex will be assigned a full weight to its closest joint.
        """
        influences = self.get_influence_ids()

        inf_positions = {
            key: cmds.xform(inf, q=True, ws=True, t=True)
            for key, inf in influences.items()
        }

        verts = cmds.ls("{}.vtx[*]".format(self.name), flatten=True)

        vert_inf_mappings = {}

        for vert_index, plug, in enumerate(verts):
            vert_pos = cmds.pointPosition(plug, world=True)
            vert_point = OpenMaya.MPoint(*vert_pos)

            closest_inf_index = None
            closest_inf_dist = 0

            for inf_index in inf_positions:
                inf_point = OpenMaya.MPoint(*inf_positions[inf_index])
                dist = vert_point.distanceTo(inf_point)
                if closest_inf_index is None or dist < closest_inf_dist:
                    closest_inf_index = inf_index
                    closest_inf_dist = dist

            vert_inf_mappings[vert_index] = closest_inf_index

        cmds.setAttr("{0}.nw".format(self.skin_cluster), 0)
        cmds.skinPercent(self.skin_cluster, verts, prw=100, nrm=0)

        for vert_index, inf_index in vert_inf_mappings.items():
            weight_plug = "{0}.weightList[{1}].weights[{2}]".format(self.skin_cluster, vert_index, inf_index)
            cmds.setAttr(weight_plug, 1)

        cmds.setAttr("{0}.nw".format(self.skin_cluster), 1)
        cmds.skinCluster(self.skin_cluster, e=True, forceNormalizeWeights=True)

    def prune_weights(self, value):
        """
        Runs prune weights on selected vertexes on supplied object.

        Args:
            value(float): Removes any weights below this value.

        Returns:
            True on success.
        """
        flatten_list = utils.get_vert_indexes(self.name)
        if not flatten_list:
            OpenMaya.MGlobal.displayWarning("No vertexes are selected.")
            return False

        cmds.skinPercent(self.skin_cluster, flatten_list, prw=value, nrm=True)

        return True

    def mirror_skin_weights(self, mirror_mode, mirror_inverse, surface_association, inf_association=None, vert_filter=[]):
        objs = self.name
        if vert_filter:
            objs = [
                "{0}.vtx[{1}]".format(self.name, index)
                for index in vert_filter
            ]

        if inf_association is None:
            inf_association = "closestJoint"

        cmds.copySkinWeights(
            objs,
            mirrorMode=mirror_mode,
            mirrorInverse=mirror_inverse,
            surfaceAssociation=surface_association,
            influenceAssociation=[inf_association, "closestJoint"])

    def display_influence(self, influence, color_style=ColorTheme.Max, vert_filter=[]):
        """
        Colors a mesh to visualize skin data.

        Args:
            influence(string): Name of influence to display.
            color_style(int): 0=Max theme, 1=Maya theme.
            vert_filter(int[]): List of vertex indexes to only operate on.
        """
        if color_style == ColorTheme.Max:
            # Max
            low_rgb = [0, 0, 1]
            mid_rgb = [0, 1, 0]
            end_rgb = [1, 0, 0]
            no_rgb = [0.05, 0.05, 0.05]
            full_rgb = [1, 1, 1]
        elif color_style == ColorTheme.Maya:
            # Maya
            low_rgb = [0.5, 0, 0]
            mid_rgb = [1, 0.5, 0]
            end_rgb = [1, 1, 0]
            no_rgb = [0, 0, 0]
            full_rgb = [1, 1, 1]
        else:
            low_rgb = [0, 0, 0]
            mid_rgb = [0, 0, 0]
            end_rgb = [0, 0, 0]
            no_rgb = [0, 0, 0]
            full_rgb = [0, 0, 0]

        vert_colors = []
        vert_indexes = []

        for vert_index in self.skin_data:
            if vert_filter and vert_index not in vert_filter:
                continue

            weights_data = self.skin_data[vert_index]["weights"]

            if influence in weights_data:
                weight_value = weights_data[influence]
                rgb = utils.get_weight_color(
                    weight_value,
                    start_color=low_rgb,
                    mid_color=mid_rgb,
                    end_color=end_rgb,
                    full_color=full_rgb)
            else:
                rgb = no_rgb

            vert_colors.append(rgb)
            vert_indexes.append(vert_index)

        utils.apply_vert_colors(self.name, vert_colors, vert_indexes)

    def display_multi_color_influence(self, inf_colors=None, vert_filter=[]):
        """
        Mimics Softimage and displays all influences at once with their own unique color.

        Args:
            inf_colors(dict): Dictionary of influence names and their rgb colors.
            vert_filter(int[]): List of vertex indexes to only operate on.

        Returns:
            A dictionary of {inf_name:[r, g, b]...}
        """
        if inf_colors is None:
            inf_colors = self.collect_influence_colors()

        vert_colors = []
        vert_indexes = []

        for vert_index in self.skin_data:
            if vert_filter and vert_index not in vert_filter:
                continue

            final_color = [0, 0, 0]

            for inf, weight in self.skin_data[vert_index]["weights"].items():
                inf_color = inf_colors.get(inf)
                final_color[0] += inf_color[0] * weight
                final_color[1] += inf_color[1] * weight
                final_color[2] += inf_color[2] * weight

            vert_colors.append(final_color)
            vert_indexes.append(vert_index)

        utils.apply_vert_colors(self.name, vert_colors, vert_indexes)

        return inf_colors

    def average_by_neighbours(self, vert_index, strength):
        """
        Averages weights of surrounding vertexes.

        Args:
            vert_index(int)
            strength(int): A value of 0-1

        Returns:
            A dictionary of the new weights. {int_name:weight_value...}
        """
        old_weights = self.skin_data[vert_index]["weights"]
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
        neighbours = utils.get_vert_neighbours(self.name, vert_index)

        for index in neighbours:
            for inf, value in self.skin_data[index]["weights"].items():
                # Ignore if locked
                if inf not in unlocked:
                    continue

                # Add weight
                if inf not in new_weights:
                    new_weights[inf] = 0.0

                new_weights[inf] += value

        # Get sum of all new weight values
        total_all = sum([
            new_weights[inf]
            for inf in new_weights
            if inf in unlocked
        ])

        # Average values
        if total_all:
            for inf in new_weights:
                if inf in unlocked:
                    new_weight = new_weights[inf] * (total / total_all)
                    new_weights[inf] = old_weights[inf] + (new_weight - old_weights[inf]) * strength

        return new_weights

    def smooth_weights(self, vert_indexes, strength, normalize_weights=True):
        """
        Runs an algorithm to smooth weights on supplied vertex indexes.

        Args:
            vert_indexes(int[])
            strength(int): A value of 0-1
            normalize_weights(bool)
        """
        # Don't set new weights right away so new values don't interfere
        # when calculating other indexes.
        weights_to_set = {}
        for vert_index in vert_indexes:
            new_weights = self.average_by_neighbours(vert_index, strength)
            weights_to_set[vert_index] = new_weights

        # Set weights
        for vert_index, weights in weights_to_set.items():
            self.skin_data[vert_index]["weights"] = weights

        self.apply_current_skin_weights(vert_indexes, normalize=normalize_weights)

    def hide_vert_colors(self):
        if self.is_valid():
            utils.toggle_display_colors(self.name, False)
            utils.delete_temp_inputs(self.name)

    def switch_to_color_set(self):
        """
        Switches supplied object's color set to display skin weights.
        Needs to do this otherwise we risk overwriting another color set.

        Args:
            obj(string)
        """
        color_set_name = "weightsEditorColorSet"

        obj_shapes = cmds.listRelatives(self.name, f=True, shapes=True) or []
        old_color_sets = set(cmds.ls(cmds.listHistory(obj_shapes), type="createColorSet"))

        obj_color_sets = cmds.polyColorSet(self.name, q=True, allColorSets=True) or []

        if color_set_name not in obj_color_sets:
            cmds.polyColorSet(self.name, create=True, clamped=False, representation="RGB", colorSet=color_set_name)

        cmds.polyColorSet(self.name, currentColorSet=True, colorSet=color_set_name)

        new_color_sets = set(cmds.ls(cmds.listHistory(obj_shapes), type="createColorSet"))

        dif_color_sets = list(new_color_sets.difference(old_color_sets))
        if dif_color_sets:
            cmds.addAttr(dif_color_sets[0], ln=constants.COLOR_SET, dt="string")
            cmds.rename(dif_color_sets[0], constants.COLOR_SET)

    def has_skin_data(self):
        if self.skin_data is not None and self.skin_data.data:
            return True
        return False

    def get_influences(self):
        return utils.get_influences(self.skin_cluster)

    def get_influence_ids(self):
        return utils.get_influence_ids(self.skin_cluster)

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

    def apply_current_skin_weights(self, vert_indexes, normalize=False):
        """
        Sets skin weights with the supplied data.

        Args:
            vert_indexes(int[]): List of vertex indexes to only operate on.
            normalize(bool): Forces weights to be normalized.
        """
        # Get influence info to map with
        inf_data = self.get_influence_ids()
        inf_ids = list(inf_data.keys())
        inf_names = list(inf_data.values())

        # Remove all existing weights
        if utils.is_curve(self.name):
            plug = "{0}.cv".format(self.name)
        else:
            plug = "{0}.vtx".format(self.name)

        selected_vertexes = [
            "{0}[{1}]".format(plug, index)
            for index in vert_indexes
        ]

        cmds.setAttr("{0}.nw".format(self.skin_cluster), 0)
        cmds.skinPercent(self.skin_cluster, selected_vertexes, prw=100, nrm=0)

        # Apply weights per vert
        for vert_index in vert_indexes:
            weight_list_attr = "{0}.weightList[{1}]".format(self.skin_cluster, vert_index)
            for inf_name, weight_value in self.skin_data[vert_index]["weights"].items():
                index = inf_names.index(inf_name)
                weight_attr = ".weights[{0}]".format(inf_ids[index])
                cmds.setAttr("{0}{1}".format(weight_list_attr, weight_attr), weight_value)

            # Apply dual-quarternions
            dq_value = self.skin_data[vert_index]["dq"]
            cmds.setAttr("{0}.bw[{1}]".format(self.skin_cluster, vert_index), dq_value)

        # Re-enable weights normalizing
        cmds.setAttr("{0}.nw".format(self.skin_cluster), 1)

        if normalize:
            cmds.skinCluster(self.skin_cluster, e=True, forceNormalizeWeights=True)
