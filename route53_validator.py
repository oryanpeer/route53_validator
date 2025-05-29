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
    seen_sources = set()

    for record in records:
        if args.limit is not None and processed_count >= args.limit:
            break

        if record['Type'] not in ('A', 'CNAME'):
            continue

        source = normalize(record['Name'])
        target = normalize(record['ResourceRecords'][0]['Value']) if 'ResourceRecords' in record and record['ResourceRecords'] else None

        if source in seen_sources:
            continue
        seen_sources.add(source)

        if any(pat.search(source) or (target and pat.search(target)) for pat in ignore_patterns):
            if not args.silent:
                print(f"⚠️ Ignored: {source} (or CNAME target) matches ignore pattern")
            continue

        ip_list_source = resolve_to_external_ip(source, args.resolver)
        final_domain = source
        status_parts = []

        if ip_list_source:
            status_parts.append("✅ Source resolves")
        else:
            status_parts.append("❌ Source does not resolve")

        ip_list_target = []
        if record['Type'] == 'CNAME':
            target = normalize(record['ResourceRecords'][0]['Value'])
            final_domain = target
            ip_list_target = resolve_to_external_ip(target, args.resolver)

            if ip_list_source:
                if ip_list_target:
                    status_parts.append("✅ Target resolves")
                else:
                    status_parts.append("❌ Target does not resolve")

        ip_list = ip_list_source or []
        status = "; ".join(status_parts)

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
