import sys
import os
import json
import re
import shutil
import stat
from typing import Callable, Optional, Union, Any

from maya import cmds
from maya import mel
from maya import OpenMaya
from maya import OpenMayaUI
from maya.api import OpenMaya as om2
from maya.api import OpenMayaAnim as oma2

from weights_editor_tool.qt import QtCore, QtGui, QtWidgets
from weights_editor_tool import qt
from weights_editor_tool import constants


if sys.version_info > (3, 0):
    def long(value):
        return int(value)


class DisableUndo:
    """
    Context manager to temporarily disable Maya's undo queue.
    This is useful for bulk operations that would otherwise bloat the undo stack or cause performance issues.
    """
    def __enter__(self):
        """Disables the undo state."""
        cmds.undoInfo(stateWithoutFlush=False)

    def __exit__(self, excType, excVal, excTb):
        """Enables the undo state."""
        cmds.undoInfo(stateWithoutFlush=True)


def getSettingsPath() -> str:
    return f"{os.getenv('HOME')}/maya/weightsEditor.json"


def getMayaWindow() -> Optional[QtWidgets.QWidget]:
    """
    Retrieves the main Maya window as a QWidget.
    Uses shiboken to wrap the underlying C++ pointer for use in PySide.

    Returns:
        The Maya main window instance, or None in batch mode.
    """
    if not cmds.about(batch=True):
        ptr = OpenMayaUI.MQtUtil.mainWindow()
        return qt.shiboken.wrapInstance(long(ptr), QtWidgets.QWidget)


def loadPixmap(fileName: str, width: Optional[int] = None, height: Optional[int] = None) -> QtGui.QPixmap:
    """
    Loads an icon from the resources directory and optionally scales it.

    Args:
        fileName (str): The icon file name (e.g., 'icon.png').
        width (int, optional): The target width to scale to.
        height (int, optional): The target height to scale to.

    Returns:
        The loaded and optionally scaled pixmap.
    """
    resourcesDir = os.path.abspath(os.path.join(__file__, "..", "resources", "icons"))
    pixmap = QtGui.QPixmap(os.path.join(resourcesDir, fileName))

    if width is not None:
        pixmap = pixmap.scaledToWidth(width, QtCore.Qt.SmoothTransformation)

    if height is not None:
        pixmap = pixmap.scaledToHeight(height, QtCore.Qt.SmoothTransformation)

    return pixmap


def convertVersionString(versionString) -> tuple[int]:
    """
    Converts a version string (e.g., 'v1.2.3') into a tuple of integers.

    Args:
        versionString (str): The string to parse.

    Returns:
        A tuple representation for easy comparison.
    """
    return tuple(map(int, versionString.lstrip("v").split(".")))


def isVersionStringGreater(versionString1: str, versionString2: str) -> bool:
    """
    Compares two version strings.

    Args:
        versionString1 (str): The first version string.
        versionString2 (str): The second version string.

    Returns:
        True if the first version is greater than the second.
    """
    return convertVersionString(versionString1) > convertVersionString(versionString2)


def createShortcut(keySequence: QtGui.QKeySequence, callback: Callable) -> qt.QShortcut:
    """
    Registers a global application shortcut tied to the Maya window.

    Args:
        keySequence (QtGui.QKeySequence): The key combination.
        callback (Callable): The function to execute when triggered.

    Returns:
        The created shortcut object.
    """
    mayaWindow = getMayaWindow()
    shortcut = qt.QShortcut(keySequence, mayaWindow)
    shortcut.setContext(QtCore.Qt.ApplicationShortcut)
    shortcut.activated.connect(callback)
    return shortcut


def wrapLayout(
        widgets: list[Union[QtWidgets.QWidget, QtWidgets.QLayout]],
        orientation: QtCore.Qt.Orientation = QtCore.Qt.Vertical,
        spacing: Optional[int] = None,
        margins: Optional[list[int]] = None,
        parent: Optional[QtWidgets.QWidget] = None) -> QtWidgets.QLayout:
    """
    Helper to quickly build layouts containing widgets, sub-layouts, and spacers.

    Special string values 'stretch' and 'splitter' can be used to inject QStretch or custom QFrame separators.

    Args:
        widgets (list): List of QWidgets, QLayouts, ints (for spacing), or strings.
        orientation (Qt.Orientation): Vertical or Horizontal.
        spacing (int, optional): Layout spacing.
        margins (list[int], optional): Contents margins [left, top, right, bottom].
        parent (QWidget, optional): Parent for created separators.

    Returns:
        The constructed layout.
    """
    if orientation == QtCore.Qt.Horizontal:
        newLayout = QtWidgets.QHBoxLayout()
    else:
        newLayout = QtWidgets.QVBoxLayout()

    for widget in widgets:
        if widget == "stretch":
            newLayout.addStretch()
        elif widget == "splitter":
            frame = QtWidgets.QFrame(parent=parent)
            frame.setStyleSheet("QFrame {background-color: rgb(50, 50, 50);}")

            if orientation == QtCore.Qt.Vertical:
                frame.setFixedHeight(2)
            else:
                frame.setFixedWidth(2)

            newLayout.addWidget(frame)
        elif type(widget) == int:
            newLayout.addSpacing(widget)
        else:
            if QtCore.QObject.isWidgetType(widget):
                newLayout.addWidget(widget)
            else:
                newLayout.addLayout(widget)

    if spacing is not None:
        newLayout.setSpacing(spacing)

    if margins is not None:
        newLayout.setContentsMargins(*margins)

    return newLayout


def moveToNewLayout(
        oldLayouts: list[QtWidgets.QLayout],
        widgets: list[QtWidgets.QWidget],
        newLayout: QtWidgets.QLayout,
        insertIndex: int) -> None:
    """
    Transfers widgets from their existing layouts into a new layout.

    Args:
        oldLayouts (list[QLayout]): Potential layouts currently holding the widgets.
        widgets (list[QWidget]): The widgets to move.
        newLayout (QLayout): The target layout.
        insertIndex (int): The position index to insert at in the new layout.
    """
    for widget in widgets:
        for layout in oldLayouts:
            index = layout.indexOf(widget)
            if index > -1:
                layout.removeWidget(widget)
        newLayout.insertWidget(insertIndex, widget)


def isInComponentMode() -> bool:
    """
    Checks if Maya is currently in component selection mode.

    Returns:
       True if in component mode or if objects are 'hilited'.
    """
    return cmds.selectMode(query=True, component=True) or bool(cmds.ls(hilite=True))


def getSelectedMesh() -> Optional[str]:
    """
    Identifies a valid mesh or nurbs curve from the current selection.

    Returns:
        The full path to the transform node if valid, else None.
    """
    sel = cmds.ls(selection=True, long=True, transforms=True)
    
    if not sel:
        shapes = cmds.ls(selection=True, long=True, objectsOnly=True)
        if shapes:
            sel = cmds.listRelatives(shapes[0], fullPath=True, parent=True)

    if not sel:
        return

    if not cmds.listRelatives(sel[0], shapes=True, type=["mesh", "nurbsCurve"]):
        return
    
    return sel[0]


def isNurbsCurve(obj: str) -> bool:
    """
    Checks if the provided object is a nurbs curve.

    Args:
        obj (str): The object name or path.

    Returns:
        True if the object or its child shape is a nurbsCurve.
    """
    if cmds.objectType(obj) == "nurbsCurve":
        return True
    
    shapes = cmds.listRelatives(obj, fullPath=True, shapes=True, type="nurbsCurve")
    if shapes:
        return True
    
    return False


def getVertCount(obj: str) -> int:
    """
    Returns the total number of vertices or control points for an object.

    Args:
        obj (str): The object name.

    Returns:
        Number of vertices (Mesh) or CVs (NurbsCurve).
    """
    if isNurbsCurve(obj):
        degrees = cmds.getAttr(f"{obj}.degree")
        spans = cmds.getAttr(f"{obj}.spans")
        return degrees + spans
    else:
        return cmds.polyEvaluate(obj, vertex=True)


def areValuesCloseEnough(
        val1: float,
        val2: float,
        relativeTolerance: float = 1e-09,
        absoluteTolerance: float = 1e-15) -> bool:
    """
    Compares two floats for equality within a specified tolerance.

    Args:
        val1 (float): First value.
        val2 (float): Second value.
        relativeTolerance (float): Floating point relative tolerance.
        absoluteTolerance (float): Floating point absolute tolerance.

    Returns:
        True if the values are considered equal.
    """
    return abs(val1 - val2) <= max(relativeTolerance * max(abs(val1), abs(val2)), absoluteTolerance)


def clamp(minValue: float, maxValue: float, value: float) -> float:
    """
    Clamps a numerical value between a minimum and maximum.

    Args:
        minValue (float): Lower bound.
        maxValue (float): Upper bound.
        value (float): Input value.

    Returns:
        The clamped value.
    """
    return max(minValue, min(value, maxValue))


def remapRange(oldMin: float, oldMax: float, newMin: float, newMax: float, oldValue: float) -> float:
    """
    Remaps a value from one range to another.

    Args:
        oldMin (float): Original range start.
        oldMax (float): Original range end.
        newMin (float): Target range start.
        newMax (float): Target range end.
        oldValue (float): The value to remap.

    Returns:
        The value mapped to the new range.
    """
    oldRange = oldMax - oldMin
    newRange = newMax - newMin
    return ((oldValue - oldMin) * newRange / oldRange) + newMin


def lerpColor(startColor: QtGui.QColor, endColor: QtGui.QColor, blendValue: float) -> QtGui.QColor:
    """
    Linearly interpolates between two colors.

    Args:
        startColor (QtGui.QColor): Color at blendValue 0.0.
        endColor (QtGui.QColor): Color at blendValue 1.0.
        blendValue (float): Mixing factor between 0.0 and 1.0.

    Returns:
        The blended color.
    """
    r = startColor.red() + (endColor.red() - startColor.red()) * blendValue
    g = startColor.green() + (endColor.green() - startColor.green()) * blendValue
    b = startColor.blue() + (endColor.blue() - startColor.blue()) * blendValue
    return QtGui.QColor(r, g, b)


def extractIndexes(flattenList: list[str]) -> list[int]:
    """
    Parses a list of Maya component strings and extracts their numerical indices.

    Example: ["obj.vtx[0]", "obj.vtx[1]"] -> [0, 1]

    Args:
        flattenList (list[str]): List of Maya component strings.

    Returns:
        List of extracted integer indices.
    """
    return [
        int(word[word.index("[") + 1: -1])
        for word in flattenList
    ]


def getAllVertIndexes(obj: str) -> list[str]:
    """
    Retrieves all component indices (vertices or CVs) for the given object.

    Args:
        obj (str): The mesh or nurbs curve to query.

    Returns:
        A flattened list of all component strings.
    """
    if isNurbsCurve(obj):
        return cmds.ls(f"{obj}.cv[*]", long=True, flatten=True)
    else:
        return cmds.ls(f"{obj}.vtx[*]", long=True, flatten=True)


def getVertIndexes(obj: str) -> list[str]:
    """
    Retrieves the currently selected component indices for the given object.

    Args:
        obj (str): The object to query selection from.

    Returns:
        A flattened list of selected component strings.
    """
    if isNurbsCurve(obj):
        return cmds.ls(f"{obj}.cv[*]", selection=True, long=True, flatten=True)
    else:
        components = filter(lambda x: x.startswith(obj), cmds.ls(selection=True, long=True, type="float3"))
        return cmds.ls(cmds.polyListComponentConversion(components, toVertex=True), long=True, flatten=True)


def getSkinCluster(obj: str) -> Optional[str]:
    """
    Finds the skinCluster node associated with the given object's history.

    Args:
        obj (str): The object to query.

    Returns:
        The name of the skinCluster if found, else None.
    """
    skinClusters = cmds.ls(cmds.listHistory(obj) or [], type="skinCluster")
    if skinClusters:
        return skinClusters[0]


def buildSkinCluster(
        obj: str,
        skinJoints: list[str],
        maxInfs: int = 5,
        skinMethod: int = 0,
        dqsSupportNonRigid: bool = False,
        name: str = "skinCluster") -> str:
    """
    Creates a new skinCluster for an object or returns the existing one.

    Args:
        obj (str): Mesh or geometry to skin.
        skinJoints (list[str]): Joints to use as influences.
        maxInfs (int): Maximum influences per vertex.
        skinMethod (int): Skinning algorithm (0: Classic Linear, 1: Dual Quat, 2: Weighted).
        dqsSupportNonRigid (bool): DQS attribute for non-rigid deformation.
        name (str): Desired name for the node.

    Returns:
        The name of the skinCluster node.
    """
    skinCluster = getSkinCluster(obj)
    if skinCluster:
        return skinCluster

    newSkinCluster = cmds.skinCluster(
        skinJoints, obj,
        toSelectedBones=True,
        maximumInfluences=maxInfs,
        skinMethod=skinMethod,
        name=name)[0]

    cmds.setAttr(f"{newSkinCluster}.dqsSupportNonRigid", dqsSupportNonRigid)

    return newSkinCluster


def getInfs(skinCluster: str) -> list[str]:
    """
    Queries all influences currently attached to the skinCluster.

    Args:
        skinCluster (str): The skinCluster node name.

    Returns:
        A list of influence node names.
    """
    return cmds.skinCluster(skinCluster, query=True, inf=True) or []


def getInfIds(skinCluster: str) -> dict[int, str]:
    """
    Maps skinCluster influence indices to their partial path names.

    Args:
        skinCluster (str): The skinCluster node name.

    Returns:
        A dictionary of {index: influenceName}.
    """
    mselectionList = om2.MSelectionList()
    mselectionList.add(skinCluster)
    skinClusterMObj = mselectionList.getDependNode(0)
    mfnSkinCluster = oma2.MFnSkinCluster(skinClusterMObj)
    infDagPaths = mfnSkinCluster.influenceObjects()
    if not infDagPaths:
        return {}

    infIds = {}

    for i in range(len(infDagPaths)):
        infId = mfnSkinCluster.indexForInfluenceObject(infDagPaths[i])
        infIds[infId] = infDagPaths[i].partialPathName()

    return infIds


def toggleDisplayColors(obj: str, enabled: bool) -> None:
    """
    Sets the 'displayColors' attribute on a mesh to toggle vertex color visibility.

    Args:
        obj (str): The mesh transform or shape.
        enabled (bool): Whether to show vertex colors in the viewport.
    """
    if obj is not None and cmds.objExists(obj) and cmds.listRelatives(obj, fullPath=True, shapes=True, type="mesh"):
        state = cmds.getAttr(f"{obj}.displayColors")
        if state != enabled:
            cmds.setAttr(f"{obj}.displayColors", enabled)


def getWeightColor(
        weight: float,
        startColor: list[float] = [0, 0, 1],
        midColor: list[float] = [0, 1, 0],
        endColor: list[float] = [1, 0, 0],
        fullColor: list[float] = [1.0, 1.0, 1.0]) -> list[float]:
    """
    Calculates an RGB color based on a weight value for visualization.

    Args:
        weight (float): Normalized weight value (0.0 to 1.0).
        startColor (list[float]): RGB for weight 0.0.
        midColor (list[float]): RGB for weight 0.5.
        endColor (list[float]): RGB for weight 1.0 (gradient end).
        fullColor (list[float]): RGB used specifically for values exactly 1.0.

    Returns:
        Calculated [R, G, B] values.
    """
    if weight == 1.0:
        r, g, b = fullColor
    elif weight < 0.5:
        w = weight * 2
        r = startColor[0] + w * (midColor[0] - startColor[0])
        g = startColor[1] + w * (midColor[1] - startColor[1])
        b = startColor[2] + w * (midColor[2] - startColor[2])
    else:
        w = (weight - 0.5) * 2
        r = midColor[0] + w * (endColor[0] - midColor[0])
        g = midColor[1] + w * (endColor[1] - midColor[1])
        b = midColor[2] + w * (endColor[2] - midColor[2])

    return [r, g, b]


def applyVertColors(obj: str, colors: list[list[int]], vertIndexes: list[int]) -> None:
    """
    Applies vertex colors to specific mesh indices.
    This function tags created polyColorPerVertex nodes with a custom attribute to facilitate cleanup later.

    Args:
        obj (str): The mesh to apply colors to.
        colors (list[list[float]]): List of RGB colors.
        vertIndexes (list[int]): List of vertex indices matching the color list.
    """
    objShapes = cmds.listRelatives(obj, fullPath=True, shapes=True) or []
    
    objPolyColor = set(cmds.ls(cmds.listHistory(objShapes), type="polyColorPerVertex"))
    
    colorArray = OpenMaya.MColorArray()
    intArray = OpenMaya.MIntArray()
    
    for rgb, vertIndex in zip(colors, vertIndexes):
        colorArray.append(OpenMaya.MColor(rgb[0], rgb[1], rgb[2]))
        intArray.append(vertIndex)
    
    selectionList = OpenMaya.MSelectionList()
    dagPath = OpenMaya.MDagPath()
    selectionList.add(obj)
    selectionList.getDagPath(0, dagPath)
    
    mfnMesh = OpenMaya.MFnMesh(dagPath)
    mfnMesh.setVertexColors(colorArray, intArray) # This creates polyColorPerVertex
    
    newPolyColor = set(cmds.ls(cmds.listHistory(objShapes), type="polyColorPerVertex"))
    
    diffPolyColor = list(newPolyColor.difference(objPolyColor))
    if diffPolyColor:
        cmds.addAttr(diffPolyColor[0], ln=constants.POLY_COLOR_PER_VERT, dt="string")
        cmds.rename(diffPolyColor[0], constants.POLY_COLOR_PER_VERT)


def deleteTempInputs(obj: str) -> None:
    """
    Cleans up temporary nodes created by the tool for weight visualization.
    Scans history for 'polyColorPerVertex' or 'createColorSet' nodes that contain the tool's custom identifier attribute.

    Args:
        obj (str): The mesh to clean.
    """
    inputs = cmds.ls(cmds.listHistory(obj), type=["polyColorPerVertex", "createColorSet"])
    for input in inputs:
        if cmds.attributeQuery(constants.COLOR_SET, node=input, exists=True) or \
                cmds.attributeQuery(constants.POLY_COLOR_PER_VERT, node=input, exists=True):
            cmds.delete(input)


def loadCommandPlugins():
    """
    Ensures the custom command plugin is loaded into the session.
    """
    if not cmds.pluginInfo(constants.PLUGIN_NAME, query=True, loaded=True):
        cmds.loadPlugin(constants.PLUGIN_NAME)


def setJointLabels(
        joints: Optional[list[str]] = None,
        centerAxis: str = "x",
        centerThreshold: float = 0.001,
        leftPrefix: str = "L_",
        rightPrefix: str = "R_") -> None:
    """
    Automates joint labels so that they can be used for mappings on skinning operations.

    Args:
        joints (list[str]): A list of joints to set labels to. If nothing is supplied, it will fetch all joints.
        centerAxis (str): The planar axis to determine which side a joint is on.
        centerThreshold (float): The threshold to determine if a joint is within the center or on a side.
        leftPrefix (str): The prefix to strip so it names the label a common name.
        rightPrefix (str): The prefix to strip so it names the label a common name.
    """
    if joints is None:
        joints = cmds.ls(type="joint")

    centerAxisIndexes = {"x": 0, "y": 1, "z": 2}
    centerAxisIndex = centerAxisIndexes[centerAxis]

    results = {}

    for joint in joints:
        shortName = joint.split("|")[-1].split(":")[-1]

        cmds.setAttr(f"{joint}.type", 18)

        positions = cmds.xform(joint, query=True, worldSpace=True, translation=True)
        value = positions[centerAxisIndex]

        if abs(value) < centerThreshold:
            cmds.setAttr(f"{joint}.side", 0)
            cmds.setAttr(f"{joint}.otherType", shortName, type="string")
            results[shortName] = shortName
        else:
            if value > 0:
                labelName = shortName.replace(rightPrefix, "")
                cmds.setAttr(f"{joint}.side", 2)
                cmds.setAttr(f"{joint}.otherType", labelName, type="string")
                results[shortName] = labelName
            else:
                labelName = shortName.replace(leftPrefix, "")
                cmds.setAttr(f"{joint}.side", 1)
                cmds.setAttr(f"{joint}.otherType", shortName.replace(leftPrefix, ""), type="string")
                results[shortName] = labelName

    print("Setting joint labels:")
    for joint in sorted(results):
        print(f"  joint: {joint}, label: {results[joint]}")


def getPathsFromEnvVar(envVar: str) -> list[str]:
    """Gets and returns paths from the supplied environment variable."""
    pathsValues = os.getenv(envVar, "")
    paths = [path.replace("\\", "/") for path in pathsValues.split(os.pathsep) if path]
    paths.sort()
    return paths


def uninstall() -> bool:
    """Uses Maya's paths to uninstall the Weights Editor. Returns True if it removed files."""
    uninstalled = False

    # Remove the tool if it exists.
    scriptPaths = getPathsFromEnvVar("MAYA_SCRIPT_PATH")
    for path in scriptPaths:
        toolPath = f"{path}/weights_editor_tool"
        if os.path.exists(toolPath):
            print(f"Removing {toolPath}")
            for root, dirs, files in os.walk(toolPath, topdown=False):
                for name in files + dirs:
                    os.chmod(os.path.join(root, name), stat.S_IWUSR)
            shutil.rmtree(toolPath)
            uninstalled = True

    # Unload and remove the tool's plugin.
    if cmds.pluginInfo(constants.PLUGIN_NAME, query=True, loaded=True):
        cmds.unloadPlugin(constants.PLUGIN_NAME, force=True)
    if cmds.pluginInfo(constants.PLUGIN_NAME, query=True, registered=True):
        cmds.pluginInfo(constants.PLUGIN_NAME, edit=True, remove=True)

    # Remove the tool's plugin.
    pluginPaths = getPathsFromEnvVar("MAYA_PLUG_IN_PATH")
    for path in pluginPaths:
        pluginPath = f"{path}/{constants.PLUGIN_NAME}"
        if os.path.exists(pluginPath):
            print(f"Removing {pluginPath}")
            os.remove(pluginPath)
            uninstalled = True

    return uninstalled
