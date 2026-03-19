from controller import Robot, Keyboard
import csv
import os

# --- 1. 초기화 및 설정 ---
robot = Robot()
timestep = int(robot.getBasicTimeStep())

# 장치 연결
camera = robot.getDevice("camera")
camera.enable(timestep)

steer_l = robot.getDevice("steer_left")
steer_r = robot.getDevice("steer_right")
drive_l = robot.getDevice("drive_left")
drive_r = robot.getDevice("drive_right")

# 구동 모터 무한 회전 설정
drive_l.setPosition(float('inf'))
drive_r.setPosition(float('inf'))

# 설정 상수
MAX_SPEED = 12.0
MAX_STEER = 0.45
SMOOTHING = 0.1
DATA_SAVE_INTERVAL = 10 # 10스텝마다 저장

# 폴더 및 CSV 준비
DATA_DIR = 'driving_data'
IMG_DIR = os.path.join(DATA_DIR, 'images')
if not os.path.exists(IMG_DIR):
    os.makedirs(IMG_DIR)

csv_file = open(os.path.join(DATA_DIR, 'log.csv'), 'w', newline='')
csv_writer = csv.writer(csv_file)
csv_writer.writerow(['time', 'image_path', 'steering', 'speed'])

keyboard = Keyboard()
keyboard.enable(timestep)

# 상태 변수
current_speed = 0.0
img_count = 0
step_counter = 0

# --- 2. 표준 제어 함수 ---
def set_robot_control(steering, velocity):
    """나중에 자율주행 알고리즘과 연결할 표준 인터페이스입니다."""
    steer_l.setPosition(steering)
    steer_r.setPosition(steering)
    drive_l.setVelocity(velocity)
    drive_r.setVelocity(velocity)

def save_driving_data(steering, speed):
    """현재 시야와 조종 데이터를 저장합니다."""
    global img_count
    img_filename = f"img_{img_count}.png"
    img_save_path = os.path.join(IMG_DIR, img_filename)
    csv_img_path = os.path.join('images', img_filename)
    
    camera.saveImage(img_save_path, 100)
    csv_writer.writerow([round(robot.getTime(), 3), csv_img_path, round(steering, 3), round(speed, 3)])
    img_count += 1

# --- 3. 메인 루프 ---
print("🚀 주행 시스템 및 데이터 수집 가동 중...")

while robot.step(timestep) != -1:
    key = keyboard.getKey()
    
    target_v = 0.0
    target_s = 0.0
    
    while key != -1:
        if key == Keyboard.UP: target_v = MAX_SPEED
        elif key == Keyboard.DOWN: target_v = -MAX_SPEED
        
        # 조향 방향: RIGHT는 플러스(+), LEFT는 마이너스(-)
        if key == Keyboard.LEFT: target_s = -MAX_STEER
        elif key == Keyboard.RIGHT: target_s = MAX_STEER
        key = keyboard.getKey()

    # 가속 부드럽게 보정
    current_speed += (target_v - current_speed) * SMOOTHING
    
    # 제어 실행
    set_robot_control(target_s, current_speed)
    
    # 유의미한 움직임이 있을 때만 데이터 수집
    if abs(current_speed) > 0.1:
        step_counter += 1
        if step_counter % DATA_SAVE_INTERVAL == 0:
            save_driving_data(target_s, current_speed)

csv_file.close()