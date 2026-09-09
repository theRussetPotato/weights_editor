from typing import Any

from weights_editor_tool.qt import QtCore, QtGui, QtWidgets
from weights_editor_tool import qt
from weights_editor_tool import weights_editor_utils as utils
from weights_editor_tool.widgets import abstract_weights_view


class ListView(abstract_weights_view.AbstractWeightsView):
    """
    A table-based view for displaying and editing skin weight values vertically.
    This class manages row-based sorting (by name or weight average) and synchronizes selection between the UI and the Maya vertex indices.
    """

    def __init__(self, editorInstance: 'WeightsEditor') -> None:
        """
        Initializes the view, hides horizontal headers, and sets the ListModel.

        Args:
            editorInstance (WeightsEditor): The main controller instance.
        """
        super(ListView, self).__init__(QtCore.Qt.Vertical, editorInstance)

        self._sortInfByNameAction = qt.QAction(self)
        self._sortInfByNameAction.setText("Sort by inf name")
        self._sortInfByNameAction.triggered.connect(self._onSortInfByNameTriggered)

        self.horizontalHeader().hide()
        self._headerContextMenu.addAction(self._sortInfByNameAction)

        tableModel = ListModel(editorInstance, parent=self)
        self._setModel(tableModel)
        self.horizontalHeader().setStretchLastSection(True)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        """
        Extends the mouse press to display the influence during a middle-click.

        Args:
            event (QMouseEvent): The mouse press event.
        """
        if event.button() == QtCore.Qt.MouseButton.MiddleButton:
            # Set influence at row to be displayed.
            index = self.indexAt(event.pos())
            if index.isValid():
                row = index.row()
                inf = self.tableModel.displayInfs[row]
                self.headerMiddleClicked.emit(inf)
        else:
            super().mousePressEvent(event)

    def closeEditor(self, editor: QtWidgets.QLineEdit, hint: QtWidgets.QAbstractItemDelegate.EndEditHint) -> None:
        """
        Handles the completion of an edit, applying values to all selected cells.
        Triggers the undo command creation if data was modified.

        Args:
            editor (QLineEdit): The widget used for editing.
            hint (EndEditHint): The reason why editing finished.
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
            
            self._editorInstance.addUndoCommand(
                "Set skin weights",
                self._editorInstance.obj.name,
                self._oldSkinData,
                self._editorInstance.obj.skinData.copy(),
                self._editorInstance.vertIndexes,
                self.saveTableSelection())
        
        self._oldSkinData = None

    def _reorderByName(self, order: QtCore.Qt.SortOrder = QtCore.Qt.AscendingOrder) -> None:
        """
        Sorts the displayed influences alphabetically.

        Args:
            order (SortOrder): The direction of the sort.
        """
        self.beginUpdate()
        selectionData = self.saveTableSelection()

        self.tableModel.displayInfs.sort(reverse=order)

        self.endUpdate()
        self.loadTableSelection(selectionData)

    def _reorderByValues(self, order: QtCore.Qt.SortOrder) -> None:
        """
        Sorts influences based on their average weight across selected vertices.

        Args:
            order (SortOrder): The direction of the sort.
        """
        self.beginUpdate()
        selectionData = self.saveTableSelection()

        self.tableModel.displayInfs = sorted(
            self.tableModel.displayInfs,
            key=lambda x: self.tableModel.getAverageWeight(x) or 0.0,
            reverse=order)

        self.endUpdate()
        self.loadTableSelection(selectionData)

    def _onSortByWeightsAscendingTriggered(self) -> None:
        """Triggers a reorder of the list based on weight values in ascending order."""
        self._reorderByValues(QtCore.Qt.DescendingOrder)

    def _onSortByWeightsDescendingTriggered(self) -> None:
        """Triggers a reorder of the list based on weight values in descending order."""
        self._reorderByValues(QtCore.Qt.AscendingOrder)

    def _onSortInfByNameTriggered(self) -> None:
        """Triggers an alphabetical sort of the influences."""
        self._reorderByName()

    def endUpdate(self) -> None:
        """
        Finalizes the UI update and clears the average weight cache.
        This ensures that weight averages are recalculated based on the latest skin data after a structural change or sort.
        """
        self.tableModel.averageWeights = {}
        super(ListView, self).endUpdate()

    def colorHeaders(self) -> None:
        """
        Applies color coding to the vertical headers.

        Args:
            count (int): The number of rows to process for coloring.
        """
        count = self.tableModel.rowCount(self)
        super(ListView, self).colorHeaders(count)

    def selectItemsByInf(self, inf: str) -> None:
        """
        Forces the table selection to a specific influence row.

        Args:
            inf (str): The name of the influence to select.
        """
        if inf and inf in self.tableModel.displayInfs:
            row = self.tableModel.displayInfs.index(inf)
            selectionModel = self.selectionModel()
            index = self.model().createIndex(row, 0)
            flags = QtCore.QItemSelectionModel.ClearAndSelect | QtCore.QItemSelectionModel.Rows
            selectionModel.select(index, flags)
        else:
            self.clearSelection()

    def getSelectedVertsAndInfs(self) -> list[tuple[int, str]]:
        """
        Maps current table row selection back to Maya vertex and influence pairs.

        Returns:
            A list of tuples containing (vertexIndex, influenceName).
        """
        indexes = self._getSelectedIndexes()
        if not indexes:
            return []

        vertsAndInfs = []

        for index in indexes:
            row = index.row()
            if row >= len(self.tableModel.displayInfs):
                continue

            for vertIndex in self._editorInstance.vertIndexes:
                inf = self.tableModel.displayInfs[row]
                vertsAndInfs.append((vertIndex, inf))

        return vertsAndInfs

    def saveTableSelection(self) -> dict[str, list[int]]:
        """
        Captures the current UI selection into a serializable dictionary.

        Returns:
            A dictionary mapping influence names to lists of vertex indices.
        """
        selectionData = {}

        vertsAndInfs = self.getSelectedVertsAndInfs()
        for vertIndex, inf in vertsAndInfs:
            if inf not in selectionData:
                selectionData[inf] = []
            selectionData[inf].append(vertIndex)

        return selectionData

    def loadTableSelection(self, selectionData: dict[str, list[int]]) -> None:
        """
        Restores table selection from a previously saved data set.

        Args:
            selectionData (dict): The data structure containing influences and vertices.
        """
        self.clearSelection()
        if not selectionData:
            return

        selectionModel = self.selectionModel()
        itemSelection = QtCore.QItemSelection()

        for inf, vertIndexes in selectionData.items():
            if inf not in self.tableModel.displayInfs:
                continue

            row = self.tableModel.displayInfs.index(inf)
            index = self.model().index(row, 0)
            itemSelection.append(QtCore.QItemSelectionRange(index, index))

        selectionModel.select(itemSelection, QtCore.QItemSelectionModel.Select)

    def fitHeadersToContents(self) -> None:
        """
        Dynamically resizes the vertical header width based on influence name length.
        """
        width = 0
        infs = self.displayInfs()

        if infs and self._editorInstance.vertIndexes:
            if self.tableModel.displayShortNames:
                infs = [inf.split("|")[-1].split(":")[-1] for inf in infs]

            fontMetrics = self._editorInstance.fontMetrics()
            padding = 25
            iconSize = self.tableModel.jointIcon.width()

            textWidths = []
            for inf in infs:
                if hasattr(fontMetrics, "horizontalAdvance"):
                    textWidth = fontMetrics.horizontalAdvance(inf)
                else:
                    textWidth = fontMetrics.width(inf)  # PySide2 compatible.
                textWidths.append(textWidth)
            width = sorted(textWidths)[-1] + padding + iconSize

        self.verticalHeader().size = QtCore.QSize(width, 0)


class ListModel(abstract_weights_view.AbstractModel):
    """
    Manages the average skin weight data for the vertical list view.

    This model aggregates weight values from multiple vertices to provide a single
    average value per influence, allowing for simplified batch editing.
    """

    def __init__(self, editorInstance: 'WeightsEditor', parent: QtWidgets.QWidget = None) -> None:
        """
        Initializes the model and caches icons and weight averages.

        Args:
            editorInstance (WeightsEditor): The main controller for weight data.
            parent (QWidget, optional): Parent widget.
        """
        super(ListModel, self).__init__(editorInstance, parent)

        self.averageWeights = {}
        self.lockIcon = utils.loadPixmap("inf_view/lock.png", height=24)
        self.jointIcon = utils.loadPixmap("inf_view/joint.png", height=24)
        self._validDataRoles = (QtCore.Qt.ForegroundRole, QtCore.Qt.DisplayRole, QtCore.Qt.EditRole, QtCore.Qt.BackgroundRole, QtCore.Qt.DecorationRole)
    
    def rowCount(self, parent: QtCore.QModelIndex) -> int:
        """
        Returns the number of rows, which corresponds to the number of influences.
        """
        if self._editorInstance.vertIndexes:
            return len(self.displayInfs)
        else:
            return 0
    
    def columnCount(self, parent: QtCore.QModelIndex) -> int:
        """
        Returns 1, as this view displays a single column of average values.
        """
        if self.displayInfs and self._editorInstance.vertIndexes:
            return 1
        else:
            return 0

    def data(self, index: QtCore.QModelIndex, role: QtCore.Qt.ItemDataRole) -> Any:
        """
        Determines how cells look based on weight values and lock states.

        Returns:
            The display string, text color, or background color for a weight cell.
        """
        if not index.isValid():
            return

        if role in self._validDataRoles:
            inf = self.getInf(index.row())
            value = self.getAverageWeight(inf)
            
            if role == QtCore.Qt.ForegroundRole:
                textColor = self._getWeightTextColor(inf, value)
                return textColor
                '''infIndex = self._editorInstance.obj.infs.index(inf)
                isLocked = self._editorInstance.locks[infIndex]
                if isLocked:
                    return self._lockedTextColor

                if value != 0 and value < 0.001:
                    return self._lowWeightsTextColor
                elif value == 0:
                    return self._zeroWeightsTextColor
                elif value >= 0.999:
                    return self._fullWeightsTextColor'''
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
        Captures user input and distributes the new weight to all selected vertices.

        Args:
            index (QModelIndex): The cell being edited.
            value (Any): The string input from the user.
            role (ItemDataRole): Must be EditRole.

        Returns:
            True if the data was valid and successfully applied.
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
            if not value >= 0 and value <= 1:
                return False

            self.inputValue = value
        else:
            value = self.inputValue

        # Distribute the weights.
        inf = self.getInf(index.row())

        for vertIndex in self._editorInstance.vertIndexes:
            self._editorInstance.obj.skinData.updateWeightValue(vertIndex, inf, value)

        return True
    
    def headerData(self, index: int, orientation: QtCore.Qt.Orientation, role: QtCore.Qt.ItemDataRole) -> Any:
        """
        Determines the styling of the vertical headers (joint names and icons).

        Returns:
            The joint name, lock icon, or specialized header coloring.
        """
        if role == QtCore.Qt.ForegroundRole:
            # Color locks
            if orientation == QtCore.Qt.Vertical:
                infName = self.displayInfs[index]
                
                if infName in self._editorInstance.obj.infs:
                    infIndex = self._editorInstance.obj.infs.index(infName)
                    
                    isLocked = self._editorInstance.locks[infIndex]
                    if isLocked:
                        return self._headerLockedTextColor
        elif role == QtCore.Qt.BackgroundColorRole:
            # Color background
            if orientation == QtCore.Qt.Vertical:
                # Use softimage colors
                if self.headerColors:
                    color = self.headerColors[index]
                    if color is not None:
                        return color
                else:
                    # Color selected inf
                    if self._editorInstance.colorInfluence is not None:
                        if self._editorInstance.colorInfluence == self.getInf(index):
                            return self._headerActiveInfBackgroundColor
        elif role == QtCore.Qt.DisplayRole:
            if orientation == QtCore.Qt.Vertical:
                # Show top labels
                if self.displayInfs and index < len(self.displayInfs):
                    inf = self.displayInfs[index]
                    if self.displayShortNames:
                        inf = inf.split("|")[-1].split(":")[-1]
                    return inf
            else:
                return "Average values"
        elif role == QtCore.Qt.ToolTipRole:
            if orientation == QtCore.Qt.Vertical:
                if self.displayInfs and index < len(self.displayInfs):
                    return self.displayInfs[index]
        elif role == QtCore.Qt.DecorationRole:
            if orientation == QtCore.Qt.Vertical:
                infName = self.displayInfs[index]
                icon = self.jointIcon

                if infName in self._editorInstance.obj.infs:
                    # Show locked influence icons.
                    infIndex = self._editorInstance.obj.infs.index(infName)
                    if self._editorInstance.locks[infIndex]:
                        icon = self.lockIcon

                return icon

    # TODO: Should this be elsewhere?
    def getAverageWeight(self, inf: str) -> float:
        """
        Calculates the mean weight of a specific influence across all selected vertices.

        Args:
            inf (str): The influence name to calculate.

        Returns:
            The average weight value.
        """
        if not self._editorInstance.vertIndexes:
            return 0

        if inf not in self.averageWeights:
            values = [
                self._editorInstance.obj.skinData[vertIndex]["weights"].get(inf) or 0
                for vertIndex in self._editorInstance.vertIndexes
            ]

            self.averageWeights[inf] = sum(values) / len(self._editorInstance.vertIndexes)

        return self.averageWeights[inf]
