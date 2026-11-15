import os
import sys
import json
import math
import random
from enum import Enum
import numpy as np

# Calibrated for Windows 11 🪰 emoji (faces top-left at -135° at rest).
# Use 180 on Windows 10, or 90 for a custom sprite facing straight up.
EMOJI_OFFSET = 90

class BrainState(Enum):
    WANDER = ("Wandering", "PFL3 → DNa02 (Solo Exploration)", "#38bdf8")
    SOCIAL = ("Socializing", "PFL3 + LC10a (Conspecific Tracking)", "#34d399")
    FLEEING = ("Fleeing!", "LPLC2/LC4 → DNp01 & DNa02", "#f87171")
    STRUGGLING = ("Struggling", "Tarsal Reflex Disinhibition", "#c084fc")

    def __init__(self, label: str, circuit: str, color: str):
        self.label = label
        self.circuit = circuit
        self.color = color

def resolve_data_path(filename: str) -> str:
    """Check next to the .exe first (for easy weight swaps), then inside the PyInstaller bundle."""
    if getattr(sys, "frozen", False):
        external_path = os.path.join(os.path.dirname(sys.executable), filename)
        if os.path.exists(external_path):
            return external_path
        return os.path.join(sys._MEIPASS, filename)
    return filename

def load_flywire_brain(filepath: str = "fly_brain_weights.json") -> dict:
    """Load hemispheric FlyWire matrices, falling back to baseline weights if missing."""
    try:
        with open(resolve_data_path(filepath), "r") as f:
            data = json.load(f)
        weights = data["weights"]
        raw = data.get("raw_synapses", {})
        total_loom_synapses = int(
            np.array(raw.get("loom_to_gf", [[2400, 2400], [2400, 2400]])).sum()
        )
        return {
            "loom_to_gf": np.array(weights["loom_to_gf"], dtype=np.float64),
            "loom_to_steer": np.array(weights["loom_to_steer"], dtype=np.float64),
            "cx_to_steer": np.array(weights["cx_to_steer"], dtype=np.float64),
            "escape_threshold": float(data.get("escape_threshold", 0.28)),
            "source_label": f"FlyWire JSON ({total_loom_synapses:,} GF syn)",
        }
    except (FileNotFoundError, KeyError, ValueError):
        return {
            "loom_to_gf": np.array([[1.0, 0.15], [0.15, 1.0]], dtype=np.float64),
            "loom_to_steer": np.array([[0.25, 1.0], [1.0, 0.25]], dtype=np.float64),
            "cx_to_steer": np.array([[0.20, 1.0], [1.0, 0.20]], dtype=np.float64),
            "escape_threshold": 0.28,
            "source_label": "FlyWire Baseline (Default)",
        }


def _wrap_angle(angle: float) -> float:
    """Normalize angle in radians to [-pi, pi]."""
    return (angle + math.pi) % (2 * math.pi) - math.pi


class FlyBrain:
    """Simulated Drosophila connectome controller with cursor escape & LC10a social circuits."""

    def __init__(self, brain_data: dict):
        self.W_loom_gf = brain_data["loom_to_gf"]
        self.W_loom_steer = brain_data["loom_to_steer"]
        self.W_cx_steer = brain_data["cx_to_steer"]
        self.escape_threshold = brain_data["escape_threshold"]

        self.state = BrainState.WANDER
        self.active_circuit = BrainState.WANDER.circuit
        self.heading = random.uniform(0, 2 * math.pi)
        self.cx_activity = np.array([0.5, 0.5], dtype=np.float64)

        self.escape_ticks = 0
        self.social_ticks = 0  # Hysteresis timer to prevent Solo <-> Social badge flicker
        self.burst_speed = 0.0
        self.sprite_angle = (math.degrees(self.heading) + EMOJI_OFFSET) % 360.0

    def on_grab(self):
        """Disinhibit tarsal contact reflex when picked up."""
        self.escape_ticks = 0
        self.social_ticks = 0
        self.burst_speed = 0.0
        self.state = BrainState.STRUGGLING
        self.active_circuit = BrainState.STRUGGLING.circuit

    def on_release(self):
        """Launch forward along whatever direction the fly's head faces when released."""
        self.heading = math.radians(self.sprite_angle - EMOJI_OFFSET) % (2 * math.pi)
        self.escape_ticks = 10
        self.burst_speed = 32.0
        self.state = BrainState.FLEEING
        self.active_circuit = BrainState.FLEEING.circuit

    def reflect_heading(self, reflect_x: bool, reflect_y: bool):
        """Smoothly deflect heading when hitting monitor boundaries."""
        if reflect_x:
            self.heading = math.pi - self.heading
        if reflect_y:
            self.heading = -self.heading
        if reflect_x or reflect_y:
            self.heading = (self.heading + random.uniform(-0.30, 0.30)) % (2 * math.pi)
            self.sprite_angle = (math.degrees(self.heading) + EMOJI_OFFSET) % 360.0

    def _compute_social_signals(
        self, neighbors: list[dict]
    ) -> tuple[float, bool, float, str]:
        """
        Process nearby flies via LC10a conspecific tracking & alarm contagion.
        Returns: (social_turn_torque, alarm_triggered, alarm_escape_heading, social_subcircuit)
        """
        fwd_x, fwd_y = math.cos(self.heading), math.sin(self.heading)
        right_x, right_y = -fwd_y, fwd_x

        social_torque = 0.0
        alarm_triggered = False
        alarm_away_x, alarm_away_y = 0.0, 0.0
        closest_dist = float("inf")
        subcircuit = ""

        for n in neighbors:
            dx, dy, dist = n["dx"], n["dy"], n["dist"]
            if dist < 1e-3 or dist > 280.0:
                continue

            lateral = (dx * right_x + dy * right_y) / dist

            # 1. Visual Alarm Contagion: startle if a nearby fly is panicking at high speed
            if n["is_fleeing"] and dist < 210.0:
                alarm_triggered = True
                alarm_away_x -= dx / dist
                alarm_away_y -= dy / dist

            # 2. Personal Space / Collision Avoidance (< 95px)
            if dist < 95.0:
                repel_strength = (95.0 - dist) / 95.0
                sign = -1.0 if lateral >= 0 else 1.0
                social_torque += sign * repel_strength * 0.42
                if dist < closest_dist:
                    closest_dist = dist
                    subcircuit = "LC10a → DNa02 (Collision Avoidance)"

            # 3. Loose Social Grouping (130px - 280px) when calm
            elif dist > 130.0:
                attract_strength = 1.0 - abs(dist - 205.0) / 75.0
                social_torque += lateral * max(0.0, attract_strength) * 0.09
                if dist < closest_dist:
                    closest_dist = dist
                    subcircuit = "PFL3 + LC10a (Group Orbit)"

        alarm_heading = self.heading
        if alarm_triggered and math.hypot(alarm_away_x, alarm_away_y) > 1e-3:
            alarm_heading = math.atan2(alarm_away_y, alarm_away_x)

        return social_torque, alarm_triggered, alarm_heading, subcircuit

    def step(
        self,
        vec_to_cursor_x: float,
        vec_to_cursor_y: float,
        distance: float,
        is_grabbed: bool,
        neighbors: list[dict],
        threat_radius: float = 250.0,
    ) -> tuple[BrainState, float, float, float]:
        """
        Advance neural state by one tick.
        Returns: (active_state, heading_rad, sprite_angle_deg, speed_px)
        """
        if is_grabbed:
            self.state = BrainState.STRUGGLING
            self.active_circuit = BrainState.STRUGGLING.circuit
            self.sprite_angle = (self.sprite_angle + 42.0) % 360.0
            return self.state, self.heading, self.sprite_angle, 0.0

        fwd_x, fwd_y = math.cos(self.heading), math.sin(self.heading)
        right_x, right_y = -fwd_y, fwd_x

        # 1. Project cursor threat onto Left vs. Right compound eye
        if distance < threat_radius:
            intensity = (threat_radius - distance) / threat_radius
            if distance > 1e-3:
                lateral = (
                    vec_to_cursor_x * right_x + vec_to_cursor_y * right_y
                ) / distance
            else:
                lateral = random.choice([-1.0, 1.0])

            loom_input = np.array(
                [
                    intensity * max(0.05, 0.5 - 0.5 * lateral),
                    intensity * max(0.05, 0.5 + 0.5 * lateral),
                ],
                dtype=np.float64,
            )
        else:
            loom_input = np.array([0.0, 0.0], dtype=np.float64)

        # 2. Propagate through FlyWire Giant Fiber & Steering matrices
        gf_firing = loom_input @ self.W_loom_gf
        escape_steer = loom_input @ self.W_loom_steer

        # 3. Evaluate neighboring flies (LC10a collision avoidance, grouping & alarm)
        social_torque, alarm_triggered, alarm_heading, social_subcircuit = (
            self._compute_social_signals(neighbors)
        )

        # 4. State Machine & Motor Execution
        cursor_threat_active = float(gf_firing.max()) >= self.escape_threshold

        if cursor_threat_active:
            self.state = BrainState.FLEEING
            self.active_circuit = BrainState.FLEEING.circuit
            self.social_ticks = 0

            if distance > 1e-3:
                away_angle = math.atan2(-vec_to_cursor_y, -vec_to_cursor_x)
            else:
                away_angle = random.uniform(0, 2 * math.pi)

            angle_err = _wrap_angle(away_angle - self.heading)
            if abs(angle_err) > 2.7:
                angle_err += random.choice([-0.6, 0.6])

            matrix_bias = (escape_steer[1] - escape_steer[0]) * 0.25
            self.heading = (
                self.heading + (angle_err * 0.65) + matrix_bias + (social_torque * 0.4)
            ) % (2 * math.pi)

            self.escape_ticks = 14
            self.burst_speed = max(
                self.burst_speed, 24.0 + 16.0 * float(gf_firing.max())
            )
            speed = self.burst_speed

        elif alarm_triggered and self.escape_ticks <= 0 and self.burst_speed < 10.0:
            self.state = BrainState.FLEEING
            self.active_circuit = "LC10a → DNp01 (Social Alarm)"
            self.social_ticks = 0

            angle_err = _wrap_angle(alarm_heading - self.heading)
            self.heading = (
                self.heading + (angle_err * 0.7) + random.uniform(-0.35, 0.35)
            ) % (2 * math.pi)
            self.escape_ticks = 10
            self.burst_speed = 26.0
            speed = self.burst_speed

        elif self.escape_ticks > 0:
            self.state = BrainState.FLEEING
            self.escape_ticks -= 1
            self.heading = (
                self.heading + random.uniform(-0.08, 0.08) + (social_torque * 0.5)
            ) % (2 * math.pi)
            speed = self.burst_speed
            self.burst_speed *= 0.96

        elif self.burst_speed > 4.5:
            self.state = BrainState.FLEEING
            self.heading = (self.heading + (social_torque * 0.5)) % (2 * math.pi)
            speed = self.burst_speed
            self.burst_speed *= 0.89

        else:
            self.burst_speed = 0.0

            # Central Complex PFL3 ring drift + LC10a social steering
            self.cx_activity = np.clip(
                self.cx_activity + np.random.normal(0.0, 0.08, size=2), 0.1, 1.0
            )
            cx_steer = self.cx_activity @ self.W_cx_steer
            cx_turn = (cx_steer[1] - cx_steer[0]) * 0.26

            self.heading = (self.heading + cx_turn + social_torque) % (2 * math.pi)
            speed = 3.2 * float(cx_steer.mean())

            # Engage SOCIAL state if LC10a is actively steering, with 15-frame hold
            if abs(social_torque) > 0.03:
                self.social_ticks = 15
                self.state = BrainState.SOCIAL
                self.active_circuit = social_subcircuit or BrainState.SOCIAL.circuit
            elif self.social_ticks > 0:
                self.social_ticks -= 1
                self.state = BrainState.SOCIAL
            else:
                self.state = BrainState.WANDER
                self.active_circuit = BrainState.WANDER.circuit

        self.sprite_angle = (math.degrees(self.heading) + EMOJI_OFFSET) % 360.0
        return self.state, self.heading, self.sprite_angle, speed