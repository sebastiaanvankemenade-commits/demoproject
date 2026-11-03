# Voortgang AssemblyVision

> Stand: 2026-11-02. Bedoeld om zonder voorkennis verder te kunnen, ook in een nieuwe sessie.

De specificatie staat in `claude.md`. Dit document houdt bij wat daarvan bereikt is, wat we anders doen en wat er nog moet.

## Laatste update: klaar voor de NVIDIA-computer (Linux, Windows als terugval)

- `cameras/opencv.py`: cameralaag voor Windows (DirectShow, camera's op nummer) en Linux (V4L2, `/dev/v4l/by-id` met serienummer). MJPEG op 1080p, 3 s opwarmtijd. Getest met de echte Facecams via OpenCV op de Mac (1080p, ±29 FPS); DirectShow op Windows niet getest.
- `start.ps1` voor Windows en `docs/INSTALLATIE-WINDOWS.md`. Een zip met gebouwde frontend (zonder instellingen, activiteit en beelden) staat in Downloads, omdat npm op kantoor geblokkeerd wordt.
- De machine draait waarschijnlijk Linux. `start.sh` is nu bash in plaats van zsh, werkt op macOS en Linux en heeft geen npm nodig als de frontend al gebouwd is. Handleiding: `docs/INSTALLATIE-LINUX.md`; voor Windows `docs/INSTALLATIE-WINDOWS.md` en `start.ps1`.
- Dartpijl op de Air: hetzelfde beeld gaf de ene keer "voltooid", de andere keer "niet voltooid", ook bij een strakke uitsnede. `4b` is te klein voor deze verbinding. Op de NVIDIA-computer `qwen3-vl:32b` proberen.
- 191 backend-tests groen. Niet gecommit.

## Eerdere update: voordoen (werkinstructie maken uit een voorbeeld)

Stand: gebouwd, 185 backend-tests groen; **nog niet als geheel getest met het echte model** (de proef met de clip werd afgebroken toen de Air vol liep). Niet gecommit.

- Dashboard → Voordoen: naam en optioneel de onderdeelnamen ("barrel, shaft, flight"). De app legt de beginsituatie vast.
- `demonstration.py`: beweging in het werkgebied start een stap, ±2,5 s stilte sluit hem af (stappen automatisch herkennen, uit te zetten). Zelf een stap afsluiten met notitie kan ook; notities zijn achteraf per stap aan te vullen.
- Per stap een filmstrip: begin, de momenten met de meeste beweging, eind. Licht: 4 beelden, Krachtig: 8. Het model beschrijft wat de handen deden en schrijft een criterium over het eindbeeld. De beelden blijven in het geheugen en worden daarna weggegooid.
- Resultaat wordt een nieuwe, niet actieve werkinstructie die in de editor opent met de melding om elke stap te controleren. Een stap die niet lukt blijft leeg met "Vul zelf in", er wordt niets verzonnen.
- Eerste versie (twee foto's, prompt over "wat ligt waar") gaf op de echte dartpijl onzin: Engels, een verzonnen dartboard, de geprinte vakken als onderdelen. Daarna: prompt over vastmaken/draaien/verwijderen, matmarkeringen expliciet uitgesloten, Nederlandse veldnamen. Op gegenereerde scènes zonder notities: van 2 van 6 Nederlandse titels naar 3 van 3, criteria 3 van 3 goed beoordeeld. Op de dartpijl nog niet opnieuw getest.
- **Geheugen:** 8 beelden vroegen een grotere contextlengte; Ollama laadde het model daardoor met ±11 GB en de Air schreef 22 GB naar swap, waarna de schijf vol liep. Daarom op Licht maximaal 4 beelden binnen 8192 tokens. De schijf van de Air is bijna vol (±10 GB vrij); dat maakt swap krap.
- **Eerste echte proef (dartpijl, 2026-11-03):** de gemaakte stappen waren bruikbaar ("The shaft is attached to the barrel", "The flight is attached to the shaft"), plus een dubbele stap door een extra handmatige markering. Afvinken lukte niet: (1) ruis in de markerherkenning verschoof het werkgebied elke 5 s een fractie en wiste zo steeds de bevestigingen; opgelost met 2% tolerantie. (2) Drie bevestigingen bij ±23 s per analyse betekent ±70 s stilliggen per stap. (3) Het model zag een complete dart en zei toch "shaft niet vast aan barrel": kleine onderdelen op een hele A4 in beeld.
- Testclip `voordoen_blokken` (`spike/demo_clip.py`) en `spike/demo_film_check.py` voor een proef tegen een testserver.

## Eerdere update: werkmat

Voor een opstelling die vaak wordt op- en afgebouwd (168 backend-tests, `ui_check.py` 48 van 48, `overlay_check.py` 27 van 27; niet gecommit).

- `workmat.py`: printbare werkmat (Instellingen → Werkmat downloaden) met vier ArUco-markers (DICT_4X4_50, id 0–3) en de vakken A, B en C. De printschaal maakt niet uit.
- Elke camera zoekt de mat elke ±5 s (±3 ms per beeld) en zet het werkgebied om de mat. Er hoeft niets getekend of gekalibreerd te worden. Drie van de vier markers is genoeg, zodat een hand op één hoek niets uitmaakt.
- Het telgebied wordt bewaard in matcoördinaten en verhuist mee bij opnieuw opbouwen. Gebieden buiten de mat worden afgekapt tot de mat.
- Na 3 keer niet gevonden (±15 s) verschijnt de melding "Werkmat niet in beeld"; het laatste werkgebied blijft staan. Zonder mat valt de app terug op de kalibratie met het referentiebeeld.
- Tekenen van een werkgebied staat uit zolang de mat het bepaalt. Uit te zetten onder Instellingen.
- De testmodus heeft nu een eigen activiteitenbestand (`events-test.sqlite`). Eerder kwamen testruns in de echte activiteit terecht.
- Getest op gegenereerde beelden: twee opbouwen met verschillende camerastanden, een afgedekte marker, geen mat. Nog niet met een geprinte mat op echte camera's.

## Eerdere update: kalibratie

`calibration.py` merkt dat een camera is verschoven sinds de gebieden zijn getekend (157 backend-tests, `ui_check.py` 48 van 48, `overlay_check.py` 19 van 19; niet gecommit).

- Een werkgebied of telgebied tekenen bewaart automatisch een referentiebeeld van die camera (`backend/data/calibration/`). Met het vizier-icoon op een camera ververs je de referentie zonder de gebieden te veranderen.
- Bij het starten van de monitoring en ±elke 30 s vergelijkt de app het live beeld met de referentie: ORB-kenmerken en RANSAC, zonder het model.
- Onder 1% verschuiving: niets. Tussen 1% en 20%: werkgebied en telgebied schuiven mee, de log meldt het en de lopende bevestigingen vervallen. Daarboven, of als het beeld niet te herkennen is: waarschuwing op die camera, de gebieden blijven staan. De monitoring loopt in dat geval wel door.
- Correcties gaan altijd uit van de gebieden zoals ze op de referentie getekend zijn, dus kleine fouten stapelen niet op.
- Met het lagen-icoon ligt het referentiebeeld half doorzichtig over het live beeld, om de camera fysiek terug te zetten.
- Getest met verschoven en gedraaide testbeelden (5,5% verschuiving werd herkend, het werkgebied lag daarna op ±1% van de verwachte plek), en met onderdelen en een hand in beeld. Nog niet op echte camera's: belichting, autofocus en een rommelig werkvlak kunnen anders uitpakken. Een zwakke plek: verschuift alleen het werkvlak of de mal, en niet de camera, dan ziet de app dat ook als camerabeweging.

## Eerdere update: apparaatprofielen

`device_profile.py` herkent de hardware bij het starten (`nvidia-smi`, of chip en geheugen op de Mac) en kiest een profiel. Handmatig te overschrijven onder Instellingen, blijft bewaard (145 backend-tests, `ui_check.py` 48 van 48, `overlay_check.py` 11 van 11; niet gecommit).

| | Licht | Krachtig |
|---|---|---|
| Automatisch bij | Mac, onbekende hardware, GPU onder 16 GB VRAM | NVIDIA met 16 GB VRAM of meer |
| Grootste model | Maximaal 12 GB, op de Mac 50% van het geheugen | 85% van het VRAM (RTX PRO 6000: ±82 GB) |
| Beeldbreedte | 768 px | 1024 px |
| Minimale interval | 3 s | 1 s |
| Vakken per ronde | Eén camera, om en om | Alle camera's |

- Een profiel zet startwaarden, één keer per wijziging. Wat je daarna zelf aanpast blijft staan.
- Het profiel kiest nooit zelf een groter model: `8b` scoorde hier lager dan `4b`. Grotere modellen zijn een keuze in de lijst. Ze moeten eerst geïnstalleerd zijn met `ollama pull`.
- Een te groot model staat in de lijst als "(te groot)" en is niet te kiezen. De server weigert het ook.
- `nvidia-smi`-uitvoer is alleen getest met voorbeeldtekst, nooit op echte NVIDIA-hardware. De Krachtig-waarden zijn inschattingen en niet gemeten. De grenzen van 50% en 85% zijn vuistregels, en de bestandsgrootte is een benadering van wat een model in het geheugen gebruikt.

## Eerdere update: vakken en draaibewegingen tellen

Bijgebouwd (129 backend-tests groen, `ui_check.py` 42 van 42, `overlay_check.py` 11 van 11; niet gecommit):

- **Vakken van het model.** Na elke analyse een aparte aanvraag voor één camera, om en om (`InferenceService.detect`). De gemeten statusprompt en het schema zijn niet veranderd, en een fout bij de vakken raakt het besluit niet. Vakken horen bij de actieve stap en verdwijnen bij een nieuwe stap of na stoppen. Uit te zetten met "Vakken tonen".
- **Kosten vakken:** ±11 s per aanvraag. Werkelijke interval op de Air ging van ±20 naar ±32 s, dus een stap wordt ook trager bevestigd.
- **Draaibewegingen tellen.** `motion_counter.py` werkt met optische stroming op ±15 FPS, los van het model: een analyse duurt ±20 s en een draai ±1 s, dus het model kan dit niet zien gebeuren. Per stap in te stellen (`expected_turns`) in de editor onder Geavanceerd. Telgebied tekenen met het draai-icoon op een camera. Nieuwe werkinstructie: Schroef aandraaien.
- De teller telt heen-en-weerbewegingen van wat in het telgebied beweegt, dus de hand. Hij bewijst niet hoe ver de schroef is ingedraaid. De telling wordt vastgelegd bij de stap maar **blokkeert de stap niet**, tot de teller op echt beeld is gemeten.
- De testbron speelt nu ook clips af (`<scene>_top.mp4`). `spike/turn_check.py` haalt een eigen film door de teller.

Vakken gemeten met `spike/box_step_check.py`: `4b`, gegenereerde scènes, per stap, 28 metingen per variant.

| Variant | Aanwezig blok gevonden | Vak bij afwezig blok | Fout vak |
|---|---|---|---|
| Met "position A" in de vraag | 16/16 | 2/12 | 0 |
| Zonder positie, Nederlandse labels (gekozen) | 16/16 | 0/12 | 0 |
| Zonder positie, Engelse labels | 16/16 | 0/12 | 0 |

Teller getest op gegenereerde clips: 2, 3, 6 en 10 bewegingen exact; 0,5 tot 3 keer per seconde; ±11° tot ±69°; 8 tot 30 FPS; met ruis. Stilstaand beeld, ruis, flikkerend licht en een hand die alleen langskomt geven 0. In de app tijdens analyses: 20 geteld tegen ±20 verwacht.

Bekende grenzen van de teller:
- Eén losse beweging telt niet, omdat die lijkt op een hand die in en uit beeld gaat. Hij telt pas mee als er binnen 3 s een tweede volgt.
- Langzamer dan ongeveer één beweging per 2 s telt niet (0,3 per seconde gaf 0).
- Continu in één richting draaien telt niet: er is geen heen-en-weer.
- Drempels zijn afgesteld op getekende clips, **nog nooit op echte handen**.
- De vakken zijn nog niet op echte onderdelen gemeten. Ze horen bij het beeld van de genoemde tijd, niet bij het live beeld: beweegt er iets, dan loopt het vak achter.

## Eerdere update: testbron, simulatie, Playground, editor

Bijgebouwd en getest (72 backend-tests groen, nog niet gecommit):

- `./start.sh --test-beelden [map]` speelt opgeslagen beelden af, zichtbaar gelabeld als TESTBEELDEN.
- Werkgebied tekenen per camera, knop Testopname (bewaart in `backend/data/snapshots/`, afspeelbaar als testscène).
- Model wordt pas actief na een geslaagde beeldaanvraag; bij een fout blijft het oude model actief.
- Simulatiemodus, AI Playground met vergelijking van twee modellen, werkinstructie-editor met import en export.

Getest zonder camera's:

- `spike/ui_check.py` klikte 32 van 32 controles goed door in headless Chrome. Daarna zijn twee kleine fouten gefixt (testbron wisselde boven- en zijaanzicht, tekst "1 stappen"); die fixes zijn wel door de tests maar niet opnieuw in de browser bekeken.
- `spike/live_workflow.py` draaide Workflow B met het echte model op gegenereerde scènes: 17 analyses, 0 ongeldig, ±19 s met twee beelden, alle 3 de stappen door AI bevestigd. Een blauw blok op de foute positie is 4 keer op rij afgekeurd.
- Bekende herkenningsfout: de Playground zag "twee witte blokken" waar lege vakken stonden.
- Eén analyse duurde 56 s tegenover ±19 s gemiddeld; oorzaak niet onderzocht.

Daarna toegevoegd (94 backend-tests groen, `ui_check.py` 42 van 42; alles nog niet gecommit):

- Live afwijkingen op vooraf benoemde fouten, per stap instelbaar in de editor. Stappen zonder benoemde afwijkingen houden het gemeten schema.
- Prestaties (mediaan, P95, overgeslagen analyses, drie grafieken, app-geheugen) en Instellingen (AI-parameters, modelinformatie, data wissen en exporteren). De instelling beeldbreedte werd eerder niet gebruikt en is nu aangesloten.
- De FPS-grafiek kreeg daarna nog een fix voor overlappende labels; die is getest en gebouwd, maar niet opnieuw bekeken.

Afwijkingsregel gemeten met `spike/deviation_check.py`, 5 keer per geval, twee beelden, `4b`, gegenereerde scènes (`spike/results/deviation.jsonl`):

| Geval | Oude regel | Nieuwe regel |
|---|---|---|
| Onderdeel nog niet geplaatst, vals alarm (15 metingen) | 12 | 0 |
| Onderdeel op verkeerde positie, herkend (10 metingen) | 10 | 10 |
| Blauw in plaats van rood op A, herkend (5 metingen) | 0 | 0 |

Geen enkele meting gaf `completed`. Het laatste geval is een gat: een verkeerd onderdeel op de juiste plek blijft "nog niet voltooid" en wordt geen afwijking. De stap wordt wel terecht niet goedgekeurd. Een Workflow B-run door de hele keten is alleen gedaan met de oude regel; met de nieuwe regel is alleen `deviation_check.py` gedraaid.

Nog niet gebouwd: Benchmark, Linux-cameralaag. Workflows en werkgebieden staan in `backend/data/`, dat niet in git zit.

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

1. **Benchmark** (spec 17).
2. **Linux-cameralaag** voor de NVIDIA-machine. Let op: Elgato biedt Camera Hub alleen voor PC en Mac, dus belichting op Linux gaat via `v4l2-ctl`, ongetest.

## Alleen op kantoor (met camera's)

1. Workflow B met gekleurde blokken op gemarkeerde vakken, camera's op ±30–40 cm. **Dit is de belangrijkste open test:** er is nog nooit een stap op echt beeld afgevinkt.
2. Daarna Workflow A met bout en sluitring, met uitsnede.
3. Testbeelden opslaan van de echte opstelling, zodat die ook buiten kantoor bruikbaar zijn.
4. Camera loskoppelen tijdens gebruik, en van poort wisselen.
5. De drempels van de beeldcontrole toetsen aan echt beeld.
6. De eenmalige 13 FPS uit een screenshot nakijken. Met twee previews bleef het 30 FPS.
7. Teller op echte handen: werkinstructie Schroef aandraaien, telgebied om schroef en hand, zelf meetellen en vergelijken. Een telefoonfilmpje kan ook: `spike/turn_check.py`.
8. Vakken op echte onderdelen bekijken: staan ze goed, en tekent het model niets bij een leeg werkvlak?
11. Voordoen met de dartpijl: onderdeelnamen opgeven, per stap een korte notitie, kijken of de stappen automatisch herkend worden en of de instructies kloppen.
10. Werkmat printen, onder het werk leggen; daarna opstelling afbreken en anders opbouwen en kijken of beide camera's de mat vinden. Let op: lukt het bij het zijaanzicht, dat bijna vlak over de tafel kijkt?
9. Kalibratie: werkgebied tekenen, camera een paar cm verzetten, kijken of het werkgebied meeschuift.

Nog door te klikken in de browser, kan ook zonder camera's: alle knoppen, en wisselen van model.

## Bekende valkuilen

- **Zscaler blokkeert `registry.npmjs.org`** op het kantoornetwerk. PyPI werkte wel. Frontend installeren met `npm install --offline`; `package.json` staat vast op versies uit de lokale cache. Zet TLS-controle niet uit en gebruik geen omweg.
- In zsh wordt `$variabele` niet gesplitst op spaties, en `pgrep -f` matcht ook de eigen shell.
- `PaddleOCR-VL` staat in de modellijst omdat Ollama het als vision-model meldt, maar het is een OCR-model en niet getest voor deze taak.
- De schijf van de Air zit op 97%; genoeg om te bouwen, krap voor nog meer modellen.
