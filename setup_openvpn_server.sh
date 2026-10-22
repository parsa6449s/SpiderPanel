#!/usr/bin/env bash
# First-time OpenVPN server setup for Ubuntu/Debian. Stops if existing server
# configuration/PKI is detected; never flushes firewall rules.
set -Eeuo pipefail
umask 077

log() { printf '[OpenVPN setup] %s\n' "$*"; }
fail() { printf '[OpenVPN setup] ERROR: %s\n' "$*" >&2; exit 1; }
[[ ${EUID:-$(id -u)} -eq 0 ]] || fail 'این اسکریپت باید با sudo اجرا شود.'
[[ -r /etc/os-release ]] || fail 'سیستم‌عامل قابل تشخیص نیست.'
# shellcheck disable=SC1091
. /etc/os-release
case "${ID:-}" in ubuntu|debian) ;; *) fail 'فقط Ubuntu و Debian در این نسخه پشتیبانی می‌شوند.' ;; esac
command -v systemctl >/dev/null 2>&1 || fail 'systemd لازم است.'

EASYRSA_DIR=/etc/openvpn/easy-rsa
SERVER_DIR=/etc/openvpn/server
APP_DIR="${SPIDER_APP_DIR:-/opt/SpiderPanel}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

[[ -x "$SCRIPT_DIR/spider-openvpnctl" ]] || fail 'فایل spider-openvpnctl کنار این اسکریپت پیدا نشد.'
[[ ! -e "$SERVER_DIR/server.conf" ]] || fail 'پیکربندی OpenVPN در حال حاضر وجود دارد؛ برای جلوگیری از بازنویسی متوقف شد.'
[[ ! -e "$EASYRSA_DIR/pki" ]] || fail 'PKI موجود است؛ برای جلوگیری از بازنویسی CA متوقف شد.'
if systemctl is-active --quiet openvpn-server@server.service 2>/dev/null; then
  fail 'سرویس OpenVPN از قبل فعال است؛ این نصب‌کننده را اجرا نکن.'
fi

read -r -p 'IP عمومی یا دامنه‌ای که کلاینت‌ها به آن وصل می‌شوند: ' PUBLIC_HOST
PUBLIC_HOST="$(printf '%s' "$PUBLIC_HOST" | tr -d '[:space:]')"
[[ "$PUBLIC_HOST" =~ ^[A-Za-z0-9]([A-Za-z0-9.-]{0,250}[A-Za-z0-9])?$ ]] || fail 'دامنه/IP نامعتبر است. IPv6 در این نسخه پشتیبانی نمی‌شود.'
[[ "$PUBLIC_HOST" != *..* && "$PUBLIC_HOST" != localhost ]] || fail 'دامنه واردشده معتبر نیست.'
WAN_IF="$(ip -4 route show default 2>/dev/null | awk 'NR==1 {print $5}')"
[[ -n "$WAN_IF" && "$WAN_IF" =~ ^[A-Za-z0-9_.:-]{1,32}$ ]] || fail 'رابط خروجی پیش‌فرض پیدا نشد؛ شبکه را بررسی کن.'

printf '\nاین اسکریپت OpenVPN را نصب می‌کند، یک CA جدید می‌سازد،
IPv4 forwarding و یک قانون NAT مشخص اضافه می‌کند و UDP/1194 را باز می‌کند.
قوانین موجود فایروال پاک نمی‌شوند، اما سرویس OpenVPN و فایروال را بعد از نصب بررسی کن.\n\n'
read -r -p 'برای ادامه دقیقاً INSTALL را وارد کن: ' CONFIRM
[[ "$CONFIRM" == 'INSTALL' ]] || fail 'لغو شد؛ هیچ تغییری اعمال نشد.'

export DEBIAN_FRONTEND=noninteractive
log 'نصب بسته‌ها…'
apt-get update -y
apt-get install -y openvpn easy-rsa iptables

[[ -x /usr/share/easy-rsa/easyrsa ]] || fail 'باینری Easy-RSA پیدا نشد.'
install -d -o root -g root -m 0700 "$EASYRSA_DIR" "$SERVER_DIR"
cp -a /usr/share/easy-rsa/. "$EASYRSA_DIR/"
chmod 0700 "$EASYRSA_DIR"

export EASYRSA_PKI="$EASYRSA_DIR/pki"
export EASYRSA_BATCH=1
export EASYRSA_REQ_CN='SpiderPanel OpenVPN CA'
export EASYRSA_CERT_EXPIRE=825
export EASYRSA_CRL_DAYS=3650
cat > "$EASYRSA_DIR/vars" <<'VARS'
set_var EASYRSA_CERT_EXPIRE 825
set_var EASYRSA_CRL_DAYS 3650
VARS
chmod 0600 "$EASYRSA_DIR/vars"
cd "$EASYRSA_DIR"
log 'ساخت CA و گواهی سرور…'
"$EASYRSA_DIR/easyrsa" --batch init-pki
"$EASYRSA_DIR/easyrsa" --batch build-ca nopass
"$EASYRSA_DIR/easyrsa" --batch build-server-full server nopass
"$EASYRSA_DIR/easyrsa" --batch gen-crl

install -o root -g root -m 0644 "$EASYRSA_DIR/pki/ca.crt" "$SERVER_DIR/ca.crt"
install -o root -g root -m 0644 "$EASYRSA_DIR/pki/issued/server.crt" "$SERVER_DIR/server.crt"
install -o root -g root -m 0600 "$EASYRSA_DIR/pki/private/server.key" "$SERVER_DIR/server.key"
install -o root -g root -m 0644 "$EASYRSA_DIR/pki/crl.pem" "$SERVER_DIR/crl.pem"
chmod 0700 "$EASYRSA_DIR/pki/private"
openvpn --genkey tls-crypt "$SERVER_DIR/ta.key"
chmod 0600 "$SERVER_DIR/ta.key"

cat > "$SERVER_DIR/server.conf" <<'CONF'
port 1194
proto udp
dev tun
user nobody
group nogroup
persist-key
persist-tun
topology subnet
server 10.8.0.0 255.255.255.0
ifconfig-pool-persist /var/lib/openvpn/ipp.txt
push "redirect-gateway def1 bypass-dhcp"
push "dhcp-option DNS 1.1.1.1"
push "dhcp-option DNS 9.9.9.9"
keepalive 10 120
ca ca.crt
cert server.crt
key server.key
dh none
tls-crypt ta.key
crl-verify crl.pem
tls-version-min 1.2
verify-client-cert require
remote-cert-tls client
auth SHA256
data-ciphers AES-256-GCM:AES-128-GCM:CHACHA20-POLY1305
explicit-exit-notify 1
verb 3
CONF
chmod 0644 "$SERVER_DIR/server.conf"

# Add a single idempotent NAT rule via systemd. We never flush the ruleset.
cat > /usr/local/sbin/spider-openvpn-nat <<NAT
#!/bin/sh
set -eu
WAN_IF='$WAN_IF'
if ! /usr/sbin/iptables -t nat -C POSTROUTING -s 10.8.0.0/24 -o "\$WAN_IF" -j MASQUERADE 2>/dev/null; then
  /usr/sbin/iptables -t nat -A POSTROUTING -s 10.8.0.0/24 -o "\$WAN_IF" -j MASQUERADE
fi
NAT
chmod 0750 /usr/local/sbin/spider-openvpn-nat
chown root:root /usr/local/sbin/spider-openvpn-nat
cat > /etc/systemd/system/spider-openvpn-nat.service <<'UNIT'
[Unit]
Description=SpiderPanel OpenVPN NAT rule
After=network-online.target
Wants=network-online.target
Before=openvpn-server@server.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/spider-openvpn-nat
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
UNIT

cat > /etc/sysctl.d/99-spider-openvpn.conf <<'SYSCTL'
net.ipv4.ip_forward=1
SYSCTL
sysctl -q -w net.ipv4.ip_forward=1

# UFW modifications are additive only; no rules are deleted.
if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q 'Status: active'; then
  ufw allow 1194/udp
  ufw route allow in on tun0 out on "$WAN_IF" from 10.8.0.0/24 to any
fi

# Install the fixed, allow-listed control helper. Its commands are hard-coded;
# it never accepts arbitrary paths or shell commands from API input.
install -o root -g root -m 0750 "$SCRIPT_DIR/spider-openvpnctl" /usr/local/sbin/spider-openvpnctl

systemctl daemon-reload
systemctl enable --now spider-openvpn-nat.service
systemctl enable --now openvpn-server@server.service

# SpiderPanel's upstream installer uses /etc/spider-panel.env and runs its unit
# as root. Keep existing unrelated environment settings unchanged.
ENV_FILE=/etc/spider-panel.env
TMP_ENV="$(mktemp /tmp/spider-panel-env.XXXXXX)"
if [[ -f "$ENV_FILE" ]]; then
  grep -v '^SPIDER_OPENVPN_' "$ENV_FILE" > "$TMP_ENV" || true
fi
cat >> "$TMP_ENV" <<ENV
SPIDER_OPENVPN_PUBLIC_HOST=$PUBLIC_HOST
SPIDER_OPENVPN_PORT=1194
SPIDER_OPENVPN_PROTO=udp
SPIDER_OPENVPN_CTL=/usr/local/sbin/spider-openvpnctl
SPIDER_OPENVPN_USE_SUDO=0
SPIDER_OPENVPN_REQUIRE_HTTPS=1
SPIDER_OPENVPN_DB=$APP_DIR/data/openvpn.sqlite3
ENV
install -o root -g root -m 0600 "$TMP_ENV" "$ENV_FILE"
rm -f "$TMP_ENV"

if ! systemctl is-active --quiet openvpn-server@server.service; then
  journalctl -u openvpn-server@server.service -n 40 --no-pager || true
  fail 'سرویس OpenVPN بعد از نصب فعال نشد؛ لاگ بالا را بررسی کن.'
fi

log 'پیکربندی اولیه تمام شد.'
printf '\nآدرس: %s\nپورت: UDP/1194\n\n' "$PUBLIC_HOST"
printf 'اگر از فایروال پنل شرکت VPS استفاده می‌کنی، UDP/1194 را آنجا هم باز کن.\n'
printf 'کلید خصوصی CA روی همین سرور است و فقط دسترسی root دارد؛ این موضوع را در مدل تهدید خود لحاظ کن.\n'
printf 'اکنون فایل‌های افزونه را کنار /opt/SpiderPanel/main.py قرار بده، patch را اجرا کن و سپس: systemctl restart spider-panel\n'
printf 'صفحهٔ افزونه پس از راه‌اندازی از مسیر /openvpn در دسترس خواهد بود.\n'
