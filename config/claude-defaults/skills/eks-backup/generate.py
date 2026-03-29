#!/usr/bin/env python3
"""EKS Backup generator — creates all backup infrastructure from a config file.

Usage:
    python generate.py init <project-dir> --namespace <ns> --accounts <p1,p2>
    python generate.py apply <project-dir>
    python generate.py status <project-dir>
    python generate.py restore <project-dir> [--dry-run]
"""
import argparse
import json
import os
import subprocess
import sys
import yaml

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")


def load_config(project_dir):
    cfg_path = os.path.join(project_dir, "backup-config.yaml")
    if not os.path.isfile(cfg_path):
        print(f"ERROR: No backup-config.yaml in {project_dir}")
        sys.exit(1)
    with open(cfg_path) as f:
        return yaml.safe_load(f)


def resolve_accounts(cfg):
    """Resolve account IDs from AWS CLI if not set in config."""
    for acct in cfg.get("aws_accounts", []):
        if not acct.get("account_id"):
            try:
                r = subprocess.run(
                    ["aws", "--profile", acct["profile"], "sts", "get-caller-identity",
                     "--query", "Account", "--output", "text"],
                    capture_output=True, text=True, timeout=10)
                if r.returncode == 0:
                    acct["account_id"] = r.stdout.strip()
            except Exception:
                pass
    return cfg


def render_template(template_name, variables):
    """Read template and substitute {{variables}}."""
    path = os.path.join(TEMPLATE_DIR, template_name)
    with open(path) as f:
        content = f.read()
    for key, val in variables.items():
        content = content.replace("{{" + key + "}}", str(val))
    return content


def cmd_init(args):
    project_dir = args.project_dir
    namespace = args.namespace
    profiles = [p.strip() for p in args.accounts.split(",")]

    os.makedirs(project_dir, exist_ok=True)
    os.makedirs(os.path.join(project_dir, "cloudformation"), exist_ok=True)
    os.makedirs(os.path.join(project_dir, "k8s"), exist_ok=True)

    # Build config
    accounts = []
    for p in profiles:
        acct_id = ""
        region = "us-east-2"
        try:
            r = subprocess.run(
                ["aws", "--profile", p, "sts", "get-caller-identity",
                 "--query", "Account", "--output", "text"],
                capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                acct_id = r.stdout.strip()
            r2 = subprocess.run(
                ["aws", "--profile", p, "configure", "get", "region"],
                capture_output=True, text=True, timeout=5)
            if r2.returncode == 0 and r2.stdout.strip():
                region = r2.stdout.strip()
        except Exception:
            pass
        accounts.append({
            "profile": p,
            "account_id": acct_id,
            "region": region,
        })

    cfg = {
        "namespace": namespace,
        "aws_accounts": accounts,
        "bucket_prefix": f"{namespace}-backup",
        "secret_name": f"{namespace}/graph-refresh-token",
        "backup_schedule": "0 */6 * * *",
        "pvc_name": f"{namespace}-data",
        "data_paths": ["messages", "mentions", "state.json"],
        "token_source": "/home/claude/.msgraph/tokens.json",
    }

    cfg_path = os.path.join(project_dir, "backup-config.yaml")
    with open(cfg_path, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, sort_keys=False)
    print(f"  Created {cfg_path}")

    # Generate all files from templates
    generate_files(project_dir, cfg)
    print(f"\n  Init complete. Review backup-config.yaml, then run:")
    print(f"    python generate.py apply {project_dir}")


def generate_files(project_dir, cfg):
    """Generate all backup files from config."""
    ns = cfg["namespace"]
    accounts = cfg["aws_accounts"]
    profiles_csv = ",".join(a["profile"] for a in accounts)

    # Variables for templates
    v = {
        "NAMESPACE": ns,
        "BUCKET_PREFIX": cfg["bucket_prefix"],
        "SECRET_NAME": cfg["secret_name"],
        "PVC_NAME": cfg["pvc_name"],
        "BACKUP_SCHEDULE": cfg["backup_schedule"],
        "AWS_PROFILES": profiles_csv,
        "TOKEN_SOURCE": cfg["token_source"],
        "DATA_PATHS_JSON": json.dumps(cfg["data_paths"]),
    }

    files = {
        "cloudformation/backup.yaml": render_template("cf-backup.yaml", v),
        "k8s/backup-cronjob.yaml": render_template("k8s-backup-cronjob.yaml", v),
        "backup.py": render_template("backup.py", v),
        "restore.py": render_template("restore.py", v),
    }

    for rel_path, content in files.items():
        full_path = os.path.join(project_dir, rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w") as f:
            f.write(content)
        print(f"  Generated {rel_path}")


def cmd_apply(args):
    cfg = load_config(args.project_dir)
    cfg = resolve_accounts(cfg)
    cf_path = os.path.join(args.project_dir, "cloudformation", "backup.yaml")
    cf_path_win = cf_path.replace("/", "\\")

    # Try cygpath for Git Bash
    try:
        r = subprocess.run(["cygpath", "-w", cf_path], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            cf_path_win = r.stdout.strip()
    except Exception:
        pass

    stack_name = f"{cfg['namespace']}-backup"

    for acct in cfg["aws_accounts"]:
        profile = acct["profile"]
        print(f"\n--- Deploying CF to {profile} ({acct.get('account_id', '?')}) ---")

        # Check if stack exists
        r = subprocess.run(
            ["aws", "--profile", profile, "cloudformation", "describe-stacks",
             "--stack-name", stack_name],
            capture_output=True, text=True, timeout=15)

        if r.returncode == 0:
            print("  Updating stack...")
            subprocess.run(
                ["aws", "--profile", profile, "cloudformation", "update-stack",
                 "--stack-name", stack_name,
                 "--template-body", f"file://{cf_path_win}",
                 "--capabilities", "CAPABILITY_NAMED_IAM"],
                timeout=60)
        else:
            print("  Creating stack...")
            subprocess.run(
                ["aws", "--profile", profile, "cloudformation", "create-stack",
                 "--stack-name", stack_name,
                 "--template-body", f"file://{cf_path_win}",
                 "--capabilities", "CAPABILITY_NAMED_IAM"],
                timeout=60)
            print("  Waiting...")
            subprocess.run(
                ["aws", "--profile", profile, "cloudformation", "wait",
                 "stack-create-complete", "--stack-name", stack_name],
                timeout=300)

        # Seed token
        token_file = cfg.get("token_source", "")
        if os.path.isfile(token_file):
            with open(token_file) as f:
                tokens = json.load(f)
            rt = tokens.get("refresh_token", "")
            if rt:
                subprocess.run(
                    ["aws", "--profile", profile, "secretsmanager", "put-secret-value",
                     "--secret-id", cfg["secret_name"],
                     "--secret-string", json.dumps({"refresh_token": rt})],
                    capture_output=True, timeout=15)
                print("  Token seeded.")

    print("\nDone.")


def cmd_status(args):
    cfg = load_config(args.project_dir)
    cfg = resolve_accounts(cfg)
    stack_name = f"{cfg['namespace']}-backup"

    print(f"=== Backup Status: {cfg['namespace']} ===\n")
    for acct in cfg["aws_accounts"]:
        profile = acct["profile"]
        acct_id = acct.get("account_id", "?")
        bucket = f"{cfg['bucket_prefix']}-{acct_id}"
        print(f"  [{profile}] Account: {acct_id}")

        # Check last backup marker
        r = subprocess.run(
            ["aws", "--profile", profile, "s3", "cp",
             f"s3://{bucket}/backup-markers/{profile}.json", "-"],
            capture_output=True, text=True, timeout=15)
        if r.returncode == 0:
            try:
                marker = json.loads(r.stdout)
                print(f"    Last backup: {marker.get('timestamp', '?')}")
            except json.JSONDecodeError:
                print(f"    Last backup: (corrupt marker)")
        else:
            print(f"    Last backup: never")


def cmd_restore(args):
    cfg = load_config(args.project_dir)
    cfg = resolve_accounts(cfg)
    restore_script = os.path.join(args.project_dir, "restore.py")
    cmd = [sys.executable, restore_script]
    if args.dry_run:
        cmd.append("--dry-run")
    subprocess.run(cmd)


def main():
    parser = argparse.ArgumentParser(description="EKS Backup generator")
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="Initialize backup config for a namespace")
    p_init.add_argument("project_dir", help="Project directory")
    p_init.add_argument("--namespace", required=True, help="K8s namespace")
    p_init.add_argument("--accounts", required=True, help="Comma-separated AWS profile names")

    p_apply = sub.add_parser("apply", help="Deploy CF stacks")
    p_apply.add_argument("project_dir")

    p_status = sub.add_parser("status", help="Check backup health")
    p_status.add_argument("project_dir")

    p_restore = sub.add_parser("restore", help="Restore from backups")
    p_restore.add_argument("project_dir")
    p_restore.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    if args.command == "init":
        cmd_init(args)
    elif args.command == "apply":
        cmd_apply(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "restore":
        cmd_restore(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
