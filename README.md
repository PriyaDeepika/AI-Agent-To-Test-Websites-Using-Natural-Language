# AI Web Testing Agent Using Natural Language

## 📌 Project Overview

This project implements an AI-powered web testing agent that converts natural language instructions into automated end-to-end (E2E) browser tests using Playwright.

Users can provide human-readable test instructions such as:
- "open login page and type admin"
- "fill the form with name and email and submit"
- "go for youtube and search linux administration"

The agent parses these instructions, generates executable Playwright automation steps, executes them on a real browser, and displays the results through a web-based UI.

The system is designed with a modular agent architecture, using LangGraph to orchestrate the workflow and Flask to serve both the UI and sample test pages.

---

## 🎯 Key Features

- Natural Language → Browser Actions
- LangGraph-based agent workflow
- Real browser automation using Playwright (Chromium)
- Interactive web UI to run and view tests
- Downloadable execution report
- Rule-based parser with LLM fallback support
- Clear PASS / FAIL execution results

---

## 🧱 Project Structure

```
project/
│
├── app.py                  # Flask application entry point
├── agent.py                # Agent interface to LangGraph workflow
├── workflow.py             # LangGraph state machine definition
├── parser.py               # Rule-based instruction parser
├── llm_parser.py           # LLM-based instruction parser (optional)
├── code_generator.py       # Playwright code generation module
├── executor.py             # Playwright execution engine
├── reporter.py             # Test report generator
├── config.py               # Environment configuration
├── requirements.txt        # Python dependencies
│
├── templates/
│   ├── index.html          # Agent UI
│   ├── login_page.html     # Sample login page
│   ├── form_page.html      # Sample form page
│   └── success_page.html   # Sample success page
│
├── static/
│   └── css/
│       ├── style.css       # Main UI styling
│       └── login.css       # Sample test page styling
│
├── screenshots/            # Project screenshots (UI, results)
│
└── venv/                   # Python virtual environment (ignored in Git)
```

---

## ⚙️ Technology Stack

- Python 3.x
- Flask – Web server and UI rendering
- LangGraph – Agent workflow orchestration
- Playwright (Python) – Browser automation
- HTML / CSS / JavaScript – Frontend UI
- google-generativeai – Optional LLM-based instruction parsing

---

## 🧠 System Architecture

The agent follows a state-driven workflow:

1. Instruction Input – User enters a natural language test instruction
2. Instruction Parsing – Parsed using rule-based logic or LLM (if available)
3. Command Structuring – Actions converted into structured commands
4. Playwright Code Generation – Browser actions are generated dynamically
5. Test Execution – Playwright runs the test in a real browser
6. Result Display – PASS / FAIL result shown in UI and downloadable report

LangGraph manages this flow by passing a shared state between workflow nodes.

---

## 🔄 LangGraph Workflow

The LangGraph workflow consists of the following nodes:

- Parser Node – Extracts actions from instructions
- Code Generator Node – Produces Playwright commands
- Executor Node – Executes tests and captures results
- Reporter Node – Generates execution summary

Each node updates only the relevant part of the shared agent state.

---

## 📝 Example Instructions

open login page and type admin and submit

fill the form with name as john and email as john@gmail.com and submit

go for youtube and search linux administration

---

## ▶️ How to Run the Project

1. Clone the repository

```
git clone https://github.com/your-username/AI-Agent-Test-Websites.git  
cd AI-Agent-Test-Websites
```

2. Create and activate virtual environment

```
python -m venv venv  
source venv/bin/activate   (Windows: venv\Scripts\activate)
```

3. Install dependencies

```
pip install -r requirements.txt
```

4. Install Playwright browser

```
playwright install
```

5. Run the application

```
python app.py
```

Open browser at:

http://127.0.0.1:5000

---

## ⚠️ Notes & Limitations

- External website search is performed using keyboard-based interaction
- Not all websites expose searchable inputs
- LLM parsing is optional and may be disabled when API quota is exceeded
- Rule-based parser ensures system works without LLM access

---

## 🚀 Future Enhancements

- Screenshot capture on test failure
- Test history and execution logs
- Site-specific search strategies
- Headless execution mode
- CI/CD integration

---

## 📜 License

This project is intended for educational and demonstration purposes.
