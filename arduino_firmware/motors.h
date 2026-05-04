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
extern Motor steerMotor;
extern Motor rollerMotor;

void motorsBegin();
void motorsAllStop();

// 전후진: 좌우 바퀴 동시에 같은 방향/속도로 회전 (RC카 방식)
void driveBoth(float speed);

// 조향: 랙&피니언 모터 PWM. 양수=우회전 방향, 음수=좌회전, 0=정지
// 버튼을 누르고 있는 동안만 호출 (release 시 0 보내야 함)
void steerSet(float speed);

// 롤러: on/off + 방향(speed의 부호)
void rollerSet(bool on, float speed);
