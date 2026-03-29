"""SMTP Relay - Send emails via external VPS to bypass port 25 blocks."""
import argparse
import sys
import os
import keyring
import paramiko

SERVICE = "claude-code"
CRED_PREFIX = "smtp-relay"


def get_creds():
    """Retrieve VPS credentials from OS credential store."""
    ip = keyring.get_password(SERVICE, f"{CRED_PREFIX}/VPS_IP")
    user = keyring.get_password(SERVICE, f"{CRED_PREFIX}/VPS_USER")
    pw = keyring.get_password(SERVICE, f"{CRED_PREFIX}/VPS_PASSWORD")
    missing = []
    if not ip:
        missing.append(f"{CRED_PREFIX}/VPS_IP")
    if not user:
        missing.append(f"{CRED_PREFIX}/VPS_USER")
    if not pw:
        missing.append(f"{CRED_PREFIX}/VPS_PASSWORD")
    if missing:
        print(f"Missing credentials: {', '.join(missing)}")
        print("Store them with:")
        for k in missing:
            print(f"  python ~/.claude/skills/credential-manager/cred_cli.py store {k} --clipboard")
        sys.exit(1)
    return ip, user, pw


def check_connectivity(ip, user, pw):
    """Verify SSH and outbound port 25 from VPS."""
    print(f"Connecting to VPS {ip}...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(ip, username=user, password=pw, timeout=15)
        print("SSH connection: OK")
        stdin, stdout, stderr = client.exec_command(
            "python3 -c \"import smtplib; print('python3 smtplib: OK')\"", timeout=10
        )
        out = stdout.read().decode().strip()
        err = stderr.read().decode().strip()
        if "OK" in out:
            print(out)
        else:
            print(f"python3 check failed: {err or out}")
        client.close()
        print("VPS ready for SMTP relay.")
    except Exception as e:
        print(f"Connection failed: {e}")
        sys.exit(1)


def build_email_script(args):
    """Build the Python script to execute on the VPS."""
    recipients = [r.strip() for r in args.to.split(",")]

    if args.eml:
        eml_path = os.path.abspath(args.eml)
        if not os.path.exists(eml_path):
            print(f"EML file not found: {eml_path}")
            sys.exit(1)
        with open(eml_path, "r", encoding="utf-8", errors="replace") as f:
            eml_data = f.read()
        # Escape for Python string embedding
        eml_data = eml_data.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
        script = f'''
import smtplib

data = """{eml_data}"""
recipients = {recipients!r}

try:
    with smtplib.SMTP({args.host!r}, {args.port}, timeout=30) as server:
        server.set_debuglevel({1 if args.debug else 0})
        server.ehlo({args.helo!r})
        for i in range({args.count}):
            server.sendmail({args.sender!r}, recipients, data)
            print(f"Message {{i+1}}/{args.count} sent")
    print("Done")
except Exception as e:
    print(f"Error: {{e}}")
'''
    else:
        script = f'''
import smtplib
from email.mime.text import MIMEText

msg = MIMEText({args.body!r})
msg["Subject"] = {args.subject!r}
msg["From"] = {args.sender!r}
msg["To"] = {args.to!r}
recipients = {recipients!r}

try:
    with smtplib.SMTP({args.host!r}, {args.port}, timeout=30) as server:
        server.set_debuglevel({1 if args.debug else 0})
        server.ehlo({args.helo!r})
        for i in range({args.count}):
            server.sendmail({args.sender!r}, recipients, msg.as_string())
            print(f"Message {{i+1}}/{args.count} sent")
    print("Done")
except Exception as e:
    print(f"Error: {{e}}")
'''
    return script


def send(args):
    """SSH into VPS and send email."""
    ip, user, pw = get_creds()

    script = build_email_script(args)

    print(f"Connecting to VPS {ip}...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(ip, username=user, password=pw, timeout=15)

    sftp = client.open_sftp()
    with sftp.open("/tmp/smtp_relay_send.py", "w") as f:
        f.write(script)
    sftp.close()

    print(f"Sending {args.count} email(s) to {args.to} via {args.host}:{args.port}...")
    stdin, stdout, stderr = client.exec_command("python3 /tmp/smtp_relay_send.py", timeout=120)
    out = stdout.read().decode()
    err = stderr.read().decode()

    if out:
        print(out.rstrip())
    if err and args.debug:
        print("--- SMTP debug ---")
        print(err.rstrip())

    client.close()


def main():
    parser = argparse.ArgumentParser(description="Send emails via VPS SMTP relay")
    parser.add_argument("--from", dest="sender", help="Envelope sender (MAIL FROM)")
    parser.add_argument("--to", help="Envelope recipient (RCPT TO), comma-separated")
    parser.add_argument("--host", help="Target SMTP host")
    parser.add_argument("--port", type=int, default=25, help="SMTP port (default: 25)")
    parser.add_argument("--subject", default="test", help="Subject (default: test)")
    parser.add_argument("--body", default="This is a test email.", help="Body text")
    parser.add_argument("--eml", help="Send raw .eml file instead")
    parser.add_argument("--helo", default="emailTester", help="HELO hostname")
    parser.add_argument("--count", type=int, default=1, help="Number of copies")
    parser.add_argument("--check", action="store_true", help="Verify connectivity only")
    parser.add_argument("--debug", action="store_true", help="Show SMTP conversation")
    args = parser.parse_args()

    if args.check:
        ip, user, pw = get_creds()
        check_connectivity(ip, user, pw)
        return

    if not args.sender or not args.to or not args.host:
        parser.error("--from, --to, and --host are required")

    send(args)


if __name__ == "__main__":
    main()
