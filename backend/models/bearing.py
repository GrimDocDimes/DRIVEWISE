"""
DRIVEWISE — Bearing Vibration & Wear Model
Generates vibration spectrum with defect frequency growth over time.
"""
import math
import numpy as np


class BearingModel:
    """Rolling element bearing health and vibration simulation."""

    def __init__(self, config):
        self.cfg = config

        # Bearing geometry
        self.n_balls = config.get('n_balls', 8)
        self.ball_dia = config.get('ball_diameter', 17.462)    # mm
        self.pitch_dia = config.get('pitch_diameter', 58.5)    # mm
        self.contact_angle = math.radians(config.get('contact_angle', 0.0))

        # Health state
        self.health = config.get('initial_health', 100.0)
        self.degradation_rate = config.get('degradation_rate', 0.001)  # %/hour
        self.operating_hours = 0.0

        # ISO 10816 thresholds (mm/s RMS)
        self.iso_good = config.get('iso_good_threshold', 1.8)
        self.iso_satisfactory = config.get('iso_satisfactory_threshold', 4.5)
        self.iso_unsatisfactory = config.get('iso_unsatisfactory_threshold', 11.2)

        # Vibration spectrum (32 bins, 0-320 Hz)
        self.spectrum = np.zeros(32)
        self.dominant_defect = 'None'

        # Defect severity (0 = pristine, 1 = failed)
        self.defect_severity = 0.0

    def _calc_defect_frequencies(self, shaft_freq):
        """Calculate characteristic defect frequencies from bearing geometry."""
        d = self.ball_dia
        D = self.pitch_dia
        n = self.n_balls
        phi = self.contact_angle

        # Ball Pass Frequency Outer Race
        bpfo = (n / 2.0) * shaft_freq * (1 - (d / D) * math.cos(phi))
        # Ball Pass Frequency Inner Race
        bpfi = (n / 2.0) * shaft_freq * (1 + (d / D) * math.cos(phi))
        # Ball Spin Frequency
        bsf = (D / (2 * d)) * shaft_freq * (1 - ((d / D) * math.cos(phi))**2)
        # Fundamental Train Frequency
        ftf = (shaft_freq / 2.0) * (1 - (d / D) * math.cos(phi))

        return {'BPFO': bpfo, 'BPFI': bpfi, 'BSF': bsf, 'FTF': ftf}

    def update(self, dt, speed_rpm, load_pct):
        """
        Update bearing state for one time step.

        Args:
            dt: time step in seconds
            speed_rpm: shaft speed in RPM
            load_pct: load as percentage of rated
        """
        if speed_rpm < 1:
            self.spectrum = np.zeros(32)
            return

        # === Accumulate operating hours ===
        dt_hours = dt / 3600.0
        self.operating_hours += dt_hours

        # === Degradation rate increases with load and speed ===
        load_factor = 1.0 + (load_pct / 100.0 - 0.5) * 0.5
        speed_factor = (speed_rpm / 1500.0) ** 1.5
        effective_rate = self.degradation_rate * load_factor * speed_factor

        # Health degrades over time
        self.health = max(0.0, self.health - effective_rate * dt_hours)
        self.defect_severity = (100.0 - self.health) / 100.0

        # === Generate vibration spectrum ===
        shaft_freq = speed_rpm / 60.0  # Hz
        defect_freqs = self._calc_defect_frequencies(shaft_freq)
        freq_resolution = 10.0  # Hz per bin
        n_bins = 32

        # Base spectrum — noise floor
        base_noise = 0.1 + np.random.uniform(0, 0.05, n_bins)
        spectrum = base_noise.copy()

        # Shaft frequency (1X) — always present
        shaft_bin = int(shaft_freq / freq_resolution)
        if 0 <= shaft_bin < n_bins:
            spectrum[shaft_bin] += 0.8 + self.defect_severity * 0.5

        # Add defect frequency peaks based on severity
        max_defect_amplitude = 0
        max_defect_name = 'None'

        for name, freq in defect_freqs.items():
            fbin = int(freq / freq_resolution)
            if 0 <= fbin < n_bins:
                # Defect amplitude grows with severity
                amplitude = self.defect_severity ** 1.5 * 8.0
                # Add some randomness
                amplitude *= (0.8 + np.random.uniform(0, 0.4))
                # BPFO typically dominant in outer race defects
                if name == 'BPFO':
                    amplitude *= 1.3
                spectrum[fbin] += amplitude

                if amplitude > max_defect_amplitude:
                    max_defect_amplitude = amplitude
                    max_defect_name = name

                # Harmonics (2X and 3X of defect frequency)
                for harmonic in [2, 3]:
                    hbin = int(freq * harmonic / freq_resolution)
                    if 0 <= hbin < n_bins:
                        spectrum[hbin] += amplitude * (0.3 / harmonic)

        self.spectrum = spectrum
        self.dominant_defect = max_defect_name if max_defect_amplitude > 0.5 else 'None'

    @property
    def iso_class(self):
        """ISO 10816 vibration severity classification."""
        rms = math.sqrt(np.mean(self.spectrum**2)) if len(self.spectrum) > 0 else 0
        if rms <= self.iso_good:
            return 'Good'
        elif rms <= self.iso_satisfactory:
            return 'Satisfactory'
        elif rms <= self.iso_unsatisfactory:
            return 'Unsatisfactory'
        else:
            return 'Unacceptable'

    @property
    def remaining_useful_life_hours(self):
        """Estimated remaining operating hours."""
        if self.degradation_rate <= 0 or self.operating_hours < 0.01:
            return 50000
        avg_rate = (100.0 - self.health) / max(self.operating_hours, 1)
        if avg_rate <= 0.00001:
            return 50000
        return min(50000, max(0, self.health / avg_rate))

    def get_tags(self, prefix):
        """Return all bearing tags with prefix."""
        return {
            f'{prefix}_bearing_health': round(self.health, 2),
            f'{prefix}_combined_health': round((self.health + 100) / 2, 2),
            f'{prefix}_bearing_iso': self.iso_class,
            f'{prefix}_bearing_defect_freq': self.dominant_defect,
            f'{prefix}_rul_hours': round(self.remaining_useful_life_hours, 0),
            f'{prefix}_vibration_spectrum': [round(float(v), 3) for v in self.spectrum],
        }
