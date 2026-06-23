import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import numpy as np
import random
import math
import time
import threading

BaseOptions = mp.tasks.BaseOptions
HandLandmarker = mp.tasks.vision.HandLandmarker
HandLandmarkerOptions = mp.tasks.vision.HandLandmarkerOptions
VisionRunningMode = mp.tasks.vision.RunningMode

# Colors
COLOR_SKY_BLUE = (135, 206, 235)
COLOR_RED = (0, 0, 255)
COLOR_WHITE = (255, 255, 255)
COLOR_YELLOW = (0, 255, 255)
COLOR_GREEN = (0, 255, 0)
COLOR_PURPLE = (255, 0, 255)

options = HandLandmarkerOptions(
    base_options=BaseOptions(model_asset_path='hand_landmarker.task'),
    running_mode=VisionRunningMode.VIDEO,
    num_hands=2,
    min_hand_detection_confidence=0.7,
    min_hand_presence_confidence=0.7,
    min_tracking_confidence=0.7
)

landmarker = HandLandmarker.create_from_options(options)

cap = cv2.VideoCapture(0)

# Threading and shared state
frame_lock = threading.Lock()
latest_raw_frame = None
latest_landmarks = []  # List of hands, each containing 21 (x, y) coordinates
thread_running = True

def hand_tracking_worker():
    global latest_landmarks, thread_running
    
    last_timestamp_ms = 0
    
    while thread_running:
        # Get the latest frame safely
        with frame_lock:
            frame_to_process = latest_raw_frame
            
        if frame_to_process is None:
            time.sleep(0.005)
            continue
            
        h, w, _ = frame_to_process.shape
        
        # Downsample for faster detection (max width 480)
        target_w = 480
        if w > target_w:
            scale = target_w / w
            target_h = int(h * scale)
            small_frame = cv2.resize(frame_to_process, (target_w, target_h))
        else:
            small_frame = frame_to_process
            
        # Convert to MediaPipe Image
        rgb_frame = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
        )
        
        # Get strictly increasing timestamp in milliseconds
        timestamp_ms = int(time.time() * 1000)
        if timestamp_ms <= last_timestamp_ms:
            timestamp_ms = last_timestamp_ms + 1
        last_timestamp_ms = timestamp_ms
        
        try:
            detection_result = landmarker.detect_for_video(rgb_frame, timestamp_ms)
            
            # Extract landmarks and scale them back to original frame size
            hands_landmarks = []
            if detection_result and detection_result.hand_landmarks:
                for hand_landmarks in detection_result.hand_landmarks:
                    scaled_hand = []
                    for lm in hand_landmarks:
                        scaled_hand.append((int(lm.x * w), int(lm.y * h)))
                    hands_landmarks.append(scaled_hand)
                    
            with frame_lock:
                latest_landmarks = hands_landmarks
        except Exception:
            pass
            
        time.sleep(0.005)

# Start background thread
tracking_thread = threading.Thread(target=hand_tracking_worker, daemon=True)
tracking_thread.start()

# Game state
game_state = "setup"  # setup, puzzle, win
captured = False
tiles = []
original_tiles = []
completed_puzzle_image = None  # Store the clean puzzle image for win screen
selected_tile = None
selected_tile_pos = None
frame_corner1 = None
frame_corner2 = None
frame_active = False
hold_start_time = None
prev_pinches_count = 0

ROWS = 3
COLS = 3
tile_h = 0
tile_w = 0
puzzle_x = 0
puzzle_y = 0
MIN_FRAME_SIZE = 300  # Minimum width/height for frame


def create_puzzle(img):
    h, w, _ = img.shape

    th = h // ROWS
    tw = w // COLS

    pieces = []
    for i in range(ROWS):
        for j in range(COLS):
            piece = img[
                i * th:(i + 1) * th,
                j * tw:(j + 1) * tw
            ]
            pieces.append((piece, i, j))  # Store original position

    random.shuffle(pieces)

    shuffled_pieces = [piece[0] for piece in pieces]
    original_indices = [(piece[1], piece[2]) for piece in pieces]

    return shuffled_pieces, original_indices


def draw_glossy_button(img, x, y, w, h, text):
    # Draw glossy green button
    overlay = img.copy()
    cv2.rectangle(overlay, (x, y), (x + w, y + h), (0, 180, 0), -1)
    cv2.rectangle(overlay, (x, y), (x + w, y + h // 3), (0, 220, 0), -1)
    alpha = 0.8
    cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0, img)

    # Draw text
    font = cv2.FONT_HERSHEY_SIMPLEX
    text_size = cv2.getTextSize(text, font, 2, 5)[0]
    text_x = x + (w - text_size[0]) // 2
    text_y = y + (h + text_size[1]) // 2
    cv2.putText(img, text, (text_x, text_y), font, 2, (255, 255, 255), 5, cv2.LINE_AA)


while True:

    success, frame = cap.read()

    if not success:
        break

    frame = cv2.flip(frame, 1)
    h_frame, w_frame, _ = frame.shape

    # Update latest frame for background hand tracking thread
    with frame_lock:
        latest_raw_frame = frame.copy()

    # Get latest hand landmark detection results
    with frame_lock:
        current_landmarks = latest_landmarks

    pinches = []

    for idx, hand_landmarks in enumerate(current_landmarks):
        if len(hand_landmarks) > 8:
            x1, y1 = hand_landmarks[4]
            x2, y2 = hand_landmarks[8]

            color = COLOR_SKY_BLUE if idx == 0 else COLOR_RED
            cv2.circle(frame, (x1, y1), 10, color, -1)
            cv2.circle(frame, (x2, y2), 10, color, -1)

            dist = math.hypot(x2 - x1, y2 - y1)
            cv2.line(frame, (x1, y1), (x2, y2), color, 3)

            if dist < 40:
                pinch_x = (x1 + x2) // 2
                pinch_y = (y1 + y2) // 2
                pinches.append((pinch_x, pinch_y, color))
                cv2.circle(frame, (pinch_x, pinch_y), 15, color, -1)

    if game_state == "setup":
        if len(pinches) >= 2:
            # Use both pinches as frame corners
            frame_corner1 = pinches[0][:2]
            frame_corner2 = pinches[1][:2]
            frame_active = True

            # Start hold timer if not already started
            if hold_start_time is None:
                hold_start_time = time.time()

            # Draw frame
            x_min = min(frame_corner1[0], frame_corner2[0])
            y_min = min(frame_corner1[1], frame_corner2[1])
            x_max = max(frame_corner1[0], frame_corner2[0])
            y_max = max(frame_corner1[1], frame_corner2[1])

            # Check minimum frame size
            frame_width = x_max - x_min
            frame_height = y_max - y_min
            if frame_width < MIN_FRAME_SIZE or frame_height < MIN_FRAME_SIZE:
                cv2.putText(frame, f"Make frame bigger! Min {MIN_FRAME_SIZE}px", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.8, COLOR_RED, 2)
                # Draw red brackets indicating size issue
                bracket_len = 30
                cv2.line(frame, (x_min, y_min), (x_min + bracket_len, y_min), COLOR_RED, 4)
                cv2.line(frame, (x_min, y_min), (x_min, y_min + bracket_len), COLOR_RED, 4)
                cv2.line(frame, (x_max, y_min), (x_max - bracket_len, y_min), COLOR_RED, 4)
                cv2.line(frame, (x_max, y_min), (x_max, y_min + bracket_len), COLOR_RED, 4)
                cv2.line(frame, (x_min, y_max), (x_min + bracket_len, y_max), COLOR_RED, 4)
                cv2.line(frame, (x_min, y_max), (x_min, y_max - bracket_len), COLOR_RED, 4)
                cv2.line(frame, (x_max, y_max), (x_max - bracket_len, y_max), COLOR_RED, 4)
                cv2.line(frame, (x_max, y_max), (x_max, y_max - bracket_len), COLOR_RED, 4)
                
                hold_start_time = None  # Reset timer if frame is too small
            else:
                # Viewfinder Overlay: Darken outside the selection
                mask = np.zeros_like(frame)
                cv2.rectangle(mask, (x_min, y_min), (x_max, y_max), (255, 255, 255), -1)
                frame = np.where(mask == 255, frame, cv2.addWeighted(frame, 0.4, np.zeros_like(frame), 0.6, 0))

                # Draw stylish camera corner brackets instead of a plain rectangle
                bracket_len = 40
                color_bracket = (0, 200, 255)
                # Top-left
                cv2.line(frame, (x_min, y_min), (x_min + bracket_len, y_min), color_bracket, 4)
                cv2.line(frame, (x_min, y_min), (x_min, y_min + bracket_len), color_bracket, 4)
                # Top-right
                cv2.line(frame, (x_max, y_min), (x_max - bracket_len, y_min), color_bracket, 4)
                cv2.line(frame, (x_max, y_min), (x_max, y_min + bracket_len), color_bracket, 4)
                # Bottom-left
                cv2.line(frame, (x_min, y_max), (x_min + bracket_len, y_max), color_bracket, 4)
                cv2.line(frame, (x_min, y_max), (x_min, y_max - bracket_len), color_bracket, 4)
                # Bottom-right
                cv2.line(frame, (x_max, y_max), (x_max - bracket_len, y_max), color_bracket, 4)
                cv2.line(frame, (x_max, y_max), (x_max, y_max - bracket_len), color_bracket, 4)
                
                # Draw subtle grid lines in viewfinder
                cv2.line(frame, (x_min + frame_width // 3, y_min), (x_min + frame_width // 3, y_max), (255, 255, 255, 100), 1)
                cv2.line(frame, (x_min + 2 * frame_width // 3, y_min), (x_min + 2 * frame_width // 3, y_max), (255, 255, 255, 100), 1)
                cv2.line(frame, (x_min, y_min + frame_height // 3), (x_max, y_min + frame_height // 3), (255, 255, 255, 100), 1)
                cv2.line(frame, (x_min, y_min + 2 * frame_height // 3), (x_max, y_min + 2 * frame_height // 3), (255, 255, 255, 100), 1)

                # Show stylish progress bar
                hold_duration = time.time() - hold_start_time
                progress = min(hold_duration / 1.0, 1.0)  # 1 second hold
                bar_width = 300
                bar_height = 20
                bar_x = w_frame // 2 - bar_width // 2
                bar_y = h_frame - 80
                cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_width, bar_y + bar_height), (40, 40, 40), -1)
                cv2.rectangle(frame, (bar_x, bar_y), (bar_x + int(bar_width * progress), bar_y + bar_height), (0, 200, 255), -1)
                cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_width, bar_y + bar_height), (200, 200, 200), 2)
                cv2.putText(frame, "HOLD TO CAPTURE", (bar_x + 50, bar_y - 15), cv2.FONT_HERSHEY_DUPLEX, 0.7, (255, 255, 255), 1)

                # Capture if held long enough
                if hold_duration >= 1.0 and not captured:
                    puzzle_area = frame[y_min:y_max, x_min:x_max].copy()
                    if puzzle_area.size > 0:
                        completed_puzzle_image = puzzle_area.copy()  # Save for win screen
                        tiles, original_tiles = create_puzzle(puzzle_area)
                        tile_h = (y_max - y_min) // ROWS
                        tile_w = (x_max - x_min) // COLS
                        puzzle_x = x_min
                        puzzle_y = y_min
                        captured = True
                        frame_active = False
                        game_state = "puzzle"
                        hold_start_time = None
                        frame_corner1 = None
                        frame_corner2 = None
        else:
            # No pinches - reset timer
            hold_start_time = None
            frame_active = False
            frame_corner1 = None
            frame_corner2 = None
            # Draw semi-transparent overlay to hint user to pinch
            overlay = frame.copy()
            cv2.rectangle(overlay, (0, 0), (w_frame, h_frame), (0, 0, 0), -1)
            frame = cv2.addWeighted(overlay, 0.3, frame, 0.7, 0)
            text = "Pinch both hands to select puzzle area"
            font = cv2.FONT_HERSHEY_SIMPLEX
            ts = cv2.getTextSize(text, font, 1, 2)[0]
            cv2.putText(frame, text, ((w_frame - ts[0]) // 2, 50), font, 1, COLOR_WHITE, 2)

    elif game_state == "puzzle":
        # Draw puzzle directly onto the frame copy (optimized: no resize, no sum mask)
        combined = frame.copy()

        k = 0
        for i in range(ROWS):
            for j in range(COLS):
                piece = tiles[k]
                px = puzzle_x + j * tile_w
                py = puzzle_y + i * tile_h
                combined[py:py + tile_h, px:px + tile_w] = piece

                # Draw yellow grid lines
                cv2.rectangle(combined, (px, py), (px + tile_w, py + tile_h), COLOR_YELLOW, 2)

                k += 1

        # Puzzle interaction
        current_pinches_count = len(pinches)
        if current_pinches_count == 1:
            pinch_x, pinch_y, _ = pinches[0]
            col = (pinch_x - puzzle_x) // tile_w
            row = (pinch_y - puzzle_y) // tile_h

            if prev_pinches_count == 0 and selected_tile is None:
                # Just pinched - pick up tile!
                if 0 <= col < COLS and 0 <= row < ROWS:
                    selected_tile = row * COLS + col
                    selected_tile_pos = (pinch_x, pinch_y)
            elif selected_tile is not None:
                # Holding pinch - move tile!
                selected_tile_pos = (pinch_x, pinch_y)
        elif prev_pinches_count == 1 and current_pinches_count == 0 and selected_tile is not None:
            # Released pinch - place or swap tile!
            pinch_x, pinch_y = selected_tile_pos
            col = (pinch_x - puzzle_x) // tile_w
            row = (pinch_y - puzzle_y) // tile_h
            if 0 <= col < COLS and 0 <= row < ROWS:
                target_tile = row * COLS + col
                if target_tile != selected_tile:
                    # Swap tiles
                    tiles[selected_tile], tiles[target_tile] = tiles[target_tile], tiles[selected_tile]
                    original_tiles[selected_tile], original_tiles[target_tile] = original_tiles[target_tile], original_tiles[selected_tile]
            # Drop tile
            selected_tile = None
            selected_tile_pos = None

            # Check win
            expected = []
            for i in range(ROWS):
                for j in range(COLS):
                    expected.append((i, j))
            if original_tiles == expected:
                game_state = "win"

        prev_pinches_count = current_pinches_count

        # Draw selected tile on top if we have one (optimized: no resize)
        if selected_tile is not None and selected_tile_pos is not None:
            piece = tiles[selected_tile]
            px = selected_tile_pos[0] - tile_w // 2
            py = selected_tile_pos[1] - tile_h // 2
            # Make sure it's within frame
            px = max(0, min(px, w_frame - tile_w))
            py = max(0, min(py, h_frame - tile_h))
            
            # Draw shadow effect
            shadow_offset = 8
            shadow_px = max(0, min(px + shadow_offset, w_frame - tile_w))
            shadow_py = max(0, min(py + shadow_offset, h_frame - tile_h))
            
            # Create a darker version of the region for shadow
            shadow_region = combined[shadow_py:shadow_py + tile_h, shadow_px:shadow_px + tile_w].copy()
            shadow_region = cv2.addWeighted(shadow_region, 0.4, np.zeros_like(shadow_region), 0.6, 0)
            combined[shadow_py:shadow_py + tile_h, shadow_px:shadow_px + tile_w] = shadow_region
            
            # Draw the piece itself
            combined[py:py + tile_h, px:px + tile_w] = piece
            
            # Draw glowing border
            cv2.rectangle(combined, (px, py), (px + tile_w, py + tile_h), (0, 255, 255), 4)

        frame = combined

    elif game_state == "win":
        # Draw a beautiful complete screen
        # 1. Darken and blur background
        overlay = cv2.GaussianBlur(frame, (21, 21), 0)
        overlay = cv2.addWeighted(overlay, 0.5, np.zeros_like(overlay), 0.5, 0)
        frame = overlay

        # 2. Draw completed puzzle in center
        if completed_puzzle_image is not None:
            img_h, img_w, _ = completed_puzzle_image.shape
            start_y = (h_frame - img_h) // 2
            start_x = (w_frame - img_w) // 2
            # Make sure it fits
            start_y = max(0, min(start_y, h_frame - img_h))
            start_x = max(0, min(start_x, w_frame - img_w))
            
            frame[start_y:start_y + img_h, start_x:start_x + img_w] = completed_puzzle_image
            
            # Draw a nice white border around the image
            cv2.rectangle(frame, (start_x - 4, start_y - 4), (start_x + img_w + 4, start_y + img_h + 4), COLOR_WHITE, 4)

        # 3. Draw text banner
        font = cv2.FONT_HERSHEY_DUPLEX
        text1 = "PUZZLE COMPLETE \U0001F947"
        text2 = "Press R to Restart"
        
        ts1 = cv2.getTextSize(text1, font, 1.5, 3)[0]
        ts2 = cv2.getTextSize(text2, font, 0.8, 2)[0]
        
        # Draw banner rectangle behind text
        banner_h = 100
        banner_y = 50
        cv2.rectangle(frame, (0, banner_y), (w_frame, banner_y + banner_h), (0, 180, 0), -1)
        
        cv2.putText(frame, text1, ((w_frame - ts1[0]) // 2, banner_y + 45), font, 1.5, COLOR_WHITE, 3)
        cv2.putText(frame, text2, ((w_frame - ts2[0]) // 2, banner_y + 85), font, 0.8, (200, 255, 200), 2)

    cv2.imshow("Camera", frame)

    key = cv2.waitKey(1)

    if key == ord('r'):
        game_state = "setup"
        captured = False
        selected_tile = None
        selected_tile_pos = None
        tiles = []
        original_tiles = []
        completed_puzzle_image = None
        frame_active = False
        frame_corner1 = None
        frame_corner2 = None
        hold_start_time = None
        prev_pinches_count = 0

    if key == 27:
        break


landmarker.close()
cap.release()
cv2.destroyAllWindows()
