from typing import Any

from maya import cmds

from weights_editor_tool.qt import QtCore, QtGui, QtWidgets
from weights_editor_tool import qt
from weights_editor_tool.enums import ColorTheme
from weights_editor_tool import weights_editor_utils as utils
from weights_editor_tool.widgets import custom_header_view


class AbstractWeightsView(QtWidgets.QTableView):
    """
    An abstract base class for weight-specific table and list views.

    This class provides shared UI functionality.
    It handles header interactions, context menus for influence locking/sorting, and custom viewport painting for user guidance.

    Signals:
        keyPressed (QKeyEvent): Emitted when the user presses a key.
        headerMiddleClicked (str): Emitted with the name of the influence middle-clicked.
        displayInfTriggered (str): Emitted to trigger viewport weight visualization.
        selectInfVertsTriggered (str): Emitted to select affected vertices in Maya.

    Args:
        headerOrientation (Orientation): Determines if headers are Horizontal or Vertical.
        editorInstance (WeightsEditor): The main tool instance for shared state access.
    """

    headerMiddleClicked = QtCore.Signal(str)
    displayInfTriggered = QtCore.Signal(str)
    selectInfVertsTriggered = QtCore.Signal(str)
    selectInfBordersTriggered = QtCore.Signal(str)

    def __init__(self, headerOrientation: QtCore.Qt.Orientation, editorInstance: 'WeightsEditor') -> None:
        """
        Initializes the view, configures custom headers, and sets up context menu actions.
        """
        super(AbstractWeightsView, self).__init__(editorInstance)

        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setGridStyle(QtCore.Qt.DashLine)

        systemFont = QtWidgets.QApplication.font()

        self._orientation = headerOrientation
        self._font = QtGui.QFont(systemFont.family(), systemFont.pixelSize()-1)
        self._editorInstance = editorInstance
        self._oldSkinData = None  # Need to store this to work with undo/redo.
        self.tableModel = None

        imageHeight = 50
        self._selectSkinImage = utils.loadPixmap("table_view/select_skin.png", height=imageHeight)
        self._sadImage = utils.loadPixmap("table_view/sad.png", height=imageHeight)
        self._selectPointsImage = utils.loadPixmap("table_view/select_points.png", height=imageHeight)

        self._header = None

        if headerOrientation == QtCore.Qt.Horizontal:
            self._header = custom_header_view.CustomHeaderView(headerOrientation, parent=self)
        else:
            self._header = custom_header_view.VerticalHeaderView(parent=self)

        self._header.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self._header.customContextMenuRequested.connect(self._onHeaderCustomContextMenuTriggered)
        self._header.headerLeftClicked.connect(self._onHeaderLeftClicked)
        self._header.headerMiddleClicked.connect(self._onHeaderMiddleClicked)

        if headerOrientation == QtCore.Qt.Horizontal:
            self.setHorizontalHeader(self._header)
        else:
            self.setVerticalHeader(self._header)

        self._lockInfAction = qt.QAction(self)
        self._lockInfAction.setText("Lock influence")
        self._lockInfAction.triggered.connect(self._onLockInfTriggered)

        self._unlockInfAction = qt.QAction(self)
        self._unlockInfAction.setText("Unlock influence")
        self._unlockInfAction.triggered.connect(self._onTriggeredUnlockInf)

        self._displayInfAction = qt.QAction(self)
        self._displayInfAction.setText("Display influence (middle-click)")
        self._displayInfAction.triggered.connect(self._onDisplayInfTriggered)

        self._selectInfVertsAction = qt.QAction(self)
        self._selectInfVertsAction.setText("Select vertexes effected by influence")
        self._selectInfVertsAction.triggered.connect(self._onSelectInfVertsTriggered)

        self._selectInfBordersAction = qt.QAction(self)
        self._selectInfBordersAction.setText("Select influence's borders")
        self._selectInfBordersAction.triggered.connect(self._onSelectInfBordersTriggered)

        self._selectInfAction = qt.QAction(self)
        self._selectInfAction.setText("Select influence")
        self._selectInfAction.triggered.connect(self._onSelectInfTriggered)

        self._sortByWeightsAscendingAction = qt.QAction(self)
        self._sortByWeightsAscendingAction.setText("Sort by weights (ascending)")
        self._sortByWeightsAscendingAction.triggered.connect(self._onSortByWeightsAscendingTriggered)

        self._sortByWeightsDescendingAction = qt.QAction(self)
        self._sortByWeightsDescendingAction.setText("Sort by weights (descending)")
        self._sortByWeightsDescendingAction.triggered.connect(self._onSortByWeightsDescendingTriggered)

        self._headerContextMenu = QtWidgets.QMenu(parent=self)
        self._headerContextMenu.addAction(self._displayInfAction)
        self._headerContextMenu.addSeparator()
        self._headerContextMenu.addAction(self._selectInfAction)
        self._headerContextMenu.addAction(self._selectInfVertsAction)
        self._headerContextMenu.addAction(self._selectInfBordersAction)
        self._headerContextMenu.addSeparator()
        self._headerContextMenu.addAction(self._lockInfAction)
        self._headerContextMenu.addAction(self._unlockInfAction)
        self._headerContextMenu.addSeparator()
        self._headerContextMenu.addAction(self._sortByWeightsAscendingAction)
        self._headerContextMenu.addAction(self._sortByWeightsDescendingAction)

    def paintEvent(self, paintEvent: QtGui.QPaintEvent) -> None:
        """
        Custom paint event to draw 'Call to Action' messages.

        If the view is empty, it checks the state of the SkinnedObj:
            1. No Object: Prompts to select a mesh.
            2. No SkinCluster: Notifies the user of missing skinning.
            3. No Selection: Prompts to select vertices/CVs.

        Args:
            paintEvent (QPaintEvent): The Qt paint event.
        """
        if self.model().rowCount(self) == 0:
            if not self._editorInstance.obj.isValid():
                message = ("Select a skinned object and push\n"
                       "the button on top edit its weights.")
                image = self._selectSkinImage
            elif not self._editorInstance.obj.hasValidSkin():
                message = "Unable to detect a skinCluster on this object."
                image = self._sadImage
            else:
                message = "Select the object's components to edit it."
                image = self._selectPointsImage

            painter = QtGui.QPainter(self.viewport())
            if not painter.isActive():
                painter.begin(self)

            if image is not None:
                painter.drawPixmap(
                    self.width() / 2 - image.width() / 2,
                    self.height() / 2 - image.height(),
                    image)

            rect = paintEvent.rect()
            rect.setTop(self.height() / 2)
            rect.setLeft(rect.left() + 5)
            rect.setRight(rect.right() - 5)

            painter.setPen(QtGui.QColor(255, 255, 255))
            painter.setFont(self._font)
            painter.drawText(rect, QtCore.Qt.AlignHCenter | QtCore.Qt.AlignTop | QtCore.Qt.TextWordWrap, message)
            painter.end()

        QtWidgets.QTableView.paintEvent(self, paintEvent)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        """
        Extends the mouse press to trigger cell editing.

        On Right-Click: Captures a snapshot of current skin weights for undo purposes and opens the item delegate (editor) for the cell.

        Args:
            event (QMouseEvent): The mouse press event.
        """
        QtWidgets.QTableView.mousePressEvent(self, event)

        # Begins edit on current cell.
        if event.button() == QtCore.Qt.MouseButton.RightButton:
            # Save this prior to any changes.
            self._oldSkinData = self._editorInstance.obj.skinData.copy()
            self.edit(self.currentIndex())

    def selectItemsByInf(self) -> None:
        """
        Selects all cells or items in the view that correspond to a specific influence.
        To be implemented by subclasses to handle specific selection logic.
        """
        raise NotImplementedError

    def getSelectedVertsAndInfs(self) -> list[tuple[int, str]]:
        """
        Retrieves a list of (vertexIndex, influenceName) pairs based on current UI selection.

        Returns:
            A list of tuples containing the vertex index and the influence name for every selected cell.
        """
        raise NotImplementedError

    def saveTableSelection(self) -> dict[str, list[int]]:
        """
        Captures the current UI selection state to be restored later.

        Returns:
            A mapping of selection metadata (row/column indices).
        """
        raise NotImplementedError

    def loadTableSelection(self, selectionData: dict[str, list[int]]) -> None:
        """
        Restores a previously saved UI selection state.

        Args:
            selectionData (dict[str, list[int]]): The data captured by saveTableSelection.
        """
        raise NotImplementedError

    def fitHeadersToContents(self) -> None:
        """
        Resizes the headers to ensure all text and weight values are visible without being truncated.
        """
        raise NotImplementedError

    def _onSortByWeightsAscendingTriggered(self) -> None:
        """Abstract method to sort the view by weight values in ascending order."""
        raise NotImplementedError

    def _onSortByWeightsDescendingTriggered(self) -> None:
        """Abstract method to sort the view by weight values in descending order."""
        raise NotImplementedError

    def _getLastClickedInf(self):
        """
        Retrieves the influence name associated with the most recently interacted header index.

        Returns:
            The influence name.
        """
        return self.tableModel.displayInfs[self._header.lastIndex]

    def _setModel(self, abstractModel: QtCore.QAbstractTableModel) -> None:
        """
        Internal helper to link the view to the weights data model.

        Args:
            abstractModel (QAbstractTableModel): The custom model instance.
        """
        self.tableModel = abstractModel
        self.setModel(self.tableModel)

    def _resetColorHeaders(self) -> None:
        """Clears existing header color data from the model."""
        self.tableModel.headerColors = []

    def _getSelectedIndexes(self) -> list[int]:
        """
        Filters the view's current selection for valid indexes.

        Returns:
            list[QModelIndex]: List of valid selected model indexes.
        """
        return [
            index
            for index in self.selectedIndexes()
            if index.isValid()
        ]

    def _onHeaderCustomContextMenuTriggered(self, point: QtCore.QPoint) -> None:
        """
        Displays the influence context menu at the requested global position.

        Args:
            point (QPoint): Local coordinates where the menu was requested.
        """
        self._headerContextMenu.exec_(self.mapToGlobal(point))

    def _onHeaderLeftClicked(self, index: int) -> None:
        """
        Selects the entire column when a horizontal header is clicked.

        Args:
            index (int): The index of the header that was clicked.
        """
        self.selectColumn(index)

    def _onHeaderMiddleClicked(self, index: int) -> None:
        """
        Retrieves the influence name and emits a signal to visualize it.

        Args:
            index (int): The index of the header that was middle-clicked.
        """
        inf = self.tableModel.displayInfs[index]
        self.headerMiddleClicked.emit(inf)

    def _onDisplayInfTriggered(self) -> None:
        """Emits a signal to display the last interacted influence in the viewport."""
        self.displayInfTriggered.emit(self._getLastClickedInf())

    def _onLockInfTriggered(self) -> None:
        """Triggers a weight lock for the last interacted influence."""
        self._editorInstance.toggleInfLocks([self._getLastClickedInf()], True)

    def _onTriggeredUnlockInf(self) -> None:
        """Triggers a weight unlock for the last interacted influence."""
        self._editorInstance.toggleInfLocks([self._getLastClickedInf()], False)

    def _onSelectInfVertsTriggered(self) -> None:
        """Emits a signal to select all vertices affected by the current influence."""
        self.selectInfVertsTriggered.emit(self._getLastClickedInf())

    def _onSelectInfBordersTriggered(self) -> None:
        """Emits a signal to select border vertices affected by the current influence."""
        self.selectInfBordersTriggered.emit(self._getLastClickedInf())

    def _onSelectInfTriggered(self) -> None:
        """Selects the actual influence in the Maya scene."""
        inf = self._getLastClickedInf()
        if cmds.objExists(inf):
            cmds.select(inf)

    def displayInfs(self) -> list[str]:
        """
        Returns the list of influences currently being displayed in the model.

        Returns:
            Influence names.
        """
        return self.tableModel.displayInfs

    def setDisplayInfs(self, newInfs: list[str]):
        """
        Updates the model's influence list.

        Args:
            newInfs (list[str]): The new list of influences to show.
        """
        self.tableModel.displayInfs = newInfs

    def beginUpdate(self) -> None:
        """Notifies the view that the underlying model layout is about to change."""
        self.tableModel.layoutAboutToBeChanged.emit()

    def endUpdate(self) -> None:
        """Notifies the view that the model layout changes are complete."""
        self.tableModel.layoutChanged.emit()

    def emitHeaderDataChanged(self) -> None:
        """Signals the view to refresh its header visuals (labels and colors)."""
        infCount = len(self.tableModel.displayInfs)
        if self._orientation == QtCore.Qt.Horizontal:
            self.tableModel.headerDataChanged.emit(QtCore.Qt.Horizontal, 0, infCount)
        else:
            self.tableModel.headerDataChanged.emit(QtCore.Qt.Vertical, 0, infCount)

    def colorHeaders(self, count: int) -> None:
        """
        Populates the model's header color list.
        If the Softimage theme is active, it fetches the unique RGB colors from the SkinnedObj instance.

        Args:
            count (int): Number of headers to process.
        """
        self._resetColorHeaders()

        if self._editorInstance.colorTheme == ColorTheme.Softimage:
            for index in range(count):
                headerName = self.tableModel.getInf(index)
                rgb = self._editorInstance.obj.infColors.get(headerName)

                color = None
                if rgb is not None:
                    color = QtGui.QColor.fromRgbF(*rgb)
                self.tableModel.headerColors.append(color)

    def setDisplayShortNames(self, enabled: bool) -> None:
        """
        Toggles between long DAG paths and short names in the headers.

        Args:
            enabled (bool): Whether to show short names.
        """
        self.beginUpdate()
        self.tableModel.displayShortNames = enabled
        self.endUpdate()


class AbstractModel(QtCore.QAbstractTableModel):
    """
    An abstract data model for managing and formatting skin weight data.

    This class defines the interface for data retrieval and provides shared styling logic,
    such as color-coding weights based on their value and handling influence display names.

    Args:
        editorInstance (WeightsEditor): Reference to the main editor for accessing scene data and lock states.
        parent (QWidget, optional): Parent widget for Qt memory management.
    """

    def __init__(self, editorInstance: 'WeightsEditor', parent: QtWidgets.QWidget = None) -> None:
        """
        Initializes default colors and display settings for the model.
        """
        super(AbstractModel, self).__init__(parent)
        
        self._editorInstance = editorInstance

        self._lockedTextColor = QtGui.QColor(140, 140, 140)
        self._lockedBackgroundColor = QtGui.QColor(70, 70, 70)
        self._headerLockedTextColor = QtGui.QColor(QtCore.Qt.black)
        self._headerActiveInfBackgroundColor = QtGui.QColor(60, 170, 60)

        # This is a blank icon to give whitespace from the text, otherwise the text is too near the cell's edge.
        self._spacerIcon = QtGui.QPixmap(3, 1)
        self._spacerIcon.fill(QtCore.Qt.transparent)

        self.headerColors = []
        self.displayInfs = []
        self.inputValue = None  # Used to properly set multiple cells.
        self.displayShortNames = True

    def rowCount(self, parent: QtCore.QModelIndex) -> int:
        """Abstract: Must return the number of vertices or influences."""
        raise NotImplementedError

    def columnCount(self, parent: QtCore.QModelIndex) -> int:
        """Abstract: Must return the number of vertices or influences."""
        raise NotImplementedError

    def data(self, index: QtCore.QModelIndex, role: QtCore.Qt.ItemDataRole) -> Any:
        """Abstract: Must return data for Display, Decoration, or Edit roles."""
        raise NotImplementedError

    def setData(self, index: QtCore.QModelIndex, value: Any, role: QtCore.Qt.ItemDataRole) -> bool:
        """Abstract: Must handle weight updates from the UI."""
        raise NotImplementedError

    def headerData(self, column: int, orientation: QtCore.Qt.Orientation, role: QtCore.Qt.ItemDataRole) -> Any:
        """Abstract: Must provide influence names or vertex indices."""
        raise NotImplementedError

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlags:
        """
        Sets the interaction state for the cells.

        Returns:
            Enabled | Selectable | Editable.
        """
        return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEditable

    def getInf(self, index: QtCore.QModelIndex) -> str:
        """
        Retrieves the name of the influence at the specified model index.

        Args:
            index (int): The column or row index in the model.

        Returns:
            The influence name.
        """
        return self.displayInfs[index]

    # TODO: Optimize this function since it gets called often
    def _getWeightTextColor(self, inf: str, value: float) -> QtGui.QColor:
        """
        Determines the text color for a weight cell based on its value.

        Weights are color-coded using linear interpolation:
            - Gray: Zero or near-zero weights.
            - Light Blue to Green: Low to mid-range weights (0.0 - 0.5).
            - Green to Orange/Red: Mid to high-range weights (0.5 - 1.0).
            - White: Full 1.0 weighting.
            - Specific Gray: Used if the influence is currently locked.

        Args:
            inf (str): The name of the influence.
            value (float): The current skin weight (0.0 to 1.0).

        Returns:
            The calculated color for the UI text.
        """
        infIndex = self._editorInstance.obj.infs.index(inf)
        isLocked = self._editorInstance.locks[infIndex]
        if isLocked:
            return self._lockedTextColor

        zeroWeightColor = QtGui.QColor(QtCore.Qt.gray)
        lowWeightColor = QtGui.QColor(50, 200, 255)
        midWeightColor = QtGui.QColor(50, 255, 50)
        highWeightColor = QtGui.QColor(255, 100, 50)
        fullWeightColor = QtGui.QColor(QtCore.Qt.white)

        if value <= 0.001:
            textColor = zeroWeightColor
        elif value == 1:
            textColor = fullWeightColor
        elif value < 0.5:
            lerpValue = value*2
            textColor = utils.lerpColor(lowWeightColor,midWeightColor,lerpValue)
        else:
            lerpValue = (value-0.5)*2
            textColor = utils.lerpColor(midWeightColor,highWeightColor,lerpValue)

        return textColor
