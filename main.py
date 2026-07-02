import os
import requests
import pandas as pd
import time
import logging
from datetime import datetime, timedelta

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
)
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────
GETTOKEN_URL = 'http://www.vehtec.ai/api/VTService.svc/GetToken'
STATUS_URL   = 'http://www.vehtec.ai/api/VTService.svc/GetVehicleStatus'
BACKEND_URL  = 'https://backend-tdm-qa.onrender.com/gpsdata'

TARGET_PLATES = [
    '73-3484',
    '73-3485',
    '73-3483',
    '73-3486',
    '73-3556',
    '73-3554',
    '73-3552',
    '73-3560',
    '73-3558',
    '73-3557'
]
PLATE_TYPE    = 'H'
GPS_VENDOR    = 'songdee'  # ต้องตรงกับ gps_vendor ที่ลงทะเบียนใน backend DB

TIMEOUT = 15
# vehtec ส่งเวลาเป็นเวลาไทยอยู่แล้ว → 0; ถ้าเป็น UTC ให้เปลี่ยนเป็น 7
TIME_OFFSET_HOURS = 0


def load_env_file(path: str = '.env') -> None:
    """โหลด .env แบบง่าย ๆ สำหรับรัน local (Jenkins ใช้ env จริง)"""
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip())


def pick(d: dict, *names):
    """หา key แบบไม่สนตัวพิมพ์เล็กใหญ่/ขีดล่าง — กัน API เปลี่ยนรูปแบบชื่อ field"""
    lookup = {str(k).lower().replace('_', ''): v for k, v in d.items()}
    for name in names:
        v = lookup.get(name.lower().replace('_', ''))
        if v is not None:
            return v
    return None


# ── Step 1: Get Token ─────────────────────────────────────────────────
def get_token(username: str, password: str) -> str:
    r = requests.get(
        GETTOKEN_URL,
        params={'username': username, 'password': password},
        timeout=TIMEOUT,
    )
    r.raise_for_status()

    # รูปแบบจริง: JSON object เช่น {"vResponseCode":"5"} ตอน login fail
    # ตอนสำเร็จคาดว่า token (hex ยาว) อยู่ใน field เช่น vToken — หาแบบยืดหยุ่น
    try:
        data = r.json()
    except ValueError:
        data = r.text

    token = ''
    if isinstance(data, str):
        token = data.strip().strip('"')
    elif isinstance(data, dict):
        token = str(
            pick(data, 'vToken', 'token', 'jtoken', 'GetTokenResult', 'd') or ''
        ).strip()
        if not token:
            # fallback: หา value ที่หน้าตาเป็น token (hex ยาว ≥ 16 ตัว)
            import re
            for v in data.values():
                if isinstance(v, str) and re.fullmatch(r'[A-Fa-f0-9]{16,}', v):
                    token = v
                    break

    if not token or len(token) < 16:
        raise RuntimeError(f'GetToken failed (เช็ค username/password): {data!r}')

    log.info(f'GetToken OK — token={token[:8]}…')
    return token


# ── Step 2: Get Vehicle Status ────────────────────────────────────────
def get_vehicle_status(token: str) -> list:
    r = requests.get(STATUS_URL, params={'jtoken': token}, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()

    # รูปแบบจริง: {"vResponseCode": 0, "vTotalRecords": 48, "vData": [...]}
    if isinstance(data, dict):
        code = pick(data, 'vResponseCode')
        if code is not None and str(code) != '0':
            raise RuntimeError(f'GetVehicleStatus failed (vResponseCode={code}) — token อาจหมดอายุ')
        wrapped = pick(data, 'vData', 'GetVehicleStatusResult', 'd', 'data', 'vehicles', 'result')
        if isinstance(wrapped, list):
            data = wrapped
        else:
            raise RuntimeError(f'Unexpected GetVehicleStatus response: {str(data)[:300]}')

    if not isinstance(data, list):
        raise RuntimeError(f'Unexpected GetVehicleStatus response: {str(data)[:300]}')

    log.info(f'GetVehicleStatus OK — {len(data)} vehicles in account')
    return data


def match_plate(vehicle_no: str) -> str | None:
    """คืนทะเบียนเป้าหมายถ้า vehicle no ของ vehtec ตรงกับ TARGET_PLATES"""
    cleaned = str(vehicle_no or '').replace(' ', '')
    for plate in TARGET_PLATES:
        if plate in cleaned:
            return plate
    return None


def parse_vehicle(v: dict) -> dict:
    """field names ตาม response จริงของ vehtec (ทดสอบ 12/06/2026)"""
    return {
        'vehicle_no': pick(v, 'vehicleno'),
        'unit_id'   : pick(v, 'unitno'),
        'gps_status': pick(v, 'gps'),                       # "A" = active
        'driver'    : pick(v, 'drivername'),
        'address'   : pick(v, 'location'),
        'lat'       : pick(v, 'latitude'),
        'lng'       : pick(v, 'longitude'),
        'speed'     : pick(v, 'speed'),
        'ignition'  : pick(v, 'ignition'),                  # "ON" / "OFF"
        'odometer'  : pick(v, 'odometer'),
        'fuel'      : pick(v, 'fueltank1', 'totalfuel'),
        'datetime'  : pick(v, 'datetime'),                  # "12/06/2026 16:44:11" (เวลาไทย)
        'network'   : pick(v, 'networktype'),
    }


def _to_bkk(dt_str) -> str:
    for fmt in ('%Y-%m-%d %H:%M:%S', '%d/%m/%Y %H:%M:%S', '%Y-%m-%dT%H:%M:%S'):
        try:
            dt = datetime.strptime(str(dt_str), fmt)
            return (dt + timedelta(hours=TIME_OFFSET_HOURS)).strftime('%Y-%m-%d %H:%M:%S')
        except (ValueError, TypeError):
            continue
    return str(dt_str)


def build_payload(df: pd.DataFrame) -> list:
    payload = []
    for _, row in df.iterrows():
        payload.append({
            'gps_id'        : str(row['unit_id'] or ''),
            'plate_master'  : row['plate'],
            'plate_type'    : PLATE_TYPE,
            'gps_vendor'    : GPS_VENDOR,
            'current_latlng': f"{row['lat']},{row['lng']}" if row['lat'] and row['lng'] else '',
            'gps_updated_at': _to_bkk(row['datetime']),
            'status'        : 'หยุด' if (row['speed'] or 0) == 0 else 'วิ่ง',
        })
    return payload


def post_to_backend(payload: list) -> None:
    resp = requests.post(
        BACKEND_URL,
        json=payload,
        headers={'Content-Type': 'application/json'},
        timeout=30,
    )
    resp.raise_for_status()
    result = resp.json() if resp.text else []
    updated = len([r for r in result if r.get('gps_updated_at')])
    log.info(f'POST {resp.status_code} — sent={len(payload)}, updated={updated}')


def main():
    log.info(f'=== VehTec GPS sync started — {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} ===')

    load_env_file()
    username = os.environ.get('VEHTEC_USERNAME', '')
    password = os.environ.get('VEHTEC_PASSWORD', '')
    if not username or not password:
        raise SystemExit('Missing VEHTEC_USERNAME / VEHTEC_PASSWORD env vars')

    # Step 1 — token
    token = get_token(username, password)

    # Step 2 — vehicle status (ทุกคันในบัญชี)
    vehicles = get_vehicle_status(token)

    # filter เฉพาะทะเบียนเป้าหมาย
    rows = []
    for v in vehicles:
        parsed = parse_vehicle(v)
        plate = match_plate(parsed['vehicle_no'])
        if not plate:
            continue
        rows.append({**parsed, 'plate': plate})
        log.info(
            f"{plate}  unit={parsed['unit_id']}  lat={parsed['lat']}  lng={parsed['lng']}  "
            f"speed={parsed['speed']}  odo={parsed['odometer']}  fuel={parsed['fuel']}  "
            f"dt={parsed['datetime']}  driver={parsed['driver']}"
        )

    log.info(f'Matched {len(rows)}/{len(TARGET_PLATES)} target plates')
    missing = set(TARGET_PLATES) - {r['plate'] for r in rows}
    if missing:
        log.warning(f'Plates not found in account: {sorted(missing)}')

    if not rows:
        log.error('No target vehicles found — aborting POST')
        return

    df = pd.DataFrame(rows)
    payload = build_payload(df)
    post_to_backend(payload)
    log.info('=== Done ===')


if __name__ == '__main__':
    main()
