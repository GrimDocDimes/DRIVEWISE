"""
DRIVEWISE — Simulation Coordinator
Orchestrates 3 drive units, manages time stepping, fault injection, and tag aggregation.
"""
import time
import math
from models.drive import DriveModel
from models.motor import MotorThermalModel
from models.conveyor import ConveyorModel
from models.bearing import BearingModel
from config import (
    MOTOR_DEFAULTS, DRIVE_DEFAULTS, CONVEYOR_DEFAULTS,
    BEARING_DEFAULTS, THERMAL_DEFAULTS, PROTECTION_DEFAULTS,
    SIM_DEFAULTS, COORDINATION_DEFAULTS
)


class DriveUnit:
    """One complete drive unit: drive + motor + conveyor + bearing."""

    def __init__(self, section_id, motor_cfg=None, drive_cfg=None):
        m_cfg = {**MOTOR_DEFAULTS, **(motor_cfg or {})}
        d_cfg = {**DRIVE_DEFAULTS, **(drive_cfg or {}), **m_cfg}

        self.section = section_id
        self.drive = DriveModel(d_cfg)
        self.motor = MotorThermalModel(m_cfg, THERMAL_DEFAULTS)
        self.conveyor = ConveyorModel(CONVEYOR_DEFAULTS, m_cfg)
        self.bearing = BearingModel(BEARING_DEFAULTS)

        # Protection state
        self.prot_overcurrent_trip = False
        self.prot_overvoltage_trip = False
        self.prot_undervoltage_trip = False
        self.prot_earthfault_trip = False
        self.prot_thermal_trip = False
        self.overcurrent_timer = 0.0
        self.supply_voltage_pct = 100.0

    def update(self, dt):
        """Run one simulation step for this drive unit."""
        # Get load torque from conveyor
        motor_speed, load_torque = self.conveyor.motor_speed, self.conveyor.torque_demand

        # Drive produces torque
        torque_out, current_out = self.drive.update(dt, load_torque)

        # Update mechanical (conveyor updates motor speed)
        actual_speed, _ = self.conveyor.update(dt, torque_out, self.drive.speed_ref)

        # Feed actual speed back to drive
        self.drive.speed_actual = actual_speed

        # Update thermal model
        self.motor.update(dt, current_out, actual_speed)

        # Update bearing
        self.bearing.update(dt, actual_speed, self.drive.torque_pct)

        # Update combined health (average of insulation and bearing)
        insulation_h = self.motor.insulation_health
        bearing_h = self.bearing.health

        # Check protections
        self._check_protections(dt, current_out, actual_speed)

    def _check_protections(self, dt, current, speed):
        """Evaluate all protection functions."""
        # Overcurrent — IEC 60255 inverse time
        current_pct = (current / self.drive.rated_current) * 100.0
        pickup = PROTECTION_DEFAULTS['overcurrent_pickup']
        if current_pct > pickup and not self.prot_overcurrent_trip:
            ratio = current_pct / pickup
            # Inverse time: t = k / (I/Ip)^alpha - 1)
            k = PROTECTION_DEFAULTS['overcurrent_k']
            alpha = PROTECTION_DEFAULTS['overcurrent_alpha']
            try:
                trip_time = k / (ratio**alpha - 1)
            except ZeroDivisionError:
                trip_time = 999
            self.overcurrent_timer += dt
            if self.overcurrent_timer >= trip_time:
                self.prot_overcurrent_trip = True
                self.drive.fault('OVERCURRENT')
        else:
            self.overcurrent_timer = max(0, self.overcurrent_timer - dt * 0.5)

        # Overvoltage — DC bus
        if self.drive.dc_bus_voltage > PROTECTION_DEFAULTS['overvoltage_threshold']:
            self.prot_overvoltage_trip = True
            self.drive.fault('OVERVOLTAGE')

        # Undervoltage
        actual_v = self.drive.rated_voltage * (self.supply_voltage_pct / 100.0)
        if actual_v < self.drive.rated_voltage * (PROTECTION_DEFAULTS['undervoltage_trip_pct'] / 100.0):
            self.prot_undervoltage_trip = True
            self.drive.fault('UNDERVOLTAGE')

        # Thermal overload
        if self.motor.winding_temp >= PROTECTION_DEFAULTS['thermal_trip']:
            self.prot_thermal_trip = True
            self.drive.fault('THERMAL_OVERLOAD')

    def get_tags(self):
        """Aggregate all tags for this unit."""
        p = self.section
        tags = {}
        tags.update(self.drive.get_tags(p))
        tags.update(self.motor.get_tags(p))
        tags.update(self.conveyor.get_tags(p))
        tags.update(self.bearing.get_tags(p))

        # Protection tags
        current_pct = self.drive.current_pct
        tags.update({
            f'{p}_prot_overcurrent_value': round(current_pct, 1),
            f'{p}_prot_overcurrent_threshold': PROTECTION_DEFAULTS['overcurrent_pickup'],
            f'{p}_prot_overcurrent_trip': self.prot_overcurrent_trip,
            f'{p}_prot_overvoltage_value': round(self.drive.dc_bus_voltage, 0),
            f'{p}_prot_overvoltage_threshold': PROTECTION_DEFAULTS['overvoltage_threshold'],
            f'{p}_prot_overvoltage_trip': self.prot_overvoltage_trip,
            f'{p}_prot_undervoltage_value': round(self.drive.rated_voltage * self.supply_voltage_pct / 100, 0),
            f'{p}_prot_undervoltage_threshold': PROTECTION_DEFAULTS['undervoltage_trip_pct'] / 100 * self.drive.rated_voltage,
            f'{p}_prot_undervoltage_trip': self.prot_undervoltage_trip,
            f'{p}_prot_earthfault_value': 0,
            f'{p}_prot_earthfault_threshold': PROTECTION_DEFAULTS['earthfault_threshold'],
            f'{p}_prot_earthfault_trip': self.prot_earthfault_trip,
            f'{p}_prot_thermal_value': round(self.motor.winding_temp, 1),
            f'{p}_prot_thermal_threshold': PROTECTION_DEFAULTS['thermal_trip'],
            f'{p}_prot_thermal_trip': self.prot_thermal_trip,
        })

        return tags


class SimulationCoordinator:
    """Manages all 3 drive units and system-level coordination."""

    def __init__(self):
        self.units = {
            'S1': DriveUnit('S1'),
            'S2': DriveUnit('S2'),
            'S3': DriveUnit('S3'),
        }
        self.dt = SIM_DEFAULTS['dt']
        self.speed_multiplier = SIM_DEFAULTS['speed_multiplier']
        self.sim_time = 0.0
        self.running = False
        self.shift_energy = 0.0  # kWh

        # Coordination
        self.master = COORDINATION_DEFAULTS['master_section']
        self.coord = COORDINATION_DEFAULTS

        # Fault schedule
        self.fault_schedule = []
        self._fault_schedule_idx = 0

    def start_all(self):
        """Start all sections in sequence."""
        self.running = True
        for sid in ['S1', 'S2', 'S3']:
            unit = self.units[sid]
            unit.drive.start()
            unit.drive.set_speed_target(unit.drive.rated_speed)

    def stop_all(self):
        """Normal stop all sections."""
        for unit in self.units.values():
            unit.drive.stop()

    def estop_all(self):
        """Emergency stop all sections."""
        for unit in self.units.values():
            unit.drive.emergency_stop()

    def start_section(self, section):
        """Start a single section."""
        self.running = True
        unit = self.units.get(section)
        if unit:
            unit.drive.start()
            unit.drive.set_speed_target(unit.drive.rated_speed)

    def stop_section(self, section):
        """Stop a single section."""
        unit = self.units.get(section)
        if unit:
            unit.drive.stop()

    def estop_section(self, section):
        """E-stop a single section."""
        unit = self.units.get(section)
        if unit:
            unit.drive.emergency_stop()

    def set_parameter(self, section, param, value):
        """Set a drive parameter."""
        unit = self.units.get(section)
        if not unit:
            return
        drive = unit.drive
        if param == 'speed_ref':
            drive.set_speed_target(float(value))
        elif param == 'control_mode':
            drive.control_mode = str(value)
        elif param == 'ramp_accel':
            drive.ramp_accel = float(value)
        elif param == 'ramp_decel':
            drive.ramp_decel = float(value)
        elif param == 'ramp_estop':
            drive.ramp_estop = float(value)
        elif param == 'current_limit':
            drive.current_limit = float(value)

    def configure(self, config):
        """Apply configuration from frontend."""
        if 'simSpeed' in config:
            self.speed_multiplier = max(1, min(60, int(config['simSpeed'])))

        if 'loadProfile' in config:
            profile = config['loadProfile']
            if isinstance(profile, list) and len(profile) > 0:
                for unit in self.units.values():
                    unit.conveyor.set_load_profile(profile)
                print(f"[CFG] Load profile updated: {profile}")

        if 'faultSchedule' in config:
            self.fault_schedule = config['faultSchedule']
            self._fault_schedule_idx = 0
            print(f"[CFG] Fault schedule updated: {len(self.fault_schedule)} faults")

        if 'motor' in config:
            mc = config['motor']
            print(f"[CFG] Motor config updated: {mc}")


    def step(self):
        """Execute one simulation step for all units."""
        effective_dt = self.dt * self.speed_multiplier

        # Master-follower coordination
        master_unit = self.units[self.master]
        master_speed = master_unit.drive.speed_actual

        for sid in ['S2', 'S3']:
            if self.units[sid].drive.running:
                ratio = self.coord['follower_speed_ratio'][sid]
                trim = self.coord['follower_trim'][sid]
                target = master_speed * ratio * (1 + trim / 100.0)
                if master_speed > 10:
                    self.units[sid].drive.set_speed_target(target)

        # Fault cascade: if master faults, stop all followers
        if master_unit.drive.faulted:
            for sid in ['S2', 'S3']:
                if self.units[sid].drive.running:
                    self.units[sid].drive.emergency_stop()

        # Check scheduled faults
        self._check_fault_schedule()

        # Update all units
        for unit in self.units.values():
            unit.update(effective_dt)

        # System totals
        total_power = sum(u.drive.power for u in self.units.values())
        self.shift_energy += total_power * effective_dt / 3600.0

        self.sim_time += effective_dt

    def _check_fault_schedule(self):
        """Process scheduled fault injections."""
        while self._fault_schedule_idx < len(self.fault_schedule):
            fault = self.fault_schedule[self._fault_schedule_idx]
            if self.sim_time >= fault.get('time', 0):
                section = fault.get('section', 'S1')
                fault_type = fault.get('type', 'Overcurrent')
                unit = self.units.get(section)
                if unit:
                    unit.drive.fault(fault_type.upper().replace(' ', '_'))
                self._fault_schedule_idx += 1
            else:
                break

    def get_all_tags(self):
        """Aggregate tags from all units + system tags."""
        tags = {
            'sim_running': self.running,
            'sim_speed_multiplier': self.speed_multiplier,
            'sim_time': round(self.sim_time, 1),
            'total_power_kw': round(sum(u.drive.power for u in self.units.values()), 2),
            'total_energy_kwh': round(self.shift_energy, 2),
            'system_power_factor': round(
                sum(u.drive.power_factor for u in self.units.values()) / 3, 2
            ),
        }
        for unit in self.units.values():
            tags.update(unit.get_tags())
        return tags
