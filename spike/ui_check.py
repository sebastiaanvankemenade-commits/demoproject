"""Click through the dashboard in headless Chrome. Needs the app running with --test-beelden.

Run from backend/ with its venv: .venv/bin/python ../spike/ui_check.py
"""
import base64
import os
import json
import subprocess
import sys
import tempfile
import time
import urllib.request

from websockets.sync.client import connect

APP = os.environ.get("ASSEMBLYVISION_URL", "http://127.0.0.1:8420")
PORT = 9333
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

HELPERS = """
window.byText = (text, tag='button') => [...document.querySelectorAll(tag)].find(e => e.textContent.trim().includes(text));
window.clickText = (text) => { const e = byText(text); if (!e || e.disabled) return false; e.click(); return true; };
window.setValue = (element, value) => {
  const proto = element.tagName === 'SELECT' ? HTMLSelectElement.prototype : element.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, 'value').set.call(element, value);
  element.dispatchEvent(new Event(element.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true }));
};
window.field = (label) => [...document.querySelectorAll('label')].find(l => l.textContent.trim().startsWith(label))?.querySelector('input,select,textarea');
"""


class Page:
    def __init__(self, url: str):
        self.socket = connect(url, max_size=None)
        self.id = 0

    def send(self, method: str, **params):
        self.id += 1
        self.socket.send(json.dumps({"id": self.id, "method": method, "params": params}))
        while True:
            message = json.loads(self.socket.recv())
            if message.get("id") == self.id:
                return message.get("result", {})

    def eval(self, expression: str):
        result = self.send("Runtime.evaluate", expression=expression, awaitPromise=True, returnByValue=True)
        if "exceptionDetails" in result:
            raise RuntimeError(result["exceptionDetails"])
        return result["result"].get("value")

    def wait(self, expression: str, timeout: float = 15) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.eval(expression):
                return True
            time.sleep(0.15)
        return False

    def text(self) -> str:
        return self.eval("document.body.innerText")

    def contains(self, needle: str, timeout: float = 15) -> bool:
        return self.wait(f"document.body.innerText.includes({json.dumps(needle)})", timeout)

    def click(self, text: str) -> bool:
        return bool(self.eval(f"clickText({json.dumps(text)})"))

    def drag(self, x1: float, y1: float, x2: float, y2: float) -> None:
        self.send("Input.dispatchMouseEvent", type="mousePressed", x=x1, y=y1, button="left", clickCount=1)
        self.send("Input.dispatchMouseEvent", type="mouseMoved", x=x2, y=y2, button="left", buttons=1)
        self.send("Input.dispatchMouseEvent", type="mouseReleased", x=x2, y=y2, button="left", clickCount=1)

    def screenshot(self, path: str) -> None:
        with open(path, "wb") as file:
            file.write(base64.b64decode(self.send("Page.captureScreenshot", format="png")["data"]))


def state() -> dict:
    with urllib.request.urlopen(f"{APP}/api/state") as response:
        return json.load(response)


results: list[tuple[bool, str]] = []


def check(ok, label: str) -> None:
    results.append((bool(ok), label))
    print(("OK   " if ok else "FOUT ") + label, flush=True)


def run(page: Page, shots: str) -> None:
    check(page.contains("TESTBEELDEN"), "testbeelden staan zichtbaar gelabeld")
    check(page.wait("document.querySelectorAll('img').length === 2"), "twee beelden zichtbaar")

    page.eval("setValue(field('Testscène'), '2_rood_op_a')")
    check(page.wait("field('Testscène').value === '2_rood_op_a'"), "testscène wisselt")

    box = page.eval("(() => { const r = document.querySelector('section').getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; })()")
    page.click_label = None
    page.eval("document.querySelector('[aria-label^=\"Werkgebied Bovenaanzicht\"]').click()")
    check(page.contains("Sleep een kader"), "werkgebied-modus opent")
    page.drag(box[0] + box[2] * 0.2, box[1] + box[3] * 0.3, box[0] + box[2] * 0.8, box[1] + box[3] * 0.8)
    check(page.click("Opslaan"), "werkgebied opslaan")
    time.sleep(0.5)
    roi = state()["cameras"][0]["roi"]
    check(roi and abs(roi["x"] - 0.2) < 0.03 and abs(roi["w"] - 0.6) < 0.03, f"werkgebied klopt met het gesleepte kader: {roi}")
    page.screenshot(f"{shots}/1-werkgebied.png")
    page.eval("document.querySelector('[aria-label^=\"Werkgebied Bovenaanzicht\"]').click()")
    page.contains("Sleep een kader")
    page.click("Verwijderen")
    time.sleep(0.4)
    check(state()["cameras"][0]["roi"] is None, "werkgebied verwijderen")

    page.eval("window.prompt = () => 'ui-check'")
    check(page.click("Testopname") and page.contains("Testopname 'ui-check' opgeslagen"), "testopname opslaan")
    page.click("Wissel camera's")
    check(page.contains("Camera's gewisseld"), "camera's wisselen")
    page.click("Wissel camera's")

    check(page.click("Handmatig bevestigen") and page.contains("Handmatig bevestigd om"), "handmatig bevestigen")
    check(page.contains("handmatig bevestigd."), "handmatige bevestiging staat apart in het log")
    check(page.click("Opnieuw beginnen") and page.wait("!document.body.innerText.includes('Handmatig bevestigd om')"), "opnieuw beginnen")

    check(page.click("Simulatie") and page.contains("SIMULATIEMODUS"), "simulatie aan, label zichtbaar")
    check(page.wait("byText('Start monitoring')?.disabled === true"), "start monitoring uit tijdens simulatie")
    page.click("Onvolledige observatie")
    check(page.contains("nog niet voltooid"), "simulatie: onvolledig")
    page.click("Geldige observatie")
    check(page.contains("Bevestiging 1 van 3"), "simulatie: eerste bevestiging")
    page.click("Onzekerheid")
    check(page.contains("Onvoldoende bewijs"), "simulatie: onzeker zet teller terug")
    for _ in range(3):
        page.click("Geldige observatie")
        time.sleep(0.15)
    check(page.contains("Gesimuleerd bevestigd om"), "simulatie: stap gesimuleerd bevestigd, niet als AI")
    for _ in range(3):
        page.click("Verkeerde handeling")
        time.sleep(0.15)
    check(page.contains("Afwijking gedetecteerd"), "simulatie: afwijking na 3 keer")
    page.screenshot(f"{shots}/2-simulatie.png")
    page.click("Simulatie uit")
    check(page.wait("!document.body.innerText.includes('SIMULATIEMODUS')"), "simulatie uit, label weg")

    page.eval("byText('Werkinstructies').click()")
    check(page.contains("Kies een werkinstructie"), "pagina werkinstructies")
    page.eval("document.querySelector('[aria-label=\"Nieuwe werkinstructie\"]').click()")
    page.wait("!!field('Naam werkinstructie')")
    page.eval("setValue(field('Naam werkinstructie'), 'UI-test')")
    page.click("Opslaan")
    check(page.contains("De invoer is ongeldig"), "lege stap wordt geweigerd")
    page.eval("setValue(field('Titel'), 'Testtitel')")
    page.eval("setValue(field('Instructie voor de operator'), 'Doe iets')")
    page.eval("setValue(field('Wat moet zichtbaar'), 'A block is visible')")
    page.click("Stap toevoegen")
    time.sleep(0.2)
    page.eval("document.querySelectorAll('[aria-label=\"Stap verwijderen\"]')[1].click()")
    page.click("Opslaan")
    check(page.contains("Opgeslagen."), "nieuwe werkinstructie opgeslagen")
    check(page.contains("UI-test"), "nieuwe werkinstructie in de lijst")
    page.screenshot(f"{shots}/3-editor.png")
    page.eval("window.confirm = () => true")
    page.eval("[...document.querySelectorAll('li')].find(l => l.textContent.includes('UI-test')).querySelector('[aria-label=\"Dupliceren\"]').click()")
    check(page.contains("UI-test (kopie)"), "dupliceren")
    for name in ("UI-test (kopie)", "UI-test"):
        page.eval(f"[...document.querySelectorAll('li')].find(l => l.textContent.includes({json.dumps(name)})).querySelector('[aria-label=\"Verwijderen\"]').click()")
        time.sleep(0.4)
    check(page.wait("!document.body.innerText.includes('UI-test')"), "verwijderen")

    page.eval("byText('AI Playground').click()")
    check(page.contains("geen invloed op de actieve werkinstructie"), "pagina playground")
    page.eval("setValue(document.querySelector('textarea'), 'Welke kleuren blokken zie je?')")
    page.eval("setValue(field('Beeld'), '1')")
    page.click("Uitvoeren")
    check(page.wait("document.querySelectorAll('article').length === 1", 90), "playground geeft antwoord van het echte model")
    print("     antwoord:", page.eval("document.querySelector('article').innerText")[:160].replace("\n", " "), flush=True)
    page.screenshot(f"{shots}/4-playground.png")
    check(state()["workflow"]["steps"][0]["confirmations"] == 0, "playground raakt de werkinstructie niet")

    page.eval("byText('Dashboard').click()")
    page.wait("!!field('AI-model')")
    page.eval("setValue(field('AI-model'), 'qwen3-vl:8b')")
    check(page.contains("laden en controleren"), "modelwissel toont laden")
    check(page.contains("AI-model gewijzigd naar qwen3-vl:8b", 120), "modelwissel naar 8b lukt zonder herstart")
    page.eval("setValue(field('AI-model'), 'qwen3-vl:4b-instruct')")
    check(page.contains("AI-model gewijzigd naar qwen3-vl:4b-instruct", 120), "terug naar 4b")

    page.eval("byText('Prestaties').click()")
    check(page.contains("Duur per analyse"), "pagina prestaties")
    check(page.contains("Geheugen van de app"), "systeemmetingen zichtbaar")
    check(page.contains("geen betrouwbare meting"), "geen verzonnen GPU-cijfers")
    page.screenshot(f"{shots}/5-prestaties.png")

    page.eval("byText('Instellingen').click()")
    check(page.contains("Geïnstalleerde vision-modellen"), "pagina instellingen")
    page.eval("setValue(field('Beeldbreedte naar het model'), '512')")
    page.click("Opslaan")
    check(page.contains("Opgeslagen."), "instelling opslaan")
    time.sleep(0.5)
    check(state()["settings"]["inference"]["image_width"] == 512, "beeldbreedte komt aan in de backend")
    page.eval("setValue(field('Time-out'), '5')")
    page.click("Opslaan")
    check(page.contains("De invoer is ongeldig", 3) or page.contains("Ongeldige instelling", 3), "ongeldige time-out wordt geweigerd")
    page.eval("window.confirm = () => true")
    page.click("Voorkeuren terugzetten")
    check(page.contains("Voorkeuren teruggezet."), "voorkeuren terugzetten")
    time.sleep(0.5)
    check(state()["settings"]["inference"]["image_width"] == 768, "beeldbreedte weer standaard")

    check(page.contains("Apple M3"), "apparaat wordt herkend")
    check(page.contains("Automatisch (Licht)"), "MacBook krijgt automatisch Licht")
    page.eval("setValue(field('Profiel'), 'power')")
    check(page.wait("field('Beeldbreedte naar het model').value === '1024'"), "profiel Krachtig zet de beeldbreedte")
    check(state()["settings"]["boxes_all_cameras"] and state()["settings"]["interval_s"] == 1, "Krachtig: vakken op alle camera's, interval 1 s")
    page.eval("setValue(field('Profiel'), 'auto')")
    check(page.wait("field('Beeldbreedte naar het model').value === '768'"), "terug naar Automatisch geeft Licht")
    check(state()["device"]["model_limit_gb"] == 12.0, "grootste model op de Air is 12 GB")
    page.screenshot(f"{shots}/6-instellingen.png")
    with urllib.request.urlopen(f"{APP}/api/data/events.csv") as response:
        check(b"tijdstip" in response.read(), "activiteit exporteren als CSV")


def main(shots: str) -> None:
    profile = tempfile.mkdtemp()
    chrome = subprocess.Popen(
        [CHROME, "--headless=new", f"--remote-debugging-port={PORT}", f"--user-data-dir={profile}", "--window-size=1512,900", "about:blank"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(40):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json") as response:
                    target = next(t for t in json.load(response) if t["type"] == "page")
                break
            except (OSError, StopIteration):
                time.sleep(0.25)
        page = Page(target["webSocketDebuggerUrl"])
        page.send("Page.enable")
        page.send("Page.addScriptToEvaluateOnNewDocument", source=HELPERS)
        page.send("Page.navigate", url=APP)
        page.wait("!!document.querySelector('header')")
        run(page, shots)
    finally:
        chrome.terminate()
    failed = [label for ok, label in results if not ok]
    print(f"\n{len(results) - len(failed)} van {len(results)} geslaagd")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main(sys.argv[1])
