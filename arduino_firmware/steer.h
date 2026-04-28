#pragma once
#include <Arduino.h>

void steerBegin();
void steerSet(float steer);   // -1.0 (full left) ~ +1.0 (full right)
void steerCenter();
