from PySide2 import QtCore
from PySide2 import QtGui
from PySide2 import QtWidgets

import maya.cmds as cmds

from weights_editor_tool import weights_editor_utils as utils


class PresetsDialog(QtWidgets.QDialog):

    Defaults = {
        "add": [-0.2, -0.1, -0.05, -0.01, 0.01, 0.05, 0.1, 0.2],
        "scale": [-50, -25, -10, -5, 5, 10, 25, 50],
        "set": [0.0, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0]
    }

    def __init__(self, add_presets, scale_presets, set_presets, parent=None):
        QtWidgets.QDialog.__init__(self, parent=parent)

        self.add_presets = add_presets
        self.scale_presets = scale_presets
        self.set_presets = set_presets

        self.create_gui()

    def create_gui(self):
        self.menu_bar = QtWidgets.QMenuBar(self)
        self.menu_bar.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)

        self.settings_menu = QtWidgets.QMenu("&Tool settings", parent=self)
        self.menu_bar.addMenu(self.settings_menu)

        self.reset_to_defaults_action = QtWidgets.QAction("Reset to defaults", self)
        self.reset_to_defaults_action.triggered.connect(self.reset_to_defaults_on_triggered)
        self.settings_menu.addAction(self.reset_to_defaults_action)

        self.tooltip_label = QtWidgets.QLabel(
            "Enter numbers separated by commas to define which preset buttons to build",
            parent=self)
        self.tooltip_label.setWordWrap(True)
        self.tooltip_label.setStyleSheet("""
            QLabel {
                padding: 10px;
                font-style: italic;
            }
        """)

        self.add_preset_widget = PresetWidget("Add / subtract presets", (-1, 1), self.add_presets, parent=self)
        self.scale_preset_widget = PresetWidget("Scale presets", (-100, 100), self.scale_presets, parent=self)
        self.set_preset_widget = PresetWidget("Set presets", (0, 1), self.set_presets, parent=self)

        self.main_layout = QtWidgets.QVBoxLayout()
        self.main_layout.addWidget(self.menu_bar)
        self.main_layout.addLayout(self.add_preset_widget.layout)
        self.main_layout.addLayout(self.scale_preset_widget.layout)
        self.main_layout.addLayout(self.set_preset_widget.layout)

        self.apply_button = QtWidgets.QPushButton("Apply changes", parent=self)
        self.apply_button.clicked.connect(self.accept_on_clicked)

        self.cancel_button = QtWidgets.QPushButton("Cancel", parent=self)
        self.cancel_button.clicked.connect(self.reject)

        self.buttons_layout = QtWidgets.QHBoxLayout()
        self.buttons_layout.addWidget(self.apply_button)
        self.buttons_layout.addWidget(self.cancel_button)

        self.main_frame = QtWidgets.QFrame(parent=self)
        self.main_frame.setLayout(self.main_layout)

        self.menu_layout = QtWidgets.QVBoxLayout()
        self.menu_layout.setContentsMargins(0, 0, 0, 0)
        self.menu_layout.addWidget(self.menu_bar)
        self.menu_layout.addWidget(self.tooltip_label)
        self.menu_layout.addWidget(self.main_frame)
        self.menu_layout.addLayout(self.buttons_layout)
        self.setLayout(self.menu_layout)

        self.setWindowTitle("Edit Preset Buttons")
        self.resize(500, 0)

    @classmethod
    def launch(cls, add_presets, scale_presets, set_presets, parent):
        dialog = cls(add_presets, scale_presets, set_presets, parent=parent)
        return dialog.exec_(), dialog

    def serialize(self):
        return {
            "add": self.add_preset_widget.values,
            "scale": self.scale_preset_widget.values,
            "set": self.set_preset_widget.values
        }

    def reset_to_defaults_on_triggered(self):
        self.add_preset_widget.set_values(self.Defaults["add"])
        self.scale_preset_widget.set_values(self.Defaults["scale"])
        self.set_preset_widget.set_values(self.Defaults["set"])

    def accept_on_clicked(self):
        try:
            self.accept()
        except Exception as err:
            utils.show_error_msg("Error!", str(err), self.parent())


class PresetWidget:

    def __init__(self, caption, min_max_range, values, parent=None):
        self.values = []

        self.caption = QtWidgets.QLabel(caption, parent=parent)
        self.caption.setMinimumWidth(120)
        self.caption.setStyleSheet("""
            QLabel {
                font-weight: bold;
            }
        """)

        self.line_edit = QtWidgets.QLineEdit(parent=parent)
        self.validator = CustomValidator(self.line_edit, min_max_range, parent=parent)
        self.validator.values_updated.connect(self.on_values_updated)
        self.line_edit.setText(self.validator.clean_up_items(values))
        self.line_edit.setPlaceholderText("No presets have been set")
        self.line_edit.setValidator(self.validator)

        self.min_label = QtWidgets.QLabel("Min: {}".format(min_max_range[0]), parent=parent)
        self.min_label.setMinimumWidth(50)

        self.max_label = QtWidgets.QLabel("Max: {}".format(min_max_range[1]), parent=parent)
        self.max_label.setAlignment(QtCore.Qt.AlignRight)
        self.max_label.setMinimumWidth(50)

        self.sub_layout = utils.wrap_layout(
            [self.min_label, self.line_edit, self.max_label],
            QtCore.Qt.Horizontal,
            margins=[20, 0, 20, 5])

        self.sub_frame = QtWidgets.QWidget(parent=parent)
        self.sub_frame.setLayout(self.sub_layout)

        self.layout = utils.wrap_layout(
            [self.caption, self.sub_frame],
            QtCore.Qt.Vertical)

        self.set_values(values)

    def set_values(self, values):
        self.values = values
        self.line_edit.setText(self.validator.clean_up_items(values))

    def on_values_updated(self, values):
        self.values = values


class CustomValidator(QtGui.QValidator):

    values_updated = QtCore.Signal(list)

    def __init__(self, line_edit, min_max_range, parent=None):
        QtGui.QValidator.__init__(self, parent)
        self.line_edit = line_edit
        self.min_value = min_max_range[0]
        self.max_value = min_max_range[1]

    @staticmethod
    def num_to_str(num):
        value = str(num)
        if value.endswith(".0"):
            value = value[:-2]
        return value

    @classmethod
    def clean_up_items(cls, items):
        return ", ".join(map(cls.num_to_str, items))

    def validate(self, txt, pos):
        if not txt:
            return QtGui.QValidator.Acceptable, pos

        valid_chars = ["-", ",", ".", " "]
        char = txt[pos - 1]
        if not char.isdigit() and char not in valid_chars:
            return QtGui.QValidator.Invalid, pos

        return QtGui.QValidator.Intermediate, pos

    def fixup(self, txt):
        new_values = []

        for s in txt.split(","):
            try:
                if s:
                    value = float(s)
                    if value < self.min_value:
                        cmds.warning("Unable to put a value below {0}".format(self.min_value))
                        continue

                    if value > self.max_value:
                        cmds.warning("Unable to put a value over {0}".format(self.max_value))
                        continue

                    new_values.append(value)
            except Exception:
                pass

        self.line_edit.setText(self.clean_up_items(new_values))
        self.values_updated.emit(new_values)
