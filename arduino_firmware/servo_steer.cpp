#include "servo_steer.h"
#include "config.h"
#include <Servo.h>

static Servo srv;
static int   curDeg = SERVO_CENTER_DEG;

void servoBegin() {
  srv.attach(SERVO_PIN);
  servoCenter();
}

void servoCenter() {
  curDeg = SERVO_CENTER_DEG;
  srv.write(curDeg);
}

void servoSetDeg(int deg) {
  // ±SERVO_MAX_DEG 범위로 클램프
  int minD = SERVO_CENTER_DEG - SERVO_MAX_DEG;
  int maxD = SERVO_CENTER_DEG + SERVO_MAX_DEG;
  if (deg < minD) deg = minD;
  if (deg > maxD) deg = maxD;
  curDeg = deg;
  srv.write(curDeg);
}

void servoStep(int direction) {
  // direction: +1 = 우, -1 = 좌, 0 = 중앙으로 복귀
  if (direction == 0) {
    servoCenter();
  } else {
    servoSetDeg(curDeg + (direction > 0 ? SERVO_STEP_DEG : -SERVO_STEP_DEG));
  }
}

int servoCurrentDeg() {
  return curDeg;
}
