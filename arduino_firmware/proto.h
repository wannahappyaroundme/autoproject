#pragma once
#include <Arduino.h>
#include "imu.h"

// RPi → Arduino 명령 (JSON 라인 1줄)
//   {"cmd":"move","speed":0.5,"steer":0.2}
//   {"cmd":"roller","on":true,"speed":0.7}
//   {"cmd":"stop"}
//   {"cmd":"reset_yaw"}
//   {"cmd":"ping"}
struct Command {
  enum Type { NONE, MOVE, ROLLER, STOP, RESET_YAW, PING } type;
  float speed;     // -1.0 ~ +1.0
  float steer;     // -1.0 ~ +1.0
  bool  rollerOn;
  float rollerSpd;
};

// 한 줄(\n까지) 수신해서 명령 파싱.
// 리턴: true=새 명령 수신 / false=대기 중
bool protoReadCommand(Command& out);

// Arduino → RPi 텔레메트리 (JSON 라인)
void protoSendTelemetry(uint32_t t_ms, const uint16_t us[5], const ImuData& imu,
                        float speed, float steer, bool rollerOn,
                        bool safe, const char* err);
