#pragma once
#include <Arduino.h>

// === RC-car 구조 자율수거 로봇 ===
// 전후진: Motor#1의 좌/우 바퀴가 같은 방향으로 동시 회전 (독립 제어 X)
// 좌/우 조향: Motor#2 ENA에 연결된 랙&피니언 모터로 앞바퀴 각도 변경
// 롤러: Motor#2 ENB에 연결, 수거/배출 토글

// --- Motor Driver #1: 구동 바퀴 ×2 (NP01D-288) ---
// 우측 바퀴
constexpr uint8_t DRIVE_R_PWM = 2;     // ENA
constexpr uint8_t DRIVE_R_IN1 = 22;
constexpr uint8_t DRIVE_R_IN2 = 23;
// 좌측 바퀴
constexpr uint8_t DRIVE_L_IN3 = 24;
constexpr uint8_t DRIVE_L_IN4 = 25;
constexpr uint8_t DRIVE_L_PWM = 3;     // ENB

// --- Motor Driver #2: 조향(랙&피니언) + 롤러 (JGA25-370 ×2) ---
// 조향 모터 (랙&피니언)
constexpr uint8_t STEER_PWM = 4;       // ENA
constexpr uint8_t STEER_IN1 = 26;
constexpr uint8_t STEER_IN2 = 27;
// 롤러 모터
constexpr uint8_t ROLLER_IN3 = 28;
constexpr uint8_t ROLLER_IN4 = 29;
constexpr uint8_t ROLLER_PWM = 5;      // ENB

// --- 초음파 HC-SR04 ×5 ---
// 인덱스: 0=전, 1=좌, 2=우, 3=후, 4=수거함내부
constexpr uint8_t US_TRIG[5] = {30, 32, 34, 36, 38};
constexpr uint8_t US_ECHO[5] = {31, 33, 35, 37, 39};
enum UsIdx { US_FRONT = 0, US_LEFT, US_RIGHT, US_REAR, US_BIN };

// --- IMU (MPU-9250) ---
// Mega의 하드웨어 I2C 핀 사용: SDA=20, SCL=21 (Wire 라이브러리 자동 사용)
// 풀업 4.7kΩ 외부 또는 모듈 내장 (둘 다 OK)

// --- 안전 임계값 (cm) ---
constexpr uint16_t SAFE_FRONT_CM = 15;
constexpr uint16_t SAFE_SIDE_CM  = 10;
constexpr uint16_t SAFE_REAR_CM  = 10;

// --- 루프 / 통신 ---
constexpr uint32_t LOOP_PERIOD_MS = 100;   // 10 Hz
constexpr uint32_t WATCHDOG_MS    = 500;   // RPi 명령 끊기면 정지
constexpr uint32_t SERIAL_BAUD    = 115200;

// --- PWM 데드존 (실측 후 보정) ---
constexpr uint8_t  DRIVE_PWM_MIN  = 60;    // NP01D-288
constexpr uint8_t  STEER_PWM_MIN  = 70;    // JGA25-370
constexpr uint8_t  ROLLER_PWM_MIN = 70;    // JGA25-370

// --- 🔒 테스트 단계 안전 캡 (하드웨어 검증 전 보호용) ---
// RPi가 1.0 보내도 펌웨어가 이 값으로 클램프. 실측 끝나면 1.0으로 변경 가능.
constexpr float MAX_DRIVE_SPEED  = 0.30f;   // 30% 까지
constexpr float MAX_STEER_SPEED  = 0.40f;
constexpr float MAX_ROLLER_SPEED = 0.40f;

// --- 🐢 가속 램프 (PWM 급변 방지, 100ms 사이클당 최대 변화량) ---
// 0.05 × 10Hz = 0.5/sec → 0에서 최대치까지 도달에 1.5초 (안전)
constexpr float DRIVE_RAMP_PER_CYCLE  = 0.05f;
constexpr float STEER_RAMP_PER_CYCLE  = 0.10f;
constexpr float ROLLER_RAMP_PER_CYCLE = 0.10f;
