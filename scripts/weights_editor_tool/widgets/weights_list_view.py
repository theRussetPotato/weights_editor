import copy

from PySide2 import QtCore
from PySide2 import QtWidgets

from weights_editor_tool import weights_editor_utils as utils
from weights_editor_tool.widgets import abstract_weights_view


class ListView(abstract_weights_view.AbstractWeightsView):

    def __init__(self, editor_inst):
        super(ListView, self).__init__("list", QtCore.Qt.Vertical, editor_inst)

        self.sort_inf_name_action = QtWidgets.QAction(self)
        self.sort_inf_name_action.setText("Sort by inf name")
        self.sort_inf_name_action.triggered.connect(self.sort_inf_name_on_triggered)

        self.header_context_menu.addAction(self.sort_inf_name_action)

        table_model = ListModel(editor_inst, parent=self)
        self.set_model(table_model)

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
            
            current_obj = self.editor_inst.get_obj_by_name(self.editor_inst.obj)
            
            self.editor_inst.add_undo_command(
                "Set skin weights",
                current_obj,
                self.old_skin_data,
                copy.deepcopy(self.editor_inst.skin_data),
                self.editor_inst.vert_indexes,
                self.save_table_selection())
        
        self.old_skin_data = None

    def sort_ascending_on_triggered(self):
        self.reorder_by_values(QtCore.Qt.DescendingOrder)

    def sort_descending_on_triggered(self):
        self.reorder_by_values(QtCore.Qt.AscendingOrder)

    def sort_inf_name_on_triggered(self):
        self.reorder_by_name()

    def end_update(self):
        self.table_model.average_weights = {}
        super(ListView, self).end_update()

    def reorder_by_name(self, order=QtCore.Qt.AscendingOrder):
        self.begin_update()
        selection_data = self.save_table_selection()

        self.table_model.display_infs.sort(reverse=order)

        self.end_update()
        self.load_table_selection(selection_data)

    def reorder_by_values(self, order):
        self.begin_update()
        selection_data = self.save_table_selection()

        self.table_model.display_infs = sorted(
            self.table_model.display_infs,
            key=lambda x: self.table_model.get_average_weight(x) or 0.0,
            reverse=order)

        self.end_update()
        self.load_table_selection(selection_data)

    def color_headers(self):
        count = self.table_model.rowCount(self)
        super(ListView, self).color_headers(count)

    def select_items_by_inf(self, inf):
        if inf and inf in self.table_model.display_infs:
            row = self.table_model.display_infs.index(inf)
            selection_model = self.selectionModel()
            index = self.model().createIndex(row, 0)
            flags = QtCore.QItemSelectionModel.ClearAndSelect | QtCore.QItemSelectionModel.Rows
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
            if row >= len(self.table_model.display_infs):
                continue

            for vert_index in self.editor_inst.vert_indexes:
                inf = self.table_model.display_infs[row]
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

        verts_and_infs = self.get_selected_verts_and_infs()
        for vert_index, inf in verts_and_infs:
            if inf not in selection_data:
                selection_data[inf] = []
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

            row = self.table_model.display_infs.index(inf)
            index = self.model().index(row, 0)
            item_selection.append(QtCore.QItemSelectionRange(index, index))

        selection_model.select(item_selection, QtCore.QItemSelectionModel.Select)


class ListModel(abstract_weights_view.AbstractModel):
    
    def __init__(self, editor_inst, parent=None):
        super(ListModel, self).__init__(editor_inst, parent)

        self.average_weights = {}
    
    def rowCount(self, parent):
        return len(self.display_infs)
    
    def columnCount(self, parent):
        if self.display_infs:
            return 1
        else:
            return 0

    def data(self, index, role):
        if not index.isValid():
            return

        roles = [QtCore.Qt.ForegroundRole, QtCore.Qt.DisplayRole, QtCore.Qt.EditRole]

        if role in roles:
            inf = self.get_inf(index.row())
            value = self.get_average_weight(inf)
            
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

            self.input_value = value
        else:
            value = self.input_value

        # Distribute the weights.
        inf = self.get_inf(index.row())

        for vert_index in self.editor_inst.vert_indexes:
            utils.update_weight_value(
                self.editor_inst.skin_data[vert_index]["weights"],
                inf,
                value)

        return True
    
    def headerData(self, index, orientation, role):
        """
        Deterimines the header's labels and style.
        """
        if role == QtCore.Qt.ForegroundRole:
            # Color locks
            if orientation == QtCore.Qt.Vertical:
                inf_name = self.display_infs[index]
                
                if inf_name in self.editor_inst.infs:
                    inf_index = self.editor_inst.infs.index(inf_name)
                    
                    is_locked = self.editor_inst.locks[inf_index]
                    if is_locked:
                        return self.header_locked_text
        elif role == QtCore.Qt.BackgroundColorRole:
            # Color background
            if orientation == QtCore.Qt.Vertical:
                # Use softimage colors
                if self.header_colors:
                    color = self.header_colors[index]
                    if color is not None:
                        return color
                else:
                    # Color selected inf
                    if self.editor_inst.color_inf is not None:
                        if self.editor_inst.color_inf == self.get_inf(index):
                            return self.header_active_inf_back_color
        elif role == QtCore.Qt.DisplayRole:
            if orientation == QtCore.Qt.Vertical:
                # Show top labels
                if self.display_infs and index < len(self.display_infs):
                    return self.display_infs[index]
            else:
                return "Average values"
        elif role == QtCore.Qt.ToolTipRole:
            if orientation == QtCore.Qt.Vertical:
                if self.display_infs and index < len(self.display_infs):
                    return self.display_infs[index]

    def get_average_weight(self, inf):
        if not self.editor_inst.vert_indexes:
            return 0

        if inf not in self.average_weights:
            values = [
                self.editor_inst.skin_data[vert_index]["weights"].get(inf) or 0
                for vert_index in self.editor_inst.vert_indexes
            ]

            self.average_weights[inf] = sum(values) / len(self.editor_inst.vert_indexes)

        return self.average_weights[inf]
