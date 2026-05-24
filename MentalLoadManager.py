import platform
import sys
import threading
from collections import deque
from datetime import datetime

import numpy as np


# Configuration du chemin pour la librairie PLUX selon l'OS.
osDic = {
    "Darwin": f"MacOS/Intel{''.join(platform.python_version().split('.')[:2])}",
    "Linux": "Linux64",
    "Windows": f"Win{platform.architecture()[0][:2]}_{''.join(platform.python_version().split('.')[:2])}",
}

if platform.mac_ver()[0] != "":
    import subprocess
    from os import linesep

    p = subprocess.Popen("sw_vers", stdout=subprocess.PIPE)
    result = p.communicate()[0].decode("utf-8").split(str("\t"))[2].split(linesep)[0]
    if result.startswith("12."):
        osDic["Darwin"] = "MacOS/Intel310"
        if int(platform.python_version().split(".")[0]) <= 3 and int(platform.python_version().split(".")[1]) < 10:
            print(f"Python version required is >= 3.10. Installed is {platform.python_version()}")
            exit()

sys.path.append(f"PLUX-API-Python3/{osDic[platform.system()]}")

try:
    import plux
    PLUX_IMPORT_ERROR = None
except ImportError as exc:
    PLUX_IMPORT_ERROR = exc

    class _MissingSignalsDev:
        @staticmethod
        def __init__(*args, **kwargs):
            raise RuntimeError(
                "Impossible de charger la librairie PLUX/BITalino. "
                "Verifiez que la version Python correspond au plux.pyd fourni "
                "et que les DLL natives PLUX sont dans le PATH."
            ) from PLUX_IMPORT_ERROR

    class _MissingPlux:
        SignalsDev = _MissingSignalsDev

    plux = _MissingPlux()


class MentalLoadManager(plux.SignalsDev):
    """
    Gere l'acquisition BITalino et calcule un score de charge mentale interpretable.

    Ordre des ports attendu par defaut:
    - port 1: EDA
    - port 2: PPG
    - port 3: ECG
    - port 4: respiration

    Le score n'utilise pas les amplitudes brutes ECG/PPG comme proxy direct. Il extrait:
    - EDA tonique et activite phasique
    - frequence cardiaque et RMSSD depuis ECG, sinon PPG
    - frequence respiratoire approximee
    puis normalise ces features par rapport a la calibration de repos.
    """

    def __init__(self, address, active_ports=None, channel_names=None):
        plux.SignalsDev.__init__(address)
        self.address = address
        self.is_running = False
        self.sampling_rate = 1000
        self.active_ports = active_ports or [1, 2, 3, 4]
        self.channel_names = channel_names or ["eda", "ppg", "ecg", "resp"]

        self.buffer_duration = 20
        self.max_samples = self.sampling_rate * self.buffer_duration
        self.buffers = {
            name: deque(maxlen=self.max_samples)
            for name in self.channel_names
        }

        self.sample_count = 0
        self.current_mental_load = 0.0
        self.current_features = {}
        self.current_score_components = {}
        self.current_phase = "IDLE"
        self.current_trial_id = 0
        self.current_intensity = None
        self.current_condition = "IDLE"
        self.current_quality = "warming_up"

        self._lock = threading.Lock()
        self.baselines = {}
        self.baseline_stats = {}
        self.is_calibrating = False
        self.calibration_buffer = []
        self.rest_reference_buffer = deque(maxlen=240)
        self.history_load = []
        self.load_history_full = []
        self.feature_history_full = []

        # BITalino EDA raw values usually increase with conductance. If your EDA
        # drops during stress, set this to -1 after a quick visual check.
        self.eda_direction = 1

    def onRawFrame(self, nSeq, data):
        """Callback appele par l'API PLUX pour chaque echantillon."""
        with self._lock:
            for idx, name in enumerate(self.channel_names):
                if idx < len(data):
                    self.buffers[name].append(float(data[idx]))
            self.sample_count += 1
            should_update = self.sample_count % max(1, self.sampling_rate // 2) == 0

        if should_update:
            self._update_metrics()

        return not self.is_running

    def set_phase(self, phase):
        """Ajoute un marqueur de phase experimentale aux futurs points exportes."""
        with self._lock:
            self.current_phase = phase

    def set_context(self, trial_id=None, intensity=None, condition=None):
        """Ajoute les informations d'essai aux futurs points exportes."""
        with self._lock:
            if trial_id is not None:
                self.current_trial_id = trial_id
            if intensity is not None:
                self.current_intensity = intensity
            if condition is not None:
                if condition != self.current_condition:
                    self.history_load = []
                self.current_condition = condition

    def _last_seconds(self, name, seconds):
        values = self.buffers.get(name)
        if not values:
            return np.array([], dtype=float)
        count = min(len(values), int(self.sampling_rate * seconds))
        return np.array(list(values)[-count:], dtype=float)

    def _smooth(self, signal, window_samples):
        if len(signal) < 3 or window_samples <= 1:
            return signal
        window_samples = min(window_samples, len(signal))
        kernel = np.ones(window_samples) / window_samples
        return np.convolve(signal, kernel, mode="same")

    def _detect_peaks(self, signal, min_distance_seconds, threshold_std=0.7):
        if len(signal) < self.sampling_rate:
            return np.array([], dtype=int)

        centered = signal - np.median(signal)
        std = np.std(centered)
        if std < 1e-6:
            return np.array([], dtype=int)

        x = centered / std
        min_distance = max(1, int(min_distance_seconds * self.sampling_rate))
        threshold = threshold_std
        peaks = []
        last_peak = -min_distance

        for idx in range(1, len(x) - 1):
            if idx - last_peak < min_distance:
                continue
            if x[idx] > threshold and x[idx] >= x[idx - 1] and x[idx] > x[idx + 1]:
                peaks.append(idx)
                last_peak = idx

        return np.array(peaks, dtype=int)

    def _best_polarity_peaks(self, signal, min_distance_seconds, threshold_std=0.7):
        positive = self._detect_peaks(signal, min_distance_seconds, threshold_std)
        negative = self._detect_peaks(-signal, min_distance_seconds, threshold_std)
        return positive if len(positive) >= len(negative) else negative

    def _heart_features_from_signal(self, signal, source):
        if len(signal) < self.sampling_rate * 8:
            return {}

        smooth_window = int(self.sampling_rate * (0.025 if source == "ecg" else 0.08))
        smoothed = self._smooth(signal, smooth_window)
        peaks = self._best_polarity_peaks(smoothed, min_distance_seconds=0.35, threshold_std=0.65)
        if len(peaks) < 5:
            return {}

        rr = np.diff(peaks) / self.sampling_rate
        rr = rr[(rr >= 0.33) & (rr <= 1.5)]
        if len(rr) < 4:
            return {}

        heart_rate = 60.0 / np.mean(rr)
        if heart_rate < 40 or heart_rate > 180:
            return {}

        rmssd = 0.0
        if len(rr) > 1:
            rmssd = float(np.sqrt(np.mean(np.diff(rr) ** 2)) * 1000.0)

        return {
            "heart_rate": float(heart_rate),
            "rmssd": float(rmssd),
            "heart_source": source,
            "heart_peaks": int(len(peaks)),
        }

    def _respiration_rate(self, signal):
        if len(signal) < self.sampling_rate * 10:
            return np.nan

        smoothed = self._smooth(signal - np.median(signal), int(self.sampling_rate * 0.4))
        peaks = self._best_polarity_peaks(smoothed, min_distance_seconds=1.5, threshold_std=0.25)
        if len(peaks) < 2:
            return np.nan

        breath_intervals = np.diff(peaks) / self.sampling_rate
        breath_intervals = breath_intervals[(breath_intervals >= 1.5) & (breath_intervals <= 10.0)]
        if len(breath_intervals) == 0:
            return np.nan

        return float(60.0 / np.mean(breath_intervals))

    def _extract_features(self):
        eda = self._last_seconds("eda", 10)
        ppg = self._last_seconds("ppg", 10)
        ecg = self._last_seconds("ecg", 10)
        resp = self._last_seconds("resp", 15)

        if len(eda) < self.sampling_rate * 5:
            return {}

        eda_smooth = self._smooth(eda, int(self.sampling_rate * 0.5))
        eda_tonic = float(np.median(eda_smooth[-self.sampling_rate * 5:]))
        eda_phasic = float(np.std(eda - eda_smooth))

        heart = self._heart_features_from_signal(ecg, "ecg")
        if not heart:
            heart = self._heart_features_from_signal(ppg, "ppg")

        features = {
            "eda_tonic": eda_tonic,
            "eda_phasic": eda_phasic,
            "heart_rate": np.nan,
            "rmssd": np.nan,
            "heart_source": "none",
            "heart_peaks": 0,
            "resp_rate": self._respiration_rate(resp),
            "resp_amplitude": float(np.std(resp)) if len(resp) else np.nan,
        }
        features.update(heart)
        return features

    def _finite_values(self, values):
        return [float(v) for v in values if isinstance(v, (int, float, np.floating)) and np.isfinite(v)]

    def _build_baseline_stats(self):
        return self._build_stats(self.calibration_buffer)

    def _build_stats(self, rows):
        stats = {}
        numeric_keys = [
            "eda_tonic",
            "eda_phasic",
            "heart_rate",
            "rmssd",
            "resp_rate",
            "resp_amplitude",
        ]

        for key in numeric_keys:
            values = self._finite_values(row.get(key) for row in rows)
            if not values:
                continue
            mean = float(np.mean(values))
            std = float(np.std(values))
            floor = max(abs(mean) * 0.03, 1e-3)
            stats[key] = {"mean": mean, "std": max(std, floor)}

        return stats

    def _reference_stats(self):
        if len(self.rest_reference_buffer) >= 20:
            return self._build_stats(self.rest_reference_buffer), "adaptive_rest"
        return self.baseline_stats, "calibration"

    def _z_from_stats(self, stats, key, value, direction=1, mode="directional", deadband=0.25):
        if key not in stats or not np.isfinite(value):
            return 0.0

        mean = stats[key]["mean"]
        std = stats[key]["std"]
        signed_z = direction * (float(value) - mean) / std
        if mode == "absolute":
            z = abs(signed_z)
        else:
            z = signed_z
        z = max(0.0, z - deadband)
        return float(np.clip(z, 0.0, 3.0))

    def _score_from_features(self, features, condition):
        stats, reference_source = self._reference_stats()
        if not stats:
            return 0.0, {"reference_source": "none"}

        components = {
            "rmssd_drop": self._z_from_stats(
                stats, "rmssd", features.get("rmssd", np.nan), direction=-1, deadband=0.20
            ),
            "resp_deviation": self._z_from_stats(
                stats, "resp_rate", features.get("resp_rate", np.nan), mode="absolute", deadband=0.25
            ),
            "heart_deviation": self._z_from_stats(
                stats, "heart_rate", features.get("heart_rate", np.nan), mode="absolute", deadband=0.25
            ),
            "eda_phasic_rise": self._z_from_stats(
                stats, "eda_phasic", features.get("eda_phasic", np.nan), direction=1, deadband=0.20
            ),
            "eda_tonic_deviation": self._z_from_stats(
                stats,
                "eda_tonic",
                features.get("eda_tonic", np.nan),
                direction=self.eda_direction,
                mode="absolute",
                deadband=0.35,
            ),
        }

        weights = {
            "rmssd_drop": 0.42,
            "resp_deviation": 0.32,
            "heart_deviation": 0.06,
            "eda_phasic_rise": 0.15,
            "eda_tonic_deviation": 0.05,
        }
        weighted_z = sum(components[key] * weight for key, weight in weights.items())

        # REST doit rester proche de 0: on l'utilise comme reference, pas comme tache.
        if condition == "REST":
            weighted_z *= 0.35

        score = (weighted_z / 3.0) * 100.0
        components["reference_source"] = reference_source
        return float(np.clip(score, 0.0, 100.0)), components

    def _quality_label(self, features):
        missing = []
        if features.get("heart_source") == "none":
            missing.append("cardiac")
        if not np.isfinite(features.get("resp_rate", np.nan)):
            missing.append("respiration")
        if not self.baseline_stats:
            missing.append("baseline")

        if missing:
            return "limited:" + ",".join(missing)
        return "ok"

    def _update_metrics(self):
        with self._lock:
            features = self._extract_features()
            phase = self.current_phase
            trial_id = self.current_trial_id
            intensity = self.current_intensity
            condition = self.current_condition

        if not features:
            return

        if self.is_calibrating:
            self.calibration_buffer.append(features)
            with self._lock:
                self.current_features = features
                self.current_score_components = {}
                self.current_quality = "calibrating"
            return

        if self.baseline_stats:
            raw_load, score_components = self._score_from_features(features, condition)
            self.history_load.append(raw_load)
            if len(self.history_load) > 6:
                self.history_load.pop(0)
            current_load = float(np.mean(self.history_load))
        else:
            current_load = 0.0
            score_components = {"reference_source": "none"}

        if condition == "REST" and self.baseline_stats:
            self.rest_reference_buffer.append(features)

        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        quality = self._quality_label(features)
        row = {
            "timestamp": timestamp,
            "trial_id": trial_id,
            "intensity": intensity,
            "condition": condition,
            "phase": phase,
            "mental_load": current_load,
            "quality": quality,
            **features,
            **{f"score_{key}": value for key, value in score_components.items()},
        }

        with self._lock:
            self.current_mental_load = current_load
            self.current_features = features
            self.current_score_components = score_components
            self.current_quality = quality
            self.load_history_full.append([timestamp, condition, phase, current_load, quality])
            self.feature_history_full.append(row)

    def start_capture(self):
        """Lance l'acquisition dans un thread dedie."""
        if self.is_running:
            return

        self.is_running = True
        self.thread = threading.Thread(target=self._run_acquisition)
        self.thread.daemon = True
        self.thread.start()
        print(f"Acquisition demarree sur {self.address}")

    def _run_acquisition(self):
        try:
            self.start(self.sampling_rate, self.active_ports, 16)
            self.loop()
        except Exception as e:
            print(f"Erreur lors de l'acquisition : {e}")
        finally:
            self.is_running = False
            self.stop()
            self.close()

    def start_calibration(self):
        """Demarre l'accumulation de donnees pour la ligne de base."""
        with self._lock:
            self.calibration_buffer = []
            self.rest_reference_buffer.clear()
            self.history_load = []
            self.current_mental_load = 0.0
            self.is_calibrating = True
            self.current_phase = "CALIBRATION"
            self.current_quality = "calibrating"
        print("Calibration demarree...")

    def stop_calibration(self):
        """Calcule la ligne de base a partir des donnees accumulees."""
        with self._lock:
            self.is_calibrating = False
            self.baseline_stats = self._build_baseline_stats()
            self.baselines = {
                key: value["mean"]
                for key, value in self.baseline_stats.items()
            }
            self.current_phase = "IDLE"

        print(f"Calibration terminee. Features baseline : {list(self.baselines.keys())}")

    def stop_capture(self):
        """Arrete proprement l'acquisition."""
        self.is_running = False
        if hasattr(self, "thread"):
            self.thread.join(timeout=2.0)
        print("Acquisition arretee.")

    def get_current_load(self):
        """Retourne le dernier score de charge mentale calcule."""
        return self.current_mental_load

    def get_current_quality(self):
        """Retourne un indicateur simple sur la qualite des features."""
        return self.current_quality


if __name__ == "__main__":
    manager = MentalLoadManager("98:D3:C1:FE:04:BB")
