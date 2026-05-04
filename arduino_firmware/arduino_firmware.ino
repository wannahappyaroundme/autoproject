/*
 * 자율 음식물쓰레기통 수거 로봇 — Arduino Mega 펌웨어 (RC-car 구조)
 *
 * 동작 모델:
 *   - 전후진: Motor#1 양쪽 채널이 같은 방향/속도로 회전 (좌우 동시)
 *   - 조향: Motor#2 ENA에 연결된 랙&피니언 모터 직접 PWM 제어
 *   - 롤러: Motor#2 ENB에 연결, on/off + 방향
 *
 * 통신: USB Serial @ 115200, JSON 라인 1줄 단위
 *
 * 안전: 충돌 임박 시 RPi 명령 무시하고 즉시 정지 (조향은 살림)
 *       워치독 500ms (RPi 명령 끊기면 자동 정지)
 */

#include "config.h"
#include "motors.h"
#include "ultrasonic.h"
#include "imu.h"
#include "safety.h"
#include "proto.h"

static float    curDriveSpeed = 0;   // -1.0 ~ +1.0 (전후진)
static float    curSteerSpeed = 0;   // -1.0 ~ +1.0 (조향 모터 PWM, 0 = 정지)
static bool     rollerOn = false;
static float    rollerSpd = 0;
static uint32_t lastCmdMs = 0;
static uint32_t lastLoopMs = 0;
static bool     g_imuOk = false;     // IMU 미장착 시 false → I2C hang 방지

void setup() {
  Serial.begin(SERIAL_BAUD);
  while (!Serial && millis() < 2000);

  motorsBegin();
  ultrasonicBegin();
  g_imuOk = imuBegin();

  motorsAllStop();

  Serial.print(F("{\"event\":\"boot\",\"imu\":"));
  Serial.print(g_imuOk ? F("true") : F("false"));
  Serial.println('}');

  lastCmdMs = millis();
}

void loop() {
  uint32_t now = millis();

  // ── 1) 명령 수신 ──
  Command cmd;
  if (protoReadCommand(cmd)) {
    lastCmdMs = now;
    switch (cmd.type) {
      case Command::DRIVE:
        curDriveSpeed = cmd.speed;
        break;
      case Command::STEER:
        curSteerSpeed = cmd.speed;
        break;
      case Command::ROLLER:
        rollerOn  = cmd.rollerOn;
        rollerSpd = cmd.speed;
        break;
      case Command::STOP:
        curDriveSpeed = 0;
        curSteerSpeed = 0;
        rollerOn = false;
        break;
      case Command::RESET_YAW:
        if (g_imuOk) imuResetYaw();
        break;
      case Command::PING:
        break;
      default: break;
    }
  }

  // ── 2) 100ms 주기로만 센서 + 제어 + 텔레메트리 ──
  if (now - lastLoopMs < LOOP_PERIOD_MS) return;
  lastLoopMs = now;

  uint16_t us[5];
  ultrasonicReadAll(us);
  ImuData imu = g_imuOk ? imuRead() : ImuData{0, 0, 0, false};

  // 워치독: RPi 명령 끊긴 지 오래되면 모든 모터 정지
  bool watchdogTrip = (now - lastCmdMs > WATCHDOG_MS);
  if (watchdogTrip) {
    curDriveSpeed = 0;
    curSteerSpeed = 0;
    rollerOn = false;
  }

  // 안전 체크 (전후진 방향만 체크, 조향은 위험 X 이라 그대로 진행)
  bool safe = safetyCheck(us, curDriveSpeed);
  const char* err = nullptr;
  float effDrive = curDriveSpeed;
  if (!safe) {
    effDrive = 0;
    err = safetyLastReason();
  } else if (watchdogTrip) {
    err = "watchdog";
    safe = false;
  }

  // ── 3) 안전 캡 + 가속 램프 (하드웨어 보호) ──
  static float driveApplied = 0, steerApplied = 0, rollerApplied = 0;

  float tDrive  = constrain(effDrive,       -MAX_DRIVE_SPEED,  MAX_DRIVE_SPEED);
  float tSteer  = constrain(curSteerSpeed,  -MAX_STEER_SPEED,  MAX_STEER_SPEED);
  float tRoller = (rollerOn && safe) ? constrain(rollerSpd, -MAX_ROLLER_SPEED, MAX_ROLLER_SPEED) : 0;

  // 램프: 목표값에 사이클당 maxDelta씩 점진 접근
  #define RAMP(applied, target, maxDelta) do { \
    float _d = (target) - (applied); \
    if (fabs(_d) > (maxDelta)) _d = (_d > 0) ? (maxDelta) : -(maxDelta); \
    (applied) += _d; \
  } while(0)
  RAMP(driveApplied,  tDrive,  DRIVE_RAMP_PER_CYCLE);
  RAMP(steerApplied,  tSteer,  STEER_RAMP_PER_CYCLE);
  RAMP(rollerApplied, tRoller, ROLLER_RAMP_PER_CYCLE);

  // 액추에이터 적용
  driveBoth(driveApplied);
  steerSet(steerApplied);
  rollerMotor.set(rollerApplied);

  // 텔레메트리 송신 (실제 적용된 램프 후 값 보고)
  protoSendTelemetry(now, us, imu, driveApplied, steerApplied,
                     rollerOn, rollerApplied, safe, err);
}
