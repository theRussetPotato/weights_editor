from base import MayaBaseTestCase
from weights_editor_tool.classes.skinned_obj import SkinnedObj


class TestSkinnedObj(MayaBaseTestCase):

    def setUp(self):
        super(self.__class__, self).setUp()

    def test_name(self):
        scn_objs = self.create_skin_scene()
        skinned_obj = SkinnedObj.create(scn_objs["mesh"])
        self.assertEqual(skinned_obj.name, "mesh")

    def test_skin_cluster(self):
        scn_objs = self.create_skin_scene()
        skinned_obj = SkinnedObj.create(scn_objs["mesh"])
        self.assertEqual(skinned_obj.skin_cluster, "skinCluster1")

    def test_vert_count(self):
        scn_objs = self.create_skin_scene()
        skinned_obj = SkinnedObj.create(scn_objs["mesh"])
        self.assertEqual(skinned_obj.vert_count, 32)

    def test_serialize(self):
        scn_objs = self.create_skin_scene()
        skinned_obj = SkinnedObj.create(scn_objs["mesh"])
        skin_data = skinned_obj.serialize()
        self.assertEqual(skin_data, self.get_test_data("serialized_data"))
