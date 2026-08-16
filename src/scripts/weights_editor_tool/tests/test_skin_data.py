from base import MayaBaseTestCase

from weights_editor_tool.enums import WeightOperation
from weights_editor_tool.classes.skinned_obj import SkinnedObj


class TestSkinData(MayaBaseTestCase):

    def setUp(self):
        super(self.__class__, self).setUp()

    def _editAndValidateWeights(
            self, skinnedObj: SkinnedObj, vertIndex: int, inf: str, inputValue: float,
            weightOperation: WeightOperation, valueToCheck: float, dataToCheck: dict) -> None:
        _, newValue = skinnedObj.skinData.calculateNewValue(inputValue, vertIndex, inf, weightOperation)
        self.assertAlmostEqual(newValue, valueToCheck)

        skinnedObj.skinData.updateWeightValue(vertIndex, inf, newValue)
        self.compareDicts(skinnedObj.skinData[vertIndex], dataToCheck)

    def testAddSubWeights(self) -> None:
        sceneObjs = self.createSkinScene()
        skinnedObj = SkinnedObj.create(sceneObjs["mesh"])

        self._editAndValidateWeights(
            skinnedObj, 22, "lower", 0.2, WeightOperation.Relative,
            0.25526488809039555, self.getTestData("add_sub_data"))

        self._editAndValidateWeights(
            skinnedObj, 22, "right", -0.15, WeightOperation.Relative,
            0.15491365404933458, self.getTestData("add_sub_data_2"))

        self._editAndValidateWeights(
            skinnedObj, 22, "upper", 2, WeightOperation.Relative,
            1.0, self.getTestData("add_sub_data_3"))

        skinnedObj.applyCurrentSkinWeights([22])

    def testSetWeights(self) -> None:
        sceneObjs = self.createSkinScene()
        skinnedObj = SkinnedObj.create(sceneObjs["mesh"])

        self._editAndValidateWeights(
            skinnedObj, 15, "left", 0.5, WeightOperation.Absolute,
            0.5, self.getTestData("set_data"))

        self._editAndValidateWeights(
            skinnedObj, 15, "upper", 0, WeightOperation.Absolute,
            0, self.getTestData("set_data_2"))

        self._editAndValidateWeights(
            skinnedObj, 15, "lower", 1, WeightOperation.Absolute,
            1, self.getTestData("set_data_3"))

        skinnedObj.applyCurrentSkinWeights([15])

    def testScaleWeights(self) -> None:
        sceneObjs = self.createSkinScene()
        skinnedObj = SkinnedObj.create(sceneObjs["mesh"])

        self._editAndValidateWeights(
            skinnedObj, 10, "lower", 0.5, WeightOperation.Percentage,
            0.2486919393457866, self.getTestData("scale_data"))

        self._editAndValidateWeights(
            skinnedObj, 10, "right", 1.6, WeightOperation.Percentage,
            0.9250958139612324, self.getTestData("scale_data_2"))

        skinnedObj.applyCurrentSkinWeights([10])
