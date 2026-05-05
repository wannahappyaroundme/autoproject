#pragma once
#include <Arduino.h>

// MG996R 서보 (조향). Arduino Servo 라이브러리 사용.
// SERVO_PIN 신호선 1개만 Arduino. 전원은 LM2596HV 직결.

void servoBegin();
void servoCenter();
void servoSetDeg(int deg);    // 절대 각도 (SERVO_CENTER_DEG ± SERVO_MAX_DEG)
void servoStep(int direction); // +1 = 우, -1 = 좌, 5° 증분
int  servoCurrentDeg();
