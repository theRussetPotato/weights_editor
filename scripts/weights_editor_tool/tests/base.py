"""
TODO:
    Unit tests:
        - Prune
        - Smooth
        - Mirror
        - Mirror all
        - Copy vertex
        - Paste vertex
        - Flood to closest
"""

import os
import sys

from unittest import TestCase

# Add tool to PYTHONPATH.
tests_path = os.path.dirname(os.path.realpath(__file__))

base_path = tests_path.rsplit(os.sep, 1)[0]
if base_path not in sys.path:
    sys.path.insert(0, base_path)

root_path = base_path.rsplit(os.sep, 1)[0]
if root_path not in sys.path:
    sys.path.insert(0, root_path)

# Initialize Maya in batch mode.
if sys.version_info < (3, 0):
    in_batch_mode = isinstance(sys.stdout, file)
else:
    from io import IOBase
    in_batch_mode = isinstance(sys.stdout, IOBase)

if in_batch_mode:
    import maya.standalone
    maya.standalone.initialize()

from maya import cmds
from weights_editor_tool import weights_editor_utils as utils
from weights_editor_tool.tests import test_data


class MayaBaseTestCase(TestCase):

    @classmethod
    def setUpClass(cls):
        cmds.file(newFile=True, force=True)

    def tearDown(self):
        cmds.file(newFile=True, force=True)

    @staticmethod
    def get_test_data(name):
        return getattr(test_data, name)

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
        jnts.append(cmds.joint(root, position=[0, 1, 0], name="upper"))
        jnts.append(cmds.joint(root, position=[0, -1, 0], name="lower"))

        skin_cluster = utils.build_skin_cluster(
            mesh, jnts, max_infs=4, dqs_support_non_rigid=True, name="skinCluster1")

        return {
            "root": root,
            "mesh": mesh,
            "skinCluster": skin_cluster,
            "joints": jnts
        }

    def _compare_dicts(self, d1, d2):
        for key in d1:
            if key not in d2:
                raise AssertionError("Missing key `{}`\n{}\n{}".format(key, d1, d2))

            if type(d1[key]) is dict:
                self.compare_dicts(d1[key], d2[key])
            else:
                if d1[key] != d2[key]:
                    if type(d1[key]) == float and type(d2[key]) == float:
                        self.assertAlmostEqual(
                            d1[key], d2[key], 7,
                            "Values are different at key `{}`\n{}\n{}".format(key, d1, d2))
                    else:
                        raise AssertionError(
                            "Values are different at key `{}` with values `{}` and `{}`\n{}\n{}".format(key, d1[key], d2[key], d1, d2))

    def compare_dicts(self, d1, d2):
        self._compare_dicts(d1, d2)
        self._compare_dicts(d2, d1)

    def runTest(self):
        pass

