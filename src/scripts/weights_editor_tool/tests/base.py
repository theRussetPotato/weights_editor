"""
TODO:
    Unit tests:
        - Prune
        - Prune max infs
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
from typing import Any


# Add tool to PYTHONPATH.
testsPath = os.path.dirname(os.path.realpath(__file__))

basePath = testsPath.rsplit(os.sep, 1)[0]
if basePath not in sys.path:
    sys.path.insert(0, basePath)

rootPath = basePath.rsplit(os.sep, 1)[0]
if rootPath not in sys.path:
    sys.path.insert(0, rootPath)

# Initialize Maya in batch mode.
if sys.version_info < (3, 0):
    inBatchMode = isinstance(sys.stdout, file)
else:
    from io import IOBase
    inBatchMode = isinstance(sys.stdout, IOBase)

if inBatchMode:
    import maya.standalone
    maya.standalone.initialize()

from maya import cmds
from weights_editor_tool import weights_editor_utils as utils
from weights_editor_tool.tests import test_data


class MayaBaseTestCase(TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cmds.file(newFile=True, force=True)

    def tearDown(self) -> None:
        cmds.file(newFile=True, force=True)

    @staticmethod
    def getTestData(name: str) -> dict[str, Any]:
        return getattr(test_data, name)

    @staticmethod
    def createSkinScene() -> dict[str, Any]:
        root = cmds.ls(cmds.createNode("transform", name="root"), long=True)[0]
        mesh = cmds.polySphere(name="mesh", subdivisionsX=6, subdivisionsY=6)[0]
        cmds.parent(mesh, root)
        mesh = cmds.ls("mesh", long=True)[0]

        jnts = list()

        jnts.append(cmds.joint(root, position=[-1, 0, 0], name="left"))
        jnts.append(cmds.joint(root, position=[1, 0, 0], name="right"))
        jnts.append(cmds.joint(root, position=[0, 1, 0], name="upper"))
        jnts.append(cmds.joint(root, position=[0, -1, 0], name="lower"))

        skinCluster = utils.buildSkinCluster(
            mesh, jnts, maxInfs=4, dqsSupportNonRigid=True, name="skinCluster1")

        return {
            "root": root,
            "mesh": mesh,
            "skinCluster": skinCluster,
            "joints": jnts
        }

    def _compareDicts(self, d1: dict, d2: dict) -> None:
        for key in d1:
            if key not in d2:
                raise AssertionError(f"Missing key `{key}`\n{d1}\n{d2}")

            if type(d1[key]) is dict:
                self.compareDicts(d1[key], d2[key])
            else:
                if d1[key] != d2[key]:
                    if type(d1[key]) == float and type(d2[key]) == float:
                        self.assertAlmostEqual(
                            d1[key], d2[key], 7,
                            f"Values are different at key `{key}`\n{d1}\n{d2}")
                    else:
                        raise AssertionError(
                            f"Values are different at key `{key}` with values `{d1[key]}` and `{d2[key]}`\n{d1}\n{d2}")

    def compareDicts(self, d1: dict, d2: dict) -> None:
        self._compareDicts(d1, d2)
        self._compareDicts(d2, d1)

    def runTest(self) -> None:
        pass
