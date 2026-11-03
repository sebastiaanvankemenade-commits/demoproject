# AssemblyVision

Lokale monitoring van fysieke werkinstructies met twee camera's en een lokaal vision-model via Ollama. Beelden en resultaten blijven op deze machine. De volledige specificatie staat in `claude.md`.

## Starten

```sh
./start.sh
```

Open daarna http://127.0.0.1:8420. Stoppen doe je met Ctrl+C in dat terminalvenster.

Vereist: Python 3.11+, Node 24, en Ollama met minstens één vision-model (`qwen3-vl:4b-instruct` heeft de voorkeur). macOS vraagt bij de eerste keer om camera-toegang.

Op een netwerk dat `registry.npmjs.org` blokkeert, installeer je de frontend vanuit de lokale cache met `cd frontend && npm install --offline`. De versies in `package.json` zijn daarom vastgezet op wat in de cache van deze Mac stond.

## Status

| Onderdeel | Status |
|---|---|
| Workflow-engine, validatie, beeldcontrole | Gebouwd, unit-tests groen |
| Ollama-koppeling, modelkeuze uit geïnstalleerde modellen | Gebouwd, getest met echt model. Modelwissel nog niet in de browser doorgeklikt |
| Camera's op serienummer (macOS) | Gebouwd, getest met twee Facecams. Poortwissel en loskoppelen niet getest |
| Dashboard met live beeld, checklist, observaties, log | Gebouwd, in de browser gecontroleerd. Knoppen nog niet doorgeklikt |
| Workflows A en B | Aanwezig, nog nooit op echte onderdelen getest |
| Werkinstructie-editor, AI Playground, Prestaties, Instellingen, Simulatie | Gebouwd, getest zonder echte camera's |
| Vakken van het model, draaibewegingen tellen | Gebouwd, getest op gegenereerde beelden |
| Benchmark | Nog niet gebouwd |
| Linux/Windows-cameralaag | Nog niet gebouwd |

## Bekende beperkingen

- Op de MacBook Air duurt een analyse met twee camera's ±20 s, dus een stap met 3 bevestigingen duurt ±1 minuut.
- De camera's bieden alleen 30 en 60 FPS. Lagere waarden uit de spec moeten softwarematig.
- Een vision-model kan geen aanhaalmoment of mechanische veiligheid vaststellen. Een voltooide stap betekent alleen dat de toestand zichtbaar klopt.
- Het model antwoordt soms deels in het Engels. Beslissingen hangen daar niet van af.

## Tests

```sh
cd backend && .venv/bin/python -m pytest
```

`spike/` bevat de metingen en losse controles die aan de ontwerpkeuzes vooraf gingen.
