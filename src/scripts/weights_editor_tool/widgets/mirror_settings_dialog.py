import copy
from dataclasses import fields
from typing import Any

from weights_editor_tool.qt import QtCore, QtGui, QtWidgets
from weights_editor_tool import qt
from weights_editor_tool.dataclasses import ToolSettings, MirrorAxis, MirrorSurface, MirrorInfluence
from weights_editor_tool import weights_editor_utils as utils


class MirrorSettingsDialog(QtWidgets.QDialog):
    """
    A modal dialog for configuring the tool's mirror settings.
    """

    def __init__(self, toolSettings: ToolSettings = None, parent: QtWidgets = None) -> None:
        """
        Initializes the dialog and populates widgets with current settings.

        Args:
            toolSettings (ToolSettings): The settings object to read/modify.
            parent (QWidget): Parent widget for modal behavior.
        """
        QtWidgets.QDialog.__init__(self, parent=parent)

        if toolSettings is None:
            toolSettings = ToolSettings()

        self._toolSettings = toolSettings

        self._createGui()
        self._setToolSettingsToWidgets()

    @classmethod
    def run(cls, toolSettings: ToolSettings = None, parent: QtWidgets.QWidget = None) -> ToolSettings:
        """
        Convenience method to instantiate, execute, and return new settings.
        """
        dialog = cls(toolSettings=toolSettings, parent=parent)
        dialog.exec_()
        newToolSettings = dialog.serialize()
        return newToolSettings

    def _dataClassToList(self, dataclass) -> list[str]:
        """Converts the supplied generic dataclass to a list of its field names."""
        return [
            getattr(dataclass, field.name)
            for field in fields(dataclass)]

    def _createGui(self) -> None:
        """
        Builds the layouts, menus, and widgets.
        """
        mirrorAxisOptions = self._dataClassToList(MirrorAxis)
        mirrorSurfaceOptions = self._dataClassToList(MirrorSurface)
        mirrorInfluenceOptions = self._dataClassToList(MirrorInfluence)

        self._menuBar = QtWidgets.QMenuBar(self)
        self._menuBar.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)

        self._settingsMenu = QtWidgets.QMenu("&Settings", parent=self)
        self._menuBar.addMenu(self._settingsMenu)

        self._resetSettingsAction = qt.QAction("Reset to defaults", self)
        self._resetSettingsAction.triggered.connect(self._onResetSettingsTriggered)
        self._settingsMenu.addAction(self._resetSettingsAction)

        self._mirrorAxisLabel = QtWidgets.QLabel("Mirror Axis:")

        self._mirrorAxisCombobox = QtWidgets.QComboBox()
        self._mirrorAxisCombobox.setToolTip("Mirror axis")
        self._mirrorAxisCombobox.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        self._mirrorAxisCombobox.setMinimumWidth(35)
        self._mirrorAxisCombobox.addItems(mirrorAxisOptions)

        self._mirrorModeLayout = utils.wrapLayout(
            [self._mirrorAxisLabel, self._mirrorAxisCombobox],
             QtCore.Qt.Horizontal)

        self._mirrorSurfaceLabel = QtWidgets.QLabel("Surface Association:")

        self._mirrorSurfaceCombobox = QtWidgets.QComboBox()
        self._mirrorSurfaceCombobox.setToolTip("Mirror surface association")
        self._mirrorSurfaceCombobox.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        self._mirrorSurfaceCombobox.setMinimumWidth(35)
        self._mirrorSurfaceCombobox.addItems(mirrorSurfaceOptions)

        self._mirrorSurfaceLayout = utils.wrapLayout(
            [self._mirrorSurfaceLabel, self._mirrorSurfaceCombobox],
             QtCore.Qt.Horizontal)

        self._mirrorInfLabel = QtWidgets.QLabel("Influence Association:")

        self._mirrorInfCombobox = QtWidgets.QComboBox()
        self._mirrorInfCombobox.setToolTip("Mirror influence association")
        self._mirrorInfCombobox.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        self._mirrorInfCombobox.setMinimumWidth(35)
        self._mirrorInfCombobox.addItems(mirrorInfluenceOptions)

        self._mirrorInfLayout = utils.wrapLayout(
            [self._mirrorInfLabel, self._mirrorInfCombobox],
             QtCore.Qt.Horizontal)

        self._mainLayout = utils.wrapLayout(
            [self._mirrorModeLayout, self._mirrorSurfaceLayout, self._mirrorInfLayout],
             QtCore.Qt.Vertical)

        self._mainFrame = QtWidgets.QFrame(parent=self)
        self._mainFrame.setLayout(self._mainLayout)

        self._dialogLayout = utils.wrapLayout(
            [self._menuBar, self._mainFrame],
             QtCore.Qt.Vertical,
             margins=[0, 0, 0, 0])
        self.setLayout(self._dialogLayout)

        self.setWindowTitle("Mirror Settings")
        self.resize(340, 30)

    def _setToolSettingsToWidgets(self) -> None:
        """Applies the internal tool settings the widgets."""
        self._mirrorAxisCombobox.setCurrentText(self._toolSettings.mirrorAxis)
        self._mirrorSurfaceCombobox.setCurrentText(self._toolSettings.mirrorSurface)
        self._mirrorInfCombobox.setCurrentText(self._toolSettings.mirrorInfluence)

    def _onResetSettingsTriggered(self) -> None:
        """Restores the UI widgets and internal settings to factory defaults."""
        defaultToolSettings = ToolSettings()
        self._toolSettings.mirrorAxis = defaultToolSettings.mirrorAxis
        self._toolSettings.mirrorSurface = defaultToolSettings.mirrorSurface
        self._toolSettings.mirrorInfluence = defaultToolSettings.mirrorInfluence
        self._setToolSettingsToWidgets()

    def serialize(self) -> ToolSettings:
        """
        Extracts the values from the UI widgets and returns a new ToolSettings object.

        Returns:
            ToolSettings: A deep copy of the original settings updated with the current UI selections.
        """
        newToolSettings = copy.deepcopy(self._toolSettings)
        newToolSettings.mirrorAxis = self._mirrorAxisCombobox.currentText()
        newToolSettings.mirrorSurface = self._mirrorSurfaceCombobox.currentText()
        newToolSettings.mirrorInfluence = self._mirrorInfCombobox.currentText()
        return newToolSettings
