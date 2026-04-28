#pragma once
#include <Arduino.h>

void ultrasonicBegin();
uint16_t ultrasonicReadCm(uint8_t idx);   // 0~4, 0xFFFF = timeout (멀거나 없음)
void ultrasonicReadAll(uint16_t out[5]);
