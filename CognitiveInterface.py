import tkinter as tk
from tkinter import ttk
import random
import string
import csv
import time
from datetime import datetime
from MentalLoadManager import MentalLoadManager

class CognitiveGame:
    def __init__(self, root):
        self.root = root
        self.root.title("Protocole d'Évaluation de la Charge Mentale")
        self.root.geometry("900x700")
        self.root.configure(bg="#1A1A2E") # Bleu très foncé presque noir

        # Couleurs de thème
        self.colors = {
            "bg": "#1A1A2E",
            "card": "#16213E",
            "accent": "#E94560",
            "text": "#E9E9E9",
            "blue": "#0F3460",
            "success": "#00D26A"
        }

        # Variables d'état
        self.intensity = 3  # Niveau de 1 à 10
        self.mental_load = 0  # Charge mentale (0-100), à lier aux capteurs plus tard
        self.state = "IDLE" # IDLE, MEMORIZE, READ, MATH, INPUT, RECALL
        self.target_letters = ""
        self.math_solution = 0
        self.math_correct = None
        self.timer_value = 0
        self.timer_running = False
        self.all_data = []
        self.is_calibrated = False

        # --- Zone d'Affichage Principale ---
        self.main_frame = tk.Frame(root, bg=self.colors["card"], highlightbackground="#4E4E6A", highlightthickness=1)
        self.main_frame.pack(expand=True, fill="both", padx=40, pady=(40, 20))

        self.label_task = tk.Label(self.main_frame, text="", font=("Helvetica", 16), fg=self.colors["text"], bg=self.colors["card"], wraplength=700)
        self.label_task.pack(expand=True)

        self.label_timer = tk.Label(self.main_frame, text="", font=("Helvetica", 14), fg=self.colors["accent"], bg=self.colors["card"])
        self.label_timer.pack(pady=10)

        # Champ de saisie pour le rappel (caché par défaut)
        self.entry_recall = tk.Entry(self.main_frame, font=("Helvetica", 40, "bold"), 
                                    bg=self.colors["bg"], fg=self.colors["accent"], 
                                    insertbackground="white", justify="center", width=10,
                                    relief="flat", highlightthickness=1, highlightbackground="#4E4E6A")

        # --- Feedback Charge Mentale (Représentation Simplifiée) ---
        self.viz_frame = tk.LabelFrame(root, text=" CHARGE MENTALE (TEMPS RÉEL) ", font=("Helvetica", 10, "bold"), fg="#8888A0", bg=self.colors["bg"], bd=1)
        self.viz_frame.pack(fill="x", padx=40, pady=10)

        self.canvas_load = tk.Canvas(self.viz_frame, height=40, bg="#dddddd", highlightthickness=0)
        self.canvas_load.pack(fill="x", padx=20, pady=10)
        self.load_bar = self.canvas_load.create_rectangle(0, 0, 0, 40, fill="#4CAF50")
        
        # --- Contrôles de l'Expérience ---
        self.ctrl_frame = tk.Frame(root, bg=self.colors["bg"])
        self.ctrl_frame.pack(pady=10)

        # Réglage de l'intensité
        tk.Label(self.ctrl_frame, text="AJUSTER L'INTENSITÉ", font=("Helvetica", 9), fg="#8888A0", bg=self.colors["bg"]).grid(row=0, column=0, columnspan=3)
        
        self.btn_minus = tk.Button(self.ctrl_frame, text="-", command=self.decrease_intensity, width=4, 
                                   bg=self.colors["blue"], fg="white", font=("Arial", 14, "bold"), relief="flat")
        self.btn_minus.grid(row=1, column=0, padx=5, pady=5)
        
        self.label_int_val = tk.Label(self.ctrl_frame, text=f"Niveau : {self.intensity}", font=("Helvetica", 14, "bold"), fg=self.colors["text"], bg=self.colors["bg"])
        self.label_int_val.grid(row=1, column=1, padx=20)

        self.btn_plus = tk.Button(self.ctrl_frame, text="+", command=self.increase_intensity, width=4, 
                                  bg=self.colors["blue"], fg="white", font=("Arial", 14, "bold"), relief="flat")
        self.btn_plus.grid(row=1, column=2, padx=5, pady=5)

        # Barre de niveau d'intensité (Visuelle)
        self.canvas_int_lvl = tk.Canvas(self.ctrl_frame, width=200, height=10, bg=self.colors["card"], highlightthickness=0)
        self.canvas_int_lvl.grid(row=2, column=0, columnspan=3, pady=10)
        self.int_lvl_bar = self.canvas_int_lvl.create_rectangle(0, 0, 0, 10, fill=self.colors["accent"])

        # Bouton d'action
        self.btn_action = tk.Button(root, text="DÉMARRER LA SESSION", command=self.next_step, 
                                   bg=self.colors["accent"], fg="white", font=("Helvetica", 14, "bold"), 
                                   padx=40, pady=15, relief="flat", cursor="hand2")
        self.btn_action.pack(pady=30)

        # Bouton d'export CSV (masqué par défaut)
        self.btn_export = tk.Button(root, text="EXPORTER LES DONNÉES (CSV)", command=self.export_csv, 
                                   bg=self.colors["blue"], fg="white", font=("Helvetica", 12, "bold"), 
                                   padx=20, pady=10, relief="flat", cursor="hand2")

        # Initialisation du gestionnaire de charge mentale (BITalino)
        # On utilise l'adresse MAC configurée dans vos fichiers d'acquisition
        self.manager = MentalLoadManager("98:D3:C1:FE:04:BB")
        self.manager.start_capture()

        # Protocole pour arrêter l'acquisition quand on ferme la fenêtre
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.update_ui_elements()

        # Lancement de la boucle de simulation de charge (à lier au BITalino plus tard)
        self.update_load_visual()

    def increase_intensity(self):
        if self.intensity < 10:
            self.intensity += 1
            self.update_ui_elements()

    def decrease_intensity(self):
        if self.intensity > 1:
            self.intensity -= 1
            self.update_ui_elements()

    def update_ui_elements(self):
        self.label_int_val.config(text=f"Niveau : {self.intensity}")
        # Mise à jour de la petite barre sous les boutons +/-
        fill_width = (self.intensity / 10.0) * 200
        self.canvas_int_lvl.coords(self.int_lvl_bar, 0, 0, fill_width, 10)

        # Mise à jour dynamique des instructions si on est sur l'écran d'accueil (IDLE)
        if self.state == "IDLE":
            self.btn_action.config(state="normal")
            if not self.is_calibrated:
                calib_text = "BIENVENUE DANS L'EXPÉRIENCE\n\nPour garantir des mesures fiables, nous devons établir votre profil physiologique de base (ligne de base).\n\nCONSIGNES :\n1. Installez-vous confortablement.\n2. Restez immobile et silencieux.\n3. Respirez normalement et détendez-vous.\n\nCette phase durera 30 secondes."
                self.label_task.config(text=calib_text, font=("Helvetica", 18, "bold"), fg=self.colors["accent"])
                self.btn_action.config(text="LANCER LA CALIBRATION (30s)")
            else:
                self.label_task.config(text=self.get_instructions(), font=("Helvetica", 16), fg=self.colors["text"])
                self.btn_action.config(text="DÉMARRER LA SESSION")

    def get_instructions(self):
        """Génère les modalités de l'examen dynamiquement selon l'intensité"""
        num_letters_memorize = 3 + (self.intensity // 2)
        timer_memorize = 5 + (self.intensity // 2)
        timer_input = 10 + (self.intensity // 2)

        math_desc = ""
        if self.intensity < 5:
            math_desc = "• CALCUL : Désactivé pour ce niveau."
        elif self.intensity < 7:
            math_desc = "• CALCUL : Résolvez une addition simple (10s)."
        elif self.intensity < 9:
            math_desc = "• CALCUL : Résolvez une addition plus complexe (10s)."
        else:
            math_desc = "• CALCUL : Résolvez une multiplication (10s)."

        return (
            f"MODALITÉS DE L'EXPÉRIENCE (INTENSITÉ {self.intensity})\n\n"
            f"• MÉMORISATION : Une suite de {num_letters_memorize} lettres va apparaître. Retenez-les bien ({timer_memorize}s).\n"
            "• LECTURE : Un texte scientifique s'affichera. Lisez-le attentivement pour maintenir votre concentration.\n"
            f"{math_desc}\n"
            f"• RAPPEL : Saisissez les lettres initiales dans l'ordre exact ({timer_input}s).\n\n"
            "UTILISEZ LES BOUTONS +/- POUR AJUSTER LA DIFFICULTÉ AVANT DE COMMENCER."
        )

    def start_timer(self, seconds):
        self.timer_value = seconds
        self.timer_running = True
        self.update_timer()

    def update_timer(self):
        if self.timer_running and self.timer_value > 0:
            self.label_timer.config(text=f"Temps restant : {self.timer_value}s")
            self.timer_value -= 1
            self.root.after(1000, self.update_timer)
        elif self.timer_running:
            self.timer_running = False
            if self.state == "CALIBRATING":
                self.manager.stop_calibration()
                self.is_calibrated = True
                self.state = "IDLE"
                self.update_ui_elements()
            else:
                self.next_step() # Déclenchement automatique du changement de slide

    def update_load_visual(self):
        """Affiche la charge mentale calculée en temps réel par le MentalLoadManager"""
        width = self.canvas_load.winfo_width()
        if width <= 1: width = 820 # Largeur par défaut si le rendu n'est pas fini

        # Récupération de la valeur calculée par le thread d'acquisition
        self.mental_load = self.manager.get_current_load()
        fill_width = (self.mental_load / 100.0) * width

        # Changement de couleur selon la charge
        color = "#4CAF50" if self.mental_load < 40 else "#FF9800" if self.mental_load < 80 else "#F44336"
        
        self.canvas_load.coords(self.load_bar, 0, 0, fill_width, 40)
        self.canvas_load.itemconfig(self.load_bar, fill=color)
        
        # Rafraîchissement toutes le 200ms
        self.root.after(200, self.update_load_visual)

    def next_step(self):
        self.timer_running = False # Arrêt du timer à chaque transition
        self.label_timer.config(text="")

        if self.state == "IDLE":
            if not self.is_calibrated:
                self.state = "CALIBRATING"
                self.label_task.config(text="CALIBRATION EN COURS...\n\nNe bougez pas, respirez normalement.", fg=self.colors["text"])
                self.btn_action.config(text="CALIBRATION...", state="disabled")
                self.manager.start_calibration()
                self.start_timer(30)
                return

            self.btn_export.pack_forget() # On cache le bouton d'export si on recommence
            self.btn_export.config(text="EXPORTER LES DONNÉES (CSV)", state="normal", bg=self.colors["blue"])
            self.state = "MEMORIZE"
            self.math_correct = None
            # Le nombre de lettres dépend de l'intensité (de 3 à 8 lettres)
            num_letters = 3 + (self.intensity // 2)
            self.target_letters = ''.join(random.choices(string.ascii_uppercase, k=num_letters))
            self.label_task.config(text=f"MÉMORISATION ({num_letters} lettres)\n\n{self.target_letters}", font=("Helvetica", 40, "bold"), fg=self.colors["accent"])
            self.btn_action.config(text="J'AI MÉMORISÉ", bg=self.colors["success"])
            self.start_timer(5 + (self.intensity // 2)) # Timer proportionnel
            
        elif self.state == "MEMORIZE":
            self.state = "READ"
            if self.intensity < 5:
                text_sample = ("L'attention est une fonction cognitive complexe qui permet de sélectionner un stimulus "
                              "spécifique parmi une multitude d'informations sensorielles tout en ignorant les "
                              "distractions environnementales. Elle est essentielle pour le traitement efficace de "
                              "l'information et joue un rôle crucial dans les processus d'apprentissage.")
            else:
                text_sample = ("L'inhibition cognitive est la capacité de l'esprit à écarter des informations non "
                              "pertinentes ou à supprimer des réponses automatiques qui interfèrent avec les objectifs "
                              "de la tâche en cours. Le modèle de Baddeley décrit la mémoire de travail comme un système "
                              "composé d'un administrateur central, d'une boucle phonologique pour les sons et d'un "
                              "calepin visuo-spatial pour les images. Ce système possède une capacité limitée, et son "
                              "dépassement entraîne une fatigue cognitive importante, souvent accompagnée de variations "
                              "physiologiques mesurables telles que l'augmentation de la conductance cutanée ou la "
                              "modification de la variabilité cardiaque.")
            
            self.label_task.config(text=f"LECTURE\n\n{text_sample}", font=("Helvetica", 16), fg=self.colors["text"])
            self.btn_action.config(text="CONTINUER", bg=self.colors["blue"])

        elif self.state == "READ":
            # Si intensité élevée, on ajoute une tâche de calcul mental
            if self.intensity >= 5:
                self.state = "MATH"
                operation_text = ""
                if self.intensity < 7: # Intensité 5-6: addition simple
                    a, b = random.randint(10, 50), random.randint(10, 50)
                    self.math_solution = a + b
                    operation_text = f"{a} + {b}"
                elif self.intensity < 9: # Intensité 7-8: addition plus complexe
                    a, b = random.randint(50, 100), random.randint(50, 100)
                    self.math_solution = a + b
                    operation_text = f"{a} + {b}"
                else: # Intensité 9-10: multiplication
                    # Nombres choisis pour rester faisables mentalement
                    a = random.randint(10, 20)
                    b = random.randint(5, 15)
                    self.math_solution = a * b
                    operation_text = f"{a} x {b}"

                self.label_task.config(text=f"CALCUL MENTAL\n\nCombien font : {operation_text} ?", font=("Helvetica", 25, "bold"))
                self.entry_recall.pack(pady=20)
                self.entry_recall.delete(0, tk.END)
                self.entry_recall.focus_set()
                self.btn_action.config(text="VALIDER LE CALCUL", bg=self.colors["accent"])
                self.start_timer(10)
            else:
                self.go_to_input()

        elif self.state == "MATH":
            try:
                user_val = self.entry_recall.get().strip()
                self.math_correct = (int(user_val) == self.math_solution)
            except ValueError:
                self.math_correct = False
                
            self.entry_recall.pack_forget()
            self.go_to_input()

        elif self.state == "INPUT":
            self.process_recall()

        elif self.state == "RECALL":
            self.state = "IDLE"
            self.update_ui_elements() # Re-affiche les instructions dynamiques
            self.btn_action.config(text="DÉMARRER LA SESSION", bg=self.colors["accent"])
            if self.all_data: # On affiche le bouton d'export seulement s'il y a des données
                self.btn_export.pack(pady=5)

    def go_to_input(self):
            self.state = "INPUT"
            self.label_task.config(text=f"RECOUVREMENT\n\nTapez les {len(self.target_letters)} lettres mémorisées :", font=("Helvetica", 18, "bold"))
            self.entry_recall.pack(pady=20)
            self.entry_recall.delete(0, tk.END)
            self.entry_recall.focus_set()
            self.btn_action.config(text="VÉRIFIER LES LETTRES", bg=self.colors["accent"])
            self.start_timer(10 + (self.intensity // 2)) # Ajout d'un timer pour la saisie

    def process_recall(self):
            user_res = self.entry_recall.get().strip().upper()
            self.entry_recall.pack_forget()
            self.state = "RECALL"
            
            if user_res == self.target_letters:
                result_text = f"BRAVO !\n\nVous avez trouvé : {user_res}"
                result_color = self.colors["success"]
            else:
                result_text = f"DOMMAGE...\n\nVous avez tapé : {user_res}\nLa réponse était : {self.target_letters}"
                result_color = self.colors["accent"]

            # Ajout de l'indicateur de calcul mental si la tâche a eu lieu
            if self.intensity >= 5 and self.math_correct is not None:
                math_status = "✅ Calcul correct" if self.math_correct else f"❌ Calcul faux (réponse: {self.math_solution})"
                result_text += f"\n\n{math_status}"

            # Accumulation des données pour l'export optionnel à la fin
            self.all_data.append([
                datetime.now().strftime('%H:%M:%S'), self.intensity, 
                self.target_letters, user_res, self.math_correct, self.mental_load
            ])

            self.label_task.config(text=result_text, font=("Helvetica", 22, "bold"), fg=result_color)
            self.btn_action.config(text="CONTINUER", bg=self.colors["blue"])

    def export_csv(self):
        """Génère le fichier CSV avec toutes les données accumulées durant la session"""
        timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        summary_filename = f"summary_{timestamp_str}.csv"
        timeline_filename = f"timeline_{timestamp_str}.csv"
        
        # 1. Export du résumé (Performance globale par étape)
        with open(summary_filename, mode='w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Timestamp', 'Intensity', 'Letters_Target', 'Letters_Input', 'Math_Correct', 'Final_Load'])
            writer.writerows(self.all_data)
            
        # 2. Export de la chronologie complète (Charge mentale toutes les 0.5s)
        with open(timeline_filename, mode='w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Timestamp', 'Mental_Load_Value'])
            writer.writerows(self.manager.load_history_full)
        
        # Feedback visuel après export
        self.btn_export.config(text="CSV GÉNÉRÉS ✅", state="disabled", bg=self.colors["success"])

    def on_closing(self):
        """Arrête proprement l'acquisition BITalino avant de quitter"""
        self.manager.stop_capture()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    game = CognitiveGame(root)
    root.mainloop()