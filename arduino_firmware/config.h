#pragma once
#include <Arduino.h>

// === RC-car 구조 자율수거 로봇 ===
// 4종 모터 시스템:
//   1) 구동 (drive)  : NP01D-288 ×2 (좌/우 후륜 동시 회전, 전후진)
//   2) 조향 (steer)  : MG996R 서보 (앞바퀴 각도, ±15° 권장)
//   3) 랙&피니언(rack): JGA25-370 ×1 (별도 메커니즘, ~2회전 매우 느림)
//   4) 롤러 (roller) : JGA25-370 ×1 (위/아래 회전)

// --- Motor Driver #1: 구동 바퀴 ×2 (NP01D-288) ---
// 우측 바퀴 (배선 극성 반전 보정: IN1/IN2 swap → 전진 명령에 정방향 회전)
constexpr uint8_t DRIVE_R_PWM = 2;     // ENA
constexpr uint8_t DRIVE_R_IN1 = 23;    // 원래 22 → 23 (swap)
constexpr uint8_t DRIVE_R_IN2 = 22;    // 원래 23 → 22 (swap)
// 좌측 바퀴
constexpr uint8_t DRIVE_L_IN3 = 24;
constexpr uint8_t DRIVE_L_IN4 = 25;
constexpr uint8_t DRIVE_L_PWM = 3;     // ENB

// --- Motor Driver #2: 랙&피니언 + 롤러 (JGA25-370 ×2) ---
// 랙&피니언 그리퍼: 피니언 1개 + 랙 2개. 회전 방향에 따라 두 랙(=양쪽 롤러)이
//   안쪽으로 모이거나 바깥쪽으로 벌어짐 → 빈을 좌우에서 파지.
// 🔧 RPi 측 부호 약속 (rpi_firmware/config.py:GRIP_SPEED, planner.py):
//     rack( +0.15 ) = 모음(close, 파지)
//     rack( -0.15 ) = 벌림(open, 평소 상태)
// 실측 후 방향 반대면 IN1/IN2 swap 또는 motors.cpp의 rackSet() 부호 반전.
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
constexpr int     SERVO_MAX_DEG    = 90;       // 중앙 ±90° = 0~180° (전체 범위)
constexpr int     SERVO_STEP_DEG   = 30;       // (legacy) 수동 클릭 1회당 점프 — pickup 자율에선 안 씀

// --- 🐢 서보 점진 변화 (rack/pinion 분리 방지) ---
// 사유(2026-05-25 실측): 큰 각도 점프 시 피니언/랙 기어가 순간 mismatch.
// 매 100ms 사이클에서 target_deg 쪽으로 이 값만큼만 이동 → 각도 변화가 부드러움.
// 90→120 (30°)를 부드럽게 가려면 ~10 사이클(1초) 소요.
constexpr int SERVO_RAMP_DEG_PER_CYCLE = 3;    // 사이클당 최대 3° 변화

// --- 초음파 HC-SR04 ×5 ---
// 🔧 핀↔위치 매핑 (2026-05-25 실측 — 기존 매핑이 실제와 다르고 좌측 센서 고장):
//   idx 0 US_FRONT = 핀 32/33  (실제 부착: 구 "전방우측" → 단일 전방 센서로 사용)
//   idx 1 US_LEFT  = 핀 30/31  (실제 부착: 구 "전방좌측" → 위치 이동해서 좌측)
//   idx 2 US_RIGHT = 핀 36/37  (실제 부착: 우측, 그대로)
//   idx 3 US_REAR  = 핀 38/39  (실제 부착: 후방, 그대로)
//   idx 4 US_BIN   = 핀 0/0    (미사용 — 원래 좌측 34/35였으나 신호 안 잡힘, 폐기)
// ultrasonic.cpp는 핀==0이면 read skip 처리.
constexpr uint8_t US_TRIG[5] = {32, 30, 36, 38, 0};
constexpr uint8_t US_ECHO[5] = {33, 31, 37, 39, 0};
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

// --- 🎯 랙&피니언 1회 최대 동작 시간 ---
// 0 = 무제한 (hold-to-move 방식). RPi가 0 명령 또는 watchdog로 멈춤.
// 만약 메커니즘 보호를 위해 자동정지 원하면 350~700 정도로 설정.
constexpr uint32_t RACK_MAX_DURATION_MS = 0;

// --- 서보 ---
// MG996R은 신호선만 Arduino, 전원은 LM2596HV 직결 (Arduino 5V 거치지 말 것)
