#pragma once
#include <Arduino.h>

class Motor {
  uint8_t pwmPin, in1Pin, in2Pin, pwmMin;
public:
  Motor(uint8_t pwm, uint8_t in1, uint8_t in2, uint8_t deadzone);
  void begin();
  void set(float speed);   // -1.0 ~ +1.0  (음수 = 반대 방향, 0 = 정지)
  void stop();
};

extern Motor leftDrive;
extern Motor rightDrive;
extern Motor rackMotor;     // 랙&피니언 (별도 메커니즘, 2회전 max)
extern Motor rollerMotor;

void motorsBegin();
void motorsAllStop();

// 전후진: 좌우 바퀴 동시에 같은 방향/속도로 회전 (RC카 방식)
void driveBoth(float speed);

// 랙&피니언 모터: 매우 느린 회전. 양수=정방향, 음수=역방향, 0=정지
// 최대 동작 시간(2회전 ≈ RACK_MAX_DURATION_MS)은 main loop에서 제한
void rackSet(float speed);

// 롤러: on/off + 방향(speed의 부호). 위(+)/아래(-) 회전
void rollerSet(bool on, float speed);
