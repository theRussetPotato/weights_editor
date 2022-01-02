from base import MayaBaseTestCase

from weights_editor_tool.enums import WeightOperation
from weights_editor_tool.classes.skinned_obj import SkinnedObj


class TestSkinData(MayaBaseTestCase):

    def setUp(self):
        super(self.__class__, self).setUp()

    def _edit_and_validate_weights(self, skinned_obj, vert_index, inf, input_value, weight_operation, value_to_check, data_to_check):
        _, new_value = skinned_obj.skin_data.calculate_new_value(input_value, vert_index, inf, weight_operation)
        self.assertAlmostEqual(new_value, value_to_check)

        skinned_obj.skin_data.update_weight_value(vert_index, inf, new_value)
        self.assertEqual(skinned_obj.skin_data[vert_index], data_to_check)

    def test_add_sub_weights(self):
        scn_objs = self.create_skin_scene()
        skinned_obj = SkinnedObj.create(scn_objs["mesh"])

        self._edit_and_validate_weights(
            skinned_obj, 22, "lower", 0.2, WeightOperation.Relative,
            0.25526488809039555,
            self.get_test_data("add_sub_data"))

        self._edit_and_validate_weights(
            skinned_obj, 22, "right", -0.15, WeightOperation.Relative,
            0.15491365404933458,
            self.get_test_data("add_sub_data_2"))

        self._edit_and_validate_weights(
            skinned_obj, 22, "upper", 2, WeightOperation.Relative,
            1.0,
            self.get_test_data("add_sub_data_3"))

        skinned_obj.apply_current_skin_weights([22])

    def test_set_weights(self):
        scn_objs = self.create_skin_scene()
        skinned_obj = SkinnedObj.create(scn_objs["mesh"])

        self._edit_and_validate_weights(
            skinned_obj, 15, "left", 0.5, WeightOperation.Absolute,
            0.5,
            self.get_test_data("set_data"))

        self._edit_and_validate_weights(
            skinned_obj, 15, "upper", 0, WeightOperation.Absolute,
            0,
            self.get_test_data("set_data_2"))

        self._edit_and_validate_weights(
            skinned_obj, 15, "lower", 1, WeightOperation.Absolute,
            1,
            self.get_test_data("set_data_3"))

        skinned_obj.apply_current_skin_weights([15])

    def test_scale_weights(self):
        scn_objs = self.create_skin_scene()
        skinned_obj = SkinnedObj.create(scn_objs["mesh"])

        self._edit_and_validate_weights(
            skinned_obj, 10, "lower", 0.5, WeightOperation.Percentage,
            0.2486919393457866,
            self.get_test_data("scale_data"))

        self._edit_and_validate_weights(
            skinned_obj, 10, "right", 1.6, WeightOperation.Percentage,
            0.9250958139612324,
            self.get_test_data("scale_data_2"))

        skinned_obj.apply_current_skin_weights([10])
