import fnmatch
from functools import partial
from typing import Optional, Any

from maya import cmds
from maya import OpenMaya

from weights_editor_tool.qt import QtCore, QtGui, QtWidgets
from weights_editor_tool import qt
from weights_editor_tool.classes.skinned_obj import SkinnedObj
from weights_editor_tool import weights_editor_utils as utils


class InfItem(QtGui.QStandardItem):
    """
    A specialized list item representing a single Maya influence.

    This class stores the full DAG path of the influence while managing a 'Short Name' for cleaner UI display.
    It also enforces a consistent height for the list rows to ensure better readability in the sidebar.

    Args:
        influence (str): The full DAG path or name of the influence node.
    """

    def __init__(self, influence: str) -> None:
        """
        Initializes the item, parses the short name, and sets the default tooltip and row height.
        """
        super().__init__(influence)

        self.influence = influence
        self.influenceShortName = influence.split("|")[-1].split(":")[-1]

        self.setToolTip(influence)
        self.setSizeHint(QtCore.QSize(1, 30))

    def showShortName(self) -> None:
        """
        Switches the item's display text to the leaf name (e.g., 'L_Arm_Jnt').
        Useful for saving horizontal space in the UI.
        """
        self.setText(self.influenceShortName)

    def showFullName(self) -> None:
        """
        Switches the item's display text back to the full DAG path (e.g., '|Rig|Spine|L_Arm_Jnt').
        Essential for resolving name clashes.
        """
        self.setText(self.influence)

    def node(self) -> str:
        """
        Returns the original full path of the influence.

        Returns:
            The full Maya node name.
        """
        return self.influence


class InfListView(QtWidgets.QListView):
    """
    A specialized list view for displaying and interacting with skin influences.

    This view provides a robust interface for searching, selecting, and locking joints.
    It supports standard Maya interactions like double-clicking to select nodes and middle-clicking to visualize weights in the viewport.

    Signals:
        middleClicked (str): Emitted when an influence is middle-clicked.
        toggleLocksTriggered (list): Emitted to toggle the lock state of joints.
        setLocksTriggered (list, bool): Emitted to explicitly set lock states.
        selectInfVertsTriggered (): Request to select affected vertices.
        selectInfBordersTriggered (): Request to select affected border vertices.
        addInfsToVertsTriggered (): Request to add selected joints to vertex weights.
        infsUpdated (): Signal emitted after the list has been refreshed.
    """

    middleClicked = QtCore.Signal(str)
    toggleLocksTriggered = QtCore.Signal(list)
    setLocksTriggered = QtCore.Signal(list, bool)
    selectInfVertsTriggered = QtCore.Signal()
    selectInfBordersTriggered = QtCore.Signal()
    addInfsToVertsTriggered = QtCore.Signal()
    infsUpdated = QtCore.Signal()
    
    def __init__(self, editorInstance: 'WeightsEditor', parent: QtWidgets.QWidget = None) -> None:
        """
        Initializes the list view, sets up the internal model, and creates the extensive right-click context menu.
        """
        QtWidgets.QListView.__init__(self, parent=parent)

        self._filterPattern = ""

        self.listModel = InfListModel(editorInstance, parent=self)
        self.setModel(self.listModel)

        self.setAlternatingRowColors(True)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)

        self.doubleClicked.connect(self._onDoubleClicked)

        self._displayInfAction = qt.QAction(self)
        self._displayInfAction.setText("Display influence (middle-click)")
        self._displayInfAction.triggered.connect(self._onDisplayInfTriggered)

        self._selectInfsAction = qt.QAction(self)
        self._selectInfsAction.setText("Select Influence (double-click)")
        self._selectInfsAction.triggered.connect(self.selectCurrentInfs)

        self._selectInfVertsAction = qt.QAction(self)
        self._selectInfVertsAction.setText("Select influence's vertexes")
        self._selectInfVertsAction.triggered.connect(self.selectInfVertsTriggered.emit)

        self._selectInfBordersAction = qt.QAction(self)
        self._selectInfBordersAction.setText("Select influence's borders")
        self._selectInfBordersAction.triggered.connect(self.selectInfBordersTriggered.emit)

        self._lockInfsAction = qt.QAction(self)
        self._lockInfsAction.setText("Lock influences (space)")
        self._lockInfsAction.triggered.connect(partial(self._onLockInfsTriggered, True))

        self._unlockInfsAction = qt.QAction(self)
        self._unlockInfsAction.setText("Unlock influences (space)")
        self._unlockInfsAction.triggered.connect(partial(self._onLockInfsTriggered, False))

        self._addInfsToVertsAction = qt.QAction(self)
        self._addInfsToVertsAction.setText("Add influences to vertexes")
        self._addInfsToVertsAction.triggered.connect(self.addInfsToVertsTriggered.emit)

        self._headerContextMenu = QtWidgets.QMenu(parent=self)
        self._headerContextMenu.addAction(self._displayInfAction)
        self._headerContextMenu.addSeparator()
        self._headerContextMenu.addAction(self._selectInfsAction)
        self._headerContextMenu.addAction(self._selectInfVertsAction)
        self._headerContextMenu.addAction(self._selectInfBordersAction)
        self._headerContextMenu.addSeparator()
        self._headerContextMenu.addAction(self._lockInfsAction)
        self._headerContextMenu.addAction(self._unlockInfsAction)
        self._headerContextMenu.addSeparator()
        self._headerContextMenu.addAction(self._addInfsToVertsAction)

        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._onContextRequested)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        """
        Overrides mouse press to capture middle-clicks for instant viewport weight display.
        """
        if event.button() == QtCore.Qt.MiddleButton:
            index = self.indexAt(event.pos())
            if not index.isValid():
                return
            self._displayCurrentInf(index)
        else:
            QtWidgets.QListView.mousePressEvent(self, event)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        """
        Lets the user scroll to to active influence when pressing 'F'.
        """
        if qt.QT_VERSION == 2:
            keyCombo = event.key() | event.modifiers()
        else:
            key = QtCore.Qt.Key(event.key())
            keyCombo = QtCore.QKeyCombination(event.modifiers(), key)

        if keyCombo == QtCore.Qt.Key_F:
            self._scrollToColorInf()
        else:
            QtWidgets.QListView.keyPressEvent(self, event)

    def setDisplayShortNames(self, enabled: bool) -> None:
        """
        Toggles the display mode of all items in the list between full DAG paths and leaf names.

        Args:
            enabled (bool): If True, shows short names (e.g., 'arm_jnt').
                            If False, shows full paths (e.g., '|char|arm_jnt').
        """
        self.beginUpdate()
        self.listModel.displayShortNames = enabled
        self.endUpdate()

    def toggleLocks(self) -> None:
        """
        Gathers all currently selected influences in the list and emits a signal to invert their lock status.
        """
        infs = [
            self._getInternalName(index.row())
            for index in self.selectedIndexes()
        ]

        if infs:
            self.toggleLocksTriggered.emit(infs)

    def _scrollToColorInf(self) -> None:
        """Scrolls to the current active influence being colored."""
        colorInf = self.listModel.getColorInf()
        if colorInf:
            self.scrollToItem(colorInf)

    def _displayCurrentInf(self, index: QtCore.QModelIndex = None) -> None:
        """
        Retrieves the influence name for the given index (or the current selection)
        and emits the middleClicked signal to trigger viewport visualization.

        Args:
            index (QModelIndex, optional): The index to display. Defaults to current.
        """
        if index is None:
            index = self.currentIndex()

        if index.isValid():
            model = self.model()
            selectionModel = self.selectionModel()
            selectionModel.select(index, selectionModel.SelectionFlag.SelectCurrent)

            inf = self._getInternalName(index.row())
            self.middleClicked.emit(inf)

    def _findItem(self, name: str) -> Optional[InfItem]:
        """
        Searches the model for an InfItem matching the given name string.

        Returns:
            The found item, or None if no match exists.
        """
        results = self.model().findItems(name)
        if results:
            return results[0]

    def _getInternalName(self, row: int) -> str:
        """
        Retrieves the full Maya node path for the influence at a specific row.

        Args:
            row (int): The row index in the list.

        Returns:
            The full DAG path.
        """
        return self.listModel.item(row).node()

    def _getDisplayName(self, row: int) -> str:
        """
        Returns the string currently being shown to the user (Short or Full).

        Args:
            row (int): The row index in the list.

        Returns:
            The displayed name.
        """
        item = self.listModel.item(row)
        if self.listModel.displayShortNames:
            return item.influenceShortName
        else:
            return item.influence

    def _onDoubleClicked(self, *args) -> None:
        """Slot for the double-click event. Triggers Maya node selection."""
        self.selectCurrentInfs()

    def _onContextRequested(self, point: QtCore.QPoint) -> None:
        """Slot that maps the local mouse point to a global coordinate for the context menu."""
        self._headerContextMenu.exec_(self.mapToGlobal(point))

    def _onDisplayInfTriggered(self, *args) -> None:
        """
        Slot that helps display the current influence.
        """
        self._displayCurrentInf()

    def _onLockInfsTriggered(self, lock: bool) -> None:
        """
        Collects all selected influences and emits a signal to set their lock status to the specified 'lock' boolean.

        Args:
            lock (bool): True to lock, False to unlock.
        """
        infs = [
            self._getInternalName(index.row())
            for index in self.selectedIndexes()
        ]

        if infs:
            self.setLocksTriggered.emit(infs, lock)

    def beginUpdate(self) -> None:
        """Suspends layout updates for batch model changes."""
        self.listModel.layoutAboutToBeChanged.emit()

    def endUpdate(self) -> None:
        """Resumes layout updates and refreshes the view."""
        self.listModel.layoutChanged.emit()

    def selectCurrentInfs(self) -> None:
        """
        Selects the actual Maya nodes corresponding to the current selection in the list view.
        """
        objs = []
        indexes = self.selectedIndexes()

        for index in indexes:
            objName = self._getInternalName(index.row())
            if not cmds.objExists(objName):
                OpenMaya.MGlobal.displayWarning(f"Unable to find '{objName}' in the scene")
                continue
            objs.append(objName)

        if objs:
            cmds.select(objs)

    def scrollToItem(self, itemName: str) -> None:
        """
        Tries to scroll to an item that matches the supplied name.

        Args:
            itemName (str): The name of the item to scroll to.
        """
        item = self._findItem(itemName)
        if not item:
            return

        model = self.model()
        selectionModel = self.selectionModel()
        index = model.indexFromItem(item)
        self.scrollTo(index, QtWidgets.QAbstractItemView.PositionAtCenter)

    def selectItem(self, name: str) -> None:
        """
        Force-selects an item in the UI based on its name.
        Useful for syncing the list with external scene selections.

        Args:
            name (str): The influence name to find and select.
        """
        item = self._findItem(name)
        if item:
            model = self.model()
            selectionModel = self.selectionModel()
            index = model.indexFromItem(item)
            selectionModel.select(index, selectionModel.SelectionFlag.SelectCurrent)

    def getDisplayedItems(self) -> list[str]:
        """
        Returns a list of all strings currently visible in the list view rows.

        Returns:
            Displayed influence names.
        """
        return [
            self._getDisplayName(i)
            for i in range(self.listModel.rowCount())
        ]

    def applyFilter(self, pattern: str) -> None:
        """
        Filters the visible influences using glob-style pattern matching.

        This uses the `fnmatch` module, allowing users to search using wildcards like '*' or '?'.
        Rows that do not match the pattern are hidden from view.

        Args:
            pattern (str): The search string (e.g., "L_Leg_*").
        """
        self._filterPattern = pattern

        if pattern:
            allInfs = self.getDisplayedItems()
            filterInfs = fnmatch.filter(allInfs, pattern)

            for i in range(len(allInfs)):
                isInFilter = allInfs[i] in filterInfs
                self.setRowHidden(i, not isInFilter)
        else:
            for i in range(self.listModel.rowCount()):
                self.setRowHidden(i, False)

    def updateInfs(self, skinnedObj: SkinnedObj, showAll: bool) -> None:
        """
        Rebuilds the entire influence list based on the provided SkinnedObj.
        The list is automatically sorted alphabetically and the current filter is re-applied after the update.

        Args:
            skinnedObj (SkinnedObj): The data source for the influences.
        """
        self.beginUpdate()
        try:
            self.listModel.clear()
            self.listModel.infs = skinnedObj.infs[:]

            if showAll:
                joints = sorted(cmds.ls(type="joint"))
            else:
                joints = self.listModel.infs

            for i, inf in enumerate(joints):
                item = InfItem(inf)
                self.listModel.appendRow(item)

            self.applyFilter(self._filterPattern)
        finally:
            self.endUpdate()
            self.infsUpdated.emit()


class InfListModel(QtGui.QStandardItemModel):
    """
    A specialized model that manages the visual state of skin influences.

    This class handles conditional formatting, such as swapping icons when
    an influence is locked and highlighting the currently visualized influence.
    """

    def __init__(self, editorInstance: 'WeightsEditor', parent: QtWidgets.QWidget = None) -> None:
        """
        Initializes the model with specific color palettes and icons.
        """
        QtGui.QStandardItemModel.__init__(self, parent=parent)
        
        self._editorInstance = editorInstance
        self.displayShortNames = False
        self.infs = []

        self._lockIcon = utils.loadPixmap("inf_view/lock.png", height=24)
        self._jointIcon = utils.loadPixmap("inf_view/joint.png", height=24)
        self._sizeHint = QtCore.QSize(1, 26)
        self._textColor = QtGui.QColor(QtCore.Qt.white)
        self._lockedTextColor = QtGui.QColor(140, 140, 140)
        self._lockedBackgroundColor = QtGui.QColor(70, 70, 70)
        self._activeInfBackgroundColor = QtGui.QColor(60, 170, 60)
        self._activeInfTextColor = QtGui.QColor(QtCore.Qt.black)

    def getColorInf(self) -> str:
        """Returns the current active influence being colored."""
        return self._editorInstance.colorInfluence

    def data(self, index: QtCore.QModelIndex, role: QtCore.Qt.ItemDataRole) -> Any:
        """
        Provides formatting data for the View based on the requested role.

        Args:
            index (QModelIndex): The specific row/item being painted.
            role (ItemDataRole): The type of data requested (Color, Text, Icon, etc.).

        Returns:
            The specific visual attribute (QColor, QPixmap, str) for that role.
        """
        QtGui.QStandardItemModel.data(self, index, role)
        
        if not index.isValid():
            return

        item = self.itemFromIndex(index)
        infName = item.node()
        colorInf = self.getColorInf()

        if role == QtCore.Qt.DisplayRole:
            # Show influence's name.
            if self.displayShortNames:
                return item.influenceShortName
            else:
                return item.influence
        elif role == QtCore.Qt.BackgroundColorRole:
            # Show color influence.
            if infName == colorInf:
                return self._activeInfBackgroundColor
            else:
                if infName in self._editorInstance.obj.infs:
                    infIndex = self._editorInstance.obj.infs.index(infName)
                    if self._editorInstance.locks[infIndex]:
                        return self._lockedBackgroundColor
                else:
                    return QtGui.QColor(55, 40, 40)
        elif role == QtCore.Qt.ForegroundRole:
            # Show locked influences.
            if infName in self._editorInstance.obj.infs:
                infIndex = self._editorInstance.obj.infs.index(infName)
                if self._editorInstance.locks[infIndex]:
                    if infName == colorInf:
                        return self._activeInfTextColor
                    else:
                        return self._lockedTextColor
                return self._textColor
            else:
                return QtGui.QColor(255, 200, 200)
        elif role == QtCore.Qt.SizeHintRole:
            return self._sizeHint
        elif role == QtCore.Qt.DecorationRole:
            icon = self._jointIcon

            if infName in self._editorInstance.obj.infs:
                # Show locked influence icons.
                infIndex = self._editorInstance.obj.infs.index(infName)
                if self._editorInstance.locks[infIndex]:
                    icon = self._lockIcon

            return icon
        elif role == QtCore.Qt.ToolTipRole:
            return infName
