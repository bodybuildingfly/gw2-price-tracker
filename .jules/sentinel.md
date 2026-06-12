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

## 2026-06-05 - [Information Exposure] Sensitive Data Leakage via UI Form Values
**Vulnerability:** The Streamlit application was rendering the plaintext Gemini API key inside the HTML value attribute of a text input field (`value=current.get("gemini_api_key", "")`). Although `type="password"` visually obscures the input, the plaintext secret is still sent to the user's browser DOM, making it readable by browser extensions or through DOM inspection tools.
**Learning:** Returning secrets directly to the UI layer as form values is an Information Exposure risk. Web interfaces should act as write-only sinks for secrets or provide indirect representations.
**Prevention:** Use placeholder text (e.g., `"********"`) to indicate a secret is saved, keep the actual `value` empty, and update the backend secret only if the user submits a new value.

## 2026-06-06 - [Denial of Service] Rate Limit Bypass on Backend Failure (FDoS)
**Vulnerability:** The AI Recommendations rate limit state (`st.session_state["ai_recs_last_call"]`) was only being updated *after* the Gemini API returned successfully. If an attacker spammed the button and the backend failed, the limit state wasn't updated, allowing repeated calls causing a Financial Denial of Service (FDoS).
**Learning:** State management for security mechanisms like rate limiting must happen at the point of action initiation, not solely upon successful completion. Failing to commit the rate limit token early allows bypass through intentionally malformed requests or backend timeouts.
**Prevention:** Always update the rate limit state marker immediately upon passing the check, *before* executing the expensive or rate-limited operation.

## 2026-06-08 - [Denial of Service] Resource Exhaustion via Unbounded Cache
**Vulnerability:** The Streamlit application was using `@st.cache_data` without a `max_entries` limit for dynamically parameterized queries like `fetch_price_history(item_id: int)`. Since there are thousands of unique items, querying many items would cause the cache to grow indefinitely, exhausting server memory (OOM) and causing a Denial of Service.
**Learning:** In long-running Streamlit applications, unbounded caches on functions that accept a large domain of unique parameters will inevitably leak memory. Caches must always be bounded to limit the memory footprint.
**Prevention:** Always explicitly define `max_entries` on `@st.cache_data` and `@st.cache_resource` decorators for parameterized functions to enforce a strict memory boundary.

## 2026-06-12 - [Denial of Service] Resource Exhaustion via Hanging External API Calls
**Vulnerability:** The application was calling the Gemini API (`genai.Client`) without explicitly configuring a timeout (`http_options={'timeout': ...}`).
**Learning:** External services can hang indefinitely without explicitly terminating the connection. If the user invokes this action repeatedly, the server will keep those connections open, consuming resources until memory exhaustion or connection limits are reached (Resource Exhaustion/DoS).
**Prevention:** When using external API clients, always specify explicit timeouts to force a failure and resource cleanup if the external dependency stops responding.
