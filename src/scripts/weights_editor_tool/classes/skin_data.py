import copy
from typing import Any

from maya import cmds
from maya.api import OpenMaya as om2
from maya.api import OpenMayaAnim as oma2

from weights_editor_tool.enums import WeightOperation
from weights_editor_tool import weights_editor_utils as utils


class SkinData:
    """
    A container and manager for skin cluster weight data.

    This class abstracts the complex nested weight data of a Maya skinCluster into a serializable dictionary format.
    It provides methods for querying, copying, and mathematically manipulating weights while maintaining
    normalization and respecting influence locks.

    Attributes:
        data (dict): The underlying weight storage.
                     Format: {vertIndex: {"weights": {infName: weightValue...}, "dq": float}}
    """

    def __init__(self, data):
        """
        Initializes the SkinData instance with existing weight data.
        """
        self.data = data

    def __iter__(self):
        for vertIndex in self.data:
            yield vertIndex

    def __getitem__(self, vertIndex):
        return self.data[vertIndex]

    def __setitem__(self, vertIndex, value):
        self.data[vertIndex] = value

    @classmethod
    def createEmptySkin(cls) -> 'SkinData':
        """
        Creates an instance of SkinData with no initial data.

        Returns:
            An empty container.
        """
        return cls(None)

    @classmethod
    def get(cls, skinCluster: str) -> 'SkinData':
        """
        Convenience method to create a SkinData instance directly from a Maya skinCluster node.

        Args:
            skinCluster (str): The name of the skinCluster in the scene.

        Returns:
            An instance populated with current scene data.
        """
        return cls(cls.getData(skinCluster))

    @staticmethod
    def getData(skinCluster: str) -> dict[int, Any]:
        """
        Fetches all weight and blend weight (DQ) data.
        This is optimized for performance, fetching all weights in large chunks rather than querying vertex by vertex.

        Returns:
            A mapping of vertex indices to weight and dual-quat data.
        """
        # Get skinCluster object.
        mselectionList = om2.MSelectionList()
        mselectionList.add(skinCluster)
        skinClusterMObj = mselectionList.getDependNode(0)
        mfnSkinCluster = oma2.MFnSkinCluster(skinClusterMObj)

        shapeDagPath = mfnSkinCluster.getPathAtIndex(0)
        if not shapeDagPath.isValid():
            return {}

        # Get current influence ids.
        infIds = utils.getInfIds(skinCluster)
        infIdIndexes = list(infIds)
        infCount = len(infIds)

        # Query all skin and blend weights.
        singleIndexComponent = om2.MFnSingleIndexedComponent()
        components = singleIndexComponent.create(om2.MFn.kMeshVertComponent)
        weightsData = mfnSkinCluster.getWeights(shapeDagPath, components)
        blendWeightsData = mfnSkinCluster.getBlendWeights(shapeDagPath, components)

        # Parse through weights data to dump it into a dictionary.
        # Each vert will include a value for every influence, so exclude the influences that are 0 (aren't weighted).
        skinWeights = {}

        for vertIndex, chunkIndex in enumerate(range(0, len(weightsData[0]), infCount)):
            skinWeights[vertIndex] = {"weights": {}, "dq": blendWeightsData[vertIndex]}

            for index, value in enumerate(weightsData[0][chunkIndex:chunkIndex+infCount]):
                if value > 0:
                    inf = infIds[infIdIndexes[index]]
                    skinWeights[vertIndex]["weights"][inf] = value

        return skinWeights

    def copy(self) -> 'SkinData':
        """
        Creates a deep copy of the current skin weight data.

        Returns:
            A new instance with identical weight values.
        """
        return self.__class__(copy.deepcopy(self.data))

    def copyVertex(self, vertIndex: int) -> dict[str, Any]:
        """
        Retrieves a deep copy of weight data for a single vertex.

        Args:
            vertIndex (int): The vertex index to copy.

        Returns:
            The weight and DQ data for that vertex.
        """
        return copy.deepcopy(self.data[vertIndex])

    def getVertexInfs(self, vertIndex: int) -> list[str]:
        """
        Returns a list of influence names that have non-zero weights on the specified vertex.

        Args:
            vertIndex (int): The vertex index to query.

        Returns:
            Influence names.
        """
        try:
            return list(self.data[vertIndex]["weights"].keys())
        except KeyError:
            return []

    def calculateNewValue(self, inputValue: float, vertIndex: int, inf: str, weightOperation: WeightOperation) -> tuple[float, float]:
        """
        Calculates what the new weight should be based on the operation type before it is applied.

        Args:
            inputValue (float): The user's input value.
            vertIndex (int): Target vertex index.
            inf (str): Target influence name.
            weightOperation (WeightOperation): Type of method to calculate with.

        Returns:
            The (oldValue, calculatedNewValue) pair.
        """
        oldValue = self.data[vertIndex]["weights"].get(inf) or 0.0

        if weightOperation == WeightOperation.Absolute:
            return oldValue, inputValue
        elif weightOperation == WeightOperation.Relative:
            return oldValue, utils.clamp(0.0, 1.0, oldValue + inputValue)
        elif weightOperation == WeightOperation.Percentage:
            return oldValue, utils.clamp(0.0, 1.0, oldValue * inputValue)
        else:
            raise NotImplementedError("Weight operation hasn't been implemented")

    def updateWeightValue(self, vertIndex: int, infName: str, newValue: float):
        """
        Updates a specific influence's weight and normalizes the remaining weights.

        This method ensures the sum of weights for the vertex remains 1.0 by distributing the delta (difference)
        proportionally across all other unlocked influences.
        If an influence is locked in Maya, it is completely ignored during redistribution.

        Args:
            vertIndex (int): The vertex to modify.
            infName (str): The influence whose weight is being set.
            newValue (float): The target weight value (0.0 to 1.0).

        Raises:
            ValueError: If the newValue is outside the 0.0 to 1.0 range.
        """
        if newValue < 0 or newValue > 1:
            raise ValueError("Value needs to be within 0.0 to 1.0.")

        # Ignore if trying to set to a locked influence
        isInfLocked = cmds.getAttr(f"{infName}.lockInfluenceWeights")
        if isInfLocked:
            return

        skinWeightsData = self.data[vertIndex]["weights"]

        # Add in influence with 0 weight if it's not already in
        if infName not in skinWeightsData:
            skinWeightsData[infName] = 0

        # Get total of all unlocked weights
        total = 0
        unlockCount = 0
        for inf in skinWeightsData:
            isLocked = cmds.getAttr(f"{inf}.lockInfluenceWeights")
            if not isLocked:
                total += skinWeightsData[inf]
                unlockCount += 1

        if unlockCount > 1:
            # New value must not exceed total
            newValue = min(newValue, total)

            # Distribute weights
            dif = (total - newValue) / (total - skinWeightsData[infName])

            for inf in skinWeightsData:
                isLocked = cmds.getAttr(f"{inf}.lockInfluenceWeights")
                if isLocked:
                    continue

                if inf == infName:
                    skinWeightsData[inf] = newValue
                else:
                    skinWeightsData[inf] *= dif

        for key in list(skinWeightsData.keys()):
            if utils.areValuesCloseEnough(0.0, skinWeightsData[key]):
                skinWeightsData.pop(key)

        # Force weight to be 1 if there's only one influence left
        if len(skinWeightsData) == 1:
            key = list(skinWeightsData.keys())[0]
            skinWeightsData[key] = 1.0
