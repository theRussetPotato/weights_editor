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

TODO:
    - Implement private accessors
"""

import os
import copy
import json
import traceback
import shiboken2
import webbrowser
from functools import partial

from maya import cmds
from maya import mel
from maya import OpenMaya

from PySide2 import QtGui
from PySide2 import QtCore
from PySide2 import QtWidgets
from PySide2 import QtNetwork

from weights_editor_tool import constants
from weights_editor_tool.enums import ColorTheme, WeightOperation, SmoothOperation
from weights_editor_tool import weights_editor_utils as utils
from weights_editor_tool.classes.skinned_obj import SkinnedObj
from weights_editor_tool.classes import hotkey as hotkey_module
from weights_editor_tool.classes import command_edit_weights
from weights_editor_tool.classes import command_lock_infs
from weights_editor_tool.widgets import custom_double_spinbox
from weights_editor_tool.widgets import inf_list_view
from weights_editor_tool.widgets import weights_list_view
from weights_editor_tool.widgets import weights_table_view
from weights_editor_tool.widgets import hotkeys_dialog
from weights_editor_tool.widgets import presets_dialog
from weights_editor_tool.widgets import about_dialog


class WeightsEditor(QtWidgets.QMainWindow):

    version = "2.2.0"
    instance = None
    cb_selection_changed = None
    shortcuts = []

    def __init__(self, parent=None):
        QtWidgets.QMainWindow.__init__(self, parent=parent)

        self.del_prev_instance()
        self.__class__.instance = self

        self.setWindowIcon(utils.load_pixmap("interface/icon.png"))

        self.maya_main_window = utils.get_maya_window()
        self.setParent(self.maya_main_window)
        self.setWindowFlags(QtCore.Qt.Window)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.setObjectName("weightsEditor")
        
        self.undo_stack = QtWidgets.QUndoStack(parent=self)
        self.undo_stack.setUndoLimit(30)

        self.obj = SkinnedObj.create_empty()
        self.color_inf = None
        self.copied_vertex = None
        self.vert_indexes = []
        self.infs = []
        self.locks = []
        self.inf_colors = {}
        self.color_style = ColorTheme.Max
        self.block_selection_cb = False
        self.ignore_cell_selection_event = False
        self.allow_to_fetch_update = True
        self.in_component_mode = utils.is_in_component_mode()
        self.settings_path = os.path.join(os.getenv("HOME"), "maya", "weights_editor.json")
        self.add_preset_values = presets_dialog.PresetsDialog.Defaults["add"]
        self.scale_preset_values = presets_dialog.PresetsDialog.Defaults["scale"]
        self.set_preset_values = presets_dialog.PresetsDialog.Defaults["set"]

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

        if self.allow_to_fetch_update and self.update_on_open_action.isChecked():
            try:
                self.fetch_latest_tool_version()
            except Exception as err:
                print(traceback.format_exc())
                cmds.warning("Could not get version from GitHub: {e}".format(e=err))

    @classmethod
    def run(cls):
        inst = cls()
        inst.show()
        inst.pick_obj_on_clicked()
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

        icon_size = QtCore.QSize(13, 13)

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
            
            #updateFrame {{
                background-color: rgb(50, 180, 50);
                padding: 0px;
                margin: 0;
            }}
            
            #updateLabel {{
                font-weight: bold;
                color: white;
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

        self.color_separator = QtWidgets.QAction("[ Settings ]", self)
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

        self.hide_long_names_action = QtWidgets.QAction("Hide long names", self)
        self.hide_long_names_action.setCheckable(True)
        self.hide_long_names_action.setChecked(True)
        self.hide_long_names_action.toggled.connect(self.hide_long_names_on_triggered)
        self.options_menu.addAction(self.hide_long_names_action)

        self.update_on_open_action = QtWidgets.QAction("Check for updates on open", self)
        self.update_on_open_action.setCheckable(True)
        self.update_on_open_action.setChecked(True)
        self.options_menu.addAction(self.update_on_open_action)

        self.visibility_separator = QtWidgets.QAction("Visibility settings", self)
        self.visibility_separator.setSeparator(True)
        self.options_menu.addAction(self.visibility_separator)

        self.launch_hotkeys_action = QtWidgets.QAction("Edit hotkeys", self)
        self.launch_hotkeys_action.triggered.connect(self.launch_hotkeys_on_clicked)

        self.launch_presets_action = QtWidgets.QAction("Edit preset buttons", self)
        self.launch_presets_action.triggered.connect(self.launch_presets_on_clicked)

        self.prefs_menu = self.menu_bar.addMenu("&Preferences")
        self.prefs_menu.addAction(self.launch_hotkeys_action)
        self.prefs_menu.addAction(self.launch_presets_action)

        self.about_action = QtWidgets.QAction("About this tool", self)
        self.about_action.triggered.connect(self.about_on_triggered)

        self.github_page_action = QtWidgets.QAction("Github page", self)
        self.github_page_action.triggered.connect(self.github_page_on_triggered)

        self.about_menu = self.menu_bar.addMenu("&About")
        self.about_menu.addAction(self.about_action)
        self.about_menu.addAction(self.github_page_action)

    #
    # CENTRAL WIDGET
    #

        self.central_widget = QtWidgets.QWidget(parent=self)
        self.central_widget.setObjectName("weightsEditorCentralWidget")

        self.toggle_view_button = self.create_button("TABLE", "interface/table.png")
        self.show_utilities_button = self.create_button("UTL", "interface/utils.png")
        self.show_add_button = self.create_button("ADD", "interface/add.png")
        self.show_scale_button = self.create_button("SCA", "interface/percent.png")
        self.show_set_button = self.create_button("SET", "interface/equal.png")
        self.show_inf_button = self.create_button("INF", "interface/inf.png")

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

        self.refresh_button = self.create_button(
            "", "interface/refresh.png",
            tool_tip="Refreshes the skin's data.",
            icon_size=QtCore.QSize(22, 22),
            click_event=self.refresh_on_clicked)
        self.refresh_button.setMinimumWidth(18)
        self.refresh_button.setFixedHeight(24)
        self.refresh_button.setFlat(True)

        self.pick_obj_layout = utils.wrap_layout(
            [self.pick_obj_label,
             self.pick_obj_button,
             self.refresh_button,
             3,
             "stretch",
             self.show_layout],
             QtCore.Qt.Horizontal,
             margins=[5, 5, 5, 5])

        self.prune_spinbox = QtWidgets.QDoubleSpinBox(value=0.1, parent=self.central_widget)
        self.prune_spinbox.setToolTip("Prune any influence below this value.")
        self.prune_spinbox.setMinimumWidth(60)
        self.prune_spinbox.setDecimals(3)
        self.prune_spinbox.setMinimum(0.001)
        self.prune_spinbox.setSingleStep(0.01)

        self.prune_button = self.create_button(
            "Prune", "interface/prune.png",
            click_event=self.prune_on_clicked)

        self.prune_layout = utils.wrap_layout(
            [self.prune_spinbox,
             self.prune_button,
             "stretch"],
            QtCore.Qt.Horizontal)

        self.smooth_strength_spinbox = QtWidgets.QDoubleSpinBox(value=1, parent=self.central_widget)
        self.smooth_strength_spinbox.setToolTip("Smooth's strength.")
        self.smooth_strength_spinbox.setMinimumWidth(60)
        self.smooth_strength_spinbox.setDecimals(2)
        self.smooth_strength_spinbox.setMinimum(0)
        self.smooth_strength_spinbox.setMaximum(1)
        self.smooth_strength_spinbox.setSingleStep(0.1)

        self.smooth_button = self.create_button(
            "Smooth (vert's infs)", "interface/smooth.png",
            click_event=partial(self.run_smooth, SmoothOperation.Normal))

        self.smooth_br_button = self.create_button(
            "Smooth (all infs)", "interface/smooth.png",
            click_event=partial(self.run_smooth, SmoothOperation.AllInfluences))

        if not hasattr(cmds, "brSmoothWeightsContext"):
            self.smooth_br_button.setEnabled(False)

        self.smooth_layout = utils.wrap_layout(
            [self.smooth_strength_spinbox,
             self.smooth_button,
             self.smooth_br_button,
             "stretch"],
            QtCore.Qt.Horizontal)

        self.mirror_skin_button = self.create_button(
            "Mirror", "interface/mirror.png",
            tool_tip="Mirror weights on selected vertexes only",
            click_event=self.mirror_skin_on_clicked)

        self.mirror_all_skin_button = self.create_button(
            "Mirror all", "interface/mirror.png",
            click_event=self.mirror_all_skin_on_clicked)

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

        self.copy_vertex_button = self.create_button(
            "Copy vertex", "interface/copy.png",
            tool_tip="Copy weights on first selected vertex",
            click_event=self.copy_vertex_on_clicked)

        self.paste_vertex_button = self.create_button(
            "Paste vertex", "interface/paste.png",
            tool_tip="Paste weights on selected vertexes",
            click_event=self.paste_vertex_on_clicked)

        self.copy_vert_layout = utils.wrap_layout(
            [self.copy_vertex_button,
             self.paste_vertex_button,
             "stretch"],
            QtCore.Qt.Horizontal)

        self.weight_layout = utils.wrap_layout(
            [self.prune_layout,
             self.smooth_layout,
             self.mirror_layout,
             self.copy_vert_layout],
            QtCore.Qt.Vertical,
            margins=[0, 0, 0, 0],
            spacing=5)

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
            self.create_preset_layout(
                -1, 1, 0.1,
                self.set_add_on_clicked,
                "Add / subtract weight")

        self.scale_layout, self.scale_groupbox, self.scale_spinbox = \
            self.create_preset_layout(
                -100, 100, 1,
                self.set_scale_on_clicked,
                "Scale weight",
                suffix="%")

        self.set_layout, self.set_groupbox, self.set_spinbox = \
            self.create_preset_layout(
                0, 1, 0.1,
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

        self.show_all_button = self.create_button(
            "Show all influences", "interface/show.png",
            tool_tip="Forces the table to show all influences.",
            click_event=self.selection_on_changed)
        self.show_all_button.setCheckable(True)

        self.hide_colors_button = self.create_button(
            "Hide influence colors", "interface/hide.png")
        self.hide_colors_button.setCheckable(True)
        self.hide_colors_button.toggled.connect(self.hide_colors_on_toggled)

        self.flood_to_closest_button = self.create_button(
            "Flood to closest", "interface/flood.png",
            tool_tip="Set full weights to the closest joints for easier blocking.",
            click_event=self.flood_to_closest_on_clicked)

        self.settings_layout = utils.wrap_layout(
            [self.show_all_button,
             self.hide_colors_button,
             self.flood_to_closest_button],
            QtCore.Qt.Horizontal)

        # Undo buttons
        self.undo_button = self.create_button(
            "Undo", "interface/undo.png",
            click_event=self.undo_on_click)
        self.undo_button.setFixedHeight(40)

        self.redo_button = self.create_button(
            "Redo", "interface/redo.png",
            click_event=self.redo_on_click)
        self.redo_button.setFixedHeight(40)

        self.undo_layout = utils.wrap_layout(
            [self.undo_button,
             self.redo_button],
            QtCore.Qt.Horizontal)

        widgets = [
            self.show_all_button, self.hide_colors_button,
            self.flood_to_closest_button, self.undo_button]
        for button in widgets:
            button.setMinimumWidth(10)

        self.update_label = QtWidgets.QLabel(parent=self.central_widget)
        self.update_label.setObjectName("updateLabel")
        self.update_label.setOpenExternalLinks(True)

        self.update_layout = utils.wrap_layout(
            [self.update_label],
            QtCore.Qt.Horizontal,
            margins=[3, 0, 3, 0])

        self.update_frame = QtWidgets.QFrame(parent=self.central_widget)
        self.update_frame.setObjectName("updateFrame")
        self.update_frame.setLayout(self.update_layout)
        self.update_frame.hide()

        self.main_layout = utils.wrap_layout(
            [self.update_frame,
             self.pick_obj_layout,
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
        self.inf_filter_edit.textChanged.connect(self.apply_filter_to_inf_list)

        self.inf_list = inf_list_view.InfListView(self, parent=self.inf_widget)
        self.inf_list.middle_clicked.connect(self.inf_list_on_middle_clicked)
        self.inf_list.toggle_locks_triggered.connect(self.inf_list_on_toggle_locks_triggered)
        self.inf_list.set_locks_triggered.connect(self.toggle_inf_locks)
        self.inf_list.select_inf_verts_triggered.connect(self.select_by_infs_on_clicked)
        self.inf_list.add_infs_to_verts_triggered.connect(self.add_inf_to_vert_on_clicked)

        self.add_inf_to_vert_button = QtWidgets.QPushButton("Add inf to verts", parent=self.inf_widget)
        self.add_inf_to_vert_button.setIconSize(icon_size)
        self.add_inf_to_vert_button.setIcon(utils.load_pixmap("interface/add_inf.png"))
        self.add_inf_to_vert_button.setToolTip("Adds the selected influence to all selected vertexes.")
        self.add_inf_to_vert_button.clicked.connect(self.add_inf_to_vert_on_clicked)

        self.select_by_infs_button = QtWidgets.QPushButton("Select influence's verts", parent=self.inf_widget)
        self.select_by_infs_button.setIconSize(icon_size)
        self.select_by_infs_button.setIcon(utils.load_pixmap("interface/select.png"))
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
        self.update_window_title()
        self.resize(1200, 1000)

#
# Custom functions
#

    def update_window_title(self):
        title = "Weights Editor v{ver}".format(ver=self.version)
        if self.obj.is_valid():
            title += " - {obj}".format(obj=self.obj.short_name())
        self.setWindowTitle(title)

    def get_active_weights_view(self):
        if self.toggle_view_button.isChecked():
            return self.weights_table
        else:
            return self.weights_list

    def create_button(self, caption, img_name, icon_size=QtCore.QSize(13, 13), tool_tip=None, click_event=None, parent=None):
        if parent is None:
            parent = self.central_widget

        button = QtWidgets.QPushButton(caption, parent=parent)
        button.setIconSize(icon_size)
        button.setIcon(utils.load_pixmap(img_name))

        if tool_tip is not None:
            button.setToolTip(tool_tip)

        if click_event is not None:
            button.clicked.connect(click_event)

        return button

    def create_preset_layout(self, spinbox_min, spinbox_max, spinbox_steps, spinbox_callback, caption, suffix=""):
        spinbox = custom_double_spinbox.CustomDoubleSpinbox(parent=self.central_widget)
        spinbox.setToolTip("Click spinbox and press enter to apply its value")
        spinbox.setFixedWidth(80)
        spinbox.setFixedHeight(25)
        spinbox.setSuffix(suffix)
        spinbox.setSingleStep(spinbox_steps)
        spinbox.setMinimum(spinbox_min)
        spinbox.setMaximum(spinbox_max)
        spinbox.enter_pressed.connect(spinbox_callback)

        layout = utils.wrap_layout(
            [spinbox],
            QtCore.Qt.Horizontal,
            margins=[5, 3, 1, 3])
        layout.setAlignment(QtCore.Qt.AlignLeft)

        groupbox = QtWidgets.QGroupBox(caption, parent=self.central_widget)
        groupbox.setLayout(layout)

        return layout, groupbox, spinbox

    def append_preset_buttons(self, values, layout, preset_callback, tooltip, suffix=""):
        """
        Procedurally creates multiple preset buttons to adjust weights.
        """
        for i in range(layout.count() - 1):
            old_button = layout.takeAt(1).widget()
            old_button.deleteLater()

        for value in values:
            text = "".join([str(value), suffix])
            preset_button = QtWidgets.QPushButton(text, parent=self.central_widget)
            preset_button.setMaximumWidth(60)
            preset_button.setSizePolicy(
                QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
            preset_button.clicked.connect(partial(preset_callback, value))
            preset_button.setToolTip("{0} by {1}".format(tooltip, text))

            if value > 0:
                preset_button.setObjectName("presetPositiveButton")
            else:
                preset_button.setObjectName("presetNegativeButton")

            layout.addWidget(preset_button)

    def append_add_presets_buttons(self, values):
        self.append_preset_buttons(values, self.add_layout, self.add_preset_on_clicked, "Add / subtract weight")

    def append_scale_presets_buttons(self, values):
        self.append_preset_buttons(values, self.scale_layout, self.scale_preset_on_clicked, "Scale weight", suffix="%")

    def append_set_presets_buttons(self, values):
        self.append_preset_buttons(values, self.set_layout, self.set_preset_on_clicked, "Set weight")

    def toggle_check_button(self, button):
        button.setChecked(not button.isChecked())

    def fetch_latest_tool_version(self):
        url = QtCore.QUrl(constants.GITHUB_LATEST_RELEASE)

        request = QtNetwork.QNetworkRequest()
        request.setUrl(url)

        manager = QtNetwork.QNetworkAccessManager()

        response = manager.get(request)
        response.finished.connect(
            partial(self.request_on_finished, manager, response))  # Pass manager to keep it alive.

    def request_on_finished(self, manager, response):
        raw_response = response.readAll()
        data = json.loads(bytes(raw_response))

        latest_version = data["tag_name"]
        is_obsolete = utils.is_version_string_greater(latest_version, self.version)

        if is_obsolete:
            self.update_label.setText(
                "{ver} is available to <a href='{url}'>download here</a>".format(
                    ver=latest_version, url=data["html_url"]))
            self.update_frame.show()

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
            "update_on_open_action.isChecked": self.update_on_open_action.isChecked(),
            "hide_long_names_action.isChecked": self.hide_long_names_action.isChecked(),
            "weights_table.max_display_count": self.weights_table.table_model.max_display_count,
            "add_presets_values": self.add_preset_values,
            "scale_presets_values": self.scale_preset_values,
            "set_presets_values": self.set_preset_values
        }

        hotkeys_data = {}
        for hotkey in self.hotkeys:
            hotkeys_data.update(hotkey.serialize())
        data["hotkeys"] = hotkeys_data

        OpenMaya.MGlobal.displayInfo("Saving settings to {0}".format(self.settings_path))
        
        with open(self.settings_path, "w") as f:
            f.write(json.dumps(data, indent=4, sort_keys=True))

    def fetch_settings(self):
        if not os.path.exists(self.settings_path):
            return {}

        with open(self.settings_path, "r") as f:
            return json.loads(f.read())

    def restore_state(self):
        """
        Restores gui's last state if the file is available.
        """
        data = self.fetch_settings()

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
            "show_inf_button.isChecked": self.show_inf_button,
            "update_on_open_action.isChecked": self.update_on_open_action,
            "hide_long_names_action.isChecked": self.hide_long_names_action
        }

        for key, checkbox in checkboxes.items():
            if key in data:
                checkbox.setChecked(data[key])

        self.auto_update_on_toggled()

        if "hotkeys" in data:
            for hotkey in self.hotkeys:
                if hotkey.caption in data["hotkeys"]:
                    values = data["hotkeys"][hotkey.caption]
                    hotkey.ctrl = values["ctrl"]
                    hotkey.shift = values["shift"]
                    hotkey.alt = values["alt"]
                    hotkey.key = values["key"]

        if "add_presets_values" in data:
            self.add_preset_values = data["add_presets_values"]
        self.append_add_presets_buttons(self.add_preset_values)

        if "scale_presets_values" in data:
            self.scale_preset_values = data["scale_presets_values"]
        self.append_scale_presets_buttons(self.scale_preset_values)

        if "set_presets_values" in data:
            self.set_preset_values = data["set_presets_values"]
        self.append_set_presets_buttons(self.set_preset_values)
    
    def update_obj(self, obj):
        """
        Re-points tool to work on another object and re-collect its skin data.
        
        Args:
            obj(string): Object to re-point to.
        """
        weights_view = self.get_active_weights_view()
        weights_view.begin_update()

        try:
            self.obj.hide_vert_colors()

            # Reset values
            self.obj = SkinnedObj.create(obj)
            self.infs = []
            self.in_component_mode = utils.is_in_component_mode()

            # Reset undo stack.
            self.undo_stack.clear()
            self.set_undo_buttons_enabled_state()

            # Collect new values
            if self.obj.is_valid() and self.obj.has_valid_skin():
                if self.obj.is_skin_corrupt():
                    utils.show_error_msg(
                        "Skin cluster error!",
                        "The mesh's vert count doesn't match the skin cluster's weight count!\n"
                        "This is likely because changes were done on the mesh with an enabled skinCluster.\n"
                        "\n"
                        "You may have to duplicate the mesh and use copy weights to fix it.",
                        self)
                    return
                else:
                    self.infs = self.get_all_infs()

            self.update_inf_list()

            caption = "Load object's skin data"
            if self.obj.is_valid():
                caption = self.obj.short_name()
            self.pick_obj_button.setText(caption)

            self.update_window_title()

            self.recollect_table_data(load_selection=False)
        finally:
            weights_view.end_update()

        if self.obj.is_valid():
            if self.infs:
                self.auto_assign_color_inf()

            if not self.hide_colors_button.isChecked() and self.in_component_mode:
                self.obj.switch_to_color_set()
                self.update_vert_colors()
            else:
                self.obj.hide_vert_colors()
    
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
        Also collects unique colors of each influence for the Softimage theme.
        """
        self.inf_colors = self.obj.skin_cluster.collect_influence_colors()
        return sorted(self.obj.skin_cluster.get_influences())
    
    def get_selected_infs(self):
        """
        Gets and returns a list of influences that effects selected vertexes.
        """
        infs = set()

        if self.obj.has_valid_skin():
            for vert_index in self.vert_indexes:
                vert_infs = self.obj.skin_cluster.skin_data.get_vertex_infs(vert_index)
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

        if not self.obj.is_valid():
            return

        selection_data = None
        if load_selection:
            selection_data = weights_view.save_table_selection()
        
        if update_skin_data:
            self.obj.update_skin_data()
        
        if update_verts:
            self.vert_indexes = utils.extract_indexes(
                utils.get_vert_indexes(self.obj.obj))
        
        if update_infs:
            self.collect_display_infs()
        
        if update_headers:
            weights_view.color_headers()

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
        if not self.obj.is_valid():
            return

        weights_view = self.get_active_weights_view()

        verts_and_infs = weights_view.get_selected_verts_and_infs()
        if not verts_and_infs:
            OpenMaya.MGlobal.displayWarning("Select cells inside the table to edit.")
            return

        sel_vert_indexes = set()
        old_skin_data = self.obj.skin_cluster.skin_data.copy()

        for vert_index, inf in verts_and_infs:
            old_weight_data = old_skin_data[vert_index]["weights"]
            old_value = old_weight_data.get(inf) or 0.0

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

            self.obj.skin_cluster.skin_data.update_weight_value(vert_index, inf, new_value)
            
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
            self.obj.obj,
            old_skin_data,
            self.obj.skin_cluster.skin_data.copy(),
            list(sel_vert_indexes),
            weights_view.save_table_selection())

    def update_vert_colors(self, vert_filter=[]):
        """
        Displays active influence.
        
        Args:
            vert_filter(int[]): List of vertex indexes to only operate on.
        """
        if self.hide_colors_button.isChecked():
            return

        if self.obj.is_valid():
            if utils.is_curve(self.obj.obj):
                return
        
        if not self.infs:
            return

        if self.color_inf is None:
            self.auto_assign_color_inf()
        
        if self.color_style == ColorTheme.Softimage:
            self.set_color_inf(None)

            self.obj.display_multi_color_influence(
                inf_colors=self.inf_colors,
                vert_filter=vert_filter)
        else:
            if self.color_inf is not None:
                self.obj.display_influence(
                    self.color_inf,
                    color_style=self.color_style,
                    vert_filter=vert_filter)

        utils.toggle_display_colors(self.obj.obj, True)
    
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
        if not self.obj.is_valid():
            OpenMaya.MGlobal.displayWarning("No object to operate on.")
            return

        selected_vertexes = utils.extract_indexes(
            utils.get_vert_indexes(self.obj.obj))

        if not selected_vertexes:
            OpenMaya.MGlobal.displayWarning("No vertexes are selected.")
            return

        old_skin_data = self.obj.skin_cluster.skin_data.copy()

        weights_view = self.get_active_weights_view()
        table_selection = weights_view.save_table_selection()

        sel_vert_indexes = utils.extract_indexes(
            utils.get_vert_indexes(self.obj.obj))

        if smooth_operation == SmoothOperation.Normal:
            self.obj.smooth_weights(
                selected_vertexes,
                self.smooth_strength_spinbox.value())

            self.recollect_table_data(update_skin_data=False, update_verts=False)

            undo_caption = "Smooth weights"
        else:
            # Re-collects all data since this smooth doesn't change internal data.
            utils.br_smooth_verts(self.smooth_strength_spinbox.value(), True)
            self.recollect_table_data()
            undo_caption = "Smooth weights (all influences)"

        self.update_vert_colors(vert_filter=selected_vertexes)

        new_skin_data = self.obj.skin_cluster.skin_data.copy()

        self.add_undo_command(
            undo_caption,
            self.obj.obj,
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

    def auto_assign_color_inf(self):
        if self.infs:
            weights_view = self.get_active_weights_view()
            display_infs = weights_view.display_infs()

            if display_infs:
                self.set_color_inf(display_infs[0])
            else:
                self.set_color_inf(self.infs[0])

    def update_inf_list(self):
        self.inf_list.begin_update()

        try:
            self.inf_list.list_model.clear()

            for i, inf in enumerate(sorted(self.infs)):
                item = QtGui.QStandardItem(inf)
                item.setToolTip(inf)
                item.setSizeHint(QtCore.QSize(1, 30))
                self.inf_list.list_model.appendRow(item)

            self.apply_filter_to_inf_list()
        finally:
            self.inf_list.end_update()
            self.update_inf_filter_items()

    def update_inf_filter_items(self):
        items = self.inf_list.get_displayed_items()
        completer = QtWidgets.QCompleter(items, self)
        completer.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
        completer.setCompletionMode(QtWidgets.QCompleter.PopupCompletion)
        completer.setFilterMode(QtCore.Qt.MatchContains)
        self.inf_filter_edit.setCompleter(completer)

    def apply_filter_to_inf_list(self):
        self.inf_list.apply_filter("*" + self.inf_filter_edit.text() + "*")

    def mirror_weights(self, selection_only):
        if not self.obj.is_valid():
            return

        old_skin_data = self.obj.skin_cluster.skin_data.copy()

        weights_view = self.get_active_weights_view()
        table_selection = weights_view.save_table_selection()

        if selection_only:
            vert_indexes = utils.extract_indexes(
                utils.get_vert_indexes(self.obj.obj))
        else:
            vert_indexes = utils.extract_indexes(
                utils.get_all_vert_indexes(self.obj.obj))

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

        self.obj.mirror_skin_weights(
            mirror_mode,
            mirror_inverse,
            surface_association,
            inf_association,
            vert_filter=vert_indexes)

        self.recollect_table_data(update_verts=False)

        vert_filter = vert_indexes if selection_only else []
        self.update_vert_colors(vert_filter=vert_filter)

        new_skin_data = self.obj.skin_cluster.skin_data.copy()

        self.add_undo_command(
            "Mirror weights",
            self.obj.obj,
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
        if self.obj.is_valid() and self.obj.has_valid_skin():
            # Toggle influence colors if component selection mode changes.
            now_in_component_mode = utils.is_in_component_mode()

            # No point to adjust colors if it's already disabled.
            if not self.hide_colors_button.isChecked():
                if now_in_component_mode != self.in_component_mode:  # Only continue if component mode was switched.
                    if now_in_component_mode:
                        self.update_vert_colors()
                    else:
                        self.obj.hide_vert_colors()

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

            if self.obj.is_valid():
                utils.toggle_display_colors(self.obj.obj, False)
                utils.delete_temp_inputs(self.obj.obj)
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
        self.update_obj(self.obj.obj)
    
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
        if not self.obj.is_valid():
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
        
        self.obj.select_inf_vertexes(infs)
    
    def prune_on_clicked(self):
        if not self.obj.is_valid():
            return
        
        old_skin_data = self.obj.skin_cluster.skin_data.copy()

        weights_view = self.get_active_weights_view()
        table_selection = weights_view.save_table_selection()
        
        sel_vert_indexes = utils.extract_indexes(
            utils.get_vert_indexes(self.obj.obj))

        if not self.obj.prune_weights(self.prune_spinbox.value()):
            return
        
        self.recollect_table_data(update_verts=False)
        
        self.update_vert_colors(vert_filter=sel_vert_indexes)
        
        new_skin_data = self.obj.skin_cluster.skin_data.copy()
        
        self.add_undo_command(
            "Prune weights",
            self.obj.obj,
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
        if not self.obj.is_valid():
            return

        vert_indexes = utils.extract_indexes(
            utils.get_vert_indexes(self.obj.obj))

        if not vert_indexes:
            OpenMaya.MGlobal.displayError("Need a vertex to be selected.")
            return

        vert_index = vert_indexes[0]
        self.copied_vertex = self.obj.skin_cluster.skin_data.copy_vertex(vert_index)
        OpenMaya.MGlobal.displayInfo("Copied vertex {}".format(vert_index))

    def paste_vertex_on_clicked(self):
        if self.copied_vertex is None:
            OpenMaya.MGlobal.displayError("Need to copy a vertex first.")
            return

        if not self.obj.is_valid():
            return

        vert_indexes = utils.extract_indexes(
            utils.get_vert_indexes(self.obj.obj))

        if not vert_indexes:
            return

        weights_view = self.get_active_weights_view()
        table_selection = weights_view.save_table_selection()
        old_skin_data = self.obj.skin_cluster.skin_data.copy()

        for vert_index in vert_indexes:
            self.obj.skin_cluster.skin_data[vert_index] = copy.deepcopy(self.copied_vertex)

        new_skin_data = self.obj.skin_cluster.skin_data.copy()

        self.add_undo_command(
            "Paste vertex",
            self.obj.obj,
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
        if self.obj.is_valid() and self.in_component_mode:
            self.update_vert_colors()
            utils.toggle_display_colors(self.obj.obj, not checked)

    def flood_to_closest_on_clicked(self):
        if not self.obj.is_valid() or not self.obj.has_valid_skin():
            return

        old_skin_data = self.obj.skin_cluster.skin_data.copy()

        weights_view = self.get_active_weights_view()
        table_selection = weights_view.save_table_selection()

        vert_indexes = utils.extract_indexes(
            utils.get_all_vert_indexes(self.obj.obj))

        self.obj.flood_weights_to_closest()

        self.recollect_table_data(update_verts=False)
        self.update_vert_colors()

        new_skin_data = self.obj.skin_cluster.skin_data.copy()

        self.add_undo_command(
            "Flood weights to closest",
            self.obj.obj,
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

    def hide_long_names_on_triggered(self, visible):
        self.inf_list.toggle_long_names(visible)
        self.update_inf_filter_items()
        self.weights_list.toggle_long_names(visible)
        self.weights_table.toggle_long_names(visible)

    def launch_hotkeys_on_clicked(self):
        status, dialog = hotkeys_dialog.HotkeysDialog.launch(self.hotkeys, self)
        if status:
            self.hotkeys = dialog.serialize()
            self.register_shortcuts()
        dialog.deleteLater()

    def launch_presets_on_clicked(self):
        status, dialog = presets_dialog.PresetsDialog.launch(
            self.add_preset_values,
            self.scale_preset_values,
            self.set_preset_values,
            self)

        if status:
            presets = dialog.serialize()
            self.add_preset_values = presets["add"]
            self.scale_preset_values = presets["scale"]
            self.set_preset_values = presets["set"]
            self.append_add_presets_buttons(self.add_preset_values)
            self.append_scale_presets_buttons(self.scale_preset_values)
            self.append_set_presets_buttons(self.set_preset_values)

        dialog.deleteLater()

    def about_on_triggered(self):
        dialog = about_dialog.AboutDialog.launch(self.version, self)
        dialog.deleteLater()

    def github_page_on_triggered(self):
        webbrowser.open(constants.GITHUB_HOME)

    def toggle_view_on_toggled(self, enabled):
        self.limit_warning_label.setVisible(False)
        self.weights_list.setVisible(not enabled)
        self.weights_table.setVisible(enabled)

        if enabled:
            self.toggle_view_button.setText("TABLE")
            self.toggle_view_button.setIcon(utils.load_pixmap("interface/table.png"))
        else:
            self.toggle_view_button.setText("LIST")
            self.toggle_view_button.setIcon(utils.load_pixmap("interface/list.png"))

        self.recollect_table_data()

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

    def inf_list_on_toggle_locks_triggered(self, infs):
        if infs[0] not in self.infs:
            OpenMaya.MGlobal.displayError("Unable to find influence in internal data.. Is it out of sync?")
            return

        inf_index = self.infs.index(infs[0])
        lock = not self.locks[inf_index]
        self.toggle_inf_locks(infs, lock)

    def add_inf_to_vert_on_clicked(self):
        """
        Adds a very small weight value from selected influences to selected vertexes.
        """
        if not self.obj.is_valid():
            OpenMaya.MGlobal.displayError("There's no active object to work on.")
            return
        
        sel_vert_indexes = utils.extract_indexes(utils.get_vert_indexes(self.obj.obj))
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
        
        old_skin_data = self.obj.skin_cluster.skin_data.copy()

        weights_view = self.get_active_weights_view()
        table_selection = weights_view.save_table_selection()
        
        # Add infs by setting a very low value so it doesn't effect other weights too much.
        for inf in sel_infs:
            for vert_index in sel_vert_indexes:
                weight_data = self.obj.skin_cluster.skin_data[vert_index]["weights"]
                if weight_data.get(inf) is None:
                    self.obj.skin_cluster.skin_data.update_weight_value(vert_index, inf, 0.001)

        new_skin_data = self.obj.skin_cluster.skin_data.copy()

        self.add_undo_command(
            "Add influence to verts",
            self.obj.obj,
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
        if self.obj.is_valid():
            self.obj.select_inf_vertexes([inf])


def run():
    WeightsEditor.run()
