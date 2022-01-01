import os
import sys

from unittest import TestCase

# Add repository base path to system paths, so Maya can access your scripts.
tests_path = os.path.dirname(os.path.realpath(__file__))

base_path = tests_path.rsplit(os.sep, 1)[0]
if base_path not in sys.path:
    sys.path.insert(0, base_path)

root_path = base_path.rsplit(os.sep, 1)[0]
if root_path not in sys.path:
    sys.path.insert(0, root_path)

# Initialize Maya - otherwise tests run before Maya is actually ready!
import maya.standalone
maya.standalone.initialize()

from maya import cmds
from weights_editor_tool import weights_editor_utils as utils


class MayaBaseTestCase(TestCase):

    @classmethod
    def setUpClass(self):
        cmds.file(newFile=True, force=True)

    def tearDown(self):
        cmds.file(newFile=True, force=True)

    @staticmethod
    def create_skin_scene():
        root = "root"
        mesh = "mesh"

        cmds.createNode("transform", name=root)
        cmds.polySphere(name=mesh, sx=6, sy=6)
        cmds.parent(mesh, "root")

        jnts = list()

        jnts.append(cmds.joint(root, position=[-1, 0, 0], name="left"))
        jnts.append(cmds.joint(root, position=[1, 0, 0], name="right"))
        jnts.append(cmds.joint(root, position=[0, 1, 0], name="top"))
        jnts.append(cmds.joint(root, position=[0, -1, 0], name="bottom"))

        skin_cluster = utils.build_skin_cluster(
            mesh, jnts, max_infs=4, dqs_support_non_rigid=True, name="skinCluster1")

        return {
            "root": root,
            "mesh": mesh,
            "skinCluster": skin_cluster,
            "joints": jnts
        }

