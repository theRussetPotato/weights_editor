import copy
from dataclasses import fields

from weights_editor_tool.qt import QtCore, QtGui, QtWidgets
from weights_editor_tool import qt
from weights_editor_tool.dataclasses import ToolSettings, JointLabelsSetOn, Axis
from weights_editor_tool import weights_editor_utils as utils


class JointLabelsDialog(QtWidgets.QDialog):
    """
    A dialog for configuring the tool's joint label settings.
    """

    closed = QtCore.Signal()

    def __init__(self, toolSettings: ToolSettings = None, parent: QtWidgets = None) -> None:
        """
        Initializes the dialog and populates widgets with current settings.

        Args:
            toolSettings (ToolSettings): The settings object to read/modify.
            parent (QWidget): Parent widget.
        """
        QtWidgets.QDialog.__init__(self, parent=parent)

        if toolSettings is None:
            toolSettings = ToolSettings()

        self._toolSettings = toolSettings

        self._createGui()
        self._setToolSettingsToWidgets()

    @classmethod
    def run(cls, toolSettings: ToolSettings = None, parent: QtWidgets.QWidget = None) -> 'JointLabelsDialog':
        """
        Convenience method to instantiate, execute, and return new settings.
        """
        dialog = cls(toolSettings=toolSettings, parent=parent)
        dialog.show()
        return dialog

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self.closed.emit()

    def _dataClassToList(self, dataclass) -> list[str]:
        """Converts the supplied generic dataclass to a list of its field names."""
        return [
            getattr(dataclass, field.name)
            for field in fields(dataclass)]

    def _createGui(self) -> None:
        """
        Builds the layouts, menus, and widgets.
        """
        setOnOptions = self._dataClassToList(JointLabelsSetOn)
        axisOptions = self._dataClassToList(Axis)

        self._menuBar = QtWidgets.QMenuBar(self)
        self._menuBar.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)

        self._settingsMenu = QtWidgets.QMenu("&Settings", parent=self)
        self._menuBar.addMenu(self._settingsMenu)

        self._resetSettingsAction = qt.QAction("Reset to defaults", self)
        self._resetSettingsAction.triggered.connect(self._onResetSettingsTriggered)
        self._settingsMenu.addAction(self._resetSettingsAction)

        self._setOnLabel = QtWidgets.QLabel("Work on:")

        self._setOnComboBox = QtWidgets.QComboBox()
        self._setOnComboBox.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        self._setOnComboBox.setMinimumWidth(35)
        self._setOnComboBox.addItems(setOnOptions)

        self._setOnLayout = utils.wrapLayout(
            [self._setOnLabel, self._setOnComboBox],
             QtCore.Qt.Horizontal)

        self._centerAxisLabel = QtWidgets.QLabel("Center Axis:")

        self._centerAxisCombobox = QtWidgets.QComboBox()
        self._centerAxisCombobox.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        self._centerAxisCombobox.setMinimumWidth(35)
        self._centerAxisCombobox.addItems(axisOptions)

        self._centerAxisLayout = utils.wrapLayout(
            [self._centerAxisLabel, self._centerAxisCombobox],
             QtCore.Qt.Horizontal)

        self._centerThresholdLabel = QtWidgets.QLabel("Center Threshold:")

        self._centerThresholdSpinBox = QtWidgets.QDoubleSpinBox()
        self._centerThresholdSpinBox.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        self._centerThresholdSpinBox.setMinimumWidth(35)
        self._centerThresholdSpinBox.setDecimals(3)

        self._centerThresholdLayout = utils.wrapLayout(
            [self._centerThresholdLabel, self._centerThresholdSpinBox],
             QtCore.Qt.Horizontal)

        self._leftPrefixLabel = QtWidgets.QLabel("Left Prefix:")

        self._leftPrefixLineEdit = QtWidgets.QLineEdit()
        self._leftPrefixLineEdit.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        self._leftPrefixLineEdit.setMinimumWidth(35)

        self._leftPrefixLayout = utils.wrapLayout(
            [self._leftPrefixLabel, self._leftPrefixLineEdit],
             QtCore.Qt.Horizontal)

        self._rightPrefixLabel = QtWidgets.QLabel("Right Prefix:")

        self._rightPrefixLineEdit = QtWidgets.QLineEdit()
        self._rightPrefixLineEdit.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        self._rightPrefixLineEdit.setMinimumWidth(35)

        self._rightPrefixLayout = utils.wrapLayout(
            [self._rightPrefixLabel, self._rightPrefixLineEdit],
             QtCore.Qt.Horizontal)

        self._setJointLabelsButton = QtWidgets.QPushButton("Set Joint Labels")
        self._setJointLabelsButton.clicked.connect(self._onSetJointLabelsClicked)

        self._mainLayout = utils.wrapLayout(
            [self._setOnLayout, self._centerAxisLayout, self._centerThresholdLayout,
                    self._leftPrefixLayout, self._rightPrefixLayout, self._setJointLabelsButton],
             QtCore.Qt.Vertical)

        self._mainFrame = QtWidgets.QFrame(parent=self)
        self._mainFrame.setLayout(self._mainLayout)

        self._dialogLayout = utils.wrapLayout(
            [self._menuBar, self._mainFrame],
             QtCore.Qt.Vertical,
             margins=[0, 0, 0, 0])
        self.setLayout(self._dialogLayout)

        self.setWindowTitle("Automate Joint Labels")
        self.resize(340, 30)

    def _setToolSettingsToWidgets(self) -> None:
        """Applies the internal tool settings the widgets."""
        self._setOnComboBox.setCurrentText(self._toolSettings.jointLabelsSetOn)
        self._centerAxisCombobox.setCurrentText(self._toolSettings.jointLabelsCenterAxis)
        self._centerThresholdSpinBox.setValue(self._toolSettings.jointLabelsCenterThreshold)
        self._leftPrefixLineEdit.setText(self._toolSettings.jointLabelsLeftPrefix)
        self._rightPrefixLineEdit.setText(self._toolSettings.jointLabelsRightPrefix)

    def _onResetSettingsTriggered(self) -> None:
        """Restores the UI widgets and internal settings to factory defaults."""
        defaultToolSettings = ToolSettings()
        self._toolSettings.jointLabelsSetOn = defaultToolSettings.jointLabelsSetOn
        self._toolSettings.jointLabelsCenterAxis = defaultToolSettings.jointLabelsCenterAxis
        self._toolSettings.jointLabelsCenterThreshold = defaultToolSettings.jointLabelsCenterThreshold
        self._toolSettings.jointLabelsLeftPrefix = defaultToolSettings.jointLabelsLeftPrefix
        self._toolSettings.jointLabelsRightPrefix = defaultToolSettings.jointLabelsRightPrefix
        self._setToolSettingsToWidgets()

    def _onSetJointLabelsClicked(self) -> None:
        """Triggered when clicking the button. Runs function to set joint labels."""
        joints = None
        if self._setOnComboBox.currentText() == JointLabelsSetOn.selectedJoints:
            joints = cmds.ls(selection=True, type="joint")

        utils.setJointLabels(
            joints=joints,
            centerAxis=self._centerAxisCombobox.currentText(),
            centerThreshold=self._centerThresholdSpinBox.value(),
            leftPrefix=self._leftPrefixLineEdit.text(),
            rightPrefix=self._rightPrefixLineEdit.text())

    def serialize(self) -> ToolSettings:
        """
        Extracts the values from the UI widgets and returns a new ToolSettings object.

        Returns:
            ToolSettings: A deep copy of the original settings updated with the current UI selections.
        """
        newToolSettings = copy.deepcopy(self._toolSettings)
        newToolSettings.jointLabelsSetOn = self._setOnComboBox.currentText()
        newToolSettings.jointLabelsCenterAxis = self._centerAxisCombobox.currentText()
        newToolSettings.jointLabelsCenterThreshold = self._centerThresholdSpinBox.value()
        newToolSettings.jointLabelsLeftPrefix = self._leftPrefixLineEdit.text()
        newToolSettings.jointLabelsRightPrefix = self._rightPrefixLineEdit.text()
        return newToolSettings
