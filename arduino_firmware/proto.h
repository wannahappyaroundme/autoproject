#pragma once
#include <Arduino.h>
#include "imu.h"

// === RPi → Arduino 명령 (JSON 라인 1줄) ===
//   {"cmd":"drive","speed":0.5}     좌우바퀴 같이 회전 (양수=전진, 음수=후진, 0=정지)
//   {"cmd":"steer","speed":0.5}     조향모터 (양수=우회전, 음수=좌회전, 0=정지)
//   {"cmd":"roller","on":true,"speed":0.7}    롤러 (speed 부호로 방향)
//   {"cmd":"stop"}                  모든 모터 정지
//   {"cmd":"reset_yaw"}             IMU yaw 영점 리셋
//   {"cmd":"ping"}                  헬스체크
struct Command {
  enum Type { NONE, DRIVE, STEER, ROLLER, STOP, RESET_YAW, PING } type;
  float speed;     // -1.0 ~ +1.0
  bool  rollerOn;
};

bool protoReadCommand(Command& out);

// === Arduino → RPi 텔레메트리 ===
void protoSendTelemetry(uint32_t t_ms, const uint16_t us[5], const ImuData& imu,
                        float driveSpeed, float steerSpeed,
                        bool rollerOn, float rollerSpd,
                        bool safe, const char* err);
