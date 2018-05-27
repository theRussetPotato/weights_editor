import copy

from ..resources import variables

if variables.qt_version > 4:
    from PySide2 import QtGui
    from PySide2 import QtCore
    from PySide2 import QtWidgets
else:
    from PySide import QtGui
    from PySide import QtCore
    QtWidgets = QtGui

from .. import weights_editor_utils as utils


class TableView(QtWidgets.QTableView):
    
    key_pressed = QtCore.Signal(QtGui.QKeyEvent)
    selection_changed = QtCore.Signal()
    
    def __init__(self, parent=None):
        super(TableView, self).__init__(parent)
        
        self.main_widget = parent
        
        # Need to store this to work with undo/redo.
        self.old_skin_data = None
    
    def paintEvent(self, paint_event):
        """
        Shows tooltip when table is empty.
        """
        if self.model().rowCount(self) == 0:
            if self.main_widget.obj is None:
                msg = ("Select a skinned object and push\n"
                       "the button on top edit its weights.")
            elif self.main_widget.skin_cluster is None:
                msg = "Unable to detect a skinCluster on this object."
            else:
                msg = "Select the object's vertices."
            
            qp = QtGui.QPainter(self.viewport())
            if not qp.isActive():
                qp.begin(self)
            
            qp.setPen(QtGui.QColor(255, 255, 255))
            qp.setFont(QtGui.QFont("", 15))
            qp.drawText(paint_event.rect(), 
                        QtCore.Qt.AlignCenter, 
                        msg)
            qp.end()
        
        QtWidgets.QTableView.paintEvent(self, paint_event)
    
    def selectionChanged(self, selected, deselected):
        QtWidgets.QTableView.selectionChanged(self, selected, deselected)
        self.selection_changed.emit()
    
    def mousePressEvent(self, event):
        """
        Begins edit on current cell.
        """
        QtWidgets.QTableView.mousePressEvent(self, event)
        
        if event.button() == QtCore.Qt.MouseButton.RightButton:
            # Save this prior to any changes.
            self.old_skin_data = copy.deepcopy(self.main_widget.skin_data)
            
            self.edit(self.currentIndex())
    
    def keyPressEvent(self, event):
        """
        Emits when a key is pressed.
        """
        if event.key() in self.main_widget.accept_keys:
            self.key_pressed.emit(event)
        else:
            QtWidgets.QWidget.keyPressEvent(self, event)
    
    def closeEditor(self, editor, hint):
        """
        Enables multiple cells to be set.
        """
        is_cancelled = (hint == QtWidgets.QAbstractItemDelegate.RevertModelCache)
        
        if not is_cancelled:
            for index in self.selectedIndexes():
                if index == self.currentIndex():
                    continue
                
                self.model().setData(index, None, QtCore.Qt.EditRole)
        
        QtWidgets.QTableView.closeEditor(self, editor, hint)
        
        if self.model()._input_value is not None:
            self.model()._input_value = None
            
            vert_indexes = list(set(self.model().get_vert_index(index.row()) 
                                    for index in self.selectedIndexes()))
            
            current_obj = self.main_widget.get_obj_by_name(self.main_widget.obj)
            
            self.main_widget.add_undo_command("Set skin weights", current_obj, self.old_skin_data, copy.deepcopy(self.main_widget.skin_data), vert_indexes, self.main_widget.save_table_selection())
        
        self.old_skin_data = None
    
    def get_selected_indexes(self):
        """
        Gets and returns valid indexes from the table.
        """
        return [index 
                for index in self.selectedIndexes() 
                if index.isValid()]


class TableModel(QtCore.QAbstractTableModel):
    
    def __init__(self, parent=None):
        super(TableModel, self).__init__(parent)
        
        self.main_widget = parent
        
        self.header_colors = []
        
        self._input_value = None # Used to properly set multiple cells
    
    def get_inf(self, column):
        return self.main_widget.display_infs[column]
    
    def get_vert_index(self, row):
        return self.main_widget.vert_indexes[row]
    
    def rowCount(self, parent):
        return len(self.main_widget.vert_indexes)
    
    def columnCount(self, parent):
        return len(self.main_widget.display_infs)
    
    def data(self, index, role):
        if not index.isValid():
            return
        
        if role == QtCore.Qt.ForegroundRole or role == QtCore.Qt.DisplayRole:
            inf = self.get_inf(index.column())
            vert_index = self.get_vert_index(index.row())
            value = self.main_widget.skin_data[vert_index]["weights"].get(inf) or 0
            
            if role == QtCore.Qt.ForegroundRole:
                inf_index = self.main_widget.infs.index(inf)
                is_locked = self.main_widget.locks[inf_index]
                if is_locked:
                    return QtGui.QColor(100, 100, 100)
                if value == 0:
                    return QtGui.QColor(255, 50, 50)
            else:
                if value != 0 and value < 0.001:
                    return "< 0.001"
                return "{0:.3f}".format(value)
        
        return
    
    def setData(self, index, value, role):
        """
        Qt doesn't handle multiple cell edits very well.
        This is the only place we can get the user's input, so first
        we check if it's valid first. If not, all other cells will be ignored.
        """
        if not index.isValid():
            return False
        
        if role != QtCore.Qt.EditRole:
            return False
        
        # Triggers if first cell wasn't valid
        if value is None and self._input_value is None:
            return False
        
        if self._input_value is None:
            if not value.replace(".", "").isdigit():
                return False
            
            value = float(value)
            
            if not (value >= 0 and value <= 1):
                return False
            
            self._input_value = value
        else:
            value = self._input_value
        
        # Distribute the weights.
        inf = self.get_inf(index.column())
        vert_index = self.get_vert_index(index.row())
        utils.update_weight_value(self.main_widget.skin_data[vert_index]["weights"], inf, value)
        
        return True
    
    def headerData(self, column, orientation, role):
        """
        Deterimines the header's labels and style.
        """
        if role == QtCore.Qt.ForegroundRole:
            # Color locks
            if orientation == QtCore.Qt.Horizontal:
                inf_name = self.main_widget.display_infs[column]
                
                if inf_name in self.main_widget.infs:
                    inf_index = self.main_widget.infs.index(inf_name)
                    
                    is_locked = self.main_widget.locks[inf_index]
                    if is_locked:
                        return QtGui.QColor(QtCore.Qt.black)
        elif role == QtCore.Qt.BackgroundColorRole:
            # Color background
            if orientation == QtCore.Qt.Horizontal:
                # Use softimage colors
                if self.header_colors:
                    color = self.header_colors[column]
                    if color is not None:
                        return color
                else:
                    # Color selected inf
                    if self.main_widget.color_inf is not None:
                        if self.main_widget.color_inf == self.get_inf(column):
                            return QtGui.QColor(82, 133, 166)
        elif role == QtCore.Qt.DisplayRole:
            if orientation == QtCore.Qt.Horizontal:
                # Show top labels
                if self.main_widget.display_infs and column < len(self.main_widget.display_infs):
                    return self.main_widget.display_infs[column]
            else:
                # Show side labels
                if self.main_widget.vert_indexes and column < len(self.main_widget.vert_indexes):
                    return self.main_widget.vert_indexes[column]
    
    def flags(self, index):
        return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEditable
    
    def begin_update(self):
        self.emit(QtCore.SIGNAL("layoutAboutToBeChanged()"))
    
    def end_update(self):
        self.emit(QtCore.SIGNAL("layoutChanged()"))