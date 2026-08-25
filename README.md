# Finch Employment Data Explorer

A web application that connects to Finch's API to display employer and employee data 
across HR and payroll providers, with an AI-powered assistant for querying and 
exporting employee data using natural language.

## Features

- Connect to any Finch-supported HR or payroll provider via Finch Connect
- View company information including entity type, locations, and contact details
- Browse employee directory grouped by department with search and active/inactive filtering
- View detailed individual and employment information for each employee
- AI-powered HR Data Assistant (powered by Claude) that can:
  - Filter the employee directory using natural language (e.g. "show me active employees in Sports")
  - Answer questions about employees, departments, and company data
  - Generate and export downloadable CSV reports on request (e.g. "build me a report of active employees")
- Graceful null handling — all missing fields display "Not available"
- Custom error messages when a provider does not implement a specific endpoint
- Access token scoped to company, directory, individual, and employment only — 
  payment and pay-statement endpoints are explicitly excluded and blocked at the route level

## Prerequisites

- Python 3.8 or higher
- A Finch sandbox account with a valid client_id and client_secret
- An Anthropic API key (for the AI Data Assistant feature)
- pip

## Setup Instructions

**1. Clone the repository**
```bash
git clone https://github.com/dynnog/finch-app.git
cd finch-app
```

**2. Create and activate a virtual environment**

Mac/Linux:
```bash
python3 -m venv venv
source venv/bin/activate
```

Windows:
```bash
python -m venv venv
venv\Scripts\activate
```

**3. Install dependencies**
```bash
pip install -r requirements.txt
```

**4. Create a `.env` file in the root of the project**

FINCH_CLIENT_ID=your_sandbox_client_id
FINCH_CLIENT_SECRET=your_sandbox_client_secret
FINCH_REDIRECT_URI=http://localhost:5000/callback
FLASK_SECRET_KEY=any_long_random_string_you_choose
ANTHROPIC_API_KEY=provided_in_submission_email


You will need:
- A Finch sandbox account: https://dashboard.tryfinch.com/signup
- An Anthropic API key will be provided separately via email for testing the AI assistant

**5. Add the redirect URI to your Finch Dashboard**

In your Finch Dashboard under Redirect URIs, add:

http://localhost:5000/callback


**6. Run the application**
```bash
python app.py
```

**7. Open your browser and navigate to**

http://localhost:5000


## How to Use

1. Click **Connect Provider** on the home page
2. Select any HR or payroll provider from the Finch Connect screen
3. Log in with sandbox credentials: username `good_user`, password `good_pass`
4. View company information and the full employee directory
5. Click any employee to view their individual and employment details
6. Use the **HR Data Assistant** to ask questions or filter the directory in natural language
7. Ask the assistant to build a report (e.g. "generate a report of inactive employees") to receive a downloadable CSV
8. Click **Disconnect** in the top banner to reset the session and connect a different provider

## Tech Stack

- Python 3
- Flask
- Jinja2
- Requests
- python-dotenv
- Anthropic SDK (Claude Haiku 4.5) with tool use for natural language filtering and report generation

## Design Decisions

**Token scoping:** The access token is scoped at connection creation time to only 
include company, directory, individual, and employment products. This explicitly 
prevents the token from accessing payment or pay-statement endpoints. Direct calls 
to those routes are also blocked at the application level and return a 403 error.

**Token storage:** The access token is stored server-side in Flask's session, 
never exposed to the frontend or stored in the browser. A static Flask secret key 
is used so sessions persist across server restarts during local development.

**Null handling:** All fields are checked before rendering. Any null value displays 
"Not available" rather than rendering blank or throwing an error.

**Error handling:** If a provider does not implement an endpoint, the application 
displays a clear, user-friendly error message rather than exposing raw API errors.

**AI-native design:** Rather than a simple Q&A chatbot, the HR Data Assistant uses 
Claude's tool use feature to take direct action on the interface. When a user asks 
to filter or export data, Claude selects the appropriate tool (filter_employees or 
generate_report) and the backend executes it, updating the UI or producing a CSV 
download in response. This keeps the assistant grounded in actual API data rather 
than generating responses from memory.

**Dynamic customer_id:** Each Finch Connect session is created with a unique 
customer_id (generated via uuid) to avoid connection_already_exists errors when 
testing multiple connections during development.

## Project Structure

finch-app/
├── app.py # Flask application and route handlers
├── requirements.txt # Python dependencies
├── .env # Local credentials (not committed to Git)
├── .gitignore # Excludes .env and venv from Git
├── static/
│ └── style.css # Application styles
└── templates/
├── index.html # Home page with connect button
├── company.html # Company dashboard, employee directory, and AI assistant
└── employee.html # Individual employee detail page


## Given More Time

- Add webhook support so the app is notified of employee record changes in real 
  time rather than polling the API on every page load
- Add a caching layer to avoid redundant API calls when the same data is requested 
  repeatedly within a short window
- Support pagination for directories with more than 20 employees
- Persist generated CSV reports to disk or cloud storage with expiration, rather 
  than storing them in memory
- Add retry logic with exponential backoff for rate-limited API responses
