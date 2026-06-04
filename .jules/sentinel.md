## 2026-05-29 - [Information Exposure] Stack Trace Leaks via Streamlit UI
**Vulnerability:** The Streamlit application was displaying full Python stack traces directly on the frontend using `st.code(traceback.format_exc())` when database or API errors occurred in `pages/ai_recs.py`.
**Learning:** Returning raw stack traces exposes internal application layout, database connection libraries, and third-party API implementation details to end users.
**Prevention:** Always log full exception details securely to the server console (`traceback.print_exc()`) and provide only generic, safe summary messages (e.g., `st.error("Database error. Check server logs.")`) to the UI.

## 2026-06-01 - [Information Exposure] Exception String Leakage via Streamlit UI
**Vulnerability:** The Streamlit application was displaying the stringified exception objects (`str(exc)`) on the frontend using `st.error(f"Database error: {exc}")`.
**Learning:** Returning stringified exceptions, even without the full stack trace, still exposes database connection details (like host, port, and database name, e.g., in SQLAlchemy/psycopg2 OperationalErrors) to end users.
**Prevention:** Never include exception objects (`{exc}`) in UI messages. Always log exception details securely to the server console (`traceback.print_exc()`) and provide only hardcoded, generic safe summary messages (e.g., `st.error("Database error. Check server logs.")`) to the UI.

## 2026-06-02 - [Security Enhancement] Restrict File Permissions for Sensitive Configuration
**Vulnerability:** The `settings.json` file, which stores sensitive configuration data such as the Gemini API Key, was being created with default file permissions (typically 644). This allowed read access to the API key by any user on the host system or container.
**Learning:** Storing API keys or sensitive credentials in plaintext configuration files without explicit permission restrictions violates the principle of least privilege and introduces a risk of unauthorized access.
**Prevention:** Always explicitly set restrictive file permissions (e.g., `chmod(0o600)`) on configuration files that store secrets after creation or modification to ensure only the owner can read or write to them.

## 2026-06-03 - [Security Enhancement] Missing Rate Limiting on External API Calls
**Vulnerability:** The AI Recommendations page (`pages/ai_recs.py`) lacked rate limiting for the Gemini API call triggered by the "Analyze My Holdings" button. This could allow malicious or accidental repeated clicks to exhaust API quotas or incur unexpected financial costs (Financial Denial of Service - FDoS).
**Learning:** Any user-triggered action that invokes an external, potentially paid API or performs a computationally expensive operation must have rate limiting or throttling applied to prevent abuse and manage costs.
**Prevention:** Implement global or per-user rate limiting (e.g., using `time.time()` in Streamlit's session state or a module-level variable) to ensure minimum delays between consecutive API calls.
