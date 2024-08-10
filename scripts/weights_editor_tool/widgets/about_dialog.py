from weights_editor_tool import constants, weights_editor_utils as utils
from weights_editor_tool.widgets.widgets_utils import *


class AboutDialog(QDialog):

    def __init__(self, version, parent=None):
        QDialog.__init__(self, parent=parent)

        self._version = version

        self._create_gui()

    def _wrap_groupbox(self, title, msg):
        label = QLabel(msg, parent=self)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
        label.setCursor(QCursor(Qt.IBeamCursor))
        label.setOpenExternalLinks(True)

        layout = QVBoxLayout()
        layout.addWidget(label)

        groupbox = QGroupBox(title, parent=self)
        groupbox.setLayout(layout)

        return groupbox

    def _create_gui(self):
        self._logo_img = QLabel(parent=self)
        self._logo_img.setAlignment(Qt.AlignCenter)
        self._logo_img.setPixmap(utils.load_pixmap("about/logo.png", width=125))

        self._version_label = QLabel("Version v{}".format(self._version), parent=self)
        self._version_label.setAlignment(Qt.AlignCenter)
        self._version_label.setStyleSheet(
            "QLabel {font-weight: bold; color: white;}")

        self._table_tips_groupbox = self._wrap_groupbox(
            "Using weights list / table",
            "- Right-click a cell to edit its value<br>"
            "- Press space to toggle locks on selected influences<br>"
            "- Click top or side headers to select rows or columns<br>"
            "- Middle-click influence header to display that influence<br>"
            "- Right-click influence header to trigger a menu")

        self._inf_list_tips_groupbox = self._wrap_groupbox(
            "Using influence list",
            "- Press space to toggle locks on selected influences<br>"
            "- Middle-click header to display that influence<br>"
            "- Right-click to trigger a menu<br>"
            "- Double-click to select the influence")

        self._limitations_groupbox = self._wrap_groupbox(
            "Limitations",
            "- This may not handle very dense meshes. Either work with smaller selections, or with a proxy mesh.<br>"
            "- External changes to skin weights won't be detected. Things like painting weights while the tool is open"
            " aren't reflected and require the object to be refreshed to see any modifications. This is to prevent "
            "constant monitoring and improve its performance.")

        self._developed_by_groupbox = self._wrap_groupbox(
            "Developed by",
            "<b>Jason Labbe</b>")

        self._special_thanks_groupbox = self._wrap_groupbox(
            "Special thanks to",
            "<b>Enrique Caballero</b> and <b>John Lienard</b> for pushing me to make this")

        self._bugs_groupbox = self._wrap_groupbox(
            "Bugs and features",
            "Please report any bugs on its <b><a href='{url}'>GitHub issues page</a></b>".format(url=constants.GITHUB_ISSUES))

        self._scroll_layout = QVBoxLayout()
        self._scroll_layout.addWidget(self._table_tips_groupbox)
        self._scroll_layout.addWidget(self._inf_list_tips_groupbox)
        self._scroll_layout.addWidget(self._limitations_groupbox)
        self._scroll_layout.addWidget(self._developed_by_groupbox)
        self._scroll_layout.addWidget(self._special_thanks_groupbox)
        self._scroll_layout.addWidget(self._bugs_groupbox)
        self._scroll_layout.addStretch()

        self._scroll_frame = QFrame(parent=self)
        self._scroll_frame.setLayout(self._scroll_layout)

        self._scroll_area = QScrollArea(parent=self)
        self._scroll_area.setFocusPolicy(Qt.NoFocus)
        self._scroll_area.setStyleSheet("QScrollArea {border: none;}")
        self._scroll_area.setWidget(self._scroll_frame)
        self._scroll_area.setWidgetResizable(True)

        self._ok_button = QPushButton("OK", parent=self)
        self._ok_button.clicked.connect(self.close)

        self._ok_layout = QHBoxLayout()
        self._ok_layout.addStretch()
        self._ok_layout.addWidget(self._ok_button)
        self._ok_layout.addStretch()

        self._main_layout = QVBoxLayout()
        self._main_layout.addWidget(self._logo_img)
        self._main_layout.addWidget(self._version_label)
        self._main_layout.addWidget(self._scroll_area)
        self._main_layout.addLayout(self._ok_layout)
        self.setLayout(self._main_layout)

        self.setWindowTitle("About Weights Editor")
        self.resize(400, 500)

    @classmethod
    def launch(cls, version, parent):
        dialog = cls(version, parent=parent)
        dialog.exec_()
        return dialog
