## 2026-05-29 - [Information Exposure] Stack Trace Leaks via Streamlit UI
**Vulnerability:** The Streamlit application was displaying full Python stack traces directly on the frontend using `st.code(traceback.format_exc())` when database or API errors occurred in `pages/ai_recs.py`.
**Learning:** Returning raw stack traces exposes internal application layout, database connection libraries, and third-party API implementation details to end users.
**Prevention:** Always log full exception details securely to the server console (`traceback.print_exc()`) and provide only generic, safe summary messages (e.g., `st.error(f"Database error: {exc}")`) to the UI.
