/*
 * 자율주행 음식물쓰레기통 수거 로봇 — Arduino Mega 펌웨어
 *
 * 하드웨어 명세서 Section 7.2 핀 배치 기준
 *
 * 통신 프로토콜:
 *   Jetson → Arduino: CMD,<type>,<val1>,<val2>\n
 *   Arduino → Jetson: DATA,<type>,<values>\n
 *
 * 주기:
 *   - 센서 데이터 전송: 50Hz (20ms)
 *   - 시리얼 수신: 매 루프
 *   - PID 제어: 50Hz
 */

// ===== 핀 정의 (하드웨어 명세서 Section 7.2) =====

// 구동 모터 인코더 (인터럽트 핀)
#define ENC_L_A 2
#define ENC_L_B 3
#define ENC_R_A 18
#define ENC_R_B 19

// 구동 모터 드라이버 (L298N #1)
#define MOTOR_L_PWM 5    // ENA
#define MOTOR_R_PWM 6    // ENB
#define MOTOR_L_IN1 7
#define MOTOR_L_IN2 8
#define MOTOR_R_IN1 9
#define MOTOR_R_IN2 10

// 롤러 모터 드라이버 (L298N #2)
#define ROLLER_L_PWM 11  // ENA
#define ROLLER_R_PWM 12  // ENB
#define ROLLER_L_IN1 22
#define ROLLER_L_IN2 23
#define ROLLER_R_IN1 24
#define ROLLER_R_IN2 25

// 조향 서보
#define SERVO_PIN 44

// 초음파 센서 × 5 (Trig/Echo)
#define US_FL_TRIG 26
#define US_FL_ECHO 31
#define US_FR_TRIG 27
#define US_FR_ECHO 32
#define US_SL_TRIG 28
#define US_SL_ECHO 33
#define US_SR_TRIG 29
#define US_SR_ECHO 34
#define US_R_TRIG  30
#define US_R_ECHO  35

// 배터리 전압 모니터링
#define BAT_ADC A0

// IMU (I2C — SDA/SCL은 Mega 기본)
// MPU-9250: Wire 라이브러리 사용

#include <Servo.h>
#include <Wire.h>

// ===== 전역 변수 =====

// 인코더 틱
volatile long enc_left = 0;
volatile long enc_right = 0;

// 모터 목표 PWM
int target_left_pwm = 0;
int target_right_pwm = 0;

// 롤러 PWM
int roller_left_pwm = 0;
int roller_right_pwm = 0;

// 서보
Servo steer_servo;
int servo_angle = 90;  // 중립

// 초음파 거리 (cm)
int us_distances[5] = {999, 999, 999, 999, 999};
const int US_TRIG_PINS[] = {US_FL_TRIG, US_FR_TRIG, US_SL_TRIG, US_SR_TRIG, US_R_TRIG};
const int US_ECHO_PINS[] = {US_FL_ECHO, US_FR_ECHO, US_SL_ECHO, US_SR_ECHO, US_R_ECHO};

// IMU 데이터
float imu_ax = 0, imu_ay = 0, imu_az = 0;
float imu_gx = 0, imu_gy = 0, imu_gz = 0;

// 비상정지
bool estop = false;

// 타이밍
unsigned long last_sensor_time = 0;
unsigned long last_imu_time = 0;
const unsigned long SENSOR_INTERVAL = 20;  // 50Hz
const unsigned long IMU_INTERVAL = 20;

// 시리얼 버퍼
char serial_buf[128];
int serial_idx = 0;

// ===== 인코더 인터럽트 =====

void enc_left_a_isr() {
  if (digitalRead(ENC_L_B)) enc_left--;
  else enc_left++;
}

void enc_right_a_isr() {
  if (digitalRead(ENC_R_B)) enc_right--;
  else enc_right++;
}

// ===== 초음파 측정 =====

int read_ultrasonic(int trig_pin, int echo_pin) {
  digitalWrite(trig_pin, LOW);
  delayMicroseconds(2);
  digitalWrite(trig_pin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trig_pin, LOW);

  long duration = pulseIn(echo_pin, HIGH, 30000);  // 30ms 타임아웃 (~5m)
  if (duration == 0) return 999;
  return (int)(duration * 0.034 / 2.0);
}

// ===== IMU 읽기 (MPU-9250) =====

void read_imu() {
  Wire.beginTransmission(0x68);  // MPU-9250 주소
  Wire.write(0x3B);              // ACCEL_XOUT_H
  Wire.endTransmission(false);
  Wire.requestFrom(0x68, 14, true);

  int16_t ax_raw = Wire.read() << 8 | Wire.read();
  int16_t ay_raw = Wire.read() << 8 | Wire.read();
  int16_t az_raw = Wire.read() << 8 | Wire.read();
  Wire.read(); Wire.read();  // temp 건너뛰기
  int16_t gx_raw = Wire.read() << 8 | Wire.read();
  int16_t gy_raw = Wire.read() << 8 | Wire.read();
  int16_t gz_raw = Wire.read() << 8 | Wire.read();

  // 단위 변환: ±2g → m/s², ±250°/s → rad/s
  imu_ax = ax_raw / 16384.0 * 9.81;
  imu_ay = ay_raw / 16384.0 * 9.81;
  imu_az = az_raw / 16384.0 * 9.81;
  imu_gx = gx_raw / 131.0 * 0.01745;  // deg/s → rad/s
  imu_gy = gy_raw / 131.0 * 0.01745;
  imu_gz = gz_raw / 131.0 * 0.01745;
}

// ===== 모터 제어 =====

void set_motor(int in1, int in2, int pwm_pin, int pwm_val) {
  if (estop) {
    digitalWrite(in1, LOW);
    digitalWrite(in2, LOW);
    analogWrite(pwm_pin, 0);
    return;
  }

  if (pwm_val > 0) {
    digitalWrite(in1, HIGH);
    digitalWrite(in2, LOW);
  } else if (pwm_val < 0) {
    digitalWrite(in1, LOW);
    digitalWrite(in2, HIGH);
    pwm_val = -pwm_val;
  } else {
    digitalWrite(in1, LOW);
    digitalWrite(in2, LOW);
  }
  analogWrite(pwm_pin, constrain(pwm_val, 0, 255));
}

void apply_motors() {
  set_motor(MOTOR_L_IN1, MOTOR_L_IN2, MOTOR_L_PWM, target_left_pwm);
  set_motor(MOTOR_R_IN1, MOTOR_R_IN2, MOTOR_R_PWM, target_right_pwm);
  set_motor(ROLLER_L_IN1, ROLLER_L_IN2, ROLLER_L_PWM, roller_left_pwm);
  set_motor(ROLLER_R_IN1, ROLLER_R_IN2, ROLLER_R_PWM, roller_right_pwm);
}

// ===== 시리얼 명령 파싱 =====

void parse_command(char* cmd) {
  // CMD,DRIVE,<left>,<right>
  // CMD,STEER,<angle>
  // CMD,ROLLER,<left>,<right>
  // CMD,STOP,0,0

  char* token = strtok(cmd, ",");
  if (!token || strcmp(token, "CMD") != 0) return;

  token = strtok(NULL, ",");
  if (!token) return;

  if (strcmp(token, "DRIVE") == 0) {
    char* v1 = strtok(NULL, ",");
    char* v2 = strtok(NULL, ",");
    if (v1 && v2) {
      target_left_pwm = atoi(v1);
      target_right_pwm = atoi(v2);
      estop = false;
    }
  }
  else if (strcmp(token, "STEER") == 0) {
    char* v1 = strtok(NULL, ",");
    if (v1) {
      servo_angle = constrain(atoi(v1), 60, 120);  // ±30도
      steer_servo.write(servo_angle);
    }
  }
  else if (strcmp(token, "ROLLER") == 0) {
    char* v1 = strtok(NULL, ",");
    char* v2 = strtok(NULL, ",");
    if (v1 && v2) {
      roller_left_pwm = atoi(v1);
      roller_right_pwm = atoi(v2);
    }
  }
  else if (strcmp(token, "STOP") == 0) {
    target_left_pwm = 0;
    target_right_pwm = 0;
    roller_left_pwm = 0;
    roller_right_pwm = 0;
    estop = true;
  }
}

// ===== 센서 데이터 전송 =====

void send_sensor_data() {
  // 인코더
  Serial.print("DATA,ENC,");
  Serial.print(enc_left);
  Serial.print(",");
  Serial.println(enc_right);

  // IMU
  Serial.print("DATA,IMU,");
  Serial.print(imu_ax, 3); Serial.print(",");
  Serial.print(imu_ay, 3); Serial.print(",");
  Serial.print(imu_az, 3); Serial.print(",");
  Serial.print(imu_gx, 4); Serial.print(",");
  Serial.print(imu_gy, 4); Serial.print(",");
  Serial.println(imu_gz, 4);

  // 초음파 (라운드로빈 — 매 주기 1개씩 측정)
  static int us_idx = 0;
  us_distances[us_idx] = read_ultrasonic(US_TRIG_PINS[us_idx], US_ECHO_PINS[us_idx]);
  us_idx = (us_idx + 1) % 5;

  Serial.print("DATA,USS,");
  for (int i = 0; i < 5; i++) {
    Serial.print(us_distances[i]);
    if (i < 4) Serial.print(",");
  }
  Serial.println();

  // 배터리 (12V → 분압 → ADC)
  int bat_raw = analogRead(BAT_ADC);
  float bat_voltage = bat_raw * (5.0 / 1023.0) * 3.0;  // 분압비 3:1
  Serial.print("DATA,BAT,");
  Serial.println(bat_voltage, 2);

  // 롤러 전류 (L298N current sense 미사용 시 PWM 값으로 대체)
  Serial.print("DATA,ROLLER,");
  Serial.print(abs(roller_left_pwm));
  Serial.print(",");
  Serial.println(abs(roller_right_pwm));
}

// ===== Setup =====

void setup() {
  Serial.begin(115200);

  // 인코더 핀
  pinMode(ENC_L_A, INPUT_PULLUP);
  pinMode(ENC_L_B, INPUT_PULLUP);
  pinMode(ENC_R_A, INPUT_PULLUP);
  pinMode(ENC_R_B, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(ENC_L_A), enc_left_a_isr, RISING);
  attachInterrupt(digitalPinToInterrupt(ENC_R_A), enc_right_a_isr, RISING);

  // 모터 핀
  int motor_pins[] = {MOTOR_L_PWM, MOTOR_R_PWM, MOTOR_L_IN1, MOTOR_L_IN2,
                      MOTOR_R_IN1, MOTOR_R_IN2, ROLLER_L_PWM, ROLLER_R_PWM,
                      ROLLER_L_IN1, ROLLER_L_IN2, ROLLER_R_IN1, ROLLER_R_IN2};
  for (int i = 0; i < 12; i++) pinMode(motor_pins[i], OUTPUT);

  // 서보
  steer_servo.attach(SERVO_PIN);
  steer_servo.write(90);  // 중립

  // 초음파 핀
  for (int i = 0; i < 5; i++) {
    pinMode(US_TRIG_PINS[i], OUTPUT);
    pinMode(US_ECHO_PINS[i], INPUT);
  }

  // IMU
  Wire.begin();
  Wire.beginTransmission(0x68);
  Wire.write(0x6B);  // PWR_MGMT_1
  Wire.write(0x00);  // 슬립 해제
  Wire.endTransmission(true);

  Serial.println("DATA,STATUS,READY");
}

// ===== Loop =====

void loop() {
  unsigned long now = millis();

  // 시리얼 수신
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (serial_idx > 0) {
        serial_buf[serial_idx] = '\0';
        parse_command(serial_buf);
        serial_idx = 0;
      }
    } else if (serial_idx < 126) {
      serial_buf[serial_idx++] = c;
    }
  }

  // 모터 적용
  apply_motors();

  // 센서 데이터 전송 (50Hz)
  if (now - last_sensor_time >= SENSOR_INTERVAL) {
    last_sensor_time = now;
    read_imu();
    send_sensor_data();
  }
}
