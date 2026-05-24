# Notes experimentales CogniCharge

## Diagnostic rapide

Les capteurs disponibles sont pertinents, mais ils ne mesurent pas directement la
"charge mentale". Ils mesurent des correlats physiologiques:

- EDA: tres utile pour l'activation/stress, mais lente et sensible au placement
  des electrodes.
- ECG: meilleur choix pour extraire la frequence cardiaque et la HRV/RMSSD.
- PPG: utile si l'ECG est difficile a poser, mais plus sensible aux mouvements.
- Respiration: utile, car stress et effort cognitif peuvent modifier le rythme.
- ACC: surtout utile pour detecter/rejeter les artefacts de mouvement.
- EMG: optionnel, utile si vous voulez mesurer la tension musculaire, pas
  prioritaire pour la charge cognitive.

Le probleme principal du code initial etait qu'il utilisait des amplitudes brutes
ou des ecarts-types ECG/PPG. Ces valeurs ne separent pas proprement low load et
high load, car elles dependent beaucoup du placement du capteur, du contact et du
bruit. Le code calcule maintenant des features plus interpretablees: EDA tonique,
EDA phasique, frequence cardiaque, RMSSD et respiration.

## Protocole recommande

1. Faire une baseline plus longue si possible: 60 a 120 s au repos au lieu de
   30 s, surtout pour l'EDA et la respiration.
2. Repeter plusieurs essais par condition: au moins 5 blocs low load et 5 blocs
   high load par sujet.
3. Randomiser l'ordre low/high pour eviter un effet fatigue ou apprentissage.
4. Garder des durees comparables entre conditions, sinon la difference mesuree
   peut venir du temps passe dans la tache.
5. Exporter les donnees et comparer par phase: MEMORIZE, READ, MATH, INPUT,
   RECALL. Ne pas comparer seulement le score final.
6. Ajouter une mesure subjective simple apres chaque bloc: effort percu de 1 a 7
   ou NASA-TLX court. C'est votre "ground truth" pratique.
7. Conserver les performances: rappel correct/faux, temps de reponse, calcul
   correct/faux. Une charge elevee devrait souvent alterer performance ou temps.

Pour faire apparaitre un contraste clair avec le materiel actuel, evitez de
comparer intensite 6 contre intensite 10. Comparez plutot:

- Low load: intensite 1 ou 2, lecture simple ou fixation, pas de calcul, 60 s.
- High load: intensite 9 ou 10, calcul mental continu ou n-back, 60 s.

La duree de 60 s aide beaucoup, car l'EDA et la respiration reagissent lentement.
Une tache de 10 s peut etre trop courte pour produire une difference stable.

## Protocole implemente dans l'interface

`CognitiveInterface.py` utilise maintenant un protocole par blocs:

- Calibration repos: 60 s.
- Blocs REST: 30 s.
- Blocs LOW: 60 s, fixation calme, pas de memorisation ni calcul.
- Blocs HIGH: 60 s, calcul mental continu par soustractions repetees.
- Apres chaque bloc: note subjective de charge mentale de 1 a 7.

L'ordre des blocs LOW/HIGH est randomise a chaque session, avec des blocs REST
intercales. Le fichier `summary_*.csv` donne une ligne par bloc, tandis que
`timeline_*.csv` donne les features physiologiques toutes les 0.5 s.

Le score courant est volontairement relatif: chaque sujet est compare a sa
propre calibration puis aux blocs REST recents. Cela le rend plus generalisable
que des seuils fixes en bpm ou en valeurs EDA brutes.

## Interpretation du CSV timeline

Le fichier `timeline_*.csv` contient maintenant:

- `phase`: etape experimentale au moment de la mesure.
- `condition`: `REST`, `LOW`, `HIGH`, `RATING` ou `FINISHED`.
- `trial_id`: numero du bloc.
- `intensity`: 0 pour REST, 2 pour LOW, 10 pour HIGH.
- `mental_load`: score 0-100 calcule par deviation au repos.
- `score_reference_source`: `calibration` au debut, puis `adaptive_rest` quand
  assez de donnees REST ont ete collectees.
- `score_rmssd_drop`: contribution de la baisse de HRV/RMSSD.
- `score_resp_deviation`: contribution d'une respiration differente du repos,
  plus rapide ou plus lente.
- `score_heart_deviation`: contribution d'une frequence cardiaque differente du
  repos.
- `score_eda_phasic_rise`: contribution de l'activite EDA rapide.
- `score_eda_tonic_deviation`: contribution faible de l'EDA tonique, car elle
  derive beaucoup pendant une session.
- `quality`: `ok` si les signaux principaux sont exploitables, sinon indique les
  features limitees.
- `eda_tonic`, `eda_phasic`: niveau lent et activite rapide EDA.
- `heart_rate`: frequence cardiaque estimee.
- `rmssd`: HRV court terme; elle baisse souvent avec stress/effort.
- `heart_source`: `ecg`, `ppg` ou `none`.
- `resp_rate`: frequence respiratoire estimee.

Si `quality` contient souvent `limited:cardiac`, le capteur cardiaque ou le
placement pose probleme. Si `heart_source` vaut souvent `ppg`, l'ECG n'est pas
exploitable et le PPG prend le relais.

## Point important sur l'EDA

Selon le montage, la valeur brute EDA peut augmenter ou diminuer quand la
conductance cutanee augmente. Si vous observez que l'EDA baisse clairement pendant
une tache stressante, mettez `self.eda_direction = -1` dans `MentalLoadManager.py`.

## Materiel a privilegier

Configuration conseillee pour une premiere version fiable:

- ECG ou PPG pour coeur, avec preference ECG pour la HRV.
- EDA pour activation/stress.
- Respiration si le capteur est stable.
- ACC 3 axes pour annoter ou rejeter les periodes avec mouvement.

Evitez d'ajouter EMG/ACC au score principal au debut. Utilisez-les d'abord comme
indicateurs de qualite ou d'artefacts, puis ajoutez-les seulement si les donnees
montrent une difference claire.
