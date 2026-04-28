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

Motor driveMotor(DRIVE_PWM,   DRIVE_IN1,   DRIVE_IN2,   DRIVE_PWM_MIN);
Motor roller1   (ROLLER1_PWM, ROLLER1_IN1, ROLLER1_IN2, ROLLER_PWM_MIN);
Motor roller2   (ROLLER2_PWM, ROLLER2_IN1, ROLLER2_IN2, ROLLER_PWM_MIN);

void motorsBegin() {
  driveMotor.begin();
  roller1.begin();
  roller2.begin();
}

void motorsAllStop() {
  driveMotor.stop();
  roller1.stop();
  roller2.stop();
}

void rollerSet(bool on, float speed) {
  if (!on) { roller1.stop(); roller2.stop(); return; }
  roller1.set(speed);
  roller2.set(speed);
}
