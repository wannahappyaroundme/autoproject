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
Motor steerMotor (STEER_PWM,   STEER_IN1,   STEER_IN2,   STEER_PWM_MIN);
Motor rollerMotor(ROLLER_PWM,  ROLLER_IN3,  ROLLER_IN4,  ROLLER_PWM_MIN);

void motorsBegin() {
  leftDrive.begin();
  rightDrive.begin();
  steerMotor.begin();
  rollerMotor.begin();
}

void motorsAllStop() {
  leftDrive.stop();
  rightDrive.stop();
  steerMotor.stop();
  rollerMotor.stop();
}

void driveBoth(float speed) {
  // 좌우 바퀴를 같은 PWM/방향으로 동시 구동 (RC카 방식 전후진)
  leftDrive.set(speed);
  rightDrive.set(speed);
}

void steerSet(float speed) {
  // 조향 모터 직접 PWM 제어. 버튼 누르고 있는 동안만 회전, 떼면 0 보내서 정지.
  // 실제 조향각 제한은 기구적 스토퍼 또는 추후 엔코더/리밋스위치로 처리.
  steerMotor.set(speed);
}

void rollerSet(bool on, float speed) {
  if (!on) { rollerMotor.stop(); return; }
  rollerMotor.set(speed);
}
