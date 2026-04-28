#pragma once
#include <Arduino.h>

// === RC-car style 자율 수거 로봇 ===
// 후륜 2개 병렬 (L298N #1 한 채널) + 전륜 조향 서보 + 롤러 모터 ×2 (L298N #2 양 채널)

// --- 구동 모터 (L298N #1, 후륜 2개를 한 채널에 병렬 연결) ---
constexpr uint8_t DRIVE_PWM = 5;     // ENA
constexpr uint8_t DRIVE_IN1 = 32;
constexpr uint8_t DRIVE_IN2 = 33;

// --- 롤러 모터 ×2 (L298N #2, 양 채널) ---
constexpr uint8_t ROLLER1_PWM = 7;   // ENA
constexpr uint8_t ROLLER1_IN1 = 36;
constexpr uint8_t ROLLER1_IN2 = 37;
constexpr uint8_t ROLLER2_PWM = 8;   // ENB
constexpr uint8_t ROLLER2_IN1 = 38;
constexpr uint8_t ROLLER2_IN2 = 39;

// --- 조향 서보 (MG996R) ---
constexpr uint8_t STEER_PIN = 9;
constexpr int     STEER_CENTER_DEG = 90;
constexpr int     STEER_RANGE_DEG = 35;   // ±35°

// --- 초음파 HC-SR04 ×5 ---
// 인덱스: 0=전, 1=좌, 2=우, 3=후, 4=수거함내부
constexpr uint8_t US_TRIG[5] = {22, 24, 26, 28, 30};
constexpr uint8_t US_ECHO[5] = {23, 25, 27, 29, 31};
enum UsIdx { US_FRONT = 0, US_LEFT, US_RIGHT, US_REAR, US_BIN };

// --- 안전 임계값 (cm) ---
constexpr uint16_t SAFE_FRONT_CM = 15;
constexpr uint16_t SAFE_SIDE_CM  = 10;
constexpr uint16_t SAFE_REAR_CM  = 10;

// --- 루프 / 통신 ---
constexpr uint32_t LOOP_PERIOD_MS  = 100;   // 10 Hz
constexpr uint32_t WATCHDOG_MS     = 500;   // RPi 명령 끊기면 정지
constexpr uint32_t SERIAL_BAUD     = 115200;

// --- PWM 데드존 (실측 후 보정) ---
constexpr uint8_t  DRIVE_PWM_MIN   = 60;
constexpr uint8_t  ROLLER_PWM_MIN  = 80;
