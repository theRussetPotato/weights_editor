"""
Author:
    Jason Labbe

Known Issues:
    - Internal data won't sync if weights or influences are modified externally. (ie: can't paint weights while tool is open)
    - The table view is really not made to handle tons of verts.
    - Resizing is slow when the table view has tons of verts selected.

TODO:
    - Uninstall option in the interface
    * Create installer
    * Add setting to disable instant tooltips
    * Remove 'about' dialog
    * [high] Compatibility: Make it compatible for 2025 (QT6)
    * Cohesive icons for "select" buttons
    * Bug: It always starts the tool in the weight's listview
    * Feature: Add "select inf border" to context menu
    * Clean up commands script
    * Weight list - add a bit of white space to value so it's not so close to the edge of the cell
    * Optimize tool's height
        * Make preset section shorter?
        * Add scroll area for all button sections?
    * Split skinning utils to other group boxes? (smooth weights, mirror, prune)
    * Fix compact mode
    * When hiding all presets, the groupbox should hide too
    * Automate joint labels?
    * When middle-click influence list:
        * Also select it
    * [high] Feature: Show all joints in inf list
        * Error on 'select inf vertexes'
        * Error on 'display inf'
        * Error on 'lock inf'
    * [high] Bug: Listview - selecting first header items don't select their cells
        * Combine all different methods to set color inf to one function
    * [high] Bug: Listview - middle-click on a cell should set it as the active inf
    * UX: Hotkey LineEdits should have a button to revert to default
    * Bug: Hotkey lineEdits don't recognize arrow keys
    * [high] Adding a new hotkey is kind of complicated.
    * [low] Feature: Hotkeys for presets?
    * [normal] Inf listview - autoscroll to the active inf
    * [normal] UX: When max influence colors is showing but you're trying to switch the active inf, throw a warning. Otherwise it's confusing why the active inf didn't show.
    * [high] Refactor: Refactor code to camelCase to match Maya API and Qt
        * Convert vars to camelCase
        * Add typing hints
        * Convert to fstrings
        * Use long name args for cmds
        * Make all events use signature 'onButtonClicked' (on + object + action)
        * Add docstrings
    * [high] Put stylesheet in separate file
    * Bug: Buttons need a method to update their caption to better support checked buttons in compact mode
    * Interface: Get instant tooltips working for spinboxes
    * UX: Hide reference name across ui
        * weights table
        * weights list
        * influence view
            * Toggle with settings
        * pick mesh button?
    * Feature: Check for updates on open
        * Have a setting to disable it
    * UX: Move export/import buttons to menu?
    * Feature: Sort out the smooth buttons
    * UX: 'set' preset buttons should include a '=' prefix
    * Usability: Editing preset buttons is really janky
    * UX: Link to help report an issue on GitHub
    * UX: Add better text color to weights (red when low, white when high?)
    * UX: Add an 'x' button to clear the filter's text
    * Currently creating new settings dialog
        * Remove old settings
        * Get general settings to work
        * Get hotkeys to work
        * Get presets to work
        * Save new settings on close
        * Restore settings on open
            * Need to work with mirror dialog
        * Move settings to an icon button

Completed:
    * Interface: Improve tooltips of preset buttons
    * Set a fixed max row limit for table view
    * Always hide long names
    * Get sync/pause view button to work
    * Bug: Showing display color should not be in the undo stack
    * Make sure undo/redo have a proper name set
    * Color pick mesh button with a green border when a mesh isn't picked
    * Properly handle undo/redo so it works within maya
    * Make max infs color view into its own button
    * Views toolbar to hide infs, presets
    * Bug fix: Refresh shouldn't change current influence that's showing
    * Show lock icon on list and table views
    * Instant tooltip on widgets?
    * Turn buttons to icon only when window resizes small enough
    * Change inf highlight color
    * Make theme setting into a button
    - Initial read of skin weights sped up 80% by switching to om2
    - Import by world results in smoother weights by using inverse distance weighting

Example of usage:
from weights_editor_tool import weights_editor
weights_editor.run()
"""

import os
import copy
import json
import traceback
import webbrowser
import dataclasses
from functools import partial
from typing import Optional, Union, Callable, Any

from maya import cmds
from maya import mel
from maya import OpenMaya

from weights_editor_tool.qt import QtCore, QtGui, QtWidgets, QtNetwork
from weights_editor_tool import qt
from weights_editor_tool import constants
from weights_editor_tool.enums import ColorTheme, WeightOperation, SmoothOperation
from weights_editor_tool.dataclasses import ToolSettings, ColorTheme, WeightViewType, HotkeyData, HotkeySettings
from weights_editor_tool import weights_editor_utils as utils
from weights_editor_tool.classes.skin_data import SkinData
from weights_editor_tool.classes.skinned_obj import SkinnedObj
from weights_editor_tool.classes.hotkey import Hotkey
from weights_editor_tool.classes.commands import CommandEditWeights, CommandLockInfs
from weights_editor_tool.widgets.instant_tooltip_dialog import InstantToolTipDialog
from weights_editor_tool.widgets.abstract_weights_view import AbstractWeightsView
from weights_editor_tool.widgets import inf_list_view
from weights_editor_tool.widgets import weights_list_view
from weights_editor_tool.widgets import weights_table_view
from weights_editor_tool.widgets.custom_button import CustomButton
from weights_editor_tool.widgets.custom_double_spinbox import CustomDoubleSpinBox
from weights_editor_tool.widgets.custom_spinbox import CustomSpinBox
from weights_editor_tool.widgets.custom_label import CustomLabel
from weights_editor_tool.widgets.custom_scroll_area import CustomScrollArea
from weights_editor_tool.widgets.mirror_settings_dialog import MirrorSettingsDialog
from weights_editor_tool.widgets.joint_labels_dialog import JointLabelsDialog
from weights_editor_tool.widgets import settings_dialog


class WeightsEditor(QtWidgets.QWidget):
    """
    The main widget for the Weights Editor tool.
    Provides a comprehensive interface for managing skin weights.
    """

    version = "3.0.0"
    instance = None
    selectionChangedCallbackID = None
    shortcuts = []

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        """
        Initializes the widget.

        Args:
            parent (QtWidgets.QWidget, optional): The parent widget. Defaults to the Maya main window.
        """
        if parent is None:
            parent = utils.getMayaWindow()

        QtWidgets.QWidget.__init__(self, parent=parent)

        # Setup instance.
        self._deletePreviousInstance()
        self.__class__.instance = self
        self.setWindowIcon(utils.loadPixmap("interface/icon.png"))
        self.setWindowFlags(QtCore.Qt.Window)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.setObjectName("weightsEditor")

        # Public properties.
        self.blockSelectionCallback = False
        self.ignoreCellSelectionEvent = False
        self.obj = SkinnedObj.createEmptySkin()
        self.colorInfluence = None
        self.vertIndexes = []
        self.locks = []
        self.colorTheme = ColorTheme.Max

        # Private properties.
        self._compactMode: bool = False
        self._copiedVertex = None
        self._deleteSkinOnExport: bool = True
        self._inComponentMode = utils.isInComponentMode()
        self._hotkeys = []
        self._toolSettings = ToolSettings()

        self._createGui()

        # Mappings for which function a hotkey should call.
        # HotkeySettings[key]: callableFunction
        self._hotkeyFunctions = {
            "toggleTableListViews": partial(self._invertCheckedState, self._weightsViewButton),
            "showInfList": partial(self._invertCheckedState, self._showInfsViewAction),
            "showInfColors": partial(self._invertCheckedState, self._hideVertColorsButton),
            "mirrorAll": self._mirrorSkinWeights,
            "prune": self._onPruneByValueClicked,
            "pruneMaxInfs": self._onPruneInfCountClicked,
            "runSmooth": partial(self._runSmooth, SmoothOperation.PreserveInfs),
            "runSmoothAllInfs": partial(self._runSmooth, SmoothOperation.AddInfs),
            "growSelection": self._growSelection,
            "shrinkSelection": self._shrinkSelection,
            "selectEdgeLoop": self._selectEdgeLoop,
            "selectRingLoop": self._selectRingLoop,
            "selectPerimeter": self._selectPerimeter,
            "selectShell": self._selectShell,
            "toggleInfLock": self._toggleSelectedInfLocks,
            "toggleInfLock2": self._toggleSelectedInfLocks,
            "addWeightUp": partial(self._addSelectedWeights, 0.1),
            "addWeightDown": partial(self._addSelectedWeights, -0.1),
            "scaleWeightUp": partial(self._scaleSelectedWeights, 20),
            "scaleWeightDown": partial(self._scaleSelectedWeights, -20)
        }

        self._readUserToolSettings()
        self._applyCurrentToolSettings()
        self._updateWindowTitle()

        # Resize and move the tool's window.
        self.move(
            self.parent().geometry().center().x() - self.width()/2,
            self.parent().geometry().topLeft().y())
        self.resize(self.width(), 900)
        self._resizeWindowWidthByWeightsView()

        if self._toolSettings.checkForUpdatesOnOpen:
            self._fetchLatestToolVersion(quiet=True)

    #
    # Class Methods.
    #

    @classmethod
    def run(cls) -> "WeightsEditor":
        """
        Main entry point to launch the tool.

        Returns:
            The instance of the tool.
        """
        # Load the tool's plugin.
        try:
            utils.loadCommandPlugins()
        except Exception as e:
            print(traceback.format_exc())
            mayaWindow = utils.getMayaWindow()
            QtWidgets.QMessageBox.critical(
                mayaWindow,
                "Cannot Find Plugin!",
                f"Cannot load plugin '{constants.PLUGIN_NAME}'.\n"
                f"Please make sure it's in the Plugin Manager.\n"
                f"If it's still giving issues try running the tool's installer again.")
            raise RuntimeError(e)

        inst = cls()
        inst.show()
        inst._pickSelectedObj()
        return inst

    @classmethod
    def _deletePreviousInstance(cls) -> None:
        """
        Closes and deletes any existing instance of the tool to prevent duplicates.
        """
        if cls.instance is not None:
            try:
                cls.instance.close()
                if cls.instance and qt.shiboken.isValid(cls.instance):
                    cls.instance.deleteLater()
            finally:
                cls.instance = None

    @classmethod
    def _removeHotkeys(cls) -> None:
        """
        Disables and clears all registered tool-specific hotkey shortcuts.
        """
        for shortcut in cls.shortcuts:
            shortcut.setEnabled(False)
        cls.shortcuts = []

    @classmethod
    def getCurrentInstance(cls) -> Optional["WeightsEditor"]:
        """
        Retrieves the currently active instance of this class.

        Returns:
            The active instance if it exists and is valid, else None.
        """
        if cls.instance is None:
            return

        if not qt.shiboken.isValid(cls.instance):
            return

        return cls.instance

    def _createGui(self) -> None:
        """
        Initializes and builds the entire gui.
        """
        self._applyStyleSheet()
        self.setFocusPolicy(QtCore.Qt.StrongFocus)

        #
        # MENU BAR
        #

        self._menuBar = QtWidgets.QMenuBar(parent=self)

        self._exportAction = qt.QAction("Export Skin Weights", self)
        self._exportAction.triggered.connect(self._onExportTriggered)

        self._exportAllAction = qt.QAction("Export All Skin Weights", self)
        self._exportAllAction.triggered.connect(self._onExportAllTriggered)

        self._exportMenu = self._menuBar.addMenu("&Export")
        self._exportMenu.addAction(self._exportAction)
        self._exportMenu.addAction(self._exportAllAction)

        self._importAction = qt.QAction("Import Skin Weights", self)
        self._importAction.triggered.connect(partial(self._onImportTriggered, False))

        self._importByWorldPosAction = qt.QAction("Import Skin Weights (using world positions)", self)
        self._importByWorldPosAction.triggered.connect(partial(self._onImportTriggered, True))

        self._importAllAction = qt.QAction("Import All Skin Weights", self)
        self._importAllAction.triggered.connect(self._onImportAllTriggered)

        self._importMenu = self._menuBar.addMenu("&Import")
        self._importMenu.addAction(self._importAction)
        self._importMenu.addAction(self._importByWorldPosAction)
        self._importMenu.addAction(self._importAllAction)

        self._showInfsViewAction = qt.QAction("Influences View", self)
        self._showInfsViewAction.setCheckable(True)
        self._showInfsViewAction.setChecked(True)
        self._showInfsViewAction.toggled.connect(self._onShowInfsViewTriggered)

        self._showPresetsViewAction = qt.QAction("Presets View", self)
        self._showPresetsViewAction.setCheckable(True)
        self._showPresetsViewAction.setChecked(True)
        self._showPresetsViewAction.toggled.connect(self._onShowPresetsViewTriggered)

        self._viewsMenu = self._menuBar.addMenu("&Views")
        self._viewsMenu.addAction(self._showInfsViewAction)
        self._viewsMenu.addAction(self._showPresetsViewAction)

        self._checkForUpdatesAction = qt.QAction("Check for Updates", self)
        self._checkForUpdatesAction.triggered.connect(self._fetchLatestToolVersion)

        self._reportIssueAction = qt.QAction("Report an Issue", self)
        self._reportIssueAction.triggered.connect(self._onReportIssueTriggered)

        self._githubPageAction = qt.QAction("Github Page", self)
        self._githubPageAction.triggered.connect(self._onGitHubPageTriggered)

        self._uninstallAction = qt.QAction("Uninstall", self)
        self._uninstallAction.triggered.connect(self._onUninstallTriggered)

        self._aboutMenu = self._menuBar.addMenu("&About")
        self._aboutMenu.addAction(self._checkForUpdatesAction)
        self._aboutMenu.addAction(self._reportIssueAction)
        self._aboutMenu.addAction(self._githubPageAction)
        self._aboutMenu.addAction(self._uninstallAction)

        #
        # TOP LAYOUT
        #

        headerIconSize = QtCore.QSize(18, 18)

        self._settingsButton = CustomButton(
            "",
            icon="interface/settings.png",
            toolTip="Open the settings dialog.",
            iconSize=headerIconSize,
            clickEvent=self._onSettingsClicked,
            supportCompactMode=False)
        self._settingsButton.setFixedWidth(35)

        self._pickObjButton = CustomButton(
            "",
            icon="interface/mesh.png",
            toolTip="Loads-in the selected mesh/curve to edit its skin weights.",
            iconSize=headerIconSize,
            clickEvent=self._pickSelectedObj,
            supportCompactMode=False)
        self._pickObjButton.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)

        self._refreshButton = CustomButton(
            "",
            icon="interface/refresh.png",
            toolTip="Refreshes the skin's data.",
            iconSize=headerIconSize,
            clickEvent=self._onRefreshClicked)

        self._headerLayout = utils.wrapLayout(
            [self._settingsButton, self._pickObjButton, self._refreshButton],
            orientation=QtCore.Qt.Horizontal,
            margins=[5, 5, 5, 5])

        #
        # INFLUENCE WIDGET
        #

        self._infGroupBox = QtWidgets.QGroupBox("Influences")

        self._infFilterEdit = QtWidgets.QLineEdit()
        self._infFilterEdit.setPlaceholderText("Filter list by names (use * as a wildcard)")
        self._infFilterEdit.textChanged.connect(self._onInfFilterTextChanged)

        self._clearFilterAction = qt.QAction()
        self._clearFilterAction.triggered.connect(self._onClearFilterTriggered)
        self._clearFilterAction.setToolTip("Clear text")
        self._clearFilterAction.setIcon(utils.loadPixmap("interface/remove.png", height=32))

        self.infListView = inf_list_view.InfListView(self, parent=self._infGroupBox)
        self.infListView.middleClicked.connect(partial(self._onSetColorInfTriggered, False))
        self.infListView.toggleLocksTriggered.connect(self._onInfListToggleLocksTriggered)
        self.infListView.setLocksTriggered.connect(self._onInfListSetLocksTriggered)
        self.infListView.selectInfVertsTriggered.connect(self._selectInfVerts)
        self.infListView.selectInfBordersTriggered.connect(self._selectInfEdges)
        self.infListView.addInfsToVertsTriggered.connect(self._onInfListAddInfsToVertsTriggered)
        self.infListView.infsUpdated.connect(self._updateInfFilterItems)

        self._addInfToVertButton = CustomButton(
            "Add Inf",
            icon="interface/add_inf.png",
            toolTip="Adds the selected influence to all selected vertexes.")
        self._addInfToVertButton.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self._addInfToVertButton.clicked.connect(self._onInfListAddInfsToVertsTriggered)

        self._showAllJointsButton = CustomButton(
            "Show All",
            icon="interface/show_infs.png",
            pressedText="Hide All",
            checkable=True,
            toolTip="Forces the list to show all joints in the scene.",
            clickEvent=self._onShowAllJointsToggled)
        self._showAllJointsButton.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)

        self._infButtonsLayout = utils.wrapLayout(
            [self._addInfToVertButton, self._showAllJointsButton],
            orientation=QtCore.Qt.Horizontal)

        self._infLayout = utils.wrapLayout(
            [self._infFilterEdit, self._infButtonsLayout, self.infListView])
        self._infGroupBox.setLayout(self._infLayout)

        #
        # LISTS WIDGET
        #

        # Setup table
        self._rowWarningLimitLabel = QtWidgets.QLabel(parent=self)
        self._rowWarningLimitLabel.setObjectName("warningLabel")
        self._rowWarningLimitLabel.setWordWrap(True)
        self._rowWarningLimitLabel.hide()

        self._weightsTableView = weights_table_view.TableView(self)
        self._weightsTableView.updateEnded.connect(self._onWeightsTableUpdateEnded)

        self._weightsListView = weights_list_view.ListView(self)
        self._weightsListView.hide()

        for view in [self._weightsListView, self._weightsTableView]:
            view.headerMiddleClicked.connect(partial(self._onSetColorInfTriggered, True))
            view.displayInfTriggered.connect(partial(self._onSetColorInfTriggered, True))
            view.selectInfVertsTriggered.connect(self._onSelectInfVertsTriggered)
            view.selectInfBordersTriggered.connect(self._onSelectInfBordersTriggered)

        self._weightsViewButton = CustomButton(
            "List",
            icon="interface/list.png",
            pressedIcon="interface/table.png",
            pressedText="Table",
            checkable=True,
            toolTip="Toggle to show weights in a list or table view.")
        self._weightsViewButton.setChecked(True)
        self._weightsViewButton.toggled.connect(self._onWeightsViewToggled)

        self._pinWeightsViewButton = CustomButton(
            "Pin",
            icon="interface/pin.png",
            pressedText="Unpin",
            checkable=True,
            toolTip="When enabled, it pins the view from updating when the selection changes until it's unpinned.")
        self._pinWeightsViewButton.setChecked(False)
        self._pinWeightsViewButton.toggled.connect(self._onPinWeightsViewToggled)
        self._onPinWeightsViewToggled(self._pinWeightsViewButton.isChecked())

        self._showAllInfsButton = CustomButton(
            "Show All",
            icon="interface/show_infs.png",
            pressedText="Hide All",
            checkable=True,
            toolTip="Forces the table to show all influences.",
            clickEvent=self._onShowAllInfsClicked)
        self._showAllInfsButton.setMinimumWidth(10)

        self._weightsViewSettingsLayout = utils.wrapLayout(
            [self._weightsViewButton, self._pinWeightsViewButton, self._showAllInfsButton],
            orientation=QtCore.Qt.Horizontal)

        self._weightsViewLayout = utils.wrapLayout(
            [self._rowWarningLimitLabel, self._weightsViewSettingsLayout, self._weightsListView, self._weightsTableView],
            spacing=3)

        self._weightsViewGroupBox = QtWidgets.QGroupBox("Weights From Selection")
        self._weightsViewGroupBox.setLayout(self._weightsViewLayout)

        #
        # PRESET WIDGETS
        #

        self._addPresetLayout, self._addPresetWidget = self._createPresetLayout("+", "Add or subtract weight by a value")
        self._scalePresetLayout, self._scalePresetWidget = self._createPresetLayout("%", "Scale weight by a percentage")
        self._setPresetLayout, self._setPresetWidget = self._createPresetLayout("=", "Set weight to a specific value")

        self._presetsLayout = utils.wrapLayout(
            [self._addPresetWidget, self._scalePresetWidget, self._setPresetWidget],
            spacing=0,
            margins=[0, 0, 0, 0])

        self._presetsGroupBox = QtWidgets.QGroupBox("Presets")
        self._presetsGroupBox.setLayout(self._presetsLayout)

        #
        # VERT COLOR WIDGETS
        #

        self._maxThemeAction = qt.QAction("3dsMax theme", self)
        self._maxThemeAction.setCheckable(True)
        self._maxThemeAction.setChecked(True)
        self._maxThemeAction.triggered.connect(partial(self._onColorThemeTriggered, ColorTheme.Max))

        self._mayaThemeAction = qt.QAction("Maya theme", self)
        self._mayaThemeAction.setCheckable(True)
        self._mayaThemeAction.triggered.connect(partial(self._onColorThemeTriggered, ColorTheme.Maya))

        self._softimageThemeAction = qt.QAction("Softimage theme", self)
        self._softimageThemeAction.setCheckable(True)
        self._softimageThemeAction.triggered.connect(partial(self._onColorThemeTriggered, ColorTheme.Softimage))

        self._themesActionGroup = qt.QActionGroup(self)
        self._themesActionGroup.addAction(self._maxThemeAction)
        self._themesActionGroup.addAction(self._mayaThemeAction)
        self._themesActionGroup.addAction(self._softimageThemeAction)
        self._themesActionGroup.triggered.connect(self._onThemeTriggered)

        self._themesMenu = QtWidgets.QMenu(self)
        self._themesMenu.addAction(self._maxThemeAction)
        self._themesMenu.addAction(self._mayaThemeAction)
        self._themesMenu.addAction(self._softimageThemeAction)

        self._switchThemesButton = CustomButton(
            "Themes",
            icon="interface/colors.png",
            toolTip="Switch the theme to display influence colors.",
            supportCompactMode=False)
        self._switchThemesButton.setMenu(self._themesMenu)

        self._hideVertColorsButton = CustomButton(
            "Hide Colors",
            icon="interface/show.png",
            pressedIcon="interface/hide.png",
            pressedText="Show Colors",
            checkable=True,
            supportCompactMode=False,
            toolTip="Toggle visibility of influence colors")
        self._hideVertColorsButton.setMinimumWidth(10)
        self._hideVertColorsButton.toggled.connect(self._onHideVertColorsToggled)

        self._themesLayout = utils.wrapLayout(
            [self._switchThemesButton, self._hideVertColorsButton],
            orientation=QtCore.Qt.Horizontal,
            margins=[3, 3, 3, 3])

        self._themesGroupBox = QtWidgets.QGroupBox("Vert Colors")
        self._themesGroupBox.setLayout(self._themesLayout)

        #
        # SELECTION WIDGETS
        #

        self._selectInfsButton = CustomButton(
            "Inf(s)",
            icon="interface/selectInf.png",
            toolTip="Selects from the scene the current selected influences.",
            supportCompactMode=False,
            clickEvent=self.infListView.selectCurrentInfs)
        self._selectInfsButton.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)

        self._selectVertsByInfsButton = CustomButton(
            "Inf's Verts",
            icon="interface/selectInfVertex.png",
            toolTip="Selects all vertexes that is effected by the selected influences.",
            supportCompactMode=False,
            clickEvent=self._selectInfVerts)
        self._selectVertsByInfsButton.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)

        self._selectInfEdgesButton = CustomButton(
            "Inf's Borders",
            icon="interface/selectInfBorder.png",
            toolTip="Selects the edges from the selected influence.",
            supportCompactMode=False,
            clickEvent=self._selectInfEdges)
        self._selectInfEdgesButton.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)

        self._selectInfEdgesLevelLabel = QtWidgets.QLabel("Levels:")

        self._selectInfEdgesLevelSpinBox = CustomSpinBox(
            1,
            minValue=1,
            maxValue=10,
            toolTip="The number of vert neighbors it should consider when selecting",
            label=self._selectInfEdgesLevelLabel,
            valueChangedEvent=self._onSelectInfEdgesLevelValueChanged,
            parent=self)

        self._selectInfEdgesLayout = utils.wrapLayout(
            [self._selectInfEdgesButton, self._selectInfEdgesLevelLabel, self._selectInfEdgesLevelSpinBox],
            orientation=QtCore.Qt.Horizontal,
            spacing=5)

        self._selectionLayout = utils.wrapLayout(
            [self._selectInfsButton, self._selectVertsByInfsButton, 10, self._selectInfEdgesLayout],
            orientation=QtCore.Qt.Horizontal,
            margins=[3, 3, 3, 3])

        self._selectionGroupBox = QtWidgets.QGroupBox("Select (From Inf List)")
        self._selectionGroupBox.setLayout(self._selectionLayout)

        #
        # SMOOTH WEIGHTS WIDGETS
        #

        self._smoothPreserveButton = CustomButton(
            "Smooth (Preserve Infs)",
            icon="interface/smooth.png",
            toolTip="Smooth skin weights on selected vertexes with only influences weighted to the vert.",
            supportCompactMode=False,
            clickEvent=partial(self._runSmooth, SmoothOperation.PreserveInfs))
        self._smoothPreserveButton.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)

        self._smoothPreserveStrengthLabel = QtWidgets.QLabel("Strength:")

        self._smoothPreserveStrengthSpinBox = CustomDoubleSpinBox(
            1,
            minValue=0,
            maxValue=1,
            decimals=2,
            singleStep=0.1,
            toolTip="The smooth's strength amount",
            label=self._smoothPreserveStrengthLabel,
            valueChangedEvent=self._onSmoothPreserveStrengthValueChanged,
            parent=self)

        self._smoothPreserveLayout = utils.wrapLayout(
            [self._smoothPreserveButton, 10, self._smoothPreserveStrengthLabel, self._smoothPreserveStrengthSpinBox],
            orientation=QtCore.Qt.Horizontal)

        self._smoothAddButton = CustomButton(
            "Smooth (Add Infs)",
            icon="interface/smooth.png",
            toolTip="Smooth skin weights on selected vertexes that may add neighbouring influences.\n"
                    "Be mindful that this can quickly introduce new influences to increase its influence count.",
            supportCompactMode=False,
            clickEvent=partial(self._runSmooth, SmoothOperation.AddInfs))
        self._smoothAddButton.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)

        self._smoothAddStrengthLabel = QtWidgets.QLabel("Strength:")

        self._smoothAddStrengthSpinBox = CustomDoubleSpinBox(
            1,
            minValue=0,
            maxValue=1,
            decimals=2,
            singleStep=0.1,
            toolTip="The smooth's strength amount",
            label=self._smoothAddStrengthLabel,
            valueChangedEvent=self._onSmoothAddStrengthValueChanged,
            parent=self)

        self._smoothAddLevelLabel = QtWidgets.QLabel("Levels:")

        self._smoothAddLevelSpinBox = CustomSpinBox(
            1,
            minValue=0,
            maxValue=1,
            toolTip="The number of vert neighbors it should consider when smoothing",
            label=self._smoothAddLevelLabel,
            valueChangedEvent=self._onSmoothAddLevelValueChanged,
            parent=self)

        self._smoothAddLayout = utils.wrapLayout(
            [self._smoothAddButton, 10, self._smoothAddLevelLabel, self._smoothAddLevelSpinBox, self._smoothAddStrengthLabel, self._smoothAddStrengthSpinBox],
            orientation=QtCore.Qt.Horizontal)

        self._smoothLayout = utils.wrapLayout(
            [self._smoothPreserveLayout, self._smoothAddLayout],
            orientation=QtCore.Qt.Vertical,
            margins=[3, 3, 3, 3])

        self._smoothGroupBox = QtWidgets.QGroupBox("Smooth Weights")
        self._smoothGroupBox.setLayout(self._smoothLayout)

        #
        # PRUNE WEIGHTS WIDGETS
        #

        self._pruneValueButton = CustomButton(
            "Prune Below Value",
            icon="interface/prune.png",
            toolTip="Prune skin weights on selected vertexes to remove any influence that exceeds the spinbox's value.",
            supportCompactMode=False,
            clickEvent=self._onPruneByValueClicked)
        self._pruneValueButton.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)

        self._pruneValueLabel = QtWidgets.QLabel("Value:")

        self._pruneValueSpinBox = CustomDoubleSpinBox(
            0.1,
            minValue=0.001,
            decimals=3,
            singleStep=0.01,
            toolTip="Prune all influences that have weight below this value",
            label=self._pruneValueLabel,
            valueChangedEvent=self._onPruneByValueValueChanged,
            parent=self)

        self._pruneValueLayout = utils.wrapLayout(
            [self._pruneValueButton, 10, self._pruneValueLabel, self._pruneValueSpinBox],
            orientation=QtCore.Qt.Horizontal)

        self._pruneInfCountButton = CustomButton(
            "Prune to Inf Count",
            icon="interface/prune.png",
            toolTip="Prune skin weights on selected vertexes to remove any extra influences that exceed the spinbox's number",
            supportCompactMode=False,
            clickEvent=self._onPruneInfCountClicked)
        self._pruneInfCountButton.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)

        self._showMaxInfsButton = CustomButton(
            "",
            icon="interface/hide_max_infs.png",
            toolTip="Color vertexes that exceed the number of influences from the spinbox.",
            checkable=True,
            supportCompactMode=False)
        self._showMaxInfsButton.setFixedWidth(30)
        self._showMaxInfsButton.toggled.connect(self._onShowMaxInfsToggled)

        self._pruneInfCountLabel = CustomLabel("Inf Count:", toolTip="Prune influences to force the number of influences to this number")

        self._pruneInfCountSpinBox = CustomSpinBox(
            4,
            minValue=1,
            maxValue=99,
            toolTip="Prune influences to force the number of influences to this number",
            label=self._pruneInfCountLabel,
            valueChangedEvent=self._onPruneInfCountValueChanged,
            parent=self)

        self._pruneInfCountLayout = utils.wrapLayout(
            [self._pruneInfCountButton, self._showMaxInfsButton, 10, self._pruneInfCountLabel, self._pruneInfCountSpinBox],
            orientation=QtCore.Qt.Horizontal)

        self._pruneLayout = utils.wrapLayout(
            [self._pruneValueLayout, self._pruneInfCountLayout],
            orientation=QtCore.Qt.Vertical,
            margins=[3, 3, 3, 3])

        self._pruneGroupBox = QtWidgets.QGroupBox("Prune Weights")
        self._pruneGroupBox.setLayout(self._pruneLayout)

        #
        # MIRROR WEIGHTS WIDGETS
        #

        self._mirrorSkinButton = CustomButton(
            "Mirror (Selection)",
            icon="interface/mirror.png",
            toolTip="Mirror skin weights on selected vertexes only.",
            supportCompactMode=False,
            clickEvent=partial(self._mirrorSkinWeights, True))
        self._mirrorSkinButton.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)

        self._mirrorAllSkinButton = CustomButton(
            "Mirror (All)",
            icon="interface/mirror.png",
            toolTip="Mirror skin weights across the whole mesh.",
            supportCompactMode=False,
            clickEvent=partial(self._mirrorSkinWeights, False))
        self._mirrorAllSkinButton.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)

        self._mirrorSettingsButton = CustomButton(
            "",
            icon="interface/settings.png",
            toolTip="Open settings for mirroring.",
            supportCompactMode=False,
            clickEvent=self._onMirrorSettingsClicked)
        self._mirrorSettingsButton.setFixedWidth(30)

        self._mirrorLayout = utils.wrapLayout(
            [self._mirrorSkinButton, self._mirrorAllSkinButton, self._mirrorSettingsButton],
            orientation=QtCore.Qt.Horizontal,
            margins=[3, 3, 3, 3])

        self._mirrorGroupBox = QtWidgets.QGroupBox("Mirror Weights")
        self._mirrorGroupBox.setLayout(self._mirrorLayout)

        #
        # UTILS
        #

        self._copyVertexButton = CustomButton(
            "Copy Vertex",
            icon="interface/copy.png",
            toolTip="Copy skin weights from the first selected vertex.",
            supportCompactMode=False,
            clickEvent=self._onCopyVertexClicked)
        self._copyVertexButton.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)

        self._pasteVertexButton = CustomButton(
            "Paste Vertex",
            icon="interface/paste.png",
            toolTip="Paste skin weights onto the selected vertexes.",
            supportCompactMode=False,
            clickEvent=self._onPasteVertexClicked)
        self._pasteVertexButton.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)

        self._copyPasteVertexLayout = utils.wrapLayout(
            [self._copyVertexButton, self._pasteVertexButton],
            orientation=QtCore.Qt.Horizontal)

        self._floodToClosestButton = CustomButton(
            "Flood to Closest",
            icon="interface/flood.png",
            toolTip="Iterate across all vertexes and assign them to their closest joint for easier blocking.",
            supportCompactMode=False,
            clickEvent=self._onFloodToClosestClicked)
        self._floodToClosestButton.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)

        self._setJointLabelsButton = CustomButton(
            "Automate Joint Labels",
            icon="interface/show_infs.png",
            toolTip="Set joint labels to get better mappings for mirroring and copying skin weights.",
            supportCompactMode=False,
            clickEvent=self._onSetJointLabelsClicked)
        self._setJointLabelsButton.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)

        self._skinUtilsLayout = utils.wrapLayout(
            [self._copyPasteVertexLayout, self._floodToClosestButton, self._setJointLabelsButton, "stretch"],
            margins=[3, 3, 3, 3])

        self._skinUtilsGroupBox = QtWidgets.QGroupBox("Other Utils")
        self._skinUtilsGroupBox.setLayout(self._skinUtilsLayout)

        self._newAvailableVersionLabel = QtWidgets.QLabel()
        self._newAvailableVersionLabel.setObjectName("updateLabel")
        self._newAvailableVersionLabel.setOpenExternalLinks(True)

        self._newAvailableVersionLayout = utils.wrapLayout(
            [self._newAvailableVersionLabel],
            orientation=QtCore.Qt.Horizontal,
            margins=[5, 5, 5, 5])

        self._newAvailableVersionFrame = QtWidgets.QFrame()
        self._newAvailableVersionFrame.setObjectName("updateFrame")
        self._newAvailableVersionFrame.setLayout(self._newAvailableVersionLayout)
        self._newAvailableVersionFrame.hide()

        #
        # SPLITTERS AND MAIN LAYOUT
        #

        self._scrollLayout = utils.wrapLayout(
            [self._themesGroupBox, self._selectionGroupBox, self._smoothGroupBox, self._pruneGroupBox, self._mirrorGroupBox, self._skinUtilsGroupBox],
            margins=[0, 5, 0, 0])

        self._skinUtilsFrame = QtWidgets.QWidget(parent=self)
        self._skinUtilsFrame.setObjectName("utilsFrame")
        self._skinUtilsFrame.setLayout(self._scrollLayout)

        self._skinUtilsScrollArea = CustomScrollArea(parent=self)
        self._skinUtilsScrollArea.setObjectName("utilsScrollArea")
        self._skinUtilsScrollArea.setFocusPolicy(QtCore.Qt.NoFocus)
        self._skinUtilsScrollArea.setWidget(self._skinUtilsFrame)
        self._skinUtilsScrollArea.setWidgetResizable(True)
        self._skinUtilsScrollArea.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

        self._splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self._splitter.addWidget(self._infGroupBox)
        self._splitter.addWidget(self._weightsViewGroupBox)
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 1)

        self._mainLayout = QtWidgets.QVBoxLayout()
        self._mainLayout.setContentsMargins(5, 5, 5, 5)
        self._mainLayout.setSpacing(3)
        self._mainLayout.setMenuBar(self._menuBar)
        self._mainLayout.addWidget(self._newAvailableVersionFrame)
        self._mainLayout.addLayout(self._headerLayout)
        self._mainLayout.addWidget(self._splitter, stretch=1)
        self._mainLayout.addWidget(self._presetsGroupBox)
        self._mainLayout.addWidget(self._skinUtilsScrollArea)
        self.setLayout(self._mainLayout)

    #
    # Private Methods.
    #

    def _applyStyleSheet(self) -> None:
        """
        Loads and applies the stylesheet to the tool, dynamically calculating
        colors based on the user's current Maya palette.
        """
        winColor = self.palette().color(QtGui.QPalette.Normal, QtGui.QPalette.Window)
        buttonColor = self.palette().color(QtGui.QPalette.Normal, QtGui.QPalette.Button)
        buttonHoverColor = buttonColor.lighter(130)
        presetHoverColor = winColor.lighter(130)

        stylePath = os.path.join(os.path.dirname(__file__), "resources", "style.qss")
        styleFile = QtCore.QFile(stylePath)
        if styleFile.open(QtCore.QFile.OpenModeFlag.ReadOnly | QtCore.QFile.OpenModeFlag.Text):
            stream = QtCore.QTextStream(styleFile)
            rawStyleSheet = stream.readAll()

            styleSheet = rawStyleSheet.format(
                presetBg=winColor.lighter(120).name(),
                winColor=winColor.lighter(110).name(),
                buttonColor=buttonColor.name(),
                buttonHoverColor=buttonHoverColor.name(),
                presetHoverColor=presetHoverColor.name(),
                presetPosR=presetHoverColor.red(),
                presetPosG=presetHoverColor.green() + 20,
                presetPosB=presetHoverColor.blue(),
                presetNegR=presetHoverColor.red() + 20,
                presetNegG=presetHoverColor.green(),
                presetNegB=presetHoverColor.blue())

            self.setStyleSheet(styleSheet)

    def _resizeWindowWidthByWeightsView(self) -> None:
        """Resizes the tool's width to work better with the current weights view type."""
        if self._toolSettings.currentViewType == WeightViewType.Table:
            self.resize(700, self.height())
            self._splitter.setSizes([self.width() * 0.3, self.width() * 0.7])
        else:
            self.resize(500, self.height())
            self._splitter.setSizes([self.width() * 0.5, self.width() * 0.5])

    def _updateCurrentObjectCaption(self) -> None:
        """
        Updates the text on the 'Pick Object' button to show the currently loaded mesh.
        """
        caption = "Load selection's skin data"
        if self.obj.isValid():
            obj = self.obj.shortName()
            if self._toolSettings.displayShortNames:
                obj = obj.split(":")[-1]
            caption = f"Working on `{obj}`"
        self._pickObjButton.setText(caption)

    def _updateWindowTitle(self) -> None:
        """
        Updates the window title to reflect the tool version and currently loaded mesh.
        """
        title = f"Weights Editor v{self.version}"
        if self.obj.isValid():
            obj = self.obj.shortName()
            if self._toolSettings.displayShortNames:
                obj = obj.split(":")[-1]
            title += f" - {obj}"
        self.setWindowTitle(title)

    def _createPresetLayout(self, caption: str, tooltip: str) -> tuple[QtWidgets.QLabel, QtWidgets.QWidget]:
        """
        Creates a standardized layout for a preset weight operation row (Add, Scale, or Set).

        Args:
            caption (str): The label text (e.g., '+', '%', '=').
            tooltip (str): The tooltip description for the row.

        Returns:
            The layout and the container widget.
        """
        label = CustomLabel(caption, toolTip=tooltip)
        label.setObjectName("presetLabel")
        label.setFixedWidth(16)

        layout = utils.wrapLayout(
            [label],
            orientation=QtCore.Qt.Horizontal,
            margins=[0, 2, 0, 2])
        layout.setAlignment(QtCore.Qt.AlignLeft)

        widget = QtWidgets.QWidget()
        widget.setLayout(layout)

        return layout, widget

    def _addSelectedWeights(self, value: float) -> None:
        """
        Triggers a relative weight addition or subtraction.

        Args:
            value (float): The amount to add to or subtract from existing weights.
        """
        self._editSelectedWeightValues(value, WeightOperation.Relative)

    def _scaleSelectedWeights(self, perc: float) -> None:
        """
        Scales selected weights based on a percentage.

        Args:
            perc (float): The percentage value (-100 to 100).
        """
        multiplier = utils.remapRange(-100.0, 100.0, 0.0, 2.0, perc)
        self._editSelectedWeightValues(multiplier, WeightOperation.Percentage)

    def _setSelectedWeights(self, value: float) -> None:
        """
        Sets the selected weights to an absolute value.

        Args:
            value (float): The absolute weight value (0.0 to 1.0).
        """
        self._editSelectedWeightValues(value, WeightOperation.Absolute)

    def _appendPresetButtons(
            self, values: list[float], layout: QtWidgets.QLayout, presetCallback: Callable,
            operationType: WeightOperation) -> None:
        """
        Procedurally creates multiple preset buttons to adjust weights.

        Args:
            values (list[float]): The numerical values for the buttons.
            layout (QtWidgets.QLayout): The layout to add buttons to.
            presetCallback (Callable): The function to call when a button is clicked.
            operationType (WeightOperation): The type of weight modification to apply.
        """
        offset = 1
        for i in range(layout.count() - offset):
            oldButton = layout.takeAt(offset).widget()
            oldButton.deleteLater()

        suffix = ""
        if operationType == WeightOperation.Percentage:
            suffix = "%"

        for value in values:
            valueStr = str(value).removesuffix(".0")

            if operationType == WeightOperation.Absolute:
                prefix = "="
            else:
                prefix = ""
                if value > 0:
                    prefix = "+"
            text = "".join([prefix, valueStr, suffix])

            if operationType == WeightOperation.Absolute:
                tooltip = f"Set to {valueStr}"
            else:
                if operationType == WeightOperation.Relative:
                    if value > 0:
                        word = "Add"
                    else:
                        word = "Subtract"
                else:
                    word = "Scale"
                tooltip = f"{word} by {prefix}{value}{suffix}"

            presetButton = CustomButton(
                text,
                icon="",
                toolTip=tooltip,
                supportCompactMode=False)
            presetButton.setMinimumWidth(30)

            presetButton.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
            presetButton.clicked.connect(partial(presetCallback, value))

            if value > 0:
                presetButton.setObjectName("presetPositiveButton")
            else:
                presetButton.setObjectName("presetNegativeButton")

            layout.addWidget(presetButton)

    def _invertCheckedState(self, button: QtWidgets.QPushButton) -> None:
        """
        Toggles the checked state of a checkable button or action.

        Args:
            button (QtWidgets.QPushButton): The widget to toggle.
        """
        button.setChecked(not button.isChecked())

    def _fetchLatestToolVersion(self, quiet=False) -> None:
        """
        Asynchronously checks the GitHub repository for the latest release version.

        Args:
            quiet (bool): If disabled, may popup a dialog.
        """
        try:
            url = QtCore.QUrl(constants.GITHUB_LATEST_RELEASE)

            request = QtNetwork.QNetworkRequest()
            request.setUrl(url)

            manager = QtNetwork.QNetworkAccessManager()

            networkReply = manager.get(request)
            networkReply.finished.connect(partial(self._onNetworkRequestFinished, manager, networkReply, quiet))  # Pass manager to keep it alive.
        except Exception as err:
            print(traceback.format_exc())
            cmds.warning(f"Could not get version from GitHub: {err}")

    def _registerHotkeys(self) -> None:
        """
        Installs temporary hotkeys that override Maya's defaults while the tool is open.
        """
        self._removeHotkeys()
        for hotkey in self._hotkeys:
            shortcut = utils.createShortcut(QtGui.QKeySequence(hotkey.keyCode()), hotkey.func)
            if shortcut:
                self.__class__.shortcuts.append(shortcut)

    def _saveToolSettings(self) -> None:
        """
        Serializes current tool settings and saves them to a JSON file in the user's maya directory.
        """
        # Serialize the settings.
        serializedToolSettings = self._toolSettings.serialize()

        # Get the path to save to.
        settingsPath = utils.getSettingsPath()
        settingsDir = os.path.dirname(settingsPath)
        if not os.path.exists(settingsDir):
            os.makedirs(settingsDir)

        # Write to the path.
        with open(settingsPath, "w") as f:
            f.write(json.dumps(serializedToolSettings, indent=4))

    def _readUserToolSettings(self) -> None:
        """
        Reads tool settings from the user's saved JSON configuration file if it exists.
        """
        newToolSettings = ToolSettings.readUserSettings()
        if newToolSettings is not None:
            self._toolSettings = newToolSettings

    def _applyCurrentToolSettings(self, updateWidgets: bool = True) -> None:
        """
        Updates the UI and internal state to match the current ToolSettings object.

        Args:
            updateWidgets (bool): Whether to refresh the visual state of UI elements.
        """
        if updateWidgets:
            # Set the color theme.
            themeActions = self._themesActionGroup.actions()
            themeActions[self._toolSettings.colorTheme].setChecked(True)

            # Set numeral values.
            self._smoothPreserveStrengthSpinBox.setValue(self._toolSettings.smoothPreserveStrength)
            self._smoothAddStrengthSpinBox.setValue(self._toolSettings.smoothAddStrength)
            self._smoothAddLevelSpinBox.setValue(self._toolSettings.smoothAddLevels)
            self._selectInfEdgesLevelSpinBox.setValue(self._toolSettings.selectInfEdgeLevels)
            self._pruneValueSpinBox.setValue(self._toolSettings.pruneValue)
            self._pruneInfCountSpinBox.setValue(self._toolSettings.pruneMaxInfsValue)

            # Set bool values.
            self._showAllInfsButton.setChecked(self._toolSettings.showAllInfs)
            self._hideVertColorsButton.setChecked(self._toolSettings.hideVertColors)
            self._showInfsViewAction.setVisible(self._toolSettings.showInfView)
            self._showPresetsViewAction.setVisible(self._toolSettings.showPresetButtonsView)
            self._showMaxInfsButton.setChecked(self._toolSettings.showMaxInfs)

            # Toggle the weight view.
            if self._toolSettings.currentViewType == WeightViewType.List:
                self._weightsViewButton.setChecked(False)
            elif self._toolSettings.currentViewType == WeightViewType.Table:
                self._weightsViewButton.setChecked(True)

        InstantToolTipDialog.enabled = self._toolSettings.enableInstantTooltips

        self._deleteSkinOnExport = self._toolSettings.deleteSkinOnExport
        self._weightsTableView.autoSelectVertexFromCell = self._toolSettings.autoSelectVertexFromCell

        self._updateCurrentObjectCaption()
        self._updateWindowTitle()

        self.infListView.setDisplayShortNames(self._toolSettings.displayShortNames)

        self._weightsListView.setDisplayShortNames(self._toolSettings.displayShortNames)
        self._weightsTableView.setDisplayShortNames(self._toolSettings.displayShortNames)
        weightsView = self.getActiveWeightsView()
        weightsView.fitHeadersToContents()

        # Re-create preset buttons.
        self._appendPresetButtons(
            self._toolSettings.addPresetValues,
            self._addPresetLayout,
            self._addSelectedWeights,
            WeightOperation.Relative)

        self._appendPresetButtons(
            self._toolSettings.scalePresetValues,
            self._scalePresetLayout,
            self._scaleSelectedWeights,
            WeightOperation.Percentage)

        self._appendPresetButtons(
            self._toolSettings.setPresetValues,
            self._setPresetLayout,
            self._setSelectedWeights,
            WeightOperation.Absolute)

        # Toggle visibility of preset buttons.
        self._addPresetWidget.setVisible(self._toolSettings.enableAddPresets)
        self._scalePresetWidget.setVisible(self._toolSettings.enableScalePresets)
        self._setPresetWidget.setVisible(self._toolSettings.enableSetPresets)

        self._presetsGroupBox.setVisible(
            any([self._toolSettings.enableAddPresets, self._toolSettings.enableScalePresets, self._toolSettings.enableSetPresets]))

        # Restore the last path used from the file browser.
        if self._toolSettings.lastBrowserPath and os.path.exists(self._toolSettings.lastBrowserPath):
            SkinnedObj.lastBrowserPath = self._toolSettings.lastBrowserPath

        # Delete previous hotkeys.
        del self._hotkeys[:]
        self._removeHotkeys()

        # Create new hotkeys.
        if self._toolSettings.enableHotkeys:
            for hotkeyField in dataclasses.fields(self._toolSettings.hotkeys):
                hotkeySettingsKey = hotkeyField.name
                hotkeyData: HotkeyData = getattr(self._toolSettings.hotkeys, hotkeySettingsKey)

                function = self._hotkeyFunctions.get(hotkeySettingsKey)
                if function is None:
                    cmds.warning(f"Unable to register hotkey '{hotkeySettingsKey}' since it has no callable function")
                    continue

                hotkey = Hotkey.fromHotkeyData(hotkeyData, func=function)
                self._hotkeys.append(hotkey)
            self._registerHotkeys()

    def _updateObj(self, obj: str) -> None:
        """
        Re-points the tool to work on a specific object and re-collects its skin data.

        Args:
            obj (str): The name of the Maya object (mesh/curve) to load.
        """
        if obj is None:
            self._pickObjButton.setProperty("empty", True)
        else:
            self._pickObjButton.setProperty("empty", None)

        self._pickObjButton.style().unpolish(self._pickObjButton)
        self._pickObjButton.style().polish(self._pickObjButton)
        self._pickObjButton.update()

        previousColorInf = self.colorInfluence

        weightsView = self.getActiveWeightsView()
        weightsView.beginUpdate()

        with utils.DisableUndo():
            try:
                self.obj.hideVertColors()

                # Reset values
                self.obj = SkinnedObj.create(obj)
                self._inComponentMode = utils.isInComponentMode()

                # Collect new values
                if self.obj.isValid() and self.obj.hasValidSkin():
                    if self.obj.isSkinCorrupt():
                        msg = ("The mesh's vert count doesn't match the skin cluster's weight count!\n"
                            "This is likely because changes were done on the mesh with an enabled skinCluster.\n"
                            "\n"
                            "You may have to duplicate the mesh and use copy weights to fix it.")
                        QtWidgets.QMessageBox.critical(self, "Skin cluster error!", msg)
                        return

                showAll = self._showAllJointsButton.isChecked()
                self.infListView.updateInfs(self.obj, showAll)

                self._updateCurrentObjectCaption()
                self._updateWindowTitle()

                self._recollectTableData(loadSelection=False)
            finally:
                weightsView.endUpdate()

            if self.obj.isValid():
                if self.obj.infs:
                    if previousColorInf in self.obj.infs:
                        self._setColorInf(previousColorInf)
                    else:
                        self._assignToFirstColorInf()

    def _collectInfLocks(self) -> None:
        """
        Queries and updates the internal lock state for all influences in the current skin cluster.
        """
        self.locks = [
            cmds.getAttr(f"{infName}.lockInfluenceWeights")
            for infName in self.obj.infs
        ]

    def _getInfsBySelectedVerts(self) -> list[str]:
        """
        Determines which influences are currently affecting the selected vertices.

        Returns:
            A sorted list of influence names.
        """
        infs = set()

        if self.obj.hasValidSkin():
            for vertIndex in self.vertIndexes:
                vertInfs = self.obj.skinData.getVertexInfs(vertIndex)
                infs = infs.union(vertInfs)

        return sorted(list(infs))

    def _recollectTableData(
            self, updateSkinData: bool = True, updateVerts: bool = True,
            updateInfs: bool = True, updateHeaders: bool = True, loadSelection: bool = True) -> None:
        """
        Refreshes the data driving the weights views.

        Can be optimized by selectively disabling updates for skin data, vertices, or influences
        depending on the context of the refresh.

        Args:
            updateSkinData (bool): If True, re-read skin weights from the mesh.
            updateVerts (bool): If True, refresh the list of selected vertex indices.
            updateInfs (bool): If True, refresh the influence list.
            updateHeaders (bool): If True, refresh the column/row headers in the table.
            loadSelection (bool): If True, attempt to restore the previous cell selection.
        """
        # Ignore this event otherwise it slows down the tool by firing many times.
        self.ignoreCellSelectionEvent = True

        weightsView = self.getActiveWeightsView()
        weightsView.beginUpdate()

        try:
            if not self.obj.isValid():
                return

            selectionData = None
            if loadSelection:
                selectionData = weightsView.saveTableSelection()

            if updateSkinData:
                self.obj.updateSkinData()

            if updateVerts:
                self.vertIndexes = utils.extractIndexes(utils.getVertIndexes(self.obj.name))

            if updateInfs:
                self.collectDisplayInfs()

            if updateHeaders:
                weightsView.colorHeaders()
        finally:
            weightsView.endUpdate()
            weightsView.emitHeaderDataChanged()

        if loadSelection:
            weightsView.selectItemsByInf(self.colorInfluence)

        weightsView.fitHeadersToContents()

        self.ignoreCellSelectionEvent = False

    def _editSelectedWeightValues(self, inputValue: float, weightOperation: WeightOperation) -> None:
        """
        Calculates and applies new weight values to the selected cells in the active view.
        It distributes the difference across other influences and registers the operation in the undo stack.

        Args:
            inputValue (float): The numerical value to apply (0.0 to 1.0).
            weightOperation (WeightOperation): The math operation to perform.
        """
        if not self.obj.isValid():
            return

        weightsView = self.getActiveWeightsView()

        vertsAndInfs = weightsView.getSelectedVertsAndInfs()
        if not vertsAndInfs:
            OpenMaya.MGlobal.displayWarning("Select cells inside the table to edit.")
            return

        selectedVertIndexes = set()
        oldSkinData = self.obj.skinData.copy()

        for vertIndex, inf in vertsAndInfs:
            oldValue, newValue = self.obj.skinData.calculateNewValue(inputValue, vertIndex, inf, weightOperation)
            if utils.areValuesCloseEnough(oldValue, newValue):  # Skip it if the new value is too similar.
                continue

            self.obj.skinData.updateWeightValue(vertIndex, inf, newValue)
            selectedVertIndexes.add(vertIndex)

        if not selectedVertIndexes:
            return

        if weightOperation == WeightOperation.Absolute:
            description = f"Set weights by {inputValue}"
        elif weightOperation == WeightOperation.Relative:
            if inputValue > 0:
                description = f"Add weights by {inputValue}"
            else:
                description = f"Subtract weights by {inputValue}"
        elif weightOperation == WeightOperation.Percentage:
            description = f"Scale weights by x{inputValue}"
        else:
            description = f"Edit weights by {inputValue}"

        self.addUndoCommand(
            description,
            self.obj.name,
            oldSkinData,
            self.obj.skinData.copy(),
            list(selectedVertIndexes),
            weightsView.saveTableSelection())

    def _switchColorTheme(self, colorTheme: ColorTheme) -> None:
        """
        Changes the viewport weight visualization to a different color theme.

        Args:
            colorTheme (ColorTheme): The theme to apply.
        """
        self.colorTheme = colorTheme

        if utils.isInComponentMode():
            self.updateVertColors()

        self._recollectTableData(
            updateSkinData=False,
            updateVerts=False,
            updateInfs=False,
            loadSelection=False)

    def _runSmooth(self, smoothOperation: SmoothOperation) -> None:
        """
        Smooths weights on selected vertices by averaging with adjacent vertex weights.

        Args:
            smoothOperation (SmoothOperation): The smooth method to run.

        Raises:
            NotImplementedError: If an unsupported smooth operation type is passed.
        """
        if not self.obj.isValid():
            OpenMaya.MGlobal.displayError("Need to pick a skinned object first.")
            return

        selectedVertexes = utils.extractIndexes(utils.getVertIndexes(self.obj.name))
        if not selectedVertexes:
            OpenMaya.MGlobal.displayError("No vertexes are selected.")
            return

        oldSkinData = self.obj.skinData.copy()
        weightsView = self.getActiveWeightsView()
        tableSelection = weightsView.saveTableSelection()

        selectedVertIndexes = utils.extractIndexes(utils.getVertIndexes(self.obj.name))

        with utils.DisableUndo():
            if smoothOperation == SmoothOperation.PreserveInfs:
                strength = self._smoothPreserveStrengthSpinBox.value()
                level = 1
                allowNewInfs = False
                undoCaption = "Smooth weights (preserve influences)"
            elif smoothOperation == SmoothOperation.AddInfs:
                strength = self._smoothAddStrengthSpinBox.value()
                level = self._smoothAddLevelSpinBox.value()
                allowNewInfs = True
                undoCaption = "Smooth weights (add influences)"
            else:
                raise NotImplementedError

            self.obj.smoothSkinWeights(
                selectedVertexes,
                strength=strength,
                level=level,
                allowNewInfs=allowNewInfs)

            self._recollectTableData(updateSkinData=False, updateVerts=False)
            self.updateVertColors(vertFilter=selectedVertexes)

        newSkinData = self.obj.skinData.copy()

        self.addUndoCommand(
            undoCaption,
            self.obj.name,
            oldSkinData,
            newSkinData,
            selectedVertIndexes,
            tableSelection,
            skipFirstRedo=True)

    def _setColorInf(self, inf: str, updateListView: bool = True) -> None:
        """
        Colors verts to the supplied influence.

        Args:
            inf (str): The name of the influence to color.
            updateListView (bool): When enabled, scroll the influence list to this inf.
        """
        if not self._canDisplayColorInf():
            return

        if inf not in self.obj.infs:
            return

        invalidThemes = [ColorTheme.Softimage, ColorTheme.MaximumInfluences]
        if self.colorTheme in invalidThemes:
            return

        with utils.DisableUndo():
            weightsView = self.getActiveWeightsView()
            weightsView.beginUpdate()
            self.infListView.beginUpdate()

            self.colorInfluence = inf
            weightsView.colorHeaders()

            self.infListView.endUpdate()
            weightsView.endUpdate()
            weightsView.emitHeaderDataChanged()
            weightsView.selectItemsByInf(inf)

            self.updateVertColors()

        if updateListView:
            self.infListView.scrollToItem(self.colorInfluence)
            self.infListView.selectItem(self.colorInfluence)


    def _assignToFirstColorInf(self) -> None:
        """
        Automatically assigns the viewport color display to the first influence
        available in the current view or skin cluster.
        """
        with utils.DisableUndo():
            if self.obj.infs:
                weightsView = self.getActiveWeightsView()
                displayInfs = weightsView.displayInfs()
                if displayInfs:
                    inf = displayInfs[0]
                else:
                    inf = self.obj.infs[0]
                self._setColorInf(inf)

    def _updateInfFilterItems(self) -> None:
        """
        Refreshes the QCompleter for the influence filter search bar based
        on the influences currently displayed in the list.
        """
        items = self.infListView.getDisplayedItems()
        completer = QtWidgets.QCompleter(items, self)
        completer.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
        completer.setCompletionMode(QtWidgets.QCompleter.PopupCompletion)
        completer.setFilterMode(QtCore.Qt.MatchContains)
        self._infFilterEdit.setCompleter(completer)

    def _applyFilterToInfList(self):
        """
        Updates the influence list visibility based on the text currently entered in the filter search bar.
        """
        self.infListView.applyFilter("*" + self._infFilterEdit.text() + "*")

    def _mirrorSkinWeights(self, selectionOnly: Optional[bool] = False) -> None:
        """
        Executes a mirror skin weights operation based on the user's tool settings.

        Args:
            selectionOnly (bool, optional): If True, only mirror weights for selected vertices.
                                            If False, mirrors the entire mesh. Defaults to False.
        """
        if not self.obj.isValid():
            return

        oldSkinData = self.obj.skinData.copy()

        weightsView = self.getActiveWeightsView()
        tableSelection = weightsView.saveTableSelection()

        if selectionOnly:
            vertIndexes = utils.extractIndexes(utils.getVertIndexes(self.obj.name))
        else:
            vertIndexes = utils.extractIndexes(utils.getAllVertIndexes(self.obj.name))

        rawMirrorMode = self._toolSettings.mirrorAxis
        mirrorMode = rawMirrorMode.lstrip("-")
        mirrorInverse = rawMirrorMode.startswith("-")
        mirrorSurface = self._toolSettings.mirrorSurface
        mirrorInf = self._toolSettings.mirrorInfluence

        with utils.DisableUndo():
            self.obj.mirrorSkinWeights(
                mirrorMode,
                mirrorInverse,
                mirrorSurface,
                mirrorInf,
                vertFilter=vertIndexes)

            self._recollectTableData(updateVerts=False)

            vertFilter = vertIndexes if selectionOnly else []
            self.updateVertColors(vertFilter=vertFilter)

        newSkinData = self.obj.skinData.copy()

        self.addUndoCommand(
            "Mirror weights",
            self.obj.name,
            oldSkinData,
            newSkinData,
            vertIndexes,
            tableSelection,
            skipFirstRedo=True)

    def _growSelection(self) -> None:
        """
        Expands the current component selection to include adjacent components.
        """
        mel.eval("PolySelectTraverse 1;")

    def _shrinkSelection(self) -> None:
        """
        Removes the boundary components from the current selection.
        """
        mel.eval("PolySelectTraverse 2;")

    def _selectPerimeter(self) -> None:
        """
        Converts the current selection to the outer vertex perimeter.
        """
        mel.eval("ConvertSelectionToVertexPerimeter;")

    def _selectEdgeLoop(self) -> None:
        """
        Expands the current edge selection to a loop.
        """
        mel.eval("SelectEdgeLoopSp;")

    def _selectShell(self) -> None:
        """
        Expands the current selection to all connected components on the same shell.
        """
        mel.eval("polyConvertToShell;")

    def _selectRingLoop(self) -> None:
        """
        Converts the selection to the edge ring and selects the resulting vertices.
        """
        mel.eval("ConvertSelectionToContainedEdges;")
        mel.eval("SelectEdgeRingSp;")
        mel.eval("ConvertSelectionToVertices;")

    def _toggleSelectedInfLocks(self):
        """
        Toggles the locks for influences based on the active UI focus.
        If the weights view is focused, it toggles the lock state of influences associated with selected cells.
        If the influence list is focused, it triggers the list's internal toggle logic.
        """
        weightsView = self.getActiveWeightsView()
        if weightsView.hasFocus():
            infs = set(inf for _, inf in weightsView.getSelectedVertsAndInfs())
            infs = list(infs)
            if infs:
                infIndex = self.obj.infs.index(infs[-1])
                doLock = not self.locks[infIndex]
                self.toggleInfLocks(infs, doLock)
        elif self.infListView.hasFocus():
            self.infListView.toggleLocks()

    def _shouldVertColorsBeShowing(self) -> bool:
        """
        Determines if vertex weight colors should be displayed in the viewport.

        Returns:
            True if conditions allow for color display, False otherwise.
        """
        if self._hideVertColorsButton.isChecked() or not self._inComponentMode:
            return False

        if self.obj.isValid():
            if utils.isNurbsCurve(self.obj.name):
                return False

        if not self.obj.infs:
            return False

        return True

    def _addSelectionCallback(self) -> None:
        """
        Registers the Maya API callback to monitor scene selection changes.
        """
        if self.selectionChangedCallbackID is None:
            self.selectionChangedCallbackID = OpenMaya.MEventMessage.addEventCallback(
                "SelectionChanged", self._onSelectionChanged)

    def _removeSelectionCallback(self) -> None:
        """
        Unregisters the Maya API selection change callback.
        """
        if self.selectionChangedCallbackID is not None:
            OpenMaya.MEventMessage.removeCallback(self.selectionChangedCallbackID)
            self.selectionChangedCallbackID = None

    def _enableCompactMode(self) -> None:
        """
        Adjusts the UI layout and widget sizes to a minimized, space-saving state.
        """
        self._compactMode = True

        for cls in [CustomButton, CustomSpinBox, CustomDoubleSpinBox]:
            for widget in self.findChildren(cls):
                widget.enableCompactMode()

        utils.moveToNewLayout(
            (self._infLayout, self._infButtonsLayout),
            [self._infFilterEdit], self._infButtonsLayout,
            0)

    def _disableCompactMode(self) -> None:
        """
        Restores the UI layout and widget sizes to the standard, full-sized state.
        """
        self._compactMode = False

        for cls in [CustomButton, CustomSpinBox, CustomDoubleSpinBox]:
            for widget in self.findChildren(cls):
                widget.disableCompactMode()

        utils.moveToNewLayout(
            (self._infLayout, self._infButtonsLayout),
            [self._infFilterEdit],
            self._infLayout,
            0)

    def _pickSelectedObj(self) -> None:
        """
        Identifies the currently selected mesh in the scene and loads it into the tool.
        """
        obj = utils.getSelectedMesh()
        self._updateObj(obj)

    def _selectInfVerts(self) -> None:
        """
        Selects all vertices affected by the influences currently selected in the influence list.
        """
        if not self.obj.isValid():
            OpenMaya.MGlobal.displayError("The current object isn't set to anything.")
            return

        selectedIndexes = self.infListView.selectedIndexes()
        if not selectedIndexes:
            OpenMaya.MGlobal.displayError("There are no influences selected.")
            return

        infs = []

        for index in selectedIndexes:
            infName = self.infListView.listModel.itemFromIndex(index).node()

            if not cmds.objExists(infName):
                OpenMaya.MGlobal.displayError(f"Unable to find influence '{infName}' in the scene. Is the list out of sync?")
                return

            if infName not in self.obj.infs:
                OpenMaya.MGlobal.displayError(f"The joint needs to be added to the skinCluster: `{infName}`")
                return

            infs.append(infName)

        self.obj.selectInfVertexes(infs)

    def _selectInfEdges(self):
        """
        Selects border vertices affected by the influence currently selected in the influence list.
        """
        if not self.obj.isValid():
            OpenMaya.MGlobal.displayError("The current object isn't set to anything.")
            return

        selectedIndexes = self.infListView.selectedIndexes()
        if not selectedIndexes:
            OpenMaya.MGlobal.displayError("There are no influences selected.")
            return

        inf = None
        for index in selectedIndexes:
            infName = self.infListView.listModel.itemFromIndex(index).node()

            if not cmds.objExists(infName):
                OpenMaya.MGlobal.displayError(f"Unable to find influence '{infName}' in the scene. Is the list out of sync?")
                return

            if infName not in self.obj.infs:
                OpenMaya.MGlobal.displayError(f"The joint needs to be added to the skinCluster: `{infName}`")
                return

            inf = infName
            break

        level = self._selectInfEdgesLevelSpinBox.value()
        self.obj.selectEdges(inf, level)

    def _getActiveColorThemeIndex(self) -> int:
        """
        Retrieves the index of the currently checked color theme action.

        Returns:
            The index of the active theme.
        """
        colorActions = [self._maxThemeAction, self._mayaThemeAction, self._softimageThemeAction]
        checkedAction = self._themesActionGroup.checkedAction()
        index = colorActions.index(checkedAction)
        return index

    def _canDisplayColorInf(self):
        """
        Checks current state of the tool to see if it's allowed to display an inf color, or is something overriding it.

        Returns:
            True is it's valid to display, otherwise False.
        """
        if self.colorTheme == ColorTheme.Softimage:
            return False
        elif self.colorTheme == ColorTheme.MaximumInfluences:
            return False
        else:
            return True

    #
    # Sub-class Events.
    #

    def closeEvent(self, closeEvent: QtGui.QCloseEvent) -> None:
        """
        Handles cleanup operations when the tool is closed.

        Saves user settings, disables viewport vertex colors for the current object,
        cleans up temporary Maya nodes, and removes scene callbacks and hotkeys.

        Args:
            closeEvent (QtGui.QCloseEvent): The Qt close event.
        """
        try:
            with utils.DisableUndo():
                self._saveToolSettings()

                if self.obj.isValid():
                    utils.toggleDisplayColors(self.obj.name, False)
                    utils.deleteTempInputs(self.obj.name)
        finally:
            self._removeSelectionCallback()
            self._removeHotkeys()
            self._deletePreviousInstance()

    def resizeEvent(self, resizeEvent: QtGui.QResizeEvent) -> None:
        """
        Triggers UI layout changes based on the window width.

        Automatically toggles 'Compact Mode' when the window width crosses
        a threshold to ensure the UI remains usable at smaller sizes.

        Args:
            resizeEvent (QtGui.QResizeEvent): The Qt resize event.
        """
        super().resizeEvent(resizeEvent)

        if self.width() < 450:
            if not self.isVisible() or not self._compactMode:
                self._enableCompactMode()
        else:
            if not self.isVisible() or self._compactMode:
                self._disableCompactMode()

    #
    # Event Handling Methods.
    #

    def _onSetColorInfTriggered(self, updateListView: bool, inf: str) -> None:
        """
        Handler to set the active color influence.
        Throws a warning if it's in a theme that doesn't support displaying the color influence.
        """
        if inf not in self.obj.infs:
            OpenMaya.MGlobal.displayError(f"The joint needs to be added to the skinCluster: `{inf}`")
            return

        if self.colorTheme == ColorTheme.Softimage:
            cmds.warning("Unable to display influence color when theme is set to 'Softimage'")
        elif self.colorTheme == ColorTheme.MaximumInfluences:
            cmds.warning("Unable to display influence color when displaying maximum influences")
        self._setColorInf(inf, updateListView=updateListView)

    def _onSelectionChanged(self, *args) -> None:
        """
        Handles scene selection changes to sync the tool with the Maya viewport.

        Updates the internal component mode state, refreshes vertex colors if
        mode was switched, and triggers a table data refresh.

        Args:
            *args: Variable arguments passed by the Maya callback.
        """
        # Check if the current object is valid.
        if self.obj.isValid() and self.obj.hasValidSkin():
            # Toggle influence colors if component selection mode changes.
            wasInComponentMode = self._inComponentMode
            self._inComponentMode = utils.isInComponentMode()

            # No point to adjust colors if it's already disabled.
            if not self._hideVertColorsButton.isChecked():
                if wasInComponentMode != self._inComponentMode:  # Only continue if component mode was switched.
                    with utils.DisableUndo():
                        self.updateVertColors()

            # Update table's data.
            if not self.blockSelectionCallback:
                self._recollectTableData(updateSkinData=False)

    def _onNetworkRequestFinished(
            self, manager: QtNetwork.QNetworkAccessManager,
            networkReply: QtNetwork.QNetworkReply, quiet: bool) -> None:
        """
        Processes the result of the version check network request.

        Parses the JSON response from GitHub and displays an update notification if a newer version is available.

        Args:
            manager (QtNetwork.QNetworkAccessManager): The manager that sent the request.
            networkReply (QtNetwork.QNetworkReply): The reply containing version data.
            quiet (bool): If disabled, will popup a dialog.
        """
        response = networkReply.readAll()
        data = json.loads(bytes(response))
        latestVersion = data["tag_name"]
        isObsolete = utils.isVersionStringGreater(latestVersion, self.version)

        if isObsolete:
            url = data["html_url"]
            self._newAvailableVersionLabel.setText(f"A new version is available! Get {latestVersion} <a href='{url}'>in this page</a>.")
            self._newAvailableVersionFrame.show()
        else:
            if not quiet:
                QtWidgets.QMessageBox.information(self, "All good!", "Everything is up to date.")

    def _onInfFilterTextChanged(self) -> None:
        """
        Updates the UI and applies filtering to the influence list as the user types.
        Manages the visibility of the clear action icon in the line edit.
        """
        if self._infFilterEdit.text():
            self._infFilterEdit.addAction(self._clearFilterAction, QtWidgets.QLineEdit.TrailingPosition)
        else:
            self._infFilterEdit.removeAction(self._clearFilterAction)

        self._applyFilterToInfList()

    def _onClearFilterTriggered(self):
        """
        Clears the current text in the influence filter line edit.
        """
        self._infFilterEdit.clear()
        self._infFilterEdit.returnPressed.emit()

    def _onThemeTriggered(self, action: qt.QAction) -> None:
        """
        Updates the tool settings based on the selected theme menu action.

        Args:
            action (qt.QAction): The action triggered from the theme menu.
        """
        themeActions = self._themesActionGroup.actions()
        colorTheme: ColorTheme = themeActions.index(action)
        self._toolSettings.colorTheme = colorTheme

    def _onWeightsTableUpdateEnded(self, overLimit: bool) -> None:
        """
        Handles post-update logic for the weights table view.
        Displays or hides a warning label based on whether the number of vertices exceeds the tool's display limit.

        Args:
            overLimit (bool): True if the vertex count exceeds the row limit.
        """
        if self._rowWarningLimitLabel.isVisible() != overLimit:
            if overLimit:
                maxCount = self._weightsTableView.tableModel.maxDisplayCount
                self._rowWarningLimitLabel.setText(f"Can only display {maxCount} rows! Go to settings to increase the limit.")
            self._rowWarningLimitLabel.setVisible(overLimit)

    def _onRefreshClicked(self) -> None:
        """
        Forces a full re-collection of the current object's skinning data.
        """
        self._updateObj(self.obj.name)

    def _onPruneByValueClicked(self) -> None:
        """
        Executes a weight pruning operation on the object based on the current threshold.
        """
        if not self.obj.isValid():
            return

        oldSkinData = self.obj.skinData.copy()
        weightsView = self.getActiveWeightsView()
        tableSelection = weightsView.saveTableSelection()
        selectedVertIndexes = utils.extractIndexes(utils.getVertIndexes(self.obj.name))

        with utils.DisableUndo():
            result = self.obj.pruneSkinWeights(self._pruneValueSpinBox.value())
            if not result:
                return

            self._recollectTableData(updateVerts=False)

            self.updateVertColors(vertFilter=selectedVertIndexes)

            newSkinData = self.obj.skinData.copy()

        self.addUndoCommand(
            "Prune weights",
            self.obj.name,
            oldSkinData,
            newSkinData,
            selectedVertIndexes,
            tableSelection,
            skipFirstRedo=True)

    def _onSelectInfEdgesLevelValueChanged(self, value: int) -> None:
        """
        Syncs the select inf edges level spinbox value to tool settings.

        Args:
            value (int): The number of levels to select.
        """
        self._toolSettings.selectInfEdgeLevels = value

    def _onSmoothPreserveStrengthValueChanged(self, value: float) -> None:
        """
        Syncs the smooth preserve strength spinbox value to tool settings.

        Args:
            value (float): The new strength value.
        """
        self._toolSettings.smoothPreserveStrength = value

    def _onSmoothAddStrengthValueChanged(self, value: float) -> None:
        """
        Syncs the smooth add strength spinbox value to tool settings.

        Args:
            value (float): The new strength value.
        """
        self._toolSettings.smoothAddStrength = value

    def _onSmoothAddLevelValueChanged(self, value: int) -> None:
        """
        Syncs the smooth add level spinbox value to tool settings.

        Args:
            value (int): The number of neighbor levels to smooth.
        """
        self._toolSettings.smoothAddLevels = value

    def _onPruneInfCountValueChanged(self, value: int) -> None:
        """
        Updates the maximum influence limit in settings and refreshes visualization.

        Args:
            value (int): The maximum number of influences allowed per vertex.
        """
        self._toolSettings.pruneMaxInfsValue = value
        if self.colorTheme == ColorTheme.MaximumInfluences:
            self._onColorThemeTriggered(ColorTheme.MaximumInfluences)

    def _onPruneByValueValueChanged(self, value: float) -> None:
        """
        Syncs the weight pruning threshold value to tool settings.

        Args:
            value (float): The minimum weight threshold to keep.
        """
        self._toolSettings.pruneValue = value

    def _onPruneInfCountClicked(self) -> None:
        """
        Executes the operation to limit the maximum number of influences per vertex.
        """
        if not self.obj.isValid():
            return

        oldSkinData = self.obj.skinData.copy()
        weightsView = self.getActiveWeightsView()
        tableSelection = weightsView.saveTableSelection()
        selectedVertIndexes = utils.extractIndexes(utils.getVertIndexes(self.obj.name))

        result = self.obj.pruneMaxInfs(self._pruneInfCountSpinBox.value(), vertFilter=selectedVertIndexes)
        if not result:
            return

        newSkinData = self.obj.skinData.copy()

        self.addUndoCommand(
            "Prune maximum influences",
            self.obj.name,
            oldSkinData,
            newSkinData,
            selectedVertIndexes,
            tableSelection)

        self._recollectTableData(updateSkinData=False, updateVerts=False)

    def _onSetJointLabelsClicked(self) -> None:
        """
        Opens the joint labels settings dialog and updates local settings with the result.
        """
        self._jointLabelsDialog = JointLabelsDialog.run(toolSettings=self._toolSettings, parent=self)
        self._jointLabelsDialog.closed.connect(self._onJointsLabelDialogClosed)

    def _onJointsLabelDialogClosed(self) -> None:
        """
        Triggers when the joints label dialog has been closed. Saves its settings.
        """
        newToolSettings = self._jointLabelsDialog.serialize()
        self._toolSettings = newToolSettings
        self._jointLabelsDialog.deleteLater()

    def _onMirrorSettingsClicked(self) -> None:
        """
        Opens the mirror settings dialog and updates local settings with the result.
        """
        newToolSettings = MirrorSettingsDialog.run(toolSettings=self._toolSettings, parent=self)
        self._toolSettings = newToolSettings

    def _onCopyVertexClicked(self) -> None:
        """
        Copies the skin weight data of the first selected vertex to the clipboard.
        """
        if not self.obj.isValid():
            OpenMaya.MGlobal.displayError("Need to pick a skinned object first.")
            return

        vertIndexes = utils.extractIndexes(utils.getVertIndexes(self.obj.name))

        if not vertIndexes:
            OpenMaya.MGlobal.displayError("Must copy a vertex from the currently picked object.")
            return

        if not self.obj.isValid() or not self.obj.hasValidSkin():
            OpenMaya.MGlobal.displayError("The current object must be a skinned object.")
            return

        vertIndex = vertIndexes[0]
        self._copiedVertex = self.obj.skinData.copyVertex(vertIndex)
        OpenMaya.MGlobal.displayInfo(f"Copied vertex {vertIndex}")

    def _onPasteVertexClicked(self) -> None:
        """
        Applies copied skin weight data from the clipboard to the currently selected vertices.
        Validates that the target mesh contains all the influences present in the copied data before applying.
        """
        if self._copiedVertex is None:
            OpenMaya.MGlobal.displayError("Need to copy a vertex first.")
            return

        vertIndexes = utils.extractIndexes(utils.getVertIndexes(self.obj.name))

        if not vertIndexes:
            OpenMaya.MGlobal.displayError("Must paste on a vertex from the currently picked object.")
            return

        if not self.obj.isValid() or not self.obj.hasValidSkin():
            OpenMaya.MGlobal.displayError("The current object must be a skinned object.")
            return

        weightsView = self.getActiveWeightsView()
        tableSelection = weightsView.saveTableSelection()
        oldSkinData = self.obj.skinData.copy()

        for inf in self._copiedVertex["weights"]:
            if inf not in self.obj.infs:
                OpenMaya.MGlobal.displayError(f"Unable to paste vertex because the skin is missing influence `{inf}`")
                return

        for vertIndex in vertIndexes:
            self.obj.skinData[vertIndex] = copy.deepcopy(self._copiedVertex)

        newSkinData = self.obj.skinData.copy()

        self.addUndoCommand(
            "Paste vertex",
            self.obj.name,
            oldSkinData,
            newSkinData,
            vertIndexes,
            tableSelection)

    def _onExportTriggered(self) -> None:
        """
        Exports skin weights for the currently loaded object to a file.
        """
        try:
            self.obj.exportSkinWeights()
        except Exception as err:
            print(traceback.format_exc())
            OpenMaya.MGlobal.displayError(str(err))

    def _onExportAllTriggered(self) -> None:
        """
        Exports skin weights for all skinned objects in the current Maya scene.
        """
        try:
            SkinnedObj.exportAllSkinWeights(self._deleteSkinOnExport)
        except Exception as err:
            print(traceback.format_exc())
            OpenMaya.MGlobal.displayError(str(err))

    def _onImportTriggered(self, useWorldPositions: bool) -> None:
        """
        Imports skin weights from a file for the current object.

        Args:
            useWorldPositions (bool): If True, maps weights based on world space coordinates rather than vertex IDs.
        """
        try:
            messageBox = QtWidgets.QMessageBox(
                QtWidgets.QMessageBox.Warning,
                "Undos will be lost",
                "The tool's undo stack will reset and be lost.\n"
                "Would you like to continue?")

            messageBox.addButton(QtWidgets.QMessageBox.Cancel)
            messageBox.addButton(QtWidgets.QMessageBox.Ok)
            messageBox.setDefaultButton(QtWidgets.QMessageBox.Cancel)
            if messageBox.exec_() == QtWidgets.QMessageBox.Cancel:
                return False

            status = self.obj.importSkinWeights(worldSpace=useWorldPositions)
            if status and self.obj.isValid():
                self._updateObj(self.obj.name)
        except Exception as err:
            print(traceback.format_exc())
            OpenMaya.MGlobal.displayError(str(err))

    def _onImportAllTriggered(self):
        """
        Batch imports skin weights for all matching objects found in the source directory.
        """
        try:
            messageBox = QtWidgets.QMessageBox(
                QtWidgets.QMessageBox.Warning,
                "Undos will be lost",
                "The tool's undo stack will reset and be lost.\n"
                "Would you like to continue?")

            messageBox.addButton(QtWidgets.QMessageBox.Cancel)
            messageBox.addButton(QtWidgets.QMessageBox.Ok)
            messageBox.setDefaultButton(QtWidgets.QMessageBox.Cancel)
            if messageBox.exec_() == QtWidgets.QMessageBox.Cancel:
                return False

            SkinnedObj.importAllSkinWeights(False, True)
            if self.obj.isValid():
                self._updateObj(self.obj.name)
        except Exception as err:
            print(traceback.format_exc())
            OpenMaya.MGlobal.displayError(str(err))

    def _onHideVertColorsToggled(self, checked: bool) -> None:
        """
        Toggles the visibility of vertex colors in the Maya viewport and updates the UI button icon and caption.

        Args:
            checked (bool): The toggle state of the button.
        """
        self._toolSettings.hideVertColors = checked

        with utils.DisableUndo():
            if self.obj.isValid() and self._inComponentMode:
                self.updateVertColors()
                utils.toggleDisplayColors(self.obj.name, not checked)

    def _onFloodToClosestClicked(self) -> None:
        """
        Assigns the weight of every vertex to its single closest influence, effectively "hard skinning" the mesh.
        """
        if not self.obj.isValid() or not self.obj.hasValidSkin():
            OpenMaya.MGlobal.displayError("Must have a picked object with a valid skin.")
            return

        oldSkinData = self.obj.skinData.copy()

        weightsView = self.getActiveWeightsView()
        tableSelection = weightsView.saveTableSelection()

        vertIndexes = utils.extractIndexes(utils.getAllVertIndexes(self.obj.name))

        with utils.DisableUndo():
            self.obj.floodSkinWeightsToClosest()

            self._recollectTableData(updateVerts=False)
            self.updateVertColors()

        newSkinData = self.obj.skinData.copy()

        self.addUndoCommand(
            "Flood weights to closest",
            self.obj.name,
            oldSkinData,
            newSkinData,
            vertIndexes,
            tableSelection,
            skipFirstRedo=True)

    def _onColorThemeTriggered(self, index: ColorTheme) -> None:
        """
        Sets the active color theme for the viewport and updates the menu selection states.

        Args:
            index (ColorTheme): The index of the theme to activate.
        """
        if index != ColorTheme.MaximumInfluences:
            self._maxThemeAction.setChecked(index == ColorTheme.Max)
            self._mayaThemeAction.setChecked(index == ColorTheme.Maya)
            self._softimageThemeAction.setChecked(index == ColorTheme.Softimage)

        if self._showMaxInfsButton.isChecked():
            self._switchColorTheme(ColorTheme.MaximumInfluences)
        else:
            self._switchColorTheme(index)

    def _onSelectInfVertsTriggered(self, inf: str) -> None:
        """
        Selects all vertices affected by a specific influence.

        Args:
            inf (str): The name of the influence.
        """
        if self.obj.isValid():
            self.obj.selectInfVertexes([inf])

    def _onSelectInfBordersTriggered(self, inf: str) -> None:
        """
        Selects border vertices affected by a specific influence.

        Args:
            inf (str): The name of the influence.
        """
        if self.obj.isValid():
            level = self._selectInfEdgesLevelSpinBox.value()
            self.obj.selectEdges(inf, level)

    def _onSettingsClicked(self) -> None:
        """
        Opens the tool settings dialog and applies any changes made by the user.
        """
        newToolSettings = settings_dialog.SettingsDialog.run(toolSettings=self._toolSettings, parent=self)
        self._toolSettings = newToolSettings
        self._applyCurrentToolSettings(updateWidgets=False)

    def _onShowInfsViewTriggered(self, state: bool) -> None:
        """
        Toggles the visibility of the influence list panel.

        Args:
            state (bool): The visibility state.
        """
        self._toolSettings.showInfView = state
        self._infGroupBox.setVisible(state)

    def _onShowPresetsViewTriggered(self, state: bool) -> None:
        """
        Toggles the visibility of the weight preset buttons panel.

        Args:
            state (bool): The visibility state.
        """
        self._toolSettings.showPresetButtonsView = state
        self._presetsGroupBox.setVisible(state)

    def _onReportIssueTriggered(self) -> None:
        """
        Opens the GitHub issues page in the user's default web browser.
        """
        webbrowser.open(constants.GITHUB_ISSUES)

    def _onGitHubPageTriggered(self) -> None:
        """
        Opens the tool's GitHub repository page in the user's default web browser.
        """
        webbrowser.open(constants.GITHUB_HOME)

    def _onUninstallTriggered(self) -> None:
        """
        Deletes this tool and its plugin from this machine.
        """
        messageBox = QtWidgets.QMessageBox(
            QtWidgets.QMessageBox.Warning,
            "Uninstall?",
            "Are you sure you want to uninstall this tool?",
            buttons=QtWidgets.QMessageBox.Cancel | QtWidgets.QMessageBox.Ok,
            parent=self)
        messageBox.setDefaultButton(QtWidgets.QMessageBox.Cancel)
        if messageBox.exec_() != QtWidgets.QMessageBox.Ok:
            return

        try:
            utils.uninstall()

            QtWidgets.QMessageBox(
                QtWidgets.QMessageBox.Information,
                "Uninstall is complete",
                "The Weights Editor has been uninstalled.",
                buttons=QtWidgets.QMessageBox.Ok,
                parent=self).exec_()
        except Exception as err:
            print(traceback.format_exc())
            OpenMaya.MGlobal.displayError(str(err))
        finally:
            self.close()

    def _onShowAllInfsClicked(self, enabled: bool) -> None:
        """
        Toggles between showing all influences in the skin cluster or only those affecting the current selection.

        Args:
            enabled (bool): The toggle state.
        """
        self._toolSettings.showAllInfs = enabled
        self._onSelectionChanged()

    def _onShowAllJointsToggled(self, showAll: bool) -> None:
        """Handler when toggling the show all joints button."""
        self.infListView.updateInfs(self.obj, showAll)

    def _onWeightsViewToggled(self, enabled: bool) -> None:
        """
        Switches the UI between the Table view and the List view.

        Args:
            enabled (bool): If True, shows the Table view. Otherwise, shows the List view.
        """
        if enabled:
            self._toolSettings.currentViewType = WeightViewType.Table
        else:
            self._toolSettings.currentViewType = WeightViewType.List

        self._resizeWindowWidthByWeightsView()

        self._rowWarningLimitLabel.setVisible(False)
        self._weightsListView.setVisible(not enabled)
        self._weightsTableView.setVisible(enabled)
        self._recollectTableData()

    def _onPinWeightsViewToggled(self, enabled: bool) -> None:
        """
        Toggles the 'Pinned' state of the tool.

        When enabled, the selection callback is removed so the tool stops updating based on Maya scene selection changes.

        Args:
            enabled (bool): The toggle state.
        """
        self._toolSettings.pinView = enabled
        if enabled:
            self._removeSelectionCallback()
        else:
            self._addSelectionCallback()

    def _onShowMaxInfsToggled(self, enabled: bool) -> None:
        """
        Toggles the viewport visualization for maximum influence limits.

        Args:
            enabled (bool): If True, switches the viewport to 'MaximumInfluences' color theme.
                            Otherwise, restores the active color theme.
        """
        self._toolSettings.showMaxInfs = enabled

        if enabled:
            self._showMaxInfsButton.setIcon(utils.loadPixmap("interface/show_max_infs.png"))
        else:
            self._showMaxInfsButton.setIcon(utils.loadPixmap("interface/hide_max_infs.png"))

        if enabled:
            self._switchColorTheme(ColorTheme.MaximumInfluences)
        else:
            colorThemeIndex = self._getActiveColorThemeIndex()
            self._switchColorTheme(colorThemeIndex)

    def _onInfListToggleLocksTriggered(self, infs: list[str]) -> None:
        """
        Toggles the lock state for the provided list of influences based on the current state of the first item in the list.

        Args:
            infs (list[str]): The influence names to toggle.
        """
        badInfs = [inf for inf in infs if inf not in self.obj.infs]
        if badInfs:
            OpenMaya.MGlobal.displayError(f"The joint(s) needs to be added to the skinCluster: {badInfs}")
            return

        infIndex = self.obj.infs.index(infs[0])
        lock = not self.locks[infIndex]
        self.toggleInfLocks(infs, lock)

    def _onInfListSetLocksTriggered(self, infs: list[str], enabled: bool):
        """
        Sets the locks for the specified influences.

        Args:
            infs (list[str]): List of influence names to modify.
            enabled (bool): True to lock, False to unlock.
        """
        badInfs = [inf for inf in infs if inf not in self.obj.infs]
        if badInfs:
            OpenMaya.MGlobal.displayError(f"The joint(s) needs to be added to the skinCluster: {badInfs}")
            return
        self.toggleInfLocks(infs, enabled)

    def _onInfListAddInfsToVertsTriggered(self) -> None:
        """
        Assigns a minor weight for selected influences to selected vertices.

        This effectively "adds" the influence to the vertex's skin cluster
        membership without significantly altering existing distribution.
        """
        if not self.obj.isValid():
            OpenMaya.MGlobal.displayError("There's no active object to work on.")
            return

        selectedVertIndexes = utils.extractIndexes(utils.getVertIndexes(self.obj.name))
        if not selectedVertIndexes:
            OpenMaya.MGlobal.displayError("There's no selected vertexes to set on.")
            return

        # Collect selected influence names.
        selectedInfs = []

        for index in self.infListView.selectedIndexes():
            if not index.isValid():
                continue

            item = self.infListView.listModel.itemFromIndex(index)
            infName = item.node()
            if infName not in self.obj.infs:
                OpenMaya.MGlobal.displayError(f"The joint needs to be added to the skinCluster: {infName}")
                return

            selectedInfs.append(infName)

        if not selectedInfs:
            OpenMaya.MGlobal.displayError("Nothing is selected in the influence list.")
            return

        oldSkinData = self.obj.skinData.copy()
        weightsView = self.getActiveWeightsView()
        tableSelection = weightsView.saveTableSelection()
        self.obj.addInfsToVerts(selectedInfs, selectedVertIndexes)
        newSkinData = self.obj.skinData.copy()

        self.addUndoCommand(
            "Add influence to verts",
            self.obj.name,
            oldSkinData,
            newSkinData,
            selectedVertIndexes,
            tableSelection)

        self._recollectTableData(updateSkinData=False, updateVerts=False)

    #
    # Public Methods.
    #

    def getActiveWeightsView(self) -> AbstractWeightsView:
        """
        Retrieves the weights view widget that is currently active/visible.

        Returns:
            The TableView or ListView instance.
        """
        if self._weightsViewButton.isChecked():
            return self._weightsTableView
        else:
            return self._weightsListView

    def collectDisplayInfs(self) -> None:
        """
        Refreshes the internal list of influences to be displayed in the views.
        Determines whether to show all influences in the skin cluster or only those affecting the currently selected vertices.
        """
        weightsView = self.getActiveWeightsView()

        if self._showAllInfsButton.isChecked():
            self.obj.collectInfColors()
            weightsView.setDisplayInfs(self.obj.getAllInfs())
        else:
            weightsView.setDisplayInfs(self._getInfsBySelectedVerts())

        self._collectInfLocks()

    def toggleInfLocks(self, infs: list[str], enabled: bool) -> None:
        """
        Sets the locks for the specified influences.

        Args:
            infs (list[str]): List of influence names to modify.
            enabled (bool): True to lock, False to unlock.
        """
        if enabled:
            description = "Lock influences"
        else:
            description = "Unlock influences"

        CommandLockInfs(
            self.__class__,
            description,
            infs,
            enabled)

    def updateVertColors(self, vertFilter: list[int] = []) -> None:
        """
        Updates the Maya viewport vertex color visualization based on current tool settings.

        Args:
            vertFilter (list[int], optional): List of vertex indices to restrict the color update to.
                                              Defaults to an empty list (all vertices).
        """
        showVertColors = self._shouldVertColorsBeShowing()

        if showVertColors:
            if self.colorInfluence is None:
                self._assignToFirstColorInf()

            if self.colorTheme == ColorTheme.Softimage:
                self.colorInfluence = None
                self.obj.displayMultiColorInfs(vertFilter=vertFilter)
            elif self.colorTheme == ColorTheme.MaximumInfluences:
                self.colorInfluence = None
                maxInfCount = self._pruneInfCountSpinBox.value()
                self.obj.displayMaxInfs(maxInfCount, vertFilter=vertFilter)
            else:
                if self.colorInfluence is not None:
                    self.obj.displayInf(self.colorInfluence, colorStyle=self.colorTheme, vertFilter=vertFilter)
        else:
            self.obj.hideVertColors()

        utils.toggleDisplayColors(self.obj.name, showVertColors)

    def addUndoCommand(
            self, description: str, obj: str, oldSkinData: SkinData, newSkinData: SkinData,
            vertIndexes: list[int], tableSelection: dict[str, Any], skipFirstRedo: bool = False) -> None:
        """
        Creates and pushes a new weight edit command to the undo stack.

        Args:
            description (str): Description of the edit for the undo queue.
            obj (str): The name of the mesh.
            oldSkinData (SkinData): Weights before the edit.
            newSkinData (SkinData): Weights after the edit.
            vertIndexes (list[int]): Indices of affected vertices.
            tableSelection (dict): Current UI selection state to restore on undo/redo.
            skipFirstRedo (bool, optional): If True, the first 'redo' call is ignored (useful for operations already applied in Maya).
        """
        CommandEditWeights(
            self.__class__,
            description,
            obj,
            oldSkinData,
            newSkinData,
            vertIndexes,
            tableSelection,
            skipFirstRedo=skipFirstRedo)


def run():
    """
    The main entry point to create an instance of the tool and run it.
    """
    WeightsEditor.run()
