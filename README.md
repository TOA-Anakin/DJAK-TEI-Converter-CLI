# DJAK TEI Converter CLI

Tento repozitář obsahuje nástroje pro převod textů z formátu ODT (OpenDocument Text) do formátu TEI P5 XML pro projekt *J. A. Comenius Opera Omnia* (DJAK).

Řešení je postaveno na technologii **Docker**, což zajišťuje, že konverze proběhne naprosto stejně na jakémkoliv počítači (Windows, Linux, macOS) bez nutnosti složité instalace Pythonu a závislostí.

## 1. Požadavky (Prerequisites)

Před použitím je nutné mít nainstalovaný **Docker**:
*   **Windows / Mac:** Nainstalujte [Docker Desktop](https://www.docker.com/products/docker-desktop/).
*   **Linux:** Nainstalujte Docker Engine a Docker Compose plugin.

## 2. Instalace a Příprava

1.  **Stáhněte tento projekt** (jako ZIP soubor z GitHubu nebo pomocí `git clone`) a rozbalte jej.
2.  **Otevřete terminál** (Příkazový řádek / PowerShell / Bash) uvnitř složky projektu.
3.  **Nastavte prostředí:**
    Vytvořte konfigurační soubor zkopírováním šablony. Spusťte tento příkaz:
    ```bash
    cp .docker/local/.env.example .docker/local/.env
    ```
4.  **Sestavte aplikaci:**
    Tento krok stáhne potřebné nástroje a připraví konvertor. Spouští se pouze poprvé.
    ```bash
    ./env.sh local build
    ```

## 3. Pracovní postup (Workflow)

Proces se skládá ze dvou kroků: extrakce XML z ODT a následná konverze do TEI.

### Krok A: Příprava souborů
Vložte své `.odt` soubory (např. `10_DJAK_03_Ksaft.odt`) do složky **`input/`**.

### Krok B: Extrakce (ODT -> XML)
Spusťte skript, který z ODT souborů vytáhne technická XML data:

```bash
./odt2xml.sh
```
*Výsledek:* Ve složce `input/` se objeví nové `.xml` soubory (např. `10_DJAK_03_Ksaft.xml`).

### Krok C: Konverze (XML -> TEI)

Před spuštěním konverze se ujistěte, že skript `scripts/tei_convertor_final.py` obsahuje správná nastavení pro daný svazek (pokud je třeba upravit konstanty ručně).

**Možnost 1: Konverze jednoho souboru**
```bash
./converter.sh local 10_DJAK_03_Ksaft.xml
```

**Možnost 2: Hromadná konverze (Bulk)**
Pokud nezadáte název souboru, skript automaticky zpracuje všechny XML soubory ve složce `input/`:
```bash
./converter.sh local
```

## 4. Výstupy

Všechny výsledky se ukládají do složky **`output/`**.
Pro každý běh konverze se vytvoří nová podsložka označená názvem souboru a časem (např. `output/10_DJAK_03_Ksaft_2025-12-30-10-00`).

Složka obsahuje:
*   `*_TEI.xml`: Finální TEI P5 XML soubor.
*   `lost_comments.txt`: Seznam komentářů, které se nepodařilo automaticky umístit.
*   `lost_apparatus.txt`: Seznam položek kritického aparátu, které se nepodařilo umístit.
*   `problematic_comments.txt`: Komentáře, které mají nestandardní formátování a nebyly rozpoznány.

## 5. Řešení problémů

*   **Chyba "File not found":** Ujistěte se, že jste nejprve spustili `odt2xml.sh`. Konvertor nepracuje přímo s ODT, ale s extrahovaným XML.
*   **Docker neběží:** Ujistěte se, že aplikace Docker Desktop je spuštěná.