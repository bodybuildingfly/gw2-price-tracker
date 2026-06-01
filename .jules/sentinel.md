## 2026-05-29 - [Information Exposure] Stack Trace Leaks via Streamlit UI
**Vulnerability:** The Streamlit application was displaying full Python stack traces directly on the frontend using `st.code(traceback.format_exc())` when database or API errors occurred in `pages/ai_recs.py`.
**Learning:** Returning raw stack traces exposes internal application layout, database connection libraries, and third-party API implementation details to end users.
**Prevention:** Always log full exception details securely to the server console (`traceback.print_exc()`) and provide only generic, safe summary messages (e.g., `st.error("Database error. Check server logs.")`) to the UI.

## 2026-06-01 - [Information Exposure] Exception String Leakage via Streamlit UI
**Vulnerability:** The Streamlit application was displaying the stringified exception objects (`str(exc)`) on the frontend using `st.error(f"Database error: {exc}")`.
**Learning:** Returning stringified exceptions, even without the full stack trace, still exposes database connection details (like host, port, and database name, e.g., in SQLAlchemy/psycopg2 OperationalErrors) to end users.
**Prevention:** Never include exception objects (`{exc}`) in UI messages. Always log exception details securely to the server console (`traceback.print_exc()`) and provide only hardcoded, generic safe summary messages (e.g., `st.error("Database error. Check server logs.")`) to the UI.
