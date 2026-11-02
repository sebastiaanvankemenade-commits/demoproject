# Voortgang AssemblyVision

> Stand: 2026-11-02. Bedoeld om zonder voorkennis verder te kunnen, ook in een nieuwe sessie.

De specificatie staat in `claude.md`. Dit document houdt bij wat daarvan bereikt is, wat we anders doen en wat er nog moet.

## Situatie

- Gebouwd en getest op de MacBook Air (M3, 24 GB). Eindmachine wordt een NVIDIA-computer met Windows en Linux; Linux is de eerste keuze, Windows de terugval.
- **De twee Elgato Facecams blijven op kantoor.** Elders is er geen camerabeeld. Alles wat echte camera's vereist, staat hieronder onder "Alleen op kantoor".
- Nog open: komt de NVIDIA-computer bij de werkplek of op afstand te staan? Dat bepaalt of de app via het netwerk bereikbaar moet zijn. Nu is hij alleen lokaal bereikbaar.

## Wat werkt

Starten met `./start.sh`, daarna http://127.0.0.1:8420. Tests: `cd backend && .venv/bin/python -m pytest` (54 groen).

- Workflow-engine, validatie van modelantwoorden, beeldcontrole op te donker of overbelicht beeld.
- Ollama-koppeling met modelkeuze uit wat er echt geïnstalleerd is.
- Camera's op USB-serienummer via AVFoundation (macOS), samen 1080p op 30 FPS.
- Dashboard met live beeld, checklist, observaties, activiteitenlog en bediening.
- Monitorlus met één analyse tegelijk. Getest op echt camerabeeld: 6 analyses, geen ongeldig antwoord, ±20 s per analyse.

Zonder camera's start de app gewoon en toont per camera "Camera niet verbonden". Dat is getest met nepcamera's, niet door echte camera's los te koppelen.

## Meetresultaten

Gegenereerde scènes, 18 metingen per model, MacBook Air. De ruwe data staat in `spike/results/`.

| | `qwen3-vl:4b-instruct` | `qwen3-vl:8b` |
|---|---|---|
| Geldige JSON | 18 | 15 |
| Status goed | 16 | 13 |
| Afgekapte antwoorden | 0 | 3 |
| Tijd, 1 camera | ±13 s | ±32 s |
| Tijd, 2 camera's | ±23 s | ±52 s |

- Geen van beide zei `completed` bij een niet-afgeronde stap, behalve bij een bijna zwart beeld waarin het blok wél goed lag. Daarom stopt de beeldcontrole zulke frames vóór het model.
- De `8b`-tijden zijn mogelijk te hoog: er liepen installaties en tests naast.
- Prompt en schema maakten het grootste verschil. `status` als laatste veld en gedefinieerde statussen brachten `4b` van 6 naar 18 geldige antwoorden. Verander die niet zonder opnieuw te meten.
- De Nederlandse uitvoer is alleen losjes gecontroleerd en de matrix is niet opnieuw gedraaid met die prompt. Het model antwoordt soms deels Engels.
- Het aantal beeldtokens bleef gelijk bij 512, 768 en 1024 px. Vermoedelijk schaalt het model elk beeld naar een vaste grootte; dat is niet bewezen.

## Keuzes die afwijken van de spec

| Spec | Keuze | Waarom |
|---|---|---|
| Analyse elke 3 s | Blijft instelbaar, werkelijk ±20 s | Haalbaar tempo op de Air; de app toont de echte interval |
| OpenCV voor camera's | AVFoundation op macOS | OpenCV opent op index en die volgorde wisselde tussen runs |
| Camera 5, 10, 15 of 24 FPS | Camera op 30 FPS, verwerking lager | Facecams bieden op de Mac alleen 30 en 60 FPS |
| `uncertain`-veld in modeluitvoer | Weggelaten | `status` drukt dat al uit; getest zonder dat veld |
| Geen uitsnede genoemd | Uitsnede van het werkgebied nodig | Sluitring is ±15–20 px in heel beeld, ±50 px met uitsnede |
| 4K | Geschrapt, 1080p | Niet nodig; camera 2 weigerde 4K in ffmpeg, oorzaak onbekend |
| Fasevolgorde met dashboard vóór inferentie | Eerst dunne keten | Echte inferentie is prioriteit 1 |

Toegevoegd: `requires_transition` per stap. De stap telt dan pas als hij eerst onafgerond is gezien.

## Volgende stappen zonder camera's

1. **Testbron met opgeslagen beelden.** Een backend naast `cameras/macos.py` die beelden uit een map speelt, duidelijk gelabeld als testbron en nooit als live beeld. Daarmee is de hele keten thuis te testen. De scènes komen uit `spike/make_scenes.py`.
2. **Simulatiemodus** (spec 18), door dezelfde engine, met zichtbare SIMULATIEMODUS.
3. **Werkinstructie-editor** (spec 13), met eigen opslag. De workflows staan nu vast in `default_workflows.py`.
4. **AI Playground** (spec 14), op opgeslagen beelden.
5. **Prestaties en Benchmark** (spec 16 en 17).
6. **Instellingen** (spec 5): afbeeldingsbreedte, modelparameters, opslag wissen.
7. **Uitsnede van het werkgebied** instelbaar per camera.
8. **Model verifiëren bij wisselen**: nu wordt een nieuw model niet eerst getest met een beeld, zoals de spec vraagt.
9. **Linux-cameralaag** voor de NVIDIA-machine. Let op: Elgato biedt Camera Hub alleen voor PC en Mac, dus belichting op Linux gaat via `v4l2-ctl`, ongetest.

## Alleen op kantoor (met camera's)

1. Workflow B met gekleurde blokken op gemarkeerde vakken, camera's op ±30–40 cm. **Dit is de belangrijkste open test:** er is nog nooit een stap op echt beeld afgevinkt.
2. Daarna Workflow A met bout en sluitring, met uitsnede.
3. Testbeelden opslaan van de echte opstelling, zodat die ook buiten kantoor bruikbaar zijn.
4. Camera loskoppelen tijdens gebruik, en van poort wisselen.
5. De drempels van de beeldcontrole toetsen aan echt beeld.
6. De eenmalige 13 FPS uit een screenshot nakijken. Met twee previews bleef het 30 FPS.

Nog door te klikken in de browser, kan ook zonder camera's: alle knoppen, en wisselen van model.

## Bekende valkuilen

- **Zscaler blokkeert `registry.npmjs.org`** op het kantoornetwerk. PyPI werkte wel. Frontend installeren met `npm install --offline`; `package.json` staat vast op versies uit de lokale cache. Zet TLS-controle niet uit en gebruik geen omweg.
- In zsh wordt `$variabele` niet gesplitst op spaties, en `pgrep -f` matcht ook de eigen shell.
- `PaddleOCR-VL` staat in de modellijst omdat Ollama het als vision-model meldt, maar het is een OCR-model en niet getest voor deze taak.
- De schijf van de Air zit op 97%; genoeg om te bouwen, krap voor nog meer modellen.
