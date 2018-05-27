import os

from ..resources import variables

if variables.qt_version > 4:
    from PySide2 import QtGui
    from PySide2 import QtCore
    from PySide2 import QtWidgets
else:
    from PySide import QtGui
    from PySide import QtCore
    QtWidgets = QtGui


class InfListView(QtWidgets.QListView):
    
    middle_clicked = QtCore.Signal(QtCore.QModelIndex)
    key_pressed = QtCore.Signal(QtGui.QKeyEvent)
    
    def __init__(self, parent=None):
        QtWidgets.QListView.__init__(self, parent=parent)
        
        self.block_selection_event = False
    
    def mousePressEvent(self, event):
        QtWidgets.QListView.mousePressEvent(self, event)
        
        if event.button() == QtCore.Qt.MiddleButton:
            index = self.currentIndex()
            if not index.isValid():
                return
            
            self.middle_clicked.emit(index)
    
    def keyPressEvent(self, event):
        QtWidgets.QListView.keyPressEvent(self, event)
        
        self.key_pressed.emit(event)


class InfListModel(QtGui.QStandardItemModel):
    
    def __init__(self, parent=None):
        QtGui.QStandardItemModel.__init__(self, parent=parent)
        
        self.parent_widget = parent
        
        resources_dir =  os.path.abspath(os.path.join(__file__, "..", "..", "resources", "images"))
        self.lock_icon = QtGui.QIcon(os.path.join(resources_dir, "inf_lock.png"))
    
    def data(self, index, role):
        QtGui.QStandardItemModel.data(self, index, role)
        
        if not index.isValid():
            return
        
        main_window = self.parent_widget.parent().parent().parent()
        
        item = self.itemFromIndex(index)
        inf_name = item.text()
        
        if role ==  QtCore.Qt.DisplayRole:
            # Show influence's name.
            return inf_name
        elif role == QtCore.Qt.BackgroundColorRole:
            # Show color influence.
            if inf_name == main_window.color_inf:
                return QtGui.QColor(0, 120, 180)
        elif role == QtCore.Qt.ForegroundRole:
            # Show locked influences.
            if inf_name in main_window.infs:
                inf_index = main_window.infs.index(inf_name)
                
                if main_window.locks[inf_index]:
                    if inf_name == main_window.color_inf:
                        return QtGui.QColor(QtCore.Qt.black)
                    else:
                        return QtGui.QColor(130, 130, 130)
            
            return QtGui.QColor(QtCore.Qt.white)
        elif role == QtCore.Qt.SizeHintRole:
            return QtCore.QSize(1, 35)
        elif role == QtCore.Qt.DecorationRole:
            # Show locked influence icons.
            if inf_name in main_window.infs:
                inf_index = main_window.infs.index(inf_name)
                
                if main_window.locks[inf_index]:
                    return self.lock_icon