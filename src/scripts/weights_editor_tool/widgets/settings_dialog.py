import copy
from dataclasses import fields
from functools import partial

from maya import cmds

from weights_editor_tool.qt import QtCore, QtWidgets
from weights_editor_tool import qt
from weights_editor_tool.dataclasses import HotkeySettings, ToolSettings, HotkeyData
from weights_editor_tool import weights_editor_utils as utils
from weights_editor_tool.widgets.custom_label import CustomLabel
from weights_editor_tool.widgets.preset_button import PresetButton
from weights_editor_tool.widgets.hotkey_edit import HotkeyEdit
from weights_editor_tool.classes.hotkey import Hotkey


class SettingsDialog(QtWidgets.QDialog):
    """
    A comprehensive dialog for managing tool-wide preferences.

    This includes general behavior toggles, custom hotkey assignments that override Maya's default behavior,
    and customizable numeric presets for applying weights.
    """

    def __init__(self,toolSettings: ToolSettings = None, parent: QtWidgets.QWidget = None) -> None:
        """
        Initializes the settings dialog and internal tracking lists.

        Args:
            toolSettings (ToolSettings, optional): The settings object to load. Creates a default instance if None.
            parent (QWidget, optional): Parent widget for modal inheritance.
        """
        QtWidgets.QDialog.__init__(self, parent=parent)

        # Load defaults if nothing was provided.
        if toolSettings is None:
            toolSettings = ToolSettings()

        self._toolSettings = toolSettings
        self._hotkeyEdits = []
        self._addPresetButtons = []
        self._scalePresetButtons = []
        self._setPresetButtons = []

        self._createGui()
        self._setToolSettingsToWidgets()

    @classmethod
    def run(cls, toolSettings: ToolSettings = None, parent: QtWidgets.QWidget = None) -> ToolSettings:
        """
        Static execution method to handle the dialog lifecycle.

        Args:
            toolSettings (ToolSettings, optional): Initial settings to populate.
            parent (QWidget, optional): Parent window.

        Returns:
            ToolSettings: A new settings object containing the user's modifications.
        """
        dialog = cls(toolSettings=toolSettings, parent=parent)
        dialog.exec_()
        newToolSettings = dialog.serialize()
        return newToolSettings

    def _createGui(self) -> None:
        """
        Creates the layout, widgets, and signals.
        """
        self._menuBar = QtWidgets.QMenuBar(self)
        self._menuBar.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)

        self._settingsMenu = QtWidgets.QMenu("&Settings", parent=self)
        self._menuBar.addMenu(self._settingsMenu)

        self._resetSettingsAction = qt.QAction("Reset to defaults", self)
        self._resetSettingsAction.triggered.connect(self._onResetSettingsTriggered)
        self._settingsMenu.addAction(self._resetSettingsAction)

        self._enableInstantTooltipsCheckbox = QtWidgets.QCheckBox("Enable instant tooltips")

        self._displayShortNamesCheckbox = QtWidgets.QCheckBox("Display only short names (hide namespaces and long names)")

        self._checkForUpdatesOnOpenCheckbox = QtWidgets.QCheckBox("Check for updates when the tool opens")

        self._autoSelectVertexCheckbox = QtWidgets.QCheckBox("Auto-select vertexes when selecting cells (table view)")

        self._deleteSkinOnExportCheckbox = QtWidgets.QCheckBox("Delete skin clusters on export")

        self._generalSettingsLayout = utils.wrapLayout(
            [self._enableInstantTooltipsCheckbox,
             self._displayShortNamesCheckbox,
             self._checkForUpdatesOnOpenCheckbox,
             self._autoSelectVertexCheckbox,
             self._deleteSkinOnExportCheckbox],
            QtCore.Qt.Vertical)

        self._generalSettingsGroup = QtWidgets.QGroupBox("General Settings")
        self._generalSettingsGroup.setLayout(self._generalSettingsLayout)

        self._hotkeyLabel = QtWidgets.QLabel("<i>When this tool is open, these hotkeys will override hotkeys from Maya.</i>")

        self._toggleHotkeysCheckbox = QtWidgets.QCheckBox("Enable hotkeys")
        self._toggleHotkeysCheckbox.toggled.connect(self._onHotkeysToggled)

        self._hotkeysScrollLayout = QtWidgets.QVBoxLayout()

        self._hotkeysFrame = QtWidgets.QFrame(parent=self)
        self._hotkeysFrame.setLayout(self._hotkeysScrollLayout)

        self._hotkeysScrollArea = QtWidgets.QScrollArea(parent=self)
        self._hotkeysScrollArea.setFocusPolicy(QtCore.Qt.NoFocus)
        self._hotkeysScrollArea.setWidget(self._hotkeysFrame)
        self._hotkeysScrollArea.setWidgetResizable(True)

        self._hotkeysLayout = utils.wrapLayout(
            [self._hotkeyLabel, self._toggleHotkeysCheckbox, self._hotkeysScrollArea],
             QtCore.Qt.Vertical)

        self._hotkeysGroup = QtWidgets.QGroupBox("Hotkeys")
        self._hotkeysGroup.setLayout(self._hotkeysLayout)

        self._presetHintLabel = QtWidgets.QLabel("<i>Click a preset to change it to a new value.</i>")

        widgets = self._createPresetWidgets("+", self._toolSettings.addPresetValues, self._toolSettings.enableAddPresets)
        self._addPresetButtonsLayout = widgets[0]
        self._addPresetButtonsLabel = widgets[1]
        self._addPresetButtonsToggle = widgets[2]
        self._addPresetLayout = widgets[3]
        self._addPresetFrame = widgets[4]

        widgets = self._createPresetWidgets("%", self._toolSettings.scalePresetValues, self._toolSettings.enableScalePresets)
        self._scalePresetButtonsLayout = widgets[0]
        self._scalePresetButtonsLabel = widgets[1]
        self._scalePresetButtonsToggle = widgets[2]
        self._scalePresetLayout = widgets[3]
        self._scalePresetFrame = widgets[4]

        widgets = self._createPresetWidgets("=", self._toolSettings.setPresetValues, self._toolSettings.enableSetPresets)
        self._setPresetButtonsLayout = widgets[0]
        self._setPresetButtonsLabel = widgets[1]
        self._setPresetButtonsToggle = widgets[2]
        self._setPresetLayout = widgets[3]
        self._setPresetFrame = widgets[4]

        self._presetButtonLayout = utils.wrapLayout(
            [self._presetHintLabel, self._addPresetLayout, self._scalePresetLayout, self._setPresetLayout],
             QtCore.Qt.Vertical)

        self._presetButtonGroup = QtWidgets.QGroupBox("Preset Buttons")
        self._presetButtonGroup.setLayout(self._presetButtonLayout)

        self._mainLayout = utils.wrapLayout(
            [self._generalSettingsGroup, self._hotkeysGroup, self._presetButtonGroup],
             QtCore.Qt.Vertical,
             margins=[5, 5, 5, 5])

        self._mainFrame = QtWidgets.QFrame(parent=self)
        self._mainFrame.setLayout(self._mainLayout)

        self._dialogLayout = utils.wrapLayout(
            [self._menuBar, self._mainFrame],
             QtCore.Qt.Vertical,
             margins=[0, 0, 0, 0])
        self.setLayout(self._dialogLayout)

        self.setWindowTitle("Settings")
        self.resize(450, 550)

        self._toggleHotkeysCheckbox.toggled.emit(self._toggleHotkeysCheckbox.isChecked())

    def _recreateHotkeys(self) -> None:
        """
        Clears and rebuilds the hotkey editor list based on ToolSettings fields.
        """
        # Delete existing hotkey widgets.
        for hotkeyEdit in self._hotkeyEdits:
            parent = hotkeyEdit.parentWidget()  # Get the frame that also contains the label.
            parent.deleteLater()
        del self._hotkeyEdits[:]

        defaultHotkeySettings = HotkeySettings()

        # Create new hotkey widgets.
        for hotkeyField in fields(self._toolSettings.hotkeys):
            hotkeySettingsKey = hotkeyField.name
            hotkeyData = getattr(self._toolSettings.hotkeys, hotkeySettingsKey)

            hotkeyFrame = QtWidgets.QWidget(parent=self)

            toolTip = ""
            if hasattr(defaultHotkeySettings, hotkeySettingsKey):
                defaultHotkeyData = getattr(defaultHotkeySettings, hotkeySettingsKey)
                toolTip = defaultHotkeyData.toolTip

            label = CustomLabel(hotkeyData.name, toolTip=toolTip)
            label.setFixedWidth(150)

            hotkey = Hotkey.fromHotkeyData(hotkeyData)
            keyEdit = HotkeyEdit(hotkeySettingsKey, hotkey, parent=hotkeyFrame)
            keyEdit.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
            self._hotkeyEdits.append(keyEdit)

            resetButton = QtWidgets.QPushButton("Reset", parent=hotkeyFrame)
            resetButton.setFixedWidth(60)
            resetButton.setFixedHeight(20)
            resetButton.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
            resetButton.clicked.connect(partial(self._onResetHotkeyClicked, keyEdit))

            hotkeyLayout = QtWidgets.QHBoxLayout()
            hotkeyLayout.setContentsMargins(0, 0, 0, 0)
            hotkeyLayout.addWidget(label)
            hotkeyLayout.addWidget(keyEdit)
            hotkeyLayout.addWidget(resetButton)
            hotkeyLayout.addStretch()
            hotkeyFrame.setLayout(hotkeyLayout)

            self._hotkeysScrollLayout.addWidget(hotkeyFrame)

    def _recreatePresetButtons(self) -> None:
        """
        Clears and rebuilds all preset button rows based on the numeric values stored in the settings.
        """
        # Create the preset buttons in the same way.
        presetVars = [
            (self._addPresetButtons, self._toolSettings.addPresetValues, self._addPresetButtonsLayout, -1.0, 1.0),
            (self._scalePresetButtons, self._toolSettings.scalePresetValues, self._scalePresetButtonsLayout, -100.0, 100.0),
            (self._setPresetButtons, self._toolSettings.setPresetValues, self._setPresetButtonsLayout, 0.0, 1.0)]

        for presetButtonsVar, values, presetButtonsLayout, minValue, maxValue in presetVars:
            # Delete existing preset buttons.
            for presetButton in presetButtonsVar:
                presetButton.deleteLater()
            del presetButtonsVar[:]

            # Create new preset buttons.
            for value in values:
                presetButton = PresetButton(value, minValue, maxValue, parent=self)
                presetButton.setMinimumWidth(10)
                presetButton.setSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Preferred)
                presetButtonsLayout.addWidget(presetButton)
                presetButtonsVar.append(presetButton)

    def _setToolSettingsToWidgets(self) -> None:
        """
        Synchronizes all UI widgets and triggers the recreation of dynamic lists to match the current ToolSettings state.
        """
        self._enableInstantTooltipsCheckbox.setChecked(self._toolSettings.enableInstantTooltips)
        self._displayShortNamesCheckbox.setChecked(self._toolSettings.displayShortNames)
        self._checkForUpdatesOnOpenCheckbox.setChecked(self._toolSettings.checkForUpdatesOnOpen)
        self._autoSelectVertexCheckbox.setChecked(self._toolSettings.autoSelectVertexFromCell)
        self._deleteSkinOnExportCheckbox.setChecked(self._toolSettings.deleteSkinOnExport)
        self._toggleHotkeysCheckbox.setChecked(self._toolSettings.enableHotkeys)

        self._recreateHotkeys()

        self._recreatePresetButtons()

        self._addPresetButtonsToggle.setChecked(self._toolSettings.enableAddPresets)
        self._addPresetButtonsToggle.toggled.emit(self._addPresetButtonsToggle.isChecked())

        self._scalePresetButtonsToggle.setChecked(self._toolSettings.enableScalePresets)
        self._scalePresetButtonsToggle.toggled.emit(self._scalePresetButtonsToggle.isChecked())

        self._setPresetButtonsToggle.setChecked(self._toolSettings.enableSetPresets)
        self._setPresetButtonsToggle.toggled.emit(self._setPresetButtonsToggle.isChecked())

    def _createPresetWidgets(
            self,
            label: QtWidgets.QLabel,
            values: list[float],
            enabled: bool) -> tuple[QtWidgets.QLabel, QtWidgets.QCheckBox, QtWidgets.QLayout, QtWidgets.QWidget]:
        """
        Creates a standardized UI row for a weight preset category.

        Args:
            label (str): Symbol prefix (e.g., '+', '%').
            values (list[float]): Default numeric values for buttons.
            enabled (bool): Initial toggle state of the group.

        Returns:
            The generated layouts and control widgets.
        """
        presetButtonsLabel = QtWidgets.QLabel(label)
        presetButtonsLabel.setObjectName("presetLabel")
        presetButtonsLabel.setFixedWidth(16)

        presetButtonsLayout = QtWidgets.QHBoxLayout()
        presetButtonsLayout.setContentsMargins(0, 0, 0, 0)
        presetButtonsLayout.addWidget(presetButtonsLabel)

        presetButtonsFrame = QtWidgets.QWidget()
        presetButtonsFrame.setLayout(presetButtonsLayout)

        presetButtonsToggle = QtWidgets.QCheckBox()
        presetButtonsToggle.toggled.connect(partial(self._onPresetButtonsToggled, presetButtonsFrame))
        presetButtonsToggle.setChecked(enabled)

        presetLayout = QtWidgets.QHBoxLayout()
        presetLayout.addWidget(presetButtonsFrame)
        presetLayout.addWidget(presetButtonsToggle, 1)

        return presetButtonsLayout, presetButtonsLabel, presetButtonsToggle, presetLayout, presetButtonsFrame

    def _onResetHotkeyClicked(self, keyEdit: HotkeyEdit) -> None:
        """Resets the supplied HotkeyEdit to its default shortcut keys."""
        defaultToolSettings = ToolSettings()
        if not hasattr(defaultToolSettings.hotkeys, keyEdit.hotkeySettingsKey):
            cmds.warning(f"Unable to find '{keyEdit.hotkeySettingsKey}' in the tool's hotkeys")
            return
        hotkeyData = getattr(defaultToolSettings.hotkeys, keyEdit.hotkeySettingsKey)
        setattr(self._toolSettings.hotkeys, keyEdit.hotkeySettingsKey, hotkeyData)
        self._setToolSettingsToWidgets()

    def _onResetSettingsTriggered(self) -> None:
        """Restores all tool settings and UI widgets to factory defaults."""
        # Prompt user if settings should reset.
        messageBox = QtWidgets.QMessageBox(
            QtWidgets.QMessageBox.Warning,
            "Current settings will be lost",
            "This will revert all of the tool's settings to their default values.\nWould you like to continue?",
            buttons=QtWidgets.QMessageBox.Cancel | QtWidgets.QMessageBox.Ok,
            parent=self)
        messageBox.setDefaultButton(QtWidgets.QMessageBox.Cancel)
        if messageBox.exec_() != QtWidgets.QMessageBox.Ok:
            return

        defaultToolSettings = ToolSettings()

        self._toolSettings.autoSelectVertexFromCell = defaultToolSettings.autoSelectVertexFromCell
        self._toolSettings.deleteSkinOnExport = defaultToolSettings.deleteSkinOnExport
        self._toolSettings.enableHotkeys = defaultToolSettings.enableHotkeys

        self._toolSettings.hotkeys = defaultToolSettings.hotkeys

        self._toolSettings.addPresetValues = defaultToolSettings.addPresetValues
        self._toolSettings.scalePresetValues = defaultToolSettings.scalePresetValues
        self._toolSettings.setPresetValues = defaultToolSettings.setPresetValues

        self._toolSettings.enableAddPresets = defaultToolSettings.enableAddPresets
        self._toolSettings.enableScalePresets = defaultToolSettings.enableScalePresets
        self._toolSettings.enableSetPresets = defaultToolSettings.enableSetPresets

        self._setToolSettingsToWidgets()

    def _onHotkeysToggled(self, enabled: bool):
        """
        Sets the enabled state of the hotkey editor group.

        Args:
            enabled (bool): Whether hotkeys are active.
        """
        self._hotkeysFrame.setEnabled(enabled)

    def _onPresetButtonsToggled(self, widget: QtWidgets.QWidget, enabled: bool):
        """
        Sets the enabled state of a specific preset button group.

        Args:
            widget (QWidget): The container widget to toggle.
            enabled (bool): The new enabled state.
        """
        widget.setEnabled(enabled)

    def serialize(self) -> ToolSettings:
        """
        Gathers UI data into a new ToolSettings instance.

        Returns:
            A deep-copied and updated settings object.
        """
        newToolSettings = copy.deepcopy(self._toolSettings)

        # Get preset button values.
        addPresetValues = tuple(presetButton.value for presetButton in self._addPresetButtons)
        scalePresetValues = tuple(presetButton.value for presetButton in self._scalePresetButtons)
        setPresetValues = tuple(presetButton.value for presetButton in self._setPresetButtons)

        # Store to new settings.
        newToolSettings.enableInstantTooltips = self._enableInstantTooltipsCheckbox.isChecked()
        newToolSettings.displayShortNames = self._displayShortNamesCheckbox.isChecked()
        newToolSettings.checkForUpdatesOnOpen = self._checkForUpdatesOnOpenCheckbox.isChecked()
        newToolSettings.autoSelectVertexFromCell = self._autoSelectVertexCheckbox.isChecked()
        newToolSettings.deleteSkinOnExport = self._deleteSkinOnExportCheckbox.isChecked()
        newToolSettings.enableHotkeys = self._toggleHotkeysCheckbox.isChecked()
        newToolSettings.enableAddPresets = self._addPresetButtonsToggle.isChecked()
        newToolSettings.enableScalePresets = self._scalePresetButtonsToggle.isChecked()
        newToolSettings.enableSetPresets = self._setPresetButtonsToggle.isChecked()
        newToolSettings.addPresetValues = addPresetValues
        newToolSettings.scalePresetValues = scalePresetValues
        newToolSettings.setPresetValues = setPresetValues

        # Store hotkeys.
        for hotkeyEdit in self._hotkeyEdits:
            hotkeySettingsKey = hotkeyEdit.hotkeySettingsKey
            hotkeyData = hotkeyEdit.hotkey.toHotkeyData()
            setattr(newToolSettings.hotkeys, hotkeySettingsKey, hotkeyData)

        return newToolSettings
