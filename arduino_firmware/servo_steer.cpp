#include "servo_steer.h"
#include "config.h"
#include <Servo.h>

static Servo srv;
static int   curDeg    = SERVO_CENTER_DEG;     // 실제 적용된 각도
static int   targetDeg = SERVO_CENTER_DEG;     // 목표 각도 (RPi 명령 또는 수동 step이 설정)

static void clampToRange(int& d) {
  int minD = SERVO_CENTER_DEG - SERVO_MAX_DEG;
  int maxD = SERVO_CENTER_DEG + SERVO_MAX_DEG;
  if (d < minD) d = minD;
  if (d > maxD) d = maxD;
}

void servoBegin() {
  srv.attach(SERVO_PIN);
  curDeg = targetDeg = SERVO_CENTER_DEG;
  srv.write(curDeg);
}

void servoCenter() {
  curDeg = targetDeg = SERVO_CENTER_DEG;
  srv.write(curDeg);   // 중앙복귀는 즉시 (안전 조치)
}

void servoSetTarget(int deg) {
  clampToRange(deg);
  targetDeg = deg;
  // 실제 이동은 servoUpdate()에서 점진적으로
}

// legacy: 즉시 점프. 자율 동작에선 servoSetTarget+servoUpdate를 쓸 것.
void servoSetDeg(int deg) {
  clampToRange(deg);
  curDeg = targetDeg = deg;
  srv.write(curDeg);
}

void servoStep(int direction) {
  if (direction == 0) {
    servoCenter();
  } else {
    int next = targetDeg + (direction > 0 ? SERVO_STEP_DEG : -SERVO_STEP_DEG);
    servoSetTarget(next);   // 점진 모드로 — 큰 점프 시에도 부드럽게
  }
}

// 매 100ms loop 사이클마다 호출.
// target과 curDeg가 다르면 SERVO_RAMP_DEG_PER_CYCLE만큼만 이동.
void servoUpdate() {
  if (curDeg == targetDeg) return;
  int diff = targetDeg - curDeg;
  int step = SERVO_RAMP_DEG_PER_CYCLE;
  if (diff >  step) diff =  step;
  if (diff < -step) diff = -step;
  curDeg += diff;
  srv.write(curDeg);
}

int servoCurrentDeg() { return curDeg; }
int servoTargetDeg()  { return targetDeg; }
