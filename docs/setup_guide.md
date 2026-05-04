# 시제품 셋업 가이드 — 처음부터 끝까지

코드만 있다고 로봇이 움직이는 건 아닙니다. 아래 7단계 순서대로 진행하세요.

```
[1] PC 환경 준비          ─ Arduino IDE 설치, 코드 다운로드
[2] RPi OS 설치           ─ Raspberry Pi Imager + SD카드
[3] RPi 부팅 + SSH        ─ WiFi 연결, 원격 접속 환경
[4] RPi 소프트웨어 설치   ─ setup_rpi.sh 한 방
[5] Arduino 펌웨어 업로드 ─ Arduino IDE → Mega
[6] 하드웨어 결선         ─ docs/wiring_diagram.md 따라
[7] 실행 + 동작 검증      ─ web_control.py + 폰 브라우저
```

---

## 0. 준비물 (체크리스트)

### 하드웨어
- [ ] PC 또는 Mac (Arduino IDE 실행용)
- [ ] Raspberry Pi 4 (4GB) + 공식 5V 어댑터
- [ ] **MicroSD 카드 32GB+ (Class 10 권장)**
- [ ] **USB SD카드 리더기** (없으면 RPi OS 못 굽음)
- [ ] Arduino Mega 2560 + USB-B 케이블 (Arduino ↔ PC/RPi)
- [ ] 7.4V LiPo (로직용), 12V LiPo (모터용) — 충전된 상태
- [ ] L298N ×2, NP01D-288 ×2, JGA25-370 ×2 (조향+롤러)
- [ ] HC-SR04 ×5
- [ ] (옵션) MPU-9250
- [ ] RPi Camera Module 3 (CSI 케이블 포함), 웹캠 AU100
- [ ] XL4015 ×2, LM2596HV
- [ ] 빵판, 점퍼선, 4.7kΩ 저항 ×2 (IMU 사용 시만)
- [ ] **멀티미터** (컨버터 출력 검증, 필수)
- [ ] (있으면) 비상정지 버튼, 토글 스위치, 퓨즈, 캡, 페라이트

### 소프트웨어 (이번 가이드에서 설치할 것)
- [ ] Arduino IDE 2.x
- [ ] Raspberry Pi Imager
- [ ] (선택) Git, VS Code Remote SSH

---

## 1단계 — PC 환경 준비 (PC 또는 Mac)

### 1-1. Arduino IDE 설치
1. 브라우저: https://www.arduino.cc/en/software
2. **Arduino IDE 2.x** 다운로드 (Windows / macOS / Linux)
3. 설치 후 실행

### 1-2. 프로젝트 코드 다운로드
**옵션 A — Git 사용 (권장, 업데이트 쉬움)**:
```bash
# Mac/Linux 터미널 또는 Windows Git Bash
git clone https://github.com/wannahappyaroundme/autoproject.git
cd autoproject
```

**옵션 B — ZIP 다운로드**:
1. GitHub 저장소 페이지 → "Code" 버튼 → "Download ZIP"
2. 압축 풀기 → 폴더 위치 기억해두기 (예: `~/Desktop/autoproject/`)

---

## 2단계 — Raspberry Pi OS 설치 (PC에서 SD카드 굽기)

### 2-1. Raspberry Pi Imager 설치
1. https://www.raspberrypi.com/software/
2. OS에 맞는 버전 다운로드 → 설치 → 실행

### 2-2. SD카드 굽기
1. SD카드를 PC에 꽂기
2. Imager 실행 → **3개 버튼 선택**:
   - **Device**: Raspberry Pi 4
   - **Operating System** → "Raspberry Pi OS (64-bit)" — Bookworm 권장
   - **Storage**: 꽂은 SD카드 선택
3. **"NEXT"** → **"EDIT SETTINGS"** (⚙️ 톱니 아이콘)
4. **General 탭**:
   - ✅ Set hostname: `autorobot`
   - ✅ Set username and password: `pi` / `(원하는 비밀번호)`
   - ✅ Configure wireless LAN:
     - SSID: `(WiFi 이름)`
     - Password: `(WiFi 비밀번호)`
     - Country: `KR`
   - ✅ Set locale: Time zone `Asia/Seoul`, Keyboard layout `us`
5. **Services 탭**:
   - ✅ **Enable SSH** → "Use password authentication"
6. **Save** → **YES** → 비밀번호 입력
7. 굽기 완료까지 대기 (~5분)

### 2-3. SD카드 RPi에 꽂기
1. PC에서 SD카드 안전하게 빼기
2. 라즈베리파이 4의 SD카드 슬롯에 삽입 (방향 주의)
3. 5V 어댑터 꽂기 → 빨강 LED 점등 → 부팅 시작 (~30초)

---

## 3단계 — RPi 첫 로그인 (SSH로 PC에서 원격 접속)

### 3-1. RPi의 IP 주소 찾기
**옵션 A — `ping autorobot.local` (Mac/Linux 또는 Windows 11)**:
```bash
ping autorobot.local
# → 응답에서 IP 확인 (예: 192.168.1.50)
```

**옵션 B — 공유기 관리자 페이지**:
1. 공유기 IP (보통 192.168.1.1) 접속
2. 연결된 기기 목록에서 "raspberrypi" 또는 "autorobot" 찾기

### 3-2. SSH 접속
PC 터미널에서:
```bash
ssh pi@autorobot.local
# 또는
ssh pi@192.168.1.50

# 첫 접속 시 "yes" 입력 → 비밀번호 입력
```

성공하면 프롬프트가 `pi@autorobot:~ $` 로 바뀜.

### 3-3. (선택) VS Code Remote SSH
편하게 코드 보면서 작업하려면:
1. PC에 VS Code 설치
2. 확장 "Remote - SSH" 설치
3. F1 → "Remote-SSH: Connect to Host" → `pi@autorobot.local`
4. 연결되면 `/home/pi/` 폴더 직접 편집 가능

---

## 4단계 — RPi에 소프트웨어 설치

SSH로 RPi에 접속한 상태에서:

### 4-1. 프로젝트 클론
```bash
cd ~
git clone https://github.com/wannahappyaroundme/autoproject.git
cd autoproject
```

### 4-2. 한 방 설치 스크립트 실행
```bash
bash setup_rpi.sh
```

이게 자동으로 처리하는 것:
- apt 패키지: `python3-pip`, `python3-venv`, `libzbar0`, `python3-picamera2`, `i2c-tools`
- 카메라/I2C/시리얼 활성화 (raspi-config)
- `dialout` 그룹에 사용자 추가 (Arduino 시리얼 권한)
- Python venv 생성 + pip 패키지 설치

### 4-3. 재부팅 (그룹 권한 적용)
```bash
sudo reboot
```
30초 후 다시 SSH 접속:
```bash
ssh pi@autorobot.local
cd ~/autoproject
source .venv-rpi/bin/activate     # 이후 모든 작업 시 venv 활성화
```

### 4-4. 카메라 동작 확인
```bash
libcamera-hello --timeout 3000
# → 화면에 카메라 영상 3초간 표시 (X 환경 또는 SSH X-forwarding 필요)
# 또는 캡처:
libcamera-jpeg -o test.jpg --timeout 1000
ls test.jpg     # 파일 생기면 성공
```

---

## 5단계 — Arduino 펌웨어 업로드

### 5-1. Arduino IDE에서 폴더 열기
1. Arduino IDE 실행
2. **File → Open** → `autoproject/arduino_firmware/arduino_firmware.ino` 선택
3. 폴더 안에 `config.h`, `motors.cpp/h`, `imu.cpp/h` 등 모듈이 모두 보여야 정상 (탭으로 표시됨)

### 5-2. 보드/포트 선택
1. **Tools → Board → Arduino AVR Boards → Arduino Mega or Mega 2560**
2. **Tools → Processor → ATmega2560 (Mega 2560)**
3. Arduino를 PC에 USB로 연결
4. **Tools → Port** → 새로 나타난 포트 선택
   - Mac: `/dev/cu.usbserial-XXX` 또는 `/dev/cu.usbmodem*`
   - Windows: `COM3`, `COM4` 등
   - Linux: `/dev/ttyACM0`, `/dev/ttyUSB0`
   - **CH340 칩 모델일 때는 별도 드라이버 설치 필요** (Arduino IDE가 안내)

### 5-3. 업로드
1. ✓ 체크 버튼 (좌상단) → 컴파일 확인 (에러 없어야 함)
2. → 화살표 버튼 → 업로드
3. 콘솔 하단에 `avrdude: ... bytes of flash verified` 보이면 성공

### 5-4. 시리얼 모니터로 부팅 확인
1. **Tools → Serial Monitor** (또는 우상단 돋보기)
2. 우하단 baud rate를 **115200** 으로 설정
3. Arduino 리셋 버튼 누르거나 USB 다시 꽂기
4. 다음 메시지가 한 번 떠야 정상:
```
{"event":"boot","imu":true}     ← MPU 연결 시
{"event":"boot","imu":false}    ← MPU 미장착 (정상)
```
5. 10Hz로 텔레메트리 스트림이 계속 흐름:
```
{"t":1234,"us":[null,null,null,null,null],"imu":...,"drive":0.000,...}
```
HC-SR04 미연결이면 us는 모두 `null`. 모터 미연결이어도 정상 동작.

---

## 6단계 — 하드웨어 결선

⚠️ **중요**: 결선 작업은 **반드시 두 배터리 모두 분리한 상태**에서.

### 6-1. 전체 결선표 참조
[docs/wiring_diagram.md](wiring_diagram.md) — 12개 섹션 중:
- §1: 전원 분배 (LiPo → 컨버터 → L298N)
- §3: Arduino 핀 매핑 (Motor#1, Motor#2, HC-SR04)
- §4-5: L298N 결선 (점퍼 제거 ⚠️)
- §10: 통전 검증 5단계

### 6-2. 조립 순서 (요약)
1. **6층 적층 구조 PLA 출력** (`autoproject.3mf` 또는 별도 모델링)
2. **Layer 1 (하단)**: 모터 4개 + 휠 + 랙기어
3. **Layer 2**: 배터리 마운트 + L298N ×2 (점퍼 제거 확인!)
4. **Layer 3**: Arduino + XL4015 ×2 + LM2596HV + 빵판
5. **Layer 4**: RPi + 쿨링팬
6. **Layer 5**: 피니언 기어 (조향용) + 롤러 마운트
7. **Layer 6 (상단)**: 카메라 ×2 + HC-SR04 ×5

### 6-3. 통전 검증 (배터리 연결 직전)
1. **멀티미터로 단락 체크**: LiPo (+) ↔ GND 사이 저항 측정 → **>1kΩ** (단락 없음 확인)
2. **로직 배터리(7.4V)만** 먼저 연결
3. 멀티미터로 측정:
   - XL4015 #1 출력: **5.10V ± 0.05** (가변저항 돌려서 조정)
   - LM2596HV 출력: **5.00V ± 0.05**
4. **모터 배터리(12V)** 연결
5. **XL4015 #2 출력: 7.4V ± 0.1** ⚠️ (반드시 확인! 12V 그대로면 모터 소손)
6. RPi 부팅 LED + Arduino LED 점등 확인

---

## 7단계 — 실행 + 동작 검증

### 7-1. RPi → Arduino USB 연결
1. RPi의 **파란색 USB 3.0 포트**에 Arduino USB-B 케이블 꽂기
2. Arduino LED 점등 확인

### 7-2. 시리얼 포트 확인
RPi에서:
```bash
ls /dev/ttyACM* /dev/ttyUSB*
# → /dev/ttyACM0 보이면 정상
```

### 7-3. 텔레메트리만 먼저 확인 (모터 X)
```bash
cd ~/autoproject
source .venv-rpi/bin/activate
python -m tools.telemetry_monitor
```
화면에 거리/IMU 값이 실시간 표시. **손을 전방 센서에 가까이 → 거리 감소** 확인.

### 7-4. 웹서버 실행
```bash
python -m tools.web_control
```
콘솔 출력:
```
======================================================
  로봇 수동 조종 웹서버 시작 (테스트 모드: 30% 캡)
  같은 WiFi에서 접속: http://192.168.1.50:8080
  로컬:           http://localhost:8080
  종료: Ctrl+C
======================================================
```

### 7-5. 폰 브라우저로 접속
1. **폰을 RPi와 같은 WiFi에 연결**
2. 브라우저 주소창: `http://192.168.1.50:8080` (RPi IP에 맞춤)
3. 화면:
   - 라이브 카메라 영상
   - 방향 패드 (▲▼◀▶ + ■정지)
   - 속도/조향/롤러 슬라이더
   - 실시간 거리 표시

### 7-6. 모터 동작 검증 (차체 들어올린 채로)
**중요**: 첫 동작 시 **반드시 차체 들어올려서** 바퀴 공중에 띄우고 시작.

1. ▲ 전진 버튼 클릭 → 두 바퀴 전진 방향 회전 확인
   - 거꾸로 돌면 → 모터 +/- 선 스왑 또는 IN1↔IN2 핀 스왑
2. ■ 정지 버튼
3. ▼ 후진 → 두 바퀴 후진
4. ◀ 좌 누르고 있기 → 조향 모터 좌측 회전 (랙이 한쪽으로 슬라이드)
5. ▶ 우 누르고 있기 → 반대 방향
6. 롤러 ON → 회전 확인 → 방향 토글 → 반대 회전

**전부 정상이면 차체 내려서 저속 주행 테스트**.

---

## 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| `ssh: Could not resolve hostname autorobot.local` | mDNS 안 됨 | RPi IP를 직접 입력 (공유기에서 확인) |
| Arduino IDE에서 포트 안 보임 | CH340 드라이버 누락 | https://sparks.gogo.co.nz/ch340.html 또는 IDE 안내 따라 설치 |
| `{"event":"boot","imu":false}` | I2C 연결 X 또는 풀업 X | MPU 미장착이면 정상. 장착 시 SDA/SCL 결선 + 4.7kΩ 풀업 확인 |
| HC-SR04 모두 `null` | 5V/GND 미공급 또는 빵판 분배 안 됨 | 빵판 +/- 레인에 LM2596 5V/GND 연결 확인 |
| RPi가 모터 작동 시 리부팅 | 전압 새그 (1배터리 공유 시) | 2200µF 캡 추가, 또는 12V 모터 전용 배터리 분리 (현 설계) |
| 웹페이지에서 "미연결" | 시리얼 포트 잘못, 또는 펌웨어 미업로드 | `ls /dev/ttyACM*`, `python -m tools.telemetry_monitor` 로 직접 검증 |
| 모터가 PWM 무관하게 풀스피드 | L298N 5V 점퍼 안 빠짐 | 점퍼 제거 + 외부 5V 공급 |
| 한쪽 바퀴만 돔 | Motor#1 좌/우 채널 결선 한쪽 끊김 | ENA/ENB, IN1~4 모두 점검 |
| 폰에서 RPi 페이지 접속 안 됨 | 다른 WiFi에 있거나, RPi 방화벽 | 같은 공유기 확인. RPi 기본 방화벽 X (별도 설정 안 했으면 OK) |

---

## (참고) GitHub Pages 버전 사용

폰을 RPi와 다른 네트워크에서 보고 싶으면:
- https://wannahappyaroundme.github.io/autoproject/control 접속
- "라즈베리파이 IP" 입력란에 RPi IP 입력
- ⚠️ HTTPS→HTTP 차단 시 Safari/Chrome 보안 설정 필요. **권장: 폰을 RPi와 같은 WiFi에 두고 RPi IP 직접 접속**.

---

## 자주 쓰는 명령 모음 (RPi)

```bash
# venv 활성화 (모든 Python 작업 전)
source ~/autoproject/.venv-rpi/bin/activate

# 텔레메트리만 보기 (모터 X)
python -m tools.telemetry_monitor

# 웹 수동 조종 (메인)
python -m tools.web_control

# 키보드 수동 조종 (SSH 환경)
python -m tools.manual_control

# QR 코드 생성 (빈에 부착)
python tools/generate_qr.py

# Arduino 시리얼 포트 확인
ls /dev/ttyACM*

# I2C 디바이스 스캔 (MPU 연결 확인용)
sudo i2cdetect -y 1
# → 0x68 또는 0x69 떠야 정상

# RPi 셧다운 (SD카드 손상 방지)
sudo shutdown -h now
```
