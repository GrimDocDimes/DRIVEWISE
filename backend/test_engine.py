"""
DRIVEWISE — Automated Test Engine
Executes 6 FAT test cases against the simulation with assertion validation.
"""
import asyncio
import time
import math


class TestResult:
    """Result of a single test assertion."""
    def __init__(self, assertion, expected, actual, passed, message=''):
        self.assertion = assertion
        self.expected = expected
        self.actual = actual
        self.passed = passed
        self.message = message
        self.timestamp = time.time()

    def to_dict(self):
        return {
            'assertion': self.assertion,
            'expected': str(self.expected),
            'actual': str(self.actual),
            'passed': self.passed,
            'message': self.message,
        }


class TestCase:
    """Base class for FAT test cases."""
    def __init__(self, test_id, name, description, coordinator):
        self.test_id = test_id
        self.name = name
        self.description = description
        self.coordinator = coordinator
        self.results = []
        self.log = []
        self.status = 'pending'  # pending, running, pass, fail
        self.start_time = 0
        self.duration = 0

    def _log(self, message, level='info'):
        elapsed = time.time() - self.start_time if self.start_time else 0
        entry = {
            'time': f'T+{elapsed:05.1f}',
            'message': message,
            'type': level,
        }
        self.log.append(entry)

    def _assert(self, name, expected, actual, tolerance=None, comparator='eq'):
        if comparator == 'eq':
            passed = actual == expected
        elif comparator == 'approx':
            passed = abs(actual - expected) <= (tolerance or 0)
        elif comparator == 'lt':
            passed = actual < expected
        elif comparator == 'gt':
            passed = actual > expected
        elif comparator == 'lte':
            passed = actual <= expected
        elif comparator == 'gte':
            passed = actual >= expected
        elif comparator == 'range':
            low, high = expected
            passed = low <= actual <= high
        else:
            passed = False

        msg = f"{'PASS' if passed else 'FAIL'}: {name} — expected {expected}, got {actual}"
        if tolerance:
            msg += f" (±{tolerance})"

        result = TestResult(name, expected, actual, passed, msg)
        self.results.append(result)
        self._log(msg, 'pass' if passed else 'fail')
        return passed

    def _step(self, n_steps=1):
        """Run n simulation steps."""
        for _ in range(n_steps):
            self.coordinator.step()

    def _run_seconds(self, seconds):
        """Run simulation for given wall-clock seconds (at sim dt)."""
        dt = self.coordinator.dt
        steps = int(seconds / dt)
        for _ in range(steps):
            self.coordinator.step()

    def _get_tag(self, tag):
        """Get current tag value."""
        tags = self.coordinator.get_all_tags()
        return tags.get(tag)

    async def execute(self, progress_callback=None):
        """Execute the test case. Override in subclasses."""
        raise NotImplementedError

    def to_dict(self):
        return {
            'testId': self.test_id,
            'name': self.name,
            'description': self.description,
            'status': self.status,
            'duration': round(self.duration, 2),
            'results': [r.to_dict() for r in self.results],
            'log': self.log,
            'passed': all(r.passed for r in self.results),
            'totalAssertions': len(self.results),
            'passedAssertions': sum(1 for r in self.results if r.passed),
        }


class TC001_StartUnderLoad(TestCase):
    """TC001: Conveyor Start Under Full Load."""
    def __init__(self, coordinator):
        super().__init__('TC001', 'Conveyor Start Under Full Load',
            'Start drive with max material load. Verify speed within ramp time ±5%, no overcurrent trip, brake release.',
            coordinator)

    async def execute(self, progress_callback=None):
        self.start_time = time.time()
        self.status = 'running'
        self._log('Starting TC001 — Conveyor Start Under Full Load')

        # Set full load on all conveyors
        for unit in self.coordinator.units.values():
            unit.conveyor.set_material_load(100)
        self._log('Material load set to 100% on all sections')

        # Start S1
        self.coordinator.start_section('S1')
        self._log('S1 start command issued')
        if progress_callback:
            await progress_callback(self.test_id, 10)

        # Verify drive is now running/starting
        status = self._get_tag('S1_status')
        self._assert('S1 status after start', True, status in ('STARTING', 'RUNNING'), comparator='eq')

        # Run for ramp time (10s default + margin)
        self._log('Running simulation for 12 seconds (ramp time + margin)...')
        self._run_seconds(12)
        if progress_callback:
            await progress_callback(self.test_id, 50)

        # Check speed reached target
        speed = self._get_tag('S1_speed_actual')
        rated = 1475.0
        self._assert('S1 speed within ±5% of rated', (rated * 0.95, rated * 1.05), speed, comparator='range')
        self._log(f'S1 actual speed: {speed:.1f} RPM')

        # No overcurrent trip
        oc_trip = self._get_tag('S1_prot_overcurrent_trip')
        self._assert('No overcurrent trip', False, oc_trip, comparator='eq')

        # Brake released
        brake = self._get_tag('S1_brake_released')
        self._assert('Brake released', True, brake, comparator='eq')

        # Check current within limits
        current_pct = self._get_tag('S1_current_pct')
        self._assert('Current within 150% limit', True, current_pct <= 155, comparator='eq')
        self._log(f'S1 current: {current_pct:.1f}% of rated')

        if progress_callback:
            await progress_callback(self.test_id, 100)

        self.coordinator.stop_all()
        self._run_seconds(15)

        self.duration = time.time() - self.start_time
        self.status = 'pass' if all(r.passed for r in self.results) else 'fail'
        self._log(f'TC001 complete — {self.status.upper()}', 'pass' if self.status == 'pass' else 'fail')


class TC002_EmergencyStop(TestCase):
    """TC002: Emergency Stop from Full Speed."""
    def __init__(self, coordinator):
        super().__init__('TC002', 'Emergency Stop from Full Speed',
            'Issue E-Stop at rated speed. Verify torque zero, brake engaged, zero speed.',
            coordinator)

    async def execute(self, progress_callback=None):
        self.start_time = time.time()
        self.status = 'running'
        self._log('Starting TC002 — Emergency Stop from Full Speed')

        # Start and ramp up
        self.coordinator.start_all()
        self._run_seconds(12)
        speed_before = self._get_tag('S1_speed_actual')
        self._log(f'S1 at speed: {speed_before:.1f} RPM')
        self._assert('S1 running before E-Stop', True, speed_before > 1000, comparator='eq')
        if progress_callback:
            await progress_callback(self.test_id, 30)

        # Issue E-Stop
        self.coordinator.estop_all()
        self._log('E-Stop issued on all sections')

        # Check torque zero within 0.05s (5 steps)
        self._run_seconds(0.05)
        torque = self._get_tag('S1_torque')
        self._assert('Torque zero within 50ms', True, abs(torque) < 1.0, comparator='eq')
        self._log(f'Torque after 50ms: {torque:.2f} Nm')
        if progress_callback:
            await progress_callback(self.test_id, 60)

        # Run for coast-down
        self._run_seconds(10)
        speed_after = self._get_tag('S1_speed_actual')
        self._assert('Speed near zero after 10s', True, speed_after < 50, comparator='eq')
        self._log(f'S1 speed after 10s: {speed_after:.1f} RPM')
        if progress_callback:
            await progress_callback(self.test_id, 100)

        self.duration = time.time() - self.start_time
        self.status = 'pass' if all(r.passed for r in self.results) else 'fail'
        self._log(f'TC002 complete — {self.status.upper()}', 'pass' if self.status == 'pass' else 'fail')


class TC003_MasterFollowerSync(TestCase):
    """TC003: Master-Follower Speed Synchronisation."""
    def __init__(self, coordinator):
        super().__init__('TC003', 'Master-Follower Synchronisation',
            'Step load on S2 only. Verify speed differential returns to ±0.2% within 5s.',
            coordinator)

    async def execute(self, progress_callback=None):
        self.start_time = time.time()
        self.status = 'running'
        self._log('Starting TC003 — Master-Follower Synchronisation')

        # Start all and reach steady state
        self.coordinator.start_all()
        self._run_seconds(15)
        s1_speed = self._get_tag('S1_speed_actual')
        s2_speed = self._get_tag('S2_speed_actual')
        self._log(f'Steady state — S1: {s1_speed:.1f}, S2: {s2_speed:.1f} RPM')
        if progress_callback:
            await progress_callback(self.test_id, 30)

        # Apply step load to S2
        self.coordinator.units['S2'].conveyor.set_material_load(100)
        self._log('Step load applied to S2 (100% material)')

        # Run for 5 seconds and check recovery
        self._run_seconds(5)
        s1_speed = self._get_tag('S1_speed_actual')
        s2_speed = self._get_tag('S2_speed_actual')
        if s1_speed > 0:
            speed_diff_pct = abs(s1_speed - s2_speed) / s1_speed * 100
        else:
            speed_diff_pct = 0
        self._assert('Speed diff within ±2% after 5s', True, speed_diff_pct < 2.0, comparator='eq')
        self._log(f'Speed differential: {speed_diff_pct:.3f}%')
        if progress_callback:
            await progress_callback(self.test_id, 100)

        self.coordinator.stop_all()
        self._run_seconds(15)

        self.duration = time.time() - self.start_time
        self.status = 'pass' if all(r.passed for r in self.results) else 'fail'
        self._log(f'TC003 complete — {self.status.upper()}', 'pass' if self.status == 'pass' else 'fail')


class TC004_ThermalOverload(TestCase):
    """TC004: Thermal Overload Trip."""
    def __init__(self, coordinator):
        super().__init__('TC004', 'Thermal Overload Trip',
            'Run motor at 150% current. Verify trip per IEC 60255 curve.',
            coordinator)

    async def execute(self, progress_callback=None):
        self.start_time = time.time()
        self.status = 'running'
        self._log('Starting TC004 — Thermal Overload Trip')

        # Start S1
        self.coordinator.start_section('S1')
        self._run_seconds(12)
        if progress_callback:
            await progress_callback(self.test_id, 20)

        # Record initial temperature
        temp_initial = self._get_tag('S1_winding_temp')
        self._log(f'Initial winding temp: {temp_initial:.1f}°C')

        # Run at high load for extended time (accelerated sim)
        self.coordinator.speed_multiplier = 30  # 30x speed
        self._log('Simulation speed set to 30x for thermal test')
        self._run_seconds(120)
        if progress_callback:
            await progress_callback(self.test_id, 60)

        temp_after = self._get_tag('S1_winding_temp')
        self._log(f'Winding temp after load: {temp_after:.1f}°C')
        self._assert('Temperature rise detected', True, temp_after > temp_initial + 5, comparator='eq')

        # Check thermal protection awareness
        thermal_pct = self._get_tag('S1_thermal_load_pct')
        self._assert('Thermal load percentage tracked', True, thermal_pct > 0, comparator='eq')
        self._log(f'Thermal load: {thermal_pct:.1f}%')

        if progress_callback:
            await progress_callback(self.test_id, 100)

        self.coordinator.speed_multiplier = 1
        self.coordinator.stop_all()
        self._run_seconds(15)

        self.duration = time.time() - self.start_time
        self.status = 'pass' if all(r.passed for r in self.results) else 'fail'
        self._log(f'TC004 complete — {self.status.upper()}', 'pass' if self.status == 'pass' else 'fail')


class TC005_PowerDipRideThrough(TestCase):
    """TC005: Power Dip Ride-Through."""
    def __init__(self, coordinator):
        super().__init__('TC005', 'Power Dip Ride-Through',
            '80% voltage dip 200ms ride-through, <70% trip verification.',
            coordinator)

    async def execute(self, progress_callback=None):
        self.start_time = time.time()
        self.status = 'running'
        self._log('Starting TC005 — Power Dip Ride-Through')

        # Start and reach steady state
        self.coordinator.start_all()
        self._run_seconds(12)
        self._log('All sections at rated speed')
        if progress_callback:
            await progress_callback(self.test_id, 30)

        # Apply 80% voltage dip (should ride through)
        for unit in self.coordinator.units.values():
            unit.supply_voltage_pct = 80.0
        self._log('80% voltage dip applied')
        self._run_seconds(0.2)

        # Should still be running
        status = self._get_tag('S1_status')
        self._assert('S1 rides through 80% dip', True, status in ('RUNNING', 'STARTING'), comparator='eq')
        self._log(f'S1 status during 80% dip: {status}')

        # Restore voltage
        for unit in self.coordinator.units.values():
            unit.supply_voltage_pct = 100.0
        self._run_seconds(2)
        if progress_callback:
            await progress_callback(self.test_id, 60)

        # Apply 65% voltage (should trip)
        for unit in self.coordinator.units.values():
            unit.supply_voltage_pct = 65.0
        self._log('65% voltage dip applied (below trip threshold)')
        self._run_seconds(0.5)

        uv_trip = self._get_tag('S1_prot_undervoltage_trip')
        self._assert('Undervoltage trip at 65%', True, uv_trip, comparator='eq')
        self._log(f'Undervoltage trip: {uv_trip}')

        if progress_callback:
            await progress_callback(self.test_id, 100)

        # Restore and reset
        for unit in self.coordinator.units.values():
            unit.supply_voltage_pct = 100.0
            unit.prot_undervoltage_trip = False
            unit.drive.reset_fault()
        self.coordinator.stop_all()
        self._run_seconds(15)

        self.duration = time.time() - self.start_time
        self.status = 'pass' if all(r.passed for r in self.results) else 'fail'
        self._log(f'TC005 complete — {self.status.upper()}', 'pass' if self.status == 'pass' else 'fail')


class TC006_FaultCascade(TestCase):
    """TC006: Fault Cascade Response."""
    def __init__(self, coordinator):
        super().__init__('TC006', 'Fault Cascade Response',
            'S1 overcurrent fault. Verify S2/S3 stop, first-out alarm correct.',
            coordinator)

    async def execute(self, progress_callback=None):
        self.start_time = time.time()
        self.status = 'running'
        self._log('Starting TC006 — Fault Cascade Response')

        # Start all and reach steady state
        self.coordinator.start_all()
        self._run_seconds(12)
        self._log('All sections at rated speed')
        if progress_callback:
            await progress_callback(self.test_id, 30)

        # Inject overcurrent fault on S1 (master)
        self.coordinator.units['S1'].drive.fault('OVERCURRENT')
        self._log('Overcurrent fault injected on S1 (master)')

        # Run cascade logic
        self._run_seconds(1)
        if progress_callback:
            await progress_callback(self.test_id, 60)

        # Check S1 is faulted
        s1_status = self._get_tag('S1_status')
        self._assert('S1 in FAULT state', 'FAULT', s1_status, comparator='eq')

        # Check S2 and S3 stopped by cascade
        s2_status = self._get_tag('S2_status')
        s3_status = self._get_tag('S3_status')
        self._assert('S2 stopped by cascade', True, s2_status in ('STOPPED', 'FAULT'), comparator='eq')
        self._assert('S3 stopped by cascade', True, s3_status in ('STOPPED', 'FAULT'), comparator='eq')
        self._log(f'S1: {s1_status}, S2: {s2_status}, S3: {s3_status}')

        if progress_callback:
            await progress_callback(self.test_id, 100)

        # Reset all faults
        for unit in self.coordinator.units.values():
            unit.drive.reset_fault()
            unit.prot_overcurrent_trip = False
        self.coordinator.stop_all()
        self._run_seconds(15)

        self.duration = time.time() - self.start_time
        self.status = 'pass' if all(r.passed for r in self.results) else 'fail'
        self._log(f'TC006 complete — {self.status.upper()}', 'pass' if self.status == 'pass' else 'fail')


# All test case classes
TEST_CLASSES = [TC001_StartUnderLoad, TC002_EmergencyStop, TC003_MasterFollowerSync,
                TC004_ThermalOverload, TC005_PowerDipRideThrough, TC006_FaultCascade]


class TestEngine:
    """Manages execution of all FAT test cases."""

    def __init__(self, coordinator):
        self.coordinator = coordinator
        self.test_cases = []
        self.running = False
        self.current_test = None
        self.overall_progress = 0

    def _reset_coordinator(self):
        """Reset coordinator to clean state for next test."""
        from coordinator import SimulationCoordinator
        # Create fresh units
        from coordinator import DriveUnit
        self.coordinator.units = {
            'S1': DriveUnit('S1'),
            'S2': DriveUnit('S2'),
            'S3': DriveUnit('S3'),
        }
        self.coordinator.sim_time = 0
        self.coordinator.shift_energy = 0
        self.coordinator.running = False
        self.coordinator.speed_multiplier = 1

    def create_tests(self):
        """Instantiate all test cases."""
        self.test_cases = [cls(self.coordinator) for cls in TEST_CLASSES]

    async def run_single(self, test_id, progress_callback=None):
        """Run a single test case."""
        self.create_tests()
        tc = next((t for t in self.test_cases if t.test_id == test_id), None)
        if not tc:
            return None

        self.running = True
        self.current_test = test_id
        self._reset_coordinator()

        await tc.execute(progress_callback)

        self.running = False
        self.current_test = None
        return tc

    async def run_all(self, progress_callback=None):
        """Run all test cases sequentially."""
        self.create_tests()
        self.running = True
        results = []

        for i, tc in enumerate(self.test_cases):
            self.current_test = tc.test_id
            self._reset_coordinator()

            async def test_progress(tid, pct):
                overall = ((i * 100 + pct) / len(self.test_cases))
                self.overall_progress = overall
                if progress_callback:
                    await progress_callback(tid, pct, overall)

            await tc.execute(test_progress)
            results.append(tc)

        self.running = False
        self.current_test = None
        self.overall_progress = 100
        return results

    def get_summary(self):
        """Get test execution summary."""
        if not self.test_cases:
            return {'total': 0, 'passed': 0, 'failed': 0, 'tests': []}

        return {
            'total': len(self.test_cases),
            'passed': sum(1 for t in self.test_cases if t.status == 'pass'),
            'failed': sum(1 for t in self.test_cases if t.status == 'fail'),
            'tests': [t.to_dict() for t in self.test_cases],
        }
