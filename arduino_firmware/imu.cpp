#include "imu.h"
#include <Wire.h>

constexpr uint8_t MPU_ADDR = 0x68;       // AD0 핀이 LOW일 때
constexpr uint8_t REG_PWR_MGMT_1 = 0x6B;
constexpr uint8_t REG_ACCEL_XOUT_H = 0x3B;
constexpr uint8_t REG_GYRO_XOUT_H  = 0x43;

static float yawAcc = 0.0f;     // 누적 yaw (rad)
static float gyroBiasZ = 0.0f;  // 정지 시 gyro Z 바이어스 (deg/s)
static uint32_t lastT = 0;

static bool writeReg(uint8_t reg, uint8_t val) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(reg);
  Wire.write(val);
  return Wire.endTransmission() == 0;
}

static int read6(uint8_t reg, int16_t out[3]) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return -1;
  if (Wire.requestFrom(MPU_ADDR, (uint8_t)6) != 6) return -1;
  for (int i = 0; i < 3; i++) {
    int16_t hi = Wire.read();
    int16_t lo = Wire.read();
    out[i] = (hi << 8) | (lo & 0xFF);
  }
  return 0;
}

bool imuBegin() {
  Wire.begin();
  Wire.setClock(400000);
  if (!writeReg(REG_PWR_MGMT_1, 0x00)) return false;   // wake up
  delay(100);

  // 정지 상태에서 gyro Z 바이어스 측정 (200 샘플 평균)
  long sum = 0;
  int n = 0;
  for (int i = 0; i < 200; i++) {
    int16_t g[3];
    if (read6(REG_GYRO_XOUT_H, g) == 0) {
      sum += g[2];
      n++;
    }
    delay(3);
  }
  if (n > 0) gyroBiasZ = (sum / (float)n) / 131.0f;   // LSB → deg/s
  yawAcc = 0;
  lastT = 0;
  return true;
}

ImuData imuRead() {
  ImuData d{0, 0, 0, false};

  // Accel → roll/pitch
  int16_t a[3];
  if (read6(REG_ACCEL_XOUT_H, a) != 0) return d;
  float ax = a[0] / 16384.0f;
  float ay = a[1] / 16384.0f;
  float az = a[2] / 16384.0f;
  d.roll  = atan2(ay, az);
  d.pitch = atan2(-ax, sqrt(ay * ay + az * az));

  // Gyro Z 적분 → yaw
  int16_t g[3];
  if (read6(REG_GYRO_XOUT_H, g) != 0) return d;
  float gz_dps = (g[2] / 131.0f) - gyroBiasZ;   // deg/s

  uint32_t now = millis();
  if (lastT > 0) {
    float dt = (now - lastT) / 1000.0f;
    yawAcc += gz_dps * dt * (PI / 180.0f);
  }
  lastT = now;
  d.yaw = yawAcc;
  d.ok  = true;
  return d;
}

void imuResetYaw() {
  yawAcc = 0;
}
