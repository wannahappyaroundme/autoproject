from controller import Robot, Keyboard
import csv
import os

# --- 1. 초기화 및 설정 ---
robot = Robot()
timestep = int(robot.getBasicTimeStep())

# 장치 연결 (대각선 배치 명칭)
camera = robot.getDevice("camera")
camera.enable(timestep)

# 구동 바퀴: Front-Left(FL), Back-Right(BR)
drive_fl = robot.getDevice("drive_fl")
drive_br = robot.getDevice("drive_br")

# 조향 바퀴: Front-Right(FR), Back-Left(BL)
steer_fr = robot.getDevice("steer_fr")
steer_bl = robot.getDevice("steer_bl")

# 구동 모터 무한 회전 설정
drive_fl.setPosition(float('inf'))
drive_br.setPosition(float('inf'))

# 설정 상수
MAX_SPEED = 12.0
MAX_STEER = 0.45
SMOOTHING = 0.1
DATA_SAVE_INTERVAL = 10 

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

# --- 2. 대각선 제어용 표준 함수 (수정됨) ---
def set_robot_control(steering, velocity):
    """
    대각선 회전 최적화 로직:
    1. 앞-오른쪽(FR) 바퀴는 정방향(steering)으로 조향합니다.
    2. 뒤-왼쪽(BL) 바퀴는 반대방향(-steering)으로 조향해야 차체가 회전합니다.
    """
    # 조향 바퀴 제어 (뒤쪽 바퀴에 마이너스 부호를 붙여 반전시켰습니다)
    steer_fr.setPosition(steering)
    steer_bl.setPosition(steering) 
    
    # 구동 바퀴 제어
    drive_fl.setVelocity(velocity)
    drive_br.setVelocity(velocity)

def save_driving_data(steering, speed):
    global img_count
    img_filename = f"img_{img_count}.png"
    img_save_path = os.path.join(IMG_DIR, img_filename)
    csv_img_path = os.path.join('images', img_filename)
    
    camera.saveImage(img_save_path, 100)
    csv_writer.writerow([round(robot.getTime(), 3), csv_img_path, round(steering, 3), round(speed, 3)])
    img_count += 1

# --- 3. 메인 루프 ---
print("🚀 대각선 회전 최적화 모드로 가동 중입니다!")

while robot.step(timestep) != -1:
    key = keyboard.getKey()
    
    target_v = 0.0
    target_s = 0.0
    
    while key != -1:
        if key == Keyboard.UP: target_v = MAX_SPEED
        elif key == Keyboard.DOWN: target_v = -MAX_SPEED
        
        # 키보드 입력은 기존과 동일하게 처리
        if key == Keyboard.LEFT: target_s = -MAX_STEER
        elif key == Keyboard.RIGHT: target_s = MAX_STEER
        key = keyboard.getKey()

    # 부드러운 가속/감속 처리
    current_speed += (target_v - current_speed) * SMOOTHING
    
    # 수정된 제어 함수 호출
    set_robot_control(target_s, current_speed)
    
    # 데이터 수집 (움직일 때만)
    if abs(current_speed) > 0.1:
        step_counter += 1
        if step_counter % DATA_SAVE_INTERVAL == 0:
            save_driving_data(target_s, current_speed)

csv_file.close()