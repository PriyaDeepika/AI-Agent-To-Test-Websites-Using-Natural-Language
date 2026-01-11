from flask import Flask, request, jsonify, render_template
from agent import run_agent

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/login_page")
def login_page():
    return render_template("login_page.html")

@app.route("/agent", methods=["POST"])
def agent_api():
    data = request.get_json()
    instruction = data.get("instruction", "")
    result = run_agent(instruction)
    return jsonify(result)

if __name__ == "__main__":
    app.run(debug = False, use_reloader = False)
