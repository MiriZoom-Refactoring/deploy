#!/usr/bin/env python3
"""Validate bootstrap inputs, printing field names but never secret values."""
import argparse
import ipaddress
from pathlib import Path
import sys
import yaml

REQUIRED = {
    'jenkins.env': ['JENKINS_ADMIN_ID', 'JENKINS_ADMIN_PASSWORD', 'GITHUB_USERNAME',
                    'GITHUB_TOKEN', 'DOCKERHUB_USERNAME', 'DOCKERHUB_TOKEN',
                    'MIRIZOOM_KAKAO_JS_KEY', 'BACKEND_REPOSITORY_URL',
                    'FRONTEND_REPOSITORY_URL', 'FASTAPI_REPOSITORY_URL', 'DEPLOY_REPOSITORY_URL'],
    'app.env': ['DB_HOST', 'DB_USERNAME', 'DB_PASSWORD', 'KAKAO_REST_API_KEY',
                'JWT_SECRET', 'AI_CRYPTO_KEY_V1', 'PII_HMAC_KEY_V1', 'KRX_AUTH_KEY',
                'FSC_SECURITIES_API_KEY', 'OPENAI_API_KEY', 'MIRIZOOM_DB_HOST',
                'MIRIZOOM_DB_USER', 'MIRIZOOM_DB_PASSWORD'],
    'frontend.env': ['FRONTEND_TAG', 'BACKEND_PORT'],
}

def read_env(path):
    values = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        values[key.strip()] = value.strip().strip('\"\'')
    return values

def validate(secrets, inventory):
    errors = []
    for filename, names in REQUIRED.items():
        path = secrets / filename
        if not path.is_file():
            errors.append(f'Missing file: {filename}')
            continue
        values = read_env(path)
        for name in names:
            if not values.get(name) or values[name] in ['CHANGE_ME', 'YOUR_VALUE']:
                errors.append(f'{filename}: set {name}')
    if not inventory.is_file():
        return errors + ['Missing bootstrap inventory']
    try:
        data = yaml.safe_load(inventory.read_text())['all']
        children = data['children']
        connection_ips, private_ips = [], []
        for group in ['jenkins', 'app', 'web']:
            hosts = children[group]['hosts']
            if len(hosts) != 1:
                errors.append(f'Inventory: {group} must contain exactly one host')
            for host in hosts.values():
                for field, addresses in [('ansible_host', connection_ips), ('private_ip', private_ips)]:
                    ip = ipaddress.ip_address(host[field])
                    if ip.version != 4:
                        errors.append(f'Inventory: {group}.{field} must be IPv4')
                    addresses.append(str(ip))
        if len(set(connection_ips)) != 3 or len(set(private_ips)) != 3:
            errors.append('Inventory: use three different server addresses')
        jenkins_hosts = children['jenkins']['hosts']
        if next(iter(jenkins_hosts.values())).get('ansible_connection') != 'local':
            errors.append('Inventory: run bootstrap on the Jenkins server with ansible_connection local')
        settings = data['vars']
        if settings['ansible_user'] != 'ec2-user':
            errors.append('Inventory: ansible_user must be ec2-user for this Amazon Linux practice')
        if not Path(settings['ansible_ssh_private_key_file']).expanduser().is_file():
            errors.append('Inventory: SSH private key file does not exist')
    except (KeyError, TypeError, ValueError, yaml.YAMLError):
        errors.append('Inventory: check group structure and IPv4 addresses')
    return errors

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--secrets-dir', type=Path, required=True)
    parser.add_argument('--inventory', type=Path, required=True)
    args = parser.parse_args()
    errors = validate(args.secrets_dir, args.inventory)
    if errors:
        print('\n'.join(errors), file=sys.stderr)
        sys.exit(1)
    print('Bootstrap input validation passed. Secret values were not printed.')
