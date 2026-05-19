"""
DRIVEWISE — Motor Thermal Model (Dual-Node + Arrhenius)
Stator winding + rotor thermal nodes with insulation life tracking.
"""
import math


class MotorThermalModel:
    """Dual-node thermal equivalent circuit motor model."""

    def __init__(self, motor_cfg, thermal_cfg):
        self.motor = motor_cfg
        self.thermal = thermal_cfg

        # Temperatures
        self.winding_temp = motor_cfg.get('ambient_temp', 25.0)
        self.rotor_temp = motor_cfg.get('ambient_temp', 25.0)
        self.ambient_temp = motor_cfg.get('ambient_temp', 25.0)

        # Thermal parameters
        self.stator_thermal_mass = thermal_cfg.get('stator_thermal_mass', 25000.0)
        self.rotor_thermal_mass = thermal_cfg.get('rotor_thermal_mass', 15000.0)
        self.stator_cooling = thermal_cfg.get('stator_cooling_coeff', 35.0)
        self.rotor_cooling = thermal_cfg.get('rotor_cooling_coeff', 12.0)
        self.stator_resistance = motor_cfg.get('stator_resistance', 0.045)

        # Insulation life tracking
        self.insulation_health = 100.0  # %
        self.thermal_stress_accumulated = 0.0  # equivalent hours at reference temp
        self.arrhenius_activation = thermal_cfg.get('arrhenius_activation', 1.1)
        self.arrhenius_ref_temp = thermal_cfg.get('arrhenius_ref_temp', 155.0)
        self.arrhenius_ref_life = thermal_cfg.get('arrhenius_ref_life', 20000.0)

        # Max temperature
        self.max_winding_temp = motor_cfg.get('max_winding_temp', 155.0)

    def update(self, dt, current, speed_rpm):
        """
        Update thermal state for one time step.

        Args:
            dt: time step in seconds
            current: motor current in Amps
            speed_rpm: motor speed in RPM (affects cooling)
        """
        # === I²R losses (stator winding) ===
        i2r_loss = 3 * current**2 * self.stator_resistance  # 3-phase

        # === Core losses (rotor) — proportional to frequency² ===
        freq_ratio = speed_rpm / max(self.motor.get('rated_speed', 1475.0), 1.0)
        core_loss = 500.0 * freq_ratio**2  # Simplified: ~500W at rated

        # === Cooling effectiveness — reduces when motor is slow ===
        speed_ratio = speed_rpm / max(self.motor.get('rated_speed', 1475.0), 1.0)
        # Fan cooling is proportional to speed (TEFC motor)
        cooling_factor = 0.2 + 0.8 * min(speed_ratio, 1.0)

        # === Stator temperature dynamics ===
        stator_heat_in = i2r_loss
        stator_heat_out = self.stator_cooling * cooling_factor * (self.winding_temp - self.ambient_temp)
        d_stator = (stator_heat_in - stator_heat_out) / self.stator_thermal_mass
        self.winding_temp += d_stator * dt

        # === Rotor temperature dynamics ===
        rotor_heat_in = core_loss
        rotor_heat_out = self.rotor_cooling * cooling_factor * (self.rotor_temp - self.ambient_temp)
        # Heat transfer from rotor to stator through air gap
        gap_transfer = 5.0 * (self.rotor_temp - self.winding_temp)
        d_rotor = (rotor_heat_in - rotor_heat_out - gap_transfer) / self.rotor_thermal_mass
        self.rotor_temp += d_rotor * dt

        # Clamp to reasonable range
        self.winding_temp = max(self.ambient_temp, min(self.winding_temp, 250.0))
        self.rotor_temp = max(self.ambient_temp, min(self.rotor_temp, 250.0))

        # === Arrhenius insulation degradation ===
        if self.winding_temp > self.ambient_temp + 10:
            self._update_insulation_life(dt)

    def _update_insulation_life(self, dt):
        """Calculate insulation life consumption using Arrhenius equation."""
        # Boltzmann constant in eV/K
        kb = 8.617e-5

        # Reference and actual temperatures in Kelvin
        t_ref_k = self.arrhenius_ref_temp + 273.15
        t_actual_k = self.winding_temp + 273.15

        # Acceleration factor: AF = exp(Ea/kb * (1/T_ref - 1/T_actual))
        try:
            exponent = (self.arrhenius_activation / kb) * (1.0/t_ref_k - 1.0/t_actual_k)
            acceleration_factor = math.exp(min(exponent, 50))  # cap to prevent overflow
        except (OverflowError, ValueError):
            acceleration_factor = 1.0

        # Equivalent hours at reference temperature consumed this step
        dt_hours = dt / 3600.0
        equivalent_hours = dt_hours * acceleration_factor
        self.thermal_stress_accumulated += equivalent_hours

        # Remaining life percentage
        life_consumed_pct = (self.thermal_stress_accumulated / self.arrhenius_ref_life) * 100.0
        self.insulation_health = max(0.0, 100.0 - life_consumed_pct)

    @property
    def thermal_load_pct(self):
        """Thermal load as percentage of trip threshold."""
        return ((self.winding_temp - self.ambient_temp) /
                (self.max_winding_temp - self.ambient_temp)) * 100.0

    def get_tags(self, prefix):
        """Return all thermal tags with prefix."""
        return {
            f'{prefix}_winding_temp': round(self.winding_temp, 1),
            f'{prefix}_rotor_temp': round(self.rotor_temp, 1),
            f'{prefix}_thermal_load_pct': round(self.thermal_load_pct, 1),
            f'{prefix}_insulation_health': round(self.insulation_health, 2),
        }
