# AssemblyVision op de NVIDIA-computer (Linux)

Voor de werkstation met de RTX PRO 6000. Geschreven voor Ubuntu of Debian; op een andere distributie heten de pakketten soms anders. Reken op ±30 minuten, vooral voor het downloaden van modellen.

## 1. Controleren (eenmalig)

Open een terminal:

```bash
nvidia-smi
```

Dit moet de RTX PRO 6000 tonen. Geeft het een fout, installeer dan eerst de NVIDIA-driver (Ubuntu: `sudo ubuntu-drivers install`, daarna herstarten).

## 2. Installeren (eenmalig)

```bash
sudo apt update
sudo apt install -y python3 python3-venv unzip v4l-utils
curl -fsSL https://ollama.com/install.sh | sh
sudo usermod -aG video $USER
```

- Het Ollama-script installeert Ollama als dienst en gebruikt de NVIDIA-kaart vanzelf.
- De groep `video` geeft toegang tot de camera's. **Log daarna één keer uit en weer in.**

## 3. De app neerzetten

```bash
cd ~
unzip ~/Downloads/AssemblyVision.zip
cd "Visual work tracking"
chmod +x start.sh
```

Sluit beide Facecams rechtstreeks op de computer aan, niet via een hub. Controleer met:

```bash
ls /dev/v4l/by-id/
```

Daar moeten twee regels met `Elgato_Facecam_4K` en `video-index0` staan, elk met een eigen serienummer.

## 4. Modellen downloaden

```bash
ollama pull qwen3-vl:4b-instruct
ollama pull qwen3-vl:32b
ollama list
```

`qwen3-vl:4b-instruct` is het model waarop alles gemeten is. `qwen3-vl:32b` is het grote model om mee te vergelijken. Bestaat die naam niet meer, kies dan een ander groot Qwen3-VL-model van ollama.com/library.

## 5. Starten

```bash
./start.sh
```

De eerste keer installeert het script de Python-pakketten; dat duurt een paar minuten. Open daarna http://127.0.0.1:8420.

Zonder camera's testen: `./start.sh --test-beelden`.

## 6. Controleren in de app

- **Instellingen → Apparaat** moet de RTX PRO 6000 tonen met profiel **Krachtig**.
- **Camera's**: worden op serienummer herkend, net als op de MacBook. Staan boven- en zijaanzicht verkeerd om, klik dan één keer op "Wissel camera's"; dat blijft daarna bewaard.
- **Werkmat**: leg de geprinte mat neer; de werkgebieden komen vanzelf.
- **Model**: kies `qwen3-vl:32b` en doe dezelfde dartpijl-proef als op de MacBook.

## Instellingen van de camera

Elgato Camera Hub bestaat niet voor Linux. Belichting en focus gaan via `v4l2-ctl`, bijvoorbeeld:

```bash
v4l2-ctl -d /dev/v4l/by-id/<naam>-video-index0 --list-ctrls
```

Dat is niet getest.

## Wat hier nog niet getest is

- De camera's op Linux. De cameralaag is met de echte Facecams getest op de Mac, en de Linux-namen alleen met voorbeelddata.
- Het uitlezen van `nvidia-smi` op echte hardware; alleen met voorbeeldtekst getest.
- Snelheid en herkenning op deze machine: alles wat hierover gezegd is, is een verwachting.

Lukt iets niet, stuur dan de tekst uit de terminal mee.
