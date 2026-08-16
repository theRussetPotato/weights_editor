import os
import json
from typing import Optional, Any
from dataclasses import dataclass, fields

from weights_editor_tool.qt import QtCore
from weights_editor_tool import weights_editor_utils as utils


@dataclass
class ColorTheme:
    """Defines the color theme that vertex colors should display."""
    Max: int = 0
    Maya: int = 1
    Softimage: int = 2
    MaximumInfluences: int = 3


@dataclass
class WeightViewType:
    """Defines the tool's method to view skin weights."""
    List: int = 0
    Table: int = 1


@dataclass
class MirrorAxis:
    """Defines the mirror function's planar axis options."""
    negXY: str = "-XY"
    XY: str = "XY"
    negYZ: str = "-YZ"
    YZ: str = "YZ"
    negXZ: str = "-XZ"
    XZ: str = "XZ"


@dataclass
class MirrorSurface:
    """Defines the mirror function's surface association options."""
    closestPoint: str = "closestPoint"
    rayCast: str = "rayCast"
    closestComponent: str = "closestComponent"


@dataclass
class MirrorInfluence:
    """Defines the mirror function's influence association options."""
    label: str = "label"
    closestPoint: str = "closestPoint"
    closestBone: str = "closestBone"
    name: str = "name"
    oneToOne: str = "oneToOne"


@dataclass
class Axis:
    x: str = "x"
    y: str = "y"
    z: str = "z"


@dataclass
class JointLabelsSetOn:
    allJoints: str = "All Joints"
    selectedJoints: str = "Selected Joints"


@dataclass
class HotkeyData:
    """Defines a hotkey's properties."""
    name: str = None
    key: int = -1
    ctrl: bool = False
    shift: bool = False
    alt: bool = False
    toolTip: str = ""

    def serialize(self) -> dict[str, Any]:
        data = self.__dict__
        data["key"] = int(self.key)
        return data


@dataclass
class HotkeySettings:
    """Defines all hotkeys for the tool."""
    toggleTableListViews: Optional[HotkeyData] = None
    showInfList: Optional[HotkeyData] = None
    showInfColors: Optional[HotkeyData] = None
    mirrorAll: Optional[HotkeyData] = None
    prune: Optional[HotkeyData] = None
    pruneMaxInfs: Optional[HotkeyData] = None
    runSmooth: Optional[HotkeyData] = None
    runSmoothAllInfs: Optional[HotkeyData] = None
    growSelection: Optional[HotkeyData] = None
    shrinkSelection: Optional[HotkeyData] = None
    selectEdgeLoop: Optional[HotkeyData] = None
    selectRingLoop: Optional[HotkeyData] = None
    selectPerimeter: Optional[HotkeyData] = None
    selectShell: Optional[HotkeyData] = None
    toggleInfLock: Optional[HotkeyData] = None
    toggleInfLock2: Optional[HotkeyData] = None
    addWeightUp: Optional[HotkeyData] = None
    addWeightDown: Optional[HotkeyData] = None
    scaleWeightUp: Optional[HotkeyData] = None
    scaleWeightDown: Optional[HotkeyData] = None

    def __post_init__(self):
        if self.toggleTableListViews is None:
            self.toggleTableListViews = HotkeyData(
                name="Toggle table / list views", key=QtCore.Qt.Key_QuoteLeft, ctrl=True,
                toolTip="Toggle the weights view to display as a table or a list")

        if self.showInfList is None:
            self.showInfList = HotkeyData(
                name="Show inf list", key=QtCore.Qt.Key_4, ctrl=True,
                toolTip="Toggle visibility of the influence list panel")

        if self.showInfColors is None:
            self.showInfColors = HotkeyData(
                name="Show inf colors", key=QtCore.Qt.Key_6, ctrl=True,
                toolTip="Toggle if vertex colors should be shown")

        if self.mirrorAll is None:
            self.mirrorAll = HotkeyData(
                name="Mirror all", key=QtCore.Qt.Key_M, ctrl=True,
                toolTip="Mirrors skin weights from all vertexes")

        if self.prune is None:
            self.prune = HotkeyData(
                name="Prune", key=QtCore.Qt.Key_P, ctrl=True,
                toolTip="Prunes skin weights below a specific value")

        if self.pruneMaxInfs is None:
            self.pruneMaxInfs = HotkeyData(
                name="Prune max infs", key=QtCore.Qt.Key_P, ctrl=True, shift=True,
                toolTip="Prunes influences from vertexes so they don't exceed a certain count")

        if self.runSmooth is None:
            self.runSmooth = HotkeyData(
                name="Run smooth (vert infs)", key=QtCore.Qt.Key_S, ctrl=True, shift=True,
                toolTip="Smooth skin weights on selected vertexes with only influences weighted to the vert")

        if self.runSmoothAllInfs is None:
            self.runSmoothAllInfs = HotkeyData(
                name="Run smooth (all infs)", key=QtCore.Qt.Key_D, ctrl=True, shift=True,
                toolTip="Smooth skin weights on selected vertexes that may add neighbouring influences")

        if self.growSelection is None:
            self.growSelection = HotkeyData(
                name="Grow selection", key=QtCore.Qt.Key_Greater,
                toolTip="Grows current vertex selection")

        if self.shrinkSelection is None:
            self.shrinkSelection = HotkeyData(
                name="Shrink selection", key=QtCore.Qt.Key_Less,
                toolTip="Shrinks current vertex selection")

        if self.selectEdgeLoop is None:
            self.selectEdgeLoop = HotkeyData(
                name="Select edge loop", key=QtCore.Qt.Key_E, ctrl=True,
                toolTip="Uses selected vertexes to select an edge loop")

        if self.selectRingLoop is None:
            self.selectRingLoop = HotkeyData(
                name="Select ring loop", key=QtCore.Qt.Key_R, ctrl=True,
                toolTip="Uses selected vertexes to select a ring loop")

        if self.selectPerimeter is None:
            self.selectPerimeter = HotkeyData(
                name="Select perimeter", key=QtCore.Qt.Key_T, ctrl=True,
                toolTip="Uses selected vertexes to select its perimeter")

        if self.selectShell is None:
            self.selectShell = HotkeyData(
                name="Select shell", key=QtCore.Qt.Key_A, ctrl=True, shift=True,
                toolTip="Uses selected vertexes to select its shell")

        if self.toggleInfLock is None:
            self.toggleInfLock = HotkeyData(
                name="Toggle inf lock", key=QtCore.Qt.Key_Space,
                toolTip="Toggles lock state on selected influences from the influence list or weights view")

        if self.toggleInfLock2 is None:
            self.toggleInfLock2 = HotkeyData(
                name="Toggle inf lock 2", key=QtCore.Qt.Key_L,
                toolTip=" Alternate key to toggle lock state on selected influences from the influence list or weights view")

        if self.addWeightUp is None:
            self.addWeightUp = HotkeyData(
                name="Add Weight Up", key=QtCore.Qt.Key_Up, ctrl=True,
                toolTip="Increases weight on selected vertexes\n(from selected influences in weights view)")

        if self.addWeightDown is None:
            self.addWeightDown = HotkeyData(
                name="Add Weight Down", key=QtCore.Qt.Key_Down, ctrl=True,
                toolTip="Decreases weight on selected vertexes\n(from selected influences in weights view)")

        if self.scaleWeightUp is None:
            self.scaleWeightUp = HotkeyData(
                name="Scale Weight Up", key=QtCore.Qt.Key_Up, shift=True,
                toolTip="Scales up weight on selected vertexes\n(from selected influences in weights view)")

        if self.scaleWeightDown is None:
            self.scaleWeightDown = HotkeyData(
                name="Scale Weight Down", key=QtCore.Qt.Key_Down, shift=True,
                toolTip="Scales down weight on selected vertexes\n(from selected influences in weights view)")

    def serialize(self) -> dict[str, dict[str, Any]]:
        """Serializes the settings to a dictionary."""
        serializedHotkeys = {}
        for hotkeyField in fields(self):
            fieldName = hotkeyField.name
            hotkeyData: HotkeyData = getattr(self, fieldName)
            serializedHotkeys[fieldName] = hotkeyData.serialize()
        return serializedHotkeys


@dataclass
class ToolSettings:
    """Defines all settings across the tool."""
    colorTheme: ColorTheme = ColorTheme.Max
    enableInstantTooltips: bool = True
    displayShortNames: bool = True
    deleteSkinOnExport: bool = True
    enableHotkeys: bool = True
    enableAddPresets: bool = True
    enableScalePresets: bool = True
    enableSetPresets: bool = True
    checkForUpdatesOnOpen: bool = True
    pinView: bool = False
    showAllInfs: bool = False
    autoSelectVertexFromCell: bool = True
    hideVertColors: bool = False
    showInfView: bool = True
    showPresetButtonsView: bool = True
    showMaxInfs: bool = False
    pruneValue: float = 0.1
    pruneMaxInfsValue: int = 4
    smoothPreserveStrength: float = 1.0
    smoothAddLevels: int = 1
    smoothAddStrength: float = 1.0
    selectInfEdgeLevels: int = 1
    hotkeys: Optional[HotkeySettings] = None
    lastBrowserPath: Optional[str] = None
    currentViewType: WeightViewType = WeightViewType.List
    addPresetValues: tuple[float] = (-0.1, -0.05, -0.01, 0.01, 0.05, 0.1)
    scalePresetValues: tuple[float] = (-25.0, -10.0, -5.0, 5.0, 10.0, 25.0)
    setPresetValues: tuple[float] = (0.0, 0.1, 0.25, 0.5, 0.75, 1.0)
    mirrorAxis: MirrorAxis = MirrorAxis.YZ
    mirrorSurface: MirrorSurface = MirrorSurface.closestPoint
    mirrorInfluence: MirrorInfluence = MirrorInfluence.closestBone
    jointLabelsSetOn: JointLabelsSetOn = JointLabelsSetOn.allJoints
    jointLabelsCenterAxis: Axis = Axis.x
    jointLabelsCenterThreshold: float = 0.001
    jointLabelsLeftPrefix: str = "L_"
    jointLabelsRightPrefix: str = "R_"

    def __post_init__(self):
        """After an instance is initialized it uses default hot key settings if they are null."""
        if self.hotkeys is None:
            self.hotkeys = HotkeySettings()

    @classmethod
    def readUserSettings(cls) -> Optional["ToolSettings"]:
        """Tries to fetch the user's settings saved locally."""
        # Exit if there are no settings to fetch.
        settingsPath = utils.getSettingsPath()
        if not os.path.exists(settingsPath):
            return

        # Read settings from the file.
        with open(settingsPath, "r") as f:
            serializedToolSettings = json.loads(f.read())

        # Remove any settings that aren't valid.
        serializedToolSettings = {
            key: value
            for key, value in serializedToolSettings.items()
            if hasattr(cls, key)}

        serializedHotkeys = None
        if "hotkeys" in serializedToolSettings:
            serializedHotkeys = serializedToolSettings.pop("hotkeys")

        newToolSettings = cls(**serializedToolSettings)

        if serializedHotkeys is not None:
            serializedHotkeys = {
                key: HotkeyData(**value)
                for key, value in serializedHotkeys.items()
                if hasattr(newToolSettings.hotkeys, key)}
            newHotkeys = HotkeySettings(**serializedHotkeys)
            newToolSettings.hotkeys = newHotkeys

        return newToolSettings

    def serialize(self) -> dict[str, Any]:
        """Serializes settings to a dictionary."""
        serializedToolSettings = self.__dict__
        serializedToolSettings["hotkeys"] = self.hotkeys.serialize()
        return serializedToolSettings
