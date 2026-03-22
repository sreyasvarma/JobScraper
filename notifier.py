"""
Notifier — digest email (2x daily) + WhatsApp via Twilio.
Never sends instant per-job alerts. Accumulates unnotified jobs and
sends at scheduled digest times (default 09:00 and 18:00).
"""

import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

logger = logging.getLogger(__name__)


# ── Digest email ───────────────────────────────────────────────────────────────

def send_digest(jobs: list[dict], email_config: dict, digest_label: str = "Daily Digest"):
    """Send an HTML digest of new jobs. jobs is a list of dicts from the DB."""
    if not jobs:
        logger.info("Digest: no new jobs to send")
        return False

    sender    = email_config["sender"]
    recipient = email_config["recipient"]
    subject   = f"[Job Alert] {digest_label} - {len(jobs)} new job{'s' if len(jobs)!=1 else ''}"

    html  = _build_html(jobs, digest_label)
    plain = _build_plain(jobs)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"Job Alert <{sender}>"
    msg["To"]      = recipient
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html,  "html"))

    try:
        with smtplib.SMTP(email_config["smtp_host"], email_config["smtp_port"]) as server:
            server.ehlo()
            server.starttls()
            server.login(sender, email_config["password"])
            server.sendmail(sender, recipient, msg.as_string())
        logger.info(f"Digest sent: {len(jobs)} jobs to {recipient}")
        return True
    except Exception as e:
        logger.error(f"Failed to send digest: {e}", exc_info=True)
        return False


def _group_by_company(jobs):
    grouped = {}
    for job in jobs:
        grouped.setdefault(job["company"], []).append(job)
    return grouped


def _build_html(jobs: list[dict], label: str) -> str:
    grouped  = _group_by_company(jobs)
    now      = datetime.now().strftime("%B %d, %Y %I:%M %p")
    count    = len(jobs)
    remote_c = sum(1 for j in jobs if j.get("is_remote"))

    company_blocks = ""
    for company, cjobs in grouped.items():
        rows = ""
        for job in cjobs:
            loc = job.get("location") or "Not specified"
            if job.get("is_remote"):
                loc_html = '<span style="background:#1a6628;color:#39d353;padding:2px 8px;border-radius:3px;font-size:11px;font-weight:700;">REMOTE</span>'
            else:
                loc_html = f'<span style="color:#888;font-size:12px">{loc}</span>'

            dept = f'<div style="color:#aaa;font-size:11px;margin-top:2px">{job["department"]}</div>' if job.get("department") else ""
            rows += f"""
            <tr>
              <td style="padding:12px 16px;border-bottom:1px solid #1c2733">
                <a href="{job['url']}" style="color:#cdd9e5;font-weight:600;text-decoration:none;font-size:14px">{job['title']}</a>
                {dept}
                <div style="margin-top:4px">{loc_html}</div>
              </td>
              <td style="padding:12px 16px;border-bottom:1px solid #1c2733;text-align:right;vertical-align:top">
                <a href="{job['url']}" style="background:#39d353;color:#080c10;padding:7px 16px;border-radius:4px;text-decoration:none;font-size:12px;font-weight:700">Apply</a>
              </td>
            </tr>"""

        company_blocks += f"""
        <div style="margin-bottom:24px">
          <div style="background:#0d1117;border:1px solid #1c2733;border-radius:6px 6px 0 0;padding:10px 16px;font-weight:700;font-size:12px;color:#39d353;letter-spacing:.08em;text-transform:uppercase">{company} — {len(cjobs)} new</div>
          <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #1c2733;border-top:none;border-radius:0 0 6px 6px;background:#080c10">{rows}</table>
        </div>"""

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#080c10;font-family:'JetBrains Mono',monospace,sans-serif">
<div style="max-width:660px;margin:32px auto;padding:0 16px">
  <div style="background:linear-gradient(135deg,#0d1117,#111820);border:1px solid #1c2733;border-radius:8px;padding:28px;margin-bottom:24px;text-align:center">
    <div style="color:#39d353;font-size:32px;margin-bottom:8px">&#9678;</div>
    <div style="color:#cdd9e5;font-size:20px;font-weight:800">{label}</div>
    <div style="color:#586e82;font-size:12px;margin-top:6px">{now} &nbsp;|&nbsp; {count} new jobs &nbsp;|&nbsp; {remote_c} remote</div>
  </div>
  {company_blocks}
  <div style="text-align:center;padding:20px;color:#586e82;font-size:11px">
    job/alert &nbsp;|&nbsp; Apply early, apply first
  </div>
</div></body></html>"""


def _build_plain(jobs: list[dict]) -> str:
    lines = [f"Job Alert Digest - {len(jobs)} new jobs\n" + "="*50]
    for j in jobs:
        remote = " [REMOTE]" if j.get("is_remote") else ""
        lines.append(f"\n[{j['company']}] {j['title']}{remote}")
        lines.append(f"  Location: {j.get('location','?')}")
        lines.append(f"  URL: {j.get('url','')}")
    return "\n".join(lines)


# ── WhatsApp via Twilio ────────────────────────────────────────────────────────

def send_whatsapp_digest(jobs: list[dict], whatsapp_config: dict, label: str = "Daily Digest"):
    """
    Send a WhatsApp digest via Twilio.

    Setup (one-time, free):
    1. Sign up at twilio.com (free trial gives ~$15 credit)
    2. Go to Messaging > Try it out > Send a WhatsApp message
    3. Follow the sandbox activation (send a join code from your WhatsApp)
    4. Add to config.yaml:
         whatsapp:
           account_sid: "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
           auth_token:  "your_auth_token"
           from_number: "whatsapp:+14155238886"   # Twilio sandbox number
           to_number:   "whatsapp:+91XXXXXXXXXX"  # your number with country code
    """
    if not jobs:
        return False

    try:
        from twilio.rest import Client
    except ImportError:
        logger.error("Twilio not installed. Run: pip install twilio")
        return False

    account_sid = whatsapp_config.get("account_sid")
    auth_token  = whatsapp_config.get("auth_token")
    from_num    = whatsapp_config.get("from_number")
    to_num      = whatsapp_config.get("to_number")

    if not all([account_sid, auth_token, from_num, to_num]):
        logger.warning("WhatsApp config incomplete — skipping")
        return False

    # Build concise message (WhatsApp has 1600 char limit per message)
    lines = [f"*Job Alert - {label}*", f"_{len(jobs)} new jobs found_\n"]

    grouped = _group_by_company(jobs)
    for company, cjobs in list(grouped.items())[:8]:  # cap at 8 companies
        lines.append(f"*{company}* ({len(cjobs)})")
        for job in cjobs[:3]:  # max 3 per company in WA
            remote = " [Remote]" if job.get("is_remote") else ""
            lines.append(f"  • {job['title']}{remote}")
        if len(cjobs) > 3:
            lines.append(f"  ... +{len(cjobs)-3} more")

    if len(grouped) > 8:
        lines.append(f"\n... and {len(grouped)-8} more companies")

    lines.append("\nOpen your dashboard for all listings.")
    message_body = "\n".join(lines)

    try:
        client = Client(account_sid, auth_token)
        msg = client.messages.create(
            body=message_body,
            from_=from_num,
            to=to_num,
        )
        logger.info(f"WhatsApp sent: {msg.sid}")
        return True
    except Exception as e:
        logger.error(f"WhatsApp send failed: {e}")
        return False


# ── Legacy single-email alert (kept for --dry-run compatibility) ───────────────

def send_alert(new_jobs, email_config: dict):
    """Wraps send_digest for backwards compatibility with main.py."""
    jobs_as_dicts = [j.to_dict() if hasattr(j, 'to_dict') else j for j in new_jobs]
    send_digest(jobs_as_dicts, email_config, digest_label="New Jobs Alert")
