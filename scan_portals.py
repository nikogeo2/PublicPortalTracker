"""
Denni "dump" JS portalu s verejnymi zakazkami.

Tenhle skript nedela zadne chytre parsovani ani filtrovani - to resi Claude
nasledne, kdyz si stahne vysledne .txt soubory (jsou to uz staticke,
server-rendered soubory, takze je jde normalne fetchnout). Ukolem skriptu
je jen: otevrit stranku v headless prohlizeci (Playwright), pockat, az se
vykresli JavaScript, a ulozit viditelny text tela stranky do souboru.

Pouziti (v GitHub Actions, viz .github/workflows/scan-portals.yml):
    python scan_portals.py

Lokalne (na vlastnim pocitaci, pokud by bylo potreba):
    pip install playwright
    playwright install chromium
    python scan_portals.py
"""

from __future__ import annotations

import datetime
import pathlib
import sys

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# Cil: portaly, ktere jsou cistokrevne JS aplikace a bez prohlizece z nich
# WebFetch/curl nedostane zadny pouzitelny obsah. U kazdeho je uvedena
# nejlepsi znama URL na seznam/vypis zakazek - u nekterych (Tendermarket,
# ISVZ, eVEZA) jde o odhad, protoze presnou strukturu webu nejde overit
# bez zivého prohlizece. Pokud dump vyjde prazdny nebo nesmyslny, uprav
# URL podle toho, co v prohlizeci skutecne uvidis.
TARGETS: dict[str, str] = {
    # Tyto tri fungovaly na prvni pokus - vraceji realny seznam zakazek:
    "nen": "https://nen.nipez.cz/verejne-zakazky",
    "eveza": "https://www.eveza.cz/verejne-zakazky",
    "e-zakazky": "https://www.e-zakazky.cz/verejne-zakazky",
    # ISVZ vyrazeno - je to spis statisticky/reportovaci nastroj (dashboardy,
    # open data), ne seznam otevrenych zakazek. NEN uz tuhle roli pokryva.
    #
    # Tyhle dve jeste nejsou spravne - prvni pokus selhal (404 / prazdny
    # obsah). Zkousime jine URL, ale muze byt potreba dalsi doladeni, az
    # uvidime, co skutecne vrati:
    "tenderarena": "https://tenderarena.cz/dodavatel",
    "tendermarket": "https://www.tendermarket.cz/verejne-zakazky",
}

OUTPUT_DIR = pathlib.Path("dumps")
MAX_CHARS = 60_000  # ať jsou soubory rozumně velké pro pozdější fetch/čtení


def dump_one(page, name: str, url: str) -> None:
    print(f"-> {name}: {url}")
    try:
        page.goto(url, wait_until="networkidle", timeout=45_000)
    except PlaywrightTimeoutError:
        # networkidle se nemusi nikdy dockat u stranek s pollingem/websockety
        # - zkusime aspon "domcontentloaded" a chvili pockame rucne.
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        except Exception as exc:  # noqa: BLE001
            (OUTPUT_DIR / f"{name}.txt").write_text(
                f"CHYBA pri nacitani {url}: {exc}", encoding="utf-8"
            )
            return

    # dej JS aplikaci chvili navic na dorenderovani seznamu
    page.wait_for_timeout(4000)

    try:
        text = page.inner_text("body")
    except Exception as exc:  # noqa: BLE001
        text = f"CHYBA pri cteni obsahu: {exc}"

    text = text.strip()
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "\n\n[...oříznuto...]"

    header = (
        f"Zdroj: {name}\n"
        f"URL: {url}\n"
        f"Staženo: {datetime.datetime.now(datetime.timezone.utc).isoformat()}\n"
        f"{'-' * 60}\n"
    )
    (OUTPUT_DIR / f"{name}.txt").write_text(header + text, encoding="utf-8")


def main() -> int:
    OUTPUT_DIR.mkdir(exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="cs-CZ",
        )
        page = context.new_page()

        had_error = False
        for name, url in TARGETS.items():
            try:
                dump_one(page, name, url)
            except Exception as exc:  # noqa: BLE001
                had_error = True
                print(f"   chyba u {name}: {exc}", file=sys.stderr)
                (OUTPUT_DIR / f"{name}.txt").write_text(
                    f"CHYBA: {exc}", encoding="utf-8"
                )

        browser.close()

    return 1 if had_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
