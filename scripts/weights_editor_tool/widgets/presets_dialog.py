from maya import cmds

from PySide2 import QtCore
from PySide2 import QtGui
from PySide2 import QtWidgets

from weights_editor_tool import weights_editor_utils as utils


class PresetsDialog(QtWidgets.QDialog):

    Defaults = {
        "add": [-0.2, -0.1, -0.05, -0.01, 0.01, 0.05, 0.1, 0.2],
        "scale": [-50, -25, -10, -5, 5, 10, 25, 50],
        "set": [0.0, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0]
    }

    def __init__(self, add_presets, scale_presets, set_presets, parent=None):
        QtWidgets.QDialog.__init__(self, parent=parent)

        self._add_presets = add_presets
        self._scale_presets = scale_presets
        self._set_presets = set_presets

        self._create_gui()

    def _create_gui(self):
        self._menu_bar = QtWidgets.QMenuBar(self)
        self._menu_bar.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)

        self._settings_menu = QtWidgets.QMenu("&Tool settings", parent=self)
        self._menu_bar.addMenu(self._settings_menu)

        self._reset_to_defaults_action = QtWidgets.QAction("Reset to defaults", self)
        self._reset_to_defaults_action.triggered.connect(self._reset_to_defaults_on_triggered)
        self._settings_menu.addAction(self._reset_to_defaults_action)

        self._tooltip_label = QtWidgets.QLabel(
            "Enter numbers separated by commas to define which preset buttons to build",
            parent=self)
        self._tooltip_label.setWordWrap(True)
        self._tooltip_label.setStyleSheet("""
            QLabel {
                padding: 10px;
                font-style: italic;
            }
        """)

        self._add_preset_widget = PresetWidget("Add / subtract presets", (-1, 1), self._add_presets, parent=self)
        self._scale_preset_widget = PresetWidget("Scale presets", (-100, 100), self._scale_presets, parent=self)
        self._set_preset_widget = PresetWidget("Set presets", (0, 1), self._set_presets, parent=self)

        self._main_layout = QtWidgets.QVBoxLayout()
        self._main_layout.addWidget(self._menu_bar)
        self._main_layout.addLayout(self._add_preset_widget.layout)
        self._main_layout.addLayout(self._scale_preset_widget.layout)
        self._main_layout.addLayout(self._set_preset_widget.layout)

        self._apply_button = QtWidgets.QPushButton("Apply changes", parent=self)
        self._apply_button.clicked.connect(self._accept_on_clicked)

        self._cancel_button = QtWidgets.QPushButton("Cancel", parent=self)
        self._cancel_button.clicked.connect(self.reject)

        self._buttons_layout = QtWidgets.QHBoxLayout()
        self._buttons_layout.addWidget(self._apply_button)
        self._buttons_layout.addWidget(self._cancel_button)

        self._main_frame = QtWidgets.QFrame(parent=self)
        self._main_frame.setLayout(self._main_layout)

        self._menu_layout = QtWidgets.QVBoxLayout()
        self._menu_layout.setContentsMargins(0, 0, 0, 0)
        self._menu_layout.addWidget(self._menu_bar)
        self._menu_layout.addWidget(self._tooltip_label)
        self._menu_layout.addWidget(self._main_frame)
        self._menu_layout.addLayout(self._buttons_layout)
        self.setLayout(self._menu_layout)

        self.setWindowTitle("Edit Preset Buttons")
        self.resize(500, 0)

    @classmethod
    def launch(cls, add_presets, scale_presets, set_presets, parent):
        dialog = cls(add_presets, scale_presets, set_presets, parent=parent)
        return dialog.exec_(), dialog

    def serialize(self):
        return {
            "add": self._add_preset_widget.values,
            "scale": self._scale_preset_widget.values,
            "set": self._set_preset_widget.values
        }

    def _reset_to_defaults_on_triggered(self):
        self._add_preset_widget.set_values(self.Defaults["add"])
        self._scale_preset_widget.set_values(self.Defaults["scale"])
        self._set_preset_widget.set_values(self.Defaults["set"])

    def _accept_on_clicked(self):
        try:
            self.accept()
        except Exception as err:
            utils.show_error_msg("Error!", str(err), self.parent())


class PresetWidget:

    def __init__(self, caption, min_max_range, values, parent=None):
        self.values = []

        self._caption = QtWidgets.QLabel(caption, parent=parent)
        self._caption.setMinimumWidth(120)
        self._caption.setStyleSheet("""
            QLabel {
                font-weight: bold;
            }
        """)

        self._line_edit = QtWidgets.QLineEdit(parent=parent)
        self._validator = CustomValidator(self._line_edit, min_max_range, parent=parent)
        self._validator.values_updated.connect(self._on_values_updated)
        self._line_edit.setText(self._validator.clean_up_items(values))
        self._line_edit.setPlaceholderText("No presets have been set")
        self._line_edit.setValidator(self._validator)

        self._min_label = QtWidgets.QLabel("Min: {}".format(min_max_range[0]), parent=parent)
        self._min_label.setMinimumWidth(50)

        self._max_label = QtWidgets.QLabel("Max: {}".format(min_max_range[1]), parent=parent)
        self._max_label.setAlignment(QtCore.Qt.AlignRight)
        self._max_label.setMinimumWidth(50)

        self._sub_layout = utils.wrap_layout(
            [self._min_label, self._line_edit, self._max_label],
            QtCore.Qt.Horizontal,
            margins=[20, 0, 20, 5])

        self._sub_frame = QtWidgets.QWidget(parent=parent)
        self._sub_frame.setLayout(self._sub_layout)

        self.layout = utils.wrap_layout(
            [self._caption, self._sub_frame],
            QtCore.Qt.Vertical)

        self.set_values(values)

    def _on_values_updated(self, values):
        self.values = values

    def set_values(self, values):
        self.values = values
        self._line_edit.setText(self._validator.clean_up_items(values))


class CustomValidator(QtGui.QValidator):

    values_updated = QtCore.Signal(list)

    def __init__(self, line_edit, min_max_range, parent=None):
        QtGui.QValidator.__init__(self, parent)
        self._line_edit = line_edit
        self._min_value = min_max_range[0]
        self._max_value = min_max_range[1]

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
                    if value < self._min_value:
                        cmds.warning("Unable to put a value below {0}".format(self._min_value))
                        continue

                    if value > self._max_value:
                        cmds.warning("Unable to put a value over {0}".format(self._max_value))
                        continue

                    new_values.append(value)
            except Exception:
                pass

        self._line_edit.setText(self.clean_up_items(new_values))
        self.values_updated.emit(new_values)
