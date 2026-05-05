# Windows(삼성 노트북) 셋업 가이드 — 처음부터 끝까지

Mac이 USB-C만 있어서 USB 메모리 인식이 까다로울 때, Windows 노트북으로 진행하는 전체 가이드.
Mac 없이 Windows만으로도 모든 작업 가능.

```
[1] 준비물 확인
[2] Windows에 도구 설치 (Imager + Git + 터미널)
[3] USB 메모리에 RPi OS 굽기
[4] RPi 부팅 + SSH 접속 (Windows에서)
[5] RPi에 코드 설치
[6] Arduino 펌웨어 업로드 (WiFi 통해)
[7] 종합 진단
[8] 웹 조종 시작
```

---

## 0. 준비물

### 하드웨어
- [ ] 삼성 노트북 (Windows 10/11)
- [ ] **USB 메모리 32GB+** (USB-A 일반 사각형, 다이소 ~5,000원)
- [ ] Raspberry Pi 4 (4GB)
- [ ] RPi용 5V 전원 어댑터
- [ ] Arduino Mega + USB-B 케이블 (RPi-Arduino 연결용)
- [ ] WiFi 환경 (RPi와 노트북이 같은 네트워크)
- [ ] (선택) 멀티미터, 빵판, 점퍼선, 4.7kΩ 저항

### 소프트웨어 (이번 가이드에서 설치)
- [ ] Raspberry Pi Imager
- [ ] Git for Windows (또는 GitHub Desktop)
- [ ] Windows Terminal 또는 PowerShell (기본 내장)

---

## 1단계 — Windows 도구 설치

### 1-1. Raspberry Pi Imager 설치
1. https://www.raspberrypi.com/software/
2. **Download for Windows** 클릭
3. 다운로드한 `imager_X.X.X.exe` 실행 → Install → Finish

### 1-2. Git for Windows 설치 (GitHub에서 코드 받기용)
1. https://git-scm.com/download/win
2. 64-bit installer 다운로드 → 실행
3. 설치 옵션 모두 기본값으로 (Next 연타) → Install
4. 설치 후 **Git Bash** 라는 프로그램이 추가됨

### 1-3. SSH 클라이언트 (Windows 10/11 기본 내장)
- Windows 키 → "PowerShell" 검색 → 실행
- `ssh` 입력 → 도움말 나오면 OK
- 안 나오면 (구버전 Windows): https://docs.microsoft.com/ko-kr/windows-server/administration/openssh/openssh_install_firstuse 참조

---

## 2단계 — USB 메모리에 RPi OS 굽기

### 2-1. USB 메모리 노트북에 꽂기
- USB-A 일반 사각형 단자 → 노트북 USB 포트에 직접
- USB-C 단자면 → USB-C 포트에 직접 (삼성 노트북에 USB-C 있을 경우)

### 2-2. Imager로 굽기

1. **Raspberry Pi Imager 실행**
2. **CHOOSE DEVICE** → "Raspberry Pi 4"
3. **CHOOSE OS** → "Raspberry Pi OS (64-bit)" — Bookworm 권장
4. **CHOOSE STORAGE** → 꽂은 USB 메모리 선택
5. **NEXT** → ⚠️ **EDIT SETTINGS** (톱니 아이콘) ⚠️ 반드시 클릭

#### General 탭 — 모두 체크 + 입력
```
☑ Set hostname:               autorobot
☑ Set username and password:
    Username: pi
    Password: (기억할 수 있는 것, 예: 1234)
☑ Configure wireless LAN:
    SSID:     (본인 WiFi 이름, 대소문자 정확히)
    Password: (WiFi 비밀번호)
    Country:  KR
☑ Set locale:
    Time zone:        Asia/Seoul
    Keyboard layout:  us
```

#### Services 탭 — 반드시 SSH 활성화
```
☑ Enable SSH
    ◉ Use password authentication
```

6. **Save** → **Next** → **YES** (덮어쓰기 동의) → **YES** (관리자 권한)
7. 굽기 진행 (~5분) — 끝나면 "Write Successful"

### 2-3. USB 분리 (Eject)
- Windows 우하단 트레이 → "USB 안전하게 제거" 클릭
- 또는 그냥 뽑기 (이미 굽기 끝났으면 OK)

---

## 3단계 — RPi 부팅 + SSH 접속

### 3-1. USB를 RPi에 꽂기

⚠️ **반드시 파란색 USB 3.0 포트** (RPi 후면 안쪽 2개):

```
RPi 4 후면도:
   ┌─────────────────────────────────┐
   │ [Power] [HDMI×2] [3.5mm]        │
   │                                 │
   │ ┌─────┐  ┌─────┐                │
   │ │ USB │  │ USB │                │
   │ │ 3.0 │  │ 3.0 │  ← USB 메모리   │
   │ └─────┘  └─────┘    (파란 안쪽) │
   │ ┌─────┐  ┌─────┐                │
   │ │ USB │  │ USB │                │
   │ │ 2.0 │  │ 2.0 │  ← Arduino     │
   │ └─────┘  └─────┘    (검정 바깥) │
   └─────────────────────────────────┘
```

### 3-2. RPi 전원 인가
- 5V 어댑터를 USB-C 전원 포트(좌상단)에 꽂기
- **빨간 LED** 점등 + **초록 LED** 깜빡임 → 부팅 시작
- 첫 부팅: 1~2분 대기 (WiFi 자동 연결까지)

### 3-3. Windows에서 SSH 접속

**PowerShell 또는 Windows Terminal 실행** (Windows 키 → "PowerShell" 검색):

```powershell
ssh pi@autorobot.local
```

처음 접속 시:
```
The authenticity of host 'autorobot.local' can't be established.
Are you sure you want to continue connecting (yes/no)? yes
pi@autorobot.local's password: (Imager에서 설정한 비밀번호)
```

성공하면 프롬프트가 `pi@autorobot:~ $` 로 바뀜.

### 3-4. 만약 `autorobot.local` 안 되면

**옵션 A**: IP 직접 찾기
```powershell
# Windows 명령 프롬프트에서
arp -a | findstr "dc-a6 b8-27 e4-5f 28-cd"
```
RPi 4 MAC 주소 prefix:
- `dc-a6-32`, `b8-27-eb`, `e4-5f-01`, `28-cd-c1`

찾으면:
```powershell
ssh pi@192.168.X.X
```

**옵션 B**: 공유기 관리 페이지
- 브라우저: `192.168.0.1` 또는 `192.168.1.1`
- 로그인 → 연결된 기기 → `raspberrypi` / `autorobot` 찾기

**옵션 C**: WiFi 비번 오타? Imager로 다시 굽기 (5분).

---

## 4단계 — RPi에 코드 설치

SSH 접속한 상태에서 (`pi@autorobot:~ $` 프롬프트):

### 4-1. 프로젝트 클론
```bash
cd ~
git clone https://github.com/wannahappyaroundme/autoproject.git
cd autoproject
```

### 4-2. 한 방 설치
```bash
bash setup_rpi.sh
```

자동 처리:
- apt 패키지 (Python, libzbar0, picamera2, i2c-tools)
- 카메라/I2C/시리얼/쿨링팬 활성화
- dialout 그룹 (Arduino 시리얼 권한)
- Python venv + pip 패키지

### 4-3. 재부팅 (그룹 권한 적용)
```bash
sudo reboot
```

30초 후 다시 SSH:
```powershell
ssh pi@autorobot.local
```

---

## 5단계 — Arduino 펌웨어 업로드 (WiFi → RPi → USB)

⚠️ **노트북 ↔ Arduino 직접 USB 케이블 연결 X**.
Arduino는 **RPi의 USB-A 포트**에 연결하고, Windows 노트북에서 SSH로 RPi에 명령만 보내면 됨.

### 5-1. Arduino를 RPi에 USB 연결
- Arduino USB-B 케이블 → RPi의 **검정 USB 2.0 포트** (USB 3.0은 USB 메모리가 차지 중)
- Arduino LED 점등 확인

### 5-2. arduino-cli 설치 (1회만)
```bash
cd ~/autoproject
source .venv-rpi/bin/activate
bash tools/setup_arduino_cli.sh
source ~/.bashrc
```

### 5-3. 펌웨어 업로드
```bash
bash tools/flash_arduino.sh
```

성공 출력:
```
[1/2] 컴파일
[2/2] 업로드
✓ 업로드 완료
```

---

## 6단계 — 종합 진단

```bash
python -m tools.diagnose
```

4개 섹션 결과 확인:
1. **RPi 시스템**: OS, CPU 온도, 카메라, I2C
2. **Arduino 시리얼**: 포트, 부팅 메시지
3. **Arduino 부품**: I2C(MPU), 초음파 5개, 모터 핀
4. **라이브 텔레메트리**: 10Hz 정상 흐름

✓ 녹색 / ⚠ 노랑 / ✗ 빨강 으로 어디 정상/문제인지 한눈에 확인.

---

## 7단계 — 웹 수동 조종

### 7-1. 웹서버 실행
```bash
python -m tools.web_control
```

콘솔 출력:
```
======================================================
  로봇 수동 조종 웹서버 시작
  같은 WiFi에서 접속: http://192.168.X.X:8080
======================================================
```

### 7-2. 폰/노트북 브라우저로 접속
- 같은 WiFi 연결 확인
- 브라우저: `http://<RPi-IP>:8080`
- 화면: 카메라 + 방향 패드 + 슬라이더 + 거리 표시

### 7-3. 동작 검증 (⚠️ 차체 들어올린 채로!)
1. ▲ 클릭 → 양쪽 바퀴 전진 회전 확인
2. ◀ 누르고 있기 → 조향 모터 좌측 회전
3. ▶ 누르고 있기 → 우측 회전
4. 롤러 ON → 회전 → 방향 토글 → 반대 회전

거꾸로 돌면 → 모터 +/- 선 스왑 또는 펌웨어 IN1↔IN2 핀 스왑.

---

## 일상 워크플로우 (이후 매번)

### Windows에서 코드 수정 시
```powershell
# Windows에서 git push
cd C:\Users\<당신>\autoproject
git add -A
git commit -m "수정 내용"
git push

# RPi에서 받기
ssh pi@autorobot.local
cd ~/autoproject
git pull
bash tools/flash_arduino.sh   # 펌웨어 업데이트
python -m tools.web_control   # 웹서버 시작
```

### 한 줄로 (SSH 한 번만 들어가도)
```powershell
ssh pi@autorobot.local "cd autoproject && git pull && bash tools/flash_arduino.sh"
```

---

## 트러블슈팅

| 증상 | 해결 |
|------|------|
| `ssh: Could not resolve hostname autorobot.local` | RPi IP 직접 찾아서 `ssh pi@<IP>` |
| `Permission denied (publickey,password)` | 비밀번호 오타. Imager에서 설정한 거 다시 확인 |
| 빨강 LED만 켜지고 초록 안 깜빡 | USB 메모리 부팅 인식 실패. 다시 굽기 또는 다른 USB 포트 |
| WiFi 연결 안 됨 | 비번 오타. Imager로 다시 굽거나, RPi에 모니터+키보드 직결해서 raspi-config |
| `arp -a` 에 RPi 안 보임 | 같은 WiFi 인지 확인. 게스트 WiFi 격리 가능성 |
| Arduino 인식 안 됨 (`/dev/ttyACM0` 없음) | `ls /dev/tty*` 로 확인. USB 케이블 빼서 다시 꽂기 |
| 모터 거꾸로 회전 | 모터 +/- 스왑 또는 `config.h`의 IN1/IN2 핀 번호 스왑 |

---

## 현재 상황별 단축 명령

### 이미 OS 깔린 USB가 있고 SSH만 안 됨
USB를 노트북에 꽂아서 boot 파티션에 빈 `ssh` 파일 추가:
```powershell
# Windows 명령 프롬프트
type nul > E:\ssh
```
(E:는 USB 메모리 드라이브 문자, 본인 환경 따라 다름)

USB 빼서 RPi에 다시 꽂고 부팅 → SSH 활성화됨.

### WiFi 비번도 추가하기 (Bookworm)
```powershell
# Imager로 다시 굽는 게 가장 확실. 5분 걸림.
```
직접 텍스트 파일 추가하는 방법은 Bookworm에서 까다로움. Imager 다시 사용 권장.

---

## 자주 쓰는 RPi 명령 모음

```bash
# venv 활성화 (모든 Python 작업 전)
source ~/autoproject/.venv-rpi/bin/activate

# 텔레메트리 모니터 (모터 동작 X)
python -m tools.telemetry_monitor

# 웹 조종
python -m tools.web_control

# 진단
python -m tools.diagnose

# 펌웨어 재업로드
bash tools/flash_arduino.sh

# Arduino 시리얼 모니터 (RPi에서 직접)
arduino-cli monitor -p /dev/ttyACM0 -c baudrate=115200

# 시리얼 포트 확인
ls /dev/ttyACM*

# 카메라 단독 테스트
libcamera-hello --list-cameras
libcamera-jpeg -o test.jpg --timeout 1000

# CPU 온도 확인
vcgencmd measure_temp

# RPi 셧다운 (SD/USB 손상 방지)
sudo shutdown -h now
```

---

## 핵심 요약

```
[Windows 노트북]
   ├─ Raspberry Pi Imager: USB 메모리에 OS 굽기
   ├─ Git: 코드 push/pull
   └─ PowerShell: ssh pi@autorobot.local

[USB 메모리]
   └─ Mac/Windows에서 OS 굽기 → RPi의 파란 USB 3.0 포트에 꽂기

[Raspberry Pi 4]
   ├─ USB-C: 전원 (5V 어댑터)
   ├─ USB 3.0 #1 (파란색): USB 메모리 (부팅 매체)
   ├─ USB 2.0 (검정): Arduino 본체 USB-B
   ├─ CSI: 라즈베리파이 카메라 모듈 3
   └─ WiFi: 같은 네트워크에 노트북

[Arduino Mega]
   ├─ USB-B → RPi USB 2.0
   └─ 모터/센서 결선 (docs/wiring_diagram.md 참조)
```

→ **노트북과 RPi는 USB 케이블 X, WiFi(SSH)로만 통신**.
→ **노트북과 Arduino는 직접 연결 X, RPi 거쳐 SSH+arduino-cli로 업로드**.

---

## 다음에 할 작업 (이 가이드 완료 후)

- [docs/setup_guide.md](setup_guide.md) — 일반 셋업 (Mac/Linux도 호환)
- [docs/wiring_diagram.md](wiring_diagram.md) — 하드웨어 결선 매뉴얼
- [PROTOCOL.md](../PROTOCOL.md) — RPi-Arduino 시리얼 프로토콜

문제 생기면 `python -m tools.diagnose` 결과를 공유.
