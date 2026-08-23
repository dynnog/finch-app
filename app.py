from flask import Flask, redirect, request, session, render_template
import requests
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

CLIENT_ID = os.getenv("FINCH_CLIENT_ID")
CLIENT_SECRET = os.getenv("FINCH_CLIENT_SECRET")
REDIRECT_URI = os.getenv("FINCH_REDIRECT_URI")

FINCH_API = "https://api.tryfinch.com"
FINCH_VERSION = "2020-09-17"

PRODUCTS = ["company", "directory", "individual", "employment"]

def finch_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Finch-API-Version": FINCH_VERSION,
        "Content-Type": "application/json"
    }

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/connect")
def connect():
    payload = {
        "customer_id": "test-customer",
        "customer_name": "Test Company",
        "products": PRODUCTS,
        "redirect_uri": REDIRECT_URI,
        "sandbox": "finch"
    }
    response = requests.post(
        f"{FINCH_API}/connect/sessions",
        json=payload,
        auth=(CLIENT_ID, CLIENT_SECRET)
    )
    data = response.json()
    if "connect_url" in data:
        return redirect(data["connect_url"])
    return "Error creating session", 500

@app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return "No authorization code received", 400

    token_response = requests.post(
        f"{FINCH_API}/auth/token",
        json={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code": code,
            "redirect_uri": REDIRECT_URI
        }
    )
    token_data = token_response.json()
    if "access_token" not in token_data:
        return "Error retrieving access token", 500

    session["access_token"] = token_data["access_token"]
    session["provider_id"] = token_data.get("provider_id", "Unknown")
    return redirect("/dashboard")

@app.route("/dashboard")
def dashboard():
    token = session.get("access_token")
    if not token:
        return redirect("/")

    headers = finch_headers(token)

    company = requests.get(f"{FINCH_API}/employer/company", headers=headers).json()
    directory = requests.get(f"{FINCH_API}/employer/directory", headers=headers).json()
    employees = directory.get("individuals", [])

    return render_template(
        "company.html",
        company=company,
        employees=employees,
        provider=session.get("provider_id")
    )

@app.route("/employee/<individual_id>")
def employee(individual_id):
    token = session.get("access_token")
    if not token:
        return redirect("/")

    headers = finch_headers(token)
    payload = {"requests": [{"individual_id": individual_id}]}

    individual_res = requests.post(
        f"{FINCH_API}/employer/individual",
        json=payload,
        headers=headers
    )

    employment_res = requests.post(
        f"{FINCH_API}/employer/employment",
        json=payload,
        headers=headers
    )

    if individual_res.status_code == 501:
        individual = None
        individual_error = "This provider does not support individual data."
    else:
        individual = individual_res.json().get("responses", [{}])[0].get("body", {})
        individual_error = None

    if employment_res.status_code == 501:
        employment = None
        employment_error = "This provider does not support employment data."
    else:
        employment = employment_res.json().get("responses", [{}])[0].get("body", {})
        employment_error = None

    return render_template(
        "employee.html",
        individual=individual,
        employment=employment,
        individual_error=individual_error,
        employment_error=employment_error
    )

@app.route("/employer/payment")
def payment_blocked():
    return "Access to payment data is not permitted by this application.", 403

@app.route("/employer/pay-statement")
def pay_statement_blocked():
    return "Access to pay-statement data is not permitted by this application.", 403

if __name__ == "__main__":
    app.run(debug=True)