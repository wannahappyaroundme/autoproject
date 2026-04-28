# 시리얼 프로토콜 — RPi ↔ Arduino

USB 시리얼, **115200 bps**, JSON 라인 1줄(`\n` 종결).

## RPi → Arduino (명령)

### `move` — 주행 명령
```json
{"cmd":"move","speed":0.5,"steer":-0.2}
```
| 필드 | 범위 | 의미 |
|------|------|------|
| `speed` | -1.0 ~ +1.0 | 양수=전진, 음수=후진. PWM에 매핑 (데드존 보정 자동) |
| `steer` | -1.0 ~ +1.0 | 음수=좌, 양수=우. 서보 ±35° 매핑 |

### `roller` — 수거 롤러
```json
{"cmd":"roller","on":true,"speed":0.7}
```
- `on=false` 시 즉시 정지
- `speed` 양수=수거 방향, 음수=배출 방향 (롤러 2개 동시 제어)

### `stop` — 모든 모터 정지
```json
{"cmd":"stop"}
```

### `reset_yaw` — IMU yaw 영점 리셋
```json
{"cmd":"reset_yaw"}
```

### `ping` — 헬스체크 (응답은 다음 텔레메트리)
```json
{"cmd":"ping"}
```

---

## Arduino → RPi (텔레메트리, 10Hz)

```json
{"t":12345,"us":[52,30,80,100,25],"imu":{"yaw":1.571,"pitch":0.012,"roll":-0.008,"ok":true},"motor":{"speed":0.500,"steer":-0.200},"roller":false,"safe":true,"err":null}
```

| 필드 | 의미 |
|------|------|
| `t` | Arduino `millis()` 타임스탬프 (ms) |
| `us[5]` | HC-SR04 거리 (cm). 인덱스: `[전, 좌, 우, 후, 수거함내부]`. `null`=timeout/미감지 |
| `imu.yaw/pitch/roll` | rad. yaw는 gyro Z 적분 (drift 있음, `reset_yaw`로 보정) |
| `imu.ok` | I2C 통신 정상 여부 |
| `motor.speed` | 실제 적용된 속도 (안전 차단 시 0) |
| `motor.steer` | 실제 적용된 조향 |
| `roller` | 롤러 작동 여부 |
| `safe` | 안전 OK. `false`면 Arduino가 자체 정지 중 |
| `err` | 차단 사유: `front_obstacle` / `rear_obstacle` / `left_obstacle` / `right_obstacle` / `watchdog` / `null` |

### 부팅 메시지 (한 번만)
```json
{"event":"boot","imu":true}
```

---

## 안전 동작 (Arduino 자율)

RPi 명령보다 우선:
1. **충돌 임박**: 전방 < 15cm + speed > 0 → 즉시 정지, `err="front_obstacle"`
2. **워치독**: 500ms간 명령 없으면 자동 정지, `err="watchdog"`
3. **측면 근접**: 좌/우 < 10cm → 정지, `err="left_obstacle"` / `"right_obstacle"`

→ RPi는 `safe=false`일 때 후진 + 회전으로 빠져나오는 행동 필요.
