"""
DRIVEWISE — Simulation Configuration Defaults
All motor, drive, protection, and simulation constants.
"""

# === Motor Nameplate Defaults (ABB M3BP 250 SMA, 75kW) ===
MOTOR_DEFAULTS = {
    'rated_power': 75.0,        # kW
    'rated_voltage': 415.0,     # V (line-to-line)
    'rated_current': 135.0,     # A
    'rated_speed': 1475.0,      # RPM
    'rated_frequency': 50.0,    # Hz
    'poles': 4,
    'power_factor': 0.86,
    'efficiency': 0.945,
    'rated_torque': 485.0,      # Nm (P = T * omega)
    'stator_resistance': 0.045, # Ohms (per phase)
    'rotor_resistance': 0.035,  # Ohms (per phase, referred)
    'magnetizing_inductance': 0.120,  # H
    'insulation_class': 'F',    # 155°C max
    'max_winding_temp': 155.0,  # °C
    'ambient_temp': 25.0,       # °C
}

# === Drive Defaults (ACS880 style) ===
DRIVE_DEFAULTS = {
    'control_mode': 'DTC',      # 'DTC' or 'SCALAR'
    'ramp_accel': 10.0,         # seconds to rated speed
    'ramp_decel': 10.0,         # seconds from rated to zero
    'ramp_estop': 2.0,          # emergency stop ramp
    'jerk_limit': 500.0,        # RPM/s² (S-curve)
    'current_limit': 150.0,     # % of rated current
    'speed_min': 0.0,           # RPM
    'speed_max': 1500.0,        # RPM
    'dc_bus_nominal': 586.0,    # V (415 * sqrt(2) * sqrt(3) / sqrt(3))
    'dc_bus_overvoltage': 750.0,# V trip threshold
    'dc_bus_undervoltage': 290.0,# V trip threshold
}

# === Conveyor Defaults ===
CONVEYOR_DEFAULTS = {
    'belt_length': 200.0,       # meters
    'belt_mass': 5000.0,        # kg (empty belt)
    'max_material_mass': 8000.0,# kg (full load)
    'belt_width': 1.2,          # meters
    'friction_static': 0.35,
    'friction_dynamic': 0.25,
    'pulley_diameter': 0.6,     # meters
    'gear_ratio': 15.0,         # gearbox ratio
    'belt_speed_max': 3.5,      # m/s at rated motor speed
}

# === Bearing Defaults (6308 deep groove ball bearing) ===
BEARING_DEFAULTS = {
    'n_balls': 8,
    'ball_diameter': 17.462,    # mm
    'pitch_diameter': 58.5,     # mm
    'contact_angle': 0.0,       # degrees (deep groove)
    'initial_health': 100.0,    # %
    'degradation_rate': 0.001,  # % per operating hour
    'iso_good_threshold': 1.8,  # mm/s RMS (ISO 10816-3 Zone A)
    'iso_satisfactory_threshold': 4.5,  # Zone B
    'iso_unsatisfactory_threshold': 11.2, # Zone C
}

# === Protection Thresholds ===
PROTECTION_DEFAULTS = {
    # Overcurrent (IEC 60255 inverse time)
    'overcurrent_pickup': 150.0,  # % of rated current
    'overcurrent_curve': 'B',     # Standard inverse
    'overcurrent_k': 13.5,       # Time multiplier constant
    'overcurrent_alpha': 1.0,    # Exponent

    # Overvoltage
    'overvoltage_threshold': 750.0,  # V DC bus
    'overvoltage_trip_time': 0.1,    # seconds

    # Undervoltage
    'undervoltage_threshold': 290.0,  # V DC bus
    'undervoltage_ride_through': 0.2, # seconds at 80%
    'undervoltage_trip_pct': 70.0,    # % of rated - immediate trip

    # Earth fault
    'earthfault_threshold': 30.0,  # mA residual current
    'earthfault_trip_time': 0.1,   # seconds

    # Thermal overload
    'thermal_warning': 140.0,   # °C (insulation class F - 15°C margin)
    'thermal_trip': 155.0,      # °C (insulation class F limit)
}

# === Thermal Model Constants ===
THERMAL_DEFAULTS = {
    'stator_thermal_mass': 25000.0,    # J/°C (large motor)
    'rotor_thermal_mass': 15000.0,     # J/°C
    'stator_cooling_coeff': 35.0,      # W/°C (convective cooling)
    'rotor_cooling_coeff': 12.0,       # W/°C (through air gap)
    'arrhenius_activation': 1.1,       # eV (polyester-imide insulation)
    'arrhenius_ref_temp': 155.0,       # °C (reference for class F)
    'arrhenius_ref_life': 20000.0,     # hours at reference temp
}

# === Simulation Defaults ===
SIM_DEFAULTS = {
    'dt': 0.01,                 # Base time step (10ms)
    'ws_broadcast_interval': 0.1,  # WebSocket update rate (100ms)
    'historian_interval': 1.0,  # Historian write rate (1s)
    'speed_multiplier': 1,      # 1x to 60x
    'num_sections': 3,
}

# === Multi-drive Coordination ===
COORDINATION_DEFAULTS = {
    'master_section': 'S1',
    'follower_speed_ratio': {
        'S2': 1.0,              # Speed ratio to master
        'S3': 1.0,
    },
    'follower_trim': {
        'S2': 0.5,              # +0.5% to keep belt taut
        'S3': 1.0,              # +1.0%
    },
    'speed_diff_alarm': 2.0,    # % difference triggers alarm
    'speed_diff_trip': 5.0,     # % difference triggers trip
    'cascade_stop_timeout': 0.5, # seconds for cascade E-stop
}
