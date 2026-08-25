from flask import Flask, redirect, request, session, render_template
import requests
import os
import anthropic
import csv
import io
import uuid
from dotenv import load_dotenv
from flask import send_file

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

CLIENT_ID = os.getenv("FINCH_CLIENT_ID")
CLIENT_SECRET = os.getenv("FINCH_CLIENT_SECRET")
REDIRECT_URI = os.getenv("FINCH_REDIRECT_URI")

FINCH_API = "https://api.tryfinch.com"
FINCH_VERSION = "2020-09-17"

PRODUCTS = ["company", "directory", "individual", "employment"]
generated_reports = {}

def finch_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Finch-API-Version": FINCH_VERSION,
        "Content-Type": "application/json"
    }

@app.route("/")
def index():
    if session.get("access_token"):
        return redirect("/dashboard")
    return render_template("index.html")

@app.route("/connect")
def connect():
    if session.get("access_token"):
        return redirect("/dashboard")

    payload = {
        "customer_id": str(uuid.uuid4()),
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
    return f"Error creating session: {data}", 500

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

@app.route("/disconnect")
def disconnect():
    session.clear()
    return redirect("/")

@app.route("/employer/payment")
def payment_blocked():
    return "Access to payment data is not permitted by this application.", 403

@app.route("/employer/pay-statement")
def pay_statement_blocked():
    return "Access to pay-statement data is not permitted by this application.", 403

def build_csv_report(employee_summary, filters):
    status = filters.get("status", "all")
    department = filters.get("department")

    filtered = employee_summary
    if status != "all":
        want_active = status == "active"
        filtered = [e for e in filtered if e["is_active"] == want_active]
    if department:
        filtered = [e for e in filtered if (e.get("department") or "").lower() == department.lower()]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["First Name", "Last Name", "Department", "Status"])
    for emp in filtered:
        writer.writerow([
            emp.get("first_name", ""),
            emp.get("last_name", ""),
            emp.get("department", "Not available"),
            "Active" if emp.get("is_active") else "Inactive"
        ])

    report_id = str(uuid.uuid4())
    generated_reports[report_id] = output.getvalue()
    return report_id    

@app.route("/chat", methods=["POST"])
def chat():
    token = session.get("access_token")
    if not token:
        return {"error": "Not connected"}, 401

    user_message = request.json.get("message")
    if not user_message:
        return {"error": "No message provided"}, 400

    headers = finch_headers(token)

    company = requests.get(f"{FINCH_API}/employer/company", headers=headers).json()
    directory = requests.get(f"{FINCH_API}/employer/directory", headers=headers).json()
    employees = directory.get("individuals", [])

    employee_summary = [
        {
            "id": emp["id"],
            "first_name": emp.get("first_name"),
            "last_name": emp.get("last_name"),
            "department": emp.get("department", {}).get("name") if emp.get("department") else None,
            "is_active": emp.get("is_active"),
        }
        for emp in employees
    ]

    tools = [
        {
            "name": "filter_employees",
            "description": "Filter the employee directory shown on the dashboard based on search term and/or active status.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "search_term": {
                        "type": "string",
                        "description": "Text to search employee names or departments by. Leave empty to not filter by search."
                    },
                    "status": {
                        "type": "string",
                        "enum": ["all", "active", "inactive"],
                        "description": "Filter by employment status"
                    }
                },
                "required": ["status"]
            }
        },
        {
            "name": "generate_report",
            "description": "Generate a downloadable CSV report of employees. Use this when the user asks to build a report, export data, or download a list.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["all", "active", "inactive"],
                        "description": "Which employees to include in the report"
                    },
                    "department": {
                        "type": "string",
                        "description": "Filter report to a specific department. Leave empty for all departments."
                    }
                },
                "required": ["status"]
            }
        }
    ]

    system_prompt = f"""You are an HR data assistant for {company.get('legal_name', 'this company')}.
    You help users explore employee data by filtering the directory shown on their dashboard.

    When the user asks to see, find, or filter employees (e.g. "show me active employees", 
    "find people in Sports"), use the filter_employees tool to update the dashboard.

    When the user asks to build a report, export data, or download a list 
    (e.g. "build me a report of active employees", "export the Sports department"), 
    use the generate_report tool.

    When the user asks a question that requires an answer rather than a filter or report
    (e.g. "how many employees are inactive", "what's the company's email"), 
    answer directly using the data below without calling any tool.

    Company Information:
    - Legal Name: {company.get('legal_name')}
    - Primary Email: {company.get('primary_email')}

    Employee Data:
    {employee_summary}
    """

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=system_prompt,
        tools=tools,
        messages=[{"role": "user", "content": user_message}]
    )

    text_reply = ""
    filter_action = None
    report_id = None

    for block in response.content:
        if block.type == "text":
            text_reply += block.text
        elif block.type == "tool_use" and block.name == "filter_employees":
            filter_action = block.input
        elif block.type == "tool_use" and block.name == "generate_report":
            report_id = build_csv_report(employee_summary, block.input)

    if not text_reply and filter_action:
        text_reply = "Updated the directory for you."
    if not text_reply and report_id:
        text_reply = "Your report is ready to download."

    return {
        "response": text_reply,
        "filter": filter_action,
        "report_id": report_id
    }

@app.route("/download-report/<report_id>")
def download_report(report_id):
    csv_data = generated_reports.get(report_id)
    if not csv_data:
        return "Report not found or expired", 404

    return send_file(
        io.BytesIO(csv_data.encode()),
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"employee_report_{report_id[:8]}.csv"
    )

if __name__ == "__main__":
    app.run(debug=True)