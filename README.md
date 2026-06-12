# vehtec-gps-sync

ดึง GPS จาก **VehTec API** (www.vehtec.ai) แล้วส่งเข้า backend TDM ทุก 10 นาที — โครงเดียวกับ `hino-gps-sync`

## Flow

1. **GetToken** — `GET /api/VTService.svc/GetToken?username=&password=` → ได้ token ชั่วคราว
2. **GetVehicleStatus** — `GET /api/VTService.svc/GetVehicleStatus?jtoken=<token>` → สถานะรถทุกคันในบัญชี
3. Filter เฉพาะทะเบียนเป้าหมาย: `73-3484, 73-3485, 73-3483, 73-3486` (แก้ใน `TARGET_PLATES` ใน main.py)
4. POST เข้า `https://backend-tdm-qa.onrender.com/gpsdata` payload เดียวกับ hino (`gps_vendor: "vehtec"`)

## Run local

```bash
cp .env.example .env   # ใส่ username/password จริง
python3 -m venv venv && venv/bin/pip install -r requirements.txt
venv/bin/python main.py
```

## Jenkins

1. สร้าง credential แบบ **Username with password** ใน Jenkins, id = `vehtec-api`
2. สร้าง Pipeline job ชี้มาที่ repo นี้ (ใช้ Jenkinsfile ในตัว) — cron ทุก 10 นาทีตั้งไว้แล้ว

## หมายเหตุ

- โค้ด parse response แบบยืดหยุ่น (รองรับ key หลายแบบ เช่น `GetTokenResult`/`d`, `VehicleNo`/`plateno`)
  เพราะยังไม่ได้ยิงกับ response จริง — **ครั้งแรกที่รันด้วย credential จริง ให้เช็ค log**
  ว่า field map ถูก ถ้าชื่อ field ไม่ตรงให้เพิ่มใน `parse_vehicle()`
- ถ้าเวลาที่ได้จาก vehtec เป็น UTC (ไม่ใช่เวลาไทย) ให้แก้ `TIME_OFFSET_HOURS = 7` ใน main.py
