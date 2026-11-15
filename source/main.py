import sys
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QFrame,
    QLayout,
)
from PyQt6.QtCore import Qt, QTimer, QPoint

from brain import load_flywire_brain
from fly_pet import FlyDesktopPet


class FlyManagerHUD(QWidget):
    """Draggable, auto-resizing control panel with collapsible details & mini-bar mode."""

    def __init__(self):
        super().__init__()
        self.flies: list[FlyDesktopPet] = []
        self.max_flies = 8
        self.brain_data = load_flywire_brain("fly_brain_weights.json")

        self.is_minimized = False
        self.show_details = True
        self._user_moved = False
        self._is_dragging = False
        self._drag_offset = QPoint()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.init_ui()
        self.add_fly()
        self.anchor_bottom_right()

        self.ui_timer = QTimer(self)
        self.ui_timer.timeout.connect(self.refresh_telemetry)
        self.ui_timer.start(80)

    def init_ui(self):
        self.outer_layout = QVBoxLayout(self)
        self.outer_layout.setContentsMargins(0, 0, 0, 0)
        # Forces the frameless window to always hug the exact size of visible widgets
        self.outer_layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)

        self.card = QFrame()
        self.card.setFixedWidth(295)
        self.card.setStyleSheet("""
            QFrame {
                background-color: rgba(15, 23, 42, 238);
                border: 1px solid rgba(148, 163, 184, 80);
                border-radius: 10px;
                color: #f8fafc;
                font-family: 'Segoe UI', sans-serif;
            }
            QPushButton {
                background-color: rgba(51, 65, 85, 210);
                border: 1px solid rgba(148, 163, 184, 85);
                border-radius: 5px;
                color: #f8fafc;
                font-weight: bold;
                padding: 3px 10px;
            }
            QPushButton:hover {
                background-color: rgba(71, 85, 105, 245);
            }
            QPushButton#headerBtn {
                background-color: transparent;
                border: none;
                color: #94a3b8;
                padding: 2px 6px;
                font-size: 12px;
            }
            QPushButton#headerBtn:hover {
                color: #f8fafc;
            }
            QPushButton#quitBtn {
                background-color: transparent;
                border: none;
                color: #94a3b8;
                padding: 2px 6px;
            }
            QPushButton#quitBtn:hover {
                color: #f87171;
            }
            QPushButton#toggleDetailsBtn {
                background-color: rgba(30, 41, 59, 220);
                border: 1px solid rgba(148, 163, 184, 65);
                color: #cbd5e1;
                font-size: 10px;
                font-weight: normal;
                padding: 3px 8px;
            }
            QPushButton#toggleDetailsBtn:hover {
                background-color: rgba(51, 65, 85, 235);
                color: #f8fafc;
            }
        """)
        self.outer_layout.addWidget(self.card)

        self.main_layout = QVBoxLayout(self.card)
        self.main_layout.setContentsMargins(11, 8, 11, 8)
        self.main_layout.setSpacing(8)

        # Header Row (Draggable + Minimize & Quit buttons)
        header = QHBoxLayout()
        header.setSpacing(6)
        self.title_label = QLabel("🪰 FlyWire Manager")
        self.title_label.setStyleSheet(
            "font-weight: bold; font-size: 12px; border: none; background: transparent;"
        )

        self.min_btn = QPushButton("—")
        self.min_btn.setObjectName("headerBtn")
        self.min_btn.setToolTip("Minimize / Expand Manager")
        self.min_btn.clicked.connect(self.toggle_minimize)

        quit_btn = QPushButton("✕")
        quit_btn.setObjectName("quitBtn")
        quit_btn.setToolTip("Close all flies and exit")
        quit_btn.clicked.connect(QApplication.quit)

        header.addWidget(self.title_label)
        header.addStretch()
        header.addWidget(self.min_btn)
        header.addWidget(quit_btn)
        self.main_layout.addLayout(header)

        # Collapsible Body Container
        self.body_widget = QWidget()
        self.body_widget.setStyleSheet("background: transparent; border: none;")
        body_layout = QVBoxLayout(self.body_widget)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(8)

        # Population Controls Row
        controls = QHBoxLayout()
        self.remove_btn = QPushButton("−")
        self.remove_btn.clicked.connect(self.remove_fly)

        self.count_label = QLabel("Active Flies: 0")
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.count_label.setStyleSheet("font-size: 12px;")

        self.add_btn = QPushButton("+")
        self.add_btn.clicked.connect(self.add_fly)

        controls.addWidget(self.remove_btn)
        controls.addWidget(self.count_label, 1)
        controls.addWidget(self.add_btn)
        body_layout.addLayout(controls)

        # Connectome Metadata + Hide/Show Details Toggle Row
        meta_row = QHBoxLayout()
        meta = QLabel(self.brain_data["source_label"])
        meta.setStyleSheet("font-size: 10px; color: #94a3b8;")

        self.details_btn = QPushButton("Hide Details")
        self.details_btn.setObjectName("toggleDetailsBtn")
        self.details_btn.setToolTip("Toggle brain circuit readout and under-fly labels")
        self.details_btn.clicked.connect(self.toggle_details)

        meta_row.addWidget(meta)
        meta_row.addStretch()
        meta_row.addWidget(self.details_btn)
        body_layout.addLayout(meta_row)

        # Live Brain Circuit Telemetry Readout
        self.telemetry_label = QLabel()
        self.telemetry_label.setStyleSheet("font-size: 11px;")
        body_layout.addWidget(self.telemetry_label)

        self.main_layout.addWidget(self.body_widget)

    def _restore_anchor(self, old_bottom_right: QPoint):
        """Recalculate window size and keep its bottom-right corner pinned in place."""
        self.outer_layout.activate()
        self.adjustSize()

        if not self._user_moved:
            self.anchor_bottom_right()
        else:
            new_x = old_bottom_right.x() - self.width() + 1
            new_y = old_bottom_right.y() - self.height() + 1
            screen = (
                QApplication.screenAt(old_bottom_right)
                or QApplication.primaryScreen()
            ).availableGeometry()
            new_x = max(screen.left(), min(new_x, screen.right() - self.width()))
            new_y = max(screen.top(), min(new_y, screen.bottom() - self.height()))
            self.move(new_x, new_y)

    def anchor_bottom_right(self):
        self.outer_layout.activate()
        self.adjustSize()
        screen = QApplication.primaryScreen().availableGeometry()
        margin = 14
        x = screen.right() - self.width() - margin
        y = screen.bottom() - self.height() - margin
        self.move(x, y)

    def toggle_minimize(self):
        old_br = self.frameGeometry().bottomRight()
        self.is_minimized = not self.is_minimized

        self.body_widget.setVisible(not self.is_minimized)
        if self.is_minimized:
            self.title_label.setText("🪰")
            self.min_btn.setText("▢")
            self.card.setMinimumWidth(0)
            self.card.setMaximumWidth(16777215)
        else:
            self.title_label.setText("🪰 FlyWire Manager")
            self.min_btn.setText("—")
            self.card.setFixedWidth(295)

        self.refresh_telemetry()
        self._restore_anchor(old_br)

    def toggle_details(self):
        old_br = self.frameGeometry().bottomRight()
        self.show_details = not self.show_details

        self.telemetry_label.setVisible(self.show_details)
        self.details_btn.setText("Show Details" if not self.show_details else "Hide Details")
        for fly in self.flies:
            fly.set_badges_visible(self.show_details)

        self.refresh_telemetry()
        self._restore_anchor(old_br)

    def add_fly(self):
        if len(self.flies) >= self.max_flies:
            return
        old_br = self.frameGeometry().bottomRight()
        fly_id = len(self.flies) + 1
        fly = FlyDesktopPet(
            fly_id=fly_id,
            brain_data=self.brain_data,
            manager=self,
            show_badges=self.show_details,
        )
        fly.show()
        self.flies.append(fly)
        self.refresh_telemetry()
        self._restore_anchor(old_br)

    def remove_fly(self):
        if not self.flies:
            return
        old_br = self.frameGeometry().bottomRight()
        fly = self.flies.pop()
        fly.timer.stop()
        fly.close()
        fly.deleteLater()
        self.refresh_telemetry()
        self._restore_anchor(old_br)

    def refresh_telemetry(self):
        count = len(self.flies)
        self.count_label.setText(f"Active Flies: {count}")
        self.remove_btn.setEnabled(count > 0)
        self.add_btn.setEnabled(count < self.max_flies)

        if not self.show_details or self.is_minimized:
            return

        if not self.flies:
            self.telemetry_label.setText(
                "<span style='color:#64748b;'>No active flies. Click + to spawn.</span>"
            )
            return

        lines = []
        for fly in self.flies:
            st = fly.state
            lines.append(
                f"<b>Fly #{fly.fly_id}</b>: "
                f"<span style='color:{st.color};'><b>{st.label}</b></span><br>"
                f"<span style='color:#94a3b8; font-size:10px;'>&nbsp;&nbsp;↳ {fly.active_circuit}</span>"
            )
        self.telemetry_label.setText("<br>".join(lines))

    # --- Drag-anywhere support for the frameless HUD ---
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = True
            self._drag_offset = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            event.accept()

    def mouseMoveEvent(self, event):
        if self._is_dragging and (event.buttons() & Qt.MouseButton.LeftButton):
            self._user_moved = True
            new_pos = event.globalPosition().toPoint() - self._drag_offset
            self.move(new_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = False
            event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    hud = FlyManagerHUD()
    hud.show()
    sys.exit(app.exec())