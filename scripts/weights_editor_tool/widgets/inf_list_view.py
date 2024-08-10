import fnmatch
from functools import partial

from maya import cmds, OpenMaya

from weights_editor_tool import weights_editor_utils as utils
from weights_editor_tool.widgets.widgets_utils import *


class InfListView(QListView):
    
    middle_clicked = Signal(str)
    toggle_locks_triggered = Signal(list)
    set_locks_triggered = Signal(list, bool)
    select_inf_verts_triggered = Signal()
    add_infs_to_verts_triggered = Signal()
    
    def __init__(self, editor_inst, parent=None):
        QListView.__init__(self, parent=parent)

        self._last_filter = ""

        self.list_model = InfListModel(editor_inst, parent=self)
        self.setModel(self.list_model)

        self.setAlternatingRowColors(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)

        self.doubleClicked.connect(self._on_double_clicked)

        self._display_inf_action = QAction(self)
        self._display_inf_action.setText("Display influence (middle-click)")
        self._display_inf_action.triggered.connect(self._display_current_inf)

        self._select_infs_action = QAction(self)
        self._select_infs_action.setText("Select influences (double-click)")
        self._select_infs_action.triggered.connect(self._select_current_infs)

        self._select_inf_verts_action = QAction(self)
        self._select_inf_verts_action.setText("Select influence's vertexes")
        self._select_inf_verts_action.triggered.connect(self.select_inf_verts_triggered.emit)

        self._lock_infs_action = QAction(self)
        self._lock_infs_action.setText("Lock influences (space)")
        self._lock_infs_action.triggered.connect(partial(self._set_inf_locks_on_triggered, True))

        self._unlock_infs_action = QAction(self)
        self._unlock_infs_action.setText("Unlock influences (space)")
        self._unlock_infs_action.triggered.connect(partial(self._set_inf_locks_on_triggered, False))

        self._add_infs_to_verts_action = QAction(self)
        self._add_infs_to_verts_action.setText("Add influences to vertexes")
        self._add_infs_to_verts_action.triggered.connect(self.add_infs_to_verts_triggered.emit)

        self._header_context_menu = QMenu(parent=self)
        self._header_context_menu.addAction(self._display_inf_action)
        self._header_context_menu.addSeparator()
        self._header_context_menu.addAction(self._select_infs_action)
        self._header_context_menu.addAction(self._select_inf_verts_action)
        self._header_context_menu.addSeparator()
        self._header_context_menu.addAction(self._lock_infs_action)
        self._header_context_menu.addAction(self._unlock_infs_action)
        self._header_context_menu.addSeparator()
        self._header_context_menu.addAction(self._add_infs_to_verts_action)

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_requested)

    def mousePressEvent(self, event):
        QListView.mousePressEvent(self, event)
        if event.button() == Qt.MiddleButton:
            self._display_current_inf()
    
    def keyPressEvent(self, event):
        key_code = event.key() | event.modifiers()

        if key_code in self.window().toggle_inf_lock_key_codes:
            infs = [
                self._get_internal_name(index.row())
                for index in self.selectedIndexes()
            ]

            if infs:
                self.toggle_locks_triggered.emit(infs)
        else:
            QListView.keyPressEvent(self, event)

    def _on_double_clicked(self, *args):
        self._select_current_infs()

    def _on_context_requested(self, point):
        self._header_context_menu.exec_(self.mapToGlobal(point))

    def _set_inf_locks_on_triggered(self, lock):
        infs = [
            self._get_internal_name(index.row())
            for index in self.selectedIndexes()
        ]

        if infs:
            self.set_locks_triggered.emit(infs, lock)

    def _select_current_infs(self):
        objs = []
        indexes = self.selectedIndexes()

        for index in indexes:
            obj_name = self._get_internal_name(index.row())
            if not cmds.objExists(obj_name):
                OpenMaya.MGlobal.displayWarning("Unable to find '{0}' in the scene".format(obj_name))
                continue
            objs.append(obj_name)

        if objs:
            cmds.select(objs)

    def _display_current_inf(self):
        index = self.currentIndex()
        if index.isValid():
            inf = self._get_internal_name(index.row())
            self.middle_clicked.emit(inf)

    def _find_item(self, name):
        results = self.model().findItems(name)
        if results:
            return results[0]

    def _get_internal_name(self, row):
        return self.list_model.item(row).text()

    def _get_displayed_name(self, row):
        name = self._get_internal_name(row)
        if self.list_model.hide_long_names:
            name = name.split("|")[-1]
        return name

    def begin_update(self):
        self.list_model.layoutAboutToBeChanged.emit()

    def end_update(self):
        self.list_model.layoutChanged.emit()

    def select_item(self, name):
        item = self._find_item(name)
        if item:
            model = self.model()
            sel_model = self.selectionModel()
            index = model.indexFromItem(item)
            sel_model.select(index, sel_model.SelectCurrent)

    def get_displayed_items(self):
        return [
            self._get_displayed_name(i)
            for i in range(self.list_model.rowCount())
        ]

    def apply_filter(self, pattern):
        self._last_filter = pattern

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
            self.apply_filter(self._last_filter)


class InfListModel(QStandardItemModel):
    
    def __init__(self, editor_inst, parent=None):
        QStandardItemModel.__init__(self, parent=parent)
        
        self._editor_inst = editor_inst
        self.hide_long_names = True

        self._lock_icon = utils.load_pixmap("inf_view/lock.png", height=24)
        self._joint_icon = utils.load_pixmap("inf_view/joint.png", height=24)

        self._size_hint = QSize(1, 30)

        self._text_color = QColor(Qt.white)
        self._locked_text_color = QColor(130, 130, 130)
        self._active_inf_back_color = QColor(0, 120, 180)
        self._active_inf_text_color = QColor(Qt.black)
    
    def data(self, index, role):
        QStandardItemModel.data(self, index, role)
        
        if not index.isValid():
            return

        item = self.itemFromIndex(index)
        inf_name = item.text()
        
        if role == Qt.DisplayRole:
            # Show influence's name.
            if self.hide_long_names:
                return inf_name.split("|")[-1]
            return inf_name
        elif role == Qt.BackgroundColorRole:
            # Show color influence.
            if inf_name == self._editor_inst.color_inf:
                return self._active_inf_back_color
        elif role == Qt.ForegroundRole:
            # Show locked influences.
            if inf_name in self._editor_inst.obj.infs:
                inf_index = self._editor_inst.obj.infs.index(inf_name)
                if self._editor_inst.locks[inf_index]:
                    if inf_name == self._editor_inst.color_inf:
                        return self._active_inf_text_color
                    else:
                        return self._locked_text_color
            return self._text_color
        elif role == Qt.SizeHintRole:
            return self._size_hint
        elif role == Qt.DecorationRole:
            icon = self._joint_icon

            if inf_name in self._editor_inst.obj.infs:
                # Show locked influence icons.
                inf_index = self._editor_inst.obj.infs.index(inf_name)
                if self._editor_inst.locks[inf_index]:
                    icon = self._lock_icon

            return icon
        elif role == Qt.ToolTipRole:
            return inf_name
