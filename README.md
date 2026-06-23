# 🧩 Gesture-Controlled Puzzle Game

![Gesture Puzzle Game Demo](working.png)

Gesture-Controlled Puzzle Game is an interactive, touchless computer vision game that transforms your webcam into a virtual playground. Players can capture a picture and solve a sliding tile puzzle using entirely hand gestures—no mouse, keyboard, or touchscreen required.

## ✨ Key Features

* **Custom Puzzle Generation:** Using both hands, players make pinch gestures to draw a "viewfinder" box on the screen. Holding the pinch for 1 second captures whatever is inside the box and instantly scrambles it into a 3×3 puzzle grid.
* **Touchless Interaction:** Players play the game by physically "grabbing" puzzle pieces in the air with a single-hand pinch gesture, dragging them around the screen, and releasing to drop or swap them.
* **High-Performance Architecture:** The game utilizes a multi-threaded design. Heavy AI hand-tracking is offloaded to a background thread while the main game loop runs at a butter-smooth 30+ FPS.
* **Dynamic UI & Visuals:** It features a stylish augmented reality (AR) style viewfinder, 3D-like drop shadows when tiles are lifted off the board, and a dedicated victory presentation screen when the puzzle is solved.

## 🛠️ Technology Stack

* **Python 3** (Core game logic)
* **OpenCV** (Webcam feed processing, image manipulation, and UI rendering)
* **MediaPipe** (Real-time AI hand landmark detection)

---

## 🚀 How to Run the Project

Follow these commands in your terminal or command prompt to setup and run the game locally:

### 1. Clone the Repository
```bash
git clone [https://github.com/gourab354/gesture-puzzle-game.git](https://github.com/gourab354/gesture-puzzle-game.git)
cd gesture-puzzle-game
