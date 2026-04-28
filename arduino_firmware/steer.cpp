#include "steer.h"
#include "config.h"
#include <Servo.h>

static Servo steerServo;

void steerBegin() {
  steerServo.attach(STEER_PIN);
  steerCenter();
}

void steerSet(float s) {
  s = constrain(s, -1.0f, 1.0f);
  int deg = STEER_CENTER_DEG + (int)(s * STEER_RANGE_DEG);
  deg = constrain(deg, STEER_CENTER_DEG - STEER_RANGE_DEG,
                       STEER_CENTER_DEG + STEER_RANGE_DEG);
  steerServo.write(deg);
}

void steerCenter() {
  steerServo.write(STEER_CENTER_DEG);
}
