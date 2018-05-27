import maya.cmds as cmds


qt_version = int(cmds.about(qtVersion=True).split(".")[0])