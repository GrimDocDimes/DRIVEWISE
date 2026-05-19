"""
DRIVEWISE — Conveyor Belt Dynamics Model
Inertia, friction, variable material load, and belt slip detection.
"""
import math


class ConveyorModel:
    """Conveyor belt mechanical load simulation."""

    def __init__(self, config, motor_config):
        self.cfg = config
        self.motor = motor_config

        # Physical parameters
        self.belt_mass = config.get('belt_mass', 5000.0)
        self.max_material_mass = config.get('max_material_mass', 8000.0)
        self.friction_static = config.get('friction_static', 0.35)
        self.friction_dynamic = config.get('friction_dynamic', 0.25)
        self.pulley_diameter = config.get('pulley_diameter', 0.6)
        self.gear_ratio = config.get('gear_ratio', 15.0)
        self.belt_speed_max = config.get('belt_speed_max', 3.5)

        # State
        self.material_load_pct = 0.0    # 0-100%
        self.belt_speed = 0.0           # m/s
        self.motor_speed = 0.0          # RPM (actual)
        self.torque_demand = 0.0        # Nm at motor shaft
        self.belt_slip = False
        self.material_position = 0.0    # Normalized 0-1

        # Load profile
        self.load_profile = [20, 40, 70, 90, 100, 80, 60, 40, 30, 50, 80, 100]
        self.profile_time = 0.0
        self.profile_cycle_time = 60.0  # seconds per full cycle

        # Inertia (referred to motor shaft)
        self._update_inertia()

    def _update_inertia(self):
        """Calculate total inertia referred to motor shaft."""
        total_mass = self.belt_mass + self.max_material_mass * (self.material_load_pct / 100.0)
        pulley_radius = self.pulley_diameter / 2.0
        # Belt inertia referred to motor: J = m * r² / G²
        self.total_inertia = total_mass * pulley_radius**2 / self.gear_ratio**2
        # Add motor rotor inertia (~2 kg·m² for 75kW motor)
        self.total_inertia += 2.0

    def set_load_profile(self, profile):
        """Set the material load profile (list of % values)."""
        self.load_profile = profile

    def set_material_load(self, pct):
        """Manually set material load percentage."""
        self.material_load_pct = max(0, min(100, pct))
        self._update_inertia()

    def update(self, dt, motor_torque, speed_ref):
        """
        Update conveyor state for one time step.

        Args:
            dt: time step in seconds
            motor_torque: torque applied by drive (Nm)
            speed_ref: speed reference from drive (RPM)

        Returns:
            motor_speed: actual motor speed (RPM)
            torque_demand: load torque at motor shaft (Nm)
        """
        # === Update material load from profile ===
        self.profile_time += dt
        if self.profile_time >= self.profile_cycle_time:
            self.profile_time = 0.0

        profile_position = (self.profile_time / self.profile_cycle_time) * len(self.load_profile)
        idx = int(profile_position) % len(self.load_profile)
        next_idx = (idx + 1) % len(self.load_profile)
        frac = profile_position - int(profile_position)
        self.material_load_pct = self.load_profile[idx] * (1 - frac) + self.load_profile[next_idx] * frac
        self._update_inertia()

        # === Calculate load torque ===
        total_mass = self.belt_mass + self.max_material_mass * (self.material_load_pct / 100.0)

        # Friction torque (referred to motor shaft)
        friction = self.friction_dynamic if self.motor_speed > 10 else self.friction_static
        gravity_component = total_mass * 9.81  # N (horizontal conveyor, friction only)
        belt_force = friction * gravity_component
        pulley_radius = self.pulley_diameter / 2.0
        self.torque_demand = (belt_force * pulley_radius) / self.gear_ratio

        # === Motor dynamics: J * dω/dt = T_motor - T_load ===
        net_torque = motor_torque - self.torque_demand
        # Angular acceleration (rad/s²)
        if self.total_inertia > 0:
            alpha = net_torque / self.total_inertia
        else:
            alpha = 0.0

        # Convert to RPM/s and integrate
        omega_dot = alpha * 60.0 / (2.0 * math.pi)  # RPM/s
        self.motor_speed += omega_dot * dt
        self.motor_speed = max(0.0, self.motor_speed)

        # === Belt speed from motor speed ===
        motor_rad_per_sec = self.motor_speed * 2 * math.pi / 60.0
        pulley_rad_per_sec = motor_rad_per_sec / self.gear_ratio
        self.belt_speed = pulley_rad_per_sec * pulley_radius

        # === Belt slip detection ===
        if self.motor_speed > 10:
            expected_belt = (speed_ref * 2 * math.pi / 60.0 / self.gear_ratio) * pulley_radius
            if expected_belt > 0.1:
                slip_ratio = abs(self.belt_speed - expected_belt) / expected_belt
                self.belt_slip = slip_ratio > 0.05  # >5% slip
            else:
                self.belt_slip = False
        else:
            self.belt_slip = False

        # === Material position (for animation) ===
        if self.belt_speed > 0:
            self.material_position = (self.material_position + self.belt_speed * dt / 200.0) % 1.0

        return self.motor_speed, self.torque_demand

    def get_tags(self, prefix):
        """Return all conveyor tags with prefix."""
        return {
            f'{prefix}_belt_speed': round(self.belt_speed, 2),
            f'{prefix}_material_load': round(self.material_load_pct, 1),
            f'{prefix}_belt_slip': self.belt_slip,
            f'{prefix}_brake_released': self.motor_speed > 1.0,
        }
