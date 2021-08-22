from itertools import combinations

from PySide2 import QtCore
from PySide2 import QtGui
from PySide2 import QtWidgets

from weights_editor_tool import weights_editor_utils as utils
from weights_editor_tool.classes.hotkey import Hotkey


class HotkeysDialog(QtWidgets.QDialog):

    def __init__(self, hotkeys, parent=None):
        QtWidgets.QDialog.__init__(self, parent=parent)

        self.hotkey_edits = []

        self.create_gui(hotkeys)

    def create_gui(self, hotkeys):
        self.menu_bar = QtWidgets.QMenuBar(self)
        self.menu_bar.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)

        self.settings_menu = QtWidgets.QMenu("&Tool settings", parent=self)
        self.menu_bar.addMenu(self.settings_menu)

        self.reset_to_defaults_action = QtWidgets.QAction("Reset to defaults", self)
        self.reset_to_defaults_action.triggered.connect(self.reset_to_defaults_on_triggered)
        self.settings_menu.addAction(self.reset_to_defaults_action)

        self.main_layout = QtWidgets.QVBoxLayout()
        self.main_layout.addWidget(self.menu_bar)

        for hotkey in hotkeys:
            label = QtWidgets.QLabel(hotkey.caption, parent=self)
            label.setFixedWidth(150)

            key_edit = HotkeyEdit(hotkey.copy(), parent=self)
            key_edit.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
            self.hotkey_edits.append(key_edit)

            hotkey_layout = QtWidgets.QHBoxLayout()
            hotkey_layout.addWidget(label)
            hotkey_layout.addWidget(key_edit)
            hotkey_layout.addStretch()

            self.main_layout.addLayout(hotkey_layout)

        self.apply_button = QtWidgets.QPushButton("Apply changes", parent=self)
        self.apply_button.clicked.connect(self.accept_on_clicked)

        self.cancel_button = QtWidgets.QPushButton("Cancel", parent=self)
        self.cancel_button.clicked.connect(self.reject)

        self.buttons_layout = QtWidgets.QHBoxLayout()
        self.buttons_layout.addWidget(self.apply_button)
        self.buttons_layout.addWidget(self.cancel_button)

        self.main_frame = QtWidgets.QFrame(parent=self)
        self.main_frame.setLayout(self.main_layout)

        self.scroll_area = QtWidgets.QScrollArea(parent=self)
        self.scroll_area.setFocusPolicy(QtCore.Qt.NoFocus)
        self.scroll_area.setStyleSheet("QScrollArea {border: none;}")
        self.scroll_area.setWidget(self.main_frame)
        self.scroll_area.setWidgetResizable(True)

        self.tooltip_label = QtWidgets.QLabel(
            "These hotkeys will temporarily override your native hotkeys until the tool is closed.",
            parent=self)
        self.tooltip_label.setWordWrap(True)
        self.tooltip_label.setStyleSheet("""
            QLabel {
                padding: 10px;
                font-style: italic;
            }
        """)

        self.menu_layout = QtWidgets.QVBoxLayout()
        self.menu_layout.setContentsMargins(0, 0, 0, 0)
        self.menu_layout.addWidget(self.menu_bar)
        self.menu_layout.addWidget(self.tooltip_label)
        self.menu_layout.addWidget(self.scroll_area)
        self.menu_layout.addLayout(self.buttons_layout)
        self.setLayout(self.menu_layout)

        self.setWindowTitle("Edit Hotkeys")
        self.resize(350, 400)

    @classmethod
    def launch(cls, hotkeys, parent):
        dialog = cls(hotkeys, parent=parent)
        return dialog.exec_(), dialog

    def serialize(self):
        return [
            hotkey_edit.hotkey
            for hotkey_edit in self.hotkey_edits
        ]

    def check_for_duplicate_hotkeys(self):
        for edit, other_edit in combinations(self.hotkey_edits, 2):
            if edit.hotkey.matches(other_edit.hotkey):
                raise RuntimeError(
                    "`{hotkey1}` is clashing with another hotkey `{hotkey2}`".format(
                        hotkey1=edit.hotkey.caption, hotkey2=other_edit.hotkey.caption))

    def reset_to_defaults_on_triggered(self):
        for hotkey_edit in self.hotkey_edits:
            hotkey_edit.reset_to_default()

    def accept_on_clicked(self):
        try:
            self.check_for_duplicate_hotkeys()
            self.accept()
        except Exception as err:
            utils.show_error_msg("Error!", str(err), self.parent())


class HotkeyEdit(QtWidgets.QLineEdit):

    key_pressed = QtCore.Signal(QtWidgets.QLineEdit, QtGui.QKeyEvent)

    def __init__(self, hotkey, parent=None):
        self.hotkey = hotkey

        QtWidgets.QLineEdit.__init__(self, self.hotkey.key_to_string(), parent=parent)

    def keyPressEvent(self, key_event):
        if not key_event.text():
            return

        key_values = Hotkey.serialize_key_event(key_event)

        self.hotkey.shift = key_values["shift"]
        self.hotkey.ctrl = key_values["ctrl"]
        self.hotkey.alt = key_values["alt"]
        self.hotkey.key = key_values["key"]

        self.setText(self.hotkey.key_to_string())

    def mousePressEvent(self, event):
        self.selectAll()

    def reset_to_default(self):
        self.hotkey.reset_to_default()
        self.setText(self.hotkey.key_to_string())
