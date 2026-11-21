# Local monitoring and email

Start Thesis Monitor using the local launcher. The API, monitoring worker, and email dispatcher run independently of the browser. Local PostgreSQL stores the watchlist, financial data, jobs, alerts, and delivery history.

Set `RESEND_API_KEY`, `EMAIL_FROM`, and `ALERT_EMAIL` in your local `.env` to enable email. The sender must be verified in Resend. Restart the app after changing settings.

Keep your Mac awake for monitoring. On startup, the workers resume pending jobs and catch up on reminders for upcoming events. An accepted email was acknowledged by Resend. A delivered receipt means the recipient mail server accepted it.
