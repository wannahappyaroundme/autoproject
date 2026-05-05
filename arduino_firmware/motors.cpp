#include "motors.h"
#include "config.h"

Motor::Motor(uint8_t pwm, uint8_t in1, uint8_t in2, uint8_t deadzone)
  : pwmPin(pwm), in1Pin(in1), in2Pin(in2), pwmMin(deadzone) {}

void Motor::begin() {
  pinMode(pwmPin, OUTPUT);
  pinMode(in1Pin, OUTPUT);
  pinMode(in2Pin, OUTPUT);
  stop();
}

void Motor::set(float speed) {
  speed = constrain(speed, -1.0f, 1.0f);
  if (fabs(speed) < 0.05f) { stop(); return; }

  if (speed >= 0) {
    digitalWrite(in1Pin, HIGH);
    digitalWrite(in2Pin, LOW);
  } else {
    digitalWrite(in1Pin, LOW);
    digitalWrite(in2Pin, HIGH);
  }
  uint8_t pwm = (uint8_t)(fabs(speed) * (255 - pwmMin) + pwmMin);
  analogWrite(pwmPin, pwm);
}

void Motor::stop() {
  digitalWrite(in1Pin, LOW);
  digitalWrite(in2Pin, LOW);
  analogWrite(pwmPin, 0);
}

// === 글로벌 모터 인스턴스 ===
Motor leftDrive  (DRIVE_L_PWM, DRIVE_L_IN3, DRIVE_L_IN4, DRIVE_PWM_MIN);
Motor rightDrive (DRIVE_R_PWM, DRIVE_R_IN1, DRIVE_R_IN2, DRIVE_PWM_MIN);
Motor rackMotor  (RACK_PWM,    RACK_IN1,    RACK_IN2,    RACK_PWM_MIN);
Motor rollerMotor(ROLLER_PWM,  ROLLER_IN3,  ROLLER_IN4,  ROLLER_PWM_MIN);

void motorsBegin() {
  leftDrive.begin();
  rightDrive.begin();
  rackMotor.begin();
  rollerMotor.begin();
}

void motorsAllStop() {
  leftDrive.stop();
  rightDrive.stop();
  rackMotor.stop();
  rollerMotor.stop();
}

void driveBoth(float speed) {
  // 좌우 바퀴를 같은 PWM/방향으로 동시 구동 (RC카 방식 전후진)
  leftDrive.set(speed);
  rightDrive.set(speed);
}

void rackSet(float speed) {
  // 랙&피니언 모터 (별도 메커니즘). 매우 느림. 최대 동작 시간은 main loop에서 제한.
  rackMotor.set(speed);
}

void rollerSet(bool on, float speed) {
  // 롤러 (위/아래 회전). speed 부호 = 방향
  if (!on) { rollerMotor.stop(); return; }
  rollerMotor.set(speed);
}
