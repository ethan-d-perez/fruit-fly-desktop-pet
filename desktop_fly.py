import sys
import json
import math
import random
import numpy as np
from PyQt6.QtWidgets import QApplication, QLabel, QWidget
from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QPixmap, QPainter, QTransform, QCursor, QImage

EMOJI_OFFSET = 90


class FlyDesktopPet(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # Render emoji onto a transparent QPixmap
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

        self.canvas_size = 120
        self.label = QLabel(self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setFixedSize(self.canvas_size, self.canvas_size)
        self.label.setPixmap(self.base_pixmap)
        self.resize(self.canvas_size, self.canvas_size)

        self.x_pos, self.y_pos = 400.0, 400.0
        self.move(int(self.x_pos), int(self.y_pos))

        self.is_dragging = False
        self.struggle_angle = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.tick_count = 0
        self.visual_target_vec = (0.0, 0.0)

        # Load FlyWire escape circuit (LPLC2 -> DNp01)
        try:
            with open("escape_circuit.json") as f:
                data = json.load(f)
            loaded = data.get("synapse_count", 0)
            self.escape_synapses = loaded if loaded > 0 else 4850
            self.escape_threshold = data.get("escape_threshold", 0.25)
        except FileNotFoundError:
            self.escape_synapses = 4850
            self.escape_threshold = 0.25

        # Load FlyWire color & dark-object circuits (Dm8->Tm5c & LC11)
        try:
            with open("vision_attraction.json") as f:
                vdata = json.load(f)
            self.blue_weight = min(2.0, max(0.5, vdata.get("blue_synapses", 12000) / 10000.0))
            self.dark_weight = min(2.0, max(0.5, vdata.get("dark_synapses", 15000) / 15000.0))
        except FileNotFoundError:
            self.blue_weight = 1.2
            self.dark_weight = 1.0

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_brain_and_movement)
        self.timer.start(30)

    def get_active_screen(self):
        center = QPoint(
            int(self.x_pos + self.canvas_size / 2),
            int(self.y_pos + self.canvas_size / 2),
        )
        return QApplication.screenAt(center) or QApplication.primaryScreen()

    def set_sprite_angle(self, angle_degrees):
        transform = QTransform().rotate(angle_degrees)
        rotated = self.base_pixmap.transformed(
            transform, Qt.TransformationMode.SmoothTransformation
        )
        self.label.setPixmap(rotated)

    def rotate_sprite(self, dx, dy):
        if math.hypot(dx, dy) < 0.1:
            return
        angle = math.degrees(math.atan2(dy, dx)) + EMOJI_OFFSET
        self.struggle_angle = angle
        self.set_sprite_angle(angle)

    def clamp_to_screen(self):
        screen = self.get_active_screen().availableGeometry()
        max_x = screen.right() - self.canvas_size
        max_y = screen.bottom() - self.canvas_size
        self.x_pos = max(float(screen.left()), min(self.x_pos, float(max_x)))
        self.y_pos = max(float(screen.top()), min(self.y_pos, float(max_y)))

    def scan_compound_eye(self, center_x, center_y):
        """Sample a 320x320 screen patch around the fly and compute pull toward blue & black."""
        screen = self.get_active_screen()
        geom = screen.geometry()
        fov_radius = 160

        left = max(geom.left(), int(center_x - fov_radius))
        top = max(geom.top(), int(center_y - fov_radius))
        right = min(geom.right(), int(center_x + fov_radius))
        bottom = min(geom.bottom(), int(center_y + fov_radius))

        width = right - left
        height = bottom - top
        if width < 40 or height < 40:
            return (0.0, 0.0)

        # Grab screen region behind the fly
        pixmap = screen.grabWindow(0, left - geom.left(), top - geom.top(), width, height)
        qimg = pixmap.toImage().convertToFormat(QImage.Format.Format_RGB888)

        w, h = qimg.width(), qimg.height()
        ptr = qimg.bits()
        ptr.setsize(h * qimg.bytesPerLine())
        arr = np.frombuffer(ptr, dtype=np.uint8).reshape((h, qimg.bytesPerLine()))
        rgb = arr[:, : w * 3].reshape((h, w, 3))

        # Downsample by 4x for ultra-fast (~0.5ms) processing
        step = 4
        small = rgb[::step, ::step].astype(np.int16)
        sh, sw, _ = small.shape

        # Coordinates relative to the fly's center
        fly_local_x = (center_x - left) / step
        fly_local_y = (center_y - top) / step
        yy, xx = np.ogrid[:sh, :sw]
        dx_grid = xx - fly_local_x
        dy_grid = yy - fly_local_y
        dist_grid = np.hypot(dx_grid, dy_grid)

        # Mask out inner radius (< 65px) so the fly never chases its own black sprite!
        self_mask_radius = 65.0 / step
        peripheral_mask = dist_grid > self_mask_radius

        r, g, b = small[:, :, 0], small[:, :, 1], small[:, :, 2]

        # 1. R8 -> Dm8 -> Tm5c Blue Color Detection
        blue_mask = peripheral_mask & (b > 125) & (b > r + 45) & (b > g + 25)

        # 2. LC11 High-Contrast Black/Dark Spot Detection
        dark_mask = peripheral_mask & (r < 45) & (g < 45) & (b < 45)

        # Ignore uniform backgrounds (e.g., full-screen dark mode or solid blue wallpaper)
        total_peripheral = max(1, int(peripheral_mask.sum()))
        blue_ratio = blue_mask.sum() / total_peripheral
        dark_ratio = dark_mask.sum() / total_peripheral

        weights = np.zeros((sh, sw), dtype=np.float32)
        if 0.005 < blue_ratio < 0.60:
            weights[blue_mask] += self.blue_weight
        if 0.005 < dark_ratio < 0.60:
            weights[dark_mask] += self.dark_weight

        total_weight = float(weights.sum())
        if total_weight < 1.0:
            return (0.0, 0.0)

        # Weighted centroid of attractive blue/black pixels
        target_dx = float((dx_grid * weights).sum() / total_weight)
        target_dy = float((dy_grid * weights).sum() / total_weight)
        mag = math.hypot(target_dx, target_dy)
        if mag < 1.0:
            return (0.0, 0.0)

        return (target_dx / mag, target_dy / mag)

    def update_brain_and_movement(self):
        self.tick_count += 1

        # 1. Struggle state while grabbed
        if self.is_dragging:
            self.struggle_angle = (self.struggle_angle + 42.0) % 360.0
            self.set_sprite_angle(self.struggle_angle)
            self.label.move(random.randint(-2, 2), random.randint(-2, 2))
            return

        if self.label.x() != 0 or self.label.y() != 0:
            self.label.move(0, 0)

        half = self.canvas_size / 2.0
        center_x = self.x_pos + half
        center_y = self.y_pos + half

        # 2. Highest Priority: LPLC2 -> DNp01 Cursor Escape Reflex
        cursor_pos = QCursor.pos()
        vec_x = center_x - cursor_pos.x()
        vec_y = center_y - cursor_pos.y()
        distance = math.hypot(vec_x, vec_y)

        threat_radius = 220.0
        escaping = False

        if distance < threat_radius:
            looming_stimulus = (threat_radius - distance) / threat_radius
            synaptic_gain = min(1.5, self.escape_synapses / 2500.0)
            if looming_stimulus * synaptic_gain >= self.escape_threshold:
                escaping = True
                if distance < 1.0:
                    angle = random.uniform(0, 2 * math.pi)
                    ux, uy = math.cos(angle), math.sin(angle)
                else:
                    ux, uy = vec_x / distance, vec_y / distance

                speed = 14.0 + (16.0 * looming_stimulus)
                self.vx = ux * speed
                self.vy = uy * speed

        # 3. Scan screen colors every 3rd tick (~11 Hz) when not fleeing
        if not escaping and self.tick_count % 3 == 0:
            self.visual_target_vec = self.scan_compound_eye(center_x, center_y)

        # 4. Execute movement hierarchy: Escape > Coast > Visual Color Foraging > Random Walk
        if escaping:
            self.x_pos += self.vx
            self.y_pos += self.vy
            self.clamp_to_screen()
            self.move(int(round(self.x_pos)), int(round(self.y_pos)))
            self.rotate_sprite(self.vx, self.vy)
        elif math.hypot(self.vx, self.vy) > 1.0:
            self.x_pos += self.vx
            self.y_pos += self.vy
            self.vx *= 0.78
            self.vy *= 0.78
            self.clamp_to_screen()
            self.move(int(round(self.x_pos)), int(round(self.y_pos)))
            self.rotate_sprite(self.vx, self.vy)
        elif self.visual_target_vec != (0.0, 0.0):
            # Steer toward blue/black feature with slight natural insect jitter
            tx, ty = self.visual_target_vec
            jitter_angle = random.uniform(-0.35, 0.35)
            cos_a, sin_a = math.cos(jitter_angle), math.sin(jitter_angle)
            steer_x = tx * cos_a - ty * sin_a
            steer_y = tx * sin_a + ty * cos_a

            forage_speed = 4.5
            self.x_pos += steer_x * forage_speed
            self.y_pos += steer_y * forage_speed
            self.clamp_to_screen()
            self.move(int(round(self.x_pos)), int(round(self.y_pos)))
            self.rotate_sprite(steer_x, steer_y)
        elif random.random() > 0.88:
            dx = random.choice([-10.0, 10.0, 14.0, -14.0])
            dy = random.choice([-10.0, 10.0, 14.0, -14.0])
            self.x_pos += dx
            self.y_pos += dy
            self.clamp_to_screen()
            self.move(int(round(self.x_pos)), int(round(self.y_pos)))
            self.rotate_sprite(dx, dy)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = True
            self.vx, self.vy = 0.0, 0.0
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
            self.label.move(0, 0)
            launch_rad = math.radians(self.struggle_angle - EMOJI_OFFSET)
            self.vx = math.cos(launch_rad) * 28.0
            self.vy = math.sin(launch_rad) * 28.0
            event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    pet = FlyDesktopPet()
    pet.show()
    sys.exit(app.exec())