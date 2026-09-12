"""Consistent page header with title, subtitle, and action slot."""

from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from comicdesk.ui.theme import SPACING


class PanelChrome(QWidget):
    """Header row used at the top of major workflow pages."""

    def __init__(
        self,
        title: str,
        subtitle: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("panelChrome")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACING["lg"], SPACING["md"], SPACING["lg"], SPACING["md"])
        layout.setSpacing(SPACING["md"])

        text_column = QVBoxLayout()
        text_column.setSpacing(2)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("panelChromeTitle")
        text_column.addWidget(self.title_label)
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("panelChromeSubtitle")
        self.subtitle_label.setWordWrap(True)
        if subtitle:
            text_column.addWidget(self.subtitle_label)
        else:
            self.subtitle_label.hide()
        layout.addLayout(text_column, 1)

        self.actions_host = QWidget()
        self.actions_host.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        self.actions_layout = QHBoxLayout(self.actions_host)
        self.actions_layout.setContentsMargins(0, 0, 0, 0)
        self.actions_layout.setSpacing(SPACING["sm"])
        layout.addWidget(self.actions_host)

    def set_subtitle(self, text: str) -> None:
        self.subtitle_label.setText(text)
        self.subtitle_label.setVisible(bool(text))

    def add_action_widget(self, widget: QWidget) -> None:
        self.actions_layout.addWidget(widget)
