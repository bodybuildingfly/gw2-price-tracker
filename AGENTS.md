## Documentation Protocol

**Objective:** Maintain strict synchronization between the codebase and `README.md`.

**Action Required for Every Task:**
1. **Analyze Impact:** During your initial planning phase, evaluate if your proposed code changes affect how the application is configured, deployed, or used.
2. **Identify Triggers:** You MUST update `README.md` if your changes include:
   - New or modified environment variables.
   - Changes to Docker container setups, volume mounts, or deployment steps.
   - Database schema modifications (e.g., new PostgreSQL tables).
   - Updates to n8n webhook structures, Python dependencies, or API endpoints.
3. **Execution:** If any of the above are met, append the necessary markdown modifications to `README.md` as part of your final commit and Pull Request.
4. **Verification:** If no documentation updates are needed for a specific task, explicitly note "No README updates required" in your PR description.
