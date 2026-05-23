import platform
import sys
import threading
import numpy as np
import time
from datetime import datetime

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
        self.buffer_duration = 10  # Augmenté à 10s pour plus de stabilité
        self.max_samples = self.sampling_rate * self.buffer_duration
        
        self.eda_data = []
        self.ppg_data = []
        self.ecg_data = [] # Nouveau buffer pour l'ECG
        self.respiration_data = [] # Nouveau buffer pour la respiration
        self.sample_count = 0
        self.history_load = [] # Pour lissage final
        
        self.current_mental_load = 0.0 # Valeur entre 0 et 100
        self._lock = threading.Lock()
        self.baselines = {} # Stocke les valeurs de repos par capteur
        self.is_calibrating = False
        self.calibration_buffer = []
        self.load_history_full = [] # Historique complet pour l'export (horodatage, charge)

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
            # Fenêtrage plus large pour l'ECG/PPG afin de capturer plusieurs cycles cardiaques
            # Cela évite que la barre ne saute à chaque battement
            # EDA : Moyenne (Niveau de sudation)
            curr_eda = np.mean(self.eda_data[-self.sampling_rate * 2:]) # Moyenne sur 2s
            
            # ECG : On regarde la puissance du signal sur 5 secondes pour lisser
            curr_ecg = np.std(self.ecg_data[-self.sampling_rate * 5:])
            
            # PPG : Idem sur 5 secondes
            ppg_window = np.array(self.ppg_data[-self.sampling_rate * 5:])
            curr_ppg = np.std(ppg_window - np.mean(ppg_window))
            
            # Respiration : Fréquence d'oscillation (simplifiée par l'écart-type)
            curr_res = np.std(self.respiration_data[-self.sampling_rate:])

        # Pendant la calibration, on stocke les valeurs brutes
        if self.is_calibrating:
            self.calibration_buffer.append({
                'eda': curr_eda, 'ppg': curr_ppg, 'ecg': curr_ecg, 'res': curr_res
            })
            return

        # Calcul du score basé sur la déviation par rapport à la baseline
        if self.baselines:
            # Calcul du pourcentage de changement pour chaque capteur
            # On évite la division par zéro avec +1e-6
            diff_eda = (curr_eda - self.baselines['eda']) / (self.baselines['eda'] + 1e-6)
            diff_ecg = (curr_ecg - self.baselines['ecg']) / (self.baselines['ecg'] + 1e-6)
            diff_ppg = (curr_ppg - self.baselines['ppg']) / (self.baselines['ppg'] + 1e-6)
            diff_res = (curr_res - self.baselines['res']) / (self.baselines['res'] + 1e-6)

            # Fusion pondérée des déviations (EDA et ECG sont prioritaires)
            gain = 3.0 
            total_diff = (diff_eda * 0.4) + (diff_ecg * 0.4) + (diff_ppg * 0.1) + (diff_res * 0.1)
            
            # Mapping 0-100
            raw_load = total_diff * gain * 100
            
            # Lissage temporel (Moyenne mobile sur les 5 derniers calculs)
            self.history_load.append(raw_load)
            if len(self.history_load) > 5:
                self.history_load.pop(0)
            
            smoothed_load = sum(self.history_load) / len(self.history_load)
            self.current_mental_load = min(max(smoothed_load, 0), 100)
            
            # Sauvegarde dans l'historique complet pour l'export (chaque 0.5s)
            self.load_history_full.append([datetime.now().strftime('%H:%M:%S.%f')[:-3], self.current_mental_load])
        
        else:
            self.current_mental_load = 0.0

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
                self.baselines = {
                    'eda': np.mean([x['eda'] for x in self.calibration_buffer]),
                    'ppg': np.mean([x['ppg'] for x in self.calibration_buffer]),
                    'ecg': np.mean([x['ecg'] for x in self.calibration_buffer]),
                    'res': np.mean([x['res'] for x in self.calibration_buffer])
                }
        print(f"Calibration terminée. Baselines enregistrées : {self.baselines.keys()}")

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