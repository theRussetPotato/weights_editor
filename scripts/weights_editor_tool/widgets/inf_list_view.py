import fnmatch
from functools import partial

from maya import cmds
from maya import OpenMaya

from PySide2 import QtGui
from PySide2 import QtCore
from PySide2 import QtWidgets

from weights_editor_tool import weights_editor_utils as utils


class InfListView(QtWidgets.QListView):
    
    middle_clicked = QtCore.Signal(str)
    toggle_locks_triggered = QtCore.Signal(list)
    set_locks_triggered = QtCore.Signal(list, bool)
    select_inf_verts_triggered = QtCore.Signal()
    add_infs_to_verts_triggered = QtCore.Signal()
    
    def __init__(self, editor_inst, parent=None):
        QtWidgets.QListView.__init__(self, parent=parent)
        
        self.block_selection_event = False
        self.last_filter = ""

        self.list_model = InfListModel(editor_inst, parent=self)
        self.setModel(self.list_model)

        self.setAlternatingRowColors(True)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)

        self.doubleClicked.connect(self.on_double_clicked)

        self.display_inf_action = QtWidgets.QAction(self)
        self.display_inf_action.setText("Display influence (middle-click)")
        self.display_inf_action.triggered.connect(self.display_current_inf)

        self.select_infs_action = QtWidgets.QAction(self)
        self.select_infs_action.setText("Select influences (double-click)")
        self.select_infs_action.triggered.connect(self.select_current_infs)

        self.select_inf_verts_action = QtWidgets.QAction(self)
        self.select_inf_verts_action.setText("Select influence's vertexes")
        self.select_inf_verts_action.triggered.connect(self.select_inf_verts_triggered.emit)

        self.lock_infs_action = QtWidgets.QAction(self)
        self.lock_infs_action.setText("Lock influences (space)")
        self.lock_infs_action.triggered.connect(partial(self.set_inf_locks_on_triggered, True))

        self.unlock_infs_action = QtWidgets.QAction(self)
        self.unlock_infs_action.setText("Unlock influences (space)")
        self.unlock_infs_action.triggered.connect(partial(self.set_inf_locks_on_triggered, False))

        self.add_infs_to_verts_action = QtWidgets.QAction(self)
        self.add_infs_to_verts_action.setText("Add influences to vertexes")
        self.add_infs_to_verts_action.triggered.connect(self.add_infs_to_verts_triggered.emit)

        self.header_context_menu = QtWidgets.QMenu(parent=self)
        self.header_context_menu.addAction(self.display_inf_action)
        self.header_context_menu.addSeparator()
        self.header_context_menu.addAction(self.select_infs_action)
        self.header_context_menu.addAction(self.select_inf_verts_action)
        self.header_context_menu.addSeparator()
        self.header_context_menu.addAction(self.lock_infs_action)
        self.header_context_menu.addAction(self.unlock_infs_action)
        self.header_context_menu.addSeparator()
        self.header_context_menu.addAction(self.add_infs_to_verts_action)

        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.on_context_requested)

    def mousePressEvent(self, event):
        QtWidgets.QListView.mousePressEvent(self, event)
        if event.button() == QtCore.Qt.MiddleButton:
            self.display_current_inf()
    
    def keyPressEvent(self, event):
        QtWidgets.QListView.keyPressEvent(self, event)

        if event.key() == QtCore.Qt.Key_Space:
            infs = [
                self.get_internal_name(index.row())
                for index in self.selectedIndexes()
            ]

            if infs:
                self.toggle_locks_triggered.emit(infs)

    def on_double_clicked(self, *args):
        self.select_current_infs()

    def on_context_requested(self, point):
        self.header_context_menu.exec_(self.mapToGlobal(point))

    def set_inf_locks_on_triggered(self, lock):
        infs = [
            self.get_internal_name(index.row())
            for index in self.selectedIndexes()
        ]

        if infs:
            self.set_locks_triggered.emit(infs, lock)

    def begin_update(self):
        self.list_model.layoutAboutToBeChanged.emit()

    def end_update(self):
        self.list_model.layoutChanged.emit()

    def select_current_infs(self):
        objs = []
        indexes = self.selectedIndexes()

        for index in indexes:
            obj_name = self.get_internal_name(index.row())
            if not cmds.objExists(obj_name):
                OpenMaya.MGlobal.displayWarning("Unable to find '{0}' in the scene".format(obj_name))
                continue
            objs.append(obj_name)

        if objs:
            cmds.select(objs)

    def display_current_inf(self):
        index = self.currentIndex()
        if index.isValid():
            inf = self.get_internal_name(index.row())
            self.middle_clicked.emit(inf)

    def find_item(self, name):
        results = self.model().findItems(name)
        if results:
            return results[0]

    def select_item(self, name):
        item = self.find_item(name)
        if item:
            model = self.model()
            sel_model = self.selectionModel()
            index = model.indexFromItem(item)
            sel_model.select(index, sel_model.SelectCurrent)

    def get_internal_name(self, row):
        return self.list_model.item(row).text()

    def get_displayed_name(self, row):
        name = self.get_internal_name(row)
        if self.list_model.hide_long_names:
            name = name.split("|")[-1]
        return name

    def get_displayed_items(self):
        return [
            self.get_displayed_name(i)
            for i in range(self.list_model.rowCount())
        ]

    def apply_filter(self, pattern):
        self.last_filter = pattern

        if pattern:
            all_infs = self.get_displayed_items()
            filter_infs = fnmatch.filter(all_infs, pattern)

            for i in range(len(all_infs)):
                in_filter = all_infs[i] in filter_infs
                self.setRowHidden(i, not in_filter)
        else:
            for i in range(self.list_model.rowCount()):
                self.setRowHidden(i, False)

    def toggle_long_names(self, hidden):
        self.begin_update()
        try:
            self.list_model.hide_long_names = hidden
        finally:
            self.end_update()
            self.apply_filter(self.last_filter)


class InfListModel(QtGui.QStandardItemModel):
    
    def __init__(self, editor_inst, parent=None):
        QtGui.QStandardItemModel.__init__(self, parent=parent)
        
        self.editor_inst = editor_inst
        self.hide_long_names = True

        self.lock_icon = utils.load_pixmap("inf_view/lock.png", height=24)
        self.joint_icon = utils.load_pixmap("inf_view/joint.png", height=24)

        self.size_hint = QtCore.QSize(1, 30)

        self.text_color = QtGui.QColor(QtCore.Qt.white)
        self.locked_text_color = QtGui.QColor(130, 130, 130)
        self.active_inf_back_color = QtGui.QColor(0, 120, 180)
        self.active_inf_text_color = QtGui.QColor(QtCore.Qt.black)
    
    def data(self, index, role):
        QtGui.QStandardItemModel.data(self, index, role)
        
        if not index.isValid():
            return

        item = self.itemFromIndex(index)
        inf_name = item.text()
        
        if role == QtCore.Qt.DisplayRole:
            # Show influence's name.
            if self.hide_long_names:
                return inf_name.split("|")[-1]
            return inf_name
        elif role == QtCore.Qt.BackgroundColorRole:
            # Show color influence.
            if inf_name == self.editor_inst.color_inf:
                return self.active_inf_back_color
        elif role == QtCore.Qt.ForegroundRole:
            # Show locked influences.
            if inf_name in self.editor_inst.infs:
                inf_index = self.editor_inst.infs.index(inf_name)
                if self.editor_inst.locks[inf_index]:
                    if inf_name == self.editor_inst.color_inf:
                        return self.active_inf_text_color
                    else:
                        return self.locked_text_color
            return self.text_color
        elif role == QtCore.Qt.SizeHintRole:
            return self.size_hint
        elif role == QtCore.Qt.DecorationRole:
            icon = self.joint_icon

            if inf_name in self.editor_inst.infs:
                # Show locked influence icons.
                inf_index = self.editor_inst.infs.index(inf_name)
                if self.editor_inst.locks[inf_index]:
                    icon = self.lock_icon

            return icon
        elif role == QtCore.Qt.ToolTipRole:
            return inf_name
