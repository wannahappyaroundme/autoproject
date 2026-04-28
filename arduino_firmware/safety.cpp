#include "safety.h"
#include "config.h"

static const char* lastReason = nullptr;

bool safetyCheck(const uint16_t us[5], float commandedSpeed) {
  lastReason = nullptr;

  // 전진 시 전방 위험
  if (commandedSpeed > 0.05f && us[US_FRONT] < SAFE_FRONT_CM) {
    lastReason = "front_obstacle";
    return false;
  }
  // 후진 시 후방 위험
  if (commandedSpeed < -0.05f && us[US_REAR] < SAFE_REAR_CM) {
    lastReason = "rear_obstacle";
    return false;
  }
  // 측면 근접 (회전 중 충돌 방지)
  if (us[US_LEFT] < SAFE_SIDE_CM) {
    lastReason = "left_obstacle";
    return false;
  }
  if (us[US_RIGHT] < SAFE_SIDE_CM) {
    lastReason = "right_obstacle";
    return false;
  }
  return true;
}

const char* safetyLastReason() {
  return lastReason;
}
