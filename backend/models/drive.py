"""
DRIVEWISE — Drive Model (ACS880 DTC + Scalar V/f)
Simulates ABB's Direct Torque Control and Scalar control modes.
"""
import math

class DriveModel:
    """ACS880 variable frequency drive simulation."""

    def __init__(self, config):
        self.cfg = config
        self.control_mode = config.get('control_mode', 'DTC')

        # State
        self.speed_ref = 0.0           # RPM setpoint (after ramp)
        self.speed_target = 0.0        # RPM operator target
        self.speed_actual = 0.0        # RPM actual motor speed
        self.torque = 0.0              # Nm
        self.torque_pct = 0.0          # % of rated
        self.current = 0.0             # Amps
        self.current_pct = 0.0         # % of rated
        self.voltage = 0.0             # Volts
        self.frequency = 0.0           # Hz output
        self.dc_bus_voltage = config.get('dc_bus_nominal', 586.0)
        self.power = 0.0               # kW
        self.power_factor = 0.0

        # Ramp state
        self.ramp_accel = config.get('ramp_accel', 10.0)
        self.ramp_decel = config.get('ramp_decel', 10.0)
        self.ramp_estop = config.get('ramp_estop', 2.0)
        self.jerk_limit = config.get('jerk_limit', 500.0)
        self.current_limit = config.get('current_limit', 150.0)
        self._ramp_rate = 0.0          # Current ramp rate (for S-curve)

        # Drive state
        self.running = False
        self.starting = False
        self.estop_active = False
        self.faulted = False
        self.fault_code = None

        # Motor rated values
        self.rated_speed = config.get('rated_speed', 1475.0)
        self.rated_current = config.get('rated_current', 135.0)
        self.rated_torque = config.get('rated_torque', 485.0)
        self.rated_voltage = config.get('rated_voltage', 415.0)
        self.rated_frequency = config.get('rated_frequency', 50.0)

    def start(self):
        """Start the drive."""
        if self.faulted:
            return False
        self.running = True
        self.starting = True
        self.estop_active = False
        return True

    def stop(self):
        """Normal stop — ramp to zero."""
        self.speed_target = 0.0
        self.estop_active = False

    def emergency_stop(self):
        """Emergency stop — immediate torque removal."""
        self.estop_active = True
        self.speed_target = 0.0

    def fault(self, code):
        """Set drive into fault state."""
        self.faulted = True
        self.fault_code = code
        self.running = False
        self.starting = False
        self.speed_target = 0.0

    def reset_fault(self):
        """Reset fault condition."""
        self.faulted = False
        self.fault_code = None

    def set_speed_target(self, rpm):
        """Set operator speed target."""
        self.speed_target = max(0, min(rpm, self.cfg.get('speed_max', 1500.0)))

    def update(self, dt, load_torque):
        """
        Update drive state for one time step.
        Returns: (torque_output, current_output)
        """
        if self.faulted:
            self.speed_ref = 0.0
            self.torque = 0.0
            self.torque_pct = 0.0
            self.current = 0.0
            self.current_pct = 0.0
            self.frequency = 0.0
            self.voltage = 0.0
            self.power = 0.0
            self.power_factor = 0.0
            return 0.0, 0.0

        if self.estop_active:
            # E-stop: instant torque cut
            self.speed_ref = 0.0
            self.torque = 0.0
            self.torque_pct = 0.0
            self.current = self.rated_current * 0.05  # residual
            self.current_pct = 0.0
            self.power = 0.0
            self.running = False
            return 0.0, self.current

        # === S-curve ramp generator ===
        self.speed_ref = self._s_curve_ramp(dt)

        # === Control mode dependent output ===
        if self.control_mode == 'DTC':
            torque_out, current_out = self._dtc_control(dt, load_torque)
        else:
            torque_out, current_out = self._scalar_control(dt, load_torque)

        # Apply current limit
        max_current = self.rated_current * (self.current_limit / 100.0)
        if current_out > max_current:
            current_out = max_current
            torque_out = load_torque  # Can't accelerate further

        # Update outputs
        self.torque = torque_out
        self.torque_pct = (torque_out / self.rated_torque) * 100.0 if self.rated_torque > 0 else 0
        self.current = current_out
        self.current_pct = (current_out / self.rated_current) * 100.0 if self.rated_current > 0 else 0
        self.frequency = (self.speed_ref / self.rated_speed) * self.rated_frequency
        self.voltage = (self.frequency / self.rated_frequency) * self.rated_voltage
        self.power = (torque_out * self.speed_actual * 2 * math.pi / 60) / 1000.0  # kW
        self.power_factor = self.cfg.get('power_factor', 0.86) if self.speed_actual > 10 else 0.0

        # Check if starting is complete
        if self.starting and abs(self.speed_actual - self.speed_target) < 5:
            self.starting = False

        # Check if stopped
        if self.speed_actual < 1.0 and self.speed_target == 0.0:
            self.running = False
            self.starting = False

        return torque_out, current_out

    def _s_curve_ramp(self, dt):
        """S-curve speed ramp with jerk limiting."""
        error = self.speed_target - self.speed_ref
        if abs(error) < 0.1:
            return self.speed_target

        # Determine ramp time
        if error > 0:
            ramp_time = self.ramp_accel
        else:
            ramp_time = self.ramp_decel

        # Target ramp rate
        target_rate = self.rated_speed / max(ramp_time, 0.1)
        if error < 0:
            target_rate = -target_rate

        # Apply jerk limiting (S-curve)
        rate_error = target_rate - self._ramp_rate
        max_jerk = self.jerk_limit * dt
        if abs(rate_error) > max_jerk:
            self._ramp_rate += max_jerk if rate_error > 0 else -max_jerk
        else:
            self._ramp_rate = target_rate

        # Apply ramp
        new_ref = self.speed_ref + self._ramp_rate * dt
        if error > 0:
            new_ref = min(new_ref, self.speed_target)
        else:
            new_ref = max(new_ref, self.speed_target)

        return max(0, new_ref)

    def _dtc_control(self, dt, load_torque):
        """
        Direct Torque Control simulation.
        High-bandwidth torque loop — speed accuracy ±0.1%.
        """
        speed_error = self.speed_ref - self.speed_actual
        # PI speed controller (tight — DTC response)
        kp = 5.0
        ki = 0.5
        torque_demand = load_torque + kp * speed_error + ki * speed_error * dt

        # Torque limit
        max_torque = self.rated_torque * (self.current_limit / 100.0)
        torque_demand = max(-max_torque, min(torque_demand, max_torque))

        # Current from torque (simplified: I ≈ T / kT)
        kt = self.rated_torque / self.rated_current  # torque constant
        current = abs(torque_demand) / kt if kt > 0 else 0
        # Add magnetizing current
        current = math.sqrt(current**2 + (self.rated_current * 0.3)**2)

        return torque_demand, current

    def _scalar_control(self, dt, load_torque):
        """
        Scalar V/f control simulation.
        Open-loop — speed accuracy ±3-5%.
        """
        # V/f gives voltage proportional to frequency
        # Slip-dependent torque — less accurate
        slip = (self.speed_ref - self.speed_actual) / max(self.speed_ref, 1.0)
        slip = max(-0.1, min(slip, 0.1))

        # Approximate torque from slip (linear region)
        torque_demand = self.rated_torque * (slip / 0.03)  # 3% rated slip
        max_torque = self.rated_torque * (self.current_limit / 100.0)
        torque_demand = max(-max_torque, min(torque_demand, max_torque))

        # Current (less efficient than DTC)
        kt = self.rated_torque / self.rated_current
        current = abs(torque_demand) / kt if kt > 0 else 0
        current = math.sqrt(current**2 + (self.rated_current * 0.35)**2)
        current *= 1.05  # Scalar is less efficient

        return torque_demand, current

    def get_status(self):
        """Return drive status string."""
        if self.faulted:
            return 'FAULT'
        if self.starting:
            return 'STARTING'
        if self.running:
            return 'RUNNING'
        return 'STOPPED'

    def get_tags(self, prefix):
        """Return all drive tags with prefix."""
        return {
            f'{prefix}_status': self.get_status(),
            f'{prefix}_control_mode': self.control_mode,
            f'{prefix}_speed_ref': round(self.speed_ref, 1),
            f'{prefix}_speed_actual': round(self.speed_actual, 1),
            f'{prefix}_speed_error': round(self.speed_ref - self.speed_actual, 2),
            f'{prefix}_torque': round(self.torque, 1),
            f'{prefix}_torque_pct': round(self.torque_pct, 1),
            f'{prefix}_current': round(self.current, 1),
            f'{prefix}_current_pct': round(self.current_pct, 1),
            f'{prefix}_voltage': round(self.voltage, 1),
            f'{prefix}_frequency': round(self.frequency, 2),
            f'{prefix}_dc_bus_voltage': round(self.dc_bus_voltage, 0),
            f'{prefix}_power': round(self.power, 2),
            f'{prefix}_power_factor': round(self.power_factor, 2),
            f'{prefix}_ramp_accel': self.ramp_accel,
            f'{prefix}_ramp_decel': self.ramp_decel,
            f'{prefix}_ramp_estop': self.ramp_estop,
        }
