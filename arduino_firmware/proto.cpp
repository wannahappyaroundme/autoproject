#include "proto.h"
#include "config.h"

// 외부 라이브러리 없이 동작하도록 단순 JSON 파서 사용 (필드 형태 고정 가정)

static char rxBuf[160];
static uint8_t rxLen = 0;

// "key":<value> 패턴에서 value 부분 시작 위치 반환 (없으면 -1)
static int findValuePos(const char* buf, const char* key) {
  const char* k = strstr(buf, key);
  if (!k) return -1;
  k += strlen(key);
  while (*k == ' ' || *k == ':' || *k == '\t') k++;
  return k - buf;
}

static bool parseStringField(const char* buf, const char* key, char* out, size_t outSize) {
  int p = findValuePos(buf, key);
  if (p < 0 || buf[p] != '"') return false;
  size_t i = 0;
  p++;
  while (buf[p] && buf[p] != '"' && i < outSize - 1) out[i++] = buf[p++];
  out[i] = 0;
  return true;
}

static bool parseFloatField(const char* buf, const char* key, float& out) {
  int p = findValuePos(buf, key);
  if (p < 0) return false;
  out = atof(buf + p);
  return true;
}

static bool parseBoolField(const char* buf, const char* key, bool& out) {
  int p = findValuePos(buf, key);
  if (p < 0) return false;
  out = (buf[p] == 't' || buf[p] == '1');
  return true;
}

bool protoReadCommand(Command& out) {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (rxLen == 0) continue;
      rxBuf[rxLen] = 0;

      out = {Command::NONE, 0, 0, false, 0};
      char cmdStr[16] = {0};
      if (parseStringField(rxBuf, "\"cmd\"", cmdStr, sizeof(cmdStr))) {
        if      (!strcmp(cmdStr, "move"))      out.type = Command::MOVE;
        else if (!strcmp(cmdStr, "roller"))    out.type = Command::ROLLER;
        else if (!strcmp(cmdStr, "stop"))      out.type = Command::STOP;
        else if (!strcmp(cmdStr, "reset_yaw")) out.type = Command::RESET_YAW;
        else if (!strcmp(cmdStr, "ping"))      out.type = Command::PING;
      }
      parseFloatField(rxBuf, "\"speed\"",  out.speed);
      parseFloatField(rxBuf, "\"steer\"",  out.steer);
      parseBoolField (rxBuf, "\"on\"",     out.rollerOn);
      // 롤러 전용 speed는 같은 키 사용 (move의 speed와 충돌 없음 — type이 ROLLER일 때만 의미)
      if (out.type == Command::ROLLER) out.rollerSpd = out.speed;

      rxLen = 0;
      return out.type != Command::NONE;
    }
    if (rxLen < sizeof(rxBuf) - 1) rxBuf[rxLen++] = c;
    else rxLen = 0;   // 오버플로우 방지: 버퍼 리셋
  }
  return false;
}

static void printFloat3(float v) {
  // 소수 3자리, 메모리 절약
  char b[12];
  dtostrf(v, 1, 3, b);
  Serial.print(b);
}

void protoSendTelemetry(uint32_t t_ms, const uint16_t us[5], const ImuData& imu,
                        float speed, float steer, bool rollerOn,
                        bool safe, const char* err) {
  Serial.print(F("{\"t\":"));    Serial.print(t_ms);
  Serial.print(F(",\"us\":["));
  for (int i = 0; i < 5; i++) {
    if (us[i] == 0xFFFF) Serial.print(F("null"));
    else                 Serial.print(us[i]);
    if (i < 4) Serial.print(',');
  }
  Serial.print(F("],\"imu\":{\"yaw\":"));   printFloat3(imu.yaw);
  Serial.print(F(",\"pitch\":"));           printFloat3(imu.pitch);
  Serial.print(F(",\"roll\":"));            printFloat3(imu.roll);
  Serial.print(F(",\"ok\":"));              Serial.print(imu.ok ? F("true") : F("false"));
  Serial.print(F("},\"motor\":{\"speed\":"));  printFloat3(speed);
  Serial.print(F(",\"steer\":"));              printFloat3(steer);
  Serial.print(F("},\"roller\":"));            Serial.print(rollerOn ? F("true") : F("false"));
  Serial.print(F(",\"safe\":"));               Serial.print(safe ? F("true") : F("false"));
  Serial.print(F(",\"err\":"));
  if (err) { Serial.print('"'); Serial.print(err); Serial.print('"'); }
  else     { Serial.print(F("null")); }
  Serial.println('}');
}
