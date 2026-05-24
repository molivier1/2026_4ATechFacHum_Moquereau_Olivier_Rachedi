import csv
from pathlib import Path
import random
from datetime import datetime

import tkinter as tk

from MentalLoadManager import MentalLoadManager


class CognitiveGame:
    """Interface du protocole par blocs longs repos / low load / high load."""

    CALIBRATION_SECONDS = 60
    BLOCK_SECONDS = 60
    REST_SECONDS = 30

    def __init__(self, root):
        self.root = root
        self.root.title("CogniCharge - Protocole par blocs")
        self.root.geometry("900x720")
        self.root.configure(bg="#1A1A2E")

        self.colors = {
            "bg": "#1A1A2E",
            "card": "#16213E",
            "accent": "#E94560",
            "text": "#E9E9E9",
            "muted": "#8888A0",
            "blue": "#0F3460",
            "success": "#00D26A",
        }

        self.state = "IDLE"
        self.timer_value = 0
        self.timer_running = False
        self.mental_load = 0.0
        self.is_calibrated = False

        self.block_plan = self.build_block_plan()
        self.block_index = -1
        self.current_block = None
        self.block_results = []

        self.high_left = 0
        self.high_step = 0
        self.high_solution = 0
        self.high_total = 0
        self.high_correct = 0

        self.main_frame = tk.Frame(
            root,
            bg=self.colors["card"],
            highlightbackground="#4E4E6A",
            highlightthickness=1,
        )
        self.main_frame.pack(expand=True, fill="both", padx=40, pady=(40, 20))

        self.label_title = tk.Label(
            self.main_frame,
            text="",
            font=("Helvetica", 22, "bold"),
            fg=self.colors["accent"],
            bg=self.colors["card"],
        )
        self.label_title.pack(pady=(30, 10))

        self.label_task = tk.Label(
            self.main_frame,
            text="",
            font=("Helvetica", 18),
            fg=self.colors["text"],
            bg=self.colors["card"],
            wraplength=760,
            justify="center",
        )
        self.label_task.pack(expand=True, padx=30)

        self.chart_frame = tk.Frame(self.main_frame, bg=self.colors["card"])
        self.chart_canvas = tk.Canvas(
            self.chart_frame,
            width=760,
            height=260,
            bg="#10182C",
            highlightthickness=1,
            highlightbackground="#4E4E6A",
        )
        self.chart_canvas.pack(padx=20, pady=10)
        self.chart_canvas.bind("<Configure>", lambda event: self.draw_load_chart())

        self.entry_answer = tk.Entry(
            self.main_frame,
            font=("Helvetica", 36, "bold"),
            bg=self.colors["bg"],
            fg=self.colors["accent"],
            insertbackground="white",
            justify="center",
            width=10,
            relief="flat",
            highlightthickness=1,
            highlightbackground="#4E4E6A",
        )
        self.entry_answer.bind("<Return>", lambda event: self.submit_high_answer())

        self.label_timer = tk.Label(
            self.main_frame,
            text="",
            font=("Helvetica", 16, "bold"),
            fg=self.colors["accent"],
            bg=self.colors["card"],
        )
        self.label_timer.pack(pady=(10, 30))

        self.rating_frame = tk.Frame(self.main_frame, bg=self.colors["card"])
        self.rating_buttons = []
        for value in range(1, 8):
            btn = tk.Button(
                self.rating_frame,
                text=str(value),
                command=lambda v=value: self.submit_rating(v),
                width=4,
                bg=self.colors["blue"],
                fg="white",
                font=("Helvetica", 16, "bold"),
                relief="flat",
                cursor="hand2",
            )
            btn.pack(side="left", padx=5, pady=10)
            self.rating_buttons.append(btn)

        self.viz_frame = tk.LabelFrame(
            root,
            text=" CHARGE MENTALE TEMPS REEL ",
            font=("Helvetica", 10, "bold"),
            fg=self.colors["muted"],
            bg=self.colors["bg"],
            bd=1,
        )
        self.viz_frame.pack(fill="x", padx=40, pady=10)

        self.canvas_load = tk.Canvas(self.viz_frame, height=40, bg="#dddddd", highlightthickness=0)
        self.canvas_load.pack(fill="x", padx=20, pady=10)
        self.load_bar = self.canvas_load.create_rectangle(0, 0, 0, 40, fill="#4CAF50")

        self.btn_action = tk.Button(
            root,
            text="LANCER LA CALIBRATION",
            command=self.next_step,
            bg=self.colors["accent"],
            fg="white",
            font=("Helvetica", 14, "bold"),
            padx=40,
            pady=15,
            relief="flat",
            cursor="hand2",
        )
        self.btn_action.pack(pady=20)

        self.btn_export = tk.Button(
            root,
            text="EXPORTER LES DONNEES (CSV)",
            command=self.export_csv,
            bg=self.colors["blue"],
            fg="white",
            font=("Helvetica", 12, "bold"),
            padx=20,
            pady=10,
            relief="flat",
            cursor="hand2",
        )

        self.manager = MentalLoadManager("98:D3:C1:FE:04:BB")
        self.manager.start_capture()
        self.manager.set_phase(self.state)
        self.manager.set_context(trial_id=0, intensity=0, condition="IDLE")

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.show_home()
        self.update_load_visual()

    def build_block_plan(self):
        task_blocks = [
            {"condition": "LOW", "intensity": 2, "duration": self.BLOCK_SECONDS},
            {"condition": "LOW", "intensity": 2, "duration": self.BLOCK_SECONDS},
            {"condition": "LOW", "intensity": 2, "duration": self.BLOCK_SECONDS},
            {"condition": "HIGH", "intensity": 10, "duration": self.BLOCK_SECONDS},
            {"condition": "HIGH", "intensity": 10, "duration": self.BLOCK_SECONDS},
            {"condition": "HIGH", "intensity": 10, "duration": self.BLOCK_SECONDS},
        ]
        random.shuffle(task_blocks)

        plan = [{"condition": "REST", "intensity": 0, "duration": self.REST_SECONDS}]
        for block in task_blocks:
            plan.append(block)
            plan.append({"condition": "REST", "intensity": 0, "duration": self.REST_SECONDS})
        return plan

    def show_home(self):
        self.hide_entry()
        self.hide_rating()
        self.hide_chart()
        self.label_title.config(text="PROTOCOLE PAR BLOCS")
        self.label_task.config(
            text=(
                "Le protocole va mesurer des blocs longs et comparables.\n\n"
                f"1. Calibration repos: {self.CALIBRATION_SECONDS}s\n"
                f"2. Blocs REST: {self.REST_SECONDS}s\n"
                f"3. Blocs LOW: {self.BLOCK_SECONDS}s, fixation calme\n"
                f"4. Blocs HIGH: {self.BLOCK_SECONDS}s, calcul mental continu\n\n"
                "Apres chaque bloc, donnez votre charge percue de 1 a 7."
            ),
            font=("Helvetica", 18),
            fg=self.colors["text"],
        )
        self.label_timer.config(text="")
        self.btn_action.config(
            text="LANCER LA CALIBRATION",
            command=self.next_step,
            state="normal",
            bg=self.colors["accent"],
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
            return

        if not self.timer_running:
            return

        self.timer_running = False
        self.label_timer.config(text="")

        if self.state == "CALIBRATING":
            self.manager.stop_calibration()
            self.is_calibrated = True
            self.state = "READY"
            self.manager.set_phase(self.state)
            self.manager.set_context(trial_id=0, intensity=0, condition="READY")
            self.label_title.config(text="CALIBRATION TERMINEE")
            self.label_task.config(
                text=(
                    "La ligne de base est enregistree.\n\n"
                    "La session va maintenant alterner REST, LOW et HIGH."
                ),
                fg=self.colors["text"],
            )
            self.btn_action.config(text="DEMARRER LES BLOCS", state="normal", bg=self.colors["success"])
        elif self.state == "BLOCK":
            self.finish_current_block()

    def update_load_visual(self):
        width = self.canvas_load.winfo_width()
        if width <= 1:
            width = 820

        self.mental_load = self.manager.get_current_load()
        fill_width = (self.mental_load / 100.0) * width
        color = "#4CAF50" if self.mental_load < 40 else "#FF9800" if self.mental_load < 80 else "#F44336"

        self.canvas_load.coords(self.load_bar, 0, 0, fill_width, 40)
        self.canvas_load.itemconfig(self.load_bar, fill=color)
        self.root.after(200, self.update_load_visual)

    def next_step(self):
        if self.state == "IDLE":
            self.start_calibration()
        elif self.state == "READY":
            self.start_next_block()
        elif self.state == "FINISHED":
            self.export_csv()

    def start_calibration(self):
        self.state = "CALIBRATING"
        self.hide_entry()
        self.hide_rating()
        self.hide_chart()
        self.manager.start_calibration()
        self.label_title.config(text="CALIBRATION REPOS")
        self.label_task.config(
            text=(
                "Installez-vous confortablement.\n\n"
                "Restez immobile, silencieux, et respirez normalement."
            ),
            font=("Helvetica", 20, "bold"),
            fg=self.colors["text"],
        )
        self.btn_action.config(text="CALIBRATION...", state="disabled", bg=self.colors["blue"])
        self.start_timer(self.CALIBRATION_SECONDS)

    def start_next_block(self):
        self.block_index += 1
        if self.block_index >= len(self.block_plan):
            self.finish_protocol()
            return

        self.current_block = self.block_plan[self.block_index]
        condition = self.current_block["condition"]
        intensity = self.current_block["intensity"]
        duration = self.current_block["duration"]
        trial_id = self.block_index + 1

        self.state = "BLOCK"
        self.manager.set_phase(condition)
        self.manager.set_context(trial_id=trial_id, intensity=intensity, condition=condition)
        self.hide_rating()
        self.hide_chart()

        if condition == "HIGH":
            self.start_high_block()
        else:
            self.hide_entry()
            self.btn_action.config(text="BLOC EN COURS", state="disabled", bg=self.colors["blue"])
            if condition == "LOW":
                self.label_title.config(text=f"BLOC {trial_id} / {len(self.block_plan)} - LOW")
                self.label_task.config(
                    text=(
                        "+\n\n"
                        "Fixez le symbole central.\n"
                        "Ne memorisez rien, ne comptez rien, respirez normalement."
                    ),
                    font=("Helvetica", 28, "bold"),
                    fg=self.colors["text"],
                )
            else:
                self.label_title.config(text=f"BLOC {trial_id} / {len(self.block_plan)} - REST")
                self.label_task.config(
                    text=(
                        "REPOS\n\n"
                        "Relachez l'effort mental.\n"
                        "Gardez les capteurs immobiles."
                    ),
                    font=("Helvetica", 24, "bold"),
                    fg=self.colors["text"],
                )

        self.start_timer(duration)

    def start_high_block(self):
        self.high_total = 0
        self.high_correct = 0
        self.high_left = random.randint(700, 999)
        self.high_step = random.choice([7, 8, 9, 13, 17])
        self.new_high_problem()
        self.show_entry()
        self.btn_action.config(
            text="VALIDER",
            command=self.submit_high_answer,
            state="normal",
            bg=self.colors["accent"],
        )

    def new_high_problem(self):
        self.high_solution = self.high_left - self.high_step
        trial_id = self.block_index + 1
        self.label_title.config(text=f"BLOC {trial_id} / {len(self.block_plan)} - HIGH")
        self.label_task.config(
            text=(
                "CALCUL MENTAL CONTINU\n\n"
                f"{self.high_left} - {self.high_step} = ?\n\n"
                f"Score: {self.high_correct}/{self.high_total}"
            ),
            font=("Helvetica", 28, "bold"),
            fg=self.colors["accent"],
        )

    def submit_high_answer(self):
        if self.state != "BLOCK" or not self.current_block or self.current_block["condition"] != "HIGH":
            return

        raw_answer = self.entry_answer.get().strip()
        self.entry_answer.delete(0, tk.END)
        if raw_answer:
            self.high_total += 1
            try:
                if int(raw_answer) == self.high_solution:
                    self.high_correct += 1
                    self.high_left = self.high_solution
                else:
                    self.high_left = max(100, self.high_solution)
            except ValueError:
                self.high_left = max(100, self.high_solution)

        if self.high_left < 80:
            self.high_left = random.randint(700, 999)
            self.high_step = random.choice([7, 8, 9, 13, 17])

        self.new_high_problem()

    def finish_current_block(self):
        self.hide_entry()
        self.btn_action.config(text="EN ATTENTE", command=self.next_step, state="disabled", bg=self.colors["blue"])

        summary = self.make_block_summary()
        self.block_results.append(summary)

        self.state = "RATING"
        self.manager.set_phase("RATING")
        self.manager.set_context(condition="RATING")
        self.label_title.config(text="CHARGE PERCUE")
        self.label_task.config(
            text=(
                "Notez la charge mentale ressentie pendant le bloc.\n\n"
                "1 = tres faible, 7 = tres elevee"
            ),
            font=("Helvetica", 22, "bold"),
            fg=self.colors["text"],
        )
        self.show_rating()

    def make_block_summary(self):
        trial_id = self.block_index + 1
        condition = self.current_block["condition"]
        timeline_rows = [
            row for row in self.manager.feature_history_full
            if row.get("trial_id") == trial_id and row.get("condition") == condition
        ]

        def avg(key):
            values = []
            for row in timeline_rows:
                value = row.get(key)
                if isinstance(value, (int, float)) and value == value:
                    values.append(value)
            return sum(values) / len(values) if values else ""

        return {
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "trial_id": trial_id,
            "condition": condition,
            "intensity": self.current_block["intensity"],
            "duration_s": self.current_block["duration"],
            "subjective_load": "",
            "mean_mental_load": avg("mental_load"),
            "mean_heart_rate": avg("heart_rate"),
            "mean_rmssd": avg("rmssd"),
            "mean_eda_tonic": avg("eda_tonic"),
            "mean_eda_phasic": avg("eda_phasic"),
            "mean_resp_rate": avg("resp_rate"),
            "mean_score_rmssd_drop": avg("score_rmssd_drop"),
            "mean_score_resp_deviation": avg("score_resp_deviation"),
            "mean_score_heart_deviation": avg("score_heart_deviation"),
            "mean_score_eda_phasic_rise": avg("score_eda_phasic_rise"),
            "mean_score_eda_tonic_deviation": avg("score_eda_tonic_deviation"),
            "high_correct": self.high_correct if condition == "HIGH" else "",
            "high_total": self.high_total if condition == "HIGH" else "",
        }

    def submit_rating(self, value):
        if self.state != "RATING":
            return

        if self.block_results:
            self.block_results[-1]["subjective_load"] = value

        self.hide_rating()
        self.label_title.config(text="NOTE ENREGISTREE")
        self.label_task.config(text="Le prochain bloc va commencer.", font=("Helvetica", 22, "bold"))
        self.root.after(1200, self.start_next_block)

    def finish_protocol(self):
        self.state = "FINISHED"
        self.manager.set_phase("FINISHED")
        self.manager.set_context(condition="FINISHED")
        self.hide_entry()
        self.hide_rating()
        self.label_title.config(text="SESSION TERMINEE")
        self.label_task.config(
            text="Courbe de charge mentale par bloc",
            font=("Helvetica", 18, "bold"),
            fg=self.colors["success"],
        )
        self.show_chart()
        self.label_timer.config(text="")
        self.btn_action.config(
            text="EXPORTER LES DONNEES",
            command=self.export_csv,
            state="normal",
            bg=self.colors["success"],
        )
        self.btn_export.pack(pady=5)

    def show_entry(self):
        if not self.entry_answer.winfo_ismapped():
            self.entry_answer.pack(pady=15)
        self.entry_answer.delete(0, tk.END)
        self.entry_answer.focus_set()

    def hide_entry(self):
        if self.entry_answer.winfo_ismapped():
            self.entry_answer.pack_forget()

    def show_rating(self):
        if not self.rating_frame.winfo_ismapped():
            self.rating_frame.pack(pady=10)

    def hide_rating(self):
        if self.rating_frame.winfo_ismapped():
            self.rating_frame.pack_forget()

    def show_chart(self):
        if not self.chart_frame.winfo_ismapped():
            self.chart_frame.pack(fill="x", padx=10, pady=(0, 20))
        self.root.after(100, self.draw_load_chart)

    def hide_chart(self):
        if self.chart_frame.winfo_ismapped():
            self.chart_frame.pack_forget()

    def draw_load_chart(self):
        if not hasattr(self, "chart_canvas") or not self.chart_canvas.winfo_exists():
            return

        canvas = self.chart_canvas
        canvas.delete("all")

        rows = [
            row for row in self.manager.feature_history_full
            if row.get("condition") in ("REST", "LOW", "HIGH")
            and isinstance(row.get("mental_load"), (int, float))
        ]
        width = max(canvas.winfo_width(), 760)
        height = max(canvas.winfo_height(), 260)
        pad_left = 52
        pad_right = 18
        pad_top = 24
        pad_bottom = 42
        plot_w = width - pad_left - pad_right
        plot_h = height - pad_top - pad_bottom

        if len(rows) < 2:
            canvas.create_text(
                width / 2,
                height / 2,
                text="Pas assez de donnees pour tracer la courbe.",
                fill=self.colors["text"],
                font=("Helvetica", 14, "bold"),
            )
            return

        condition_colors = {
            "REST": "#20314F",
            "LOW": "#1D4D47",
            "HIGH": "#5A2531",
        }
        line_color = "#FFD166"
        axis_color = "#AEB7CC"
        grid_color = "#283856"

        max_load = max(40.0, min(100.0, max(row["mental_load"] for row in rows) * 1.15))

        def x_at(index):
            if len(rows) == 1:
                return pad_left
            return pad_left + (index / (len(rows) - 1)) * plot_w

        def y_at(load):
            return pad_top + plot_h - (max(0.0, min(load, max_load)) / max_load) * plot_h

        # Fonds colores par bloc/condition.
        start = 0
        for index in range(1, len(rows) + 1):
            is_end = index == len(rows)
            if is_end or rows[index].get("trial_id") != rows[start].get("trial_id"):
                end = index - 1
                condition = rows[start].get("condition")
                x1 = x_at(start)
                x2 = x_at(end)
                canvas.create_rectangle(
                    x1,
                    pad_top,
                    max(x2, x1 + 2),
                    pad_top + plot_h,
                    fill=condition_colors.get(condition, "#263247"),
                    outline="",
                )
                label_x = (x1 + x2) / 2
                if x2 - x1 > 34:
                    canvas.create_text(
                        label_x,
                        height - 18,
                        text=f"{rows[start].get('trial_id')} {condition}",
                        fill="#D9E2F2",
                        font=("Helvetica", 8, "bold"),
                    )
                start = index

        for pct in (0, 25, 50, 75, 100):
            value = max_load * pct / 100
            y = y_at(value)
            canvas.create_line(pad_left, y, pad_left + plot_w, y, fill=grid_color)
            canvas.create_text(
                pad_left - 10,
                y,
                text=f"{value:.0f}",
                fill=axis_color,
                font=("Helvetica", 8),
                anchor="e",
            )

        points = []
        for index, row in enumerate(rows):
            points.extend([x_at(index), y_at(row["mental_load"])])

        if len(points) >= 4:
            canvas.create_line(*points, fill=line_color, width=3, smooth=True)

        for index in range(0, len(rows), max(1, len(rows) // 80)):
            canvas.create_oval(
                x_at(index) - 2,
                y_at(rows[index]["mental_load"]) - 2,
                x_at(index) + 2,
                y_at(rows[index]["mental_load"]) + 2,
                fill=line_color,
                outline="",
            )

        canvas.create_rectangle(pad_left, pad_top, pad_left + plot_w, pad_top + plot_h, outline=axis_color)
        canvas.create_text(
            pad_left,
            12,
            text="Charge mentale estimee",
            fill=self.colors["text"],
            font=("Helvetica", 10, "bold"),
            anchor="w",
        )

        legend_x = width - 255
        for offset, (label, color) in enumerate(condition_colors.items()):
            x = legend_x + offset * 82
            canvas.create_rectangle(x, 9, x + 14, 21, fill=color, outline="")
            canvas.create_text(x + 20, 15, text=label, fill=self.colors["text"], font=("Helvetica", 9), anchor="w")

    def export_csv(self):
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_dir = Path("resultats") / f"session_{timestamp_str}"
        session_dir.mkdir(parents=True, exist_ok=True)
        summary_filename = session_dir / f"summary_{timestamp_str}.csv"
        timeline_filename = session_dir / f"timeline_{timestamp_str}.csv"

        summary_fields = [
            "timestamp", "trial_id", "condition", "intensity", "duration_s",
            "subjective_load", "mean_mental_load", "mean_heart_rate", "mean_rmssd",
            "mean_eda_tonic", "mean_eda_phasic", "mean_resp_rate",
            "mean_score_rmssd_drop", "mean_score_resp_deviation",
            "mean_score_heart_deviation", "mean_score_eda_phasic_rise",
            "mean_score_eda_tonic_deviation",
            "high_correct", "high_total",
        ]
        with open(summary_filename, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=summary_fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(self.block_results)

        timeline_rows = self.manager.feature_history_full
        timeline_fields = [
            "timestamp", "trial_id", "intensity", "condition", "phase",
            "mental_load", "quality", "eda_tonic", "eda_phasic",
            "heart_rate", "rmssd", "heart_source", "heart_peaks",
            "resp_rate", "resp_amplitude",
            "score_rmssd_drop", "score_resp_deviation",
            "score_heart_deviation", "score_eda_phasic_rise",
            "score_eda_tonic_deviation", "score_reference_source",
        ]
        with open(timeline_filename, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=timeline_fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(timeline_rows)

        self.btn_action.config(text=f"CSV GENERES: {session_dir}", state="disabled", bg=self.colors["success"])
        self.btn_export.config(text="CSV GENERES", state="disabled", bg=self.colors["success"])

    def on_closing(self):
        self.timer_running = False
        self.manager.stop_capture()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    game = CognitiveGame(root)
    root.mainloop()
