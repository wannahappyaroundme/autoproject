#pragma once
#include <Arduino.h>

// MG996R 서보 (조향). Arduino Servo 라이브러리 사용.
// SERVO_PIN 신호선 1개만 Arduino. 전원은 LM2596HV 직결.

void servoBegin();
void servoCenter();                 // target=current=중앙, 즉시 적용
void servoSetTarget(int deg);       // target만 설정. 실제 이동은 servoUpdate()가 점진적으로
void servoSetDeg(int deg);          // (legacy) 절대각 즉시 점프 — 주의: rack/pinion 분리 위험
void servoStep(int direction);      // (legacy) ±SERVO_STEP_DEG 점프 — 수동 클릭용
void servoUpdate();                 // 매 100ms 사이클마다 호출: current를 target 쪽으로 RAMP만큼 이동
int  servoCurrentDeg();
int  servoTargetDeg();
