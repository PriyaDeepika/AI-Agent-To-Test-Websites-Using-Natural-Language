from flask import Flask, request, jsonify, render_template, send_file
from agent import run_agent
from io import BytesIO
import json

app = Flask(__name__)

latest_result = None

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/login_page")
def login_page():
    return render_template("login_page.html")

@app.route("/form_page")
def form_page():
    return render_template("form_page.html")

@app.route("/success_page")
def success_page():
    return render_template("success_page.html")

@app.route("/agent/run", methods=["POST"])
def agent_api():
    global latest_result

    data = request.get_json()
    instruction = data.get("instruction", "").strip()
    # result = run_agent(instruction)
    
    if not instruction:
        return jsonify({"error": "Instruction is empty"}), 400

    latest_result = run_agent(instruction)
    return jsonify(latest_result)

    
@app.route("/agent/report", methods=["GET"])
def agent_report():
    if not latest_result:
        return jsonify({"error": "No report available"}), 400

    report_bytes = BytesIO()
    report_bytes.write(
        json.dumps(latest_result["report"], indent=4).encode("utf-8")
    )
    report_bytes.seek(0)

    return send_file(
        report_bytes,
        mimetype="application/json",
        as_attachment=True,
        download_name="test_report.json"
    )

if __name__ == "__main__":
    app.run(debug = False, use_reloader = False)
