from typing import Any

from maya import cmds

from weights_editor_tool.qt import QtCore, QtWidgets
from weights_editor_tool import qt
from weights_editor_tool import weights_editor_utils as utils
from weights_editor_tool.widgets import abstract_weights_view


class TableView(abstract_weights_view.AbstractWeightsView):
    """
    A multi-column table view representing the vertex-to-influence weight grid.

    This class handles bi-directional selection between the table cells and Maya's viewport selection,
    and supports sorting vertices based on their weight values for specific joints.

    Signals:
        updateEnded (bool): Emitted when the table refresh finishes. Returns True if vertex count exceeds display limits.
    """

    updateEnded = QtCore.Signal(bool)

    def __init__(self, editorInstance: 'WeightsEditor') -> None:
        """
        Initializes the table with a horizontal header and custom sort actions.

        Args:
            editorInstance (WeightsEditor): The central controller hub.
        """
        super(TableView, self).__init__(QtCore.Qt.Horizontal, editorInstance)

        self.autoSelectVertexFromCell = True
        self._selectedRows = set()
        self._header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)

        self._sortWeightsByVertOrderAction = qt.QAction(self)
        self._sortWeightsByVertOrderAction.setText("Sort by weights (vertex order)")
        self._sortWeightsByVertOrderAction.triggered.connect(self._onSortWeightsByVertOrderTriggered)

        self._headerContextMenu.addAction(self._sortWeightsByVertOrderAction)

        tableModel = TableModel(editorInstance, parent=self)
        self._setModel(tableModel)

    def selectionChanged(self, selected: QtCore.QItemSelection, deselected: QtCore.QItemSelection) -> None:
        """
        Triggers internal selection logic whenever the user highlights cells.

        Args:
            selected (QItemSelection): Newly selected items.
            deselected (QItemSelection): Items removed from selection.
        """
        QtWidgets.QTableView.selectionChanged(self, selected, deselected)
        self._onCellSelectionChanged()

    def closeEditor(self, editor: QtWidgets.QLineEdit, hint: QtWidgets.QAbstractItemDelegate.EndEditHint) -> None:
        """
        Applies a weight value edit to all selected cells and records an undo command.

        Args:
            editor (QLineEdit): The input widget.
            hint (EndEditHint): The reason for closing.
        """
        isCancelled = (hint == QtWidgets.QAbstractItemDelegate.RevertModelCache)
        
        if not isCancelled:
            for index in self.selectedIndexes():
                if index == self.currentIndex():
                    continue
                self.model().setData(index, None, QtCore.Qt.EditRole)
        
        QtWidgets.QTableView.closeEditor(self, editor, hint)
        
        if self.model().inputValue is not None:
            self.model().inputValue = None
            
            vertIndexes = list(set(
                self.model().getVertIndex(index.row())
                for index in self.selectedIndexes()))
            
            self._editorInstance.addUndoCommand(
                "Set skin weights",
                self._editorInstance.obj.name,
                self._oldSkinData,
                self._editorInstance.obj.skinData.copy(),
                vertIndexes,
                self.saveTableSelection())
        
        self._oldSkinData = None

    def _reorderRows(self, column: int, order: QtCore.Qt.SortOrder) -> None:
        """
        Sorts the vertices (rows) based on weight values in the specified column.

        Args:
            column (int): The influence index to sort by.
            order (SortOrder): Ascending, Descending, or None (for vertex index order).
        """
        self.beginUpdate()
        selectionData = self.saveTableSelection()

        inf = self.tableModel.displayInfs[column]

        if order is None:
            self._editorInstance.vertIndexes = sorted(self._editorInstance.vertIndexes)
        else:
            self._editorInstance.vertIndexes = sorted(
                self._editorInstance.vertIndexes,
                key=lambda x: self._editorInstance.obj.skinData[x]["weights"].get(inf) or 0.0,
                reverse=order)

        self.endUpdate()
        self.loadTableSelection(selectionData)

    def _onSortByWeightsAscendingTriggered(self) -> None:
        """Triggers a row reorder based on the last interacted column in ascending order."""
        self._reorderRows(self._header.lastIndex, QtCore.Qt.DescendingOrder)

    def _onSortByWeightsDescendingTriggered(self) -> None:
        """Triggers a row reorder based on the last interacted column in descending order."""
        self._reorderRows(self._header.lastIndex, QtCore.Qt.AscendingOrder)

    def _onSortWeightsByVertOrderTriggered(self) -> None:
        """Resets the row order to match the natural Maya vertex index sequence."""
        self._reorderRows(self._header.lastIndex, None)

    def _onCellSelectionChanged(self) -> None:
        """
        Syncs the table selection to the Maya viewport.
        Selecting a row in the table will select the corresponding vertex in Maya.
        """
        if self._editorInstance.ignoreCellSelectionEvent or not self.autoSelectVertexFromCell:
            return

        rows = set(
            index.row()
            for index in self._getSelectedIndexes()
        )

        if rows == self._selectedRows:
            return

        self._selectedRows = rows

        if self._editorInstance.obj.isValid():
            component = "vtx"
            if utils.isNurbsCurve(self._editorInstance.obj.name):
                component = "cv"

            vertexList = [
                f"{self._editorInstance.obj.name}.{component}[{self._editorInstance.vertIndexes[row]}]"
                for row in rows
            ]
        else:
            vertexList = []

        self._editorInstance.blockSelectionCallback = True
        cmds.select(vertexList)
        self._editorInstance.blockSelectionCallback = False

    def colorHeaders(self) -> None:
        """
        Applies colors to the horizontal headers based on influence state.
        """
        count = self.tableModel.columnCount(self)
        super(TableView, self).colorHeaders(count)

    def selectItemsByInf(self, inf: str) -> None:
        """
        Selects an entire column based on the influence name.

        Args:
            inf (str): The influence name.
        """
        if inf and inf in self.tableModel.displayInfs:
            column = self.tableModel.displayInfs.index(inf)
            selectionModel = self.selectionModel()
            index = self.model().createIndex(0, column)
            flags = QtCore.QItemSelectionModel.ClearAndSelect | QtCore.QItemSelectionModel.Columns
            selectionModel.select(index, flags)
        else:
            self.clearSelection()

    def getSelectedVertsAndInfs(self) -> list[tuple[int, str]]:
        """
        Converts the current cell selection into specific vertex and influence pairs.

        Returns:
            A list of tuples containing (vertexIndex, influenceName).
        """
        indexes = self._getSelectedIndexes()
        if not indexes:
            return []

        vertsAndInfs = []

        for index in indexes:
            row = index.row()
            column = index.column()
            if column >= len(self.tableModel.displayInfs):
                continue

            vertIndex = self._editorInstance.vertIndexes[row]
            inf = self.tableModel.displayInfs[column]
            vertsAndInfs.append((vertIndex, inf))

        return vertsAndInfs

    def saveTableSelection(self) -> dict[str, list[int]]:
        """
        Captures the current grid selection into a data structure.

        Returns:
            A dictionary mapping influence names to vertex index lists.
        """
        selectionData = {}

        for index in self.selectedIndexes():
            if not index.isValid():
                continue

            if index.column() > len(self.tableModel.displayInfs) - 1:
                continue

            inf = self.tableModel.displayInfs[index.column()]
            if inf not in selectionData:
                selectionData[inf] = []

            if index.row() > len(self._editorInstance.vertIndexes):
                continue

            vertIndex = self._editorInstance.vertIndexes[index.row()]
            selectionData[inf].append(vertIndex)

        return selectionData

    def loadTableSelection(self, selectionData: dict[str, list[int]]) -> None:
        """
        Restores cell selection using vertex indices and influence names.

        Args:
            selectionData (dict): The previously saved selection data.
        """
        self.clearSelection()

        if not selectionData:
            return

        selectionModel = self.selectionModel()
        itemSelection = QtCore.QItemSelection()

        for inf, vertIndexes in selectionData.items():
            if inf not in self.tableModel.displayInfs:
                continue

            column = self.tableModel.displayInfs.index(inf)

            for vertIndex in vertIndexes:
                if vertIndex not in self._editorInstance.vertIndexes:
                    continue

                row = self._editorInstance.vertIndexes.index(vertIndex)
                index = self.model().index(row, column)
                itemSelection.append(QtCore.QItemSelectionRange(index, index))

        selectionModel.select(itemSelection, QtCore.QItemSelectionModel.Select)

    def fitHeadersToContents(self) -> None:
        """
        Resizes every column to ensure the influence names and icons are fully visible.
        """
        for i in range(self.horizontalHeader().count()):
            self.resizeColumnToContents(i)

    def endUpdate(self) -> None:
        """
        Finalizes the update and signals if the vertex count is performance-heavy.
        """
        super(TableView, self).endUpdate()
        overLimit = len(self._editorInstance.vertIndexes) > self.tableModel.maxDisplayCount
        self.updateEnded.emit(overLimit)


class TableModel(abstract_weights_view.AbstractModel):
    """
    Data model for a two-dimensional grid of skin weights.

    Coordinates the display of vertex indices (rows) against influences (columns),
    handling real-time data retrieval and multi-cell weight distribution.
    """

    def __init__(self, editorInstance: 'WeightsEditor', parent: QtWidgets.QWidget = None):
        """
        Initializes the model.

        Args:
            editorInstance (WeightsEditor): The central controller for skin data.
            parent (QWidget, optional): Parent widget for the model.
        """
        super(TableModel, self).__init__(editorInstance, parent)
        self.maxDisplayCount = 5000
        self.lockIcon = utils.loadPixmap("inf_view/lock.png", height=24)
        self.jointIcon = utils.loadPixmap("inf_view/joint.png", height=24)
        self._validDataRoles = (QtCore.Qt.ForegroundRole, QtCore.Qt.DisplayRole, QtCore.Qt.EditRole, QtCore.Qt.BackgroundRole, QtCore.Qt.DecorationRole)

    def rowCount(self, parent: QtCore.QModelIndex) -> int:
        """
        Returns the number of rows, capped by maxDisplayCount to maintain UI performance.
        """
        return min(len(self._editorInstance.vertIndexes), self.maxDisplayCount)
    
    def columnCount(self, parent: QtCore.QModelIndex) -> int:
        """
        Returns the number of columns based on the current influence list.
        """
        if self._editorInstance.vertIndexes:
            return len(self.displayInfs)
        else:
            return 0

    def data(self, index: QtCore.QModelIndex, role: QtCore.Qt.ItemDataRole) -> Any:
        """
        Provides the weight value, text color, or background color for a specific cell.

        Returns:
            The formatted weight string or visual attribute for the requested role.
        """
        if not index.isValid():
            return

        if role in self._validDataRoles:
            inf = self.getInf(index.column())
            value = self._getValueByIndex(index)
            
            if role == QtCore.Qt.ForegroundRole:
                textColor = self._getWeightTextColor(inf, value)
                return textColor
            elif role == QtCore.Qt.BackgroundRole:
                infIndex = self._editorInstance.obj.infs.index(inf)
                isLocked = self._editorInstance.locks[infIndex]
                if isLocked:
                    return self._lockedBackgroundColor
            elif role == QtCore.Qt.DecorationRole:
                return self._spacerIcon
            else:
                if value != 0 and value < 0.001:
                    return "< 0.001"
                return f"{value:.3f}"
    
    def setData(self, index: QtCore.QModelIndex, value: Any, role: QtCore.Qt.ItemDataRole) -> bool:
        """
        Validates user input and updates the skin cluster data for the specific vertex.

        Args:
            index (QModelIndex): The cell being edited.
            value (Any): The new weight value input.
            role (ItemDataRole): Must be EditRole.

        Returns:
            True if the weight was successfully updated in the internal data structure.
        """
        if not index.isValid():
            return False
        
        if role != QtCore.Qt.EditRole:
            return False
        
        # Triggers if first cell wasn't valid
        if value is None and self.inputValue is None:
            return False

        if self.inputValue is None:
            if not value.replace(".", "").isdigit():
                return False
            
            value = float(value)
            
            if not (value >= 0 and value <= 1):
                return False

            # Skip if the values are the same.
            # Necessary since left-clicking out of cell won't cancel.
            oldValue = self._getValueByIndex(index)
            oldValueString = f"{oldValue:.3f}"
            value_str = f"{value:.3f}"
            if value_str == oldValueString:
                return False

            self.inputValue = value
        else:
            value = self.inputValue

        # Distribute the weights.
        inf = self.getInf(index.column())
        vertIndex = self.getVertIndex(index.row())
        self._editorInstance.obj.skinData.updateWeightValue(vertIndex, inf, value)
        return True
    
    def headerData(self, column: int, orientation: QtCore.Qt.Orientation, role: QtCore.Qt.ItemDataRole) -> Any:
        """
        Handles labels and styling for both Horizontal (Influences) and Vertical (Vertex IDs) headers.

        Returns:
            The joint name/icon or the vertex index string (e.g., 'vtx[124]').
        """
        if role == QtCore.Qt.ForegroundRole:
            # Color locks
            if orientation == QtCore.Qt.Horizontal:
                infName = self.displayInfs[column]
                
                if infName in self._editorInstance.obj.infs:
                    infIndex = self._editorInstance.obj.infs.index(infName)
                    
                    isLocked = self._editorInstance.locks[infIndex]
                    if isLocked:
                        return self._headerLockedTextColor
        elif role == QtCore.Qt.BackgroundColorRole:
            # Color background
            if orientation == QtCore.Qt.Horizontal:
                # Use softimage colors
                if self.headerColors:
                    color = self.headerColors[column]
                    if color is not None:
                        return color
                else:
                    # Color selected inf
                    if self._editorInstance.colorInfluence is not None:
                        if self._editorInstance.colorInfluence == self.getInf(column):
                            return self._headerActiveInfBackgroundColor
        elif role == QtCore.Qt.DisplayRole:
            if orientation == QtCore.Qt.Horizontal:
                # Show top labels
                if self.displayInfs and column < len(self.displayInfs):
                    inf = self.displayInfs[column]
                    if self.displayShortNames:
                        inf = inf.split("|")[-1].split(":")[-1]
                    return inf
            else:
                # Show side labels
                if self._editorInstance.vertIndexes and column < len(self._editorInstance.vertIndexes):
                    return f"vtx[{self._editorInstance.vertIndexes[column]}]"
        elif role == QtCore.Qt.ToolTipRole:
            if orientation == QtCore.Qt.Horizontal:
                if self.displayInfs and column < len(self.displayInfs):
                    return self.displayInfs[column]
        elif role == QtCore.Qt.DecorationRole:
            if orientation == QtCore.Qt.Horizontal:
                infName = self.displayInfs[column]
                icon = self.jointIcon

                if infName in self._editorInstance.obj.infs:
                    # Show locked influence icons.
                    infIndex = self._editorInstance.obj.infs.index(infName)
                    if self._editorInstance.locks[infIndex]:
                        icon = self.lockIcon

                return icon

    def _getValueByIndex(self, index: QtCore.QModelIndex) -> float:
        """
        Helper to retrieve a weight value from skinData using row/column coordinates.

        Args:
            index (QModelIndex): The cell index.

        Returns:
            The raw float weight value.
        """
        inf = self.getInf(index.column())
        vertIndex = self.getVertIndex(index.row())
        return self._editorInstance.obj.skinData[vertIndex]["weights"].get(inf) or 0

    def getVertIndex(self, row: int) -> int:
        """
        Maps a table row index to the actual Maya vertex index.

        Args:
            row (int): The table row.

        Returns:
            The corresponding Maya vertex index.
        """
        return self._editorInstance.vertIndexes[row]
