#pragma once
#include <Arduino.h>

struct ImuData {
  float yaw;     // rad (gyro Z 적분 기반, drift 있음)
  float pitch;   // rad
  float roll;    // rad
  bool  ok;
};

bool    imuBegin();
ImuData imuRead();
void    imuResetYaw();   // 현재 yaw를 0으로 리셋
