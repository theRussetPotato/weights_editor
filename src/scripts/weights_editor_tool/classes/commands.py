import copy
from typing import Callable, Any

import maya.cmds as cmds

from weights_editor_tool.qt import QtWidgets
from weights_editor_tool.classes.skin_data import SkinData
from weights_editor_tool.classes.skinned_obj import SkinnedObj
from weights_editor_tool.widgets import weights_table_view


class CommandEditWeights:
    """
    Maya-integrated command for editing skin weights.

    This class is designed to be executed via `cmds.weightsEditorAction`.
    It handles the application of weight data to the mesh while ensuring the tool's ui stays synchronized
    if the modified object is the one currently being viewed.
    """

    def __init__(self, weightsEditorClass: 'WeightsEditor', description: str, obj: str, oldSkinData: SkinData,
                 newSkinData: SkinData, vertIndexes: list[int], tableSelection: dict[str, Any],
                 skipFirstRedo: bool = False, parent: QtWidgets.QWidget = None) -> None:
        """
        Initializes the command and registers it with Maya's undo system.

        Args:
            weightsEditorClass (WeightsEditor): The class type used to retrieve the active instance.
            description (str): The label for the Maya undo queue.
            obj (str): Name of the mesh being modified.
            oldSkinData (SkinData): Weights to restore on undo.
            newSkinData (SkinData): Weights to apply on redo.
            vertIndexes (list[int]): Indices of affected vertices.
            tableSelection (dict): UI selection state to restore.
            skipFirstRedo (bool): If True, skips the first redo call.
            parent (QWidget, optional): Optional parent widget.
        """

        self.newSkinData = newSkinData
        self.description = description
        self._weightsEditorClass = weightsEditorClass
        self._skipFirstRedo = skipFirstRedo
        self._obj = obj
        self._oldSkinData = oldSkinData
        self._vertIndexes = vertIndexes
        self._tableSelection = tableSelection

        cmds.weightsEditorAction(self)

    def _isIntefaceUsingObj(self) -> None:
        """
        Returns True if the interface is open with the current object, otherwise returns False.
        """
        # Skip if there's no active interface.
        instance = self._weightsEditorClass.getCurrentInstance()
        if not instance:
            return False

        # Skip if there's no active skinned object in the interface.
        if not instance.obj.isValid():
            return False

        # Check if the interface is editing this node.
        # This determines if we need to also update the interface.
        return self._obj == instance.obj.name

    def _editSkinWeights(self, skinData: SkinData) -> None:
        """
        Internal logic to apply weights to the mesh and refresh the UI.
        """
        # Skip the object to edit no longer exists.
        if not self._obj or not cmds.objExists(self._obj):
            return

        isIntefaceUsingObj = self._isIntefaceUsingObj()

        if isIntefaceUsingObj:
            # Prepare the weights view to be updated.
            instance = self._weightsEditorClass.getCurrentInstance()
            weightsView = instance.getActiveWeightsView()
            oldColumnCount = weightsView.horizontalHeader().count()
            weightsView.beginUpdate()

            # Edit and apply the skin weights.
            instance.obj.skinData = copy.deepcopy(skinData)
            instance.obj.applyCurrentSkinWeights(self._vertIndexes, normalize=True)

            # Update the weights view to reflect the changes.
            instance.updateVertColors(vertFilter=self._vertIndexes)
            instance.collectDisplayInfs()
            weightsView.loadTableSelection(self._tableSelection)
            weightsView.colorHeaders()
            weightsView.endUpdate()

            if isinstance(weightsView, weights_table_view.TableView):
                if weightsView.horizontalHeader().count() != oldColumnCount:
                    weightsView.fitHeadersToContents()
        else:
            # If the interface is not defined then just update the skin weights.
            skinnedObj = SkinnedObj.create(self._obj)
            skinnedObj.skinData = copy.deepcopy(skinData)
            skinnedObj.applyCurrentSkinWeights(self._vertIndexes, normalize=True)

    def doIt(self) -> None:
        """Initial command execution."""
        pass

    def redoIt(self) -> None:
        """Executes the weight change, respecting the skipFirstRedo flag."""
        if self._skipFirstRedo:
            self._skipFirstRedo = False
        else:
            self._editSkinWeights(self.newSkinData)

    def undoIt(self) -> None:
        """Reverts the weights to the captured previous state."""
        self._editSkinWeights(self._oldSkinData)


class CommandLockInfs(object):
    """
    Maya-integrated command to toggle the 'lock' state of influences.
    Wraps the modification of the 'lockInfluenceWeights' attribute so it can be undone/redone.
    It handles both the Maya node attributes and the WeightsEditor UI state.
    """

    def __init__(self, weightsEditorClass: 'WeightsEditor', description: str, infs: list[str], enabled: bool,
                 parent: QtWidgets.QWidget = None) -> None:
        """
        Initializes the command and snapshots existing lock states.

        Args:
            weightsEditorClass (WeightsEditor): The class type of the editor.
            description (str): The label for the Maya undo queue.
            infs (list[str]): Names of the influence nodes to modify.
            enabled (bool): The target lock state for redo.
        """
        super(CommandLockInfs, self).__init__()

        self.description = description
        self._weightsEditorClass = weightsEditorClass
        # Get influence name and its old lock state: {infName, lockState}
        self._oldLockStates = {inf: cmds.getAttr(f"{inf}.lockInfluenceWeights") for inf in infs}
        self._newLockState = enabled

        cmds.weightsEditorAction(self)

    def _setInfLocks(self, useNewLockState):
        """
        Applies lock states directly to the Maya influence nodes.

        Args:
            useNewLockState (bool): If True, applies the new 'enabled' value.
                                    If False, restores the original values.
        """
        for inf, oldLockState in self._oldLockStates.items():
            if not cmds.objExists(inf):
                continue

            if useNewLockState:
                lockState = self._newLockState
            else:
                lockState = oldLockState

            cmds.setAttr(f"{inf}.lockInfluenceWeights", lockState)

    def _updateInterface(self):
        """
        Synchronizes the tool's ui with the current state of Maya nodes.
        Ensures the influence list and table view reflect the actual 'lock' values found on the joints.
        """
        # Skip if there's no active interface.
        instance = self._weightsEditorClass.getCurrentInstance()
        if not instance:
            return

        # Skip if there's no active skinned object in the interface.
        if not instance.obj.isValid():
            return

        weightsView = instance.getActiveWeightsView()
        try:
            weightsView.beginUpdate()
            instance.infListView.beginUpdate()

            for inf in self._oldLockStates:
                # Skip if the influence doesn't exist.
                if not cmds.objExists(inf):
                    continue

                # Skip if the influence is not part of the skin.
                if inf not in instance.obj.infs:
                    continue

                # Set the influence's lock state to the interface.
                lockState = cmds.getAttr(f"{inf}.lockInfluenceWeights")
                infIndex = instance.obj.infs.index(inf)
                instance.locks[infIndex] = lockState
        finally:
            weightsView.endUpdate()
            instance.infListView.endUpdate()

    def doIt(self):
        """Initial command execution."""
        pass

    def redoIt(self):
        """Applies new lock states and refreshes the ui."""
        self._setInfLocks(True)
        self._updateInterface()

    def undoIt(self):
        """Restores original lock states and refreshes the ui."""
        self._setInfLocks(False)
        self._updateInterface()
