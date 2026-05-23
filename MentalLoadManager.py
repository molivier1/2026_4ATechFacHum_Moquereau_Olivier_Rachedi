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
        self.acc_data = [[], [], []] # X, Y, Z
        self.sample_count = 0
        
        self.current_mental_load = 0.0 # Valeur entre 0 et 100
        self._lock = threading.Lock()

    def onRawFrame(self, nSeq, data):
        """
        Callback appelé par l'API PLUX pour chaque échantillon.
        Ordre attendu des ports : EDA(1), PPG(2), ACC(3,4,5)
        """
        with self._lock:
            # Extraction des données selon l'ordre des ports actifs
            # data[0] est souvent le nSeq interne ou le premier port
            # Ici on assume : 0:EDA, 1:PPG, 2:ACC_X, 3:ACC_Y, 4:ACC_Z
            self.eda_data.append(data[0])
            self.ppg_data.append(data[1])
            self.acc_data[0].append(data[2])
            self.acc_data[1].append(data[3])
            self.acc_data[2].append(data[4])

            # Maintenance de la fenêtre glissante
            if len(self.eda_data) > self.max_samples:
                self.eda_data.pop(0)
                self.ppg_data.pop(0)
                for i in range(3): self.acc_data[i].pop(0)
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
        if len(self.eda_data) < 100:
            return

        with self._lock:
            # 1. Analyse EDA (Conductance : niveau de stress/éveil)
            # On prend la moyenne récente par rapport à la moyenne du buffer
            eda_recent = np.mean(self.eda_data[-500:])
            
            # 2. Analyse PPG (Rythme cardiaque simplifié)
            # On calcule la variance du signal pour détecter l'agitation cardiaque
            ppg_std = np.std(self.ppg_data[-1000:])
            
            # 3. Analyse ACC (Micromouvements)
            # Somme des écarts-types sur les 3 axes
            acc_movement = sum([np.std(axis[-500:]) for axis in self.acc_data])

        # Algorithme de fusion (Métrique "Fiable")
        # On normalise arbitrairement pour l'exemple (à calibrer avec vos sujets)
        # EDA contribue à 50%, PPG à 30%, ACC à 20%
        load_score = (eda_recent * 0.5) + (ppg_std * 0.3) + (acc_movement * 0.2)
        
        # Mapping vers une échelle 0-100
        # Note : nécessite une calibration initiale pour être réellement "fiable"
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
            # Ports 1 à 5 actifs (EDA, PPG, ACC X/Y/Z)
            self.start(self.sampling_rate, [1, 2, 3, 4, 5], 16)
            self.loop()
        except Exception as e:
            print(f"Erreur lors de l'acquisition : {e}")
        finally:
            self.is_running = False
            self.stop()
            self.close()

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