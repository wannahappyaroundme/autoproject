/*
 * 자율 음식물쓰레기통 수거 로봇 — Arduino Mega 펌웨어
 *
 * 4종 모터:
 *   1) 구동 (drive)  : NP01D-288 ×2 (좌/우 후륜 동시, RC카 전후진)
 *   2) 조향 (steer)  : MG996R 서보 (앞바퀴 ±15°)
 *   3) 랙&피니언(rack): JGA25-370 별도 메커니즘 (~2회전, 매우 느림)
 *   4) 롤러 (roller) : JGA25-370 (위/아래 회전)
 *
 * 안전: 충돌 임박 시 RPi 명령 무시하고 정지, 워치독 500ms.
 * 모든 속도 슬로우 캡 (config.h MAX_*_SPEED).
 *
 * 통신: USB Serial @ 115200, JSON 라인 1줄.
 */

#include "config.h"
#include "motors.h"
#include "servo_steer.h"
#include "ultrasonic.h"
#include "imu.h"
#include "safety.h"
#include "proto.h"

// 현재 적용 명령 값
static float    curDriveSpeed = 0;   // 전후진
static float    curRackSpeed  = 0;   // 랙&피니언
static bool     rollerOn = false;
static float    rollerSpd = 0;

// 타이밍
static uint32_t lastCmdMs = 0;
static uint32_t lastLoopMs = 0;
static bool     g_imuOk = false;

// 랙&피니언 동작 시간 제한 (~2회전)
static uint32_t rackStartMs = 0;
static float    rackLastCmd = 0;
static bool     rackLockout = false;

void setup() {
  Serial.begin(SERIAL_BAUD);
  while (!Serial && millis() < 2000);

  motorsBegin();
  servoBegin();          // MG996R 중앙 정렬
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
        // 서보 조향: speed 부호로 10° 증분 (0 = 중앙복귀)
        if (cmd.speed > 0.05f)      servoStep(+1);
        else if (cmd.speed < -0.05f) servoStep(-1);
        else                         servoStep(0);   // 0 = 중앙
        break;

      case Command::STEER_ABS:
        // 서보 절대 각도 (deg: 0~180)
        servoSetDeg(cmd.deg);
        break;

      case Command::RACK:
        // 랙&피니언: 시간 제한 (~2회전, RACK_MAX_DURATION_MS 후 자동정지 + lockout)
        if (cmd.speed == 0.0f) {
          curRackSpeed = 0;
          rackStartMs = 0;
          rackLastCmd = 0;
          rackLockout = false;
        } else if (rackLockout) {
          curRackSpeed = 0;   // lockout 중 추가 회전 X
        } else if (rackStartMs == 0 || (cmd.speed > 0) != (rackLastCmd > 0)) {
          curRackSpeed = cmd.speed;
          rackStartMs = now;
          rackLastCmd = cmd.speed;
        } else {
          curRackSpeed = cmd.speed;
          rackLastCmd = cmd.speed;
        }
        break;

      case Command::ROLLER:
        rollerOn  = cmd.rollerOn;
        rollerSpd = cmd.speed;
        break;

      case Command::STOP:
        curDriveSpeed = 0;
        curRackSpeed = 0;
        rollerOn = false;
        rackStartMs = 0;
        rackLockout = false;
        servoCenter();
        break;

      case Command::RESET_YAW:
        if (g_imuOk) imuResetYaw();
        break;

      case Command::PING_CMD:
        break;

      case Command::DIAGNOSE:
        protoSendDiagnose();
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

  // 워치독
  bool watchdogTrip = (now - lastCmdMs > WATCHDOG_MS);
  if (watchdogTrip) {
    curDriveSpeed = 0;
    curRackSpeed = 0;
    rollerOn = false;
    rackStartMs = 0;
  }

  // 🎯 랙 시간 제한: ~2회전 후 자동정지 + lockout
  if (RACK_MAX_DURATION_MS > 0 && rackStartMs > 0
      && (now - rackStartMs) > RACK_MAX_DURATION_MS) {
    curRackSpeed = 0;
    rackStartMs = 0;
    rackLockout = true;
  }

  // 안전 체크 (전후진 방향만)
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

  // ── 3) 안전 캡 + 가속 램프 ──
  static float driveApplied = 0, rackApplied = 0, rollerApplied = 0;

  float tDrive  = constrain(effDrive,     -MAX_DRIVE_SPEED,  MAX_DRIVE_SPEED);
  float tRack   = constrain(curRackSpeed, -MAX_RACK_SPEED,   MAX_RACK_SPEED);
  float tRoller = (rollerOn && safe)
                  ? constrain(rollerSpd,  -MAX_ROLLER_SPEED, MAX_ROLLER_SPEED) : 0;

  #define RAMP(applied, target, maxDelta) do { \
    float _d = (target) - (applied); \
    if (fabs(_d) > (maxDelta)) _d = (_d > 0) ? (maxDelta) : -(maxDelta); \
    (applied) += _d; \
  } while(0)
  RAMP(driveApplied,  tDrive,  DRIVE_RAMP_PER_CYCLE);
  RAMP(rackApplied,   tRack,   RACK_RAMP_PER_CYCLE);
  RAMP(rollerApplied, tRoller, ROLLER_RAMP_PER_CYCLE);

  // 액추에이터 적용
  driveBoth(driveApplied);
  rackSet(rackApplied);
  rollerMotor.set(rollerApplied);

  // 텔레메트리
  protoSendTelemetry(now, us, imu,
                     driveApplied, servoCurrentDeg(), rackApplied,
                     rollerOn, rollerApplied, safe, err);
}
