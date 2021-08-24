"""
Author:
    Jason Labbe

Credits:
    Smooth all influences is using Brave Rabbit's brSmoothWeights plugin.
        https://www.github.com/IngoClemens/brSmoothWeights

Limitations:
    - Internal data won't sync if weights or influences are modified externally. (ie: can't paint weights while tool is open)

Example of usage:
    from weights_editor_tool import weights_editor
    weights_editor.run()
"""

import os
import copy
import json
import shiboken2
from functools import partial

import maya.cmds as cmds
import maya.mel as mel
import maya.OpenMaya as OpenMaya

from PySide2 import QtGui
from PySide2 import QtCore
from PySide2 import QtWidgets

from weights_editor_tool.enums import ColorTheme, WeightOperation, SmoothOperation
from weights_editor_tool import weights_editor_utils as utils
from weights_editor_tool.classes import hotkey as hotkey_module
from weights_editor_tool.classes import command_edit_weights
from weights_editor_tool.classes import command_lock_infs
from weights_editor_tool.widgets import custom_double_spinbox
from weights_editor_tool.widgets import inf_list_view
from weights_editor_tool.widgets import weights_list_view
from weights_editor_tool.widgets import weights_table_view
from weights_editor_tool.widgets import hotkeys_dialog
from weights_editor_tool.widgets import about_dialog


class WeightsEditor(QtWidgets.QMainWindow):

    version = "2.0.1"
    instance = None
    cb_selection_changed = None
    shortcuts = []

    def __init__(self, parent=None):
        QtWidgets.QMainWindow.__init__(self, parent=parent)

        self.del_prev_instance()
        self.__class__.instance = self

        self.maya_main_window = utils.get_maya_window()
        self.setParent(self.maya_main_window)
        self.setWindowFlags(QtCore.Qt.Window)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.setObjectName("weightsEditor")
        
        self.undo_stack = QtWidgets.QUndoStack(parent=self)
        self.undo_stack.setUndoLimit(30)

        self.obj = None
        self.skin_cluster = None
        self.vert_count = None
        self.color_inf = None
        self.copied_vertex = None
        self.vert_indexes = []
        self.infs = []
        self.locks = []
        self.skin_data = {}
        self.inf_colors = {}
        self.color_style = ColorTheme.Max
        self.block_selection_cb = False
        self.ignore_cell_selection_event = False
        self.in_component_mode = utils.is_in_component_mode()
        self.settings_path = os.path.join(os.getenv("HOME"), "maya", "weights_editor.json")
        self.add_preset_values = [-0.75, -0.5, -0.25, -0.1, 0.1, 0.25, 0.5, 0.75]
        self.scale_preset_values = [-50, -25, -10, -5, 5, 10, 25, 50]
        self.set_preset_values = [0.0, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0]

        self.create_gui()

        self.hotkeys = [
            hotkey_module.Hotkey.create_from_default("Toggle table / list view", partial(self.toggle_check_button, self.toggle_view_button)),
            hotkey_module.Hotkey.create_from_default("Show utilities", partial(self.toggle_check_button, self.show_utilities_button)),
            hotkey_module.Hotkey.create_from_default("Show add presets", partial(self.toggle_check_button, self.show_add_button)),
            hotkey_module.Hotkey.create_from_default("Show scale presets", partial(self.toggle_check_button, self.show_scale_button)),
            hotkey_module.Hotkey.create_from_default("Show set presets", partial(self.toggle_check_button, self.show_set_button)),
            hotkey_module.Hotkey.create_from_default("Show inf list", partial(self.toggle_check_button, self.show_inf_button)),
            hotkey_module.Hotkey.create_from_default("Show inf colors", partial(self.toggle_check_button, self.hide_colors_button)),
            hotkey_module.Hotkey.create_from_default("Mirror all", self.mirror_all_skin_on_clicked),
            hotkey_module.Hotkey.create_from_default("Prune", self.prune_on_clicked),
            hotkey_module.Hotkey.create_from_default("Run smooth (vert infs)", partial(self.run_smooth, SmoothOperation.Normal)),
            hotkey_module.Hotkey.create_from_default("Run smooth (all infs)", partial(self.run_smooth, SmoothOperation.AllInfluences)),
            hotkey_module.Hotkey.create_from_default("Undo", self.undo_on_click),
            hotkey_module.Hotkey.create_from_default("Redo", self.redo_on_click),
            hotkey_module.Hotkey.create_from_default("Grow selection", self.grow_selection),
            hotkey_module.Hotkey.create_from_default("Shrink selection", self.shrink_selection),
            hotkey_module.Hotkey.create_from_default("Select edge loop", self.select_edge_loop),
            hotkey_module.Hotkey.create_from_default("Select ring loop", self.select_ring_loop),
            hotkey_module.Hotkey.create_from_default("Select perimeter", self.select_perimeter),
            hotkey_module.Hotkey.create_from_default("Select shell", self.select_shell)
        ]

        self.restore_state()
        self.set_undo_buttons_enabled_state()
        self.register_shortcuts()
        self.pick_obj_on_clicked()

    @classmethod
    def run(cls):
        inst = cls()
        inst.show()
        return inst

    @classmethod
    def del_prev_instance(cls):
        """
        Deletes any previous window.
        """
        if cls.instance is not None:
            try:
                cls.instance.close()
                if cls.instance and shiboken2.isValid(cls.instance):
                    cls.instance.deleteLater()
            finally:
                cls.instance = None

    @classmethod
    def remove_shortcuts(cls):
        for shortcut in cls.shortcuts:
            shortcut.setEnabled(False)
        cls.shortcuts = []
    
    def create_gui(self):
        """
        Creates all interface objects.
        """

        win_color = self.palette().color(QtGui.QPalette.Normal, QtGui.QPalette.Window)
        preset_hover_color = win_color.lighter(130)

        self.setStyleSheet("""
            QGroupBox {{
                font-style: italic;
            }}
            
            QMenuBar {{
                background-color: {winColor};
            }}
            
            QTableView:item {{
                border: 0px;
                padding: 3px;
            }}
            
            QListView::item {{
                color: None;
            }}
            
            QScrollArea {{
                border: none;
            }}
            
            #presetPositiveButton {{
                border: 1px solid gray;
                background-color: {presetBg};
            }}
            
            #presetPositiveButton:hover {{
                background-color: rgb({presetPosR}, {presetPosG}, {presetPosB});
            }}
            
            #presetPositiveButton:pressed {{
                background-color: black;
                border: none;
            }}
            
            #presetNegativeButton {{
                border: 1px solid gray;
                background-color: {presetBg};
            }}
            
            #presetNegativeButton:hover {{
                background-color: rgb({presetNegR}, {presetNegG}, {presetNegB});
            }}
            
            #presetNegativeButton:pressed {{
                background-color: black;
                border: none;
            }}
            
            #warningLabel {{
                background-color: yellow;
                color: black;
                padding-left: 4px;
            }}
        """.format(
            presetBg=win_color.lighter(120).name(),
            winColor=win_color.lighter(110).name(),
            presetHoverColor=preset_hover_color.name(),
            presetPosR=preset_hover_color.red(),
            presetPosG=preset_hover_color.green() + 20,
            presetPosB=preset_hover_color.blue(),
            presetNegR=preset_hover_color.red() + 20,
            presetNegG=preset_hover_color.green(),
            presetNegB=preset_hover_color.blue()
        ))

    #
    # MENU BAR
    #
        self.menu_bar = self.menuBar()

        self.options_menu = QtWidgets.QMenu("&Tool settings", parent=self)
        self.menu_bar.addMenu(self.options_menu)

        self.view_separator = QtWidgets.QAction("[ Weights list / table view ]", self)
        self.view_separator.setEnabled(False)
        self.options_menu.addAction(self.view_separator)

        self.auto_update_table_action = QtWidgets.QAction("Auto-update view when selecting in viewport", self)
        self.auto_update_table_action.setCheckable(True)
        self.auto_update_table_action.setChecked(True)
        self.auto_update_table_action.triggered.connect(self.auto_update_on_toggled)
        self.options_menu.addAction(self.auto_update_table_action)

        self.auto_select_infs_action = QtWidgets.QAction("Auto-select cells from active influence", self)
        self.auto_select_infs_action.setCheckable(True)
        self.auto_select_infs_action.setChecked(True)
        self.options_menu.addAction(self.auto_select_infs_action)

        self.table_view_separator = QtWidgets.QAction("[ Table view ]", self)
        self.table_view_separator.setEnabled(False)
        self.options_menu.addAction(self.table_view_separator)

        self.auto_select_vertex_action = QtWidgets.QAction("Auto-select vertexes when selecting cells", self)
        self.auto_select_vertex_action.setCheckable(True)
        self.options_menu.addAction(self.auto_select_vertex_action)

        self.set_limit_action = QtWidgets.QAction("Set max row limit", self)
        self.set_limit_action.triggered.connect(self.set_limit_on_triggered)
        self.options_menu.addAction(self.set_limit_action)

        self.color_separator = QtWidgets.QAction("[ Color settings ]", self)
        self.color_separator.setEnabled(False)
        self.options_menu.addAction(self.color_separator)

        self.color_sub_menu = self.options_menu.addMenu("Switch influence color style")

        self.max_color_action = QtWidgets.QAction("3dsMax theme", self)
        self.max_color_action.setCheckable(True)
        self.max_color_action.setChecked(True)
        self.max_color_action.triggered.connect(partial(self.switch_color_on_clicked, ColorTheme.Max))
        self.color_sub_menu.addAction(self.max_color_action)

        self.maya_color_action = QtWidgets.QAction("Maya theme", self)
        self.maya_color_action.setCheckable(True)
        self.maya_color_action.triggered.connect(partial(self.switch_color_on_clicked, ColorTheme.Maya))
        self.color_sub_menu.addAction(self.maya_color_action)

        self.softimage_color_action = QtWidgets.QAction("Softimage theme", self)
        self.softimage_color_action.setCheckable(True)
        self.softimage_color_action.triggered.connect(partial(self.switch_color_on_clicked, ColorTheme.Softimage))
        self.color_sub_menu.addAction(self.softimage_color_action)

        self.visibility_separator = QtWidgets.QAction("Visibility settings", self)
        self.visibility_separator.setSeparator(True)
        self.options_menu.addAction(self.visibility_separator)

        self.launch_hotkeys_action = QtWidgets.QAction("Edit", self)
        self.launch_hotkeys_action.triggered.connect(self.launch_hotkeys_on_clicked)

        self.hotkeys_menu = self.menu_bar.addMenu("&Hotkeys")
        self.hotkeys_menu.addAction(self.launch_hotkeys_action)

        self.about_action = QtWidgets.QAction("About this tool", self)
        self.about_action.triggered.connect(self.about_on_triggered)

        self.about_menu = self.menu_bar.addMenu("&About")
        self.about_menu.addAction(self.about_action)

    #
    # CENTRAL WIDGET
    #

        self.central_widget = QtWidgets.QWidget(parent=self)
        self.central_widget.setObjectName("weightsEditorCentralWidget")

        self.toggle_view_button = QtWidgets.QPushButton("TABLE", parent=self.central_widget)

        self.show_utilities_button = QtWidgets.QPushButton("UTL", parent=self.central_widget)

        self.show_add_button = QtWidgets.QPushButton("ADD", parent=self.central_widget)

        self.show_scale_button = QtWidgets.QPushButton("SCA", parent=self.central_widget)

        self.show_set_button = QtWidgets.QPushButton("SET", parent=self.central_widget)

        self.show_inf_button = QtWidgets.QPushButton("INF", parent=self.central_widget)

        for widget in [
                self.toggle_view_button, self.show_utilities_button, self.show_add_button,
                self.show_scale_button, self.show_set_button, self.show_inf_button]:
            widget.setMinimumWidth(25)
            widget.setMaximumWidth(150)
            widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
            widget.setCheckable(True)
            widget.setChecked(True)

        self.toggle_view_button.toggled.connect(self.toggle_view_on_toggled)
        self.show_utilities_button.toggled.connect(self.show_utilities_on_toggled)
        self.show_add_button.toggled.connect(self.show_add_on_toggled)
        self.show_scale_button.toggled.connect(self.show_scale_on_toggled)
        self.show_set_button.toggled.connect(self.show_set_on_toggled)
        self.show_inf_button.toggled.connect(self.show_inf_on_toggled)

        self.show_layout = utils.wrap_layout(
            [self.toggle_view_button,
             self.show_utilities_button,
             self.show_add_button,
             self.show_scale_button,
             self.show_set_button,
             self.show_inf_button],
            QtCore.Qt.Horizontal,
            spacing=5)

        self.pick_obj_label = QtWidgets.QLabel("Object:", parent=self.central_widget)

        self.pick_obj_button = QtWidgets.QPushButton("", parent=self.central_widget)
        self.pick_obj_button.setToolTip("Switches to selected mesh for editing.")
        self.pick_obj_button.clicked.connect(self.pick_obj_on_clicked)

        self.pick_obj_layout = utils.wrap_layout(
            [self.pick_obj_label,
             self.pick_obj_button,
             10,
             "stretch",
             self.show_layout],
             QtCore.Qt.Horizontal,
             margins=[5, 5, 5, 5])

        self.smooth_button = QtWidgets.QPushButton("Smooth (vert's infs)", parent=self.central_widget)
        self.smooth_button.clicked.connect(partial(self.run_smooth, SmoothOperation.Normal))

        self.smooth_br_button = QtWidgets.QPushButton("Smooth (all infs)", parent=self.central_widget)
        self.smooth_br_button.clicked.connect(partial(self.run_smooth, SmoothOperation.AllInfluences))

        if not hasattr(cmds, "brSmoothWeightsContext"):
            self.smooth_br_button.setEnabled(False)

        self.smooth_strength_spinbox = QtWidgets.QDoubleSpinBox(value=1, parent=self.central_widget)
        self.smooth_strength_spinbox.setToolTip("Smooth's strength.")
        self.smooth_strength_spinbox.setMinimumWidth(50)
        self.smooth_strength_spinbox.setDecimals(1)
        self.smooth_strength_spinbox.setMinimum(0)
        self.smooth_strength_spinbox.setMaximum(1)
        self.smooth_strength_spinbox.setSingleStep(0.1)

        self.prune_button = QtWidgets.QPushButton("Prune", parent=self.central_widget)
        self.prune_button.clicked.connect(self.prune_on_clicked)

        self.prune_spinbox = QtWidgets.QDoubleSpinBox(value=0.1, parent=self.central_widget)
        self.prune_spinbox.setToolTip("Prune any influence below this value.")
        self.prune_spinbox.setDecimals(3)
        self.prune_spinbox.setMinimum(0.001)
        self.prune_spinbox.setSingleStep(0.01)

        self.vert_ops_layout = utils.wrap_layout(
            [self.prune_button,
             self.prune_spinbox,
             self.smooth_button,
             self.smooth_br_button,
             self.smooth_strength_spinbox,
             "stretch"],
            QtCore.Qt.Horizontal)

        self.mirror_skin_button = QtWidgets.QPushButton("Mirror", parent=self.central_widget)
        self.mirror_skin_button.setToolTip("Mirror weights on selected vertexes only")
        self.mirror_skin_button.clicked.connect(self.mirror_skin_on_clicked)

        self.mirror_all_skin_button = QtWidgets.QPushButton("Mirror all", parent=self.central_widget)
        self.mirror_all_skin_button.clicked.connect(self.mirror_all_skin_on_clicked)

        self.mirror_mode = QtWidgets.QComboBox(parent=self.central_widget)
        self.mirror_mode.setToolTip("Mirror axis")
        self.mirror_mode.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.mirror_mode.setMinimumWidth(35)
        self.mirror_mode.setMaximumWidth(50)
        self.mirror_mode.addItems(["XY", "YZ", "XZ", "-XY", "-YZ", "-XZ"])

        self.mirror_surface = QtWidgets.QComboBox(parent=self.central_widget)
        self.mirror_surface.setToolTip("Mirror surface association")
        self.mirror_surface.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.mirror_surface.setMinimumWidth(35)
        self.mirror_surface.setMaximumWidth(100)
        self.mirror_surface.addItems(["Closest Point", "Ray Cast", "Closest Component"])

        self.mirror_inf = QtWidgets.QComboBox(parent=self.central_widget)
        self.mirror_inf.setToolTip("Mirror influence association")
        self.mirror_inf.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.mirror_inf.setMinimumWidth(35)
        self.mirror_inf.setMaximumWidth(100)
        self.mirror_inf.addItems(["Label", "Closest Point", "Closest Bone", "Name", "One To One"])

        self.mirror_layout = utils.wrap_layout(
            [self.mirror_skin_button,
             self.mirror_all_skin_button,
             self.mirror_mode,
             self.mirror_surface,
             self.mirror_inf,
             "stretch"],
            QtCore.Qt.Horizontal,
            margins=[0, 0, 0, 0])

        self.copy_vertex_button = QtWidgets.QPushButton("Copy vertex", parent=self.central_widget)
        self.copy_vertex_button.setToolTip("Copy weights on first selected vertex")
        self.copy_vertex_button.clicked.connect(self.copy_vertex_on_clicked)

        self.paste_vertex_button = QtWidgets.QPushButton("Paste vertex", parent=self.central_widget)
        self.paste_vertex_button.setToolTip("Paste weights on selected vertexes")
        self.paste_vertex_button.clicked.connect(self.paste_vertex_on_clicked)

        self.copy_vert_layout = utils.wrap_layout(
            [self.copy_vertex_button,
             self.paste_vertex_button,
             "stretch"],
            QtCore.Qt.Horizontal)

        self.weight_layout = utils.wrap_layout(
            [self.vert_ops_layout,
             self.mirror_layout,
             self.copy_vert_layout],
            QtCore.Qt.Vertical,
            margins=[0, 0, 0, 0])

        self.weight_frame = QtWidgets.QFrame(parent=self.central_widget)
        self.weight_frame.setLayout(self.weight_layout)
        self.weight_frame.setStyleSheet("QFrame {{background-color: {}}}".format(win_color.lighter(109).name()))

        self.weight_scroll_area = QtWidgets.QScrollArea(parent=self.central_widget)
        self.weight_scroll_area.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.weight_scroll_area.setFocusPolicy(QtCore.Qt.NoFocus)
        self.weight_scroll_area.setWidget(self.weight_frame)
        self.weight_scroll_area.setWidgetResizable(True)

        self.weight_scroll_layout = utils.wrap_layout(
            [self.weight_scroll_area],
            QtCore.Qt.Vertical,
            margins=[5, 0, 1, 0])

        self.weight_groupbox = QtWidgets.QGroupBox("Weight utilities", parent=self.central_widget)
        self.weight_groupbox.setLayout(self.weight_scroll_layout)

        self.add_layout, self.add_groupbox, self.add_spinbox = \
            self.create_preset_buttons(
                self.add_preset_values,
                self.add_preset_on_clicked,
                self.set_add_on_clicked,
                "Add / subtract weight")

        self.scale_layout, self.scale_groupbox, self.scale_spinbox = \
            self.create_preset_buttons(
                self.scale_preset_values,
                self.scale_preset_on_clicked,
                self.set_scale_on_clicked,
                "Scale weight",
                suffix="%")

        self.set_layout, self.set_groupbox, self.set_spinbox = \
            self.create_preset_buttons(
                self.set_preset_values,
                self.set_preset_on_clicked,
                self.set_on_clicked,
                "Set weight")

        # Setup table
        self.limit_warning_label = QtWidgets.QLabel(parent=self)
        self.limit_warning_label.setObjectName("warningLabel")
        self.limit_warning_label.setWordWrap(True)
        self.limit_warning_label.hide()

        self.weights_table = weights_table_view.TableView(self)
        self.weights_table.update_ended.connect(self.table_on_update_ended)

        self.weights_list = weights_list_view.ListView(self)
        self.weights_list.hide()

        for view in [self.weights_list, self.weights_table]:
            view.key_pressed.connect(self.weights_view_on_key_pressed)
            view.header_middle_clicked.connect(self.header_on_middle_clicked)
            view.display_inf_triggered.connect(self.display_inf_on_triggered)
            view.select_inf_verts_triggered.connect(self.select_inf_verts_on_triggered)

        self.refresh_button = QtWidgets.QPushButton("Refresh", parent=self.central_widget)
        self.refresh_button.setToolTip("Refreshes the table with selected vertexes from the viewport.")
        self.refresh_button.clicked.connect(self.refresh_on_clicked)

        self.show_all_button = QtWidgets.QPushButton("Show all influences", parent=self.central_widget)
        self.show_all_button.setCheckable(True)
        self.show_all_button.setToolTip("Forces the table to show all influences.")
        self.show_all_button.clicked.connect(self.refresh_on_clicked)

        self.hide_colors_button = QtWidgets.QPushButton("Hide influence colors", parent=self.central_widget)
        self.hide_colors_button.setCheckable(True)
        self.hide_colors_button.toggled.connect(self.hide_colors_on_toggled)

        self.flood_to_closest_button = QtWidgets.QPushButton("Flood to closest", parent=self.central_widget)
        self.flood_to_closest_button.setToolTip("Set full weights to the closest joints for easier blocking.")
        self.flood_to_closest_button.clicked.connect(self.flood_to_closest_on_clicked)

        # Undo buttons
        self.undo_button = QtWidgets.QPushButton("Undo", parent=self.central_widget)
        self.undo_button.clicked.connect(self.undo_on_click)
        self.undo_button.setFixedHeight(40)

        self.redo_button = QtWidgets.QPushButton("Redo", parent=self.central_widget)
        self.redo_button.clicked.connect(self.redo_on_click)
        self.redo_button.setFixedHeight(40)

        widgets = [self.refresh_button, self.show_all_button, self.hide_colors_button, self.flood_to_closest_button, self.undo_button, self.refresh_button]
        for button in widgets:
            button.setMinimumWidth(10)

        self.undo_layout = utils.wrap_layout(
            [self.undo_button,
             self.redo_button],
            QtCore.Qt.Horizontal)

        self.settings_layout = utils.wrap_layout(
            [self.refresh_button,
             self.show_all_button,
             self.hide_colors_button,
             self.flood_to_closest_button],
            QtCore.Qt.Horizontal)

        self.main_layout = utils.wrap_layout(
            [self.pick_obj_layout,
             self.weight_groupbox,
             self.add_groupbox,
             self.scale_groupbox,
             self.set_groupbox,
             self.limit_warning_label,
             self.weights_list,
             self.weights_table,
             self.settings_layout,
             self.undo_layout],
            QtCore.Qt.Vertical,
            spacing=3)
        self.central_widget.setLayout(self.main_layout)

        self.setCentralWidget(self.central_widget)

    #
    # INFLUENCE WIDGET
    #

        self.inf_dock_widget = QtWidgets.QDockWidget(parent=self)
        self.setObjectName("weightsEditorInfluenceWidget")
        self.inf_dock_widget.setFeatures(QtWidgets.QDockWidget.DockWidgetMovable)
        self.inf_dock_widget.setWindowTitle("Influences")
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.inf_dock_widget)

        self.inf_widget = QtWidgets.QWidget(parent=self.inf_dock_widget)
        self.inf_dock_widget.setWidget(self.inf_widget)

        self.inf_filter_edit = QtWidgets.QLineEdit(parent=self.inf_widget)
        self.inf_filter_edit.setPlaceholderText("Filter list by names (use * as a wildcard)")
        self.inf_filter_edit.textEdited.connect(self.apply_filter_to_inf_list)

        self.inf_list = inf_list_view.InfListView(self, parent=self.inf_widget)
        self.inf_list.middle_clicked.connect(self.inf_list_on_middle_clicked)
        self.inf_list.toggle_lock_triggered.connect(self.inf_list_on_toggle_lock_triggered)

        self.add_inf_to_vert_button = QtWidgets.QPushButton("Add inf to verts", parent=self.inf_widget)
        self.add_inf_to_vert_button.setToolTip("Adds the selected influence to all selected vertexes.")
        self.add_inf_to_vert_button.clicked.connect(self.add_inf_to_vert_on_clicked)

        self.select_by_infs_button = QtWidgets.QPushButton("Select influence's verts", parent=self.inf_widget)
        self.select_by_infs_button.setToolTip("Selects all vertexes that is effected by the selected influences.")
        self.select_by_infs_button.clicked.connect(self.select_by_infs_on_clicked)

        self.inf_layout = utils.wrap_layout(
            [self.inf_filter_edit,
             self.inf_list,
             self.add_inf_to_vert_button,
             self.select_by_infs_button],
            QtCore.Qt.Vertical)
        self.inf_widget.setLayout(self.inf_layout)

        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setWindowTitle("Weights Editor v{ver}".format(ver=self.version))
        self.resize(1200, 1000)

#
# Custom functions
#

    def get_active_weights_view(self):
        if self.toggle_view_button.isChecked():
            return self.weights_table
        else:
            return self.weights_list

    def create_preset_buttons(self, values, preset_callback, spinbox_callback, caption, suffix=""):
        """
        Procedurally creates a group of preset buttons to adjust weights.
        """
        spinbox = custom_double_spinbox.CustomDoubleSpinbox(parent=self.central_widget)
        spinbox.setFixedWidth(80)
        spinbox.setFixedHeight(25)
        spinbox.setSuffix(suffix)
        spinbox.setSingleStep(10)
        spinbox.setMinimum(-100)
        spinbox.setMaximum(100)
        spinbox.enter_pressed.connect(spinbox_callback)

        layout = utils.wrap_layout(
            [spinbox],
            QtCore.Qt.Horizontal,
            margins=[5, 3, 1, 3])
        layout.setAlignment(QtCore.Qt.AlignLeft)

        for value in values:

            text = "".join([str(value), suffix])
            preset_button = QtWidgets.QPushButton(text, parent=self.central_widget)
            preset_button.setMaximumWidth(60)
            preset_button.setSizePolicy(
                QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
            preset_button.clicked.connect(partial(preset_callback, value))
            preset_button.setToolTip("{0} by {1}".format(caption, text))

            if value > 0:
                preset_button.setObjectName("presetPositiveButton")
            else:
                preset_button.setObjectName("presetNegativeButton")

            layout.addWidget(preset_button)

        groupbox = QtWidgets.QGroupBox(caption, parent=self.central_widget)
        groupbox.setLayout(layout)

        return layout, groupbox, spinbox

    def toggle_check_button(self, button):
        button.setChecked(not button.isChecked())

    def update_tooltips(self):
        """
        Updates tooltips with the latest shortcuts.
        """
        # Matches same indexes as hotkeys in constructor.
        tooltips = [
            (self.toggle_view_button, "Toggle between list or table view"),
            (self.show_utilities_button, "Show weights utility settings"),
            (self.show_add_button, "Show add / sub weight settings"),
            (self.show_scale_button, "Show scale weight settings"),
            (self.show_set_button, "Show set weight settings"),
            (self.show_inf_button, "Show influence list"),
            (self.hide_colors_button, "Hides colors that visualize the weight values.<br><br>"
                                      "Enable this to help speed up performance"),
            (self.mirror_all_skin_button, "Mirror all weights"),
            (self.prune_button, "Prunes selected vertexes in the viewport that are below this value."),
            (self.smooth_button, "Selected vertexes in the viewport will smooth with only influences that are already assigned to it."),
            (self.smooth_br_button, "Selected vertexes in the viewport will smooth with all influences available."),
            (self.undo_button, "Undo last action"),
            (self.redo_button, "Redo last action")
        ]

        for i in range(len(tooltips)):
            widget, tooltip = tooltips[i]
            new_tooltip = tooltip + "<br><br><b>" + self.hotkeys[i].key_to_string() + "</b>"
            widget.setToolTip(new_tooltip)

    def register_shortcuts(self):
        """
        Installs temporary hotkeys that overrides Maya's.
        """
        self.remove_shortcuts()

        for hotkey in self.hotkeys:
            self.__class__.shortcuts.append(
                utils.create_shortcut(
                    QtGui.QKeySequence(hotkey.key_code()), hotkey.func))

        self.update_tooltips()

    def get_obj_by_name(self, obj):
        if obj is not None and cmds.objExists(obj):
            return obj
    
    def set_undo_buttons_enabled_state(self):
        """
        Checks the undo stack and determines enabled state and labels on undo/redo buttons.
        """
        self.undo_button.setEnabled(self.undo_stack.canUndo())
        self.redo_button.setEnabled(self.undo_stack.canRedo())
        
        undo_text = self.undo_stack.undoText()
        
        if undo_text:
            self.undo_button.setText("Undo\n({0})".format(undo_text))
        else:
            self.undo_button.setText("No undos available")
        
        redo_text = self.undo_stack.redoText()
        
        if redo_text:
            self.redo_button.setText("Redo\n({0})".format(redo_text))
        else:
            self.redo_button.setText("No redos available")
    
    def save_state(self):
        """
        Saves gui's current state to a file.
        """
        if not os.path.exists(os.path.dirname(self.settings_path)):
            os.makedirs(os.path.dirname(self.settings_path))
        
        data = {
            "width": self.width(),
            "height": self.height(),
            "inf_dock_widget.area": int(self.dockWidgetArea(self.inf_dock_widget)),
            "color_style": self.color_style,
            "prune_spinbox.value": self.prune_spinbox.value(),
            "smooth_strength_spinbox.value": self.smooth_strength_spinbox.value(),
            "mirror_mode.currentIndex": self.mirror_mode.currentIndex(),
            "mirror_surface.currentIndex": self.mirror_surface.currentIndex(),
            "mirror_inf.currentIndex": self.mirror_inf.currentIndex(),
            "add_spinbox.value": self.add_spinbox.value(),
            "scale_spinbox.value": self.scale_spinbox.value(),
            "set_spinbox.value": self.set_spinbox.value(),
            "auto_update_button.isChecked": self.auto_update_table_action.isChecked(),
            "show_all_button.isChecked": self.show_all_button.isChecked(),
            "auto_select_button.isChecked": self.auto_select_vertex_action.isChecked(),
            "auto_select_infs_button.isChecked": self.auto_select_infs_action.isChecked(),
            "hide_colors_button.isChecked": self.hide_colors_button.isChecked(),
            "toggle_view_button.isChecked": self.toggle_view_button.isChecked(),
            "show_utilities_button.isChecked": self.show_utilities_button.isChecked(),
            "show_add_button.isChecked": self.show_add_button.isChecked(),
            "show_scale_button.isChecked": self.show_scale_button.isChecked(),
            "show_set_button.isChecked": self.show_set_button.isChecked(),
            "show_inf_button.isChecked": self.show_inf_button.isChecked(),
            "weights_table.max_display_count": self.weights_table.table_model.max_display_count
        }

        hotkeys_data = {}
        for hotkey in self.hotkeys:
            hotkeys_data.update(hotkey.serialize())
        data["hotkeys"] = hotkeys_data

        OpenMaya.MGlobal.displayInfo("Saving settings to {0}".format(self.settings_path))
        
        with open(self.settings_path, "w") as f:
            f.write(json.dumps(data, indent=4, sort_keys=True))
    
    def restore_state(self):
        """
        Restores gui's last state if the file is available.
        """
        if not os.path.exists(self.settings_path):
            return
        
        with open(self.settings_path, "r") as f:
            data = json.loads(f.read())
        
        if "width" in data and "height" in data:
            self.resize(QtCore.QSize(data["width"], data["height"]))
        
        if "inf_dock_widget.area" in data:
            all_areas = {
                1: QtCore.Qt.LeftDockWidgetArea,
                2: QtCore.Qt.RightDockWidgetArea,
                4: QtCore.Qt.TopDockWidgetArea,
                8: QtCore.Qt.BottomDockWidgetArea}
            
            area = all_areas.get(data["inf_dock_widget.area"])
            if area is not None:
                self.addDockWidget(area, self.inf_dock_widget)
        
        if "color_style" in data:
            self.color_style = data["color_style"]
            for i, widget in enumerate([self.max_color_action, self.maya_color_action, self.softimage_color_action]):
                widget.setChecked(i == self.color_style)

        if "mirror_mode.currentIndex" in data:
            self.mirror_mode.setCurrentIndex(data["mirror_mode.currentIndex"])

        if "mirror_surface.currentIndex" in data:
            self.mirror_surface.setCurrentIndex(data["mirror_surface.currentIndex"])

        if "mirror_inf.currentIndex" in data:
            self.mirror_inf.setCurrentIndex(data["mirror_inf.currentIndex"])

        if "weights_table.max_display_count" in data:
            self.weights_table.table_model.max_display_count = data["weights_table.max_display_count"]

        spinboxes = {
            "prune_spinbox.value": self.prune_spinbox,
            "smooth_strength_spinbox.value": self.smooth_strength_spinbox,
            "add_spinbox.value": self.add_spinbox,
            "scale_spinbox.value": self.scale_spinbox,
            "set_spinbox.value": self.set_spinbox
        }

        for key, spinbox in spinboxes.items():
            if key in data:
                spinbox.setValue(data[key])

        checkboxes = {
            "auto_update_button.isChecked": self.auto_update_table_action,
            "show_all_button.isChecked": self.show_all_button,
            "auto_select_button.isChecked": self.auto_select_vertex_action,
            "auto_select_infs_button.isChecked": self.auto_select_infs_action,
            "hide_colors_button.isChecked": self.hide_colors_button,
            "toggle_view_button.isChecked": self.toggle_view_button,
            "show_utilities_button.isChecked": self.show_utilities_button,
            "show_add_button.isChecked": self.show_add_button,
            "show_scale_button.isChecked": self.show_scale_button,
            "show_set_button.isChecked": self.show_set_button,
            "show_inf_button.isChecked": self.show_inf_button
        }

        for key, checkbox in checkboxes.items():
            if key in data:
                checkbox.setChecked(data[key])

        self.auto_update_on_toggled()

        if "hotkeys" in data:
            for hotkey in self.hotkeys:
                if hotkey.caption in data["hotkeys"]:
                    values =  data["hotkeys"][hotkey.caption]
                    hotkey.ctrl = values["ctrl"]
                    hotkey.shift = values["shift"]
                    hotkey.alt = values["alt"]
                    hotkey.key = values["key"]
    
    def update_obj(self, obj):
        """
        Re-points tool to work on another object and re-collect its skin data.
        
        Args:
            obj(string): Object to re-point to.
        """
        weights_view = self.get_active_weights_view()
        weights_view.begin_update()
        
        last_obj = self.get_obj_by_name(self.obj)
        if last_obj is not None:
            self.hide_vert_colors(last_obj)
        
        # Reset values
        self.obj = obj
        self.skin_cluster = None
        self.skin_data = {}
        self.vert_count = None
        self.infs = []
        self.in_component_mode = utils.is_in_component_mode()
        
        # Reset undo stack.
        self.undo_stack.clear()
        self.set_undo_buttons_enabled_state()
        
        current_obj = self.get_obj_by_name(self.obj)
        
        # Collect new values
        if current_obj is not None:
            if utils.is_curve(current_obj):
                curve_degree = cmds.getAttr("{0}.degree".format(current_obj))
                curve_spans = cmds.getAttr("{0}.spans".format(current_obj))
                self.vert_count = curve_degree + curve_spans
            else:
                self.vert_count = cmds.polyEvaluate(current_obj, vertex=True)
            
            skin_cluster = utils.get_skin_cluster(obj)
            
            if skin_cluster:
                # Maya doesn't update this attribute if topology changes were done while it has a skinCluster.
                weights_count = len(cmds.getAttr("{0}.weightList[*]".format(skin_cluster)))
                
                if self.vert_count == weights_count:
                    self.skin_cluster = skin_cluster
                    
                    self.infs = self.get_all_infs()
                else:
                    msg = ("The mesh's vert count doesn't match the skin cluster's weight count!\n"
                           "This is likely because changes were done on the mesh with an enabled skinCluster.\n"
                           "\n"
                           "You may have to duplicate the mesh and use copy weights to fix it.")
                    utils.show_error_msg("Skin cluster error!", msg, self)
        
        self.update_inf_list()
        
        # Display values
        self.pick_obj_button.setText(self.obj or "Load object's skin data")
        
        self.recollect_table_data(load_selection=False)
        
        if current_obj is not None:
            if not self.hide_colors_button.isChecked() and self.in_component_mode:
                utils.switch_to_color_set(current_obj)
                self.update_vert_colors()
            else:
                self.hide_vert_colors(current_obj)

        weights_view.end_update()
    
    def collect_inf_locks(self):
        """
        Collects a list of bools from active influences.
        """
        self.locks = [
            cmds.getAttr("{0}.lockInfluenceWeights".format(inf_name))
            for inf_name in self.infs
        ]
    
    def toggle_inf_locks(self, infs, enabled):
        """
        Sets lock on influences by table's columns.
        
        Args:
            infs(string[]): A list of influence names to set.
            enabled(bool): Locks if True.
        """
        if enabled:
            description = "Lock influences"
        else:
            description = "Unlock influences"
        
        self.undo_stack.push(
            command_lock_infs.CommandLockInfs(
                self.__class__,
                description,
                infs,
                enabled))

        self.set_undo_buttons_enabled_state()
    
    def get_all_infs(self):
        """
        Gets and returns a list of all influences from the active skinCluster.
        """
        return sorted(
            cmds.skinCluster(self.skin_cluster, q=True, inf=True) or [])
    
    def get_selected_infs(self):
        """
        Gets and returns a list of influences that effects selected vertexes.
        """
        infs = set()
        
        for vert_index in self.vert_indexes:
            vert_infs = self.skin_data[vert_index]["weights"].keys()
            infs = infs.union(vert_infs)
        
        return sorted(list(infs))
    
    def collect_display_infs(self):
        """
        Sets influences to be shown in the table.
        """
        weights_view = self.get_active_weights_view()

        if self.show_all_button.isChecked():
            weights_view.set_display_infs(self.get_all_infs())
        else:
            weights_view.set_display_infs(self.get_selected_infs())
        
        self.collect_inf_locks()
    
    def recollect_table_data(
            self, update_skin_data=True, update_verts=True,
            update_infs=True, update_headers=True, load_selection=True):
        """
        Collects all necessary data to display the table and refreshes it.
        Optimize this method by setting some arguments to False.
        """
        # Ignore this event otherwise it slows down the tool by firing many times.
        self.ignore_cell_selection_event = True

        weights_view = self.get_active_weights_view()
        weights_view.begin_update()
        
        current_obj = self.get_obj_by_name(self.obj)
        if current_obj is None:
            return

        selection_data = None
        if load_selection:
            selection_data = weights_view.save_table_selection()
        
        if update_skin_data:
            if self.skin_cluster:
                self.skin_data = utils.get_skin_data(self.skin_cluster)
        
        if update_verts:
            self.vert_indexes = utils.get_vert_indexes(current_obj)
        
        if update_infs:
            self.collect_display_infs()
        
        if update_headers:
            if self.color_style == ColorTheme.Softimage:
                weights_view.color_headers()
            else:
                weights_view.reset_color_headers()

        weights_view.end_update()
        weights_view.emit_header_data_changed()
        
        if load_selection:
            if self.auto_select_infs_action.isChecked():
                weights_view.select_items_by_inf(self.color_inf)
            else:
                weights_view.load_table_selection(selection_data)

            weights_view.fit_headers_to_contents()
        
        self.ignore_cell_selection_event = False
    
    def edit_weights(self, input_value, mode):
        """
        Sets new weight value while distributing the difference.
        Using the mode argument determines how input_value will be implemented.
        
        Args:
            input_value(float): Value between 0 to 1.0.
            mode(enums.WeightOperation)
        """
        current_obj = self.get_obj_by_name(self.obj)
        if current_obj is None:
            return

        weights_view = self.get_active_weights_view()

        verts_and_infs = weights_view.get_selected_verts_and_infs()
        if not verts_and_infs:
            OpenMaya.MGlobal.displayWarning("Select cells inside the table to edit.")
            return

        sel_vert_indexes = set()
        new_skin_data = copy.deepcopy(self.skin_data)

        for vert_index, inf in verts_and_infs:
            weight_data = new_skin_data[vert_index]["weights"]
            old_value = weight_data.get(inf) or 0.0

            new_value = None

            if mode == WeightOperation.Absolute:
                # Ignore if value is almost the same as its old value
                new_value = input_value
                if utils.is_close(old_value, new_value):
                    continue
            elif mode == WeightOperation.Relative:
                new_value = utils.clamp(0.0, 1.0, old_value + input_value)
            elif mode == WeightOperation.Percentage:
                new_value = utils.clamp(0.0, 1.0, old_value * input_value)

            utils.update_weight_value(weight_data, inf, new_value)
            
            sel_vert_indexes.add(vert_index)
        
        if not sel_vert_indexes:
            return
        
        if mode == WeightOperation.Absolute:
            description = "Set weights"
        elif mode == WeightOperation.Relative:
            if input_value > 0:
                description = "Add weights"
            else:
                description = "Subtract weights"
        elif mode == WeightOperation.Percentage:
            description = "Scale weights"
        else:
            description = "Edit weights"
        
        self.add_undo_command(
            description,
            current_obj,
            copy.deepcopy(self.skin_data),
            new_skin_data,
            list(sel_vert_indexes),
            weights_view.save_table_selection())

    def hide_vert_colors(self, obj=None):
        if obj is None:
            obj = self.obj

        current_obj = self.get_obj_by_name(obj)
        if not current_obj:
            return

        utils.toggle_display_colors(current_obj, False)
        utils.delete_temp_inputs(current_obj)

    def update_vert_colors(self, vert_filter=[]):
        """
        Displays active influence.
        
        Args:
            vert_filter(int[]): List of vertex indexes to only operate on.
        """
        if self.hide_colors_button.isChecked():
            return

        current_obj = self.get_obj_by_name(self.obj)
        if current_obj is not None:
            if utils.is_curve(current_obj):
                return
        
        if not self.infs:
            return

        if self.color_inf is None:
            weights_view = self.get_active_weights_view()
            display_infs = weights_view.display_infs()

            if display_infs:
                self.set_color_inf(display_infs[0])
            else:
                self.set_color_inf(self.infs[0])
        
        if self.color_style == ColorTheme.Softimage:
            self.set_color_inf(None)
            self.inf_colors = utils.display_multi_color_influence(
                current_obj,
                self.skin_cluster,
                self.skin_data,
                vert_filter=vert_filter)
        else:
            if self.color_inf is not None:
                utils.display_influence(
                    current_obj,
                    self.skin_data,
                    self.color_inf,
                    color_style=self.color_style,
                    vert_filter=vert_filter)

        utils.toggle_display_colors(current_obj, True)
    
    def switch_color_style(self, color_theme):
        """
        Changes color display to a different theme.
        
        Args:
            color_theme(enums.ColorTheme)
        """
        self.color_style = color_theme

        if utils.is_in_component_mode():
            self.update_vert_colors()

        self.recollect_table_data(
            update_skin_data=False,
            update_verts=False,
            update_infs=False,
            load_selection=False)

    def run_smooth(self, smooth_operation):
        """
        Smooths weights on selected vertexes with adjacent weights.

        Args:
            smooth_operation(SmoothOperation)
        """
        current_obj = self.get_obj_by_name(self.obj)
        if current_obj is None:
            OpenMaya.MGlobal.displayWarning("No object to operate on.")
            return

        selected_vertexes = utils.get_vert_indexes(current_obj)
        if not selected_vertexes:
            OpenMaya.MGlobal.displayWarning("No vertexes are selected.")
            return

        old_skin_data = copy.deepcopy(WeightsEditor.instance.skin_data)

        weights_view = self.get_active_weights_view()
        table_selection = weights_view.save_table_selection()

        sel_vert_indexes = utils.get_vert_indexes(current_obj)

        if smooth_operation == SmoothOperation.Normal:
            utils.smooth_weights(
                current_obj,
                selected_vertexes,
                self.skin_data,
                self.smooth_strength_spinbox.value())

            self.recollect_table_data(update_skin_data=False, update_verts=False)

            undo_caption = "Smooth weights"
        else:
            # Re-collects all data since this smooth doesn't change internal data.
            utils.br_smooth_verts(self.smooth_strength_spinbox.value(), True)
            self.recollect_table_data()
            undo_caption = "Smooth weights (all influences)"

        self.update_vert_colors(vert_filter=selected_vertexes)

        new_skin_data = copy.deepcopy(WeightsEditor.instance.skin_data)

        self.add_undo_command(
            undo_caption,
            current_obj,
            old_skin_data,
            new_skin_data,
            sel_vert_indexes,
            table_selection,
            skip_first_redo=True)
    
    def add_undo_command(
            self, description, obj, old_skin_data, new_skin_data, vert_indexes,
            table_selection, skip_first_redo=False):

        self.undo_stack.push(
            command_edit_weights.CommandEditWeights(
                self.__class__,
                description,
                obj,
                old_skin_data,
                new_skin_data,
                vert_indexes,
                table_selection,
                skip_first_redo=skip_first_redo))

        self.set_undo_buttons_enabled_state()
    
    def set_color_inf(self, inf):
        weights_view = self.get_active_weights_view()
        weights_view.begin_update()
        self.inf_list.begin_update()
        
        self.color_inf = inf
        
        self.inf_list.end_update()
        weights_view.end_update()
    
    def update_inf_list(self):
        self.inf_list.begin_update()
        
        self.inf_list.list_model.clear()
        
        for i, inf in enumerate(sorted(self.infs)):
            item = QtGui.QStandardItem(inf)
            item.setToolTip(inf)
            item.setSizeHint(QtCore.QSize(1, 30))
            self.inf_list.list_model.appendRow(item)
        
        self.apply_filter_to_inf_list()
        
        self.inf_list.end_update()
    
    def apply_filter_to_inf_list(self):
        self.inf_list.apply_filter("*" + self.inf_filter_edit.text() + "*")

    def mirror_weights(self, selection_only):
        current_obj = self.get_obj_by_name(self.obj)
        if current_obj is None:
            return

        old_skin_data = copy.deepcopy(WeightsEditor.instance.skin_data)

        weights_view = self.get_active_weights_view()
        table_selection = weights_view.save_table_selection()

        vert_indexes = utils.get_vert_indexes(current_obj, selection=selection_only)
        vert_components = cmds.ls("{0}.vtx[*]".format(current_obj), sl=selection_only, fl=True)

        mirror_mode = self.mirror_mode.currentText().lstrip("-")
        mirror_inverse = self.mirror_mode.currentText().startswith("-")

        surface_options = {
            "Closest Point": "closestPoint",
            "Ray Cast": "rayCast",
            "Closest Component": "closestComponent"
        }

        surface_association = surface_options[self.mirror_surface.currentText()]

        inf_options = {
            "Label": "label",
            "Closest Point": "closestJoint",
            "Closest Bone": "closestBone",
            "Name": "name",
            "One To One": "oneToOne"
        }

        inf_association = inf_options[self.mirror_inf.currentText()]

        utils.mirror_skin_weights(
            vert_components,
            mirror_mode,
            mirror_inverse,
            surface_association,
            inf_association)

        self.recollect_table_data(update_verts=False)

        vert_filter = vert_indexes if selection_only else []
        self.update_vert_colors(vert_filter=vert_filter)

        new_skin_data = copy.deepcopy(WeightsEditor.instance.skin_data)

        self.add_undo_command(
            "Mirror weights",
            current_obj,
            old_skin_data,
            new_skin_data,
            vert_indexes,
            table_selection,
            skip_first_redo=True)

    def grow_selection(self):
        mel.eval("PolySelectTraverse 1;")

    def shrink_selection(self):
        mel.eval("PolySelectTraverse 2;")

    def select_perimeter(self):
        mel.eval("ConvertSelectionToVertexPerimeter;")

    def select_edge_loop(self):
        mel.eval("SelectEdgeLoopSp;")

    def select_shell(self):
        mel.eval("polyConvertToShell;")

    def select_ring_loop(self):
        mel.eval("ConvertSelectionToContainedEdges;")
        mel.eval("SelectEdgeRingSp;")
        mel.eval("ConvertSelectionToVertices;")

    def toggle_selected_inf_locks(self):
        weights_view = self.get_active_weights_view()

        infs = list(
            set(
                inf
                for _, inf in weights_view.get_selected_verts_and_infs()
            )
        )

        if infs:
            inf_index = self.infs.index(infs[-1])
            do_lock = not self.locks[inf_index]
            self.toggle_inf_locks(infs, do_lock)

#
# Callbacks
#
    
    def selection_on_changed(self, *args):
        """
        Triggers when user selects a new vertex in the viewport.
        Then refreshes table to be in sync.
        """
        # Check if the current object is valid.
        current_obj = self.get_obj_by_name(self.obj)
        current_skin_cluster = self.get_obj_by_name(self.skin_cluster)

        if current_obj is not None and current_skin_cluster is not None:
            # Toggle influence colors if component selection mode changes.
            now_in_component_mode = utils.is_in_component_mode()

            # No point to adjust colors if it's already disabled.
            if not self.hide_colors_button.isChecked():
                if now_in_component_mode != self.in_component_mode:  # Only continue if component mode was switched.
                    if now_in_component_mode:
                        self.update_vert_colors()
                    else:
                        self.hide_vert_colors(current_obj)

            self.in_component_mode = now_in_component_mode
            
            # Update table's data.
            if not self.block_selection_cb:
                self.recollect_table_data(update_skin_data=False)
    
    def add_selection_callback(self):
        if self.cb_selection_changed is None:
            self.cb_selection_changed = OpenMaya.MEventMessage.addEventCallback(
                "SelectionChanged", self.selection_on_changed)
    
    def remove_selection_callback(self):
        if self.cb_selection_changed is not None:
            OpenMaya.MEventMessage.removeCallback(self.cb_selection_changed)
            self.cb_selection_changed = None
    
#
# Events
#
    
    def closeEvent(self, *args):
        try:
            self.save_state()

            current_obj = self.get_obj_by_name(self.obj)
            if current_obj is not None:
                utils.toggle_display_colors(current_obj, False)
                utils.delete_temp_inputs(current_obj)
        finally:
            self.remove_selection_callback()
            self.remove_shortcuts()
            self.del_prev_instance()
    
    def pick_obj_on_clicked(self):
        obj = utils.get_selected_mesh()
        self.update_obj(obj)

    def table_on_update_ended(self, over_limit):
        if self.limit_warning_label.isVisible() != over_limit:
            if over_limit:
                max_count = self.weights_table.table_model.max_display_count
                self.limit_warning_label.setText(
                    "Can only display {} rows! Go to settings to increase the limit.".format(max_count))
            self.limit_warning_label.setVisible(over_limit)

    def weights_view_on_key_pressed(self, key_event):
        if key_event.key() == QtCore.Qt.Key_Space:
            self.toggle_selected_inf_locks()
    
    def refresh_on_clicked(self):
        self.recollect_table_data()
    
    def auto_update_on_toggled(self):
        enable_cb = self.auto_update_table_action.isChecked()
        
        if enable_cb:
            self.add_selection_callback()
        else:
            self.remove_selection_callback()

    def set_limit_on_triggered(self):
        dialog = QtWidgets.QInputDialog(parent=self)
        dialog.setInputMode(QtWidgets.QInputDialog.IntInput)
        dialog.setIntRange(0, 99999)
        dialog.setIntValue(self.weights_table.table_model.max_display_count)
        dialog.setWindowTitle("Enter max row limit")
        dialog.setLabelText(
            "To help prevent the tool to freeze\n"
            "when selecting a large number of vertexes,\n"
            "a limit can be put in place. (table view only)\n")
        dialog.exec_()

        if dialog.result() == QtWidgets.QDialog.Accepted:
            self.weights_table.begin_update()
            self.weights_table.table_model.max_display_count = dialog.intValue()
            self.weights_table.end_update()

    def header_on_middle_clicked(self, inf):
        """
        Sets active influence to color with.
        """
        if self.color_style == ColorTheme.Softimage:
            return

        self.inf_list.select_item(inf)
        self.set_color_inf(inf)
        self.update_vert_colors()
        self.recollect_table_data(
            update_skin_data=False,
            update_verts=False,
            update_infs=False,
            load_selection=False)

    def select_by_infs_on_clicked(self):
        current_obj = self.get_obj_by_name(self.obj)
        if current_obj is None:
            OpenMaya.MGlobal.displayError("The current object isn't set to anything.")
            return
        
        sel_indexes = self.inf_list.selectedIndexes()
        if not sel_indexes:
            OpenMaya.MGlobal.displayError("There are no influences selected.")
            return
        
        infs = []
        
        for index in sel_indexes:
            inf_name = self.inf_list.list_model.itemFromIndex(index).text()
            
            if not cmds.objExists(inf_name):
                OpenMaya.MGlobal.displayError("Unable to find influence '{0}' in the scene. Is the list out of sync?".format(inf_name))
                return
            
            infs.append(inf_name)
        
        utils.select_inf_vertexes(current_obj, infs, self.skin_data)
    
    def prune_on_clicked(self):
        current_obj = self.get_obj_by_name(self.obj)
        if current_obj is None:
            return
        
        old_skin_data = copy.deepcopy(WeightsEditor.instance.skin_data)

        weights_view = self.get_active_weights_view()
        table_selection = weights_view.save_table_selection()
        
        sel_vert_indexes = utils.get_vert_indexes(current_obj)
        
        is_pruned = utils.prune_weights(current_obj, self.skin_cluster, self.prune_spinbox.value())
        if not is_pruned:
            return
        
        self.recollect_table_data(update_verts=False)
        
        self.update_vert_colors(vert_filter=sel_vert_indexes)
        
        new_skin_data = copy.deepcopy(WeightsEditor.instance.skin_data)
        
        self.add_undo_command(
            "Prune weights",
            current_obj,
            old_skin_data,
            new_skin_data,
            sel_vert_indexes,
            table_selection,
            skip_first_redo=True)

    def mirror_skin_on_clicked(self):
        self.mirror_weights(True)

    def mirror_all_skin_on_clicked(self):
        self.mirror_weights(False)

    def copy_vertex_on_clicked(self):
        current_obj = self.get_obj_by_name(self.obj)
        if not current_obj:
            return

        vert_indexes = utils.get_vert_indexes(current_obj)
        if not vert_indexes:
            OpenMaya.MGlobal.displayError("Need a vertex to be selected.")
            return

        vert_index = vert_indexes[0]
        self.copied_vertex = copy.deepcopy(self.skin_data[vert_index])
        OpenMaya.MGlobal.displayInfo("Copied vertex {}".format(vert_index))

    def paste_vertex_on_clicked(self):
        if self.copied_vertex is None:
            OpenMaya.MGlobal.displayError("Need to copy a vertex first.")
            return

        current_obj = self.get_obj_by_name(self.obj)
        if not current_obj:
            return

        vert_indexes = utils.get_vert_indexes(current_obj)
        if not vert_indexes:
            return

        weights_view = self.get_active_weights_view()
        table_selection = weights_view.save_table_selection()
        old_skin_data = copy.deepcopy(WeightsEditor.instance.skin_data)
        new_skin_data = copy.deepcopy(WeightsEditor.instance.skin_data)
        
        for vert_index in vert_indexes:
            new_skin_data[vert_index] = copy.deepcopy(self.copied_vertex)
        
        self.add_undo_command(
            "Paste vertex",
            current_obj,
            old_skin_data,
            new_skin_data,
            vert_indexes,
            table_selection)

    def set_add_on_clicked(self):
        self.edit_weights(self.add_spinbox.value(), WeightOperation.Relative)
    
    def add_preset_on_clicked(self, value):
        self.add_spinbox.setValue(value)
        self.set_add_on_clicked()
    
    def set_scale_on_clicked(self):
        perc = self.scale_spinbox.value()
        multiplier = utils.remap_range(-100.0, 100.0, 0.0, 2.0, perc)
        self.edit_weights(multiplier, WeightOperation.Percentage)
    
    def scale_preset_on_clicked(self, perc):
        self.scale_spinbox.setValue(perc)
        self.set_scale_on_clicked()
    
    def set_on_clicked(self):
        self.edit_weights(self.set_spinbox.value(), WeightOperation.Absolute)
    
    def set_preset_on_clicked(self, value):
        self.set_spinbox.setValue(value)
        self.set_on_clicked()

    def hide_colors_on_toggled(self, checked):
        current_obj = self.get_obj_by_name(self.obj)
        if current_obj is not None and self.in_component_mode:
            self.update_vert_colors()
            utils.toggle_display_colors(current_obj, not checked)

    def flood_to_closest_on_clicked(self):
        current_obj = self.get_obj_by_name(self.obj)
        if current_obj is None:
            return

        if not self.skin_cluster:
            return

        old_skin_data = copy.deepcopy(WeightsEditor.instance.skin_data)

        weights_view = self.get_active_weights_view()
        table_selection = weights_view.save_table_selection()

        vert_indexes = utils.get_vert_indexes(current_obj, selection=False)

        utils.flood_weights_to_closest(current_obj, self.skin_cluster)

        self.recollect_table_data(update_verts=False)

        self.update_vert_colors()

        new_skin_data = copy.deepcopy(WeightsEditor.instance.skin_data)

        self.add_undo_command(
            "Flood weights to closest",
            current_obj,
            old_skin_data,
            new_skin_data,
            vert_indexes,
            table_selection,
            skip_first_redo=True)

    def switch_color_on_clicked(self, index):
        self.max_color_action.setChecked(index == ColorTheme.Max)
        self.maya_color_action.setChecked(index == ColorTheme.Maya)
        self.softimage_color_action.setChecked(index == ColorTheme.Softimage)
        self.switch_color_style(index)

    def launch_hotkeys_on_clicked(self):
        status, dialog = hotkeys_dialog.HotkeysDialog.launch(self.hotkeys, self)
        if status:
            self.hotkeys = dialog.serialize()
            self.register_shortcuts()
        dialog.deleteLater()

    def about_on_triggered(self):
        dialog = about_dialog.AboutDialog.launch(self.version, self)
        dialog.deleteLater()

    def toggle_view_on_toggled(self, enabled):
        self.limit_warning_label.setVisible(False)
        self.weights_list.setVisible(not enabled)
        self.weights_table.setVisible(enabled)

        if enabled:
            self.toggle_view_button.setText("TABLE")
        else:
            self.toggle_view_button.setText("LIST")

        self.refresh_on_clicked()

    def show_utilities_on_toggled(self, enabled):
        self.weight_groupbox.setVisible(enabled)

    def show_add_on_toggled(self, enabled):
        self.add_groupbox.setVisible(enabled)

    def show_scale_on_toggled(self, enabled):
        self.scale_groupbox.setVisible(enabled)

    def show_set_on_toggled(self, enabled):
        self.set_groupbox.setVisible(enabled)

    def show_inf_on_toggled(self, enabled):
        self.inf_dock_widget.setVisible(enabled)
    
    def undo_on_click(self):
        if not self.undo_stack.canUndo():
            OpenMaya.MGlobal.displayError("There are no more commands to undo.")
            return
        
        self.undo_stack.undo()
        self.set_undo_buttons_enabled_state()
    
    def redo_on_click(self):
        if not self.undo_stack.canRedo():
            OpenMaya.MGlobal.displayError("There are no more commands to redo.")
            return
        
        self.undo_stack.redo()
        self.set_undo_buttons_enabled_state()
    
    def inf_list_on_middle_clicked(self, inf):
        if inf in self.infs:
            self.set_color_inf(inf)
            self.update_vert_colors()

    def inf_list_on_toggle_lock_triggered(self, infs):
        if infs[0] not in self.infs:
            OpenMaya.MGlobal.displayError(
                "Unable to find influence in internal data.. Is it out of sync?")
            return

        inf_index = self.infs.index(infs[0])
        do_lock = not self.locks[inf_index]
        self.toggle_inf_locks(infs, do_lock)
    
    def add_inf_to_vert_on_clicked(self):
        """
        Adds a very small weight value from selected influences to selected vertexes.
        """
        current_obj = self.get_obj_by_name(self.obj)
        if current_obj is None:
            OpenMaya.MGlobal.displayError("There's no active object to work on.")
            return
        
        sel_vert_indexes = utils.get_vert_indexes(current_obj)
        if not sel_vert_indexes:
            OpenMaya.MGlobal.displayError("There's no selected vertexes to set on.")
            return
        
        # Collect selected influence names.
        sel_infs = []
        
        for index in self.inf_list.selectedIndexes():
            if not index.isValid():
                continue
            
            item = self.inf_list.list_model.itemFromIndex(index)
            
            inf_name = item.text()
            if inf_name not in self.infs:
                continue
            
            sel_infs.append(inf_name)
        
        if not sel_infs:
            OpenMaya.MGlobal.displayError("Nothing is selected in the influence list.")
            return
        
        old_skin_data = copy.deepcopy(WeightsEditor.instance.skin_data)
        new_skin_data = copy.deepcopy(WeightsEditor.instance.skin_data)

        weights_view = self.get_active_weights_view()
        table_selection = weights_view.save_table_selection()
        
        # Add infs by setting a very low value so it doesn't effect other weights too much.
        for inf in sel_infs:
            for vert_index in sel_vert_indexes:
                weight_data = new_skin_data[vert_index]["weights"]
                
                # No need to change it if it's already weighted to the vert.
                if weight_data.get(inf) is not None:
                    continue
                
                utils.update_weight_value(weight_data, inf, 0.001)
        
        self.add_undo_command(
            "Add influence to verts",
            current_obj,
            old_skin_data,
            new_skin_data,
            sel_vert_indexes,
            table_selection)
        
        self.recollect_table_data(update_skin_data=False, update_verts=False)
    
#
# Context menu events
#

    def display_inf_on_triggered(self, inf):
        if self.color_style == ColorTheme.Softimage:
            return

        self.set_color_inf(inf)
        self.update_vert_colors()

        self.recollect_table_data(
            update_skin_data=False,
            update_verts=False,
            update_infs=False,
            load_selection=False)

    def select_inf_verts_on_triggered(self, inf):
        current_obj = self.get_obj_by_name(self.obj)
        if current_obj is not None:
            utils.select_inf_vertexes(current_obj, [inf], self.skin_data)


def run():
    WeightsEditor.run()
