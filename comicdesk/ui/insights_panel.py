"""Local collection statistics for the Collection area."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from comicdesk.models import Comic
from comicdesk.services.library_insights import compute_library_insights
from comicdesk.ui.theme import muted_label_stylesheet


class InsightsPanel(QWidget):
    """Read-only summary from the current library scan."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._theme = "dark"
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        self.summary_label = QLabel("Scan a folder on Browse to see insights.")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)
        self.publishers_label = QLabel("")
        self.publishers_label.setWordWrap(True)
        layout.addWidget(self.publishers_label)
        self.years_label = QLabel("")
        self.years_label.setWordWrap(True)
        layout.addWidget(self.years_label)
        self.gaps_label = QLabel("")
        self.gaps_label.setWordWrap(True)
        layout.addWidget(self.gaps_label)
        layout.addStretch()
        self.apply_theme(self._theme)

    def set_comics(self, comics: list[Comic]) -> None:
        if not comics:
            self.summary_label.setText("No comics loaded.")
            self.publishers_label.setText("")
            self.years_label.setText("")
            self.gaps_label.setText("")
            return
        insights = compute_library_insights(comics)
        self.summary_label.setText(f"Total files: {insights.total_files}")
        pub_lines = [
            f"{name}: {count}"
            for name, count in list(insights.publishers.items())[:15]
        ]
        self.publishers_label.setText(
            "Top publishers:\n" + ("\n".join(pub_lines) if pub_lines else "—")
        )
        year_lines = [
            f"{year}: {count}"
            for year, count in list(insights.years.items())[:15]
        ]
        self.years_label.setText(
            "Years:\n" + ("\n".join(year_lines) if year_lines else "—")
        )
        if insights.incomplete_series_names:
            preview = ", ".join(insights.incomplete_series_names[:12])
            extra = ""
            if len(insights.incomplete_series_names) > 12:
                extra = f" (+{len(insights.incomplete_series_names) - 12} more)"
            self.gaps_label.setText(
                f"Series with gaps ({insights.series_with_gaps}): {preview}{extra}"
            )
        else:
            self.gaps_label.setText("No series gaps detected (Count + issue numbers).")

    def apply_theme(self, theme: str) -> None:
        self._theme = theme
        muted = muted_label_stylesheet(theme)
        for label in (
            self.summary_label,
            self.publishers_label,
            self.years_label,
            self.gaps_label,
        ):
            label.setStyleSheet(muted)
