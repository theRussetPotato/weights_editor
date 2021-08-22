import copy

import maya.cmds as cmds

from PySide2 import QtGui
from PySide2 import QtCore
from PySide2 import QtWidgets

from weights_editor_tool.widgets import custom_header_view


class AbstractWeightsView(QtWidgets.QTableView):

    key_pressed = QtCore.Signal(QtGui.QKeyEvent)
    header_middle_clicked = QtCore.Signal(str)
    display_inf_triggered = QtCore.Signal(str)
    select_inf_verts_triggered = QtCore.Signal(str)

    def __init__(self, view_type, header_orientation, editor_inst):
        super(AbstractWeightsView, self).__init__(editor_inst)

        system_font = QtWidgets.QApplication.font()

        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setGridStyle(QtCore.Qt.DashLine)
        self.font = QtGui.QFont(system_font.family(), system_font.pixelSize())
        self.view_type = view_type
        self.editor_inst = editor_inst
        self.table_model = None
        self.old_skin_data = None  # Need to store this to work with undo/redo.

        self.header = custom_header_view.CustomHeaderView(header_orientation, parent=self)
        self.header.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.header.customContextMenuRequested.connect(self.header_on_context_trigger)
        self.header.header_left_clicked.connect(self.header_on_left_clicked)
        self.header.header_middle_clicked.connect(self.header_on_middle_clicked)

        if header_orientation == QtCore.Qt.Horizontal:
            self.setHorizontalHeader(self.header)
        else:
            self.setVerticalHeader(self.header)

        self.display_inf_action = QtWidgets.QAction(self)
        self.display_inf_action.setText("Display influence")
        self.display_inf_action.triggered.connect(self.display_inf_on_triggered)

        self.select_inf_verts_action = QtWidgets.QAction(self)
        self.select_inf_verts_action.setText("Select vertexes effected by influence")
        self.select_inf_verts_action.triggered.connect(self.select_inf_verts_on_triggered)

        self.select_inf_action = QtWidgets.QAction(self)
        self.select_inf_action.setText("Select influence")
        self.select_inf_action.triggered.connect(self.select_inf_on_triggered)

        self.sort_weights_ascending_action = QtWidgets.QAction(self)
        self.sort_weights_ascending_action.setText("Sort by weights (ascending)")
        self.sort_weights_ascending_action.triggered.connect(self.sort_ascending_on_triggered)

        self.sort_weights_descending_action = QtWidgets.QAction(self)
        self.sort_weights_descending_action.setText("Sort by weights (descending)")
        self.sort_weights_descending_action.triggered.connect(self.sort_descending_on_triggered)

        self.header_context_menu = QtWidgets.QMenu(parent=self)
        self.header_context_menu.addAction(self.display_inf_action)
        self.header_context_menu.addSeparator()
        self.header_context_menu.addAction(self.select_inf_verts_action)
        self.header_context_menu.addAction(self.select_inf_action)
        self.header_context_menu.addSeparator()
        self.header_context_menu.addAction(self.sort_weights_ascending_action)
        self.header_context_menu.addAction(self.sort_weights_descending_action)

    def sort_ascending_on_triggered(self):
        raise NotImplementedError

    def sort_descending_on_triggered(self):
        raise NotImplementedError

    def select_items_by_inf(self):
        raise NotImplementedError

    def get_selected_verts_and_infs(self):
        raise NotImplementedError

    def save_table_selection(self):
        raise NotImplementedError

    def load_table_selection(self, selection_data):
        raise NotImplementedError

    def paintEvent(self, paint_event):
        """
        Shows tooltip when table is empty.
        """
        if self.model().rowCount(self) == 0:
            if self.editor_inst.obj is None:
                msg = ("Select a skinned object and push\n"
                       "the button on top edit its weights.")
            elif self.editor_inst.skin_cluster is None:
                msg = "Unable to detect a skinCluster on this object."
            else:
                msg = "Select the object's vertices."
            
            qp = QtGui.QPainter(self.viewport())
            if not qp.isActive():
                qp.begin(self)
            
            qp.setPen(QtGui.QColor(255, 255, 255))
            qp.setFont(self.font)
            qp.drawText(paint_event.rect(), QtCore.Qt.AlignCenter, msg)
            qp.end()
        
        QtWidgets.QTableView.paintEvent(self, paint_event)

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Space:
            self.key_pressed.emit(event)
        else:
            QtWidgets.QWidget.keyPressEvent(self, event)
    
    def mousePressEvent(self, event):
        QtWidgets.QTableView.mousePressEvent(self, event)

        # Begins edit on current cell.
        if event.button() == QtCore.Qt.MouseButton.RightButton:
            # Save this prior to any changes.
            self.old_skin_data = copy.deepcopy(self.editor_inst.skin_data)
            self.edit(self.currentIndex())

    def header_on_context_trigger(self, point):
        self.header_context_menu.exec_(self.mapToGlobal(point))

    def header_on_left_clicked(self, index):
        self.selectColumn(index)

    def header_on_middle_clicked(self, index):
        inf = self.table_model.display_infs[index]
        self.header_middle_clicked.emit(inf)

    def display_inf_on_triggered(self):
        inf = self.table_model.display_infs[self.header.last_index]
        self.display_inf_triggered.emit(inf)

    def select_inf_verts_on_triggered(self):
        inf = self.table_model.display_infs[self.header.last_index]
        self.select_inf_verts_triggered.emit(inf)

    def select_inf_on_triggered(self):
        inf = self.table_model.display_infs[self.header.last_index]
        if cmds.objExists(inf):
            cmds.select(inf)

    def set_model(self, abstract_model):
        self.table_model = abstract_model
        self.setModel(self.table_model)

    def display_infs(self):
        return self.table_model.display_infs

    def set_display_infs(self, new_infs):
        self.table_model.display_infs = new_infs

    def begin_update(self):
        self.table_model.layoutAboutToBeChanged.emit()

    def end_update(self):
        self.table_model.layoutChanged.emit()

    def emit_header_data_changed(self):
        self.table_model.headerDataChanged.emit(
            QtCore.Qt.Horizontal, 0, len(self.table_model.display_infs))

    def fit_headers_to_contents(self):
        for i in range(self.horizontalHeader().count()):
            self.resizeColumnToContents(i)

    def reset_color_headers(self):
        self.table_model.header_colors = []

    def color_headers(self, count):
        """
        Resets the colors on the top headers.
        An active influence will be colored as blue.
        When using the Softimage theme, each header will be the color if its influence.
        """
        self.reset_color_headers()

        for index in range(count):
            header_name = self.table_model.get_inf(index)
            rgb = self.editor_inst.inf_colors.get(header_name)

            color = None
            if rgb is not None:
                color = QtGui.QColor.fromRgbF(*rgb)
            self.table_model.header_colors.append(color)

    def get_selected_indexes(self):
        return [
            index
            for index in self.selectedIndexes()
            if index.isValid()
        ]


class AbstractModel(QtCore.QAbstractTableModel):
    
    def __init__(self, editor_inst, parent=None):
        super(AbstractModel, self).__init__(parent)
        
        self.editor_inst = editor_inst
        self.header_colors = []
        self.display_infs = []
        self.input_value = None  # Used to properly set multiple cells

        self.locked_text = QtGui.QColor(100, 100, 100)
        self.zero_weight_text = QtGui.QColor(255, 50, 50)
        self.header_locked_text = QtGui.QColor(QtCore.Qt.black)
        self.header_active_inf_back_color = QtGui.QColor(0, 120, 180)

    def rowCount(self, parent):
        raise NotImplementedError

    def columnCount(self, parent):
        raise NotImplementedError

    def data(self, index, role):
        raise NotImplementedError
    
    def setData(self, index, value, role):
        raise NotImplementedError
    
    def headerData(self, column, orientation, role):
        raise NotImplementedError
    
    def flags(self, index):
        return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEditable

    def get_inf(self, index):
        return self.display_infs[index]
