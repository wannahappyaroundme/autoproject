#include "ultrasonic.h"
#include "config.h"

constexpr uint32_t US_TIMEOUT_US = 25000;   // 25 ms = ~4 m

void ultrasonicBegin() {
  for (uint8_t i = 0; i < 5; i++) {
    // 핀 0 = 미사용(고장 센서 폐기) → pinMode 설정 자체를 skip
    if (US_TRIG[i] == 0 || US_ECHO[i] == 0) continue;
    pinMode(US_TRIG[i], OUTPUT);
    pinMode(US_ECHO[i], INPUT);
    digitalWrite(US_TRIG[i], LOW);
  }
}

uint16_t ultrasonicReadCm(uint8_t idx) {
  if (idx >= 5) return 0xFFFF;
  // 핀 0 = 미사용 센서: 즉시 timeout으로 반환 (안전 로직이 0xFFFF를 "장애물 없음"으로 처리)
  if (US_TRIG[idx] == 0 || US_ECHO[idx] == 0) return 0xFFFF;

  digitalWrite(US_TRIG[idx], LOW);
  delayMicroseconds(2);
  digitalWrite(US_TRIG[idx], HIGH);
  delayMicroseconds(10);
  digitalWrite(US_TRIG[idx], LOW);

  uint32_t dur = pulseIn(US_ECHO[idx], HIGH, US_TIMEOUT_US);
  if (dur == 0) return 0xFFFF;     // timeout = 멀리 또는 미감지
  return (uint16_t)(dur / 58);     // µs → cm (음속 343m/s 기준)
}

void ultrasonicReadAll(uint16_t out[5]) {
  for (uint8_t i = 0; i < 5; i++) {
    out[i] = ultrasonicReadCm(i);
    delay(2);   // 센서 간 간섭 방지 (인접 센서 에코 흡수 시간)
  }
}
