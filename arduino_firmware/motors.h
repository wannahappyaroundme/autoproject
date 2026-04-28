#pragma once
#include <Arduino.h>

class Motor {
  uint8_t pwmPin, in1Pin, in2Pin, pwmMin;
public:
  Motor(uint8_t pwm, uint8_t in1, uint8_t in2, uint8_t deadzone);
  void begin();
  void set(float speed);   // -1.0 ~ +1.0
  void stop();
};

extern Motor driveMotor;   // 후륜 2개 병렬
extern Motor roller1;
extern Motor roller2;

void motorsBegin();
void motorsAllStop();
void rollerSet(bool on, float speed);   // 두 롤러 동시 제어 (수거 시 정방향, 배출 시 역방향)
