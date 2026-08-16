from base import MayaBaseTestCase
from weights_editor_tool.classes.skinned_obj import SkinnedObj


class TestSkinnedObj(MayaBaseTestCase):

    def setUp(self) -> None:
        super(self.__class__, self).setUp()

    def testName(self) -> None:
        sceneObjs = self.createSkinScene()
        skinnedObj = SkinnedObj.create(sceneObjs["mesh"])
        self.assertEqual(skinnedObj.name, "mesh")

    def testSkinCluster(self) -> None:
        sceneObjs = self.createSkinScene()
        skinnedObj = SkinnedObj.create(sceneObjs["mesh"])
        self.assertEqual(skinnedObj.skinCluster, "skinCluster1")

    def testVertCount(self) -> None:
        sceneObjs = self.createSkinScene()
        skinnedObj = SkinnedObj.create(sceneObjs["mesh"])
        self.assertEqual(skinnedObj.vertCount, 32)

    def testInfs(self) -> None:
        sceneObjs = self.createSkinScene()
        skinnedObj = SkinnedObj.create(sceneObjs["mesh"])
        self.assertEqual(skinnedObj.infs, ['left', 'lower', 'right', 'upper'])

    def testSerialize(self) -> None:
        sceneObjs = self.createSkinScene()
        skinnedObj = SkinnedObj.create(sceneObjs["mesh"])
        skinData = skinnedObj.serialize()
        self.compareDicts(skinData, self.getTestData("serialized_data"))
