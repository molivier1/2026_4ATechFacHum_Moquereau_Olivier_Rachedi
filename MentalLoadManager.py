import platform
import sys
import threading
import numpy as np
import time

# Configuration du chemin pour la librairie PLUX selon l'OS
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
            print(f"Python version required is ≥ 3.10. Installed is {platform.python_version()}")
            exit()

sys.path.append(f"PLUX-API-Python3/{osDic[platform.system()]}")

import plux

class MentalLoadManager(plux.SignalsDev):
    """
    Gère l'acquisition des données BITalino et le calcul de la charge mentale.
    Utilise un thread séparé pour l'acquisition afin de laisser l'UI fluide.
    """
    def __init__(self, address):
        plux.SignalsDev.__init__(address)
        self.address = address
        self.is_running = False
        self.sampling_rate = 1000
        
        # Buffers pour stocker les dernières secondes de données (fenêtre glissante)
        self.buffer_duration = 5  # secondes
        self.max_samples = self.sampling_rate * self.buffer_duration
        
        self.eda_data = []
        self.ppg_data = []
        self.ecg_data = [] # Nouveau buffer pour l'ECG
        self.respiration_data = [] # Nouveau buffer pour la respiration
        self.sample_count = 0
        
        self.current_mental_load = 0.0 # Valeur entre 0 et 100
        self._lock = threading.Lock()
        self.baseline_score = None
        self.is_calibrating = False
        self.calibration_buffer = []

    def onRawFrame(self, nSeq, data):
        """
        Callback appelé par l'API PLUX pour chaque échantillon.
        Ordre attendu des ports : EDA(1), PPG(2), ACC(3,4,5)
        Nouvel ordre attendu des ports : EDA(1), PPG(2), ECG(3), Respiration(4)
        """
        with self._lock:
            # Extraction des données selon l'ordre des ports actifs
            # Assumed order: 0:EDA, 1:PPG, 2:ECG, 3:Respiration
            self.eda_data.append(data[0])
            self.ppg_data.append(data[1])
            self.ecg_data.append(data[2])
            self.respiration_data.append(data[3])

            # Maintenance de la fenêtre glissante
            if len(self.eda_data) > self.max_samples:
                self.eda_data.pop(0)
                self.ppg_data.pop(0)
                self.ecg_data.pop(0) # Pop pour l'ECG
                self.respiration_data.pop(0) # Pop pour la respiration
            self.sample_count += 1

        # Calcul de la métrique tous les 500 échantillons (500ms à 1000Hz)
        if self.sample_count % 500 == 0:
            self._update_metrics()

        return not self.is_running

    def _update_metrics(self):
        """
        Calcule la corrélation entre EDA, PPG et ACC pour estimer la charge mentale.
        Ceci est une implémentation simplifiée à affiner selon vos tests.
        """
        if len(self.eda_data) < self.sampling_rate or \
           len(self.ppg_data) < self.sampling_rate or \
           len(self.ecg_data) < self.sampling_rate or \
           len(self.respiration_data) < self.sampling_rate:
            return

        with self._lock:
            # 1. Analyse EDA (Conductance : niveau de stress/éveil)
            # On prend la moyenne récente sur 0.5s
            eda_recent = np.mean(self.eda_data[-self.sampling_rate // 2:])
            
            # 2. Analyse PPG (Traitement anti-mouvement)
            ppg_window = np.array(self.ppg_data[-self.sampling_rate:])
            # On soustrait la moyenne pour supprimer la dérive de la ligne de base (mouvement)
            ppg_detrended = ppg_window - np.mean(ppg_window)
            # On utilise le percentile 90 plutôt que le std pour ignorer les pics de mouvement
            ppg_robust_amp = np.percentile(np.abs(ppg_detrended), 90)
            
            # 3. Analyse ECG (Variabilité cardiaque simplifiée)
            # On calcule la variabilité du signal sur 1s
            ecg_std = np.std(self.ecg_data[-self.sampling_rate:])
            
            # 4. Analyse Respiration (Variabilité respiratoire simplifiée)
            # On calcule la variabilité du signal sur 1s
            respiration_std = np.std(self.respiration_data[-self.sampling_rate:])

        # Algorithme de fusion (Métrique "Fiable")
        # On donne plus de poids à l'ECG et à l'EDA car le PPG est trop bruité par le mouvement
        # EDA (40%), ECG (40%), PPG (10%), Respiration (10%)
        load_score = (eda_recent * 0.4) + (ppg_robust_amp * 0.1) + (ecg_std * 0.4) + (respiration_std * 0.1)
        
        if self.is_calibrating:
            self.calibration_buffer.append(load_score)
            return

        if self.baseline_score is not None and self.baseline_score > 0:
            # On calcule l'augmentation par rapport au repos (baseline)
            # Sensibilité ajustable : ici, on considère qu'une augmentation de 15% 
            # par rapport à la baseline correspond à 100% de charge mentale.
            sensitivity = 0.15 
            diff = load_score - self.baseline_score
            
            # On transforme l'augmentation en pourcentage (0-100)
            load_percent = (diff / (self.baseline_score * sensitivity)) * 100
            self.current_mental_load = min(max(load_percent, 0), 100)
        else:
            # Valeur par défaut si pas de calibration (peu sensible)
            # Utilisation d'une valeur arbitraire pour la division si baseline non définie
            # Cela devrait être remplacé par une calibration ou une valeur par défaut plus robuste
            self.current_mental_load = min(max(load_score / 10.0, 0), 100)

    def start_capture(self):
        """Lance l'acquisition dans un thread dédié"""
        if self.is_running:
            return
        
        self.is_running = True
        self.thread = threading.Thread(target=self._run_acquisition)
        self.thread.daemon = True
        self.thread.start()
        print(f"Acquisition démarrée sur {self.address}")

    def _run_acquisition(self):
        try:
            # Ports actifs : EDA(1), PPG(2), ECG(3), Respiration(4)
            self.start(self.sampling_rate, [1, 2, 3, 4], 16)
            self.loop()
        except Exception as e:
            print(f"Erreur lors de l'acquisition : {e}")
        finally:
            self.is_running = False
            self.stop()
            self.close()

    def start_calibration(self):
        """Démarre l'accumulation de données pour la ligne de base"""
        with self._lock:
            self.calibration_buffer = []
            self.is_calibrating = True
        print("Calibration démarrée...")

    def stop_calibration(self):
        """Calcule la ligne de base à partir des données accumulées"""
        with self._lock:
            self.is_calibrating = False
            if self.calibration_buffer:
                self.baseline_score = np.mean(self.calibration_buffer)
            else:
                self.baseline_score = 1.0 # Empêche la division par zéro si aucune donnée n'est collectée
        print(f"Calibration terminée. Baseline: {self.baseline_score}")

    def stop_capture(self):
        """Arrête proprement l'acquisition"""
        self.is_running = False
        if hasattr(self, 'thread'):
            self.thread.join(timeout=2.0)
        print("Acquisition arrêtée.")

    def get_current_load(self):
        """
        Fonction à appeler depuis l'interface pour obtenir 
        le dernier score de charge mentale calculé.
        """
        return self.current_mental_load

if __name__ == "__main__":
    # Test rapide du module
    manager = MentalLoadManager("98:D3:C1:FE:04:BB")