
import math
import struct

PASSWORD = bytearray(b"WIZ")
END_BYTE = bytearray([3])
CMD_DRIVE = 1

# ---------------------------- CALIBRATION ----------------------------
# Units are whatever Robot.position uses (the old code assumed 100 units/square).
# Encoder counts per unit of WHEEL TRAVEL:
#   counts_per_wheel_rev / (pi * wheel_diameter_in_units)
# 105 is the old robot's number (10500 counts / 100 units). RECALIBRATE.
COUNTS_PER_UNIT = 105.0
# Distance from robot centre to each wheel's contact point, in position units.
ROBOT_RADIUS = 10.0
# Angle of each wheel around the robot, measured CCW from the robot's forward axis.
WHEEL_ANGLES_DEG = (90.0, 210.0, 330.0)
# ---------------------------------------------------------------------

INT16_MAX = 32767

# Unit vector along which wheel i drives the robot (tangent, CCW), robot frame.
_WHEEL_DIRS = tuple((-math.sin(a), math.cos(a))
                    for a in map(math.radians, WHEEL_ANGLES_DEG))


class Robot:

    def __init__(self, id, position, angle, server, device_id):
        self.id = id
        self.position = tuple(position)
        self.server = server
        self.device_id = device_id

        # Angle is measured counterclockwise from horizontal
        self.angle = angle % 360
        self.initial_angle = self.angle

        self.buffer = bytearray()

    def __repr__(self):
        return str(self.id)

    # ------------------------------------------------------------------
    # Low level
    # ------------------------------------------------------------------
    def _queue(self, counts):
        """Append a DRIVE command for the given per-wheel counts.

        Anything that doesn't fit in int16 is split into equal chunks, so long
        moves work instead of silently overflowing.
        """
        peak = max(abs(c) for c in counts)
        if peak == 0:
            return
        chunks = -(-peak // INT16_MAX)  # ceil division
        prev = (0, 0, 0)
        for i in range(1, chunks + 1):
            cum = tuple(round(c * i / chunks) for c in counts)
            self.buffer += struct.pack(">B3h", CMD_DRIVE,
                                       *(a - b for a, b in zip(cum, prev)))
            prev = cum

    # ------------------------------------------------------------------
    # Motion commands (buffered)
    # ------------------------------------------------------------------
    def move_by(self, dx, dy):
        """Translate by (dx, dy) in the WORLD frame, heading unchanged."""
        if dx == 0 and dy == 0:
            return
        # World -> robot frame (rotate by -angle)
        th = math.radians(self.angle)
        c, s = math.cos(th), math.sin(th)
        rx, ry = c * dx + s * dy, c * dy - s * dx
        self._queue([round(COUNTS_PER_UNIT * (kx * rx + ky * ry))
                     for kx, ky in _WHEEL_DIRS])
        self.position = (self.position[0] + dx, self.position[1] + dy)

    def move_to(self, position):
        """Straight line to a world position. No turning required."""
        self.move_by(position[0] - self.position[0],
                     position[1] - self.position[1])

    def turn(self, angle):
        """Rotate in place. Positive = counterclockwise, negative = clockwise."""
        if angle == 0:
            return
        ticks = round(COUNTS_PER_UNIT * ROBOT_RADIUS * math.radians(angle))
        self._queue([ticks] * 3)  # all wheels same sign = pure spin
        self.angle = (self.angle + angle) % 360

    def turn_to(self, angle):
        """Rotate to an absolute heading via the shortest direction."""
        self.turn((angle - self.angle + 180) % 360 - 180)

    def face_forward(self):
        self.turn_to(self.initial_angle)

    def execute_path(self, path_points):
        """Follow a list of waypoints. Collinear points are merged into a
        single drive command, and no turns are inserted between segments."""
        for p in self._merge_collinear(path_points):
            self.move_to(p)
        self.face_forward()  # no-op unless the heading was changed

    def _merge_collinear(self, points, tol=1e-6):
        merged = [self.position]
        for p in points:
            if p == merged[-1]:
                continue
            if len(merged) >= 2:
                ax, ay = merged[-1][0] - merged[-2][0], merged[-1][1] - merged[-2][1]
                bx, by = p[0] - merged[-1][0], p[1] - merged[-1][1]
                same_dir = (abs(ax * by - ay * bx) <= tol * math.hypot(ax, ay) * math.hypot(bx, by)
                            and ax * bx + ay * by > 0)
                if same_dir:
                    merged[-1] = p
                    continue
            merged.append(p)
        return merged[1:]

    # ------------------------------------------------------------------
    def send_buffer(self):
        """MUST be called for buffered commands to actually reach the robot."""
        if self.server and self.buffer:
            self.server.send_command(self.device_id,
                                     PASSWORD + self.buffer + END_BYTE)
        self.buffer = bytearray()