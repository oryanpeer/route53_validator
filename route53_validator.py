import argparse
import csv
import sys
import re

import boto3
import dns.resolver
from botocore.exceptions import ProfileNotFound


def get_route53_client(profile=None):
    if profile:
        try:
            session = boto3.Session(profile_name=profile)
        except ProfileNotFound:
            print(f"Error: AWS profile '{profile}' not found.")
            sys.exit(1)
    else:
        session = boto3.Session()

    return session.client('route53')


def find_zone_id(client, zone_name, is_private):
    paginator = client.get_paginator('list_hosted_zones')
    for page in paginator.paginate():
        for zone in page['HostedZones']:
            name_match = zone['Name'].rstrip('.') == zone_name.rstrip('.')
            privacy_match = zone['Config']['PrivateZone'] == is_private
            if name_match and privacy_match:
                return zone['Id'].split('/')[-1]
    print(f"Error: Hosted zone '{zone_name}' with private={is_private} not found.")
    sys.exit(1)


def list_records(client, zone_id):
    paginator = client.get_paginator('list_resource_record_sets')
    all_records = []
    for page in paginator.paginate(HostedZoneId=zone_id):
        all_records.extend(page['ResourceRecordSets'])
    return all_records


def normalize(name):
    return name.rstrip('.').lower()


def resolve_to_external_ip(domain, resolver_address=None):
    try:
        resolver = dns.resolver.Resolver()
        if resolver_address:
            resolver.nameservers = [resolver_address]
        answer = resolver.resolve(domain, 'A')
        return sorted([r.address for r in answer])
    except Exception:
        return None


def resolve_cname_chain(records, domain_name, resolver_address):
    tested_records = set()
    current_name = normalize(domain_name)

    while current_name not in tested_records:
        tested_records.add(current_name)

        match = next((r for r in records if normalize(r['Name']) == current_name), None)
        if not match:
            ip_list = resolve_to_external_ip(current_name, resolver_address)
            status = "Resolved externally" if ip_list else "Does not have an IP match"
            return current_name, status, ip_list

        record_type = match['Type']
        if record_type == 'A':
            ip_list = resolve_to_external_ip(current_name, resolver_address)
            status = "Externally resolvable A record" if ip_list else "A record does not resolve externally"
            return current_name, status, ip_list
        elif record_type == 'CNAME':
            current_name = normalize(match['ResourceRecords'][0]['Value'])
        else:
            return current_name, f"Unsupported record type: {record_type}", None

    return current_name, "CNAME loop detected", None


def check_a_record(domain, resolver_address):
    return resolve_to_external_ip(domain, resolver_address)


def main():
    parser = argparse.ArgumentParser(description="List Route53 records and validate DNS resolution.")
    parser.add_argument('--profile', help='AWS CLI profile name')
    parser.add_argument('--zone', required=True, help='DNS zone name to query')
    parser.add_argument('--private', action='store_true', help='Specify if hosted zone is private')
    parser.add_argument('--resolver', default=None, help='DNS resolver to use (e.g. 8.8.8.8). If not provided, uses system default.')
    parser.add_argument('--silent', action='store_true', help='Silent mode (only summary output)')
    parser.add_argument('--csv', help='Output CSV file path')
    parser.add_argument('--csv-scope', choices=['all', 'resolved', 'unresolved'], default='all', help='Which records to export to CSV')
    parser.add_argument('--limit', type=int, default=None, help='Limit the number of records to process (excluding ignored)')
    parser.add_argument('--ignore', action='append', default=[], help='Regex pattern(s) to ignore records by name. Can be used multiple times.')

    args = parser.parse_args()

    ignore_patterns = [re.compile(pat) for pat in args.ignore]

    client = get_route53_client(args.profile)
    zone_id = find_zone_id(client, args.zone, args.private)
    records = list_records(client, zone_id)

    unresolved = []
    resolved = []
    all_results = []
    processed_count = 0

    for record in records:
        if args.limit is not None and processed_count >= args.limit:
            break

        source = normalize(record['Name'])
        target = normalize(record['ResourceRecords'][0]['Value']) if record['Type'] == 'CNAME' else None

        if any(pat.search(source) or (target and pat.search(target)) for pat in ignore_patterns):
            if not args.silent:
                print(f"⚠️ Ignored: {source} (or CNAME target) matches ignore pattern")
            continue

        if record['Type'] == 'CNAME':
            target = normalize(record['ResourceRecords'][0]['Value'])
            final_domain, status, ip_list = resolve_cname_chain(records, target, args.resolver)

        elif record['Type'] == 'A':
            final_domain = source
            ip_list = check_a_record(source, args.resolver)
            status = "Externally resolvable A record" if ip_list else "A record does not resolve externally"

        else:
            continue

        processed_count += 1

        if ip_list:
            if not args.silent:
                print(f"✅ {source} resolves to {final_domain} with IP(s): {ip_list} ({status})")
            all_ips = ", ".join(ip_list)
        else:
            if not args.silent:
                print(f"❌ {source} does NOT resolve to an IP ({status})")
            all_ips = "No DNS resolution"

        result = {
            'source': source,
            'final_domain': final_domain,
            'status': status,
            'all_ips': all_ips
        }

        all_results.append(result)
        if ip_list:
            resolved.append(result)
        else:
            unresolved.append(result)

    if unresolved:
        print("\n❗ Summary: Unresolved Records")
        for item in unresolved:
            print(f"  - {item['source']} → {item['final_domain']} ({item['status']})")
    else:
        print("\n✅ All applicable records resolved to IPs.")

    if args.csv:
        try:
            if args.csv_scope == 'all':
                export_data = all_results
            elif args.csv_scope == 'resolved':
                export_data = resolved
            else:
                export_data = unresolved

            with open(args.csv, mode='w', newline='') as csvfile:
                fieldnames = ['source', 'final_domain', 'status', 'all_ips']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

                writer.writeheader()
                for item in sorted(export_data, key=lambda x: x['source']):
                    writer.writerow(item)
            print(f"\n📄 Records written to {args.csv} (scope: {args.csv_scope})")
        except Exception as e:
            print(f"Error writing CSV: {e}")


if __name__ == "__main__":
    main()
