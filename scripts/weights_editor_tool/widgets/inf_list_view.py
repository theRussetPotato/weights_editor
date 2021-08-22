import os
import fnmatch

import maya.cmds as cmds
import maya.OpenMaya as OpenMaya

from PySide2 import QtGui
from PySide2 import QtCore
from PySide2 import QtWidgets


class InfListView(QtWidgets.QListView):
    
    middle_clicked = QtCore.Signal(str)
    toggle_lock_triggered = QtCore.Signal(list)
    
    def __init__(self, editor_inst, parent=None):
        QtWidgets.QListView.__init__(self, parent=parent)
        
        self.block_selection_event = False

        self.list_model = InfListModel(editor_inst, parent=self)
        self.setModel(self.list_model)

        self.setAlternatingRowColors(True)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)

        self.doubleClicked.connect(self.on_double_clicked)
    
    def mousePressEvent(self, event):
        QtWidgets.QListView.mousePressEvent(self, event)
        
        if event.button() == QtCore.Qt.MiddleButton:
            index = self.currentIndex()
            if not index.isValid():
                return

            inf = self.list_model.itemFromIndex(index)
            self.middle_clicked.emit(inf.text())
    
    def keyPressEvent(self, event):
        QtWidgets.QListView.keyPressEvent(self, event)

        if event.key() == QtCore.Qt.Key_Space:
            indexes = self.selectedIndexes()
            if not indexes:
                return

            infs = [
                self.list_model.itemFromIndex(index).text()
                for index in indexes]

            self.toggle_lock_triggered.emit(infs)

    def on_double_clicked(self, index):
        if not index.isValid():
            return

        item = self.list_model.itemFromIndex(index)

        obj_name = item.text()
        if not cmds.objExists(obj_name):
            OpenMaya.MGlobal.displayError(
                "Unable to find '{0}' in the scene".format(obj_name))
            return

        cmds.select(obj_name)

    def begin_update(self):
        self.list_model.layoutAboutToBeChanged.emit()

    def end_update(self):
        self.list_model.layoutChanged.emit()

    def find_item(self, name):
        results = self.model().findItems(name)
        if results:
            return results[0]

    def select_item(self, name):
        item = self.find_item(name)
        if not item:
            return

        model = self.model()
        sel_model = self.selectionModel()
        index = model.indexFromItem(item)
        sel_model.select(index, sel_model.SelectCurrent)

    def apply_filter(self, pattern):
        if pattern:
            all_infs = [
                self.list_model.item(i).text()
                for i in range(self.list_model.rowCount())
            ]

            filter_infs = fnmatch.filter(all_infs, pattern)

            for i in range(self.list_model.rowCount()):
                in_filter = self.list_model.item(i).text() in filter_infs
                self.setRowHidden(i, not in_filter)
        else:
            for i in range(self.list_model.rowCount()):
                self.setRowHidden(i, False)


class InfListModel(QtGui.QStandardItemModel):
    
    def __init__(self, editor_inst, parent=None):
        QtGui.QStandardItemModel.__init__(self, parent=parent)
        
        self.editor_inst = editor_inst
        
        resources_dir =  os.path.abspath(os.path.join(__file__, "..", "..", "resources", "images"))
        self.lock_icon = QtGui.QIcon(os.path.join(resources_dir, "inf_lock.png"))

        self.size_hint = QtCore.QSize(1, 35)

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
        
        if role ==  QtCore.Qt.DisplayRole:
            # Show influence's name.
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
            # Show locked influence icons.
            if inf_name in self.editor_inst.infs:
                inf_index = self.editor_inst.infs.index(inf_name)
                if self.editor_inst.locks[inf_index]:
                    return self.lock_icon
        elif role == QtCore.Qt.ToolTipRole:
            return inf_name
