import copy

from maya import cmds
from maya import OpenMaya
from maya import OpenMayaAnim

from weights_editor_tool.enums import WeightOperation
from weights_editor_tool import weights_editor_utils as utils


class SkinData:

    def __init__(self, data):
        self.data = data

    def __iter__(self):
        for vert_index in self.data:
            yield vert_index

    def __getitem__(self, vert_index):
        return self.data[vert_index]

    def __setitem__(self, vert_index, value):
        self.data[vert_index] = value

    @classmethod
    def create_empty(cls):
        return cls(None)

    @classmethod
    def get(cls, skin_cluster):
        return cls(cls.get_data(skin_cluster))

    @staticmethod
    def get_data(skin_cluster):
        """
        Re-factored code by Tyler Thornock
        Faster than cmds.skinPercent() and more practical than OpenMaya.MFnSkinCluster()

        Returns:
            A dictionary.
            {vert_index: {"weights": {inf_name: weight_value...}, "dq": float}}
        """
        # Create skin cluster function set
        skin_cluster_mobj = utils.to_mobject(skin_cluster)
        mfn_skin_cluster = OpenMayaAnim.MFnSkinCluster(skin_cluster_mobj)

        # Get MPlugs for weights
        weight_list_plug = mfn_skin_cluster.findPlug("weightList")
        weights_plug = mfn_skin_cluster.findPlug("weights")
        weight_list_obj = weight_list_plug.attribute()
        weight_obj = weights_plug.attribute()
        weight_inf_ids = OpenMaya.MIntArray()

        skin_weights = {}

        # Get current ids
        inf_ids = utils.get_influence_ids(skin_cluster)
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
                except KeyError:
                    pass

            data["weights"] = vert_weights

            dq_value = cmds.getAttr("{0}.bw[{1}]".format(skin_cluster, vert_index))
            data["dq"] = dq_value

            skin_weights[vert_index] = data

        return skin_weights

    def copy(self):
        return self.__class__(copy.deepcopy(self.data))

    def copy_vertex(self, vert_index):
        return copy.deepcopy(self.data[vert_index])

    def get_vertex_infs(self, vert_index):
        try:
            return list(self.data[vert_index]["weights"].keys())
        except KeyError:
            return []

    def calculate_new_value(self, input_value, vert_index, inf, weight_operation):
        old_value = self.data[vert_index]["weights"].get(inf) or 0.0

        if weight_operation == WeightOperation.Absolute:
            return old_value, input_value
        elif weight_operation == WeightOperation.Relative:
            return old_value, utils.clamp(0.0, 1.0, old_value + input_value)
        elif weight_operation == WeightOperation.Percentage:
            return old_value, utils.clamp(0.0, 1.0, old_value * input_value)
        else:
            raise NotImplementedError("Weight operation hasn't been implemented")

    def update_weight_value(self, vert_index, inf_name, new_value):
        """
        Updates weight_data with an influence's value while distributing the difference
        to the rest of its influences. The sum should always be 1.0.

        Args:
            vert_index(int)
            inf_name(string): Influence to update.
            new_value(float): A number between 0 and 1.0.
        """
        if new_value < 0 or new_value > 1:
            raise ValueError("Value needs to be within 0.0 to 1.0.")

        # Ignore if trying to set to a locked influence
        is_inf_locked = cmds.getAttr("{0}.lockInfluenceWeights".format(inf_name))
        if is_inf_locked:
            return

        weight_data = self.data[vert_index]["weights"]

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
            dif = (total - new_value) / (total - weight_data[inf_name])

            for inf in weight_data:
                is_locked = cmds.getAttr("{0}.lockInfluenceWeights".format(inf))
                if is_locked:
                    continue

                if inf == inf_name:
                    weight_data[inf] = new_value
                else:
                    weight_data[inf] *= dif

        for key in list(weight_data.keys()):
            if utils.is_close(0.0, weight_data[key]):
                weight_data.pop(key)

        # Force weight to be 1 if there's only one influence left
        if len(weight_data) == 1:
            key = list(weight_data.keys())[0]
            weight_data[key] = 1.0
