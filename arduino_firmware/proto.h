#pragma once
#include <Arduino.h>
#include "imu.h"

// === RPi → Arduino 명령 (JSON 라인 1줄) ===
//   {"cmd":"drive","speed":0.5}     좌우바퀴 같이 회전 (양수=전진, 음수=후진, 0=정지)
//   {"cmd":"steer","speed":0.5}     서보 조향 (양수=우, 음수=좌, 0=중앙복귀). speed 부호로 5° 증분
//   {"cmd":"rack","speed":0.5}      랙&피니언 모터 (양수=정방향, 매우 느림, 2회전 max)
//   {"cmd":"roller","on":true,"speed":0.7}  롤러 (speed 부호 = 위/아래)
//   {"cmd":"stop"}                  모든 모터 정지 + 서보 중앙
//   {"cmd":"reset_yaw"}             IMU yaw 영점
//   {"cmd":"ping"}                  헬스체크
//   {"cmd":"diagnose"}              부품 진단 보고
struct Command {
  // PING은 AVR의 Port G Input 레지스터와 충돌 → PING_CMD로 변경
  enum Type { NONE, DRIVE, STEER, STEER_ABS, RACK, ROLLER, STOP, RESET_YAW, PING_CMD, DIAGNOSE } type;
  float speed;     // -1.0 ~ +1.0
  int   deg;       // STEER_ABS 전용 (0~180)
  bool  rollerOn;
};

bool protoReadCommand(Command& out);

// === Arduino → RPi 텔레메트리 ===
//   drive: 전후진 PWM, servo_deg: 서보 절대 각도, rack: 랙 PWM,
//   roller_spd: 롤러 PWM
void protoSendTelemetry(uint32_t t_ms, const uint16_t us[5], const ImuData& imu,
                        float driveSpeed, int servoDeg, float rackSpeed,
                        bool rollerOn, float rollerSpd,
                        bool safe, const char* err);

// 진단
void protoSendDiagnose();
