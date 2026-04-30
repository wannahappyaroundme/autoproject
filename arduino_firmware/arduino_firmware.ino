/*
 * 자율 음식물쓰레기통 수거 로봇 — Arduino Mega 펌웨어 (RC-car 구조)
 *
 * 역할: 실시간 제어 + 안전 보장 계층
 *   - 100ms 주기로 모든 센서 폴링
 *   - RPi에서 받은 명령 실행 (전후진/조향/롤러)
 *   - 안전 체크 (충돌 임박 → RPi 명령 무시하고 즉시 정지)
 *   - 워치독: 500ms간 명령 없으면 자동 정지
 *
 * 통신: USB Serial @ 115200, JSON 라인 1줄 단위
 */

#include "config.h"
#include "motors.h"
#include "steer.h"
#include "ultrasonic.h"
#include "imu.h"
#include "safety.h"
#include "proto.h"

static float    curSpeed = 0;
static float    curSteer = 0;
static bool     rollerOn = false;
static float    rollerSpd = 0;
static uint32_t lastCmdMs = 0;
static uint32_t lastLoopMs = 0;
static bool     g_imuOk = false;   // IMU 미장착 시 false → imuRead 호출 자체를 스킵 (I2C hang 방지)

void setup() {
  Serial.begin(SERIAL_BAUD);
  while (!Serial && millis() < 2000);   // USB 연결 대기 (최대 2초)

  motorsBegin();
  steerBegin();
  ultrasonicBegin();
  g_imuOk = imuBegin();   // IMU 없으면 false. 모터/센서는 정상 동작.

  // 시작 직후 정지 상태 보장
  motorsAllStop();
  steerCenter();

  // 부팅 완료 알림 (RPi가 이걸로 핸드셰이크)
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
      case Command::MOVE:
        curSpeed = cmd.speed;
        curSteer = cmd.steer;
        break;
      case Command::ROLLER:
        rollerOn  = cmd.rollerOn;
        rollerSpd = cmd.rollerSpd;
        break;
      case Command::STOP:
        curSpeed = 0; curSteer = 0;
        rollerOn = false;
        break;
      case Command::RESET_YAW:
        imuResetYaw();
        break;
      case Command::PING:
        // 응답은 다음 텔레메트리로 자동 전송됨
        break;
      default: break;
    }
  }

  // ── 2) 100ms 주기로만 센서 + 제어 + 텔레메트리 ──
  if (now - lastLoopMs < LOOP_PERIOD_MS) return;
  lastLoopMs = now;

  // 센서 읽기
  uint16_t us[5];
  ultrasonicReadAll(us);
  ImuData imu = g_imuOk ? imuRead() : ImuData{0, 0, 0, false};

  // 워치독: RPi 명령 끊긴 지 오래되면 정지
  bool watchdogTrip = (now - lastCmdMs > WATCHDOG_MS);
  if (watchdogTrip) {
    curSpeed = 0; curSteer = 0;
    rollerOn = false;
  }

  // 안전 체크
  bool safe = safetyCheck(us, curSpeed);
  const char* err = nullptr;
  float effSpeed = curSpeed;
  if (!safe) {
    effSpeed = 0;
    err = safetyLastReason();
  } else if (watchdogTrip) {
    err = "watchdog";
    safe = false;
  }

  // 액추에이터 적용
  driveMotor.set(effSpeed);
  steerSet(curSteer);
  rollerSet(rollerOn && safe, rollerSpd);

  // 텔레메트리 송신
  protoSendTelemetry(now, us, imu, effSpeed, curSteer, rollerOn, safe, err);
}
