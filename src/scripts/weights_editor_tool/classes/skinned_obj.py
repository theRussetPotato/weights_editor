import sys
import os
import random
import glob
from typing import Optional, Any
from collections import deque

if sys.version_info < (3, 0):
    import cPickle
else:
    import _pickle as cPickle

from maya import cmds
from maya import OpenMaya
from maya.api import OpenMaya as om2
from maya.api import OpenMayaAnim as oma2

from weights_editor_tool.qt import QtGui
from weights_editor_tool import constants
from weights_editor_tool.enums import ColorTheme
from weights_editor_tool import weights_editor_utils as utils
from weights_editor_tool.widgets import status_progress_bar
from weights_editor_tool.classes.skin_data import SkinData


class SkinnedObj:
    """
    Manages the relationship between a Maya mesh/nurbsCurve and its skinning data.

    This class handles high-level operations such as importing/exporting weights, mapping weights between different
    geometries using spatial lookups, and maintaining the tool's internal representation of the skinCluster.

    Attributes:
        lastBrowserPath (str): A class-level variable to remember the last directory accessed by the file picker.
    """

    lastBrowserPath = None

    def __init__(self, obj: str) -> None:
        """
        Initializes a SkinnedObj instance for a specific Maya node.

        Args:
            obj (str): The name or full path of the mesh/curve.
        """
        self.name = obj
        self.skinCluster = None
        self.skinData = None
        self.vertCount = 0
        self.infs = []
        self.infColors = {}

        if self.isValid():
            self.vertCount = utils.getVertCount(self.name)
            self.updateSkinData()

    @classmethod
    def create(cls, obj: str) -> 'SkinnedObj':
        """
        Factory method to create a SkinnedObj for an existing node.

        Args:
            obj (str): The Maya object name.

        Returns:
            An initialized instance of the class.
        """
        return cls(obj)

    @classmethod
    def createEmptySkin(cls) -> 'SkinnedObj':
        """
        Factory method to create a SkinnedObj with no associated geometry.

        Returns:
            A "null" instance of the class.
        """
        return cls(None)

    @classmethod
    def _launchFilePicker(
            cls, fileMode: int, caption: str, fileName: str = "", ext: str = "skin",
            okCaption: str = "OK") -> Optional[str]:
        """
        Wraps Maya's fileDialog2 to provide a consistent UI for skin data files.

        Args:
            fileMode (int): Maya file mode (e.g., 1 for Save, 3 for Directory).
            caption (str): Dialog title.
            fileName (str): Default filename.
            ext (str): File extension.
            okCaption (str): Label for the confirmation button.

        Returns:
            The absolute path selected by the user, or None if cancelled.
        """
        if cls.lastBrowserPath is None:
            cls.lastBrowserPath = cmds.workspace(query=True, fullName=True)

        lastPath = cls.lastBrowserPath
        if fileMode != 3:
            lastPath = os.path.join(lastPath, f"{fileName}.{ext}")

        pickedPath = cmds.fileDialog2(
            caption=caption,
            fileMode=fileMode,
            fileFilter=f"*.{ext}",
            startingDirectory=lastPath,
            okCaption=okCaption)

        if pickedPath:
            if fileMode == 3:
                cls.lastBrowserPath = pickedPath[0]
            else:
                cls.lastBrowserPath = os.path.dirname(pickedPath[0])

            return pickedPath[0]

    @staticmethod
    def _findInfByName(longName: str) -> Optional[str]:
        """
        Attempts to resolve an influence name, handling cases where names might be partial or unique short names.

        Returns:
            The resolved name if it exists in the scene, otherwise None.
        """
        shortName = longName.split("|")[-1]
        objs = cmds.ls(shortName)

        if objs:
            if longName in objs:
                return longName
            else:
                return objs[0]

    @staticmethod
    def _getDagPath(obj: str) -> om2.MDagPath:
        """
        Retrieves the MDagPath for a node using API 2.0.

        Args:
            obj (str): The object name.

        Returns:
            The DagPath object representing the node.
        """
        mselectionList = om2.MSelectionList()
        mselectionList.add(obj)
        return mselectionList.getDagPath(0)

    @classmethod
    def _toMfnMesh(cls, mesh: str) -> om2.MFnMesh:
        """
        Returns an MFnMesh function set for the given mesh.

        Args:
            mesh (str): The mesh name.

        Returns:
            The OpenMaya function set.
        """
        dagPath = cls._getDagPath(mesh)
        return om2.MFnMesh(dagPath)

    @classmethod
    def _toMfnNurbsCurve(cls, curve: str) -> om2.MFnNurbsCurve:
        """
        Returns an MFnNurbsCurve function set for the given curve.

        Args:
            curve (str): The curve name.

        Returns:
            The OpenMaya function set.
        """
        dagPath = cls._getDagPath(curve)
        return om2.MFnNurbsCurve(dagPath)

    @classmethod
    def exportAllSkinWeights(cls, deleteSkinCluster: bool, exportFolder: str = None) -> None:
        """
        Batch exports every skinCluster found in the current Maya scene.

        This is a utility method to facilitate scene cleaning or asset migration.
        It identifies the transform associated with every skinCluster and saves a corresponding .skin file.

        Args:
            deleteSkinCluster (bool): If True, deletes the skinCluster node from the object after a successful export (freezing the skinning).
            exportFolder (str, optional): Absolute path to the destination directory. If None, a folder picker is launched.
        """
        if exportFolder is None:
            exportFolder = cls._launchFilePicker(3, "Pick a folder to export all skinClusters to", okCaption="Export")
            if not exportFolder:
                return

        skinClusters = cmds.ls(type="skinCluster")
        if not skinClusters:
            OpenMaya.MGlobal.displayWarning("There are no skinClusters in the scene to export.")
            return

        for skinCluster in skinClusters:
            meshes = cmds.ls(cmds.listHistory(skinCluster) or [], type="mesh")
            if not meshes:
                continue

            transform = cmds.listRelatives(meshes[0], parent=True)[0]
            exportPath = f"{exportFolder}/{transform}.skin"
            skinnedObj = cls.create(transform)
            skinnedObj.exportSkinWeights(exportPath)
            if deleteSkinCluster:
                cmds.delete(transform, ch=True)

    @classmethod
    def importAllSkinWeights(cls, worldSpace, createMissingInfs, importFolder=None):
        """
        Batch imports multiple skin files from a directory into the current scene.

        The method iterates through all '.skin' files in the specified folder, using the filename to identify
        the target mesh in the Maya scene.
        For each match found, it executes a full weight import using the specified spatial and influence settings.

        Args:
            worldSpace (bool): If True, uses spatial mapping (IDW) to transfer weights. If False, imports based on vertex ID order.
            createMissingInfs (bool): If True, automatically creates joint nodes for any influences found in the files that do not exist in the current scene.
            importFolder (str, optional): Absolute path to the directory containing the .skin files. If None, a folder selection dialog is launched.
        """
        if importFolder is None:
            importFolder = cls._launchFilePicker(3, "Pick a folder with skin files to import them", okCaption="Import")
            if not importFolder:
                return

        skinFiles = glob.glob(f"{importFolder}/*.skin")
        if not skinFiles:
            OpenMaya.MGlobal.displayWarning("The folder contains no skin files to import with.")
            return

        for skinPath in skinFiles:
            transform = os.path.basename(skinPath).split(".")[0]
            if not cmds.objExists(transform):
                OpenMaya.MGlobal.displayWarning(f"Unable to find the object to import weights onto: `{transform}`")
                continue

            skinnedObj = SkinnedObj.create(transform)
            skinnedObj.importSkinWeights(filePath=skinPath, worldSpace=worldSpace, createMissingInfs=createMissingInfs)

    def _getPointsFromSpace(self, space: om2.MSpace = om2.MSpace.kWorld) -> om2.MPointArray:
        """
        Retrieves the positions of all vertices or CVs in the specified space.

        Args:
            space (om2.MSpace): The coordinate space to query (World, Local, etc.).

        Returns:
            om2.MPointArray: An array of MPoints containing vertex positions.

        Raises:
            NotImplementedError: If the object type is not a mesh or nurbsCurve.
        """
        if cmds.listRelatives(self.name, shapes=True, type="mesh"):
            mfnMesh = self._toMfnMesh(self.name)
            return mfnMesh.getPoints(space)
        elif cmds.listRelatives(self.name, shapes=True, type="nurbsCurve"):
            mfnNurbsCurve = self._toMfnNurbsCurve(self.name)
            return mfnNurbsCurve.cvPositions(space)
        else:
            raise NotImplementedError(f"This object's type is not supported: {self.name}")

    # TODO: Refactor?
    def _mapToClosestVertexes(
            self, vertsData: dict[int, Any], polygonData: dict[int, tuple[int]],
            vertFilter: list[int] = []) -> dict[int, Any]:
        """
        Interpolates skin weights from external data onto the current mesh.

        This method creates a temporary mesh to find the closest surface points and then uses
        Inverse Distance Weighting (IDW) to blend weights from the source face vertices.

        Args:
            vertsData (dict): Source vertex weights and positions {index: {"world_pos": [...], "weights": {...}}}.
            polygonData (dict): Source face connectivity {faceIndex: (v1, v2, v3...)}.
            vertFilter (list[int]): Optional list of vertex indices to limit the calculation.

        Returns:
            The interpolated weight data formatted for SkinData.

        Raises:
            RuntimeError: If the user cancels the operation via the progress bar.
        """
        weightsData = {}
        filePoints = [
            om2.MPoint(*vertsData[index]["world_pos"])
            for index in sorted(vertsData.keys())
        ]

        # Build a temporary new mesh from the file's positions so that it's exposed to the api.
        tempMfnMesh = om2.MFnMesh()
        for faceIndex in range(len(polygonData)):
            vertIndexes = polygonData[faceIndex]
            polygonPoints = [filePoints[vertIndex] for vertIndex in vertIndexes]
            tempMfnMesh.addPolygon(polygonPoints, mergeVertices=True, pointTolerance=0.01)
        newMesh = om2.MFnDagNode(tempMfnMesh.parent(0)).fullPathName()

        fileMfnMesh = self._toMfnMesh(newMesh)

        try:
            meshPoints = self._getPointsFromSpace()

            with status_progress_bar.StatusProgressBar("Finding closest points", len(meshPoints)) as pbar:
                for vertIndex, point in enumerate(meshPoints):
                    try:
                        # Skip calculations if index is not in the filter.
                        if vertFilter and vertIndex not in vertFilter:
                            continue

                        # Get the closest face.
                        closestPoint = fileMfnMesh.getClosestPoint(point, om2.MSpace.kWorld)
                        faceIndex = closestPoint[1]
                        faceVertexes = polygonData[faceIndex]

                        # Get a distance to each of the face's vertexes.
                        # We're going to divide with these values, so force it to epsilon if it's 0 to avoid a crash.
                        distances = [
                            filePoints[index].distanceTo(closestPoint[0]) or sys.float_info.epsilon
                            for index in faceVertexes
                        ]

                        # Collect all influences used across the vertexes.
                        infs = []
                        for index in faceVertexes:
                            for inf in vertsData[index]["weights"]:
                                if inf not in infs:
                                    infs.append(inf)

                        # Collect each influence's value across the vertexes.
                        infValues = {}
                        for inf in infs:
                            infValues[inf] = []
                            for index in faceVertexes:
                                value = vertsData[index]["weights"].get(inf, 0)
                                infValues[inf].append(value)

                        # Use inverse distance weighting to get each influence's new value.
                        vertWeights = {"weights": {}, "dq": 0}
                        power = 2

                        for inf, values in infValues.items():
                            numerator = sum([
                                val / (dist ** power)
                                for val, dist in zip(values, distances)])

                            weight = sum(
                                [1.0 / (dist ** power)
                                 for dist in distances])

                            newValue = numerator / weight
                            vertWeights["weights"][inf] = newValue

                        weightsData[vertIndex] = vertWeights

                        if pbar.wasCancelled():
                            raise RuntimeError("User cancelled")
                    finally:
                        pbar.next()
        finally:
            if cmds.objExists(newMesh):
                with utils.DisableUndo():
                    cmds.delete(newMesh)

        return weightsData

    def isValid(self) -> bool:
        """
        Checks if the object exists in the current Maya scene.

        Returns:
           True if the object name is set and exists.
        """
        return self.name is not None and cmds.objExists(self.name)

    def hasValidSkin(self) -> bool:
        """
        Checks if the object has both a skinCluster and valid weight data.

        Returns:
            True if skinning exists and data is populated.
        """
        return self.skinCluster is not None and self.hasSkinData()

    def shortName(self) -> str:
        """
        Returns the node name without the full DAG path.

        Returns:
            The name following the last '|' character.
        """
        return self.name.split("|")[-1]

    def updateSkinData(self) -> None:
        """
        Refreshes the internal SkinData container by querying the Maya skinCluster.
        """
        self.skinCluster = None
        self.skinData = SkinData.createEmptySkin()

        if self.isValid():
            self.skinCluster = utils.getSkinCluster(self.name)

            if self.skinCluster:
                self.skinData = SkinData.get(self.skinCluster)
                self.collectInfColors()
                self.infs = self.getAllInfs()

    def isSkinCorrupt(self) -> bool:
        """
        Checks if topology changes were made after the skinCluster was applied.

        A mismatch between the mesh vertex count and the skinCluster's weightList count usually indicates
        the mesh was edited without updating the skinCluster.

        Returns:
            True if vertex count and weight count are out of sync.
        """
        vertCount = utils.getVertCount(self.name)
        weightsCount = len(cmds.getAttr(f"{self.skinCluster}.weightList[*]"))
        return vertCount != weightsCount

    def getAllInfs(self) -> list[str]:
        """
        Retrieves all influences associated with the skinCluster.

        Returns:
            A list of influence names.
        """
        return sorted(utils.getInfs(self.skinCluster))

    def selectInfVertexes(self, infs: list[str]) -> None:
        """
        Selects vertices in the Maya scene that have a non-zero weight to the specified influences.

        Args:
            infs (list[str]): List of influence names to query.
        """
        infsSet = set(infs)
        effectedVerts = set()

        for vertIndex in self.skinData:
            vertInfs = self.skinData[vertIndex]["weights"].keys()

            isEffected = infsSet.intersection(vertInfs)
            if isEffected:
                if utils.isNurbsCurve(self.name):
                    effectedVerts.add(f"{self.name}.cv[{vertIndex}]")
                else:
                    effectedVerts.add(f"{self.name}.vtx[{vertIndex}]")

        cmds.select(list(effectedVerts))

    def floodSkinWeightsToClosest(self) -> None:
        """
        Assigns 100% weight of every vertex to its spatially closest joint.
        This effectively performs a 'hard-skin' operation.
        """
        influences = self.getInfIds()

        infPositions = {
            key: cmds.xform(inf, query=True, worldSpace=True, translation=True)
            for key, inf in influences.items()
        }

        verts = cmds.ls(f"{self.name}.vtx[*]", flatten=True)

        vertInfMappings = {}

        for vertIndex, plug, in enumerate(verts):
            vertPos = cmds.pointPosition(plug, world=True)
            vertPoint = OpenMaya.MPoint(*vertPos)

            closestInfIndex = None
            closestInfDist = 0

            for infIndex in infPositions:
                infPoint = OpenMaya.MPoint(*infPositions[infIndex])
                dist = vertPoint.distanceTo(infPoint)
                if closestInfIndex is None or dist < closestInfDist:
                    closestInfIndex = infIndex
                    closestInfDist = dist

            vertInfMappings[vertIndex] = closestInfIndex

        cmds.setAttr(f"{self.skinCluster}.nw", 0)
        cmds.skinPercent(self.skinCluster, verts, pruneWeights=100, normalize=0)

        for vertIndex, infIndex in vertInfMappings.items():
            weightPlug = f"{self.skinCluster}.weightList[{vertIndex}].weights[{infIndex}]"
            cmds.setAttr(weightPlug, 1)

        cmds.setAttr(f"{self.skinCluster}.nw", 1)
        cmds.skinCluster(self.skinCluster, edit=True, forceNormalizeWeights=True)

    def pruneSkinWeights(self, value: float) -> bool:
        """
        Removes small influence weights from the selection based on a threshold.

        Args:
            value (float): The threshold. Weights below this value are set to 0 and redistributed.

        Returns:
            True if the operation succeeded, False if no vertices were selected.
        """
        flattenList = utils.getVertIndexes(self.name)
        if not flattenList:
            OpenMaya.MGlobal.displayError("No vertexes are selected.")
            return False

        cmds.skinPercent(self.skinCluster, flattenList, pruneWeights=value, normalize=True)

        return True

    def pruneMaxInfs(self, maxInfCount: int, vertFilter: list[int] = []) -> bool:
        """
        Limits the number of influences per vertex by pruning the smallest weights.

        Args:
            maxInfCount (int): The maximum allowed number of influences per vertex.
            vertFilter (list[int], optional): Indices to restrict the operation to.

        Returns:
            True on success, False if the filter/selection is empty.
        """
        if not vertFilter:
            OpenMaya.MGlobal.displayError("No vertexes are selected.")
            return False

        for vertIndex in self.skinData:
            if vertFilter and vertIndex not in vertFilter:
                continue

            sortedInfs = [
                inf for inf, value in sorted(self.skinData[vertIndex]["weights"].items(), key=lambda item: item[1])]

            for inf in sortedInfs:
                infsCount = len(self.skinData[vertIndex]["weights"])
                if infsCount <= maxInfCount:
                    break

                locked = cmds.getAttr(f"{inf}.lockInfluenceWeights")
                if locked:
                    continue

                self.skinData.updateWeightValue(vertIndex, inf, 0)

        return True

    def mirrorSkinWeights(
            self, mirrorMode: str, mirrorInverse: bool, surfaceAssociation: str, infAssociation: str = None,
            vertFilter: list[int] = []) -> None:
        """
        Wraps Maya's copySkinWeights to mirror weights across a specific axis.

        Args:
            mirrorMode (str): The axis to mirror (e.g., 'XY', 'YZ', 'XZ').
            mirrorInverse (bool): Whether to mirror from positive to negative.
            surfaceAssociation (str): Method for matching points (e.g., 'closestPoint').
            infAssociation (str, optional): Method for matching joints. Defaults to 'closestJoint'.
            vertFilter (list[int], optional): Indices of vertices to mirror.
        """
        objs = self.name
        if vertFilter:
            objs = [
                f"{self.name}.vtx[{index}]"
                for index in vertFilter
            ]

        if infAssociation is None:
            infAssociation = "closestJoint"

        cmds.copySkinWeights(
            objs,
            mirrorMode=mirrorMode,
            mirrorInverse=mirrorInverse,
            surfaceAssociation=surfaceAssociation,
            influenceAssociation=[infAssociation, "closestJoint"])

    def displayInf(self, influence: str, colorStyle: ColorTheme = ColorTheme.Max, vertFilter: list[int] = []) -> None:
        """
        Updates the viewport vertex colors to visualize weights for a single influence.
        Supports different color themes to mimic different visualizations.

        Args:
            influence (str): The influence name to visualize.
            colorStyle (ColorTheme): The theme determining the color ramp.
            vertFilter (list[int], optional): Restricted list of vertex indices to colorize.
        """
        if colorStyle == ColorTheme.Max:
            # Max
            lowRgb = [0, 0, 1]
            midRgb = [0, 1, 0]
            endRgb = [1, 0, 0]
            noRgb = [0.05, 0.05, 0.05]
            fullRgb = [1, 1, 1]
        elif colorStyle == ColorTheme.Maya:
            # Maya
            lowRgb = [0.5, 0, 0]
            midRgb = [1, 0.5, 0]
            endRgb = [1, 1, 0]
            noRgb = [0, 0, 0]
            fullRgb = [1, 1, 1]
        else:
            lowRgb = [0, 0, 0]
            midRgb = [0, 0, 0]
            endRgb = [0, 0, 0]
            noRgb = [0, 0, 0]
            fullRgb = [0, 0, 0]

        vertColors = []
        vertIndexes = []

        for vertIndex in self.skinData:
            if vertFilter and vertIndex not in vertFilter:
                continue

            weightsData = self.skinData[vertIndex]["weights"]

            if influence in weightsData:
                weightValue = weightsData[influence]
                rgb = utils.getWeightColor(
                    weightValue,
                    startColor=lowRgb,
                    midColor=midRgb,
                    endColor=endRgb,
                    fullColor=fullRgb)
            else:
                rgb = noRgb

            vertColors.append(rgb)
            vertIndexes.append(vertIndex)

        utils.applyVertColors(self.name, vertColors, vertIndexes)

    def displayMultiColorInfs(self, vertFilter: list[int] = []) -> None:
        """
        Visualizes all influences simultaneously by blending their unique colors.
        This visualization style is inspired by Softimage, where each joint is assigned a specific color.
        The resulting vertex color is the weighted average of all influences affecting that vertex.

        Args:
            vertFilter (list[int], optional): A list of vertex indices to operate on. Defaults to all vertices.
        """

        if self.infColors is None:
            self.collectInfColors()

        vertColors = []
        vertIndexes = []

        for vertIndex in self.skinData:
            if vertFilter and vertIndex not in vertFilter:
                continue

            finalColor = [0, 0, 0]

            for inf, weight in self.skinData[vertIndex]["weights"].items():
                infColor = self.infColors.get(inf)
                finalColor[0] += infColor[0] * weight
                finalColor[1] += infColor[1] * weight
                finalColor[2] += infColor[2] * weight

            vertColors.append(finalColor)
            vertIndexes.append(vertIndex)

        utils.applyVertColors(self.name, vertColors, vertIndexes)

    def displayMaxInfs(self, maxInfCount: int, vertFilter: list[int] = []) -> None:
        """
        Highlights vertices that exceed a specific influence count threshold.

        Vertices exceeding the limit are colored bright red, while those within the limit are colored black.
        This is used for technical cleanup to ensure game engine compatibility.

        Args:
            maxInfCount (int): The maximum allowed influence count.
            vertFilter (list[int], optional): A list of vertex indices to operate on.
        """
        vertColors = []
        vertIndexes = []

        for vertIndex in self.skinData:
            if vertFilter and vertIndex not in vertFilter:
                continue

            infCount = len(self.skinData[vertIndex]["weights"])

            if infCount > maxInfCount:  # Over the count.
                finalColor = [1, 0, 0]
            else:
                finalColor = [0, 0, 0]  # Under the count.

            vertColors.append(finalColor)
            vertIndexes.append(vertIndex)

        utils.applyVertColors(self.name, vertColors, vertIndexes)

    def getVertexNeighbors(self, vertexId: int, level: int = 2) -> list[int]:
        """
        Finds neighboring vertices using a breadth-first search (BFS) approach.

        Args:
            vertexId (int): The starting vertex index.
            level (int): The number of edge rings to expand outward. Defaults to 2.

        Returns:
            A list of unique neighboring vertex indices.
        """
        sel = om2.MSelectionList()
        sel.add(self.name)
        dagPath = sel.getDagPath(0)

        vertexUtil = om2.MItMeshVertex(dagPath)
        vertexUtil.setIndex(vertexId)

        neighbors = set()
        visited = {vertexId}
        queue = deque([(vertexId, 0)])

        while queue:
            currentVertId, currentLevel = queue.popleft()
            if currentLevel >= level:
                continue

            vertexUtil.setIndex(currentVertId)
            currentNeighbors = vertexUtil.getConnectedVertices()

            for neighborId in currentNeighbors:
                if neighborId not in visited:
                    visited.add(neighborId)
                    neighbors.add(neighborId)
                    queue.append((neighborId, currentLevel + 1))

        return list(neighbors)

    def smoothSkinWeights(
            self, vertexList: list[int], normalizeWeights: bool = True, strength: float = 1.0,
            level: int = 1, allowNewInfs: bool = True) -> None:
        """
        Averages skin weights between a vertex and its immediate neighbors.
        It calculates an average for every influence across the sampled area and blends it with the original
        weight based on the strength value.

        Args:
            vertexList (list[int]): Indices of vertices to smooth.
            normalizeWeights (bool): Whether to force normalization after smoothing.
            strength (float): The blend factor between original and smoothed weights (0.0 to 1.0).
            level (int): Depth of neighbor search for sampling.
            allowNewInfs (bool): If False, vertices will only average weights from influences they already had (prevents "bleeding" of new joints).
        """
        # Get the MFnDependencyNode for the skin cluster
        skinSelection = om2.MSelectionList()
        skinSelection.add(self.skinCluster)
        skinClusterMObj = skinSelection.getDependNode(0)
        skinNode = om2.MFnDependencyNode(skinClusterMObj)

        # Get the plugs for the 'weightList' and 'weights' attributes
        weightListPlug = skinNode.findPlug('weightList', False)

        # Get the influence objects
        mfnSkinCluster = oma2.MFnSkinCluster(skinClusterMObj)
        infMdagPaths = mfnSkinCluster.influenceObjects()
        infCount = len(infMdagPaths)
        infNames = [
            infMdagPaths[i].partialPathName()
            for i in range(infCount)
        ]

        weightsToSet = {}
        for vertexId in vertexList:
            # Get the neighbors
            neighbors = self.getVertexNeighbors(vertexId, level=level)  # TODO: Should just include the vert id in the return value
            vertInfs = list(self.skinData[vertexId]["weights"])

            # Combine the current vertex and its neighbors
            vertsToSample = [vertexId] + neighbors

            # Get the average weights for each influence object
            averageWeights = {}
            for infId, infName in enumerate(infNames):
                if not allowNewInfs:
                    if infName not in vertInfs:
                        continue

                totalWeight = 0.0
                for sampleVertId in vertsToSample:
                    weightPlug = weightListPlug.elementByLogicalIndex(sampleVertId).child(0).elementByLogicalIndex(infId)
                    weightValue = weightPlug.asDouble()
                    totalWeight += weightValue

                if totalWeight > 0:
                    oldWeight = self.skinData[vertexId]["weights"].get(infName, 0)
                    smoothWeight = totalWeight / len(vertsToSample)
                    newWeight = (oldWeight * (1.0 - strength)) + (smoothWeight * strength)
                    averageWeights[infName] = newWeight

            weightsToSet[vertexId] = averageWeights

        # Set weights
        for vertIndex, weights in weightsToSet.items():
            self.skinData[vertIndex]["weights"] = weights

        self.applyCurrentSkinWeights(vertexList, normalize=normalizeWeights)

    def selectEdges(self, inf: str, level: int) -> None:
        """
        Selects vertexes of the supplied influence's border.
        Effectively, all vertexes that are adjacent to another vert that doesn't contain the influence.

        Args:
            inf (str): The influence to get the selection from.
            level (int): The level of vertexes to select from the border.
        """
        vertsToSelect = []

        for vertexId in self.skinData:
            if inf not in self.skinData[vertexId]["weights"]:
                continue

            neighbors = self.getVertexNeighbors(vertexId, level=level)
            vertsWithMissingInf = [neighbor for neighbor in neighbors if inf not in self.skinData[neighbor]["weights"]]
            if vertsWithMissingInf:
                vertsToSelect.append(f"{self.name}.vtx[{vertexId}]")

        cmds.select(vertsToSelect)

    def hideVertColors(self) -> None:
        """
        Disables vertex color display in the viewport and cleans up temporary color nodes created by the tool.
        """
        if self.isValid():
            utils.toggleDisplayColors(self.name, False)
            utils.deleteTempInputs(self.name)

    def hasSkinData(self) -> bool:
        """
        Checks if the internal skinData container is populated with weight values.

        Returns:
            True if skinData is present and contains entries, False otherwise.
        """
        if self.skinData is not None and self.skinData.data:
            return True
        return False

    def getInfIds(self) -> dict[int, str]:
        """
        Retrieves a mapping of influence indices to their node names for the active skinCluster.

        Returns:
            A dictionary where keys are influence indices and values are joint names.
        """
        return utils.getInfIds(self.skinCluster)

    def collectInfColors(self, sat:int = 250, brightness: int = 150) -> None:
        """
        Generates a unique RGB color for every influence in the skin cluster.
        Uses HSV color space to ensure a diverse spread of hues, which is then converted to RGB for viewport display.
        The random seed is fixed to 0 to ensure color consistency across sessions.

        Args:
            sat (int): The saturation value (0-255).
            brightness (int): The value/brightness (0-255).
        """
        infs = self.getAllInfs()
        random.seed(0)
        random.shuffle(infs)

        infColors = {}

        hueStep = 360.0 / (len(infs))

        for i, inf in enumerate(infs):
            color = QtGui.QColor()
            color.setHsv(hueStep * i, sat, brightness)
            color.toRgb()

            infColors[inf] = [
                color.red() / 255.0,
                color.green() / 255.0,
                color.blue() / 255.0]

        self.infColors = infColors

    def applyCurrentSkinWeights(self, vertIndexes: list[int], normalize: bool = False, displayProgress: bool = False) -> None:
        """
        Pushes the current internal skinData weights back onto the Maya skinCluster node.

        The process temporarily disables Maya's internal normalization to allow for precise, manual weight setting per influence.
        It also applies dual-quaternion blend weights.

        Args:
            vertIndexes (list[int]): A list of vertex indices to update.
            normalize (bool): If True, triggers a force-normalize pass on the skinCluster after values are set.
            displayProgress (bool): If True, shows a progress bar in the Maya UI.
        """
        # Get influence info to map with
        infData = self.getInfIds()
        infIds = list(infData.keys())
        infNames = list(infData.values())

        # Remove all existing weights
        if utils.isNurbsCurve(self.name):
            plug = f"{self.name}.cv"
        else:
            plug = f"{self.name}.vtx"

        selectedVertexes = [
            f"{plug}[{index}]"
            for index in vertIndexes
        ]

        cmds.setAttr(f"{self.skinCluster}.nw", 0)
        cmds.skinPercent(self.skinCluster, selectedVertexes, prw=100, nrm=0)

        if displayProgress:
            pbar = status_progress_bar.StatusProgressBar("Setting skin weights", len(vertIndexes))
            pbar.start()

        try:
            # Apply weights per vert
            for vertIndex in vertIndexes:
                weightListAttr = f"{self.skinCluster}.weightList[{vertIndex}]"

                for infName, weightValue in self.skinData[vertIndex]["weights"].items():
                    index = infNames.index(infName)
                    weightAttr = f".weights[{infIds[index]}]"
                    cmds.setAttr(f"{weightListAttr}{weightAttr}", weightValue)

                # Apply dual-quarternions
                dqValue = self.skinData[vertIndex]["dq"]
                cmds.setAttr(f"{self.skinCluster}.bw[{vertIndex}]", dqValue)

                if displayProgress:
                    if pbar.wasCancelled():
                        break
                    pbar.next()
        finally:
            if displayProgress:
                pbar.end()

        # Re-enable weights normalizing
        cmds.setAttr(f"{self.skinCluster}.nw", 1)

        if normalize:
            cmds.skinCluster(self.skinCluster, edit=True, forceNormalizeWeights=True)

    def serialize(self) -> dict[str, Any]:
        """
        Packages all skinning information and mesh topology into a serializable dictionary.
        This captures:
            - Vertex weights and world-space positions.
            - Polygon face connectivity (for spatial mapping on import).
            - Influence matrices and names.
            - SkinCluster settings (max influences, skinning method).

        Returns:
            A complete data package for the mesh skinning.

        Raises:
            RuntimeError: If no skinCluster is found or if the user cancels the progress bar during position collection.
        """
        if not self.hasValidSkin():
            raise RuntimeError(f"Unable to detect a skinCluster on '{self.name}'.")

        skinData = self.skinData.copy()
        meshPoints = self._getPointsFromSpace()

        with status_progress_bar.StatusProgressBar("Saving vert positions", len(meshPoints)) as pbar:
            for vertIndex, pnt in enumerate(meshPoints):
                skinData[vertIndex]["world_pos"] = [pnt.x, pnt.y, pnt.z]

                if pbar.wasCancelled():
                    raise RuntimeError("User cancelled")

                pbar.next()

        polygonData = {}
        mfnMesh = self._toMfnMesh(self.name)
        for polyIndex in range(mfnMesh.numPolygons):
            vertIndexes = mfnMesh.getPolygonVertices(polyIndex)
            polygonData[polyIndex] = tuple(vertIndexes)

        infData = {}
        infIds = self.getInfIds()

        with status_progress_bar.StatusProgressBar("Saving influence positions", len(infIds)) as pbar:
            for infId, inf in infIds.items():
                infData[infId] = {
                    "name": inf,
                    "world_matrix": cmds.xform(inf, q=True, ws=True, m=True)
                }

                if pbar.wasCancelled():
                    raise RuntimeError("User cancelled")

                pbar.next()

        return {
            "version": constants.EXPORT_VERSION,
            "object": self.name,
            "verts": skinData.data,
            "influences": infData,
            "polygons": polygonData,
            "skin_cluster": {
                "name": self.skinCluster,
                "vert_count": cmds.polyEvaluate(self.name, vertex=True),
                "influence_count": len(infIds),
                "max_influences": cmds.getAttr(f"{self.skinCluster}.maxInfluences"),
                "skinning_method": cmds.getAttr(f"{self.skinCluster}.skinningMethod"),
                "dqs_support_non_rigid": cmds.getAttr(f"{self.skinCluster}.dqsSupportNonRigid")
            }
        }

    def importSkinWeights(self, filePath: str = None, worldSpace: bool = False, createMissingInfs: bool = True) -> bool:
        """
        Imports skin weights from an external .skin file onto the current object.

        This method supports partial imports (if vertices are selected) and can automatically handle topology mismatches by using spatial mapping.
        If influences from the file are missing in the scene, it can optionally recreate them as joints at their original world positions.

        Args:
            filePath (str, optional): Absolute path to the .skin file. If None, a file dialog is launched.
            worldSpace (bool): If True, uses spatial mapping (IDW) to transfer weights. If False, imports based on vertex ID order.
            createMissingInfs (bool): If True, creates new joint nodes for any influences found in the file that don't exist in the scene.

        Returns:
            True if the import was successful, False if cancelled.

        Raises:
            RuntimeError: If no object is selected, if vertex counts mismatch (in non-worldSpace mode),
                          or if influences are missing while createMissingInfs is False.
        """
        if not self.isValid():
            raise RuntimeError("Need to pick an object first.")

        if filePath is None:
            filePath = self._launchFilePicker(1, "Import skin", okCaption="Import")
            if not filePath:
                return False

        vertFilter = utils.extractIndexes(utils.getVertIndexes(self.name))

        # Must have an existing skin cluster if we're only applying on some vertexes.
        if vertFilter:
            if not self.hasValidSkin():
                raise RuntimeError("A skinCluster must already exist when importing weights onto vertexes")

        with open(filePath, "rb") as f:
            skinData = cPickle.loads(f.read())

            # Keys need to be converted to ints.
            skinData["verts"] = {
                int(key): value
                for key, value in skinData["verts"].items()
            }

        # Rename influences to match scene.
        with status_progress_bar.StatusProgressBar("Matching influences", len(skinData["verts"])) as pbar:
            infs = {}

            for index in skinData["verts"]:
                for oldName in list(skinData["verts"][index]["weights"]):
                    if oldName not in infs:
                        infs[oldName] = self._findInfByName(oldName) or oldName.split("|")[-1]
                    skinData["verts"][index]["weights"][infs[oldName]] = skinData["verts"][index]["weights"].pop(oldName)

                if pbar.wasCancelled():
                    raise RuntimeError("User cancelled")

                pbar.next()

        if worldSpace:
            weightsData = self._mapToClosestVertexes(skinData["verts"], skinData["polygons"], vertFilter)
        else:
            # Bail if vert count with file and object don't match (import via point order only)
            fileVertCount = skinData["skin_cluster"]["vert_count"]
            objVertCount = cmds.polyEvaluate(self.name, vertex=True)
            if fileVertCount != objVertCount:
                raise RuntimeError(f"Vert count doesn't match. (Object: {objVertCount}, File: {fileVertCount})")
            weightsData = skinData["verts"]

        # Get influences from file
        skinJoints = []

        for infId, infData in skinData["influences"].items():
            infName = infData["name"]
            infShortName = infName.split("|")[-1]
            inf = self._findInfByName(infName)

            if inf is None:
                if not createMissingInfs:
                    raise RuntimeError(f"Missing influence '{infShortName}'")

                # Create new joint if influence is missing
                inf = cmds.createNode("joint", name=infShortName, skipSelect=True)
                cmds.xform(inf, ws=True, m=infData["world_matrix"])
                OpenMaya.MGlobal.displayWarning(f"Created '{infShortName}' because it was missing.")

            skinJoints.append(inf)

        if vertFilter:
            # Add any missing influences onto existing skin so that we can maintain weights.
            infs = self.getAllInfs()

            for inf in skinJoints:
                if inf not in infs:
                    cmds.skinCluster(self.skinCluster, edit=True, lockWeights=True, weight=0, addInfluence=inf)
                    cmds.setAttr(f"{inf}.lockInfluenceWeights", False)
        else:
            # Create new skin cluster with influences.
            if self.skinCluster and cmds.objExists(self.skinCluster):
                cmds.delete(self.skinCluster)

            self.skinCluster = utils.buildSkinCluster(
                self.name, skinJoints,
                maxInfs=skinData["skin_cluster"]["max_influences"],
                skinMethod=skinData["skin_cluster"]["skinning_method"],
                dqsSupportNonRigid=skinData["skin_cluster"]["dqs_support_non_rigid"],
                name=skinData["skin_cluster"]["name"])

        # Define all verts to apply weights to.
        vertIndexes = [
            vertIndex
            for vertIndex in weightsData
            if not vertFilter or vertIndex in vertFilter
        ]

        self.skinData.data = weightsData
        self.collectInfColors()
        self.infs = self.getAllInfs()
        self.applyCurrentSkinWeights(vertIndexes, displayProgress=True)

        return True

    def exportSkinWeights(self, filePath: str = None) -> Optional[str]:
        """
        Serializes and saves the current object's skin weights to a file.

        The data is saved using cPickle for performance and includes vertex positions, weights, and influence matrices.

        Args:
            filePath (str, optional): Absolute path to the destination file. If None, a file dialog is launched.

        Returns:
            The path to the saved file if successful, else None.

        Raises:
            RuntimeError: If the object is invalid or has no skinCluster.
        """
        if not self.isValid():
            raise RuntimeError("Need to pick a skinned object first.")

        if not self.hasValidSkin():
            raise RuntimeError("Picked object needs to have a skin cluster to export.")

        if filePath is None:
            filePath = self._launchFilePicker(0, "Export skin", fileName=self.name.split("|")[-1], okCaption="Export")
            if not filePath:
                return None

        skinData = self.serialize()

        outputDir = os.path.dirname(filePath)
        if not os.path.exists(outputDir):
            os.makedirs(outputDir)

        with open(filePath, "wb") as f:
            f.write(cPickle.dumps(skinData))

        return filePath

    def addInfsToVerts(self, infs: list[str], vertIndexes: list[int], weightValue: float = 0.001) -> None:
        """
        Add influences to supplied vertexes by setting a very low value, so they techincally get added in without impacting existing weights.

        Args:
            infs (list[str]): A list of influences to add.
            vertIndexes (list[int]): A list of vertexes to add the new influences to.
            weightValue (float): The weight value to set the new influences to.
        """
        for inf in infs:
            for vertIndex in vertIndexes:
                skinWeightsData = self.skinData[vertIndex]["weights"]
                if skinWeightsData.get(inf) is None:
                    self.skinData.updateWeightValue(vertIndex, inf, weightValue)
