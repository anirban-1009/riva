# First Run Guide 🚀

Follow these steps to set up the **Job Hunt Mind Mapper** for the first time.

## 1. Prerequisites

Before you begin, ensure you have the following installed:
- **Python 3.13+**
- **Obsidian** (to view the mind map)
- **Chrome or Firefox** (for the automated browser parts)
- **LaTeX** (for resume generation; see below)

## 2. Setting Up the Environment

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/anirban-1009/JobHuntMindMap.git
    cd JobHuntMindMap
    ```

2.  **Create a virtual environment**:
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows: .venv\Scripts\activate
    ```

3.  **Install dependencies**:
    ```bash
    pip install .
    playwright install chromium
    ```

## 2.5. Install LaTeX (for Resume Generation)

The `tailor` command compiles a tailored resume PDF using `pdflatex`, so a LaTeX distribution is required.

### macOS
Install the lightweight **BasicTeX** distribution via Homebrew:
```bash
brew install --cask basictex
```

> **Note:** BasicTeX is a minimal TeX Live distribution. If the resume template requires a package that isn't included, install it with `tlmgr` (e.g. `sudo tlmgr install <package>`). For a full distribution, use `brew install --cask mactex` instead.

### Windows
Install **MiKTeX** from [miktex.org](https://miktex.org/download).

### Linux
Install TeX Live via your package manager, e.g.:
```bash
sudo apt-get install texlive-latex-base texlive-latex-extra texlive-fonts-recommended
```

## 3. Configuration

1.  **Create your config file**:
    ```bash
    cp config.sample.yaml config.yaml
    ```
2.  **Edit `config.yaml`**:
    - Update `obsidian.vault_path` to point to where you want the vault generated.
    - Update `user.full_name` and `user.email`.
    - Place your resume PDF in `data/resume.pdf` (or update the path).

## 4. Get Your API Keys

### Google Gemini Key (Required for AI Scoring)
1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey).
2. Create a new API key.
3. Add it to your `config.yaml` under `ai.gemini.api_key` or set it as an environment variable `GEMINI_API_KEY`.

### LinkedIn Session (Required for Scraping)
LinkedIn uses strict anti-bot measures. We use your real session cookies to safely fetch data.

1. Run the login command:
   ```bash
   python -m src.main login
   ```
2. A browser window will open. **Log in to LinkedIn manually**.
3. Once you're on the LinkedIn feed, the tool will automatically detect the login, save your session to `data/session.json`, and close the browser.

## 5. Validating Setup

Run the check command to ensure everything is configured correctly:
```bash
python -m src.main check
```

## 6. Test AI Connection

Verify that your Gemini API key is working:
```bash
python -m src.main test-ai
```

---

Next Step: [Deployment Guide](DEPLOYMENT.md) for daily usage and scheduling.
