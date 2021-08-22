from PySide2 import QtCore
from PySide2 import QtGui
from PySide2 import QtWidgets


class AboutDialog(QtWidgets.QDialog):

    def __init__(self, version, parent=None):
        QtWidgets.QDialog.__init__(self, parent=parent)

        self.version = version

        self.create_gui()

    def wrap_groupbox(self, title, msg):
        label = QtWidgets.QLabel(msg, parent=self)
        label.setWordWrap(True)
        label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        label.setCursor(QtGui.QCursor(QtCore.Qt.IBeamCursor))

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(label)

        groupbox = QtWidgets.QGroupBox(title, parent=self)
        groupbox.setLayout(layout)

        return groupbox

    def create_gui(self):
        self.version_label = QtWidgets.QLabel("Version v{}".format(self.version), parent=self)

        self.table_tips_groupbox = self.wrap_groupbox(
            "Using weights list / table",
            "- Right-click a cell to edit its value<br>"
            "- Press space to toggle locks on selected influences<br>"
            "- Click top or side headers to select rows or columns<br>"
            "- Middle-click influence header to display that influence<br>"
            "- Right-click influence header to trigger a menu")

        self.inf_list_tips_groupbox = self.wrap_groupbox(
            "Using influence list",
            "- Press space to toggle locks on selected influences<br>"
            "- Middle-click to display that influence")

        self.developed_by_groupbox = self.wrap_groupbox(
            "Developed by",
            "<b>Jason Labbe</b>")

        self.special_thanks_groupbox = self.wrap_groupbox(
            "Special thanks to",
            "<b>Enrique Caballero</b> and <b>John Lienard</b> for pushing me to make this")

        self.bugs_groupbox = self.wrap_groupbox(
            "Bugs and features",
            "Please report any bugs on its GitHub issues page:<br>"
            "<font color=\"red\"><b>github.com/theRussetPotato/weights_editor</b></color>")

        self.scroll_layout = QtWidgets.QVBoxLayout()
        self.scroll_layout.addWidget(self.table_tips_groupbox)
        self.scroll_layout.addWidget(self.inf_list_tips_groupbox)
        self.scroll_layout.addWidget(self.developed_by_groupbox)
        self.scroll_layout.addWidget(self.special_thanks_groupbox)
        self.scroll_layout.addWidget(self.bugs_groupbox)
        self.scroll_layout.addStretch()

        self.scroll_frame = QtWidgets.QFrame(parent=self)
        self.scroll_frame.setLayout(self.scroll_layout)

        self.scroll_area = QtWidgets.QScrollArea(parent=self)
        self.scroll_area.setFocusPolicy(QtCore.Qt.NoFocus)
        self.scroll_area.setStyleSheet("QScrollArea {border: none;}")
        self.scroll_area.setWidget(self.scroll_frame)
        self.scroll_area.setWidgetResizable(True)

        self.ok_button = QtWidgets.QPushButton("OK", parent=self)
        self.ok_button.clicked.connect(self.close)

        self.ok_layout = QtWidgets.QHBoxLayout()
        self.ok_layout.addStretch()
        self.ok_layout.addWidget(self.ok_button)
        self.ok_layout.addStretch()

        self.main_layout = QtWidgets.QVBoxLayout()
        self.main_layout.addWidget(self.version_label)
        self.main_layout.addWidget(self.scroll_area)
        self.main_layout.addLayout(self.ok_layout)
        self.setLayout(self.main_layout)

        self.setWindowTitle("About Weights Editor")
        self.resize(400, 450)

    @classmethod
    def launch(cls, version, parent):
        dialog = cls(version, parent=parent)
        dialog.exec_()
        return dialog
