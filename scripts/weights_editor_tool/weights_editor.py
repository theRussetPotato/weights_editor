"""
A tool to edit skin weights on a vertex level.

Author:
    Jason Labbe

Credits:
    Enrique Caballero and John Lienard for pushing me to make this.
    
    Ingo Clemens (Brave Rabbit) for his smoothSkinClusterWeight plugin.
    http://www.braverabbit.com/smoothskinclusterweight
    
    Tyler Thornock for his tutorial on a faster approach to get/set skin weights.
    http://www.charactersetup.com/tutorial_skinWeights.html

Notes:
    - This tool may not fair well with high dense meshes.
      Use paint weights to get your skinning 80% there, then use this tool for polishing.
    
    - Internal data does not sync if weights or influences are externally modified.
      ie: can't paint weights while tool is open

Example of usage:
    import weights_editor
    weights_editor.run()
"""

import os
import copy
import random
import json
import fnmatch

import maya.cmds as cmds
import maya.mel as mel
import maya.OpenMaya as OpenMaya
import maya.OpenMayaUI as OpenMayaUI

from resources import variables

if variables.qt_version > 4:
    from shiboken2 import wrapInstance
    from PySide2 import QtGui
    from PySide2 import QtCore
    from PySide2 import QtWidgets
else:
    from shiboken import wrapInstance
    from PySide import QtGui
    from PySide import QtCore
    QtWidgets = QtGui

import weights_editor_utils as utils
from classes import custom_double_spinbox
from classes import custom_header_view
from classes import custom_menu
from classes import groupbox_frame
from classes import inf_list_view
from classes import weights_table_view


class CommandEditWeights(QtWidgets.QUndoCommand):
    
    """
    Command to edit skin weights.
    
    TODO:
        This could be a lot more optimized by only using skin data from selected vetexes!
    
    Args:
        description (string): The label to show up to describe this action.
        obj (string): An object with a skinCluster to edit weights on.
        old_skin_data (dict): A copy of skin data to revert to.
        new_skin_data (dict): A copy of skin data to set to.
        vert_indexes (int[]): A list of indexes to operate on.
        table_selection (dict): Selection data to revert back to.
        skip_first_redo (bool): Qt forces redo to be executed right away. Enable this to skip it if it's not needed.
    """
    
    def __init__(self, description, obj, old_skin_data, new_skin_data, vert_indexes, table_selection, skip_first_redo=False, parent=None):
        super(CommandEditWeights, self).__init__(description, parent=parent)
        
        self.skip_first_redo = skip_first_redo
        
        self.obj = obj
        self.old_skin_data = old_skin_data
        self.new_skin_data = new_skin_data
        self.vert_indexes = vert_indexes
        self.table_selection = table_selection
    
    def redo(self):
        if self.skip_first_redo:
            self.skip_first_redo = False
            return
        
        if not self.obj or not cmds.objExists(self.obj):
            return
        
        old_column_count = WeightsEditor.instance.table.horizontalHeader().count()
        
        WeightsEditor.instance.table_model.begin_update()
        
        WeightsEditor.instance.skin_data = self.new_skin_data
        
        utils.set_skin_weights(self.obj, self.new_skin_data, self.vert_indexes, normalize=True)
        
        WeightsEditor.instance.draw_inf(filter=self.vert_indexes)
        
        WeightsEditor.instance.collect_display_infs()
        
        WeightsEditor.instance.load_table_selection(self.table_selection)
        
        WeightsEditor.instance.table_model.end_update()
        
        if WeightsEditor.instance.table.horizontalHeader().count() != old_column_count:
            WeightsEditor.instance.resize_columns()
    
    def undo(self):
        if not self.obj or not cmds.objExists(self.obj):
            return
        
        old_column_count = WeightsEditor.instance.table.horizontalHeader().count()
        
        WeightsEditor.instance.table_model.begin_update()
        
        WeightsEditor.instance.skin_data = self.old_skin_data
        utils.set_skin_weights(self.obj, self.old_skin_data, self.vert_indexes, normalize=True)
        
        WeightsEditor.instance.draw_inf(filter=self.vert_indexes)
        
        WeightsEditor.instance.collect_display_infs()
        
        WeightsEditor.instance.load_table_selection(self.table_selection)
        
        WeightsEditor.instance.table_model.end_update()
        
        if WeightsEditor.instance.table.horizontalHeader().count() != old_column_count:
            WeightsEditor.instance.resize_columns()


class CommandLockInfs(QtWidgets.QUndoCommand):
    
    """
    Command to toggle influence locks.
    
    Args:
        description (string): The label to show up to describe this action.
        infs (string[]): A list of influence objects to operate on.
        enabled (bool): The state to set all the new locks to.
    """
    
    def __init__(self, description, infs, enabled, parent=None):
        super(CommandLockInfs, self).__init__(description, parent=parent)
        
        # {inf_name, default_lock_state}
        self.infs = {inf:cmds.getAttr("{0}.lockInfluenceWeights".format(inf)) for inf in infs}
        
        self.enabled = enabled
    
    def redo(self):
        WeightsEditor.instance.table_model.begin_update()
        WeightsEditor.instance.inf_list_model.layoutAboutToBeChanged.emit()
        
        for inf in self.infs:
            if not cmds.objExists(inf) or inf not in WeightsEditor.instance.infs:
                continue
            
            cmds.setAttr("{0}.lockInfluenceWeights".format(inf), self.enabled)
            
            inf_index = WeightsEditor.instance.infs.index(inf)
            
            WeightsEditor.instance.locks[inf_index] = self.enabled
        
        WeightsEditor.instance.inf_list_model.layoutChanged.emit()
        WeightsEditor.instance.table_model.end_update()
    
    def undo(self):
        WeightsEditor.instance.table_model.begin_update()
        WeightsEditor.instance.inf_list_model.layoutAboutToBeChanged.emit()
        
        for inf, enabled in self.infs.items():
            if not cmds.objExists(inf) or inf not in WeightsEditor.instance.infs:
                continue
            
            cmds.setAttr("{0}.lockInfluenceWeights".format(inf), enabled)
            
            inf_index = WeightsEditor.instance.infs.index(inf)
            
            WeightsEditor.instance.locks[inf_index] = enabled
        
        WeightsEditor.instance.inf_list_model.layoutChanged.emit()
        WeightsEditor.instance.table_model.end_update()


class WeightsEditor(QtWidgets.QMainWindow):
    
    """
    The main tool.
    """
    
    version = "1.0.0"
    instance = None
    cb_selection_changed = None
    
    def __init__(self, parent=None):
        QtWidgets.QMainWindow.__init__(self, parent=parent)
        
        self.del_prev_instance()
        self.__class__.instance = self
        
        self.maya_main_window = wrapInstance(long(OpenMayaUI.MQtUtil.mainWindow()), QtWidgets.QMainWindow)
        self.setParent(self.maya_main_window)
        self.setWindowFlags(QtCore.Qt.Window)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.setObjectName("weightsEditor")
        
        self.undo_stack = QtWidgets.QUndoStack(parent=self)
        self.undo_stack.setUndoLimit(30)
        
        self._in_component_mode = cmds.selectMode(q=True, component=True)
        
        self.obj = None
        self.skin_cluster = None
        self.skin_data = {}
        self.vert_indexes = []
        self.vert_count = None
        self.infs = []
        self.display_infs = []
        self.color_inf = None
        self.locks = []
        self.selected_rows = set()
        self.color_style = 0
        self.inf_colors = {}
        self.block_selection_cb = False
        
        # Any other keys will give focus to Maya
        self.accept_keys = [ord(char) for char in [">", "<", " ", "S", "E", "A", "R"]]
        
        self.settings_path = os.path.join(os.getenv("HOME"), "maya", "weights_editor.json")
        
        self.create_gui()
        self.setup_gui()
    
    def setup_gui(self):
        self.restore_state()
        self.auto_update_on_toggled()
        self.set_undo_buttons_enabled_state()
        self.pick_obj_on_clicked()
    
    def del_prev_instance(self):
        """
        Deletes any previous window.
        """
        if self.__class__.instance is not None:
            try:
                self.__class__.instance.close()
            finally:
                self.__class__.instance = None
    
    def create_gui(self):
        """
        Creates and sets up the interface.
        """
    #
    # MENU BAR
    #
        self.menu_bar = self.menuBar()
        self.menu_bar.setStyleSheet("QMenuBar {background-color:rgb(100, 100, 100)}")
        
        self.options_menu = custom_menu.CustomMenu("&Tool settings", parent=self)
        self.options_menu.showing.connect(self.options_menu_on_showing)
        self.menu_bar.addMenu(self.options_menu)
        
        self.auto_update_table_action = QtWidgets.QAction("Auto-update table when selecting in viewport", self)
        self.auto_update_table_action.setCheckable(True)
        self.auto_update_table_action.setChecked(True)
        self.auto_update_table_action.triggered.connect(self.auto_update_on_toggled)
        self.options_menu.addAction(self.auto_update_table_action)
        
        self.auto_select_vertex_action = QtWidgets.QAction("Auto-select vertexes when selecting table items", self)
        self.auto_select_vertex_action.setCheckable(True)
        self.options_menu.addAction(self.auto_select_vertex_action)
        
        self.auto_select_infs_action = QtWidgets.QAction("Auto-select table items from active influence", self)
        self.auto_select_infs_action.setCheckable(True)
        self.auto_select_infs_action.setChecked(True)
        self.options_menu.addAction(self.auto_select_infs_action)
        
        self.color_separator = QtWidgets.QAction("Color settings", self)
        self.color_separator.setSeparator(True)
        self.options_menu.addAction(self.color_separator)
        
        self.color_sub_menu = self.options_menu.addMenu("Switch influence color style")
        
        self.max_color_action = QtWidgets.QAction("3dsMax theme", self)
        self.max_color_action.setCheckable(True)
        self.max_color_action.setChecked(True)
        self.max_color_action.triggered.connect(lambda value=0: self.switch_color_on_clicked(value))
        self.color_sub_menu.addAction(self.max_color_action)
        
        self.maya_color_action = QtWidgets.QAction("Maya theme", self)
        self.maya_color_action.setCheckable(True)
        self.maya_color_action.triggered.connect(lambda value=1: self.switch_color_on_clicked(value))
        self.color_sub_menu.addAction(self.maya_color_action)
        
        self.softimage_color_action = QtWidgets.QAction("Softimage theme", self)
        self.softimage_color_action.setCheckable(True)
        self.softimage_color_action.triggered.connect(lambda value=2: self.switch_color_on_clicked(value))
        self.color_sub_menu.addAction(self.softimage_color_action)
        
        self.visibility_separator = QtWidgets.QAction("Visibility settings", self)
        self.visibility_separator.setSeparator(True)
        self.options_menu.addAction(self.visibility_separator)
        
        self.toggle_inf_window_action = QtWidgets.QAction("Influence window's visibility", self)
        self.toggle_inf_window_action.setCheckable(True)
        self.toggle_inf_window_action.toggled.connect(self.toggle_inf_window_on_clicked)
        self.options_menu.addAction(self.toggle_inf_window_action)
        
        self.help_menu = self.menu_bar.addMenu("&Help")
        
        self.about_controls_action = QtWidgets.QAction("Controls && hotkeys", self)
        self.about_controls_action.triggered.connect(self.about_controls_on_clicked)
        self.help_menu.addAction(self.about_controls_action)
        
        self.about_action = QtWidgets.QAction("About", self)
        self.about_action.triggered.connect(self.about_on_clicked)
        self.help_menu.addAction(self.about_action)
    #
    # CENTRAL WIDGET
    #
        
        self.central_widget = QtWidgets.QWidget(parent=self)
        self.central_widget.setObjectName("weightsEditorCentralWidget")
        
        self.pick_obj_button = QtWidgets.QPushButton("", parent=self.central_widget)
        self.pick_obj_button.setToolTip("Select a mesh, then press here to begin editing it.")
        self.pick_obj_button.clicked.connect(self.pick_obj_on_clicked)
        
        self.skin_cluster_label = QtWidgets.QLabel("", parent=self.central_widget)
        self.vert_count_label = QtWidgets.QLabel("", parent=self.central_widget)
        
        self.info_layout = QtWidgets.QGridLayout()
        self.info_layout.addWidget(QtWidgets.QLabel("Object:", parent=self.central_widget), 0, 0)
        self.info_layout.addWidget(self.pick_obj_button, 0, 1)
        self.info_layout.addItem(QtWidgets.QSpacerItem(50, 0, QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Preferred), 0, 2)
        self.info_layout.addWidget(QtWidgets.QLabel("Skin:", parent=self.central_widget), 0, 3)
        self.info_layout.addWidget(self.skin_cluster_label, 0, 4)
        self.info_layout.addItem(QtWidgets.QSpacerItem(50, 0, QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Preferred), 0, 5)
        self.info_layout.addWidget(QtWidgets.QLabel("Vertex count:", parent=self.central_widget), 0, 6)
        self.info_layout.addWidget(self.vert_count_label, 0, 7)
        self.info_layout.addItem(QtWidgets.QSpacerItem(0, 0, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred), 0, 8)
        
        self.object_groupbox = QtWidgets.QGroupBox("Info", parent=self.central_widget)
        self.object_groupbox.setLayout(self.info_layout)
        
        self.smooth_button = QtWidgets.QPushButton("Smooth vertexes (vert's infs)", parent=self.central_widget)
        self.smooth_button.setToolTip("Selected vertexes in the viewport will smooth with only influences that are already assigned to it.")
        self.smooth_button.clicked.connect(self.run_smooth)
        
        self.smooth_br_button = QtWidgets.QPushButton("Smooth vertexes (all infs)", parent=self.central_widget)
        self.smooth_br_button.setToolTip("Selected vertexes in the viewport will smooth with all influences available.")
        self.smooth_br_button.clicked.connect(self.run_br_smooth)
        
        if not cmds.pluginInfo("smoothSkinClusterWeight", q=True, loaded=True):
            self.smooth_br_button.setEnabled(False)
        
        self.prune_spinbox = QtWidgets.QDoubleSpinBox(value=0.1, parent=self.central_widget)
        self.prune_spinbox.setMinimum(0.01)
        self.prune_spinbox.setSingleStep(0.01)
        self.prune_spinbox.setFixedWidth(80)
        
        self.prune_button = QtWidgets.QPushButton("Prune vertexes", parent=self.central_widget)
        self.prune_button.setToolTip("Prunes selected vertexes in the viewport that are below this value.")
        self.prune_button.clicked.connect(self.prune_on_clicked)
        
        self.weight_layout = QtWidgets.QGridLayout()
        self.weight_layout.addWidget(self.prune_button, 0, 2)
        self.weight_layout.addWidget(self.prune_spinbox, 0, 3)
        self.weight_layout.addItem(QtWidgets.QSpacerItem(0, 0, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred), 0, 4)
        self.weight_layout.addWidget(self.smooth_button, 0, 0)
        self.weight_layout.addWidget(self.smooth_br_button, 0, 1)
        
        self.weight_frame = groupbox_frame.GroupboxFrame(parent=self)
        self.weight_frame.setLayout(self.weight_layout)
        
        self.weight_frame_layout = QtWidgets.QVBoxLayout()
        self.weight_frame_layout.setContentsMargins(0, 0, 0, 0)
        self.weight_frame_layout.addWidget(self.weight_frame)
        
        self.weight_groupbox = QtWidgets.QGroupBox("Weight utilities", parent=self.central_widget)
        self.weight_groupbox.setCheckable(True)
        self.weight_groupbox.setLayout(self.weight_frame_layout)
        self.weight_groupbox.toggled.connect(self.groupbox_on_toggle)
        
        empty_color = QtGui.QColor(50, 50, 150)
        full_color = QtGui.QColor(50, 150, 50)
        
        # Procedurally create presets for add/subtract values
        self.add_spinbox = custom_double_spinbox.CustomDoubleSpinbox(parent=self.central_widget)
        self.add_spinbox.setSingleStep(0.1)
        self.add_spinbox.setFixedSize(90, 35)
        self.add_spinbox.setMinimum(-1.0)
        self.add_spinbox.setMaximum(1.0)
        self.add_spinbox.enter_pressed.connect(self.set_add_on_clicked)
        
        add_preset_values = [-0.75, -0.5, -0.25, -0.1, 0.1, 0.25, 0.5, 0.75]
        
        self.add_layout = QtWidgets.QHBoxLayout()
        self.add_layout.addWidget(self.add_spinbox)
        
        for i, value in enumerate(add_preset_values):
            blend_value = float(i)/(len(add_preset_values)-1)
            button_color = utils.lerp_color(empty_color, full_color, blend_value)
            
            preset_button = QtWidgets.QPushButton("{0}".format(value), parent=self.central_widget)
            preset_button.setMinimumWidth(50)
            preset_button.setStyleSheet("QPushButton {background-color:rgb(%s, %s, %s)}" % (
                button_color.red(),
                button_color.green(),
                button_color.blue()))
            if value > 0:
                tooltip = "Add {0} on selected cells.".format(value)
            else:
                tooltip = "Subtract {0} on selected cells.".format(abs(value))
            preset_button.setToolTip(tooltip)
            preset_button.clicked.connect(lambda value=value: self.add_preset_on_clicked(value))
            self.add_layout.addWidget(preset_button)
        
        self.add_layout.addStretch()
        
        self.add_frame = groupbox_frame.GroupboxFrame(parent=self)
        self.add_frame.setLayout(self.add_layout)
        
        self.add_frame_layout = QtWidgets.QVBoxLayout()
        self.add_frame_layout.setContentsMargins(0, 0, 0, 0)
        self.add_frame_layout.addWidget(self.add_frame)
        
        self.add_groupbox = QtWidgets.QGroupBox("Add / subtract weight", parent=self.central_widget)
        self.add_groupbox.setCheckable(True)
        self.add_groupbox.setLayout(self.add_frame_layout)
        self.add_groupbox.toggled.connect(self.groupbox_on_toggle)
        
        # Procedurally create presets for scale
        self.scale_spinbox = custom_double_spinbox.CustomDoubleSpinbox(parent=self.central_widget)
        self.scale_spinbox.setFixedSize(90, 35)
        self.scale_spinbox.setSuffix("%")
        self.scale_spinbox.setSingleStep(10)
        self.scale_spinbox.setMinimum(-100)
        self.scale_spinbox.setMaximum(100)
        self.scale_spinbox.enter_pressed.connect(self.set_scale_on_clicked)
        
        scale_preset_values = [-50, -25, -10, -5, 5, 10, 25, 50]
        
        self.scale_layout = QtWidgets.QHBoxLayout()
        self.scale_layout.addWidget(self.scale_spinbox)
        
        for i, value in enumerate(scale_preset_values):
            blend_value = float(i)/(len(scale_preset_values)-1)
            button_color = utils.lerp_color(empty_color, full_color, blend_value)
            
            preset_button = QtWidgets.QPushButton("{0}%".format(value), parent=self.central_widget)
            preset_button.setMinimumWidth(50)
            preset_button.setStyleSheet("QPushButton {background-color:rgb(%s, %s, %s)}" % (button_color.red(),
                                                                                            button_color.green(),
                                                                                            button_color.blue()))
            if value > 0:
                tooltip = "Add {0}% on selected cells.".format(value)
            else:
                tooltip = "Subtract {0}% on selected cells.".format(abs(value))
            preset_button.setToolTip(tooltip)
            preset_button.clicked.connect(lambda value=value: self.scale_preset_on_clicked(value))
            self.scale_layout.addWidget(preset_button)
        
        self.scale_layout.addStretch()
        
        self.scale_frame = groupbox_frame.GroupboxFrame(parent=self)
        self.scale_frame.setLayout(self.scale_layout)
        
        self.scale_frame_layout = QtWidgets.QVBoxLayout()
        self.scale_frame_layout.setContentsMargins(0, 0, 0, 0)
        self.scale_frame_layout.addWidget(self.scale_frame)
        
        self.scale_groupbox = QtWidgets.QGroupBox("Scale weight", parent=self.central_widget)
        self.scale_groupbox.setCheckable(True)
        self.scale_groupbox.setLayout(self.scale_frame_layout)
        self.scale_groupbox.toggled.connect(self.groupbox_on_toggle)
        
        # Procedurally create presets for set
        self.set_spinbox = custom_double_spinbox.CustomDoubleSpinbox(parent=self.central_widget)
        self.set_spinbox.setSingleStep(0.1)
        self.set_spinbox.setFixedSize(90, 35)
        self.set_spinbox.setMinimum(0)
        self.set_spinbox.setMaximum(1.0)
        self.set_spinbox.enter_pressed.connect(self.set_on_clicked)
        
        set_preset_values = [0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0]
        
        self.set_layout = QtWidgets.QHBoxLayout()
        self.set_layout.addWidget(self.set_spinbox)
        
        for i, value in enumerate(set_preset_values):
            blend_value = float(i)/(len(set_preset_values)-1)
            button_color = utils.lerp_color(empty_color, full_color, blend_value)
            
            preset_button = QtWidgets.QPushButton("{0}".format(value), parent=self.central_widget)
            preset_button.setMinimumWidth(50)
            
            preset_button.setStyleSheet("QPushButton {background-color:rgb(%s, %s, %s)}" % (button_color.red(),
                                                                                            button_color.green(),
                                                                                            button_color.blue()))
            tooltip = "Set {0} on selected cells.".format(value)
            preset_button.setToolTip(tooltip)
            preset_button.clicked.connect(lambda value=value: self.set_preset_on_clicked(value))
            self.set_layout.addWidget(preset_button)
        
        self.set_layout.addStretch()
        
        self.set_frame = groupbox_frame.GroupboxFrame(parent=self)
        self.set_frame.setLayout(self.set_layout)
        
        self.set_frame_layout = QtWidgets.QVBoxLayout()
        self.set_frame_layout.setContentsMargins(0, 0, 0, 0)
        self.set_frame_layout.addWidget(self.set_frame)
        
        self.set_groupbox = QtWidgets.QGroupBox("Set weight", parent=self.central_widget)
        self.set_groupbox.setCheckable(True)
        self.set_groupbox.setLayout(self.set_frame_layout)
        self.set_groupbox.toggled.connect(self.groupbox_on_toggle)
        
        # Setup table
        self.ignore_cell_selection_event = False
        
        self.table = weights_table_view.TableView(parent=self)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.key_pressed.connect(self.window_on_key_pressed)
        self.table.selection_changed.connect(self.cell_selection_on_changed)
        
        self.top_header = custom_header_view.CustomHeaderView(parent=self.table)
        
        if variables.qt_version > 4:
            self.top_header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        else:
            self.top_header.setResizeMode(QtWidgets.QHeaderView.ResizeToContents)
            
        self.top_header.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.top_header.customContextMenuRequested.connect(self.header_on_context_trigger)
        self.table.setHorizontalHeader(self.top_header)
        self.top_header.header_left_clicked.connect(self.top_header_on_l_clicked)
        self.top_header.header_middle_clicked.connect(self.top_header_on_m_clicked)
        
        self.table_model = weights_table_view.TableModel(parent=self)
        self.table.setModel(self.table_model)
        
        # 1st row
        self.update_button = QtWidgets.QPushButton("Update table", parent=self.central_widget)
        self.update_button.setToolTip("Refreshes the table with selected vertexes from the viewport.")
        self.update_button.clicked.connect(self.update_on_clicked)
        
        # 2nd row
        self.show_all_button = QtWidgets.QPushButton("Show all influences", parent=self.central_widget)
        self.show_all_button.setCheckable(True)
        self.show_all_button.setToolTip("Forces the table to show all influences.")
        self.show_all_button.clicked.connect(self.update_on_clicked)
        
        self.hide_colors_button = QtWidgets.QPushButton("Hide influence colors", parent=self.central_widget)
        self.hide_colors_button.setCheckable(True)
        self.hide_colors_button.setToolTip("Hides colors that visualize the weight values.\n"
                                           "Enable this to help speed up performance.")
        self.hide_colors_button.clicked.connect(self.hide_colors_on_clicked)
        
        # Undo buttons
        self.undo_button = QtWidgets.QPushButton("Undo", parent=self.central_widget)
        self.undo_button.clicked.connect(self.undo_on_click)
        self.undo_button.setFixedHeight(60)
        
        self.redo_button = QtWidgets.QPushButton("Redo", parent=self.central_widget)
        self.redo_button.clicked.connect(self.redo_on_click)
        self.redo_button.setFixedHeight(60)
        
        self.undo_layout = QtWidgets.QHBoxLayout()
        self.undo_layout.addWidget(self.undo_button)
        self.undo_layout.addWidget(self.redo_button)
        
        self.settings_layout = QtWidgets.QHBoxLayout()
        self.settings_layout.addWidget(self.show_all_button)
        self.settings_layout.addWidget(self.hide_colors_button)
        
        self.main_layout = QtWidgets.QVBoxLayout()
        self.main_layout.addWidget(self.object_groupbox)
        self.main_layout.addWidget(self.weight_groupbox)
        self.main_layout.addWidget(self.add_groupbox)
        self.main_layout.addWidget(self.scale_groupbox)
        self.main_layout.addWidget(self.set_groupbox)
        self.main_layout.addWidget(self.table)
        self.main_layout.addWidget(self.update_button)
        self.main_layout.addLayout(self.settings_layout)
        self.main_layout.addLayout(self.undo_layout)
        self.main_layout.setSpacing(3)
        self.central_widget.setLayout(self.main_layout)
    
    #
    # TABLE'S CONTEXT MENU
    #
        
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
        self.sort_weights_ascending_action.setText("Sort weights (ascending)")
        self.sort_weights_ascending_action.triggered.connect(self.sort_ascending_on_triggered)
        
        self.sort_weights_descending_action = QtWidgets.QAction(self)
        self.sort_weights_descending_action.setText("Sort weights (descending)")
        self.sort_weights_descending_action.triggered.connect(self.sort_descending_on_triggered)
        
        self.sort_weights_vert_order_action = QtWidgets.QAction(self)
        self.sort_weights_vert_order_action.setText("Sort weights (vertex order)")
        self.sort_weights_vert_order_action.triggered.connect(self.sort_vert_order_on_triggered)
        
        self.header_context_menu = QtWidgets.QMenu(parent=self.table)
        self.header_context_menu.addAction(self.display_inf_action)
        self.header_context_menu.addSeparator()
        self.header_context_menu.addAction(self.select_inf_verts_action)
        self.header_context_menu.addAction(self.select_inf_action)
        self.header_context_menu.addSeparator()
        self.header_context_menu.addAction(self.sort_weights_ascending_action)
        self.header_context_menu.addAction(self.sort_weights_descending_action)
        self.header_context_menu.addAction(self.sort_weights_vert_order_action)
        
        self.setCentralWidget(self.central_widget)
        
    #
    # INFLUENCE WIDGET
    #
        
        self.inf_dock_widget = QtWidgets.QDockWidget(parent=self)
        self.setObjectName("weightsEditorInfluenceWidget")
        self.inf_dock_widget.setFeatures(QtWidgets.QDockWidget.DockWidgetMovable | QtWidgets.QDockWidget.DockWidgetClosable)
        self.inf_dock_widget.setWindowTitle("Influences")
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.inf_dock_widget)
        
        self.inf_widget = QtWidgets.QWidget(parent=self.inf_dock_widget)
        self.inf_dock_widget.setWidget(self.inf_widget)
        
        self.inf_filter_edit = QtWidgets.QLineEdit(parent=self.inf_widget)
        self.inf_filter_edit.setPlaceholderText("Filter list by names (use * as a wildcard)")
        self.inf_filter_edit.textEdited.connect(self.apply_filter_to_inf_list)
        
        self.inf_list = inf_list_view.InfListView(parent=self.inf_widget)
        self.inf_list.setAlternatingRowColors(True)
        self.inf_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.inf_list.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.inf_list.doubleClicked.connect(self.on_inf_double_click)
        self.inf_list.middle_clicked.connect(self.on_inf_middle_clicked)
        self.inf_list.key_pressed.connect(self.on_inf_key_pressed)
        
        self.inf_list.setStyleSheet("QListView::item {color:None;}")
        
        self.inf_list_model = inf_list_view.InfListModel(parent=self.inf_list)
        self.inf_list.setModel(self.inf_list_model)
        
        self.add_inf_to_vert_button = QtWidgets.QPushButton("Add inf to vertexes", parent=self.inf_widget)
        self.add_inf_to_vert_button.setToolTip("Adds the selected influence to all selected vertexes.")
        self.add_inf_to_vert_button.clicked.connect(self.add_inf_to_vert_on_clicked)
        
        self.select_by_infs_button = QtWidgets.QPushButton("Select vertexes effected by influences", parent=self.inf_widget)
        self.select_by_infs_button.setToolTip("Selects all vertexes that is effected by the selected influences.")
        self.select_by_infs_button.clicked.connect(self.select_by_infs_on_clicked)
        
        self.inf_layout = QtWidgets.QVBoxLayout()
        self.inf_layout.addWidget(self.inf_filter_edit)
        self.inf_layout.addWidget(self.inf_list)
        self.inf_layout.addWidget(self.add_inf_to_vert_button)
        self.inf_layout.addWidget(self.select_by_infs_button)
        self.inf_widget.setLayout(self.inf_layout)
        
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setWindowTitle("Skin Weights Editor")
        self.resize(1200, 1000)
    
    def options_menu_on_showing(self):
        self.toggle_inf_window_action.setChecked(self.inf_dock_widget.isVisible())
    
    def get_obj_by_name(self, obj):
        if obj is None:
            return
        
        if not cmds.objExists(obj):
            return
        
        return obj
    
    def set_undo_buttons_enabled_state(self):
        """
        Checks the undo stack and determines enabled state and labels on undo/redo buttons.
        """
        self.undo_button.setEnabled(self.undo_stack.canUndo())
        self.redo_button.setEnabled(self.undo_stack.canRedo())
        
        undo_text = self.undo_stack.undoText()
        
        if undo_text:
            self.undo_button.setText("Undo\n({})".format(undo_text))
        else:
            self.undo_button.setText("No undos available")
        
        redo_text = self.undo_stack.redoText()
        
        if redo_text:
            self.redo_button.setText("Redo\n({})".format(redo_text))
        else:
            self.redo_button.setText("No redos available")
    
    def save_table_selection(self):
        """
        Saves table's selection to a data set.
        
        Returns:
            A dictionary representing the selection.
            {inf_name:[vert_index, ..]}
        """
        selection_data = {}
        
        for index in self.table.selectedIndexes():
            if not index.isValid():
                continue
            
            if index.column() > len(self.display_infs)-1:
                continue
            
            inf = self.display_infs[index.column()]
            if inf not in selection_data:
                selection_data[inf] = []
            
            vert_index = self.vert_indexes[index.row()]
            selection_data[inf].append(vert_index)
        
        return selection_data
    
    def load_table_selection(self, selection_data):
        """
        Attempts to load selection by supplied data set.
        
        Args:
            selection_data(dict): See save method for data's structure.
        """
        self.table.clearSelection()
        
        if not selection_data:
            return
        
        selection_model = self.table.selectionModel()
        
        if variables.qt_version > 4:
            selection_flag = QtCore.QItemSelectionModel.Select
        else:
            selection_flag = QtGui.QItemSelectionModel.Select
        
        item_selection = QtCore.QItemSelection()
        
        for inf, vert_indexes in selection_data.items():
            if inf not in self.display_infs:
                continue
            
            column = self.display_infs.index(inf)
            
            for vert_index in vert_indexes:
                if vert_index not in self.vert_indexes:
                    continue
                
                row = self.vert_indexes.index(vert_index)
                
                index = self.table_model.index(row, column)
                
                item_selection.append(QtCore.QItemSelectionRange(index, index))
        
        selection_model.select(item_selection, selection_flag)
    
    def select_items_by_inf(self, inf):
        """
        Selects all items that belong in the same column as the supplied influence.
        
        Args:
            inf(string): The name of the influence to get the column by.
        """
        if inf is None:
            return
        
        if inf not in self.display_infs:
            return
        
        self.table.clearSelection()
        
        column = self.display_infs.index(inf)
        
        self.table.selectColumn(column)
    
    def save_state(self):
        """
        Saves gui's current state to a file.
        """
        if not os.path.exists(os.path.dirname(self.settings_path)):
            os.makedirs(os.path.dirname(self.settings_path))
        
        data = {"width":self.width(), 
                "height":self.height(), 
                "inf_dock_widget.isVisible":self.inf_dock_widget.isVisible(), 
                "inf_dock_widget.area":int(self.dockWidgetArea(self.inf_dock_widget)), 
                "color_style":self.color_style, 
                "prune_spinbox.value":self.prune_spinbox.value(), 
                "add_spinbox.value":self.add_spinbox.value(), 
                "scale_spinbox.value":self.scale_spinbox.value(), 
                "set_spinbox.value":self.set_spinbox.value(), 
                "auto_update_button.isChecked":self.auto_update_table_action.isChecked(), 
                "show_all_button.isChecked":self.show_all_button.isChecked(), 
                "auto_select_button.isChecked":self.auto_select_vertex_action.isChecked(), 
                "auto_select_infs_button.isChecked":self.auto_select_infs_action.isChecked(), 
                "hide_colors_button.isChecked":self.hide_colors_button.isChecked(), 
                "weight_groupbox.isChecked":self.weight_groupbox.isChecked(), 
                "add_groupbox.isChecked":self.add_groupbox.isChecked(), 
                "scale_groupbox.isChecked":self.scale_groupbox.isChecked(), 
                "set_groupbox.isChecked":self.set_groupbox.isChecked()}
        
        OpenMaya.MGlobal.displayInfo("Saving settings to {0}".format(self.settings_path))
        
        with open(self.settings_path, "w") as f:
            f.write(json.dumps(data))
    
    def restore_state(self):
        """
        Restores gui's last state.
        """
        if not os.path.exists(self.settings_path):
            return
        
        with open(self.settings_path, "r") as f:
            data = json.loads(f.read())
        
        if "width" in data and "height" in data:
            self.resize(QtCore.QSize(data["width"], data["height"]))
        
        if "inf_dock_widget.isVisible" in data:
            self.inf_dock_widget.setVisible(data["inf_dock_widget.isVisible"])
        
        if "inf_dock_widget.area" in data:
            all_areas = {1:QtCore.Qt.LeftDockWidgetArea, 2:QtCore.Qt.RightDockWidgetArea, 4:QtCore.Qt.TopDockWidgetArea, 8:QtCore.Qt.BottomDockWidgetArea}
            
            area = all_areas.get(data["inf_dock_widget.area"])
            if area is not None:
                self.addDockWidget(area, self.inf_dock_widget)
        
        if "color_style" in data:
            self.color_style = data["color_style"]
            
            for i, widget in enumerate([self.max_color_action, self.maya_color_action, self.softimage_color_action]):
                widget.setChecked(i == self.color_style)
        
        if "prune_spinbox.value" in data:
            self.prune_spinbox.setValue(data["prune_spinbox.value"])
        
        if "add_spinbox.value" in data:
            self.add_spinbox.setValue(data["add_spinbox.value"])
        
        if "scale_spinbox.value" in data:
            self.scale_spinbox.setValue(data["scale_spinbox.value"])
        
        if "set_spinbox.value" in data:
            self.set_spinbox.setValue(data["set_spinbox.value"])
        
        if "auto_update_button.isChecked" in data:
            self.auto_update_table_action.setChecked(data["auto_update_button.isChecked"])
        
        if "show_all_button.isChecked" in data:
            self.show_all_button.setChecked(data["show_all_button.isChecked"])
        
        if "auto_select_button.isChecked" in data:
            self.auto_select_vertex_action.setChecked(data["auto_select_button.isChecked"])
        
        if "auto_select_infs_button.isChecked" in data:
            self.auto_select_infs_action.setChecked(data["auto_select_infs_button.isChecked"])
        
        if "hide_colors_button.isChecked" in data:
            self.hide_colors_button.setChecked(data["hide_colors_button.isChecked"])
        
        if "weight_groupbox.isChecked" in data:
            self.weight_groupbox.setChecked(data["weight_groupbox.isChecked"])
        
        if "add_groupbox.isChecked" in data:
            self.add_groupbox.setChecked(data["add_groupbox.isChecked"])
        
        if "scale_groupbox.isChecked" in data:
            self.scale_groupbox.setChecked(data["scale_groupbox.isChecked"])
        
        if "set_groupbox.isChecked" in data:
            self.set_groupbox.setChecked(data["set_groupbox.isChecked"])
    
    def resize_columns(self):
        """
        Resizes all columns to fit their contents.
        """
        for i in range(self.table.horizontalHeader().count()):
            self.table.resizeColumnToContents(i)
    
    def update_obj(self, obj):
        """
        Re-points tool to work on another object and re-collect its skin data.
        
        Args:
            obj(string): Object to re-point to.
        """
        self.table_model.begin_update()
        
        last_obj = self.get_obj_by_name(self.obj)
        if last_obj is not None:
            utils.toggle_display_colors(last_obj, False)
            utils.delete_temp_inputs(last_obj)
        
        # Reset values
        self.obj = obj
        self.skin_cluster = None
        self.skin_data = {}
        self.vert_count = None
        self.infs = []
        self._in_component_mode = cmds.selectMode(q=True, component=True)
        
        # Reset undo stack.
        self.undo_stack.clear()
        self.set_undo_buttons_enabled_state()
        
        current_obj = self.get_obj_by_name(self.obj)
        
        # Collect new values
        if current_obj is not None:
            if utils.is_curve(current_obj):
                curve_degree = cmds.getAttr("{0}.degree".format(current_obj))
                curve_spans = cmds.getAttr("{0}.spans".format(current_obj))
                self.vert_count = curve_degree+curve_spans
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
                    QtWidgets.QMessageBox.critical(self, "Skin cluster error!", msg)
        
        self.update_inf_list()
        
        # Display values
        self.pick_obj_button.setText(self.obj or "Press here to update object")
        self.skin_cluster_label.setText(self.skin_cluster or "n/a")
        self.vert_count_label.setText(str(self.vert_count or "n/a"))
        
        self.recollect_table_data(load_selection=False)
        
        if current_obj is not None:
            utils.switch_to_color_set(current_obj)
            
            self.draw_inf()
            
            if self._in_component_mode:
                utils.toggle_display_colors(current_obj, not self.hide_colors_button.isChecked())
        
        self.table_model.end_update()
    
    def collect_inf_locks(self):
        """
        Collects a list of bools from active influences.
        """
        self.locks = [cmds.getAttr("{0}.lockInfluenceWeights".format(inf_name)) 
                      for inf_name in self.infs]
    
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
        
        self.undo_stack.push(CommandLockInfs(description, infs, enabled))
        self.set_undo_buttons_enabled_state()
    
    def get_all_infs(self):
        """
        Gets and returns a list of all influences from the active skinCluster.
        """
        return sorted(cmds.skinCluster(self.skin_cluster, q=True, inf=True) or [])
    
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
        if self.show_all_button.isChecked():
            self.display_infs = self.get_all_infs()
        else:
            self.display_infs = self.get_selected_infs()
        
        self.collect_inf_locks()
    
    def recollect_table_data(self, update_skin_data=True, update_verts=True, 
                             update_infs=True, update_headers=True, load_selection=True):
        """
        Collects all necessary data to display the table and refreshes it.
        Optimize this method by setting some arguments to False.
        """
        # Ignore this event otherwise it slows down the tool by firing many times.
        self.ignore_cell_selection_event = True
        
        self.table_model.begin_update()
        
        current_obj = self.get_obj_by_name(self.obj)
        if current_obj is None:
            return
        
        if load_selection:
            selection_data = self.save_table_selection()
        
        if update_skin_data:
            if self.skin_cluster:
                self.skin_data = utils.get_skin_data(self.skin_cluster)
        
        if update_verts:
            self.vert_indexes = utils.get_selected_vertexes(current_obj)
        
        if update_infs:
            self.collect_display_infs()
        
        if update_headers:
            self.color_headers()
        
        self.table_model.end_update()
        self.table_model.headerDataChanged.emit(QtCore.Qt.Horizontal, 0, len(self.display_infs))
        
        if load_selection:
            if self.auto_select_infs_action.isChecked():
                self.select_items_by_inf(self.color_inf)
            else:
                self.load_table_selection(selection_data)
            
            self.resize_columns()

        utils.toggle_display_colors(
            current_obj,
            not self.hide_colors_button.isChecked() and cmds.selectMode(q=True, component=True))

        self.ignore_cell_selection_event = False
    
    def edit_weights(self, indexes, input_value, mode):
        """
        Sets new weight value while distributing the difference.
        Using the mode argument determines how input_value will be implemented.
        
        Args:
            indexes(QModelIndex[]): A list of cell indexes to edit.
            input_value(float): Value between 0 to 1.0.
            mode(int): 0=absolute, 1=add/subtract, 2=percentage
        """
        current_obj = self.get_obj_by_name(self.obj)
        if current_obj is None:
            return
        
        sel_vert_indexes = set()
        
        new_skin_data = copy.deepcopy(self.skin_data)
        
        for index in indexes:
            row = index.row()
            column = index.column()

            if column > len(self.display_infs) - 1:
                continue

            vert_index = self.vert_indexes[row]
            inf_name = self.display_infs[column]
            weight_data = new_skin_data[vert_index]["weights"]
            old_value = weight_data.get(inf_name) or 0.0
            
            if mode == 0:
                # Ignore if value is almost the same as its old value
                new_value = input_value
                if utils.is_close(old_value, new_value):
                    continue
            elif mode == 1:
                new_value = utils.clamp(0.0, 1.0, old_value+input_value)
            elif mode == 2:
                new_value = utils.clamp(0.0, 1.0, old_value*input_value)
            
            utils.update_weight_value(weight_data, inf_name, new_value)
            
            sel_vert_indexes.add(vert_index)
        
        if not sel_vert_indexes:
            return
        
        if mode == 0:
            description = "Set weights"
        elif mode == 1:
            if input_value > 0:
                description = "Add weights"
            else:
                description = "Subtract weights"
        elif mode == 2:
            description = "Scale weights"
        else:
            description = "Edit weights"
        
        self.add_undo_command(description, current_obj, copy.deepcopy(self.skin_data), new_skin_data, list(sel_vert_indexes), self.save_table_selection())
    
    def color_headers(self):
        """
        Resets the colors on the top headers.
        An active influence will be colored as blue.
        When using the Softimage theme, each header will be the color if its influence.
        """
        self.table_model.header_colors = []
        
        if self.color_style == 2:
            for column in range(self.table_model.columnCount(self.table)):
                header_name = self.table_model.get_inf(column)
                rgb = self.inf_colors.get(header_name)
                
                if rgb is not None:
                    color = QtGui.QColor(rgb[0]*255, rgb[1]*255, rgb[2]*255)
                    self.table_model.header_colors.append(color)
                else:
                    self.table_model.header_colors.append(None)
    
    def draw_inf(self, filter=[]):
        """
        Displays active influence.
        
        Args:
            filter(int[]): List of vertex indexes to only operate on.
        """
        current_obj = self.get_obj_by_name(self.obj)
        if current_obj is not None:
            if utils.is_curve(current_obj):
                return
        
        if not self.infs:
            return
        
        if self.color_inf is None:
            if self.display_infs:
                self.set_color_inf(self.display_infs[0])
            else:
                self.set_color_inf(self.infs[0])
        
        if self.color_style == 2:
            self.set_color_inf(None)
            self.inf_colors = utils.display_multi_color_influence(current_obj, self.skin_cluster, self.skin_data, filter=filter)
        else:
            if self.color_inf is not None:
                utils.display_influence(current_obj, self.skin_data, self.color_inf, color_style=self.color_style, filter=filter)
    
    def switch_color_style(self, index):
        """
        Changes color display to a different theme.
        
        Args:
            index(int): 0=Max, 1=Maya, 2=Softimage
        """
        self.color_style = index
        self.draw_inf()
        self.recollect_table_data(update_skin_data=False, update_verts=False, 
                                  update_infs=False, load_selection=False)
    
    def run_smooth(self):
        """
        Smooths weights on selected vertexes in the scene.
        Only uses vert's influences.
        """
        current_obj = self.get_obj_by_name(self.obj)
        if current_obj is None:
            OpenMaya.MGlobal.displayWarning("No object to operate on.")
            return
        
        selected_vertexes = utils.get_selected_vertexes(current_obj)
        if not selected_vertexes:
            OpenMaya.MGlobal.displayWarning("No vertexes are selected.")
            return
        
        old_skin_data = copy.deepcopy(WeightsEditor.instance.skin_data)
        
        table_selection = self.save_table_selection()
        
        sel_vert_indexes = utils.get_selected_vertexes(current_obj)
        
        utils.smooth_weights(current_obj, selected_vertexes, self.skin_data)
        
        self.recollect_table_data(update_skin_data=False, update_verts=False)
        
        self.draw_inf(filter=selected_vertexes)
        
        new_skin_data = copy.deepcopy(WeightsEditor.instance.skin_data)
        
        self.add_undo_command("Smooth weights", current_obj, old_skin_data, new_skin_data, sel_vert_indexes, table_selection, skip_first_redo=True)
    
    def run_br_smooth(self):
        """
        Smooths weights on selected vertexes in the scene.
        Includes all influences in its calculation.
        """
        current_obj = self.get_obj_by_name(self.obj)
        if current_obj is None:
            OpenMaya.MGlobal.displayWarning("No object to operate on.")
            return
        
        selected_vertexes = utils.get_selected_vertexes(current_obj)
        if not selected_vertexes:
            OpenMaya.MGlobal.displayWarning("No vertexes are selected.")
            return
        
        old_skin_data = copy.deepcopy(WeightsEditor.instance.skin_data)
        
        table_selection = self.save_table_selection()
        
        sel_vert_indexes = utils.get_selected_vertexes(current_obj)
        
        mel.eval("br_smoothSkinClusterWeightFlood 0;")
        
        # Need to recollect all data since the smooth isn't changing our internal data.
        self.recollect_table_data()
        
        self.draw_inf(filter=selected_vertexes)
        
        new_skin_data = copy.deepcopy(WeightsEditor.instance.skin_data)
        
        self.add_undo_command("Smooth weights (all influences)", current_obj, old_skin_data, new_skin_data, sel_vert_indexes, table_selection, skip_first_redo=True)
    
    def reorder_rows(self, column, order):
        """
        Re-orders and displays rows by weight values.
        
        Args:
            column(int): The influence to compare weights with.
            order(QtCore.Qt.SortOrder): The direction to sort the weights by.
                                        If None, re-orders based on vertex index.
        """
        self.table_model.begin_update()
        
        selection_data = self.save_table_selection()
        
        inf = self.display_infs[column]
        
        if order is None:
            self.vert_indexes = sorted(self.vert_indexes)
        else:
            self.vert_indexes = sorted(self.vert_indexes, 
                                       key=lambda x: self.skin_data[x]["weights"].get(inf) or 0.0, 
                                       reverse=order)
        
        self.table_model.end_update()
        
        self.load_table_selection(selection_data)
    
    def add_undo_command(self, description, obj, old_skin_data, new_skin_data, vert_indexes, table_selection, skip_first_redo=False):
        self.undo_stack.push(CommandEditWeights(description, obj, old_skin_data, new_skin_data, vert_indexes, table_selection, skip_first_redo=skip_first_redo))
        self.set_undo_buttons_enabled_state()
    
    def get_item_from_inf_list(self, name):
        results = self.inf_list_model.findItems(name)
        if results:
            return results[0]
    
    def set_color_inf(self, inf, update_inf_list=True):
        self.table_model.begin_update()
        self.inf_list_model.layoutAboutToBeChanged.emit()
        
        self.color_inf = inf
        
        self.inf_list_model.layoutChanged.emit()
        self.table_model.end_update()
    
    def update_inf_list(self):
        self.inf_list_model.layoutAboutToBeChanged.emit()
        
        self.inf_list_model.clear()
        
        for i, inf in enumerate(sorted(self.infs)):
            item = QtGui.QStandardItem(inf)
            item.setSizeHint(QtCore.QSize(1, 30))
            self.inf_list_model.appendRow(item)
        
        self.apply_filter_to_inf_list()
        
        self.inf_list_model.layoutChanged.emit()
    
    def apply_filter_to_inf_list(self):
        if self.inf_filter_edit.text():
            all_infs = [self.inf_list_model.item(i).text() for i in range(self.inf_list_model.rowCount())]
            
            filter_infs = fnmatch.filter(all_infs, self.inf_filter_edit.text())
            
            for i in range(self.inf_list_model.rowCount()):
                in_filter = self.inf_list_model.item(i).text() in filter_infs
                self.inf_list.setRowHidden(i, not in_filter)
        else:
            for i in range(self.inf_list_model.rowCount()):
                self.inf_list.setRowHidden(i, False)
    
#
# Callbacks
#
    
    def selection_on_changed(self, client_data):
        """
        Triggers when user selects a new vertex in the viewport.
        Then refreshes table to be in sync.
        """
        # Check if the current object is valid.
        current_obj = self.get_obj_by_name(self.obj)
        current_skin_cluster = self.get_obj_by_name(self.skin_cluster)
        
        if current_obj is not None and current_skin_cluster is not None:
            # Toggle influence colors if component selection mode changes.
            now_in_component_mode = cmds.selectMode(q=True, component=True)
            
            if not self.hide_colors_button.isChecked():
                if now_in_component_mode != self._in_component_mode:
                    utils.toggle_display_colors(current_obj, now_in_component_mode)
            
            self._in_component_mode = now_in_component_mode
            
            # Update table's data.
            if not self.block_selection_cb:
                self.recollect_table_data(update_skin_data=False)
    
    def add_selection_callback(self):
        if self.cb_selection_changed is None:
            self.cb_selection_changed = OpenMaya.MEventMessage.addEventCallback("SelectionChanged", self.selection_on_changed)
    
    def remove_selection_callback(self):
        if self.cb_selection_changed is not None:
            OpenMaya.MEventMessage.removeCallback(self.cb_selection_changed)
            self.cb_selection_changed = None
    
#
# Events
#
    
    def closeEvent(self, event):
        self.remove_selection_callback()
        
        self.save_state()
        
        current_obj = self.get_obj_by_name(self.obj)
        if current_obj is not None:
            utils.toggle_display_colors(current_obj, False)
            utils.delete_temp_inputs(current_obj)
        
        self.del_prev_instance()
    
    def keyPressEvent(self, event):
        if event.key() in self.accept_keys:
            self.window_on_key_pressed(event)
        else:
            QtWidgets.QWidget.keyPressEvent(self, event)
    
    def pick_obj_on_clicked(self):
        obj = utils.get_selected_mesh()
        self.update_obj(obj)
    
    def header_on_context_trigger(self, mouse_point):
        self.header_context_menu.exec_(self.table.viewport().mapToGlobal(mouse_point))
    
    def update_on_clicked(self):
        self.recollect_table_data(update_skin_data=False)
    
    def auto_update_on_toggled(self):
        enable_cb = self.auto_update_table_action.isChecked()
        
        if enable_cb:
            self.add_selection_callback()
        else:
            self.remove_selection_callback()
    
    def top_header_on_l_clicked(self, index):
        """
        Selects all cells from column.
        """
        self.table.selectColumn(index)
    
    def top_header_on_m_clicked(self, index):
        """
        Sets active influence to color with.
        """
        if self.color_style != 2:
            inf = self.display_infs[index]
            self.set_color_inf(inf)
            self.draw_inf()
            self.recollect_table_data(update_skin_data=False, update_verts=False, 
                                      update_infs=False, load_selection=False)
    
    def window_on_key_pressed(self, key_event):
        """
        Triggers when a key is pressed in the table.
        """
        key = key_event.key()
        
        key_mod = key_event.modifiers()
        
        if key_mod == QtCore.Qt.ShiftModifier:
            if key == ord(">"): # Grows selection
                mel.eval("PolySelectTraverse 1;")
            elif key == ord("<"): # Shrinks selection
                mel.eval("PolySelectTraverse 2;")
            elif key == ord("S"): # Selects perimeter
                mel.eval("ConvertSelectionToVertexPerimeter;")
            elif key == ord("E"): # Selects edge loop
                mel.eval("SelectEdgeLoopSp;")
            elif key == ord("A"): # Selects all
                mel.eval("polyConvertToShell;")
            elif key == ord("R"): # Selects edge ring
                mel.eval("ConvertSelectionToContainedEdges;")
                mel.eval("SelectEdgeRingSp;")
                mel.eval("ConvertSelectionToVertices;")
        elif key_mod == QtCore.Qt.AltModifier:
            if key == ord("S"): # Selects perimeter
                self.run_smooth()
        else:
            if key == ord(" "): # Toggles locks
                if not self.display_infs:
                    return
                
                sel_columns = set(index.column() 
                                  for index in self.table.get_selected_indexes())
                
                inf_name = self.display_infs[self.table.currentIndex().column()]
                inf_index = self.infs.index(inf_name)
                do_lock = not self.locks[inf_index]
                
                infs = [self.display_infs[column] for column in sel_columns]
                
                self.toggle_inf_locks(infs, do_lock)
    
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
            inf_name = self.inf_list_model.itemFromIndex(index).text()
            
            if not cmds.objExists(inf_name):
                OpenMaya.MGlobal.displayError("Unable to find influence '{}' in the scene. Is the list out of sync?".format(inf_name))
                return
            
            infs.append(inf_name)
        
        utils.select_inf_vertexes(current_obj, infs, self.skin_data)
    
    def prune_on_clicked(self):
        current_obj = self.get_obj_by_name(self.obj)
        if current_obj is None:
            return
        
        old_skin_data = copy.deepcopy(WeightsEditor.instance.skin_data)
        
        table_selection = self.save_table_selection()
        
        sel_vert_indexes = utils.get_selected_vertexes(current_obj)
        
        is_pruned = utils.prune_weights(current_obj, self.skin_cluster, self.prune_spinbox.value())
        if not is_pruned:
            return
        
        self.recollect_table_data(update_verts=False)
        
        self.draw_inf(filter=sel_vert_indexes)
        
        new_skin_data = copy.deepcopy(WeightsEditor.instance.skin_data)
        
        self.add_undo_command("Prune weights", current_obj, old_skin_data, new_skin_data, sel_vert_indexes, table_selection, skip_first_redo=True)
    
    def set_add_on_clicked(self):
        indexes = self.table.get_selected_indexes()
        if not indexes:
            OpenMaya.MGlobal.displayWarning("Select cells inside the table to edit.")
            return
        
        value = self.add_spinbox.value()
        
        self.edit_weights(indexes, value, 1)
    
    def add_preset_on_clicked(self, value):
        self.add_spinbox.setValue(value)
        self.set_add_on_clicked()
    
    def set_scale_on_clicked(self):
        indexes = self.table.get_selected_indexes()
        if not indexes:
            OpenMaya.MGlobal.displayWarning("Select cells inside the table to edit.")
            return
        
        perc = self.scale_spinbox.value()
        multiplier = utils.remap_range(-100.0, 100.0, 0.0, 2.0, perc)
        
        self.edit_weights(self.table.get_selected_indexes(), multiplier, 2)
    
    def scale_preset_on_clicked(self, perc):
        self.scale_spinbox.setValue(perc)
        self.set_scale_on_clicked()
    
    def set_on_clicked(self):
        indexes = self.table.get_selected_indexes()
        if not indexes:
            OpenMaya.MGlobal.displayWarning("Select cells inside the table to edit.")
            return
        
        value = self.set_spinbox.value()
        
        self.edit_weights(indexes, value, 0)
    
    def set_preset_on_clicked(self, value):
        self.set_spinbox.setValue(value)
        self.set_on_clicked()
    
    def cell_selection_on_changed(self):
        """
        Selects vertexes based on what was selected on the table.
        """
        if self.ignore_cell_selection_event:
            return
        
        if not self.auto_select_vertex_action.isChecked():
            return
        
        rows = set(index.row()
                   for index in self.table.get_selected_indexes())
        
        if rows == self.selected_rows:
            return
        
        self.selected_rows = rows
        
        current_obj = self.get_obj_by_name(self.obj)
        if current_obj is not None:
            if utils.is_curve(current_obj):
                vertex_list = ["{0}.cv[{1}]".format(current_obj, self.vert_indexes[row]) 
                               for row in rows]
            else:
                vertex_list = ["{0}.vtx[{1}]".format(current_obj, self.vert_indexes[row]) 
                               for row in rows]
        else:
            vertex_list = []
        
        self.block_selection_cb = True
        cmds.select(vertex_list)
        self.block_selection_cb = False
    
    def hide_colors_on_clicked(self):
        current_obj = self.get_obj_by_name(self.obj)
        if current_obj is not None and cmds.selectMode(q=True, component=True):
            hide_colors = self.hide_colors_button.isChecked()
            utils.toggle_display_colors(current_obj, not hide_colors)
    
    def switch_color_on_clicked(self, index):
        self.max_color_action.setChecked(index == 0)
        self.maya_color_action.setChecked(index == 1)
        self.softimage_color_action.setChecked(index == 2)
        
        self.switch_color_style(index)
    
    def toggle_inf_window_on_clicked(self, state):
        self.inf_dock_widget.setVisible(state)
    
    def about_controls_on_clicked(self):
        msg_box = QtWidgets.QMessageBox(parent=self)
        msg_box.setWindowTitle("Controls & hotkeys")
        
        msg_txt = ("Weights table:\n"
                   "    - Right-click cell to edit its value (Esc cancels input, Enter commits it)\n"
                   "    - Press space to toggle locks on selected influences\n"
                   "    - Left-click on top or side headers to select all of its cells\n"
                   "    - Middle-click top header to display that influence\n"
                   "    - Right-click top header to trigger menu\n"
                   "\n"
                   "Influence list:\n"
                   "    - Double click to select influence\n"
                   "    - Middle-click to display that influence\n"
                   "\n"
                   "Hotkeys: (only works if you click on this tool give it focus over the viewport)\n"
                   "    Shift + < : Shrink vertex selection\n"
                   "    Shift + > : Grow vertex selection\n"
                   "    Shift + a : Select all vertexes from object\n"
                   "    Shift + s : Grow selection and select its perimeter\n"
                   "    Shift + e : Select by edge loops\n"
                   "    Shift + r : Select by ring loops\n"
                   "    Alt + s : Smooth weights on selected vertexes")
        msg_box.setText(msg_txt)
        msg_box.exec_()
    
    def about_on_clicked(self):
        msg_box = QtWidgets.QMessageBox(parent=self)
        msg_box.setWindowTitle("About")
        msg_box.setTextFormat(QtCore.Qt.RichText)
        
        tab = "&nbsp;&nbsp;&nbsp;&nbsp;"
        
        msg_txt = ("Developed by<br>"
                   "{tab}Jason Labbe <a href='http://www.jasonlabbe3d.com'>www.jasonlabbe3d.com</a><br>"
                   "<br>"
                   "Thank you<br>"
                   "{tab}Enrique Caballero and John Lienard for pushing me to make this.<br><br>"
                   "{tab}Ingo Clemens (Brave Rabbit) for his <a href='http://www.braverabbit.com/smoothskinclusterweight'>smoothSkinClusterWeight</a> plugin.<br><br>"
                   "{tab}Tyler Thornock for his <a href='http://www.charactersetup.com/tutorial_skinWeights.html'>tutorial</a> on a faster approach to get/set skin weights<br><br>"
                   "If you would like to report a bug or have any requests please send an e-mail to jasonlabbe@gmail.com".format(tab=tab))
        msg_box.setText(msg_txt)
        msg_box.exec_()
    
    def groupbox_on_toggle(self, enabled, groupbox=None):
        if groupbox is None:
            groupbox = self.sender()
        
        frame = groupbox.findChild(groupbox_frame.GroupboxFrame)
        if frame is None:
            return
        
        if enabled:
            groupbox.setMaximumHeight(9999)
        else:
            groupbox.setMaximumHeight(20)
        
        frame.setVisible(enabled)
    
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

    def on_inf_double_click(self, index):
        """
        Select influence object.
        """
        if not index.isValid():
            return
        
        item = self.inf_list_model.itemFromIndex(index)
        
        obj_name = item.text()
        if not cmds.objExists(obj_name):
            OpenMaya.MGlobal.displayError("Unable to find '{0}' in the scene".format(obj_name))
            return
        
        cmds.select(obj_name)
    
    def on_inf_middle_clicked(self, index):
        """
        Switches what influence to color.
        """
        if not index.isValid():
            return
        
        item = self.inf_list_model.itemFromIndex(index)
        if item.text() not in self.infs:
            return
        
        self.set_color_inf(item.text(), update_inf_list=False)
        self.draw_inf()
    
    def on_inf_key_pressed(self, key_event):
        if key_event.text() == " ":
            indexes = self.inf_list.selectedIndexes()
            if not indexes:
                return
            
            inf_names = [self.inf_list_model.itemFromIndex(index).text() for index in indexes]
            
            if inf_names[0] not in self.infs:
                OpenMaya.MGlobal.displayError("Unable to find influence in internal data.. Is it out of sync?")
                return
            
            inf_index = self.infs.index(inf_names[0])
            
            do_lock = not self.locks[inf_index]
            
            self.toggle_inf_locks(inf_names, do_lock)
    
    def add_inf_to_vert_on_clicked(self):
        """
        Adds a very small weight value from selected influences to selected vertexes.
        """
        current_obj = self.get_obj_by_name(self.obj)
        if current_obj is None:
            OpenMaya.MGlobal.displayError("There's no active object to work on.")
            return
        
        sel_vert_indexes = utils.get_selected_vertexes(current_obj)
        if not sel_vert_indexes:
            OpenMaya.MGlobal.displayError("There's no selected vertexes to set on.")
            return
        
        # Collect selected influence names.
        sel_infs = []
        
        for index in self.inf_list.selectedIndexes():
            if not index.isValid():
                continue
            
            item = self.inf_list_model.itemFromIndex(index)
            
            inf_name = item.text()
            if inf_name not in self.infs:
                continue
            
            sel_infs.append(inf_name)
        
        if not sel_infs:
            OpenMaya.MGlobal.displayError("Nothing is selected in the influence list.")
            return
        
        old_skin_data = copy.deepcopy(WeightsEditor.instance.skin_data)
        
        new_skin_data = copy.deepcopy(WeightsEditor.instance.skin_data)
        
        table_selection = self.save_table_selection()
        
        # Add infs by setting a very low value so it doesn't effect other weights too much.
        for inf in sel_infs:
            for vert_index in sel_vert_indexes:
                weight_data = new_skin_data[vert_index]["weights"]
                
                # No need to change it if it's already weighted to the vert.
                if weight_data.get(inf) is not None:
                    continue
                
                utils.update_weight_value(weight_data, inf, 0.001)
        
        self.add_undo_command("Add influence to verts", current_obj, old_skin_data, new_skin_data, sel_vert_indexes, table_selection)
        
        self.recollect_table_data(update_skin_data=False, update_verts=False)
    
#
# Context menu events
#
    
    # Display influence's weights
    def display_inf_on_triggered(self):
        if self.color_style != 2:
            inf = self.display_infs[self.top_header.last_index]
            self.set_color_inf(inf)
            self.draw_inf()
            self.recollect_table_data(update_skin_data=False, update_verts=False, update_infs=False, load_selection=False)
    
    def select_inf_verts_on_triggered(self):
        current_obj = self.get_obj_by_name(self.obj)
        if current_obj is not None:
            inf = self.display_infs[self.top_header.last_index]
            utils.select_inf_vertexes(current_obj, [inf], self.skin_data)
    
    def select_inf_on_triggered(self):
        inf = self.display_infs[self.top_header.last_index]
        if cmds.objExists(inf):
            cmds.select(inf)
    
    def sort_ascending_on_triggered(self):
        self.reorder_rows(self.top_header.last_index, QtCore.Qt.DescendingOrder)
    
    def sort_descending_on_triggered(self):
        self.reorder_rows(self.top_header.last_index, QtCore.Qt.AscendingOrder)
    
    def sort_vert_order_on_triggered(self):
        self.reorder_rows(self.top_header.last_index, None)


def run():
    global tool
    tool = WeightsEditor()
    tool.show()
    return tool
