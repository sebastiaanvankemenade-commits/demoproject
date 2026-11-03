# AssemblyVision op de NVIDIA-computer (Windows)

> Draait de computer op Linux, gebruik dan `INSTALLATIE-LINUX.md`.

Voor de werkstation met de RTX PRO 6000. Reken op ±30 minuten, vooral voor het downloaden van modellen.

## 1. Installeren (eenmalig)

1. **Python 3.12 of nieuwer** van python.org. Vink bij installatie "Add python.exe to PATH" aan. De `py`-launcher komt standaard mee.
2. **Ollama voor Windows** van ollama.com. Het gebruikt de NVIDIA-kaart vanzelf; er is geen aparte CUDA-installatie nodig.
3. Optioneel: **Elgato Camera Hub**, om belichting en focus van de Facecams in te stellen.

## 2. De app neerzetten

1. Pak `AssemblyVision.zip` uit naar een map zonder bijzondere tekens, bijvoorbeeld `C:\AssemblyVision`.
2. Sluit beide Facecams aan, rechtstreeks op de computer en niet via een hub.

## 3. Modellen downloaden

Open PowerShell:

```powershell
ollama pull qwen3-vl:4b-instruct
ollama pull qwen3-vl:32b
```

`qwen3-vl:4b-instruct` is het model waarop alles gemeten is. `qwen3-vl:32b` is het grote model om mee te vergelijken. Controleer met `ollama list` dat de download gelukt is. Bestaat die naam niet meer, kies dan een ander groot Qwen3-VL-model van ollama.com/library.

## 4. Starten

```powershell
cd C:\AssemblyVision
Set-ExecutionPolicy -Scope Process Bypass
.\start.ps1
```

De eerste keer installeert het script de Python-pakketten; dat duurt een paar minuten. Open daarna http://127.0.0.1:8420.

Zonder camera's testen: `.\start.ps1 -TestBeelden`.

## 5. Controleren

- **Instellingen → Apparaat** moet de RTX PRO 6000 tonen met profiel **Krachtig**. Staat er iets anders, dan is `nvidia-smi` niet gevonden: herstart na de installatie van de NVIDIA-driver.
- **Camera's**: Windows nummert camera's in plaats van ze op serienummer te herkennen. Staan boven- en zijaanzicht verkeerd om, klik dan op "Wissel camera's". Na opnieuw inpluggen kan de volgorde weer wisselen.
- **Werkmat**: leg de geprinte mat neer; de werkgebieden komen vanzelf.
- **Model**: kies `qwen3-vl:32b` in de lijst en doe dezelfde dartpijl-proef als op de MacBook.

## Wat hier nog niet getest is

- De camera's via DirectShow op Windows. De OpenCV-cameralaag is alleen op de Mac met de echte Facecams getest.
- Het uitlezen van `nvidia-smi` op echte hardware; alleen met voorbeeldtekst getest.
- Snelheid en herkenning op deze machine: alles wat hierover gezegd is, is een verwachting.

Lukt iets niet, stuur dan de tekst uit het PowerShell-venster mee.
