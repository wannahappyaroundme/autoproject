#pragma once
#include <Arduino.h>

// === RC-car 구조 자율수거 로봇 ===
// 4종 모터 시스템:
//   1) 구동 (drive)  : NP01D-288 ×2 (좌/우 후륜 동시 회전, 전후진)
//   2) 조향 (steer)  : MG996R 서보 (앞바퀴 각도, ±15° 권장)
//   3) 랙&피니언(rack): JGA25-370 ×1 (별도 메커니즘, ~2회전 매우 느림)
//   4) 롤러 (roller) : JGA25-370 ×1 (위/아래 회전)

// --- Motor Driver #1: 구동 바퀴 ×2 (NP01D-288) ---
// 우측 바퀴
constexpr uint8_t DRIVE_R_PWM = 2;     // ENA
constexpr uint8_t DRIVE_R_IN1 = 22;
constexpr uint8_t DRIVE_R_IN2 = 23;
// 좌측 바퀴
constexpr uint8_t DRIVE_L_IN3 = 24;
constexpr uint8_t DRIVE_L_IN4 = 25;
constexpr uint8_t DRIVE_L_PWM = 3;     // ENB

// --- Motor Driver #2: 랙&피니언 + 롤러 (JGA25-370 ×2) ---
// 랙&피니언 (별도 메커니즘, 2회전 max, 매우 느림)
constexpr uint8_t RACK_PWM = 4;        // ENA
constexpr uint8_t RACK_IN1 = 26;
constexpr uint8_t RACK_IN2 = 27;
// 롤러
constexpr uint8_t ROLLER_IN3 = 28;
constexpr uint8_t ROLLER_IN4 = 29;
constexpr uint8_t ROLLER_PWM = 5;      // ENB

// --- 서보 (MG996R) — 조향 전용 ---
// 신호선 1개만 Arduino 핀 6번에. 전원(+/-)은 LM2596HV 5V + GND 직결.
constexpr uint8_t SERVO_PIN        = 6;        // PWM 핀 (모터 PWM 2~5와 충돌 X)
constexpr int     SERVO_CENTER_DEG = 90;       // 중앙 (0=좌, 180=우)
constexpr int     SERVO_MAX_DEG    = 15;       // 중앙 ±15° (좁게, 안전)
constexpr int     SERVO_STEP_DEG   = 5;        // 1회 클릭당 5° 이동

// --- 초음파 HC-SR04 ×5 ---
// 인덱스: 0=전, 1=좌, 2=우, 3=후, 4=수거함내부
constexpr uint8_t US_TRIG[5] = {30, 32, 34, 36, 38};
constexpr uint8_t US_ECHO[5] = {31, 33, 35, 37, 39};
enum UsIdx { US_FRONT = 0, US_LEFT, US_RIGHT, US_REAR, US_BIN };

// --- IMU (MPU-9250) — Mega 하드웨어 I2C (SDA=20, SCL=21) ---
// 내장 풀업(103=10kΩ) 또는 외부 4.7kΩ 둘 다 OK

// --- 안전 임계값 (cm) ---
constexpr uint16_t SAFE_FRONT_CM = 15;
constexpr uint16_t SAFE_SIDE_CM  = 10;
constexpr uint16_t SAFE_REAR_CM  = 10;

// --- 루프 / 통신 ---
constexpr uint32_t LOOP_PERIOD_MS = 100;   // 10 Hz
constexpr uint32_t WATCHDOG_MS    = 500;
constexpr uint32_t SERIAL_BAUD    = 115200;

// --- PWM 데드존 (실측 후 보정) ---
constexpr uint8_t  DRIVE_PWM_MIN  = 60;
constexpr uint8_t  RACK_PWM_MIN   = 80;    // 매우 느려서 데드존 더 높게
constexpr uint8_t  ROLLER_PWM_MIN = 70;

// --- 🔒🐢 안전 캡 — 모두 매우 느리게 (하드웨어 보호) ---
// 펌웨어가 RPi 명령을 이 값으로 클램프. 실측 후 단계별 상향.
constexpr float MAX_DRIVE_SPEED  = 0.20f;   // 20% (천천히 전후진)
constexpr float MAX_RACK_SPEED   = 0.15f;   // 15% (랙&피니언 매우 느림)
constexpr float MAX_ROLLER_SPEED = 0.20f;   // 20% (롤러 천천히)

// --- 🐢 가속 램프 (PWM 급변 방지, 100ms 사이클당 최대 변화량) ---
// 더 부드럽게 — 0에서 max까지 도달 시간 ↑
constexpr float DRIVE_RAMP_PER_CYCLE  = 0.03f;   // 0.03 × 10Hz = 0.3/sec → max 0.2까지 0.7초
constexpr float RACK_RAMP_PER_CYCLE   = 0.02f;   // 더 천천히
constexpr float ROLLER_RAMP_PER_CYCLE = 0.05f;

// --- 🎯 랙&피니언 1회 최대 동작 시간 (≈ 10도) ---
// JGA25-370 35RPM × 15% PWM ≈ 5RPM = 30°/초
// 10° = 약 350ms. 펌웨어 자동정지 + lockout (release 받기 전 추가 회전 X).
// 실측 후 조정 (더 작게 = 100ms, 더 크게 = 500ms 등).
// 0이면 무제한.
constexpr uint32_t RACK_MAX_DURATION_MS = 350;

// --- 서보 ---
// MG996R은 신호선만 Arduino, 전원은 LM2596HV 직결 (Arduino 5V 거치지 말 것)
