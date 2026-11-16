import ctypes
import math
import random
from PyQt6.QtWidgets import QApplication, QLabel, QWidget, QHBoxLayout
from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QPixmap, QPainter, QTransform, QCursor

from brain import FlyBrain, BrainState


HWND_TOPMOST = -1
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010


def keep_window_topmost(widget: QWidget):
    """Re-assert Win32 HWND_TOPMOST without stealing focus from active apps."""
    if hasattr(ctypes, "windll"):
        ctypes.windll.user32.SetWindowPos(
            int(widget.winId()),
            HWND_TOPMOST,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
        )

class FlyDesktopPet(QWidget):
    """Transparent always-on-top desktop sprite with toggleable under-sprite badges."""

    def __init__(self, fly_id: int, brain_data: dict, manager=None, show_badges: bool = True):
        super().__init__()
        self.fly_id = fly_id
        self.manager = manager
        self.brain = FlyBrain(brain_data)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # Render emoji onto a transparent QPixmap using pixel size (immune to Windows DPI shift)
        sprite_size = 80
        self.base_pixmap = QPixmap(sprite_size, sprite_size)
        self.base_pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(self.base_pixmap)
        font = painter.font()
        font.setPixelSize(44)
        painter.setFont(font)
        painter.drawText(
            self.base_pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "🪰"
        )
        painter.end()

        self.sprite_canvas = 120
        self.win_width = 128
        self.win_height = 142
        self.sprite_x_offset = (self.win_width - self.sprite_canvas) // 2

        self.resize(self.win_width, self.win_height)

        self.label = QLabel(self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setGeometry(
            self.sprite_x_offset, 0, self.sprite_canvas, self.sprite_canvas
        )
        self.label.setPixmap(self.base_pixmap)

        # Bottom badge bar directly beneath the fly sprite
        self.badge_bar = QWidget(self)
        self.badge_bar.setGeometry(2, 118, self.win_width - 4, 22)
        self.badge_bar.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        badge_layout = QHBoxLayout(self.badge_bar)
        badge_layout.setContentsMargins(2, 0, 2, 0)
        badge_layout.setSpacing(4)

        self.state_label = QLabel()
        self.id_label = QLabel(f"#{self.fly_id}")
        self.id_label.setStyleSheet("""
            QLabel {
                background-color: rgba(15, 23, 42, 205);
                color: #e2e8f0;
                border: 1px solid rgba(148, 163, 184, 70);
                border-radius: 4px;
                padding: 1px 5px;
                font-family: 'Segoe UI', sans-serif;
                font-size: 10px;
                font-weight: bold;
            }
        """)

        badge_layout.addWidget(self.state_label, 0, Qt.AlignmentFlag.AlignLeft)
        badge_layout.addStretch()
        badge_layout.addWidget(self.id_label, 0, Qt.AlignmentFlag.AlignRight)

        self._rendered_state: BrainState | None = None
        self._sync_state_badge()
        self.set_badges_visible(show_badges)

        # Spawn near the center of the primary screen
        screen = QApplication.primaryScreen().availableGeometry()
        self.x_pos = float(screen.center().x() + random.randint(-180, 180))
        self.y_pos = float(screen.center().y() + random.randint(-180, 180))
        self.move(int(self.x_pos), int(self.y_pos))

        self.is_dragging = False
        self.drag_position = QPoint()
        self.set_sprite_angle(self.brain.sprite_angle)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(30)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        self._z_order_counter = 0

    @property
    def state(self) -> BrainState:
        return self.brain.state

    @property
    def active_circuit(self) -> str:
        return self.brain.active_circuit

    def set_badges_visible(self, visible: bool):
        self.badge_bar.setVisible(visible)

    def _sync_state_badge(self):
        current = self.brain.state
        if current == self._rendered_state:
            return
        self._rendered_state = current
        self.state_label.setText(current.label)
        self.state_label.setStyleSheet(f"""
            QLabel {{
                background-color: rgba(15, 23, 42, 205);
                color: {current.color};
                border: 1px solid rgba(148, 163, 184, 70);
                border-radius: 4px;
                padding: 1px 5px;
                font-family: 'Segoe UI', sans-serif;
                font-size: 10px;
                font-weight: bold;
            }}
        """)

    def get_center(self) -> tuple[float, float]:
        return (
            self.x_pos + self.win_width / 2.0,
            self.y_pos + self.sprite_canvas / 2.0,
        )

    def get_active_screen_geometry(self):
        cx, cy = self.get_center()
        screen = QApplication.screenAt(QPoint(int(cx), int(cy))) or QApplication.primaryScreen()
        return screen.availableGeometry()

    def set_sprite_angle(self, angle_degrees: float):
        transform = QTransform().rotate(angle_degrees)
        rotated = self.base_pixmap.transformed(
            transform, Qt.TransformationMode.SmoothTransformation
        )
        self.label.setPixmap(rotated)

    def clamp_to_screen(self, heading: float):
        screen = self.get_active_screen_geometry()
        min_x = float(screen.left())
        max_x = float(screen.right() - self.win_width)
        min_y = float(screen.top())
        max_y = float(screen.bottom() - self.win_height)

        reflect_x = False
        reflect_y = False

        if self.x_pos <= min_x:
            self.x_pos = min_x
            if math.cos(heading) < 0:
                reflect_x = True
        elif self.x_pos >= max_x:
            self.x_pos = max_x
            if math.cos(heading) > 0:
                reflect_x = True

        if self.y_pos <= min_y:
            self.y_pos = min_y
            if math.sin(heading) < 0:
                reflect_y = True
        elif self.y_pos >= max_y:
            self.y_pos = max_y
            if math.sin(heading) > 0:
                reflect_y = True

        if reflect_x or reflect_y:
            self.brain.reflect_heading(reflect_x, reflect_y)

    def gather_neighbors(self, center_x: float, center_y: float) -> list[dict]:
        if self.manager is None:
            return []

        neighbors = []
        for other in self.manager.flies:
            if other is self:
                continue
            ox, oy = other.get_center()
            dx = ox - center_x
            dy = oy - center_y
            dist = math.hypot(dx, dy)
            neighbors.append(
                {
                    "dx": dx,
                    "dy": dy,
                    "dist": dist,
                    "is_fleeing": (
                        other.state == BrainState.FLEEING
                        and other.brain.burst_speed > 20.0
                    ),
                }
            )
        return neighbors

    def tick(self):
        self._z_order_counter += 1
        if self._z_order_counter >= 15:
            self._z_order_counter = 0
            keep_window_topmost(self)

        center_x, center_y = self.get_center()

        cursor_pos = QCursor.pos()
        cursor_in_hud = (
            self.manager is not None
            and self.manager.frameGeometry().contains(cursor_pos)
        )

        if cursor_in_hud:
            vec_x, vec_y, distance = 0.0, 0.0, float("inf")
        else:
            vec_x = cursor_pos.x() - center_x
            vec_y = cursor_pos.y() - center_y
            distance = math.hypot(vec_x, vec_y)

        neighbors = self.gather_neighbors(center_x, center_y)

        state, heading, sprite_angle, speed = self.brain.step(
            vec_x, vec_y, distance, self.is_dragging, neighbors
        )
        self._sync_state_badge()

        if state == BrainState.STRUGGLING:
            self.set_sprite_angle(sprite_angle)
            self.label.move(
                self.sprite_x_offset + random.randint(-2, 2),
                random.randint(-2, 2),
            )
            return

        if self.label.x() != self.sprite_x_offset or self.label.y() != 0:
            self.label.move(self.sprite_x_offset, 0)

        self.x_pos += math.cos(heading) * speed
        self.y_pos += math.sin(heading) * speed
        self.clamp_to_screen(heading)
        self.move(int(round(self.x_pos)), int(round(self.y_pos)))
        self.set_sprite_angle(self.brain.sprite_angle)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        self._z_order_counter = 0

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = True
            self.brain.on_grab()
            self._sync_state_badge()
            self.drag_position = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            new_pos = event.globalPosition().toPoint() - self.drag_position
            self.x_pos = float(new_pos.x())
            self.y_pos = float(new_pos.y())
            self.move(int(round(self.x_pos)), int(round(self.y_pos)))
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = False
            self.label.move(self.sprite_x_offset, 0)
            self.brain.on_release()
            self._sync_state_badge()
            event.accept()