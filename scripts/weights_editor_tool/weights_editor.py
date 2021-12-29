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
    - Export skin
    - Import skin
    - Add unit tests
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
from weights_editor_tool.enums import ColorTheme, WeightOperation, SmoothOperation, Hotkeys
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
        if parent is None:
            parent = utils.get_maya_window()

        QtWidgets.QMainWindow.__init__(self, parent=parent)

        self._del_prev_instance()
        self.__class__.instance = self

        self.setWindowIcon(utils.load_pixmap("interface/icon.png"))
        self.setWindowFlags(QtCore.Qt.Window)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.setObjectName("weightsEditor")
        
        self._undo_stack = QtWidgets.QUndoStack(parent=self)
        self._undo_stack.setUndoLimit(30)
        self._copied_vertex = None
        self._allow_to_fetch_update = True
        self._in_component_mode = utils.is_in_component_mode()
        self._settings_path = os.path.join(os.getenv("HOME"), "maya", "weights_editor.json")
        self._add_preset_values = presets_dialog.PresetsDialog.Defaults["add"]
        self._scale_preset_values = presets_dialog.PresetsDialog.Defaults["scale"]
        self._set_preset_values = presets_dialog.PresetsDialog.Defaults["set"]

        self.obj = SkinnedObj.create_empty()
        self.color_inf = None
        self.vert_indexes = []
        self.infs = []
        self.locks = []
        self.inf_colors = {}
        self.color_style = ColorTheme.Max
        self.block_selection_cb = False
        self.ignore_cell_selection_event = False
        self.toggle_inf_lock_key_code = None

        self._create_gui()

        self._hotkeys = [
            hotkey_module.Hotkey.create_from_default(Hotkeys.ToggleTableListViews, partial(self._toggle_check_button, self._toggle_view_button)),
            hotkey_module.Hotkey.create_from_default(Hotkeys.ShowUtilities, partial(self._toggle_check_button, self._show_utilities_button)),
            hotkey_module.Hotkey.create_from_default(Hotkeys.ShowAddPresets, partial(self._toggle_check_button, self._show_add_button)),
            hotkey_module.Hotkey.create_from_default(Hotkeys.ShowScalePresets, partial(self._toggle_check_button, self._show_scale_button)),
            hotkey_module.Hotkey.create_from_default(Hotkeys.ShowSetPresets, partial(self._toggle_check_button, self._show_set_button)),
            hotkey_module.Hotkey.create_from_default(Hotkeys.ShowInfList, partial(self._toggle_check_button, self._show_inf_button)),
            hotkey_module.Hotkey.create_from_default(Hotkeys.ShowInfColors, partial(self._toggle_check_button, self._hide_colors_button)),
            hotkey_module.Hotkey.create_from_default(Hotkeys.MirrorAll, self._mirror_all_skin_on_clicked),
            hotkey_module.Hotkey.create_from_default(Hotkeys.Prune, self._prune_on_clicked),
            hotkey_module.Hotkey.create_from_default(Hotkeys.RunSmooth, partial(self._run_smooth, SmoothOperation.Normal)),
            hotkey_module.Hotkey.create_from_default(Hotkeys.RunSmoothAllInfs, partial(self._run_smooth, SmoothOperation.AllInfluences)),
            hotkey_module.Hotkey.create_from_default(Hotkeys.Undo, self._undo_on_click),
            hotkey_module.Hotkey.create_from_default(Hotkeys.Redo, self._redo_on_click),
            hotkey_module.Hotkey.create_from_default(Hotkeys.GrowSelection, self._grow_selection),
            hotkey_module.Hotkey.create_from_default(Hotkeys.ShrinkSelection, self._shrink_selection),
            hotkey_module.Hotkey.create_from_default(Hotkeys.SelectEdgeLoop, self._select_edge_loop),
            hotkey_module.Hotkey.create_from_default(Hotkeys.SelectRingLoop, self._select_ring_loop),
            hotkey_module.Hotkey.create_from_default(Hotkeys.SelectPerimeter, self._select_perimeter),
            hotkey_module.Hotkey.create_from_default(Hotkeys.SelectShell, self._select_shell),
            hotkey_module.Hotkey.create_from_default(Hotkeys.ToggleInfLock, None)
        ]

        self._restore_state()
        self._register_shortcuts()
        self._set_undo_buttons_enabled_state()

        if self._allow_to_fetch_update and self._update_on_open_action.isChecked():
            try:
                self._fetch_latest_tool_version()
            except Exception as err:
                print(traceback.format_exc())
                cmds.warning("Could not get version from GitHub: {e}".format(e=err))

    @classmethod
    def run(cls):
        inst = cls()
        inst.show()
        inst._pick_obj_on_clicked()
        return inst

    @classmethod
    def _del_prev_instance(cls):
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
    def _remove_shortcuts(cls):
        for shortcut in cls.shortcuts:
            shortcut.setEnabled(False)
        cls.shortcuts = []

    def _create_gui(self):
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
        self._menu_bar = self.menuBar()

        self._options_menu = QtWidgets.QMenu("&Tool settings", parent=self)
        self._menu_bar.addMenu(self._options_menu)

        self._view_separator = QtWidgets.QAction("[ Weights list / table view ]", self)
        self._view_separator.setEnabled(False)
        self._options_menu.addAction(self._view_separator)

        self._auto_update_table_action = QtWidgets.QAction("Auto-update view when selecting in viewport", self)
        self._auto_update_table_action.setCheckable(True)
        self._auto_update_table_action.setChecked(True)
        self._auto_update_table_action.triggered.connect(self._auto_update_on_toggled)
        self._options_menu.addAction(self._auto_update_table_action)

        self._auto_select_infs_action = QtWidgets.QAction("Auto-select cells from active influence", self)
        self._auto_select_infs_action.setCheckable(True)
        self._auto_select_infs_action.setChecked(True)
        self._options_menu.addAction(self._auto_select_infs_action)

        self._table_view_separator = QtWidgets.QAction("[ Table view ]", self)
        self._table_view_separator.setEnabled(False)
        self._options_menu.addAction(self._table_view_separator)

        self.auto_select_vertex_action = QtWidgets.QAction("Auto-select vertexes when selecting cells", self)
        self.auto_select_vertex_action.setCheckable(True)
        self._options_menu.addAction(self.auto_select_vertex_action)

        self._set_limit_action = QtWidgets.QAction("Set max row limit", self)
        self._set_limit_action.triggered.connect(self._set_limit_on_triggered)
        self._options_menu.addAction(self._set_limit_action)

        self._color_separator = QtWidgets.QAction("[ Settings ]", self)
        self._color_separator.setEnabled(False)
        self._options_menu.addAction(self._color_separator)

        self._color_sub_menu = self._options_menu.addMenu("Switch influence color style")

        self._max_color_action = QtWidgets.QAction("3dsMax theme", self)
        self._max_color_action.setCheckable(True)
        self._max_color_action.setChecked(True)
        self._max_color_action.triggered.connect(partial(self._switch_color_on_clicked, ColorTheme.Max))
        self._color_sub_menu.addAction(self._max_color_action)

        self._maya_color_action = QtWidgets.QAction("Maya theme", self)
        self._maya_color_action.setCheckable(True)
        self._maya_color_action.triggered.connect(partial(self._switch_color_on_clicked, ColorTheme.Maya))
        self._color_sub_menu.addAction(self._maya_color_action)

        self._softimage_color_action = QtWidgets.QAction("Softimage theme", self)
        self._softimage_color_action.setCheckable(True)
        self._softimage_color_action.triggered.connect(partial(self._switch_color_on_clicked, ColorTheme.Softimage))
        self._color_sub_menu.addAction(self._softimage_color_action)

        self._hide_long_names_action = QtWidgets.QAction("Hide long names", self)
        self._hide_long_names_action.setCheckable(True)
        self._hide_long_names_action.setChecked(True)
        self._hide_long_names_action.toggled.connect(self._hide_long_names_on_triggered)
        self._options_menu.addAction(self._hide_long_names_action)

        self._update_on_open_action = QtWidgets.QAction("Check for updates on open", self)
        self._update_on_open_action.setCheckable(True)
        self._update_on_open_action.setChecked(True)
        self._options_menu.addAction(self._update_on_open_action)

        self._visibility_separator = QtWidgets.QAction("Visibility settings", self)
        self._visibility_separator.setSeparator(True)
        self._options_menu.addAction(self._visibility_separator)

        self._launch_hotkeys_action = QtWidgets.QAction("Edit hotkeys", self)
        self._launch_hotkeys_action.triggered.connect(self._launch_hotkeys_on_clicked)

        self._launch_presets_action = QtWidgets.QAction("Edit preset buttons", self)
        self._launch_presets_action.triggered.connect(self._launch_presets_on_clicked)

        self._prefs_menu = self._menu_bar.addMenu("&Preferences")
        self._prefs_menu.addAction(self._launch_hotkeys_action)
        self._prefs_menu.addAction(self._launch_presets_action)

        self._about_action = QtWidgets.QAction("About this tool", self)
        self._about_action.triggered.connect(self._about_on_triggered)

        self._github_page_action = QtWidgets.QAction("Github page", self)
        self._github_page_action.triggered.connect(self._github_page_on_triggered)

        self._about_menu = self._menu_bar.addMenu("&About")
        self._about_menu.addAction(self._about_action)
        self._about_menu.addAction(self._github_page_action)

    #
    # CENTRAL WIDGET
    #

        self._central_widget = QtWidgets.QWidget(parent=self)
        self._central_widget.setObjectName("weightsEditorCentralWidget")

        self._toggle_view_button = self._create_button("TABLE", "interface/table.png")
        self._show_utilities_button = self._create_button("UTL", "interface/utils.png")
        self._show_add_button = self._create_button("ADD", "interface/add.png")
        self._show_scale_button = self._create_button("SCA", "interface/percent.png")
        self._show_set_button = self._create_button("SET", "interface/equal.png")
        self._show_inf_button = self._create_button("INF", "interface/inf.png")

        for widget in [
                self._toggle_view_button, self._show_utilities_button, self._show_add_button,
                self._show_scale_button, self._show_set_button, self._show_inf_button]:
            widget.setMinimumWidth(25)
            widget.setMaximumWidth(150)
            widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
            widget.setCheckable(True)
            widget.setChecked(True)

        self._toggle_view_button.toggled.connect(self._toggle_view_on_toggled)
        self._show_utilities_button.toggled.connect(self._show_utilities_on_toggled)
        self._show_add_button.toggled.connect(self._show_add_on_toggled)
        self._show_scale_button.toggled.connect(self._show_scale_on_toggled)
        self._show_set_button.toggled.connect(self._show_set_on_toggled)
        self._show_inf_button.toggled.connect(self._show_inf_on_toggled)

        self._show_layout = utils.wrap_layout(
            [self._toggle_view_button,
             self._show_utilities_button,
             self._show_add_button,
             self._show_scale_button,
             self._show_set_button,
             self._show_inf_button],
            QtCore.Qt.Horizontal,
            spacing=5)

        self._pick_obj_label = QtWidgets.QLabel("Object:", parent=self._central_widget)

        self._pick_obj_button = QtWidgets.QPushButton("", parent=self._central_widget)
        self._pick_obj_button.setToolTip("Switches to selected mesh for editing.")
        self._pick_obj_button.clicked.connect(self._pick_obj_on_clicked)

        self._refresh_button = self._create_button(
            "", "interface/refresh.png",
            tool_tip="Refreshes the skin's data.",
            icon_size=QtCore.QSize(22, 22),
            click_event=self._refresh_on_clicked)
        self._refresh_button.setMinimumWidth(18)
        self._refresh_button.setFixedHeight(24)
        self._refresh_button.setFlat(True)

        self._pick_obj_layout = utils.wrap_layout(
            [self._pick_obj_label,
             self._pick_obj_button,
             self._refresh_button,
             3,
             "stretch",
             self._show_layout],
             QtCore.Qt.Horizontal,
             margins=[5, 5, 5, 5])

        self._prune_spinbox = QtWidgets.QDoubleSpinBox(value=0.1, parent=self._central_widget)
        self._prune_spinbox.setToolTip("Prune any influence below this value.")
        self._prune_spinbox.setMinimumWidth(60)
        self._prune_spinbox.setDecimals(3)
        self._prune_spinbox.setMinimum(0.001)
        self._prune_spinbox.setSingleStep(0.01)

        self._prune_button = self._create_button(
            "Prune", "interface/prune.png",
            click_event=self._prune_on_clicked)

        self._prune_layout = utils.wrap_layout(
            [self._prune_spinbox,
             self._prune_button,
             "stretch"],
            QtCore.Qt.Horizontal)

        self._smooth_strength_spinbox = QtWidgets.QDoubleSpinBox(value=1, parent=self._central_widget)
        self._smooth_strength_spinbox.setToolTip("Smooth's strength.")
        self._smooth_strength_spinbox.setMinimumWidth(60)
        self._smooth_strength_spinbox.setDecimals(2)
        self._smooth_strength_spinbox.setMinimum(0)
        self._smooth_strength_spinbox.setMaximum(1)
        self._smooth_strength_spinbox.setSingleStep(0.1)

        self._smooth_button = self._create_button(
            "Smooth (vert's infs)", "interface/smooth.png",
            click_event=partial(self._run_smooth, SmoothOperation.Normal))

        self._smooth_br_button = self._create_button(
            "Smooth (all infs)", "interface/smooth.png",
            click_event=partial(self._run_smooth, SmoothOperation.AllInfluences))

        if not hasattr(cmds, "brSmoothWeightsContext"):
            self._smooth_br_button.setEnabled(False)

        self._smooth_layout = utils.wrap_layout(
            [self._smooth_strength_spinbox,
             self._smooth_button,
             self._smooth_br_button,
             "stretch"],
            QtCore.Qt.Horizontal)

        self._mirror_skin_button = self._create_button(
            "Mirror", "interface/mirror.png",
            tool_tip="Mirror weights on selected vertexes only",
            click_event=self._mirror_skin_on_clicked)

        self._mirror_all_skin_button = self._create_button(
            "Mirror all", "interface/mirror.png",
            click_event=self._mirror_all_skin_on_clicked)

        self._mirror_mode = QtWidgets.QComboBox(parent=self._central_widget)
        self._mirror_mode.setToolTip("Mirror axis")
        self._mirror_mode.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self._mirror_mode.setMinimumWidth(35)
        self._mirror_mode.setMaximumWidth(50)
        self._mirror_mode.addItems(["XY", "YZ", "XZ", "-XY", "-YZ", "-XZ"])

        self._mirror_surface = QtWidgets.QComboBox(parent=self._central_widget)
        self._mirror_surface.setToolTip("Mirror surface association")
        self._mirror_surface.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self._mirror_surface.setMinimumWidth(35)
        self._mirror_surface.setMaximumWidth(100)
        self._mirror_surface.addItems(["Closest Point", "Ray Cast", "Closest Component"])

        self._mirror_inf = QtWidgets.QComboBox(parent=self._central_widget)
        self._mirror_inf.setToolTip("Mirror influence association")
        self._mirror_inf.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self._mirror_inf.setMinimumWidth(35)
        self._mirror_inf.setMaximumWidth(100)
        self._mirror_inf.addItems(["Label", "Closest Point", "Closest Bone", "Name", "One To One"])

        self._mirror_layout = utils.wrap_layout(
            [self._mirror_skin_button,
             self._mirror_all_skin_button,
             self._mirror_mode,
             self._mirror_surface,
             self._mirror_inf,
             "stretch"],
            QtCore.Qt.Horizontal,
            margins=[0, 0, 0, 0])

        self._copy_vertex_button = self._create_button(
            "Copy vertex", "interface/copy.png",
            tool_tip="Copy weights on first selected vertex",
            click_event=self._copy_vertex_on_clicked)

        self._paste_vertex_button = self._create_button(
            "Paste vertex", "interface/paste.png",
            tool_tip="Paste weights on selected vertexes",
            click_event=self._paste_vertex_on_clicked)

        self._copy_vert_layout = utils.wrap_layout(
            [self._copy_vertex_button,
             self._paste_vertex_button,
             "stretch"],
            QtCore.Qt.Horizontal)

        self._weight_layout = utils.wrap_layout(
            [self._prune_layout,
             self._smooth_layout,
             self._mirror_layout,
             self._copy_vert_layout],
            QtCore.Qt.Vertical,
            margins=[0, 0, 0, 0],
            spacing=5)

        self._weight_frame = QtWidgets.QFrame(parent=self._central_widget)
        self._weight_frame.setLayout(self._weight_layout)
        self._weight_frame.setStyleSheet("QFrame {{background-color: {}}}".format(win_color.lighter(109).name()))

        self._weight_scroll_area = QtWidgets.QScrollArea(parent=self._central_widget)
        self._weight_scroll_area.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self._weight_scroll_area.setFocusPolicy(QtCore.Qt.NoFocus)
        self._weight_scroll_area.setWidget(self._weight_frame)
        self._weight_scroll_area.setWidgetResizable(True)

        self._weight_scroll_layout = utils.wrap_layout(
            [self._weight_scroll_area],
            QtCore.Qt.Vertical,
            margins=[5, 0, 1, 0])

        self._weight_groupbox = QtWidgets.QGroupBox("Weight utilities", parent=self._central_widget)
        self._weight_groupbox.setLayout(self._weight_scroll_layout)

        self._add_layout, self._add_groupbox, self._add_spinbox = \
            self._create_preset_layout(
                -1, 1, 0.1,
                self._set_add_on_clicked,
                "Add / subtract weight")

        self._scale_layout, self._scale_groupbox, self._scale_spinbox = \
            self._create_preset_layout(
                -100, 100, 1,
                self._set_scale_on_clicked,
                "Scale weight",
                suffix="%")

        self._set_layout, self._set_groupbox, self._set_spinbox = \
            self._create_preset_layout(
                0, 1, 0.1,
                self._set_on_clicked,
                "Set weight")

        # Setup table
        self._limit_warning_label = QtWidgets.QLabel(parent=self)
        self._limit_warning_label.setObjectName("warningLabel")
        self._limit_warning_label.setWordWrap(True)
        self._limit_warning_label.hide()

        self._weights_table = weights_table_view.TableView(self)
        self._weights_table.update_ended.connect(self._table_on_update_ended)

        self._weights_list = weights_list_view.ListView(self)
        self._weights_list.hide()

        for view in [self._weights_list, self._weights_table]:
            view.key_pressed.connect(self._weights_view_on_key_pressed)
            view.header_middle_clicked.connect(self._header_on_middle_clicked)
            view.display_inf_triggered.connect(self._display_inf_on_triggered)
            view.select_inf_verts_triggered.connect(self._select_inf_verts_on_triggered)

        self._show_all_button = self._create_button(
            "Show all influences", "interface/show.png",
            tool_tip="Forces the table to show all influences.",
            click_event=self._selection_on_changed)
        self._show_all_button.setCheckable(True)

        self._hide_colors_button = self._create_button(
            "Hide influence colors", "interface/hide.png")
        self._hide_colors_button.setCheckable(True)
        self._hide_colors_button.toggled.connect(self._hide_colors_on_toggled)

        self._flood_to_closest_button = self._create_button(
            "Flood to closest", "interface/flood.png",
            tool_tip="Set full weights to the closest joints for easier blocking.",
            click_event=self._flood_to_closest_on_clicked)

        self._toggle_hotkeys_button = self._create_button(
            "Hotkeys enabled", "interface/hotkeys.png")
        self._toggle_hotkeys_button.setCheckable(True)
        self._toggle_hotkeys_button.toggled.connect(self._hotkeys_on_toggled)

        self._settings_layout = utils.wrap_layout(
            [self._show_all_button,
             self._hide_colors_button,
             self._flood_to_closest_button,
             self._toggle_hotkeys_button],
            QtCore.Qt.Horizontal)

        # Undo buttons
        self._undo_button = self._create_button(
            "Undo", "interface/undo.png",
            click_event=self._undo_on_click)
        self._undo_button.setFixedHeight(40)

        self._redo_button = self._create_button(
            "Redo", "interface/redo.png",
            click_event=self._redo_on_click)
        self._redo_button.setFixedHeight(40)

        self._undo_layout = utils.wrap_layout(
            [self._undo_button,
             self._redo_button],
            QtCore.Qt.Horizontal)

        widgets = [
            self._show_all_button,
            self._hide_colors_button,
            self._flood_to_closest_button,
            self._undo_button]

        for button in widgets:
            button.setMinimumWidth(10)

        self._update_label = QtWidgets.QLabel(parent=self._central_widget)
        self._update_label.setObjectName("updateLabel")
        self._update_label.setOpenExternalLinks(True)

        self._update_layout = utils.wrap_layout(
            [self._update_label],
            QtCore.Qt.Horizontal,
            margins=[3, 0, 3, 0])

        self._update_frame = QtWidgets.QFrame(parent=self._central_widget)
        self._update_frame.setObjectName("updateFrame")
        self._update_frame.setLayout(self._update_layout)
        self._update_frame.hide()

        self._main_layout = utils.wrap_layout(
            [self._update_frame,
             self._pick_obj_layout,
             self._weight_groupbox,
             self._add_groupbox,
             self._scale_groupbox,
             self._set_groupbox,
             self._limit_warning_label,
             self._weights_list,
             self._weights_table,
             self._settings_layout,
             self._undo_layout],
            QtCore.Qt.Vertical,
            spacing=3)
        self._central_widget.setLayout(self._main_layout)

        self.setCentralWidget(self._central_widget)

    #
    # INFLUENCE WIDGET
    #

        self._inf_dock_widget = QtWidgets.QDockWidget(parent=self)
        self.setObjectName("weightsEditorInfluenceWidget")
        self._inf_dock_widget.setFeatures(QtWidgets.QDockWidget.DockWidgetMovable)
        self._inf_dock_widget.setWindowTitle("Influences")
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self._inf_dock_widget)

        self._inf_widget = QtWidgets.QWidget(parent=self._inf_dock_widget)
        self._inf_dock_widget.setWidget(self._inf_widget)

        self._inf_filter_edit = QtWidgets.QLineEdit(parent=self._inf_widget)
        self._inf_filter_edit.setPlaceholderText("Filter list by names (use * as a wildcard)")
        self._inf_filter_edit.textChanged.connect(self._apply_filter_to_inf_list)

        self.inf_list = inf_list_view.InfListView(self, parent=self._inf_widget)
        self.inf_list.middle_clicked.connect(self._inf_list_on_middle_clicked)
        self.inf_list.toggle_locks_triggered.connect(self._inf_list_on_toggle_locks_triggered)
        self.inf_list.set_locks_triggered.connect(self._toggle_inf_locks)
        self.inf_list.select_inf_verts_triggered.connect(self._select_by_infs_on_clicked)
        self.inf_list.add_infs_to_verts_triggered.connect(self._add_inf_to_vert_on_clicked)

        self._add_inf_to_vert_button = QtWidgets.QPushButton("Add inf to verts", parent=self._inf_widget)
        self._add_inf_to_vert_button.setIconSize(icon_size)
        self._add_inf_to_vert_button.setIcon(utils.load_pixmap("interface/add_inf.png"))
        self._add_inf_to_vert_button.setToolTip("Adds the selected influence to all selected vertexes.")
        self._add_inf_to_vert_button.clicked.connect(self._add_inf_to_vert_on_clicked)

        self._select_by_infs_button = QtWidgets.QPushButton("Select influence's verts", parent=self._inf_widget)
        self._select_by_infs_button.setIconSize(icon_size)
        self._select_by_infs_button.setIcon(utils.load_pixmap("interface/select.png"))
        self._select_by_infs_button.setToolTip("Selects all vertexes that is effected by the selected influences.")
        self._select_by_infs_button.clicked.connect(self._select_by_infs_on_clicked)

        self._inf_layout = utils.wrap_layout(
            [self._inf_filter_edit,
             self.inf_list,
             self._add_inf_to_vert_button,
             self._select_by_infs_button],
            QtCore.Qt.Vertical)
        self._inf_widget.setLayout(self._inf_layout)

        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self._update_window_title()
        self.resize(1200, 1000)

#
# Custom functions
#

    def _update_window_title(self):
        title = "Weights Editor v{ver}".format(ver=self.version)
        if self.obj.is_valid():
            title += " - {obj}".format(obj=self.obj.short_name())
        self.setWindowTitle(title)

    def _create_button(self, caption, img_name, icon_size=QtCore.QSize(13, 13), tool_tip=None, click_event=None, parent=None):
        if parent is None:
            parent = self._central_widget

        button = QtWidgets.QPushButton(caption, parent=parent)
        button.setIconSize(icon_size)
        button.setIcon(utils.load_pixmap(img_name))

        if tool_tip is not None:
            button.setToolTip(tool_tip)

        if click_event is not None:
            button.clicked.connect(click_event)

        return button

    def _create_preset_layout(self, spinbox_min, spinbox_max, spinbox_steps, spinbox_callback, caption, suffix=""):
        spinbox = custom_double_spinbox.CustomDoubleSpinbox(parent=self._central_widget)
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

        groupbox = QtWidgets.QGroupBox(caption, parent=self._central_widget)
        groupbox.setLayout(layout)

        return layout, groupbox, spinbox

    def _append_preset_buttons(self, values, layout, preset_callback, tooltip, suffix=""):
        """
        Procedurally creates multiple preset buttons to adjust weights.
        """
        for i in range(layout.count() - 1):
            old_button = layout.takeAt(1).widget()
            old_button.deleteLater()

        for value in values:
            text = "".join([str(value), suffix])
            preset_button = QtWidgets.QPushButton(text, parent=self._central_widget)
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

    def _append_add_presets_buttons(self, values):
        self._append_preset_buttons(values, self._add_layout, self._add_preset_on_clicked, "Add / subtract weight")

    def _append_scale_presets_buttons(self, values):
        self._append_preset_buttons(values, self._scale_layout, self._scale_preset_on_clicked, "Scale weight", suffix="%")

    def _append_set_presets_buttons(self, values):
        self._append_preset_buttons(values, self._set_layout, self._set_preset_on_clicked, "Set weight")

    def _toggle_check_button(self, button):
        button.setChecked(not button.isChecked())

    def _fetch_latest_tool_version(self):
        url = QtCore.QUrl(constants.GITHUB_LATEST_RELEASE)

        request = QtNetwork.QNetworkRequest()
        request.setUrl(url)

        manager = QtNetwork.QNetworkAccessManager()

        response = manager.get(request)
        response.finished.connect(
            partial(self._request_on_finished, manager, response))  # Pass manager to keep it alive.

    def _request_on_finished(self, manager, response):
        raw_response = response.readAll()
        data = json.loads(bytes(raw_response))

        latest_version = data["tag_name"]
        is_obsolete = utils.is_version_string_greater(latest_version, self.version)

        if is_obsolete:
            self._update_label.setText(
                "{ver} is available to <a href='{url}'>download here</a>".format(
                    ver=latest_version, url=data["html_url"]))
            self._update_frame.show()

    def _update_tooltips(self):
        """
        Updates tooltips with the latest shortcuts.
        """
        # Matches same indexes as hotkeys in constructor.
        tooltips = [
            (self._toggle_view_button, "Toggle between list or table view"),
            (self._show_utilities_button, "Show weights utility settings"),
            (self._show_add_button, "Show add / sub weight settings"),
            (self._show_scale_button, "Show scale weight settings"),
            (self._show_set_button, "Show set weight settings"),
            (self._show_inf_button, "Show influence list"),
            (self._hide_colors_button, "Hides colors that visualize the weight values.<br><br>"
                                      "Enable this to help speed up performance"),
            (self._mirror_all_skin_button, "Mirror all weights"),
            (self._prune_button, "Prunes selected vertexes in the viewport that are below this value."),
            (self._smooth_button, "Selected vertexes in the viewport will smooth with only influences that are already assigned to it."),
            (self._smooth_br_button, "Selected vertexes in the viewport will smooth with all influences available."),
            (self._undo_button, "Undo last action"),
            (self._redo_button, "Redo last action")
        ]

        for i in range(len(tooltips)):
            widget, tooltip = tooltips[i]
            new_tooltip = tooltip + "<br><br><b>" + self._hotkeys[i].key_to_string() + "</b>"
            widget.setToolTip(new_tooltip)

    def _register_shortcuts(self):
        """
        Installs temporary hotkeys that overrides Maya's.
        """
        self._remove_shortcuts()

        for hotkey in self._hotkeys:
            if hotkey.caption == Hotkeys.ToggleInfLock:
                self.toggle_inf_lock_key_code = hotkey.key_code()
            else:
                self.__class__.shortcuts.append(
                    utils.create_shortcut(
                        QtGui.QKeySequence(hotkey.key_code()), hotkey.func))

        self._update_tooltips()

    def _set_undo_buttons_enabled_state(self):
        """
        Checks the undo stack and determines enabled state and labels on undo/redo buttons.
        """
        self._undo_button.setEnabled(self._undo_stack.canUndo())
        self._redo_button.setEnabled(self._undo_stack.canRedo())
        
        undo_text = self._undo_stack.undoText()
        
        if undo_text:
            self._undo_button.setText("Undo\n({0})".format(undo_text))
        else:
            self._undo_button.setText("No undos available")
        
        redo_text = self._undo_stack.redoText()
        
        if redo_text:
            self._redo_button.setText("Redo\n({0})".format(redo_text))
        else:
            self._redo_button.setText("No redos available")
    
    def _save_state(self):
        """
        Saves gui's current state to a file.
        """
        if not os.path.exists(os.path.dirname(self._settings_path)):
            os.makedirs(os.path.dirname(self._settings_path))
        
        data = {
            "width": self.width(),
            "height": self.height(),
            "inf_dock_widget.area": int(self.dockWidgetArea(self._inf_dock_widget)),
            "color_style": self.color_style,
            "prune_spinbox.value": self._prune_spinbox.value(),
            "smooth_strength_spinbox.value": self._smooth_strength_spinbox.value(),
            "mirror_mode.currentIndex": self._mirror_mode.currentIndex(),
            "mirror_surface.currentIndex": self._mirror_surface.currentIndex(),
            "mirror_inf.currentIndex": self._mirror_inf.currentIndex(),
            "add_spinbox.value": self._add_spinbox.value(),
            "scale_spinbox.value": self._scale_spinbox.value(),
            "set_spinbox.value": self._set_spinbox.value(),
            "auto_update_button.isChecked": self._auto_update_table_action.isChecked(),
            "show_all_button.isChecked": self._show_all_button.isChecked(),
            "auto_select_button.isChecked": self.auto_select_vertex_action.isChecked(),
            "auto_select_infs_button.isChecked": self._auto_select_infs_action.isChecked(),
            "hide_colors_button.isChecked": self._hide_colors_button.isChecked(),
            "toggle_hotkeys_button.isChecked": self._toggle_hotkeys_button.isChecked(),
            "toggle_view_button.isChecked": self._toggle_view_button.isChecked(),
            "show_utilities_button.isChecked": self._show_utilities_button.isChecked(),
            "show_add_button.isChecked": self._show_add_button.isChecked(),
            "show_scale_button.isChecked": self._show_scale_button.isChecked(),
            "show_set_button.isChecked": self._show_set_button.isChecked(),
            "show_inf_button.isChecked": self._show_inf_button.isChecked(),
            "update_on_open_action.isChecked": self._update_on_open_action.isChecked(),
            "hide_long_names_action.isChecked": self._hide_long_names_action.isChecked(),
            "weights_table.max_display_count": self._weights_table.table_model.max_display_count,
            "add_presets_values": self._add_preset_values,
            "scale_presets_values": self._scale_preset_values,
            "set_presets_values": self._set_preset_values
        }

        hotkeys_data = {}
        for hotkey in self._hotkeys:
            hotkeys_data.update(hotkey.serialize())
        data["hotkeys"] = hotkeys_data

        OpenMaya.MGlobal.displayInfo("Saving settings to {0}".format(self._settings_path))
        
        with open(self._settings_path, "w") as f:
            f.write(json.dumps(data, indent=4, sort_keys=True))

    def _fetch_settings(self):
        if not os.path.exists(self._settings_path):
            return {}

        with open(self._settings_path, "r") as f:
            return json.loads(f.read())

    def _restore_state(self):
        """
        Restores gui's last state if the file is available.
        """
        data = self._fetch_settings()

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
                self.addDockWidget(area, self._inf_dock_widget)
        
        if "color_style" in data:
            self.color_style = data["color_style"]
            for i, widget in enumerate([self._max_color_action, self._maya_color_action, self._softimage_color_action]):
                widget.setChecked(i == self.color_style)

        if "mirror_mode.currentIndex" in data:
            self._mirror_mode.setCurrentIndex(data["mirror_mode.currentIndex"])

        if "mirror_surface.currentIndex" in data:
            self._mirror_surface.setCurrentIndex(data["mirror_surface.currentIndex"])

        if "mirror_inf.currentIndex" in data:
            self._mirror_inf.setCurrentIndex(data["mirror_inf.currentIndex"])

        if "weights_table.max_display_count" in data:
            self._weights_table.table_model.max_display_count = data["weights_table.max_display_count"]

        spinboxes = {
            "prune_spinbox.value": self._prune_spinbox,
            "smooth_strength_spinbox.value": self._smooth_strength_spinbox,
            "add_spinbox.value": self._add_spinbox,
            "scale_spinbox.value": self._scale_spinbox,
            "set_spinbox.value": self._set_spinbox
        }

        for key, spinbox in spinboxes.items():
            if key in data:
                spinbox.setValue(data[key])

        checkboxes = {
            "auto_update_button.isChecked": self._auto_update_table_action,
            "show_all_button.isChecked": self._show_all_button,
            "auto_select_button.isChecked": self.auto_select_vertex_action,
            "auto_select_infs_button.isChecked": self._auto_select_infs_action,
            "hide_colors_button.isChecked": self._hide_colors_button,
            "toggle_hotkeys_button.isChecked": self._toggle_hotkeys_button,
            "toggle_view_button.isChecked": self._toggle_view_button,
            "show_utilities_button.isChecked": self._show_utilities_button,
            "show_add_button.isChecked": self._show_add_button,
            "show_scale_button.isChecked": self._show_scale_button,
            "show_set_button.isChecked": self._show_set_button,
            "show_inf_button.isChecked": self._show_inf_button,
            "update_on_open_action.isChecked": self._update_on_open_action,
            "hide_long_names_action.isChecked": self._hide_long_names_action
        }

        for key, checkbox in checkboxes.items():
            if key in data:
                checkbox.setChecked(data[key])

        self._auto_update_on_toggled()

        if "hotkeys" in data:
            for hotkey in self._hotkeys:
                if hotkey.caption in data["hotkeys"]:
                    values = data["hotkeys"][hotkey.caption]
                    hotkey.ctrl = values["ctrl"]
                    hotkey.shift = values["shift"]
                    hotkey.alt = values["alt"]
                    hotkey.key = values["key"]

        if "add_presets_values" in data:
            self._add_preset_values = data["add_presets_values"]
        self._append_add_presets_buttons(self._add_preset_values)

        if "scale_presets_values" in data:
            self._scale_preset_values = data["scale_presets_values"]
        self._append_scale_presets_buttons(self._scale_preset_values)

        if "set_presets_values" in data:
            self._set_preset_values = data["set_presets_values"]
        self._append_set_presets_buttons(self._set_preset_values)
    
    def _update_obj(self, obj):
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
            self._in_component_mode = utils.is_in_component_mode()

            # Reset undo stack.
            self._undo_stack.clear()
            self._set_undo_buttons_enabled_state()

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
                    self.infs = self._get_all_infs()

            self._update_inf_list()

            caption = "Load object's skin data"
            if self.obj.is_valid():
                caption = self.obj.short_name()
            self._pick_obj_button.setText(caption)

            self._update_window_title()

            self._recollect_table_data(load_selection=False)
        finally:
            weights_view.end_update()

        if self.obj.is_valid():
            if self.infs:
                self._auto_assign_color_inf()

            if not self._hide_colors_button.isChecked() and self._in_component_mode:
                self.obj.switch_to_color_set()
                self.update_vert_colors()
            else:
                self.obj.hide_vert_colors()
    
    def _collect_inf_locks(self):
        """
        Collects a list of bools from active influences.
        """
        self.locks = [
            cmds.getAttr("{0}.lockInfluenceWeights".format(inf_name))
            for inf_name in self.infs
        ]
    
    def _toggle_inf_locks(self, infs, enabled):
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
        
        self._undo_stack.push(
            command_lock_infs.CommandLockInfs(
                self.__class__,
                description,
                infs,
                enabled))

        self._set_undo_buttons_enabled_state()
    
    def _get_all_infs(self):
        """
        Gets and returns a list of all influences from the active skinCluster.
        Also collects unique colors of each influence for the Softimage theme.
        """
        self.inf_colors = self.obj.collect_influence_colors()
        return sorted(self.obj.get_influences())
    
    def _get_selected_infs(self):
        """
        Gets and returns a list of influences that effects selected vertexes.
        """
        infs = set()

        if self.obj.has_valid_skin():
            for vert_index in self.vert_indexes:
                vert_infs = self.obj.skin_data.get_vertex_infs(vert_index)
                infs = infs.union(vert_infs)
        
        return sorted(list(infs))
    
    def _recollect_table_data(
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
                utils.get_vert_indexes(self.obj.name))
        
        if update_infs:
            self.collect_display_infs()
        
        if update_headers:
            weights_view.color_headers()

        weights_view.end_update()
        weights_view.emit_header_data_changed()

        if load_selection:
            if self._auto_select_infs_action.isChecked():
                weights_view.select_items_by_inf(self.color_inf)
            else:
                weights_view.load_table_selection(selection_data)

        weights_view.fit_headers_to_contents()
        
        self.ignore_cell_selection_event = False
    
    def _edit_weights(self, input_value, mode):
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
        old_skin_data = self.obj.skin_data.copy()

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

            self.obj.skin_data.update_weight_value(vert_index, inf, new_value)
            
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
            self.obj.name,
            old_skin_data,
            self.obj.skin_data.copy(),
            list(sel_vert_indexes),
            weights_view.save_table_selection())
    
    def _switch_color_style(self, color_theme):
        """
        Changes color display to a different theme.
        
        Args:
            color_theme(enums.ColorTheme)
        """
        self.color_style = color_theme

        if utils.is_in_component_mode():
            self.update_vert_colors()

        self._recollect_table_data(
            update_skin_data=False,
            update_verts=False,
            update_infs=False,
            load_selection=False)

    def _run_smooth(self, smooth_operation):
        """
        Smooths weights on selected vertexes with adjacent weights.

        Args:
            smooth_operation(SmoothOperation)
        """
        if not self.obj.is_valid():
            OpenMaya.MGlobal.displayWarning("No object to operate on.")
            return

        selected_vertexes = utils.extract_indexes(
            utils.get_vert_indexes(self.obj.name))

        if not selected_vertexes:
            OpenMaya.MGlobal.displayWarning("No vertexes are selected.")
            return

        old_skin_data = self.obj.skin_data.copy()

        weights_view = self.get_active_weights_view()
        table_selection = weights_view.save_table_selection()

        sel_vert_indexes = utils.extract_indexes(
            utils.get_vert_indexes(self.obj.name))

        if smooth_operation == SmoothOperation.Normal:
            self.obj.smooth_weights(
                selected_vertexes,
                self._smooth_strength_spinbox.value())

            self._recollect_table_data(update_skin_data=False, update_verts=False)

            undo_caption = "Smooth weights"
        else:
            # Re-collects all data since this smooth doesn't change internal data.
            utils.br_smooth_verts(self._smooth_strength_spinbox.value(), True)
            self._recollect_table_data()
            undo_caption = "Smooth weights (all influences)"

        self.update_vert_colors(vert_filter=selected_vertexes)

        new_skin_data = self.obj.skin_data.copy()

        self.add_undo_command(
            undo_caption,
            self.obj.name,
            old_skin_data,
            new_skin_data,
            sel_vert_indexes,
            table_selection,
            skip_first_redo=True)
    
    def _set_color_inf(self, inf):
        weights_view = self.get_active_weights_view()
        weights_view.begin_update()
        self.inf_list.begin_update()
        
        self.color_inf = inf

        self.inf_list.end_update()
        weights_view.end_update()

    def _auto_assign_color_inf(self):
        if self.infs:
            weights_view = self.get_active_weights_view()
            display_infs = weights_view.display_infs()

            if display_infs:
                self._set_color_inf(display_infs[0])
            else:
                self._set_color_inf(self.infs[0])

    def _update_inf_list(self):
        self.inf_list.begin_update()

        try:
            self.inf_list.list_model.clear()

            for i, inf in enumerate(sorted(self.infs)):
                item = QtGui.QStandardItem(inf)
                item.setToolTip(inf)
                item.setSizeHint(QtCore.QSize(1, 30))
                self.inf_list.list_model.appendRow(item)

            self._apply_filter_to_inf_list()
        finally:
            self.inf_list.end_update()
            self._update_inf_filter_items()

    def _update_inf_filter_items(self):
        items = self.inf_list.get_displayed_items()
        completer = QtWidgets.QCompleter(items, self)
        completer.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
        completer.setCompletionMode(QtWidgets.QCompleter.PopupCompletion)
        completer.setFilterMode(QtCore.Qt.MatchContains)
        self._inf_filter_edit.setCompleter(completer)

    def _apply_filter_to_inf_list(self):
        self.inf_list.apply_filter("*" + self._inf_filter_edit.text() + "*")

    def _mirror_weights(self, selection_only):
        if not self.obj.is_valid():
            return

        old_skin_data = self.obj.skin_data.copy()

        weights_view = self.get_active_weights_view()
        table_selection = weights_view.save_table_selection()

        if selection_only:
            vert_indexes = utils.extract_indexes(
                utils.get_vert_indexes(self.obj.name))
        else:
            vert_indexes = utils.extract_indexes(
                utils.get_all_vert_indexes(self.obj.name))

        mirror_mode = self._mirror_mode.currentText().lstrip("-")
        mirror_inverse = self._mirror_mode.currentText().startswith("-")

        surface_options = {
            "Closest Point": "closestPoint",
            "Ray Cast": "rayCast",
            "Closest Component": "closestComponent"
        }

        surface_association = surface_options[self._mirror_surface.currentText()]

        inf_options = {
            "Label": "label",
            "Closest Point": "closestJoint",
            "Closest Bone": "closestBone",
            "Name": "name",
            "One To One": "oneToOne"
        }

        inf_association = inf_options[self._mirror_inf.currentText()]

        self.obj.mirror_skin_weights(
            mirror_mode,
            mirror_inverse,
            surface_association,
            inf_association,
            vert_filter=vert_indexes)

        self._recollect_table_data(update_verts=False)

        vert_filter = vert_indexes if selection_only else []
        self.update_vert_colors(vert_filter=vert_filter)

        new_skin_data = self.obj.skin_data.copy()

        self.add_undo_command(
            "Mirror weights",
            self.obj.name,
            old_skin_data,
            new_skin_data,
            vert_indexes,
            table_selection,
            skip_first_redo=True)

    def _grow_selection(self):
        mel.eval("PolySelectTraverse 1;")

    def _shrink_selection(self):
        mel.eval("PolySelectTraverse 2;")

    def _select_perimeter(self):
        mel.eval("ConvertSelectionToVertexPerimeter;")

    def _select_edge_loop(self):
        mel.eval("SelectEdgeLoopSp;")

    def _select_shell(self):
        mel.eval("polyConvertToShell;")

    def _select_ring_loop(self):
        mel.eval("ConvertSelectionToContainedEdges;")
        mel.eval("SelectEdgeRingSp;")
        mel.eval("ConvertSelectionToVertices;")

    def _toggle_selected_inf_locks(self):
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
            self._toggle_inf_locks(infs, do_lock)

#
# Callbacks
#

    def _selection_on_changed(self, *args):
        """
        Triggers when user selects a new vertex in the viewport.
        Then refreshes table to be in sync.
        """
        # Check if the current object is valid.
        if self.obj.is_valid() and self.obj.has_valid_skin():
            # Toggle influence colors if component selection mode changes.
            now_in_component_mode = utils.is_in_component_mode()

            # No point to adjust colors if it's already disabled.
            if not self._hide_colors_button.isChecked():
                if now_in_component_mode != self._in_component_mode:  # Only continue if component mode was switched.
                    if now_in_component_mode:
                        self.update_vert_colors()
                    else:
                        self.obj.hide_vert_colors()

            self._in_component_mode = now_in_component_mode

            # Update table's data.
            if not self.block_selection_cb:
                self._recollect_table_data(update_skin_data=False)
    
    def _add_selection_callback(self):
        if self.cb_selection_changed is None:
            self.cb_selection_changed = OpenMaya.MEventMessage.addEventCallback(
                "SelectionChanged", self._selection_on_changed)
    
    def _remove_selection_callback(self):
        if self.cb_selection_changed is not None:
            OpenMaya.MEventMessage.removeCallback(self.cb_selection_changed)
            self.cb_selection_changed = None
    
#
# Events
#

    def closeEvent(self, *args):
        try:
            self._save_state()

            if self.obj.is_valid():
                utils.toggle_display_colors(self.obj.name, False)
                utils.delete_temp_inputs(self.obj.name)
        finally:
            self._remove_selection_callback()
            self._remove_shortcuts()
            self._del_prev_instance()
    
    def _pick_obj_on_clicked(self):
        obj = utils.get_selected_mesh()
        self._update_obj(obj)

    def _table_on_update_ended(self, over_limit):
        if self._limit_warning_label.isVisible() != over_limit:
            if over_limit:
                max_count = self._weights_table.table_model.max_display_count
                self._limit_warning_label.setText(
                    "Can only display {} rows! Go to settings to increase the limit.".format(max_count))
            self._limit_warning_label.setVisible(over_limit)

    def _weights_view_on_key_pressed(self, event):
        key_code = event.key() | event.modifiers()
        if key_code == self.toggle_inf_lock_key_code:
            self._toggle_selected_inf_locks()
        else:
            QtWidgets.QTableView.keyPressEvent(self.sender(), event)
    
    def _refresh_on_clicked(self):
        self._update_obj(self.obj.name)
    
    def _auto_update_on_toggled(self):
        enable_cb = self._auto_update_table_action.isChecked()
        
        if enable_cb:
            self._add_selection_callback()
        else:
            self._remove_selection_callback()

    def _set_limit_on_triggered(self):
        dialog = QtWidgets.QInputDialog(parent=self)
        dialog.setInputMode(QtWidgets.QInputDialog.IntInput)
        dialog.setIntRange(0, 99999)
        dialog.setIntValue(self._weights_table.table_model.max_display_count)
        dialog.setWindowTitle("Enter max row limit")
        dialog.setLabelText(
            "To help prevent the tool to freeze\n"
            "when selecting a large number of vertexes,\n"
            "a limit can be put in place. (table view only)\n")
        dialog.exec_()

        if dialog.result() == QtWidgets.QDialog.Accepted:
            self._weights_table.begin_update()
            self._weights_table.table_model.max_display_count = dialog.intValue()
            self._weights_table.end_update()

    def _header_on_middle_clicked(self, inf):
        """
        Sets active influence to color with.
        """
        if self.color_style == ColorTheme.Softimage:
            return

        self.inf_list.select_item(inf)
        self._set_color_inf(inf)
        self.update_vert_colors()
        self._recollect_table_data(
            update_skin_data=False,
            update_verts=False,
            update_infs=False,
            load_selection=False)

    def _select_by_infs_on_clicked(self):
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
    
    def _prune_on_clicked(self):
        if not self.obj.is_valid():
            return
        
        old_skin_data = self.obj.skin_data.copy()

        weights_view = self.get_active_weights_view()
        table_selection = weights_view.save_table_selection()
        
        sel_vert_indexes = utils.extract_indexes(
            utils.get_vert_indexes(self.obj.name))

        if not self.obj.prune_weights(self._prune_spinbox.value()):
            return
        
        self._recollect_table_data(update_verts=False)
        
        self.update_vert_colors(vert_filter=sel_vert_indexes)
        
        new_skin_data = self.obj.skin_data.copy()
        
        self.add_undo_command(
            "Prune weights",
            self.obj.name,
            old_skin_data,
            new_skin_data,
            sel_vert_indexes,
            table_selection,
            skip_first_redo=True)

    def _mirror_skin_on_clicked(self):
        self._mirror_weights(True)

    def _mirror_all_skin_on_clicked(self):
        self._mirror_weights(False)

    def _copy_vertex_on_clicked(self):
        if not self.obj.is_valid():
            return

        vert_indexes = utils.extract_indexes(
            utils.get_vert_indexes(self.obj.name))

        if not vert_indexes:
            OpenMaya.MGlobal.displayError("Need a vertex to be selected.")
            return

        vert_index = vert_indexes[0]
        self._copied_vertex = self.obj.skin_data.copy_vertex(vert_index)
        OpenMaya.MGlobal.displayInfo("Copied vertex {}".format(vert_index))

    def _paste_vertex_on_clicked(self):
        if self._copied_vertex is None:
            OpenMaya.MGlobal.displayError("Need to copy a vertex first.")
            return

        if not self.obj.is_valid():
            return

        vert_indexes = utils.extract_indexes(
            utils.get_vert_indexes(self.obj.name))

        if not vert_indexes:
            return

        weights_view = self.get_active_weights_view()
        table_selection = weights_view.save_table_selection()
        old_skin_data = self.obj.skin_data.copy()

        for vert_index in vert_indexes:
            self.obj.skin_data[vert_index] = copy.deepcopy(self._copied_vertex)

        new_skin_data = self.obj.skin_data.copy()

        self.add_undo_command(
            "Paste vertex",
            self.obj.name,
            old_skin_data,
            new_skin_data,
            vert_indexes,
            table_selection)

    def _set_add_on_clicked(self):
        self._edit_weights(self._add_spinbox.value(), WeightOperation.Relative)
    
    def _add_preset_on_clicked(self, value):
        self._add_spinbox.setValue(value)
        self._set_add_on_clicked()
    
    def _set_scale_on_clicked(self):
        perc = self._scale_spinbox.value()
        multiplier = utils.remap_range(-100.0, 100.0, 0.0, 2.0, perc)
        self._edit_weights(multiplier, WeightOperation.Percentage)
    
    def _scale_preset_on_clicked(self, perc):
        self._scale_spinbox.setValue(perc)
        self._set_scale_on_clicked()
    
    def _set_on_clicked(self):
        self._edit_weights(self._set_spinbox.value(), WeightOperation.Absolute)
    
    def _set_preset_on_clicked(self, value):
        self._set_spinbox.setValue(value)
        self._set_on_clicked()

    def _hide_colors_on_toggled(self, checked):
        if self.obj.is_valid() and self._in_component_mode:
            self.update_vert_colors()
            utils.toggle_display_colors(self.obj.name, not checked)

    def _flood_to_closest_on_clicked(self):
        if not self.obj.is_valid() or not self.obj.has_valid_skin():
            return

        old_skin_data = self.obj.skin_data.copy()

        weights_view = self.get_active_weights_view()
        table_selection = weights_view.save_table_selection()

        vert_indexes = utils.extract_indexes(
            utils.get_all_vert_indexes(self.obj.name))

        self.obj.flood_weights_to_closest()

        self._recollect_table_data(update_verts=False)
        self.update_vert_colors()

        new_skin_data = self.obj.skin_data.copy()

        self.add_undo_command(
            "Flood weights to closest",
            self.obj.name,
            old_skin_data,
            new_skin_data,
            vert_indexes,
            table_selection,
            skip_first_redo=True)

    def _hotkeys_on_toggled(self, checked):
        self._remove_shortcuts()

        if checked:
            self._toggle_hotkeys_button.setText("Hotkeys disabled")
        else:
            self._toggle_hotkeys_button.setText("Hotkeys enabled")
            self._register_shortcuts()

    def _switch_color_on_clicked(self, index):
        self._max_color_action.setChecked(index == ColorTheme.Max)
        self._maya_color_action.setChecked(index == ColorTheme.Maya)
        self._softimage_color_action.setChecked(index == ColorTheme.Softimage)
        self._switch_color_style(index)

    def _select_inf_verts_on_triggered(self, inf):
        if self.obj.is_valid():
            self.obj.select_inf_vertexes([inf])

    def _hide_long_names_on_triggered(self, visible):
        self.inf_list.toggle_long_names(visible)
        self._update_inf_filter_items()
        self._weights_list.toggle_long_names(visible)
        self._weights_table.toggle_long_names(visible)

    def _launch_hotkeys_on_clicked(self):
        status, dialog = hotkeys_dialog.HotkeysDialog.launch(self._hotkeys, self)
        if status:
            self._hotkeys = dialog.serialize()
            self._register_shortcuts()
        dialog.deleteLater()

    def _launch_presets_on_clicked(self):
        status, dialog = presets_dialog.PresetsDialog.launch(
            self._add_preset_values,
            self._scale_preset_values,
            self._set_preset_values,
            self)

        if status:
            presets = dialog.serialize()
            self._add_preset_values = presets["add"]
            self._scale_preset_values = presets["scale"]
            self._set_preset_values = presets["set"]
            self._append_add_presets_buttons(self._add_preset_values)
            self._append_scale_presets_buttons(self._scale_preset_values)
            self._append_set_presets_buttons(self._set_preset_values)

        dialog.deleteLater()

    def _about_on_triggered(self):
        dialog = about_dialog.AboutDialog.launch(self.version, self)
        dialog.deleteLater()

    def _github_page_on_triggered(self):
        webbrowser.open(constants.GITHUB_HOME)

    def _toggle_view_on_toggled(self, enabled):
        self._limit_warning_label.setVisible(False)
        self._weights_list.setVisible(not enabled)
        self._weights_table.setVisible(enabled)

        if enabled:
            self._toggle_view_button.setText("TABLE")
            self._toggle_view_button.setIcon(utils.load_pixmap("interface/table.png"))
        else:
            self._toggle_view_button.setText("LIST")
            self._toggle_view_button.setIcon(utils.load_pixmap("interface/list.png"))

        self._recollect_table_data()

    def _show_utilities_on_toggled(self, enabled):
        self._weight_groupbox.setVisible(enabled)

    def _show_add_on_toggled(self, enabled):
        self._add_groupbox.setVisible(enabled)

    def _show_scale_on_toggled(self, enabled):
        self._scale_groupbox.setVisible(enabled)

    def _show_set_on_toggled(self, enabled):
        self._set_groupbox.setVisible(enabled)

    def _show_inf_on_toggled(self, enabled):
        self._inf_dock_widget.setVisible(enabled)
    
    def _undo_on_click(self):
        if not self._undo_stack.canUndo():
            OpenMaya.MGlobal.displayError("There are no more commands to undo.")
            return
        
        self._undo_stack.undo()
        self._set_undo_buttons_enabled_state()
    
    def _redo_on_click(self):
        if not self._undo_stack.canRedo():
            OpenMaya.MGlobal.displayError("There are no more commands to redo.")
            return
        
        self._undo_stack.redo()
        self._set_undo_buttons_enabled_state()
    
    def _inf_list_on_middle_clicked(self, inf):
        if inf in self.infs:
            self._set_color_inf(inf)
            self.update_vert_colors()

    def _inf_list_on_toggle_locks_triggered(self, infs):
        if infs[0] not in self.infs:
            OpenMaya.MGlobal.displayError("Unable to find influence in internal data.. Is it out of sync?")
            return

        inf_index = self.infs.index(infs[0])
        lock = not self.locks[inf_index]
        self._toggle_inf_locks(infs, lock)

    def _add_inf_to_vert_on_clicked(self):
        """
        Adds a very small weight value from selected influences to selected vertexes.
        """
        if not self.obj.is_valid():
            OpenMaya.MGlobal.displayError("There's no active object to work on.")
            return
        
        sel_vert_indexes = utils.extract_indexes(utils.get_vert_indexes(self.obj.name))
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
        
        old_skin_data = self.obj.skin_data.copy()

        weights_view = self.get_active_weights_view()
        table_selection = weights_view.save_table_selection()
        
        # Add infs by setting a very low value so it doesn't effect other weights too much.
        for inf in sel_infs:
            for vert_index in sel_vert_indexes:
                weight_data = self.obj.skin_data[vert_index]["weights"]
                if weight_data.get(inf) is None:
                    self.obj.skin_data.update_weight_value(vert_index, inf, 0.001)

        new_skin_data = self.obj.skin_data.copy()

        self.add_undo_command(
            "Add influence to verts",
            self.obj.name,
            old_skin_data,
            new_skin_data,
            sel_vert_indexes,
            table_selection)
        
        self._recollect_table_data(update_skin_data=False, update_verts=False)

    def _display_inf_on_triggered(self, inf):
        if self.color_style == ColorTheme.Softimage:
            return

        self._set_color_inf(inf)
        self.update_vert_colors()

        self._recollect_table_data(
            update_skin_data=False,
            update_verts=False,
            update_infs=False,
            load_selection=False)

#
# Public methods
#

    def get_active_weights_view(self):
        if self._toggle_view_button.isChecked():
            return self._weights_table
        else:
            return self._weights_list

    def collect_display_infs(self):
        """
        Sets influences to be shown in the table.
        """
        weights_view = self.get_active_weights_view()

        if self._show_all_button.isChecked():
            weights_view.set_display_infs(self._get_all_infs())
        else:
            weights_view.set_display_infs(self._get_selected_infs())

        self._collect_inf_locks()

    def update_vert_colors(self, vert_filter=[]):
        """
        Displays active influence.

        Args:
            vert_filter(int[]): List of vertex indexes to only operate on.
        """
        if self._hide_colors_button.isChecked():
            return

        if self.obj.is_valid():
            if utils.is_curve(self.obj.name):
                return

        if not self.infs:
            return

        if self.color_inf is None:
            self._auto_assign_color_inf()

        if self.color_style == ColorTheme.Softimage:
            self._set_color_inf(None)

            self.obj.display_multi_color_influence(
                inf_colors=self.inf_colors,
                vert_filter=vert_filter)
        else:
            if self.color_inf is not None:
                self.obj.display_influence(
                    self.color_inf,
                    color_style=self.color_style,
                    vert_filter=vert_filter)

        utils.toggle_display_colors(self.obj.name, True)

    def add_undo_command(
            self, description, obj, old_skin_data, new_skin_data, vert_indexes,
            table_selection, skip_first_redo=False):

        self._undo_stack.push(
            command_edit_weights.CommandEditWeights(
                self.__class__,
                description,
                obj,
                old_skin_data,
                new_skin_data,
                vert_indexes,
                table_selection,
                skip_first_redo=skip_first_redo))

        self._set_undo_buttons_enabled_state()


def run():
    WeightsEditor.run()
