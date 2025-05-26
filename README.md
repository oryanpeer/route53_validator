# 📘 Route53 DNS Validation Script

This script checks **A** and **CNAME** records in a specified AWS Route53 hosted zone (public or private) and verifies whether they resolve to an IP address using external DNS.

---

## ✅ Features

- Supports **AWS profiles** and **private/public zones**
- Resolves **CNAME chains**
- Validates **A records** via external DNS
- Uses **system default DNS resolvers** unless specified (e.g. `8.8.8.8`)
- Optional **silent mode** for clean reports
- Optional **CSV export** of all / only resolved / only unresolved records
- Customizable **DNS resolver**
- Filter records using **regex ignore patterns**
- Limit number of records processed (excluding ignored ones)

---

## 🚀 Requirements

- Python 3.12 or 3.13+
- AWS CLI with configured credentials

---

## 🔧 Setup

Install dependencies via `pipenv` (recommended for development) or `pip` globally.

### Option 1: Pipenv (for local development)

```bash
pipenv install
```

### Option 2: Global installation

```bash
pip3 install boto3 dnspython
```

---

## 🏃 How to Run

### Using Pipenv

```bash
pipenv run python route53_check.py --zone yourdomain.com
```

### Using Global Python

```bash
python3 route53_check.py --zone yourdomain.com
```

---

## 🧩 Command Line Options

| Flag             | Description |
|------------------|-------------|
| `--zone`         | **(Required)** The hosted zone name (e.g., `example.com`) |
| `--profile`      | AWS CLI profile to use |
| `--private`      | Query a private hosted zone (default is public) |
| `--resolver`     | DNS resolver IP to use (default: uses local system resolvers) |
| `--silent`       | Print only the summary report (no per-record output) |
| `--csv`          | Path to write CSV results |
| `--csv-scope`    | Choose from `all`, `resolved`, or `unresolved` records (default: `all`) |
| `--limit`        | Limit how many records to process (ignores excluded records) |
| `--ignore`       | Regex pattern(s) to skip record names or targets (can be specified multiple times) |

---

## 🔍 Examples

```bash
# Check with default settings
python3 route53_check.py --zone example.com

# Use a specific AWS profile and private zone
python3 route53_check.py --zone example.com --profile dev --private

# Use a custom resolver and export only unresolved records
python3 route53_check.py --zone example.com --resolver 1.1.1.1 --csv unresolved.csv --csv-scope unresolved

# Limit to 20 processed records and ignore internal/test records
python3 route53_check.py --zone example.com --limit 20 --ignore '.*internal.*' --ignore '^test'
```

---

## 📤 Example CSV Output

| source           | final_domain       | status                             | all_ips                     |
|------------------|--------------------|------------------------------------|------------------------------|
| login.example.com| login.example.com  | Externally resolvable A record     | 203.0.113.10, 203.0.113.11   |
| help.example.com | help.example.com   | A record does not resolve externally | No DNS resolution          |

---

## 🛑 Notes

- The script processes only A and CNAME records.
- DNS resolution uses your system's default resolvers unless overridden with `--resolver`.
- ALIAS, AAAA, MX, and other types are ignored.

---

## 📄 License

MIT License — use at your own risk. Contributions welcome!# articles
