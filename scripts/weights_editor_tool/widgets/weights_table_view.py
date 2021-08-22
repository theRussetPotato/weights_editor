import copy

import maya.cmds as cmds

from PySide2 import QtCore
from PySide2 import QtWidgets

from weights_editor_tool import weights_editor_utils as utils
from weights_editor_tool.widgets import abstract_weights_view


class TableView(abstract_weights_view.AbstractWeightsView):

    update_ended = QtCore.Signal(bool)

    def __init__(self, editor_inst):
        super(TableView, self).__init__("table", QtCore.Qt.Horizontal, editor_inst)

        self.selected_rows = set()
        self.header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)

        self.sort_weights_vert_order_action = QtWidgets.QAction(self)
        self.sort_weights_vert_order_action.setText("Sort by weights (vertex order)")
        self.sort_weights_vert_order_action.triggered.connect(self.sort_vert_order_on_triggered)

        self.header_context_menu.addAction(self.sort_weights_vert_order_action)

        table_model = TableModel(editor_inst, parent=self)
        self.set_model(table_model)

    def selectionChanged(self, selected, deselected):
        QtWidgets.QTableView.selectionChanged(self, selected, deselected)
        self.cell_selection_on_changed()

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
        
        if self.model().input_value is not None:
            self.model().input_value = None
            
            vert_indexes = list(set(
                self.model().get_vert_index(index.row())
                for index in self.selectedIndexes()))
            
            current_obj = self.editor_inst.get_obj_by_name(self.editor_inst.obj)
            
            self.editor_inst.add_undo_command(
                "Set skin weights",
                current_obj,
                self.old_skin_data,
                copy.deepcopy(self.editor_inst.skin_data),
                vert_indexes,
                self.save_table_selection())
        
        self.old_skin_data = None

    def sort_ascending_on_triggered(self):
        self.reorder_rows(self.header.last_index, QtCore.Qt.DescendingOrder)

    def sort_descending_on_triggered(self):
        self.reorder_rows(self.header.last_index, QtCore.Qt.AscendingOrder)

    def sort_vert_order_on_triggered(self):
        self.reorder_rows(self.header.last_index, None)

    def cell_selection_on_changed(self):
        """
        Selects vertexes based on what was selected on the table.
        """
        if self.editor_inst.ignore_cell_selection_event or \
                not self.editor_inst.auto_select_vertex_action.isChecked():
            return

        rows = set(
            index.row()
            for index in self.get_selected_indexes()
        )

        if rows == self.selected_rows:
            return

        self.selected_rows = rows

        current_obj = self.editor_inst.get_obj_by_name(self.editor_inst.obj)
        if current_obj is not None:
            component = "vtx"
            if utils.is_curve(current_obj):
                component = "cv"

            vertex_list = [
                "{0}.{1}[{2}]".format(current_obj, component, self.editor_inst.vert_indexes[row])
                for row in rows
            ]
        else:
            vertex_list = []

        self.editor_inst.block_selection_cb = True
        cmds.select(vertex_list)
        self.editor_inst.block_selection_cb = False

    def reorder_rows(self, column, order):
        """
        Re-orders and displays rows by weight values.

        Args:
            column(int): The influence to compare weights with.
            order(QtCore.Qt.SortOrder): The direction to sort the weights by.
                                        If None, re-orders based on vertex index.
        """
        self.begin_update()
        selection_data = self.save_table_selection()

        inf = self.table_model.display_infs[column]

        if order is None:
            self.editor_inst.vert_indexes = sorted(self.editor_inst.vert_indexes)
        else:
            self.editor_inst.vert_indexes = sorted(
                self.editor_inst.vert_indexes,
                key=lambda x: self.editor_inst.skin_data[x]["weights"].get(inf) or 0.0,
                reverse=order)

        self.end_update()
        self.load_table_selection(selection_data)

    def color_headers(self):
        count = self.table_model.columnCount(self)
        super(TableView, self).color_headers(count)

    def select_items_by_inf(self, inf):
        if inf and inf in self.table_model.display_infs:
            column = self.table_model.display_infs.index(inf)
            selection_model = self.selectionModel()
            index = self.model().createIndex(0, column)
            flags = QtCore.QItemSelectionModel.ClearAndSelect | QtCore.QItemSelectionModel.Columns
            selection_model.select(index, flags)
        else:
            self.clearSelection()

    def get_selected_verts_and_infs(self):
        indexes = self.get_selected_indexes()
        if not indexes:
            return []

        verts_and_infs = []

        for index in indexes:
            row = index.row()
            column = index.column()
            if column >= len(self.table_model.display_infs):
                continue

            vert_index = self.editor_inst.vert_indexes[row]
            inf = self.table_model.display_infs[column]
            verts_and_infs.append((vert_index, inf))

        return verts_and_infs

    def save_table_selection(self):
        """
        Saves table's selection to a data set.

        Returns:
            A dictionary representing the selection.
            {inf_name:[vert_index, ..]}
        """
        selection_data = {}

        for index in self.selectedIndexes():
            if not index.isValid():
                continue

            if index.column() > len(self.table_model.display_infs) - 1:
                continue

            inf = self.table_model.display_infs[index.column()]
            if inf not in selection_data:
                selection_data[inf] = []

            if index.row() > len(self.editor_inst.vert_indexes):
                continue

            vert_index = self.editor_inst.vert_indexes[index.row()]
            selection_data[inf].append(vert_index)

        return selection_data

    def load_table_selection(self, selection_data):
        """
        Attempts to load selection by supplied data set.

        Args:
            selection_data(dict): See save method for data's structure.
        """
        self.clearSelection()

        if not selection_data:
            return

        selection_model = self.selectionModel()
        item_selection = QtCore.QItemSelection()

        for inf, vert_indexes in selection_data.items():
            if inf not in self.table_model.display_infs:
                continue

            column = self.table_model.display_infs.index(inf)

            for vert_index in vert_indexes:
                if vert_index not in self.editor_inst.vert_indexes:
                    continue

                row = self.editor_inst.vert_indexes.index(vert_index)
                index = self.model().index(row, column)
                item_selection.append(QtCore.QItemSelectionRange(index, index))

        selection_model.select(item_selection, QtCore.QItemSelectionModel.Select)

    def end_update(self):
        super(TableView, self).end_update()
        over_limit = len(self.editor_inst.vert_indexes) > self.table_model.max_display_count
        self.update_ended.emit(over_limit)


class TableModel(abstract_weights_view.AbstractModel):
    
    def __init__(self, editor_inst, parent=None):
        super(TableModel, self).__init__(editor_inst, parent)
        self.max_display_count = 5000
    
    def rowCount(self, parent):
        return min(
            len(self.editor_inst.vert_indexes), self.max_display_count)
    
    def columnCount(self, parent):
        return len(self.display_infs)

    def data(self, index, role):
        if not index.isValid():
            return

        roles = [QtCore.Qt.ForegroundRole, QtCore.Qt.DisplayRole, QtCore.Qt.EditRole]

        if role in roles:
            inf = self.get_inf(index.column())
            value = self.get_value_by_index(index)
            
            if role == QtCore.Qt.ForegroundRole:
                inf_index = self.editor_inst.infs.index(inf)
                is_locked = self.editor_inst.locks[inf_index]
                if is_locked:
                    return self.locked_text
                if value == 0:
                    return self.zero_weight_text
            else:
                if value != 0 and value < 0.001:
                    return "< 0.001"
                return "{0:.3f}".format(value)
    
    def setData(self, index, value, role):
        """
        Qt doesn't handle multiple cell edits very well.
        This is the only place we can get the user's input, so first we check if it's valid first.
        If not, all other cells will be ignored.
        """
        if not index.isValid():
            return False
        
        if role != QtCore.Qt.EditRole:
            return False
        
        # Triggers if first cell wasn't valid
        if value is None and self.input_value is None:
            return False

        if self.input_value is None:
            if not value.replace(".", "").isdigit():
                return False
            
            value = float(value)
            
            if not (value >= 0 and value <= 1):
                return False

            # Skip if the values are the same.
            # Necessary since left-clicking out of cell won't cancel.
            old_value = self.get_value_by_index(index)
            old_value_str = "{0:.3f}".format(old_value)
            value_str = "{0:.3f}".format(value)
            if value_str == old_value_str:
                return False

            self.input_value = value
        else:
            value = self.input_value

        # Distribute the weights.
        inf = self.get_inf(index.column())
        vert_index = self.get_vert_index(index.row())
        utils.update_weight_value(self.editor_inst.skin_data[vert_index]["weights"], inf, value)
        
        return True
    
    def headerData(self, column, orientation, role):
        """
        Deterimines the header's labels and style.
        """
        if role == QtCore.Qt.ForegroundRole:
            # Color locks
            if orientation == QtCore.Qt.Horizontal:
                inf_name = self.display_infs[column]
                
                if inf_name in self.editor_inst.infs:
                    inf_index = self.editor_inst.infs.index(inf_name)
                    
                    is_locked = self.editor_inst.locks[inf_index]
                    if is_locked:
                        return self.header_locked_text
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
                    if self.editor_inst.color_inf is not None:
                        if self.editor_inst.color_inf == self.get_inf(column):
                            return self.header_active_inf_back_color
        elif role == QtCore.Qt.DisplayRole:
            if orientation == QtCore.Qt.Horizontal:
                # Show top labels
                if self.display_infs and column < len(self.display_infs):
                    return self.display_infs[column]
            else:
                # Show side labels
                if self.editor_inst.vert_indexes and column < len(self.editor_inst.vert_indexes):
                    return self.editor_inst.vert_indexes[column]
        elif role == QtCore.Qt.ToolTipRole:
            if orientation == QtCore.Qt.Horizontal:
                if self.display_infs and column < len(self.display_infs):
                    return self.display_infs[column]

    def get_vert_index(self, row):
        return self.editor_inst.vert_indexes[row]

    def get_value_by_index(self, index):
        inf = self.get_inf(index.column())
        vert_index = self.get_vert_index(index.row())
        return self.editor_inst.skin_data[vert_index]["weights"].get(inf) or 0
