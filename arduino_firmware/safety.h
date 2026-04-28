#pragma once
#include <Arduino.h>

// 초음파 5채널 거리 입력 + 현재 명령 속도(전후) 받아서 안전 여부 판단.
// 리턴: true=안전 / false=위험(즉시 정지)
bool safetyCheck(const uint16_t us[5], float commandedSpeed);

// 마지막으로 차단된 사유 (텔레메트리용 문자열, 정상이면 nullptr)
const char* safetyLastReason();
