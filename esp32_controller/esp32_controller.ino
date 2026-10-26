// ====================================================================
// TAY CAM BOMBERMAN PRO (TU CAN TAM, LOC NHIEU, KHOA HUONG MUOT MA)
// ====================================================================

const int PIN_VRX = 34;   // Truc X Joystick
const int PIN_VRY = 35;   // Truc Y Joystick
const int PIN_BOMB = 25;  // Nut bam 3 chan dat bom

// Diem tam nghi tu dong do
int centerX = 2048;
int centerY = 2048;

// Vung chet (Deadzone) quanh tam de loai bo troi can
const int DEADZONE = 450;

// Truc uu tien hien tai (0: Dung yen, 1: Ngang X, 2: Doc Y)
int activeAxis = 0;

// Ham doc lay trung binh 4 lan de khu sach nhieu ADC cua ESP32
int readSmooth(int pin) {
  int sum = 0;
  for (int i = 0; i < 4; i++) {
    sum += analogRead(pin);
  }
  return sum / 4;
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_BOMB, INPUT_PULLUP);

  // Tu dong do 30 mau de tim diem tam chinh xac cua can Joystick
  long sumX = 0, sumY = 0;
  for (int i = 0; i < 30; i++) {
    sumX += analogRead(PIN_VRX);
    sumY += analogRead(PIN_VRY);
    delay(10);
  }
  centerX = sumX / 30;
  centerY = sumY / 30;
}

void loop() {
  int rawX = readSmooth(PIN_VRX);
  int rawY = readSmooth(PIN_VRY);
  int btnVal = digitalRead(PIN_BOMB);

  // Tinh do lech so voi vi tri tam nghi
  int diffX = rawX - centerX;
  int diffY = rawY - centerY;

  int absX = abs(diffX);
  int absY = abs(diffY);

  int dx = 0;
  int dy = 0;

  // Neu gat can ra khoi vung chet
  if (absX > DEADZONE || absY > DEADZONE) {
    // Thuat toan khoa huong: chi cho phep di 1 huong manh nhat
    if (activeAxis == 1) {
      if (absY > absX * 1.25) activeAxis = 2; // Dang di ngang, muon re doc thi luc doc phai vuot troi
    } else if (activeAxis == 2) {
      if (absX > absY * 1.25) activeAxis = 1; // Dang di doc, muon re ngang thi luc ngang phai vuot troi
    } else {
      activeAxis = (absX >= absY) ? 1 : 2;
    }

    if (activeAxis == 1) {
      dx = (diffX > 0) ? 1 : -1;
      dy = 0;
    } else {
      dx = 0;
      dy = (diffY > 0) ? 1 : -1;
    }
  } else {
    activeAxis = 0; // Tha tay can ve giua
  }

  // Doc nut bam dat bom (1 la bam, 0 la tha)
  int bomb = (btnVal == LOW) ? 1 : 0;

  // Gui goi tin toc do cao
  Serial.print(dx);
  Serial.print(",");
  Serial.print(dy);
  Serial.print(",");
  Serial.println(bomb);

  delay(15); // ~66Hz, dong bo muot ma voi 60 FPS cua game
}
